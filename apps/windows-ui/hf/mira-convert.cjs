'use strict';
// Tensor layout for the pinned YatharthS/MiraTTS release. Offsets are valid only
// for the verified component digests. No ONNX execution or pickle evaluation.
const fs=require('node:fs/promises');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {Worker,isMainThread,workerData}=require('node:worker_threads');
const layout=require('./mira-layout.json');
const widths={F32:4,F16:2,I32:4,I64:8};
function readTensor(input,[start,shape,type,operation]) {
  const count=shape.reduce((n,s)=>n*s,1), bytes=count*widths[type];
  if (!Number.isSafeInteger(bytes) || start<0 || start+bytes>input.length) throw Error('MiraTTS 组件的张量范围无效。');
  const raw=input.subarray(start,start+bytes);
  if (operation==='to-f32') {
    const data=Buffer.alloc(count*4);
    for(let i=0;i<count;i++) {
      const half=raw.readUInt16LE(i*2),exp=(half>>10)&31,m=half&1023;
      const value=exp ? 2**(exp-15)*(1+m/1024) : m*2**-24;
      data.writeFloatLE(half&32768 ? -value : value,i*4);
    }
    return {data,shape,dtype:'F32'};
  }
  if (operation!=='transpose') return {data:raw,shape,dtype:type};
  if (shape.length!==2) throw Error('MiraTTS 投影矩阵维数无效。');
  const [rows,cols]=shape,width=widths[type],data=Buffer.alloc(bytes);
  for(let r=0;r<rows;r++) for(let c=0;c<cols;c++) {
    const original=(r*cols+c)*width;
    raw.copy(data,(c*rows+r)*width,original,original+width);
  }
  return {data,shape:[cols,rows],dtype:type};
}
async function writeTensors(name,tensors) {
  let position=0;
  const header={};
  for (const [key,{data,shape,dtype}] of Object.entries(tensors)) {
    header[key]={dtype,shape,data_offsets:[position,position+data.length]};position+=data.length;
  }
  const json=Buffer.from(JSON.stringify(header)),padded=Math.ceil(json.length/8)*8;
  const buffer=Buffer.alloc(8+padded,32);buffer.writeBigUInt64LE(BigInt(padded));json.copy(buffer,8);
  const handle=await fs.open(name,'wx');
  try {
    await handle.writeFile(buffer);
    for(const {data} of Object.values(tensors)) await handle.writeFile(data);
  } finally {await handle.close();}
}
function upsampler(source) {
  const out={};
  function fused(name) {
    const gain=source[name+'.weight_g'], direction=source[name+'.weight_v'];
    const data=Buffer.alloc(direction.data.length), rows=direction.shape[0], columns=data.length/(4*rows);
    for(let r=0;r<rows;r++) {
      let squares=0;
      for(let i=0;i<columns;i++) squares+=direction.data.readFloatLE((r*columns+i)*4)**2;
      const scale=gain.data.readFloatLE(r*4)/Math.max(Math.sqrt(squares),1e-12);
      for(let i=0;i<columns;i++) {
        const offset=(r*columns+i)*4;
        data.writeFloatLE(direction.data.readFloatLE(offset)*scale,offset);
      }
    }
    return {...direction,data};
  }
  function convolution(original,target) {
    out[target+'.weight']=fused(original);
    out[target+'.bias']=source[original+'.bias'];
  }
  function activation(original,target) {
    for(const [suffix,inverse] of [['alpha',false],['beta',true]]) {
      const x=source[original+'.'+suffix], data=Buffer.alloc(x.data.length);
      for(let i=0;i<data.length;i+=4) {
        const exp=Math.exp(x.data.readFloatLE(i));data.writeFloatLE(inverse?1/(exp+1e-9):exp,i);
      }
      out[target+(inverse?'.inv_beta':'.alpha')]={dtype:'F32',shape:[1,32,1],data};
    }
  }
  convolution('dec.conv_pre','upsampler.conv_pre');
  out['upsampler.conv_post.weight']=source['dec.conv_post.weight'];
  out['upsampler.activation_filter']=source['dec.activation_post.upsample.filter'];
  for(const block of [0,2]) {
    for(const group of [1,2]) for(let i=0;i<3;i++) {
      const name='resblocks.'+block+'.convs'+group+'.'+i;
      convolution('dec.'+name,'upsampler.'+name);
    }
    for(let i=0;i<6;i++) {
      const name='resblocks.'+block+'.activations.'+i;
      activation('dec.'+name+'.act','upsampler.'+name);
    }
  }
  activation('dec.activation_post.act','upsampler.activation_post');
  return Object.fromEntries(Object.entries(out).map(([name,tensor])=>[name.slice('upsampler.'.length),tensor]));
}
async function convertAuxiliary(dir) {
  for (const [group,filename] of [['speaker_encoder','s_encoder.onnx'],['processor','processer.onnx'],['upsampler','upsampler.pth']]) {
    const raw=await fs.readFile(path.join(dir,'decoders',filename));
    if (createHash('sha256').update(raw).digest('hex')!==layout.source_sha256[filename]) throw Error('MiraTTS 组件版本不匹配：'+filename);
    const entries=Object.fromEntries(Object.entries(layout[group]).map(([name,info])=>[name,readTensor(raw,info)]));
    await writeTensors(path.join(dir,group+'.safetensors'),group==='upsampler'?upsampler(entries):entries);
  }
}
function convertInWorker(dir,signal) {
  return new Promise((resolve,reject)=>{
    if (signal?.aborted) return reject(Error('运行已停止。'));
    const worker=new Worker(__filename,{workerData:{dir}});
    const stop=()=>worker.terminate();
    signal?.addEventListener('abort',stop,{once:true});
    worker.once('error',reject);
    worker.once('exit',code=>{
      signal?.removeEventListener('abort',stop);
      if(signal?.aborted) reject(Error('运行已停止。'));
      else if(code) reject(Error('MiraTTS 组件转换失败。'));
      else resolve();
    });
  });
}
if (!isMainThread && workerData?.dir) convertAuxiliary(workerData.dir).catch(error=>{setImmediate(()=>{throw error;});});
module.exports={convertInWorker};
