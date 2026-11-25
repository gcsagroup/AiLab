'use strict';
const fs=require('node:fs');
const path=require('node:path');
const {pipeline}=require('node:stream/promises');
const {metadata}=require('./gguf-metadata.cjs');
const {blocks}=require('./granite-swa-layout.cjs');
const {cachedLayout}=require('./cached-layout.cjs');
const projectorName='mmproj-cogvlm-chat-hf';
function publishedProjector(repo,f) {
  return repo?.toLowerCase()==='pandaexpresspatron/cogvlm-chat-gguf' && f.path===projectorName &&
    f.size===8858987936 && f.sha256==='aa2e53f40d8248738fc79f790227fde7f564bce870e496db89b5e90425fa1a4b';
}

// The original F16 release stores Q, K and V consecutively for both
// language and vision experts. The mainline graph reads those same rows
// through one descriptor. A small string field keeps the payload start fixed.
function joinedHeader(file) {
  const {fields,tensors,alignment,headerEnd}=metadata(file,true);
  const fail=()=>{throw Error('CogVLM 的 Q/K/V 矩阵形状或存储顺序不兼容。');};
  if (!fields.length || headerEnd>128*1024**2 || !alignment || (alignment & (alignment-1))) fail();
  const base=Math.ceil(headerEnd/alignment)*alignment, prefixEnd=fields.at(-1).end;
  const head=Buffer.alloc(base), fd=fs.openSync(file,'r');
  try {if (fs.readSync(fd,head,0,base,0)!==base) fail();} finally {fs.closeSync(fd);}
  const desc=[], byName=new Map(tensors.map(t=>[t.name,t]));
  if (byName.size!==tensors.length) fail();
  const skip=new Set(); let cursor=prefixEnd,joined=0;
  for (const t of tensors) {
    const end=t.typePosition+12;
    const match=/^((?:v\.)?blk\.\d+\.(?:vis_)?attn_)q\.(weight|bias)$/.exec(t.name);
    if (match) {
      const name=match[1]+'qkv.'+match[2], rank=match[2]==='bias' ? 1 : 2;
      if (byName.has(name) || t.shape.length!==rank || !blocks[t.type]) fail();
      const [values,bytes]=blocks[t.type], length=t.shape[0]/values*(t.shape[1] ?? 1)*bytes;
      if (t.shape[0]%values || !Number.isSafeInteger(length) || length<=0 || length%alignment) fail();
      for (const [i,key] of ['k','v'].entries()) {
        const other=byName.get(match[1]+key+'.'+match[2]);
        if (!other || other.type!==t.type || other.shape.length!==rank || other.shape.some((v,j)=>v!==t.shape[j]) ||
            other.offset!==t.offset+(i+1)*length || other.typePosition<t.typePosition) fail();
        skip.add(other.name);
      }
      const bytesName=Buffer.from(name), entry=Buffer.alloc(8+bytesName.length+4+rank*8+4+8);
      entry.writeBigUInt64LE(BigInt(bytesName.length));bytesName.copy(entry,8);
      const pos=8+bytesName.length;
      entry.writeUInt32LE(rank,pos);
      t.shape.forEach((dim,i)=>entry.writeBigUInt64LE(BigInt(dim)*(i===rank-1?3n:1n),pos+4+i*8));
      entry.writeUInt32LE(t.type,pos+4+rank*8);
      entry.writeBigUInt64LE(BigInt(t.offset),pos+8+rank*8);
      desc.push(entry);joined++;
    } else if (!skip.has(t.name)) desc.push(head.subarray(cursor,end));
    cursor=end;
  }
  if (!joined || cursor!==headerEnd || fields.some(f=>f.key==='ailab.layout_padding')) fail();
  const data=Buffer.concat(desc), key=Buffer.from('ailab.layout_padding');
  const padding=Buffer.alloc(base-prefixEnd-data.length);
  if (padding.length<20+key.length) fail();
  padding.writeBigUInt64LE(BigInt(key.length));key.copy(padding,8);
  padding.writeUInt32LE(8,8+key.length);padding.writeBigUInt64LE(BigInt(padding.length-20-key.length),12+key.length);
  padding.fill(32,20+key.length);
  const prefix=head.subarray(0,prefixEnd);
  prefix.writeBigUInt64LE(BigInt(desc.length),8);prefix.writeBigUInt64LE(BigInt(fields.length+1),16);
  return Buffer.concat([prefix,padding,data]);
}

async function joinInPrivateFile(file) {
  const header=joinedHeader(file), fd=await fs.promises.open(file,'r+');
  try {
    let pos=0;
    while (pos<header.length) pos+=(await fd.write(header,pos,header.length-pos,pos)).bytesWritten;
  } finally {await fd.close();}
}

async function preparedCog(file,manifest,signal,role='model') {
  const bytes=(await fs.promises.stat(file)).size;
  return cachedLayout(file,role==='projector'?'cogvlm-proj2':'cogvlm',manifest,bytes,signal,async partial=>{
    const disk=await fs.promises.statfs(path.dirname(file));
    if (disk.bavail*disk.bsize<bytes+64*1024**2) throw Error('准备 CogVLM 注意力矩阵所需的磁盘空间不足。');
    const header=joinedHeader(file);
    await fs.promises.writeFile(partial,header,{flag:'wx'});
    await pipeline(fs.createReadStream(file,{start:header.length}),fs.createWriteStream(partial,{flags:'a'}),{signal});
    if (role==='projector') {
      const pos=metadata(file,true).tensors.find(t=>t.name==='v.position_embd.weight');
      // The legacy export retains HF's [CLS, patches] positional table.
      // mtmd appends CLS after the patches and drops that final row.
      if (pos) {
        if (pos.type!==0 || pos.shape.length!==2 || pos.shape[0]!==1792 || pos.shape[1]!==1226)
          throw Error('CogVLM 视觉位置嵌入的布局不兼容。');
        const rowBytes=pos.shape[0]*4, data=Buffer.alloc(rowBytes*pos.shape[1]);
        const offset=header.length+pos.offset,fd=await fs.promises.open(partial,'r+');
        try {
          if ((await fd.read(data,0,data.length,offset)).bytesRead!==data.length) throw Error('CogVLM 位置嵌入不完整。');
          const cls=require('node:crypto').createHash('sha256').update(data.subarray(0,rowBytes)).digest('hex');
          if (cls!=='9fdbf841ef0f75fc8d9726d443eec4b5bad658a0b53ae9493b16afc68a93f405') return;
          const rotated=Buffer.concat([data.subarray(rowBytes),data.subarray(0,rowBytes)]);
          let done=0;
          while(done<rotated.length) done+=(await fd.write(rotated,done,rotated.length-done,offset+done)).bytesWritten;
        } finally {await fd.close();}
      }
    }
  });
}
module.exports={joinInPrivateFile,preparedCog,publishedProjector,projectorName};
