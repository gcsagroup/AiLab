const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {createHash} = require('node:crypto');
const {packages,planFiles,componentName,stored,downloaded,sourceChoices} = require('../../apps/windows-ui/hf/generation-packages.cjs');
const {HubClient} = require('../../apps/windows-ui/hf/hub.cjs');
const {OfficialModels} = require('../../apps/windows-ui/hf/official.cjs');
const {Downloads} = require('../../apps/windows-ui/hf/downloads.cjs');

test('CPU trial presets use the native implementation and step control for the selected checkpoint',()=>{
  const {audioEngine,diffusionEngine}=require('../../apps/windows-ui/hf/generation-runtime.cjs');
  const {parameters}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  const base=path.resolve('audio/audiocpp_cli.exe');
  assert.equal(audioEngine(base,packages.f5_tts),path.join(path.dirname(base),'f5','audiocpp_cli.exe'));
  assert.equal(audioEngine(base,packages.auk),path.join(path.dirname(base),'f5','audiocpp_cli.exe'));
  assert.equal(audioEngine(base,packages.m5_tts),path.join(path.dirname(base),'v0.9.6','audiocpp_cli.exe'));
  assert.equal(audioEngine(base,packages.neutts),base);
  assert.equal(packages.neutts.voiceRef,undefined);
  const draft={kind:'audio',input:{prompt:'A little bird sings.'},runtime:{seed:1,steps:1,device_id:'cpu'}};
  const info={packageId:'echo_tts',audioTask:'tts',audioFamily:'echo_tts',pipeline:'audiocpp-tts'};
  assert.equal(parameters(draft,info).steps,1);
  assert.equal(parameters({...draft,runtime:{seed:1}},info).steps,undefined);
  assert.equal(packages.moss_soundeffect.stepOption,'num_steps');
  assert.equal(packages.soulx_singer.stepOption,'num_steps');
  const visual=packages.z_image_controlnet;
  assert.ok(visual.imageReference);
  assert.deepEqual(visual.files.map(f=>f.flag),['--control-net','--diffusion-model','--llm','--vae']);
  assert.equal(diffusionEngine(path.resolve('diffusion/ailab-image.exe'),visual),path.resolve('diffusion/0d71f96/sd-cli.exe'));
  assert.equal(packages.pid.imageReference,'ref-image');
  assert.equal(packages.pid.vaeFormat,'sd3');
  assert.match(packages.pid.files[0].path,/\/pid_sd3_/);
  assert.equal(packages.moss_image.files.find(f=>f.flag==='--tokenizer').repo,'OpenMOSS-Team/MOSS-Image-Base');
});

test('publisher variants select matching FireRed, Audio8 and dots weights',()=>{
  const paths=repo=>sourceChoices(repo).map(file=>file.path);
  assert.ok(paths('FireRedTeam/FireRedTTS3-Base-HF').length);
  assert.ok(paths('FireRedTeam/FireRedTTS3-Base-HF').every(p=>p.includes('base-')));
  assert.ok(paths('FireRedTeam/FireRedTTS3-Instruct-HF').every(p=>p.includes('instruct-')));
  assert.equal(packages.firered_audio.compactAudio,true);
  assert.equal(packages.firered_audio__firered_audio_orig.compactAudio,undefined);
  assert.ok(paths('Edge0/Audio8-TTS-Preview-0.6b').every(p=>p.includes('preview-')));
  assert.deepEqual(paths('Edge0/Audio8-TTS-Realistic-0.6b'),paths('Edge0/Audio8-TTS-Realistic-Air'));
  assert.ok(paths('dots-studio/dots.tts.edit').every(p=>p.includes('edit-')));
  assert.ok(paths('YJX-Xiaomi/ControlFoley').includes(packages.controlfoley.files[0].path));
});

test('Inkling keeps raw files downloadable and resumes the publisher mainline GGUF under its native filename',async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-inkling-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const repo='unsloth/Inkling-2-Mini-GGUF',rev='a'.repeat(40),name='Inkling-2-Mini-UD-IQ1_S.gguf';
  const mainline='Mainline_Support/'+name+'_file';
  const files=[name,mainline,'mmproj-BF16.gguf','mmproj-F16.gguf'].map((path,i)=>{
    const bytes=Buffer.from('weight-'+i);
    return {path,size:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
  });
  const hub=new HubClient({fetchImpl:async url=>{
    const remote=new URL(url).pathname.split('/resolve/'+rev+'/')[1];
    const index=files.findIndex(f=>f.path===remote);
    assert.notEqual(index,-1);
    return new Response('weight-'+index);
  }});
  const detail={repoId:repo,revision:rev,license:'test',formats:['gguf','file'],files};
  const plan=hub.plan(detail,'gguf',name);
  assert.deepEqual(plan.files.map(f=>f.path),[name,'mmproj-F16.gguf']);
  assert.equal(plan.files[0].sha256,files[1].sha256);
  assert.equal(hub.plan(detail,'file',name).files[0].sha256,files[0].sha256);
  const storage=new Downloads({dataDir:dir,hub});
  const job=await storage.create(plan,'project',rev);
  await storage.active.get(job.id)?.pending;
  assert.equal(storage.get(job.id).status,'completed');
  const restored=new Downloads({dataDir:dir,hub});
  assert.ok(new URL(restored.get(job.id).files[0].url).pathname.endsWith('/'+mainline));
  assert.equal(await fs.readFile(path.join(dir,'models',job.modelId,name),'utf8'),'weight-1');
});

test('AuK Flash uses the selected generator, companion weights, voice description and native four-step schedule',async t=>{
  const {parameters}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  const {runPackage}=require('../../apps/windows-ui/hf/generation-runtime.cjs');
  const packageId='auk__auk_flash_q8_0',spec=packages[packageId];
  const draft={kind:'audio',input:{prompt:'@音色描述 A warm voice.\nHello again.'},runtime:{seed:42,steps:1,device_id:'cpu'}};
  const config=parameters(draft,{packageId,audioTask:'tts',audioFamily:'auk',pipeline:'audiocpp-tts'});
  assert.equal(config.steps,4);
  const out=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-auk-'));t.after(()=>fs.rm(out,{recursive:true,force:true}));
  const extra=Object.fromEntries(spec.files.slice(1).map((f,i)=>['package_'+packageId+'__'+(i+1),f.path]));
  let args;
  await runPackage({model:spec.files[0].path,extra,out,input:draft.input.prompt,r:config,bins:{audio:'native',ffmpeg:'encoder'},
    linkWeight:async()=>{},invoke:async (engine,argv)=>{
      if (engine===path.join('f5','audiocpp_cli.exe')) args=argv;
      else await fs.writeFile(path.join(out,'speech.wav'),Buffer.alloc(256));
    }});
  for (const option of ['auk.variant=flash','auk.model_gguf=auk-flash-q8_0.gguf','auk.qwen_gguf=qwen2.5-omni-3b-q8_0.gguf','duration_sec=2']) assert.ok(args.includes(option),option);
  assert.equal(args[args.indexOf('--instruct')+1],'A warm voice.');
  assert.equal(args[args.indexOf('--text')+1],'Hello again.');
  assert.equal(args[args.indexOf('--num-inference-steps')+1],'4');
});

test('the Windows converter keeps the Flux VAE batch counter when packing floating-point weights',async t=>{
  const {runPackage}=require('../../apps/windows-ui/hf/generation-runtime.cjs');
  const {invoke}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  const exe=path.resolve('apps/windows-ui/runtime/diffusion/sd-cli.exe');
  if (process.platform!=='win32' || !require('node:fs').existsSync(exe)) return t.skip('bundled Windows converter');
  const out=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-vae-'));t.after(()=>fs.rm(out,{recursive:true,force:true}));
  const header=Buffer.from(JSON.stringify({'bn.num_batches_tracked':{dtype:'I64',shape:[],data_offsets:[0,8]},
    'bn.running_mean':{dtype:'F32',shape:[1],data_offsets:[8,12]}}));
  const size=Buffer.alloc(8),data=Buffer.alloc(12);size.writeBigUInt64LE(BigInt(header.length));
  data.writeBigInt64LE(8n);data.writeFloatLE(0.125,8);
  const file=path.join(out,'vae.safetensors');await fs.writeFile(file,Buffer.concat([size,header,data]));
  const id='fibo2',spec=packages[id],extra=Object.fromEntries(spec.files.slice(1).map((f,i)=>['package_'+id+'__'+(i+1),file]));
  let converted=false;
  await runPackage({model:file,extra,out,input:'a bird',r:{generation_package:id,size:512,steps:1,cfg:1,seed:1},
    bins:{image:exe},linkWeight:fs.link,invoke:async (engine,args,opts)=>{
      if (args[1]!=='convert') return;
      await invoke(engine,args,{...opts,timeout:30000});
      const packed=await fs.readFile(path.join(out,args[args.indexOf('-o')+1]));
      assert.equal(packed.toString('ascii',0,4),'GGUF');
      assert.ok(packed.includes(Buffer.from('bn.num_batches_tracked')));
      converted=true;
    }});
  assert.ok(converted);
});

test('every published generation recipe binds a unique staged file and a verifiable source revision', () => {
  for (const [id,row] of Object.entries(packages)) {
    assert.ok(['audio','image','video'].includes(row.kind),id);
    assert.ok(row.files.length > 0,id);
    const primary=row.files[0];
    const current=planFiles(primary.repo,primary,primary.rev);
    assert.equal(current[0].sha256,primary.sha256,id);
    const snapshot=row.files.map((f,i)=>({path:i?'components/'+componentName('package_'+id+'__'+i):f.path,
      size:f.size,sha256:f.sha256,gitOid:f.git}));
    const planned=planFiles(primary.repo,primary,primary.rev,snapshot);
    assert.equal(planned.length,row.files.length,id);
    assert.deepEqual(planned.map(f=>f.sha256 || f.gitOid),row.files.map(f=>f.sha256 || f.git),id);
    assert.equal(new Set(planned.map(f=>f.path)).size,planned.length,id);
    for (let i=1;i<row.files.length;i++)
      assert.equal(componentName('package_'+id+'__'+i),'component-'+i+path.extname(row.files[i].path),id);
    assert.equal(new Set(row.files.map(f=>f.local.toLowerCase())).size,row.files.length,id);
    for (const f of row.files) {
      assert.match(f.rev,/^[0-9a-f]{40}$/);
      assert.ok(f.size>0 && (f.sha256 ? /^[0-9a-f]{64}$/.test(f.sha256) : /^[0-9a-f]{40}$/.test(f.git)),id);
      assert.ok(!path.isAbsolute(f.local) && !f.local.split(/[\\/]/).includes('..'),id);
    }
  }
});

test('publisher cards select the corresponding checkpoint and voice variant',async t=>{
  assert.ok(sourceChoices('ACE-Step/Ace-Step1.5').every(f=>/^ace-step/i.test(f.path)));
  assert.equal(sourceChoices('Qwen/Qwen-Image')[0].repo,'QuantStack/Qwen-Image-GGUF');
  assert.deepEqual(sourceChoices('PrunaAI/P-H3-Image'),sourceChoices('PrunaAI/P-Image-OSS'));
  assert.equal(sourceChoices('microsoft/Mage-Flow')[0].path,packages.mage_flow.files[0].path);
  const id='Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice';
  const choices=sourceChoices(id);
  assert.ok(choices.length>1 && choices.every(f=>/customvoice/i.test(f.path)));
  const first=choices[0];
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-publisher-card-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const hub=new HubClient({fetchImpl:async url=>Response.json(url.toString().includes(first.repo)
    ? {id:first.repo,sha:first.rev,siblings:choices.map(f=>({rfilename:f.path,size:f.size,lfs:{sha256:f.sha256}}))}
    : {id,sha:'c'.repeat(40),siblings:[{rfilename:'model.safetensors',size:142,lfs:{sha256:'a'.repeat(64)}}]})});
  const service=new OfficialModels({dataDir:dir,hub});t.after(()=>service.close());
  const quant=await service.inspect(id,'gguf');
  assert.equal(quant.repo,first.repo);
  assert.equal(quant.filename,first.path);
  assert.deepEqual(quant.variants,choices.map(f=>f.path));
  const original=await service.inspect(id,'safetensors');
  assert.equal(original.repo,id);
});

test('cross-repository downloads resume the original component URLs and restore the same roles',async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-component-plan-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const [main]=packages.lingbot_video.files;
  const plan=planFiles(main.repo,main);
  assert.equal(plan.length,3);
  assert.ok(plan[1].url.includes(packages.lingbot_video.files[1].repo));
  const projectId='project-package',format='gguf';
  const key=createHash('sha256').update(JSON.stringify([projectId,main.repo,main.rev,format,plan.map(f=>f.path)])).digest('hex').slice(0,24);
  const job={id:'download-'+key,modelId:'hf-'+key,repoId:main.repo,revision:main.rev,filename:main.path,format,projectId,status:'queued',
    files:plan.map(f=>({...f,url:'https://invalid.example/ignored'}))};
  await fs.mkdir(path.join(dir,'downloads'));
  await fs.writeFile(path.join(dir,'downloads',job.id+'.json'),JSON.stringify(job));
  const reopened=new Downloads({dataDir:dir,hub:new HubClient()}).get(job.id);
  assert.equal(reopened.status,'paused');
  assert.deepEqual(reopened.files.map(f=>f.url),plan.map(f=>f.url));
  const ref=downloaded(reopened,dir);
  const local=stored({generation_package:'lingbot_video',path:path.join(dir,'model.gguf')});
  assert.deepEqual(Object.keys(local.extra),Object.keys(ref.extra));
  assert.equal(path.basename(local.extra.package_lingbot_video__1),componentName('package_lingbot_video__1'));
  assert.equal(downloaded({...job,files:[plan[0]]},dir),null);
});

test('GGUF trial conversion and explicit single-file download have independent manifests',async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-gguf-selection-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const main=packages.minit2i.files[0];
  const hub=new HubClient({fetchImpl:async()=>Response.json({id:main.repo,sha:main.rev,siblings:[{rfilename:main.path,size:main.size,lfs:{sha256:main.sha256}}]})});
  const service=new OfficialModels({dataDir:dir,hub});t.after(()=>service.close());
  const entry=await service.inspect(main.repo,'gguf',main.path);
  assert.equal(entry.files.length,packages.minit2i.files.length);
  assert.match(entry.capability,/转换为 GGUF/);
  const file=await service.inspect(main.repo,'file',main.path);
  assert.deepEqual(file.files.map(f=>f.path),[main.path]);
});

test('MiniMax-H3 publisher card can prepare the audio and video runtimes independently',async t=>{
  const audio=packages.minimax_h3.files[0],publisher='MiniMaxAI/MiniMax-H3',videoRepo='leejet/MiniMax-H3-GGUF';
  const video='minimax_h3_fl2va_pruned-Q4_K_M.gguf', dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-h3-formats-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const hub=new HubClient({fetchImpl:async url=>{
    const repo=new URL(url).pathname.split('/').slice(3,5).join('/');
    const source=repo===audio.repo ? audio : {path:repo===videoRepo ? video : 'model.safetensors',size:20,sha256:'a'.repeat(64)};
    return Response.json({id:repo,sha:source.rev || 'a'.repeat(40),siblings:[{rfilename:source.path,size:source.size,lfs:{sha256:source.sha256}}]});
  }});
  const service=new OfficialModels({dataDir:dir,hub});t.after(()=>service.close());
  const entry=await service.inspect(publisher,'gguf');
  assert.equal(entry.filename,video);
  assert.ok(entry.variants.includes(audio.path));
  const sound=await service.inspect(publisher,'gguf',audio.path);
  assert.equal(sound.files.length,packages.minimax_h3.files.length);
  assert.ok(sound.files.every(f=>f.url.startsWith('https://huggingface.co/'+audio.repo+'/resolve/')));
});

test('a saved P-H3 download retains its original encoders after a lower-memory preset is added',()=>{
  const old=packages.p_h3_image, main=old.files[0];
  const files=old.files.map((f,i)=>({path:i?'components/'+componentName('package_p_h3_image__'+i):f.path,
    size:f.size,sha256:f.sha256,gitOid:f.git}));
  const job={repoId:main.repo,revision:main.rev,format:'gguf',filename:main.path,files};
  assert.equal(planFiles(main.repo,main,main.rev).length,packages.p_h3_image__low_memory.files.length);
  const resumed=planFiles(main.repo,main,main.rev,files);
  assert.deepEqual(resumed.map(f=>f.sha256),files.map(f=>f.sha256));
  assert.equal(downloaded(job,'models').info.packageId,'p_h3_image');
  assert.equal(downloaded({...job,files:files.slice(0,1)},'models'),null);
});

test('another quant of the same upstream checkpoint keeps its own hash and pinned companions',()=>{
  const main=packages.lingbot_video.files[0],path8=main.path.replace('Q4_K_S','Q8_0');
  const sha256='a'.repeat(64),revision='b'.repeat(40);
  const files=planFiles(main.repo,{path:path8,size:3789,sha256},revision);
  assert.equal(files[0].path,path8);
  assert.equal(files[0].sha256,sha256);
  assert.equal(files[0].size,3789);
  assert.ok(files[0].url.includes(revision));
  assert.equal(files[1].sha256,packages.lingbot_video.files[1].sha256);
  assert.equal(planFiles(main.repo,{path:'other/model-Q8_0.gguf',size:3789,sha256},revision),undefined);
  assert.equal(planFiles(main.repo,{path:main.path,size:3789,sha256},revision),undefined);
});

test('default GGUF selection prefers the complete model and identifies explicit overlay downloads',async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-gguf-patch-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const repo='example/paired-gguf',patch='patch-UD-IQ1_S/demo-Q4_K_M-patch.gguf',main='weights/demo-Q3_K_M.gguf';
  const hub=new HubClient({fetchImpl:async()=>Response.json({id:repo,sha:'a'.repeat(40),siblings:[patch,main].map((rfilename,i)=>({rfilename,size:100+i,lfs:{sha256:String(i+1).repeat(64)}}))})});
  const service=new OfficialModels({dataDir:dir,hub});t.after(()=>service.close());
  assert.equal((await service.inspect(repo,'gguf')).filename,main);
  assert.match((await service.inspect(repo,'gguf',patch)).capability,/完整基础模型/);
  assert.equal((await service.inspect(repo,'file',patch)).filename,patch);
});

test('audio low-memory preparation retains embedded assets and unmodified tensor bytes',async t=>{
  const {invoke,bins}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-audio-q4-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const u32=n=>{const b=Buffer.alloc(4);b.writeUInt32LE(n);return b};
  const u64=n=>{const b=Buffer.alloc(8);b.writeBigUInt64LE(BigInt(n));return b};
  const str=s=>Buffer.concat([u64(Buffer.byteLength(s)),Buffer.from(s)]);
  const strings=values=>Buffer.concat([u32(8),u64(values.length),...values.map(str)]);
  const kv=(name,type,data)=>Buffer.concat([str(name),u32(type),data]);
  const tensor=(name,dims,type,offset)=>Buffer.concat([str(name),u32(dims.length),...dims.map(u64),u32(type),u64(offset)]);
  const names=['model/backbone_llm.model.layers.0.mlp.up_proj.weight','decoder.norm.weight'];
  const asset=Buffer.from('voice-tokenizer-fixture');
  const fields=[kv('general.architecture',8,str('audiocpp')),kv('audiocpp.tensor_names',9,strings(names)),
    kv('audiocpp.weight_type',8,str('q8_0')),kv('audiocpp.embedded_files.data',9,Buffer.concat([u32(0),u64(asset.length),asset]))];
  const source=path.join(dir,'source.gguf'),output=path.join(dir,'compact.gguf');
  const table=(type,offset)=>Buffer.concat([tensor('W',[256,2],type,0),tensor('bias',[8],0,offset)]);
  const header=Buffer.concat([Buffer.from('GGUF'),u32(3),u64(2),u64(fields.length),...fields,table(8,544)]);
  const weights=Buffer.alloc(544,1),tail=Buffer.from(Array.from({length:32},(_,i)=>i));
  await fs.writeFile(source,Buffer.concat([header,Buffer.alloc((32-header.length%32)%32),weights,tail]));
  await invoke(bins.text,[],{input:{action:'compact-audio',cpu_only:true,model:source,output}});
  const result=await fs.readFile(output);
  assert.ok(result.includes(asset));
  assert.ok(result.includes(strings(names)));
  assert.ok(result.includes(table(12,288)));
  assert.deepEqual(result.subarray(-32),tail);
});

test('the pinned CPU DGL parser accepts Lens and LLaDA graphs with quoted prompts',async t=>{
  const {runBoundedImage}=require('../../apps/windows-ui/hf/bounded-diffusion.cjs');
  const {invoke,bins}=require('../../apps/windows-ui/hf/trial-worker.cjs');
  const {diffusionEngine}=require('../../apps/windows-ui/hf/generation-runtime.cjs');
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-bounded-image-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const components=new Map(['--diffusion-model','--llm','--vae','--tokenizer','--embeddings-connectors'].map(k=>[k,k.slice(2)+'.gguf']));
  for (const [family,cfg] of [['lens',3.5],['llada_image',1]]) {
    const spec=packages[family];
    assert.equal(spec.hostWeightLimitGiB,family==='lens'?12:10);
    await runBoundedImage({family,components,dir,out:dir,limit:spec.hostWeightLimitGiB,engine:diffusionEngine(bins.image,spec),
      input:'猫说 "你好"\n雨后的天空',runtime:{size:512,steps:1,cfg,seed:42,negative_prompt:'blur'},
      invoke:async (exe,args,options)=>{
        assert.equal(args[args.indexOf('--max-ram')+1],String(spec.hostWeightLimitGiB));
        await invoke(exe,[...args,'--check'],options);
      }});
  }
});

test('SeFi combines quantization inputs across shards and swaps its two modulation halves',async t=>{
  const {rewrite}=require('../../apps/windows-ui/hf/sefi-layout.cjs');
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-sefi-'));t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  async function write(file,entries) {
    const header={};let total=0;
    for(const [name,buf] of entries) {header[name]={shape:[buf.length],dtype:'U8',data_offsets:[total,total+buf.length]};total+=buf.length;}
    const text=Buffer.from(JSON.stringify(header)),length=Buffer.alloc(8);length.writeBigUInt64LE(BigInt(text.length));
    await fs.writeFile(file,Buffer.concat([length,text,...entries.map(e=>Buffer.from(e[1]))]));
  }
  const prefix='backbone.transformer_blocks.1.attn.to_';
  const first=path.join(dir,'a'),second=path.join(dir,'b'),out=path.join(dir,'out');
  await write(first,[[prefix+'q.weight',[1,2]],[prefix+'v.weight',[5,6]]]);
  await write(second,[[prefix+'k.weight',[3,4]],['backbone.norm_out.linear.bias',[7,8,9,10]]]);
  await rewrite([first,second],out,false);
  const result=await fs.readFile(out),size=Number(result.readBigUInt64LE()),header=JSON.parse(result.toString('utf8',8,8+size));
  assert.deepEqual(header['double_blocks.1.img_attn.qkv.weight'].shape,[6]);
  assert.deepEqual([...result.subarray(8+size)],[1,2,3,4,5,6,9,10,7,8]);
});
