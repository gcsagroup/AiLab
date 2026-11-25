'use strict';
// Byte-preserving transforms from stable-diffusion.cpp 532d2c1, scripts/convert_sefi.py
// and convert_qwen3_vl.py. Tensor payloads stream through a bounded buffer.
const fs=require('node:fs/promises');
const mappings={
  context_embedder:'txt_in',x_embedder:'img_in',proj_out:'final_layer.linear','norm_out.linear':'final_layer.adaLN_modulation.1',
  'norm1.linear':'img_mod.lin','norm1_context.linear':'txt_mod.lin','attn.norm_q.weight':'img_attn.norm.query_norm.scale',
  'attn.norm_k.weight':'img_attn.norm.key_norm.scale','attn.norm_added_q.weight':'txt_attn.norm.query_norm.scale',
  'attn.norm_added_k.weight':'txt_attn.norm.key_norm.scale','attn.to_out.0':'img_attn.proj','attn.to_add_out':'txt_attn.proj',
  'ff.net.0.proj':'img_mlp.0','ff.net.2':'img_mlp.2','ff_context.net.0.proj':'txt_mlp.0','ff_context.net.2':'txt_mlp.2',
  'ff.linear_in':'img_mlp.0','ff.linear_out':'img_mlp.2','ff_context.linear_in':'txt_mlp.0','ff_context.linear_out':'txt_mlp.2',
};
const single={'norm.linear':'modulation.lin','attn.norm_q.weight':'norm.query_norm.scale',
  'attn.norm_k.weight':'norm.key_norm.scale','attn.to_qkv_mlp_proj':'linear1','attn.to_out':'linear2'};
function rename(key,encoder) {
  if (encoder) return key.replace(/^model\.language_model\./,'model.');
  const root=key.replace(/^backbone\./,'');
  const block=/^(single_)?transformer_blocks\.(\d+)\.(.+)$/.exec(root);
  const prefix=block ? (block[1]?'single_blocks.':'double_blocks.')+block[2]+'.' : '';
  const tail=block?.[3] || root;
  const names=block?.[1] ? single : mappings;
  const suffix=/\.(weight|bias)$/.exec(tail)?.[0] || '';
  if (Object.hasOwn(names,tail)) return prefix+names[tail];
  const base=suffix ? tail.slice(0,-suffix.length) : tail;
  if (Object.hasOwn(names,base)) return prefix+names[base]+suffix;
  return prefix+tail.replace(/^(double_stream_modulation_(?:img|txt)|single_stream_modulation)\.linear\./,'$1.lin.');
}
async function readExact(handle,offset,bytes) {
  const dest=Buffer.alloc(bytes);
  for(let pos=0;pos<bytes;) {
    const {bytesRead}=await handle.read(dest,pos,bytes-pos,offset+pos);
    if (!bytesRead) throw Error('SeFi 权重文件不完整。');
    pos+=bytesRead;
  }
  return dest;
}
async function rewrite(files,output,encoder,signal) {
  const handles=[], entries=new Map();
  try {
    for(const file of files) {
      const handle=await fs.open(file,'r');handles.push(handle);
      const size=(await handle.stat()).size,headerSize=Number((await readExact(handle,0,8)).readBigUInt64LE());
      if (!Number.isSafeInteger(headerSize) || headerSize>64*1024**2 || headerSize+8>size) throw Error('SeFi 文件头无效。');
      const base=8+headerSize, header=JSON.parse((await readExact(handle,8,headerSize)).toString('utf8'));
      for(const [name,t] of Object.entries(header)) {
        if(name==='__metadata__') continue;
        const [start,end]=t.data_offsets;
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start<0 || end<start || base+end>size)
          throw Error('SeFi 张量范围无效。');
        const dest=rename(name,encoder);
        if(entries.has(dest)) throw Error('SeFi 分片包含重复张量：'+dest);
        const count=end-start,begin=base+start;
        const swap=!encoder && /^final_layer\.adaLN_modulation\.1\.(weight|bias)$/.test(dest);
        if (swap && (t.shape[0]%2 || count%2)) throw Error('SeFi 末层调制维度无效。');
        entries.set(dest,{dtype:t.dtype,shape:t.shape,parts:swap ? [[handle,begin+count/2,count/2],[handle,begin,count/2]] : [[handle,begin,count]]});
      }
    }
    for(const [key,q] of [...entries]) {
      const match=/^(double_blocks\.\d+\.)attn\.(to_q|add_q_proj)\.weight$/.exec(key);
      if (!match) continue;
      const image=match[2]==='to_q', prefix=match[1], names=['q','k','v'].map(v=>prefix+'attn.'+(image?'to_'+v:'add_'+v+'_proj')+'.weight');
      const triplet=names.map(k=>entries.get(k));
      if (triplet.some(t=>!t || t.dtype!==q.dtype || JSON.stringify(t.shape)!==JSON.stringify(q.shape)))
        throw Error('SeFi 注意力 Q/K/V 组件不匹配。');
      const dest=prefix+(image?'img_attn':'txt_attn')+'.qkv.weight';
      if (entries.has(dest)) throw Error('SeFi 重复的 QKV 张量。');
      for(const n of names) entries.delete(n);
      entries.set(dest,{dtype:q.dtype,shape:[3*q.shape[0],...q.shape.slice(1)],parts:triplet.flatMap(t=>t.parts)});
    }
    const keys=[...entries.keys()].sort(),header=Object.create(null);let end=0;
    for(const k of keys) {
      const {dtype,shape,parts}=entries.get(k),start=end;
      end+=parts.reduce((len,p)=>len+p[2],0);
      header[k]={dtype,shape,data_offsets:[start,end]};
    }
    const json=Buffer.from(JSON.stringify(header)),len=Math.ceil(json.length/8)*8,buf=Buffer.alloc(8+len,32);
    buf.writeBigUInt64LE(BigInt(len));json.copy(buf,8);
    const dest=await fs.open(output,'wx');
    try {
      await dest.writeFile(buf);
      for(const k of keys) for(const [handle,start,size] of entries.get(k).parts) {
        for(let copied=0;copied<size;) {
          signal?.throwIfAborted();
          const block=await readExact(handle,start+copied,Math.min(4*1024**2,size-copied));
          await dest.writeFile(block);copied+=block.length;
        }
      }
    } finally {await dest.close();}
  } finally {await Promise.all(handles.map(f=>f.close()));}
}
module.exports={rewrite};
