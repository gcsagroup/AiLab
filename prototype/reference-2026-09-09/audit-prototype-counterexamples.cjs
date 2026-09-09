// 只读审计最终 HTML 中的真实脚本；DOM 替身仅承接渲染与事件注册。
// 这些断言用于复现当前缺陷，并非说明对应行为正确。
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const crypto = require('crypto');
const assert = require('assert');
const target = path.join(__dirname, 'ailab-unified.html');
const html = fs.readFileSync(target, 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function fresh() {
  const listeners = {};
  const node = {
    innerHTML: '', textContent: '', value: '', readOnly: false,
    isConnected: true, tagName: 'DIV',
    style: { setProperty() {} },
    classList: { toggle() {}, add() {}, remove() {} },
    querySelector() { return node; }, querySelectorAll() { return []; },
    contains() { return true; }, setAttribute() {}, removeAttribute() {},
    focus() {}, select() {}, addEventListener(name, callback) {
      (listeners[name] ??= []).push(callback);
    }
  };
  const context = {
    assert, console, document: { getElementById() { return node; }, activeElement: null },
    setInterval() { return 1; }, clearInterval() {}, setTimeout() { return 1; },
    eventListeners: listeners
  };
  vm.createContext(context);
  vm.runInContext(source, context, { filename: target });
  vm.runInContext(`
    function tick(){for(let i=0;i<10;i++)advanceJobs();}
    function prepare(e){const ds=store.datasets.find(x=>x.schema===schemaFor(e));ds.ready=true;chooseDataset(e,ds.id);checkData(e);}
  `, context);
  return context;
}

const findings = [];
function reproduce(id, title, script) {
  const context = fresh();
  const evidence = vm.runInContext(script, context);
  findings.push({ id, title, result: '已复现', evidence });
}

reproduce('A-01', '新工作流可以复用上一次工作流结果，零次生成就保存成功', `
  startWorkflow('wf-product');
  const priorIds=[];
  for(let stage=0;stage<3;stage++){
    const job=submitTrial();assert(job.id);tick();priorIds.push(job.id);nextWorkflow();
  }
  const count=store.jobs.length;
  startWorkflow('wf-product');nextWorkflow();nextWorkflow();nextWorkflow();
  assert.equal(store.jobs.length,count);
  assert.equal(store.completedWorkflows.length,2);
  assert.deepEqual(store.completedWorkflows[1].outputs.map(x=>x.id),priorIds);
  ({generatedInSecondRun:store.jobs.length-count,completedWorkflows:store.completedWorkflows.length,
    firstOutputs:priorIds,secondOutputs:store.completedWorkflows[1].outputs});
`);

reproduce('A-02', '下一类别忙碌时，工作流仍推进且污染当前图片草稿', `
  setKind('video');draft().reference=true;
  const busy=submitTrial();jobAction(busy.id,'pause');
  startWorkflow('wf-product');const first=submitTrial();tick();
  assert.equal(store.kind,'image');nextWorkflow();
  assert.equal(store.kind,'image');assert.equal(store.workflow.stage,1);
  assert.equal(draft().source.id,first.id);assert.equal(draft().reference,true);
  ({workflowStage:store.workflow.stage,currentKind:store.kind,
    expectedNextKind:'video',busyStatus:busy.status,imageDraftSource:draft().source,
    outputs:store.workflow.outputs,toast:store.toast});
`);

reproduce('A-03', '切换普通草稿与 DFlash 策略后沿用旧组件和已准备状态', `
  setKind('text');const d=draft(),r=runtimeDefaults(d,'cloud');
  r.thinking='off';runtimeChange(r,'speculation','draft',d);
  runtimeChange(r,'draftModel','qwen4-draft',d);r.draftReady=true;
  runtimeChange(r,'speculation','dflash',d);
  assert.equal(r.draftModel,'qwen4-draft');assert(r.draftReady);
  assert.deepEqual(runtimeErrors(d,r),[]);assert.deepEqual(applyRuntime(d,r),[]);
  const job=submitTrial();assert(job.id);
  ({strategy:job.snapshot.runtime.speculation,draftModel:job.snapshot.runtime.draftModel,
    draftReady:job.snapshot.runtime.draftReady,validationErrors:runtimeErrors(d,r)});
`);

reproduce('A-04', '多模态理解切换模型后，界面选项与隐藏任务模式不一致', `
  setKind('vision');model('qwen-omni').ready=true;
  draft().model='qwen-omni';draft().mode='audio';draft().reference=true;
  store.overlay={type:'models',target:'trial'};
  handleAction('choose-model',{dataset:{id:'qwen-vl'}});
  const editor=trialEditor();
  assert.equal(draft().mode,'audio');assert(!editor.includes('value="audio"'));
  const job=submitTrial();assert(job.id);tick();
  assert(resultContent(trialResult()).includes('转写：'));
  ({model:job.snapshot.model,hiddenMode:job.snapshot.mode,
    editorContainsAudioOption:editor.includes('value="audio"'),
    recordedInputs:model(job.snapshot.model).inputs,renderedAnswer:'转写预置结果'});
`);

reproduce('A-05', 'Core ML 转换产物被默认按 PyTorch 路径启动', `
  const e=newExperiment('convert','image','fusion');prepare(e);submitExperiment();tick();
  evaluateExperiment(e);assert(registerCandidate(e,1));
  const candidate=model(e.candidates[0]);assert(candidate.format.includes('Core ML'));
  openModelForTrial(candidate.id);const r=runtimeFor(draft());
  assert.equal(r.engine,'pytorch');assert.deepEqual(runtimeErrors(draft(),r),[]);
  const job=submitTrial();assert(job.id);
  ({artifactFormat:candidate.format,selectedEngine:r.engine,accelerator:r.accelerator,
    validationErrors:runtimeErrors(draft(),r),submitted:job.id});
`);

reproduce('A-06', '运行页设备提示使用全局默认值，与本次提交设备不一致', `
  setKind('text');const d=draft();assert.equal(store.settings.device,'local');
  assert.deepEqual(applyRuntime(d,runtimeDefaults(d,'cloud')),[]);
  const editor=trialEditor();const job=submitTrial();assert(job.id);
  assert(editor.includes('本机 Apple Silicon · 演示执行'));
  assert.equal(job.snapshot.device,'cloud');
  ({displayedDevice:'本机 Apple Silicon',configuredDevice:d.runtime.device,
    submittedDevice:job.snapshot.device,submittedDeviceName:job.snapshot.environment.name});
`);

reproduce('A-07', '编辑字幕回写结果配方，但同次任务快照保持原值，导致两个配置来源', `
  setKind('audio');operation('asr');draft().reference=true;
  const job=submitTrial();tick();const result=trialResult();
  const before=JSON.stringify(result.recipe),snapshotBefore=JSON.stringify(job.snapshot);
  for(const callback of eventListeners.input){
    callback({target:{dataset:{resultTranscript:result.id},value:'用户校正后的字幕',
      tagName:'TEXTAREA',type:'textarea',hasAttribute(){return false;}}});
  }
  assert.notEqual(JSON.stringify(result.recipe),before);
  assert.equal(JSON.stringify(job.snapshot),snapshotBefore);
  assert.equal(result.recipe.transcript,'用户校正后的字幕');
  ({taskSnapshotHasTranscript:Object.hasOwn(job.snapshot,'transcript'),
    recipeTranscript:result.recipe.transcript,displayedTranscript:result.transcript});
`);

const report = {
  target, sha256: crypto.createHash('sha256').update(html).digest('hex'),
  method: '读取最终 HTML 内联脚本，在独立 VM 和最小 DOM 替身中执行真实状态函数及事件。计时器手动推进；未调用模型或浏览器。',
  note: '各断言确认缺陷当前存在。A-07 是可追溯性语义缺陷，需结合产品要求确认配方字段定义。',
  findings
};
const output = path.join(__dirname, 'audit-prototype-counterexamples.json');
fs.writeFileSync(output, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
