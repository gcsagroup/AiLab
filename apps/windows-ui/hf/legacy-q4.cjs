'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {cachedLayout} = require('./cached-layout.cjs');
const {metadata} = require('./gguf-metadata.cjs');

async function readAt(file, buffer, position) {
  for (let done=0; done<buffer.length;) {
    const {bytesRead}=await file.read(buffer,done,buffer.length-done,position+done);
    if (!bytesRead) throw Error('旧版 Q4 GGUF 文件被截断。');
    done+=bytesRead;
  }
}
async function writeAt(file, buffer, position) {
  for (let done=0; done<buffer.length;) {
    const {bytesWritten}=await file.write(buffer,done,buffer.length-done,position+done);
    if (!bytesWritten) throw Error('写入 Q4 GGUF 失败。');
    done+=bytesWritten;
  }
}

// Reverse ggml's historical make_block_q4_0x4 / make_block_q4_0x8. Each
// input packet contains the same column block from four or eight rows.
function unpack(input, output, blocks, rows, stripe) {
  const rowBytes=blocks*18, groupBytes=rowBytes*rows;
  for (let group=0; group<input.length; group+=groupBytes) {
    for (let column=0; column<blocks; column++) {
      const packet=group+column*rows*18, quants=packet+rows*2;
      for (let row=0; row<rows; row++) {
        const target=group+row*rowBytes+column*18;
        output.writeUInt16LE(input.readUInt16LE(packet+row*2),target);
        for (let i=0; i<16; i+=stripe) {
          const at=quants+i*rows+row*stripe;
          for (let j=0; j<stripe; j+=4) {
            output.writeInt32LE(input.readInt32LE(at+j)^0x88888888,target+2+i+j);
          }
        }
      }
    }
  }
}

async function convert(source, target, size, signal) {
  const directory=metadata(source,true);
  const space=await fs.statfs(path.dirname(target));
  if (space.bavail*space.bsize < size+64*1024**2)
    throw Error('旧版交错 Q4 GGUF 首次试用需要额外 '+(size/1024**3).toFixed(2)+' GiB 磁盘空间。');
  await fs.copyFile(source,target,fs.constants.COPYFILE_EXCL|fs.constants.COPYFILE_FICLONE);
  const file=await fs.open(target,'r+');
  try {
    const scalar=Buffer.alloc(4);
    let alignment=32;
    for (const field of directory.fields) {
      if (!['general.alignment','general.file_type'].includes(field.key)) continue;
      if (field.type!==4 || field.end-field.start!==8) throw Error('GGUF 量化元数据无效。');
      await readAt(file,scalar,field.end-4);
      const value=scalar.readUInt32LE();
      if (field.key==='general.alignment') alignment=value;
      else if (value>=33 && value<=35) {
        scalar.writeUInt32LE(2);
        await writeAt(file,scalar,field.end-4);
      }
    }
    if (!alignment || alignment>65536 || (alignment & (alignment-1))) throw Error('GGUF 对齐值无效。');
    const start=Math.ceil(directory.headerEnd/alignment)*alignment;
    const tensors=directory.tensors.sort((a,b)=>a.offset-b.offset);
    for (const [index,t] of tensors.entries()) {
      if (t.type<31 || t.type>33) continue;
      const rows=t.type===33?8:4, stripe=t.type===31?4:8;
      const blocks=t.shape[0]/32, groupBytes=rows*blocks*18;
      const totalRows=t.shape.slice(1).reduce((v,n)=>v*n,1);
      const bytes=totalRows*blocks*18, position=start+t.offset;
      const next=index+1<tensors.length?start+tensors[index+1].offset:size;
      if (t.shape.length<2 || !t.shape.every(n=>Number.isSafeInteger(n) && n>0) ||
          !Number.isInteger(blocks) || t.shape[1]%rows || groupBytes>64*1024**2 ||
          !Number.isSafeInteger(position+bytes) || position+bytes>next || next>size)
        throw Error('旧版 Q4 交错矩阵形状或数据范围无效。');
      const chunk=Math.min(bytes,Math.max(1,Math.floor(2*1024**2/groupBytes))*groupBytes);
      const packed=Buffer.allocUnsafe(chunk), native=Buffer.allocUnsafe(chunk);
      for (let offset=0; offset<bytes; offset+=chunk) {
        signal?.throwIfAborted();
        const length=Math.min(chunk,bytes-offset), src=packed.subarray(0,length), dst=native.subarray(0,length);
        await readAt(file,src,position+offset);
        unpack(src,dst,blocks,rows,stripe);
        await writeAt(file,dst,position+offset);
      }
      scalar.writeUInt32LE(2);
      await writeAt(file,scalar,t.typePosition);
    }
    await file.sync();
  } finally {await file.close();}
}

async function prepareShards(files, out, identity, signal, linkWeight) {
  if (!files.some(file=>metadata(file).legacyQ4)) return files[0];
  const dir=files.length>1?await fs.mkdtemp(path.join(out,'q4-shards-')):null;
  let main;
  for (const [i,file] of files.entries()) {
    let prepared=file;
    if (metadata(file).legacyQ4) {
      const {size}=await fs.stat(file);
      prepared=await cachedLayout(file,'q4',identity,size,signal,target=>convert(file,target,size,signal));
    }
    if (!dir) return prepared;
    const name='model-'+String(i+1).padStart(5,'0')+'-of-'+String(files.length).padStart(5,'0')+'.gguf';
    const member=path.join(dir,name);
    await linkWeight(prepared,member);
    if (!i) main=member;
  }
  return main;
}
module.exports={prepareShards,unpack};
