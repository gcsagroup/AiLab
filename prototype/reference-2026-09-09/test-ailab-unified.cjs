// 代表性流程与关键边界验证，不调用真实模型。
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={assert,console};vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/ailab-unified-state.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/ailab-runtime-state.js','utf8'),ctx);
vm.runInContext(`
let cases=0;
function tick(){for(let i=0;i<10;i++)advanceJobs();}
function prepare(e){const data=store.datasets.find(x=>x.schema===schemaFor(e));data.ready=true;assert(chooseDataset(e,data.id));checkData(e);assert(e.dataChecked);}
// 四个训练入口，模型与方法组合，输出类型与候选来源。
for(const m of initialModels){for(const method of m.methods){const e=newExperiment('train',m.module,m.id);model(m.id).ready=true;e.method=method;prepare(e);e.sourceStatement='';const job=submitExperiment();assert(job?.id,m.id+'/'+method+':'+e.error);assert.equal(e.snapshot.sourceStatement,'');tick();assert.equal(e.status,'complete');evaluateExperiment(e,true);assert(!registerCandidate(e,1));evaluateExperiment(e);assert(registerCandidate(e,1));assert.equal(model(e.candidates[0]).experiment,e.id);cases++;}}
// AI 只建议，不启动、不判定授权，应用仅改变明确字段，并支持撤销。
let e=newExperiment('train','language');const before=JSON.stringify(e);store.ai.proposal=makeProposal();assert.equal(JSON.stringify(e),before);assert.equal(e.status,'draft');assert(applyProposal());assert.equal(e.steps,'200');assert.equal(e.batch,'1');assert.equal(e.status,'draft');assert(undoProposal());assert.equal(e.steps,'600');assert.equal(e.batch,'2');const beforeQuestion=JSON.stringify(e);assert(answerAI('数据集来源是否合法，是否授权？').includes('不会给出合法性'));assert.equal(JSON.stringify(e),beforeQuestion);cases++;
// 过期建议不可覆盖用户修改；越权字段即使出现在建议对象里也不可应用。
store.ai.proposal=makeProposal();e.steps='750';assert(!applyProposal());assert.equal(e.steps,'750');store.ai.proposal={target:'exp',key:e.id,changes:{sourceStatement:{from:'',to:'已授权'}}};assert(!applyProposal());assert.equal(e.sourceStatement,'');cases++;
// 用户未填写来源或声明，技术检查通过后仍能启动；不由 AI 作授权判断。
e=newExperiment('train','language');prepare(e);e.sourceStatement='';const j=submitExperiment();assert(j.id);store.ai.proposal={target:'exp',key:e.id,changes:{batch:{from:'2',to:'1'}}};assert(!applyProposal());assert.equal(e.batch,'2');cases++;
// 必需字段缺失必须处理；AI 应用只修改任务副本，仍需重新检查。
e=newExperiment('train','language');prepare(e);changeMethod(e,'fixture','missing');checkData(e);assert(!e.dataChecked);assert.equal(submitExperiment().field,'dataChecked');store.ai.proposal=makeProposal('data');assert(applyProposal());assert(!e.dataChecked);checkData(e);assert(e.dataChecked);assert(submitExperiment().id);cases++;
// 粘贴的真实 JSONL 样例也按字段检查，全为空时不可训练。
e=newExperiment('train','language');const data=store.datasets.find(x=>x.schema==='sft');const priorRows=data.rows;data.rows=[{messages:[]},{messages:[{role:'user',content:'样例'}]},{messages:[{role:'assistant',content:'回应'}]}];chooseDataset(e,data.id);checkData(e);assert(!e.dataChecked);e.excluded=true;checkData(e);assert(e.dataChecked);data.rows=[{messages:[]}];checkData(e);assert(!e.dataChecked);if(priorRows===undefined)delete data.rows;else data.rows=priorRows;cases++;

// 改训练类型后必须重新选择对应数据，不能沿用不兼容格式。
e=newExperiment('train','language');prepare(e);changeMethod(e,'method','dpo');assert.equal(e.dataset,null);assert.equal(schemaFor(e),'dpo');assert.equal(submitExperiment().field,'dataset');prepare(e);assert(submitExperiment().id);cases++;
// 冻结配置、暂停恢复、失败后复制新尝试。
e=newExperiment('train','image');prepare(e);const originalSteps=e.steps;submitExperiment();jobAction(e.id,'pause');advanceJobs();assert.equal(e.progress,0);jobAction(e.id,'resume');advanceJobs();assert.equal(e.progress,10);failExperiment(e);const source=e.id;const n=retryExperiment(e);assert.equal(e.status,'failed');assert.equal(n.source,source);assert.equal(n.status,'draft');assert.equal(n.steps,originalSteps);assert.notEqual(n.id,source);cases++;
// 服务器未连接、非法参数和本机 QLoRA 组合清楚阻断。
e=newExperiment('train','language');prepare(e);e.device='remote';assert.equal(submitExperiment().field,'device');e.device='cloud';e.steps='-1';assert.equal(submitExperiment().field,'steps');e.steps='200';e.adapt='qlora';e.device='local';assert.equal(submitExperiment().field,'device');cases++;
// 专项实验均保留评测和候选；量化/转换产物不能误作训练原权重。
for(const type of ['armor','distill','merge','quantize','convert']){e=newExperiment(type,type==='convert'?'image':'language',type==='convert'?'fusion':undefined);prepare(e);assert(submitExperiment().id,e.error);tick();evaluateExperiment(e);assert(registerCandidate(e,1));const candidate=model(e.candidates[0]);assert.equal(candidate.runtimeOnly,['quantize','convert'].includes(type));if(candidate.runtimeOnly){const next=newExperiment('train',e.module);assert(!chooseTrainingModel(next,candidate.id));}cases++;}
// 下载可暂停/取消，再次下载独立继续。
model('flux').ready=false;downloadModel('flux');let dl=store.jobs.find(x=>x.type==='download'&&x.model==='flux'&&x.status==='running');jobAction(dl.id,'pause');advanceJobs();assert.equal(dl.progress,0);jobAction(dl.id,'cancel');downloadModel('flux');tick();assert(model('flux').ready);cases++;
// 所有运行类别、输入缺失与作品配方冻结。
for(const kind of ['text','vision','image','video','audio']){setKind(kind);const d=draft();d.model=templateModels[kind];d.reference=true;d.seed='42';d.prompt='代表性输入';const j=submitTrial();assert(j.id);d.prompt='执行后修改';tick();assert.equal(history()[0].prompt,'代表性输入');assert.equal(history()[0].recipe.model,templateModels[kind]);cases++;}
setKind('audio');for(const op of Object.keys(audioOps)){operation(op);draft().reference=true;draft().consent=false;assert(submitTrial().id);tick();assert.equal(history()[0].op,op);cases++;}
// 后台任务完成后结果仍归属原项目。
selectProject('商品内容');setKind('image');draft().prompt='商品项目样例';let job=submitTrial();selectProject('声音研究');tick();assert(!history().some(x=>x.id===job.id));selectProject('商品内容');assert.equal(history()[0].prompt,'商品项目样例');cases++;
console.log(cases+' 组代表性验证通过');
`,ctx);

const html=fs.readFileSync(__dirname+'/ailab-unified.html','utf8');new vm.Script(html.match(/<script>([\s\S]*?)<\/script>/)[1]);assert(Buffer.byteLength(html)<1000000);assert(!/<(?:html|body|head)[ >]/i.test(html));console.log('脚本语法、片段结构与体积通过');
