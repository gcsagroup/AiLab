'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {randomUUID} = require('node:crypto');
const worker = require('../../apps/windows-ui/hf/trial-worker.cjs');

test('selection loads one complete model on GPU or CPU, reuses its verification and rejects changed weights', async t=>{
  const dir=await fs.mkdtemp(path.join(os.tmpdir(),'ailab-resident-test-'));
  t.after(()=>fs.rm(dir,{recursive:true,force:true}));
  const file=path.join(dir,'weights.gguf'), runner=path.join(dir,'runner');
  await fs.writeFile(file,'weights');
  await fs.mkdir(path.join(dir,'cuda'));
  await Promise.all([runner,path.join(dir,'cuda','runner')].map(f=>fs.writeFile(f,'')));
  let free=1024, hashes=0;
  const placements=[];
  t.mock.method(worker,'devices',async()=>[{id:'CUDA0',name:'GPU',free_bytes:free,cuda_engines:['text']},{id:'cpu',name:'CPU'}]);
  t.mock.method(worker,'render',async (job,model,media,out,signal,event,extra,inputs,host,preload)=>{
    assert.ok(host);
    await host.connect(job.runtime.device_id,async (life,ready)=>{
      placements.push(job.runtime.device_id);
      await ready({});
    },signal);
    if (preload) return;
    await fs.writeFile(path.join(out,'result.txt'),'ok');
    return {name:'result.txt',media_type:'text/plain',text:'ok'};
  });
  const previous=worker.bins;
  worker.bins={...previous,text:runner,llamaService:runner};
  t.after(()=>{worker.bins=previous;});
  const {Trials}=require('../../apps/windows-ui/hf/trials.cjs');
  const trials=new Trials(dir,{modelDir:dir});
  t.after(()=>trials.close());
  const model={id:'model',version_id:'v1',manifest_digest:'digest'};
  trials.resolve=()=>({file,extra:{},verificationFiles:[file],model,info:{kind:'text',arch:'qwen3',pipeline:'llama-chat'},
    verify:async()=>{hashes++;if ((await fs.readFile(file,'utf8'))!=='weights') throw Error('权重已变化');}});
  const runtime={engine:'ailab-gguf',device_id:'CUDA0',max_tokens:1,temperature:0,seed:0,top_p:1};
  const task={id:'task-example',project_id:'project-example',kind:'text',operation:'generate',draft_revision:1,
    draft:{operation:'generate',kind:'text',model_id:model.id,input:{prompt:'test'},runtime}};
  const selection={owner:randomUUID(),project_id:task.project_id,task_id:task.id,model_id:model.id,runtime};
  async function run(device) {
    const pre=await trials.check(task);
    assert.equal(pre.can_submit,true,JSON.stringify(pre.blocking));
    assert.equal(pre.effective_config.device_id,device);
    const attempt=trials.submit(task,{preflight_id:pre.id,expected_revision:1},randomUUID());
    await trials.current.done;
    return trials.rows.get(attempt.id);
  }
  assert.equal((await trials.selectText(selection)).device_id,'CUDA0');
  assert.equal((await run('CUDA0')).state,'succeeded');
  assert.equal((await run('CUDA0')).state,'succeeded');
  free=3;
  assert.equal((await trials.selectText(selection)).fallback,true);
  assert.equal((await run('cpu')).state,'succeeded');
  free=1024;
  runtime.device_id='cpu';
  assert.equal((await trials.selectText(selection)).fallback,false);
  assert.equal(hashes,1);
  assert.deepEqual(placements,['CUDA0','cpu','cpu']);
  await fs.writeFile(file,'changed');
  assert.match((await run('cpu')).error.message,/权重已变化/);
  assert.equal(hashes,2);
});
