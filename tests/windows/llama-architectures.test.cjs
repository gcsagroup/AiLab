'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const registry = require('../../apps/windows-ui/hf/llama-architectures.json');
const { metadata } = require('../../apps/windows-ui/hf/gguf-metadata.cjs');
const { bundle, localExtras } = require('../../apps/windows-ui/hf/gguf-bundle.cjs');
const { flags, structuredInput } = require('../../apps/windows-ui/hf/llama-service.cjs');

test('a bounded CPU service uses the published model with lazy mapping and no repacking', () => {
  const file='C:\\local models\\test.gguf';
  const args=flags(file,{kind:'text'},{device_id:'cpu',cpu_no_repack:true,cpu_working_set_mib:8192},{},'test');
  assert.ok(args.includes('--no-repack'));
  assert.equal(args[args.indexOf('--load-mode')+1],'mmap');
  assert.equal(args[args.indexOf('--lazy-mode')+1],'on');
  assert.ok(args.includes(file));
});

test('Windows applies and verifies the working-set ceiling before starting the bundled service', {skip:process.platform!=='win32'}, ()=>{
  const runtime=path.resolve(__dirname,'../../apps/windows-ui/runtime/text');
  const worker=path.join(runtime,'ailab-gguf.exe');
  const launch=(floor,max)=>require('node:child_process').spawnSync(worker,['--bounded-service',floor,max,'--version'],{cwd:runtime,encoding:'utf8',windowsHide:true});
  const success=launch('64','512');
  assert.equal(success.status,0,success.stderr+success.stdout);
  assert.match(success.stderr,/resident limit 512 MiB/);
  assert.match(success.stdout+success.stderr,/version:.*build \d+/i);
  const failed=launch('513','512');
  assert.notEqual(failed.status,0);
  assert.match(failed.stdout,/Insufficient physical memory/);
});

test('old ARM Q4 layouts recover each row and column without re-quantizing', () => {
  const {unpack}=require('../../apps/windows-ui/hf/legacy-q4.cjs');
  const {useService}=require('../../apps/windows-ui/hf/llama-service.cjs');
  assert.equal(useService({kind:'text',chat:false,legacyQ4:true}),true);
  for (const [rows,stripe] of [[4,4],[4,8],[8,8]]) {
    const blocks=3, groups=2;
    const native=Buffer.alloc(rows*blocks*groups*18);
    for (let i=0;i<native.length;i++) native[i]=(i*37+Math.floor(i/17))&255;
    const packed=[];
    for (let group=0;group<groups;group++) {
      for (let column=0;column<blocks;column++) {
        const rowBlocks=Array.from({length:rows},(_,row)=>{
          const start=((group*rows+row)*blocks+column)*18;
          return native.subarray(start,start+18);
        });
        for (const block of rowBlocks) packed.push(block[0],block[1]);
        for (let i=2;i<18;i+=stripe) {
          for (const block of rowBlocks) {
            for (const value of block.subarray(i,i+stripe)) packed.push(value^0x88);
          }
        }
      }
    }
    const restored=Buffer.alloc(native.length);
    unpack(Buffer.from(packed),restored,blocks,rows,stripe);
    assert.deepEqual(restored,native);
  }
});

// Metadata-only fixtures exercise catalog/import dispatch without loading any model weights.
function gguf(arch, fields = {}, tensor = 'token_embd.weight') {
  const u32 = (n) => {
    const b = Buffer.alloc(4);
    b.writeUInt32LE(n);
    return b;
  };
  const u64 = (n) => {
    const b = Buffer.alloc(8);
    b.writeBigUInt64LE(BigInt(n));
    return b;
  };
  const str = (s) => Buffer.concat([u64(Buffer.byteLength(s)), Buffer.from(s)]);
  const pairs = Object.entries({
    'general.architecture': arch,
    'tokenizer.ggml.tokens': ['test'],
    ...fields,
  });
  const tensors = typeof tensor === 'string' ? [[tensor, [1]]] : tensor;
  const blocks = [Buffer.from('GGUF'), u32(3), u64(tensors.length), u64(pairs.length)];
  for (const [key, value] of pairs) {
    blocks.push(str(key));
    if (typeof value === 'boolean') blocks.push(u32(7), Buffer.from([Number(value)]));
    else if (typeof value === 'number') blocks.push(u32(4), u32(value));
    else if (Array.isArray(value) && value.every(n => typeof n === 'number'))
      blocks.push(u32(9), u32(5), u64(value.length), ...value.map(u32));
    else if (Array.isArray(value)) blocks.push(u32(9), u32(8), u64(value.length), ...value.map(str));
    else blocks.push(u32(8), str(value));
  }
  for (const [name, shape, type = 0, offset = 0] of tensors)
    blocks.push(str(name), u32(shape.length), ...shape.map(u64), u32(type), u64(offset));
  return Buffer.concat(blocks);
}
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ailab-arch-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  return (file, arch, fields, tensor) => {
    const p = path.join(dir, file + '.gguf');
    fs.writeFileSync(p, gguf(arch, fields, tensor));
    return p;
  };
}
test('compact text converts every expert plane and preserves the router', {skip:process.platform!=='win32'}, async t => {
  const {bins,invoke}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  if (!fs.existsSync(bins.text)) return t.skip('Windows GGUF worker unavailable');
  const write=fixture(t), name='blk.0.ffn_up_exps.weight';
  const file=write('base','rnd1',{},[[name,[32,2,2],8,0],['blk.0.ffn_gate_inp.weight',[2,2],0,160]]);
  const values=Buffer.alloc(192);
  for (let i=0;i<4;i++) {
    values.writeUInt16LE(0x3c00,i*34);
    values.fill(i+1,i*34+2,(i+1)*34);
  }
  values.writeFloatLE(0.75,160);
  fs.appendFileSync(file,Buffer.concat([Buffer.alloc((32-fs.statSync(file).size%32)%32),values]));
  const out=file+'.prepared';
  await invoke(bins.text,[],{input:{action:'compact-language',cpu_only:true,model:file,output:out,matrices:[name]}});
  const info=metadata(out,true);
  assert.deepEqual(info.tensors.map(t=>[t.type,t.shape,t.offset]),[[2,[32,2,2],0],[0,[2,2],96]]);
  const raw=fs.readFileSync(out), start=Math.ceil(info.headerEnd/32)*32;
  assert.equal(raw.readFloatLE(start+96),0.75);
  assert.equal(new Set([0,1,2,3].map(i=>raw.readUInt16LE(start+i*18))).size,4);
  assert.equal(metadata(out).compactTextBytes,undefined);
  const streamOut=file+'.streamed';
  const request={action:'compact-language',cpu_only:true,model:file,output:streamOut,matrices:[name],stream_payload:true};
  const worker=require('node:child_process').spawnSync(bins.text,[],{
    cwd:path.dirname(bins.text),windowsHide:true,
    input:Buffer.concat([Buffer.from(JSON.stringify(request)+'\n'),fs.readFileSync(file)]),
  });
  assert.equal(worker.status,0,worker.stdout.toString()+worker.stderr.toString());
  assert.deepEqual(fs.readFileSync(streamOut),raw);
});
test('CogVLM joins legacy Q/K/V rows without shifting or rewriting the tensor payload', async t=>{
  const write=fixture(t),rows=['q','k','v'].map((n,i)=>['blk.0.attn_'+n+'.weight',[16,2],1,i*64]);
  const file=write('separate','cogvlm',{},rows);
  const bytes=Buffer.from(Array.from({length:192},(_,i)=>i));
  fs.appendFileSync(file,Buffer.concat([Buffer.alloc((32-fs.statSync(file).size%32)%32),bytes]));
  assert.equal(metadata(file).legacyCogQkv,true);
  const dest=await require('../../apps/windows-ui/hf/cogvlm-layout.cjs').preparedCog(file,'fixture');
  const h=metadata(dest,true);
  assert.deepEqual(h.tensors.map(v=>[v.name,v.shape,v.offset]),[['blk.0.attn_qkv.weight',[16,6],0]]);
  assert.deepEqual(fs.readFileSync(dest).subarray(Math.ceil(h.headerEnd/32)*32),bytes);
  assert.equal(fs.statSync(dest).size,fs.statSync(file).size);
  assert.equal(metadata(dest).legacyCogQkv,undefined);
});
test('CogVLM vision folds separate QKV biases and weights at the original offsets',async t=>{
  const write=fixture(t), rows=[];
  for (const [i,axis] of ['q','k','v'].entries()) rows.push(['v.blk.0.attn_'+axis+'.bias',[8],0,i*32]);
  for (const [i,axis] of ['q','k','v'].entries()) rows.push(['v.blk.0.attn_'+axis+'.weight',[8,2],1,96+i*32]);
  const source=write('vision','clip',{'clip.projector_type':'cogvlm'},rows);
  const payload=Buffer.from(Array.from({length:192},(_,i)=>i));
  fs.appendFileSync(source,Buffer.concat([Buffer.alloc((32-fs.statSync(source).size%32)%32),payload]));
  assert.equal(metadata(source).legacyCogProjector,true);
  const packed=await require('../../apps/windows-ui/hf/cogvlm-layout.cjs').preparedCog(source,'fixture',undefined,'projector');
  const directory=metadata(packed,true);
  assert.deepEqual(directory.tensors.map(v=>[v.name,v.shape,v.offset]),[
    ['v.blk.0.attn_qkv.bias',[24],0],['v.blk.0.attn_qkv.weight',[8,6],96]]);
  assert.deepEqual(fs.readFileSync(packed).subarray(-192),payload);
  assert.equal(metadata(packed).legacyCogProjector,undefined);
});
test('low-memory expert formats preserve GGUF rank and selectively convert the routed matrices', {skip:process.platform!=='win32'}, async t => {
  const {bins,invoke}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  if (!fs.existsSync(bins.text)) return t.skip('Windows GGUF worker unavailable');
  const write=fixture(t),name='blk.0.ffn_down_exps.weight';
  for (const [arch,fromType,sourceBytes,toType] of [['mistral4',19,200,41],['kimi-k3',8,1088,42],['maion-coder',2,576,41]]) {
    const offset=Math.ceil(sourceBytes/32)*32;
    const file=write(arch,arch,{},[[name,[256,2,2],fromType,0],['blk.0.ffn_gate_inp.weight',[2,2],0,offset]]);
    const payload=Buffer.alloc(offset+32);
    payload.writeFloatLE(-1.5,offset);
    fs.appendFileSync(file,Buffer.concat([Buffer.alloc((32-fs.statSync(file).size%32)%32),payload]));
    const out=file+'.prepared';
    await invoke(bins.text,[],{input:{action:'compact-language',cpu_only:true,model:file,output:out,matrices:[name]}});
    const h=metadata(out,true);
    assert.equal(metadata(out).cpuNoRepack,true);
    assert.deepEqual(h.tensors[0].shape,[256,2,2]);
    assert.equal(h.tensors[0].type,toType);
    const router=Math.ceil(h.headerEnd/32)*32+h.tensors[1].offset;
    assert.equal(fs.readFileSync(out).readFloatLE(router),-1.5);
  }
});
test('a low-disk model import verifies the selected source and persists a private compact copy', {skip:process.platform!=='win32'}, async t => {
  const {bins}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  if (!fs.existsSync(bins.text)) return t.skip('Windows GGUF worker unavailable');
  const {Trials}=require('../../apps/windows-ui/hf/trials.cjs');
  const write=fixture(t), name='blk.0.ffn_gate_exps.weight', source=write('mai','maion-coder',{},[[name,[256,32,2],2,0]]);
  fs.appendFileSync(source,Buffer.alloc((32-fs.statSync(source).size%32)%32+9216));
  const info=metadata(source);
  assert.ok(info.compactTextBytes<info.size);
  t.mock.method(fs.promises,'statfs',async()=>({bavail:1,bsize:64*1024**2+info.compactTextBytes}));
  const profile=path.join(path.dirname(source),'profile'),project_id='project-compact';
  const trials=new Trials(profile,{records:()=>[]});
  const plan=await trials.inspectImport('models',{project_id,path:source});
  assert.equal(plan.warnings[0].code,'COMPACT_CPU_IMPORT');
  assert.match(plan.warnings[0].message,/Q1_0/);
  const model=await trials.confirmImport('models',plan);
  assert.equal(model.source_manifest_digest,plan.manifest_digest);
  assert.notEqual(model.manifest_digest,plan.manifest_digest);
  assert.equal(model.weight_conversion,'mixed_q1_0');
  assert.equal(metadata(model.path,true).tensors[0].type,41);
  const again=new Trials(profile,{records:()=>[]});
  await again.resolve(model.id,project_id).verify();
  const modified=await trials.inspectImport('models',{project_id,path:source});
  const fd=fs.openSync(source,'r+');
  try { fs.writeSync(fd,Buffer.from([1]),0,1,fs.statSync(source).size-1); } finally { fs.closeSync(fd); }
  await assert.rejects(trials.confirmImport('models',modified),/摘要不符/);
  assert.equal(trials.list('local',project_id).length,1);
});
test('Granite SWA restores IBM gate/up rows without modifying the weight bytes', async t => {
  const write=fixture(t),arch='granite_swa',gate='blk.0.ffn_gate_shexp.weight',up='blk.0.ffn_up_shexp.weight';
  const raw=write('swash',arch,{},[[gate,[4,4],30,0],['neighbor',[1],0,64],[up,[4,4],30,32]]);
  const payload=Buffer.from(Array.from({length:68},(_,i)=>i));
  const pad=(32-fs.statSync(raw).size%32)%32;
  fs.appendFileSync(raw,Buffer.concat([Buffer.alloc(pad),payload]));
  assert.equal(metadata(raw).legacyGraniteShared,true);
  const {preparedGraniteSwa}=require('../../apps/windows-ui/hf/granite-swa-layout.cjs');
  const file=await preparedGraniteSwa(raw);
  const prepared=metadata(file,true);
  assert.deepEqual(prepared.tensors.map(t=>[t.name,t.shape,t.offset]),[[up,[4,8],0],['neighbor',[1],64]]);
  assert.equal(metadata(file).legacyGraniteShared,undefined);
  assert.deepEqual(fs.readFileSync(file).subarray(Math.ceil(prepared.headerEnd/32)*32),payload);
  assert.equal(await preparedGraniteSwa(raw),file);
  const q4=write('swash-q4',arch,{},[[gate,[256,2],12,0],[up,[256,2],12,288]]);
  const data=Buffer.alloc(576,0xc3);
  fs.appendFileSync(q4,Buffer.concat([Buffer.alloc((32-fs.statSync(q4).size%32)%32),data]));
  const quantized=await preparedGraniteSwa(q4),qd=metadata(quantized,true);
  assert.deepEqual(qd.tensors.map(t=>[t.name,t.type,t.shape]),[[up,12,[256,4]]]);
  assert.deepEqual(fs.readFileSync(quantized).subarray(Math.ceil(qd.headerEnd/32)*32),data);
  const wrong=write('bad',arch,{},[[gate,[4,4],30,32],[up,[4,4],30,0]]);
  await assert.rejects(preparedGraniteSwa(wrong),/Granite SWA/);
});
test('Chameleon locates its conversation separator by vocabulary index', t => {
  const write=fixture(t);
  const tokens={'tokenizer.ggml.tokens':['x','<reserved08705>','<reserved08706>','y']};
  assert.equal(metadata(write('chameleon','chameleon',tokens)).chameleonSeparator,2);
  assert.equal(metadata(write('other','llama',tokens)).chameleonSeparator,undefined);
  assert.equal(metadata(write('custom','chameleon',{...tokens,'tokenizer.chat_template':'custom'})).chameleonSeparator,undefined);
});
test('direct-answer support follows the assistant prefix in the published reasoning template', t => {
  const write=fixture(t);
  for (const [arch,prefix,ending] of [
    ['maple','open-chatml','<|im_start|>assistant\\n<think>\\n'],
    ['limite','chatml','<|im_start|>assistant\\n'],
    ['arwkv7','deepseek','<｜Assistant｜>'],
    ['flint','flint','m.reasoning_content <|assistant|>'],
  ]) {
    const info=metadata(write(arch,arch,{'tokenizer.chat_template':'</think>'+ending}));
    assert.equal(info.thinking,true);
    assert.equal(info.reasoningPrefix,prefix);
    assert.equal(metadata(write(arch+'-other',arch,{'tokenizer.chat_template':'other template'})).reasoningPrefix,undefined);
  }
});
test('Muse streams only the user recipient, including when markers cross token boundaries', t => {
  const {museAnswerStream}=require('../../apps/windows-ui/hf/llama-service.cjs');
  const wire=' to=self<|message|>private<|eom|><|start|>assistant to=user<|message|>Paris<|eot|>';
  for (const chunks of [[wire],[...wire],[' to=se','lf<|message|>private<|eo','m|><|start|>assistant to=user<|message|>Paris<|eot|>']]) {
    let thought='';
    const reader=museAnswerStream(chunk=>{thought+=chunk;});
    assert.equal(chunks.map(c=>reader.push(c)).join('')+reader.push('',true),'Paris');
    assert.equal(reader.sawPrivate,true);
    assert.equal(thought,'private');
  }
  const plain=museAnswerStream();assert.equal(plain.push('  Already parsed.',true),'  Already parsed.');
  const hidden=museAnswerStream();assert.equal(hidden.push(' to=self<|message|>unclosed',true),'');
  const write=fixture(t);
  const fields={'tokenizer.chat_template':"reasoning_strength message.get('recipient') <|message|> <|eom|>"};
  assert.equal(metadata(write('muse','muse-glimmer',fields)).museRecipients,true);
  assert.equal(metadata(write('other','llama',fields)).museRecipients,undefined);
});
test('Wan T2V binds its denoiser, UMT5 and 16-channel video VAE regardless of filenames', (t) => {
  const write = fixture(t);
  const model = write('a', 'wan', {}, [['patch_embedding.weight',[2,2,1,16,1536]], ['head.modulation',[1536,2,1]]]);
  const enc = write('b', 't5encoder', {}, [['token_embd.weight',[4096,256384]], ['enc.blk.0.attn_rel_b.weight',[64,32]]]);
  const vae = write('c', '', {}, [['conv2.weight',[1,1,1,256]], ['decoder.conv1.weight',[3,3,3,6144]], ['encoder.conv1.weight',[3,3,3,288]]]);
  assert.equal(metadata(model).kind, null);
  assert.equal(bundle([model, enc]), null);
  assert.equal(bundle([model, vae, vae]), null);
  const group = bundle([enc, vae, model]);
  assert.equal(group.info.pipeline, 'wan21-t2v');
  assert.deepEqual(group.extra, {umt5:enc, wan_vae:vae});
});
test('Anima binds the base text encoder and 16-channel VAE and preserves standalone Qwen use', (t) => {
  const write = fixture(t);
  const main = write('a','',{},[['net.x_embedder.proj.1.weight',[68,2048]], ['net.llm_adapter.embed.weight',[1024,32128]], ['net.final_layer.linear.weight',[2048,64]]]);
  const enc = write('b','qwen3',{},[['token_embd.weight',[1024,151936]], ['blk.27.attn_q_norm.weight',[128]]]);
  const wrong = write('c','qwen3',{},[['token_embd.weight',[2560,151936]], ['blk.27.attn_q_norm.weight',[128]]]);
  const vae = write('d','',{},[['conv2.weight',[1,1,1,256]], ['decoder.conv1.weight',[3,3,3,6144]], ['encoder.conv1.weight',[3,3,3,288]]]);
  assert.equal(metadata(enc).kind, 'text');
  assert.equal(bundle([main,enc]), null);
  assert.equal(bundle([main,wrong,vae]), null);
  assert.deepEqual(bundle([vae,enc,main]).extra, {anima_encoder:enc, anima_vae:vae});
  assert.equal(bundle([main,enc,vae]).info.pipeline, 'anima');
});
test('Qwen4Exp chooses the corrected PLE graph when the gathered embedding is wider than the hidden state', (t) => {
  const write = fixture(t);
  const fields = {'qwen4exp.ple.ngram_size':3, 'qwen4exp.ple.heads_per_ngram':8,
    'qwen4exp.embedding_length_per_layer_input':1, 'tokenizer.ggml.tokens':['x']};
  const small = metadata(write('small','qwen4exp',{...fields,'qwen4exp.embedding_length':8}));
  const standard = metadata(write('standard','qwen4exp',{...fields,'qwen4exp.embedding_length':16}));
  assert.equal(small.pipeline,'llama-qwen4exp-ple');
  assert.notEqual(standard.pipeline,small.pipeline);
});
test('MiniMax derives its full-attention interval only from a complete periodic tensor layout', (t) => {
  const write=fixture(t);
  const fields={'minimax-01.block_count':2,'tokenizer.ggml.tokens':['x']};
  const layers=[...['qkv','gate','norm_2'].map(n=>['blk.0.attn_'+n+'.weight',[8]]),
    ...['q','k','v'].map(n=>['blk.1.attn_'+n+'.weight',[8]])];
  assert.equal(metadata(write('complete','minimax-01',fields,layers)).minimaxInterval,2);
  assert.equal(metadata(write('partial','minimax-01',fields,layers.slice(0,-1))).minimaxInterval,undefined);
  assert.equal(metadata(write('declared','minimax-01',{...fields,'minimax-01.full_attention_interval':4},layers)).minimaxInterval,undefined);
});
test('the GPT-OSS Harmony template exposes the existing thinking switch', t => {
  const write=fixture(t);
  const fields={'tokenizer.ggml.tokens':['x'],'tokenizer.chat_template':'<|start|>assistant<|channel|>final<|message|>'};
  const file=write('harmony','gpt-oss',fields,[['token_embd.weight',[64,8]]]);
  assert.equal(metadata(file).thinking,true);
  assert.equal(metadata(write('plain','gpt-oss',{'tokenizer.ggml.tokens':['x']},[['token_embd.weight',[64,8]]])).thinking,false);
  const inkling={...fields,'tokenizer.chat_template':'<|message_model|><|content_thinking|><|content_text|>'};
  for (const arch of ['inkling2','inkling2_loop'])
    assert.equal(metadata(write(arch,arch,inkling,[['token_embd.weight',[64,8]]])).thinking,true);
});
test('Qwen REAP25 binds both pinned sidecars and launches the on-demand table and unit-scale adapter', () => {
  const recipe=require('../../apps/windows-ui/hf/qwen-reap.cjs');
  const rows=Object.values(recipe.assets).map(f=>({...f,path:f.name}));
  const repo='anik-jha/Qwen3.8-Flash-Next-24GB-GGUF';
  assert.deepEqual(recipe.companions(repo,rows[0],rows),rows.slice(1));
  assert.throws(()=>recipe.companions(repo,rows[0],rows.slice(0,2)),/查找表/);
  const entries=rows.map((f,i)=>({file:'C:\\AiLab,models\\'+f.path,
    info:{arch:'qwen4exp',size:f.size,...[{kind:'text'},{pleOnly:true},{lora:true}][i]}}));
  const result=recipe.match(entries);
  const args=flags(result.file,result.info,{device_id:'cpu',context_limit:512,prefill_step_size:128},result.extra,'test');
  assert.equal(args[args.indexOf('--ple')+1],'"'+entries[1].file+'"');
  assert.equal(args[args.indexOf('--lazy-mode')+1],'on');
  assert.equal(args[args.indexOf('--presence-penalty')+1],'1.5');
  assert.ok(args.includes('--no-repack'));
  assert.equal(args[args.indexOf('--lora')+1],'"'+entries[2].file+'"');
  assert.throws(()=>recipe.verifyLocal(rows[0].sha256,{ple_table:rows[1].sha256}),/摘要/);
  const smallMain={path:'Qwen3.8-Flash-Next-16GB-REAP25-IQ2_XXS.gguf',size:13045640480,sha256:'30985a6da954eb6419686d2fe70160c0f7123e3b1d63165899fa908f89ee1fa9'};
  const smallAdapter={...rows[2],path:rows[2].path.replace('24GB','16GB'),sha256:'5d059ee068c0e508dc887e5b35035f04394a933374d235f485f94b42839e25b9'};
  assert.deepEqual(recipe.companions(repo.replace('24GB','16GB'),smallMain,[smallMain,rows[1],smallAdapter]),[rows[1],smallAdapter]);
  assert.throws(()=>recipe.verifyLocal(smallMain.sha256,{ple_table:rows[1].sha256,recovery_lora:rows[2].sha256}),/摘要/);
  recipe.verifyLocal(smallMain.sha256,{ple_table:rows[1].sha256,recovery_lora:smallAdapter.sha256});
});
test('a standalone PLE table attaches only to a same-architecture language backbone', t => {
  const write=fixture(t);
  const body=write('no-ple-main','qwen4exp',{'tokenizer.ggml.tokens':['x'],'qwen4exp.ple.layers':[0]},[['token_embd.weight',[64,8]]]);
  const table=write('ple','qwen4exp',{},[['per_layer_token_embd.weight',[16,100]]]);
  const other=write('other','gemma4',{},[['per_layer_token_embd.weight',[16,100]]]);
  assert.equal(bundle([body,table]).extra.ple_table,table);
  assert.throws(()=>bundle([body]),/查找表/);
  const gemma=write('sharded-00001-of-00002','gemma4',{'tokenizer.ggml.tokens':['x'],'gemma4.embedding_length_per_layer_input':8},[['token_embd.weight',[64,8]]]);
  const tail=write('sharded-00002-of-00002','gemma4',{},[['per_layer_token_embd.weight',[16,100]]]);
  assert.equal(bundle([gemma,tail]).extra.shard_00002,tail);
  assert.equal(bundle([body,other]),null);
  assert.equal(bundle([table]),null);
});
test('Iris binds the Qwen3-VL 4B encoder only inside its two-file image bundle', (t) => {
  const write = fixture(t);
  const main = write('main','iris',{},[['modulation_cores.adaln_img.weight',[1]],['y_embedder.layer_pool.weight',[1]]]);
  const encoder = write('qwen','qwen3vl',{},[['token_embd.weight',[2560,151936]]]);
  const other = write('other','qwen3vl',{},[['token_embd.weight',[4096,151936]]]);
  assert.equal(metadata(encoder).kind,'text');
  assert.equal(bundle([main, other]), null);
  assert.equal(bundle([main, encoder]).info.pipeline, 'iris');
});
test('Iris validates the original matrix shape and skips already restored matrices', (t) => {
  const write = fixture(t), key = 'blocks.0.mlp_x.w2.weight';
  const fields = {['comfy.gguf.orig_shape.' + key]:[2560,6826]};
  const packed = write('packed','iris',fields,[[key,[256,68260],11]]);
  const restored = write('restored','iris',fields,[[key,[6826,2560],1]]);
  assert.deepEqual(metadata(packed).irisPackedMatrices[key], [6826,2560]);
  assert.equal(metadata(restored).irisPackedMatrices, undefined);
  assert.throws(() => metadata(write('bad','iris',fields,[[key,[256,13],11]])), /矩阵形状/);
});
test('legacy Inkling controller rows are reordered offline and prepared weights can be reused', async (t) => {
  const write = fixture(t);
  const file = write('legacy','inkling2',{'inkling2.num_loops':3,'inkling2.loop.core_start':0,
    'inkling2.loop.core_end':2,'inkling2.block_count':7,'inkling2.embedding_length':8,
    'inkling2.attention.head_count':[4,2,4,2,4,2,8]},
    [['loop_kv_res_query.weight',[8,4],0,0],['loop_res_query.weight',[8,4],0,128],
      ['blk.0.loop_attn_gain.weight',[8],0,256],['blk.1.loop_mlp_gain.weight',[8],0,288]]);
  fs.appendFileSync(file,Buffer.alloc((32-fs.statSync(file).size%32)%32));
  for (let i=0;i<10;i++) fs.appendFileSync(file,Buffer.alloc(32,i));
  assert.equal(metadata(file).legacyInklingLoop,true);
  const {preparedInkling} = require('../../apps/windows-ui/hf/inkling-layout.cjs');
  const output = await preparedInkling(file);
  assert.equal(metadata(output).arch,'inkling2_loop');
  const dir = metadata(output,true), data=fs.readFileSync(output).subarray(Math.ceil(dir.headerEnd/32)*32);
  assert.deepEqual(dir.tensors.map(t=>t.name),['blk.0.loop_q_ctrl_gain.weight','blk.1.loop_ffn_ctrl_gain.weight',
    'blk.0.loop_msg_query.weight','blk.1.loop_msg_query.weight']);
  assert.deepEqual(Array.from({length:10},(_,i)=>data[32*i]),[8,9,4,0,1,5,6,2,3,7]);
  assert.equal(await preparedInkling(file),output);
});
test('legacy ZAYA pairs the attention and expert blocks and converts residuals and convolution taps', {
  skip:process.platform!=='win32',
}, async t=>{
  const write=fixture(t), embedding=8, head=4, groups=4;
  const entries=[],parts=[];let offset=0;
  function tensor(name,shape,fill=0) {
    const data=Buffer.alloc(shape.reduce((n,x)=>n*x,1)*4);
    for(let i=0;i<data.length/4;i++) data.writeFloatLE(typeof fill==='function'?fill(i):fill,i*4);
    const padding=(32-data.length%32)%32;
    entries.push([name,shape,0,offset]);parts.push(data,Buffer.alloc(padding));offset+=data.length+padding;
  }
  tensor('token_embd.weight',[embedding,1]);tensor('output_norm.weight',[embedding]);
  for (const prefix of ['','blk.0.','blk.1.']) {
    tensor(prefix+'res_scale_hs.weight',[embedding],2);
    tensor(prefix+'res_scale_hs.bias',[embedding],3);
    if (prefix!=='blk.0.') {
      tensor(prefix+'res_scale_res.weight',[embedding],4);
      tensor(prefix+'res_scale_res.bias',[embedding],5);
    }
  }
  for (const k of ['attn_norm','attn_q','attn_k','attn_output','ssm_conv1d']) tensor('blk.0.'+k+'.weight',[embedding]);
  tensor('blk.0.ssm_conv1d.bias',[groups*head]);tensor('blk.0.cca_conv_grp.bias',[groups*head]);
  tensor('blk.0.cca_k_scale.weight',[2]);tensor('blk.0.cca_conv_grp.weight',[2,head,groups*head],i=>i);
  tensor('blk.0.cca_val_proj1.weight',[embedding,head],1);tensor('blk.0.cca_val_proj2.weight',[embedding,head],2);
  tensor('blk.1.ffn_down_exps.weight',[4,embedding,2]);tensor('blk.1.ffn_gate_inp.weight',[embedding,4]);
  for (const n of ['attn_norm.weight','ffn_norm.weight','ffn_gate_inp.bias','ffn_gate_up_exps.weight',
    'zaya_router_biases.weight','ffn_gate.bias','ffn_gate.weight','zaya_router_mlp2.bias',
    'zaya_router_mlp2.weight','zaya_router_mlp4.weight']) tensor('blk.1.'+n,[embedding]);
  const values={'context_length':128,'block_count':2,'embedding_length':embedding,'feed_forward_length':embedding,
    'attention.head_count':2,'attention.head_count_kv':2,'attention.key_length':head,'attention.value_length':head,
    'rope.dimension_count':4,'ssm.conv_kernel':2,'expert_count':2,'expert_used_count':1,'rope.freq_base':10000,
    'attention.layer_norm_rms_epsilon':1};
  const file=write('trained-layout','zaya',Object.fromEntries(Object.entries(values).map(([k,v])=>['zaya.'+k,v])),entries);
  fs.appendFileSync(file,Buffer.alloc((32-fs.statSync(file).size%32)%32));
  fs.appendFileSync(file,Buffer.concat(parts));
  assert.equal(metadata(file).legacyZayaLayers,true);
  const out=path.join(path.dirname(file),'mainline.gguf');
  const {invoke,bins}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  await invoke(bins.text,[],{input:{action:'prepare-zaya-layout',cpu_only:true,model:file,output:out}});
  assert.equal(metadata(out).arch,'zaya1');assert.equal(metadata(out).legacyZayaLayers,undefined);
  const header=metadata(out,true),bytes=fs.readFileSync(out),start=Math.ceil(header.headerEnd/32)*32;
  const value=(key,i=0)=>bytes.readFloatLE(start+header.tensors.find(t=>t.name===key).offset+i*4);
  assert.equal(value('blk.0.attn_resid_scale.bias'),26);
  assert.equal(value('blk.0.ffn_resid_scale.bias'),26);
  assert.equal(value('blk.0.attn_v.weight',31),1);assert.equal(value('blk.0.attn_v.weight',32),2);
  assert.equal(value('blk.0.cca_conv_grp.weight',1),2);assert.equal(value('blk.0.cca_conv_grp.weight',64),1);
});
test('the publisher mainline gguf_file imports as a normal local GGUF and survives reloading', async (t) => {
  const write=fixture(t),original=write('Inkling-2-Mini','inkling2_loop');
  const dir=path.dirname(original),file=original+'_file';
  fs.renameSync(original,file);
  const {Trials}=require('../../apps/windows-ui/hf/trials.cjs');
  const profile=path.join(dir,'profile'),project_id='project-inkling';
  const trials=new Trials(profile,{records:()=>[]});
  for (const source of [file,dir]) {
    const plan=await trials.inspectImport('models',{project_id,path:source});
    const model=await trials.confirmImport('models',plan);
    const second=new Trials(profile,{records:()=>[]}),ref=second.resolve(model.id,project_id);
    assert.equal(path.extname(ref.file),'.gguf');
    assert.equal(metadata(ref.file).arch,'inkling2_loop');
    await ref.verify();
  }
});
test('voice sidecars survive import and are covered by the model digest', async (t) => {
  const write = fixture(t);
  const model = write('voice', 'audiocpp', {'audiocpp.model_spec.family':'pocket_tts_small'});
  const dir = path.dirname(model);
  const { Trials } = require('../../apps/windows-ui/hf/trials.cjs');
  const trials = new Trials(path.join(dir, 'profile'), {records:()=>[]});
  const request = {project_id:'project-voice', path:model};
  await assert.rejects(trials.inspectImport('models', request), /alba\.safetensors/);
  fs.mkdirSync(path.join(dir, 'embeddings'));
  fs.writeFileSync(path.join(dir, 'embeddings', 'alba.safetensors'), 'voice');
  const plan = await trials.inspectImport('models', request);
  const row = await trials.confirmImport('models', plan);
  const ref = trials.resolve(row.id, request.project_id);
  assert.equal(row.name, 'pocket_tts_small');
  assert.equal(row.pipeline, 'audiocpp-tts');
  assert.equal(plan.file_count, 2);
  await ref.verify();
  fs.writeFileSync(ref.extra.pocket_voice, 'different voice');
  await assert.rejects(ref.verify(), /摘要/);
});
test('Z-Image requires the denoiser, matching Qwen text encoder and 16-channel VAE together', (t) => {
  const write = fixture(t);
  const image = write('denoiser', '', {}, [
    ['cap_embedder.1.weight',[2560,3840]], ['noise_refiner.0.attention.qkv.weight',[3840,11520]],
    ['x_embedder.weight',[64,3840]], ['final_layer.linear.weight',[3840,64]],
  ]);
  const encoder = write('encoder', '', {}, [
    ['model.embed_tokens.weight',[2560,151936]], ['model.layers.35.self_attn.q_norm.weight',[128]],
    ['model.norm.weight',[2560]],
  ]);
  const vae = write('vae', '', {}, [
    ['decoder.conv_in.weight',[3,3,16,512]], ['encoder.conv_out.weight',[3,3,512,32]],
    ['decoder.conv_out.weight',[3,3,128,3]],
  ]);
  assert.equal(bundle([image,encoder,vae]).info.pipeline, 'z-image');
  assert.equal(bundle([image,encoder]), null);
  assert.equal(bundle([image,encoder,vae,vae]), null);
  assert.equal(metadata(encoder).kind, null);
});
test('the four-fold MoSR trial requires RGB and a matching pixel shuffle head', (t) => {
  const write = fixture(t);
  const base = [['gblocks.0.weight', [3,3,3,64]], ['gblocks.1.fc1.weight', [1,1,64,192]], ['gblocks.1.conv.weight', [7,7,1,64]]];
  const model = (n) => metadata(write('mosr'+n, 'mosr', {}, [...base, ['upsampler.0.weight', [3,3,64,n]]]));
  assert.equal(model(48).pipeline, 'mosr-x4');
  assert.equal(model(12).kind, null);
});
test('audio diffusion tensors cannot advertise an image trial', (t) => {
  const write = fixture(t);
  const audio = write('audiosr', 'audiocpp', { 'audiocpp.model_spec.family': 'audiosr' }, 'diffusion_model.input_blocks.0.weight');
  assert.equal(metadata(audio).kind, null);
  for (const [family, task] of [['pulsevad','vad'],['citrinet_asr','asr'],['kroko_asr','asr'],['moonshine_asr','asr'],['canary_asr','asr']]) {
    const model=metadata(write(family,'audiocpp',{'audiocpp.model_spec.family':family}));
    assert.equal(model.kind,'audio');
    assert.equal(model.audioTask,task);
    assert.equal(model.pipeline,'audiocpp-'+task);
  }
});
test('every b12648 architecture reaches a trial pipeline or its required component role', (t) => {
  const write = fixture(t);
  assert.equal(new Set([...registry.models, ...registry.projectors, ...registry.no_constructor]).size, 180);
  for (const arch of registry.models) {
    const info = metadata(write(arch, arch));
    assert.ok(info.kind || ['draft', 'speech-base', 'ocr-base'].includes(info.component), arch);
  }
  assert.equal(metadata(write('p', 'clip')).component, 'projector');
  for (const arch of ['gptj', '(unknown)', 'arbitrary-new-model'])
    assert.equal(metadata(write('unsupported' + arch, arch)).kind, null);
  assert.equal(metadata(write('adapter', 'llama', { 'general.type': 'adapter' })).kind, null);
});
test('pooled weights, decision models and distinct graph types select different operations', (t) => {
  const write = fixture(t);
  for (const [arch, fields, expected] of [
    ['qwen3', { 'qwen3.pooling_type': 3 }, 'llama-embedding'],
    ['bert', { 'bert.pooling_type': 4 }, 'llama-rerank'],
    ['maion-coder', { 'maion-coder.pooling_type': 0xffffffff }, undefined],
    ['t5', {}, 'llama-seq2seq'],
    ['t5encoder', {}, 'llama-embedding'],
    ['rnd1', {}, 'llama-diffusion'],
    ['clef', {}, 'llama-decision'],
    ['lfm2', { 'lfm2.decision.type': 'lfm2-d1', 'tokenizer.chat_template': 'render state' }, 'llama-decision'],
    ['lfm3', { 'lfm3.decision.type': 'lfm3-d1-omni', 'tokenizer.chat_template': 'render state' }, 'llama-decision'],
    ['graniteswitch', { 'graniteswitch.decision.type': 'granite-switch', 'tokenizer.chat_template': 'render chat' }, 'llama-chat'],
    ['wavtokenizer-dec', {}, 'llama-vocoder'],
    ['qwen2', {}, undefined],
    ['deepseek41', { 'tokenizer.chat_template': 'custom jinja' }, 'llama-chat'],
  ])
    assert.equal(metadata(write(arch, arch, fields)).pipeline, expected, arch);
  assert.throws(() => structuredInput('query', 'llama-rerank'), /候选/);
  assert.deepEqual(structuredInput('q\nd1\nd2', 'llama-rerank').documents, ['d1', 'd2']);
});
test('draft, audio codec and projector are bound to a base, complete shard sets survive import', (t) => {
  const write = fixture(t);
  const first = write('model-00001-of-00002', 'llama'),
    last = write('model-00002-of-00002', 'llama');
  const head = write('draft', 'eagle3'),
    proj = write('vision', 'clip', { 'clip.has_vision_encoder': true });
  assert.equal(bundle([first]), null);
  assert.equal(bundle([last, proj]), null);
  assert.equal(bundle([head]), null);
  const result = bundle([last, proj, head, first]);
  assert.equal(result.file, first);
  assert.equal(result.info.specType, 'draft-eagle3');
  assert.equal(result.extra.shard_00002, last);
  assert.equal(result.info.acceptsImage, true);
  assert.equal(localExtras({ path: first, component_digests: { shard_00002: 'hash' } }).shard_00002, last);
  const args = flags(first, result.info, { device_id: 'cpu', kv_precision: 'q8' }, result.extra, 'nonce');
  for (const val of ['--mmproj', proj, '--spec-type', 'draft-eagle3', head, 'q8_0', '--offline'])
    assert.ok(args.includes(val), val);
  const speech = write('speech', 'tiny-voca'),
    codec = write('codec', 'clip', { 'clip.has_gen_audio_encoder': true });
  assert.equal(bundle([speech, proj]), null);
  assert.equal(bundle([speech, codec]).info.pipeline, 'llama-tts');
});

test('OCR and duplex speech models require their own matching input components', t => {
  const write = fixture(t);
  const ocr = write('ocr', 'deepseek2-ocr', {'general.name':'DeepSeek OCR','deepseek2-ocr.embedding_length':1280});
  const vision = write('ocr-proj', 'clip', {'clip.has_vision_encoder':true,'clip.vision.projector_type':'deepseekocr','clip.vision.projection_dim':1280});
  const hibiki = write('hibiki', 'moshi', {'moshi.embedding_length':2048});
  const codec = width => write('codec-'+width, 'clip', {'clip.has_audio_encoder':true,'clip.has_gen_audio_encoder':true,
    'clip.audio.projector_type':'moshi','clip.audio.projection_dim':width});
  assert.equal(bundle([ocr]), null);
  assert.equal(bundle([hibiki]), null);
  assert.equal(bundle([ocr, vision]).info.pipeline, 'llama-ocr');
  assert.equal(bundle([hibiki, codec(2048)]).info.pipeline, 'llama-hibiki');
  assert.equal(bundle([ocr, codec(2048)]), null);
  assert.equal(bundle([hibiki, vision]), null);
  assert.equal(bundle([hibiki, codec(1536)]), null);
  assert.equal(bundle([write('unrelated','llama'),vision]), null);
});
