// 核对运行配置的有效组合、不可用组合、草稿隔离与结果复用。
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={assert,console};vm.createContext(ctx);
for(const f of ['ailab-unified-state.js','ailab-runtime-state.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+f,'utf8'),ctx);
vm.runInContext(`
let checks=0;const test=(name,fn)=>{fn();checks++;};
test('所有类别默认运行配置',()=>{for(const kind of Object.keys(kinds)){const d=defaultDraft(kind);assert.deepEqual(runtimeErrors(d,runtimeFor(d)),[]);}});
setKind('text');const d=draft();
test('草稿取消不改变原值',()=>{const r=clone(runtimeFor(d));r.context='4096';assert.equal(d.runtime.context,'8192');});
test('思考和上下文应用',()=>{const r=clone(runtimeFor(d));r.thinking='off';r.context='4096';assert.equal(applyRuntime(d,r).length,0);assert.equal(d.runtime.thinking,'off');});
test('输出超过上下文时保留旧值',()=>{const old=JSON.stringify(d.runtime),r=clone(d.runtime);r.maxOutput='8192';assert(applyRuntime(d,r).length);assert.equal(JSON.stringify(d.runtime),old);});
test('空值与非法数值',()=>{for(const k of ['context','maxOutput','temperature','topP','topK','minP','repeatPenalty','kvBudget','memoryLimit']){const r=clone(d.runtime);r[k]='';assert(runtimeErrors(d,r).length,k);}});
test('MTP 不对任意模型放行',()=>{const r=clone(d.runtime);r.speculation='mtp';assert(runtimeErrors(d,r).some(x=>x.includes('MTP')));});
test('DFlash 需引擎、思考及草稿配套',()=>{const r=clone(d.runtime);r.speculation='dflash';assert(runtimeErrors(d,r).length);runtimeChange(r,'engine','dflash',d);r.speculation='dflash';r.draftModel='qwen4-dflash';r.draftReady=true;r.thinking='off';assert.equal(runtimeErrors(d,r).length,0);r.thinking='on';assert(runtimeErrors(d,r).some(x=>x.includes('非思考')));});
test('ANE 不接受原始权重',()=>{const r=runtimeDefaults(d,'local','ane','coreml');assert(runtimeErrors(d,r).some(x=>x.includes('Core ML')));});
test('Core ML 产物允许 ANE 配置',()=>{const src=model('fusion');store.models.push({...src,id:'fusion-coreml',format:'Core ML FP16',runtimeOnly:true});const x=defaultDraft('image');x.model='fusion-coreml';const r=runtimeDefaults(x,'local','ane','coreml');assert.equal(runtimeErrors(x,r).length,0);});
test('AMD 与 Intel 独立硬件路径',()=>{for(const [id,acc] of [['amd','rocm'],['intel','sycl']]){const r=runtimeDefaults(d,id);assert.equal(r.accelerator,acc);assert(runtimeErrors(d,r).some(x=>x.includes('连接')));store.settings.devices[id].ready=true;assert.equal(runtimeErrors(d,r).length,0);}});
test('设备不允许错配后端',()=>{const r=runtimeDefaults(d,'local');r.accelerator='cuda';assert(runtimeErrors(d,r).some(x=>x.includes('不匹配')));});
test('切换硬件保留请求参数且清理优化',()=>{const r=clone(d.runtime);r.speculation='dflash';r.draftReady=true;runtimeChange(r,'device','cloud',d);assert.equal(r.engine,'vllm');assert.equal(r.thinking,'off');assert.equal(r.speculation,'off');assert(!r.draftReady);});
test('CUDA 调度和 Prefill 预算',()=>{const r=runtimeDefaults(d,'cloud');r.chunkedPrefill=true;r.graphs=true;r.decodeBatch='4';assert.equal(runtimeErrors(d,r).length,0);r.prefillChunk='4096';assert(runtimeErrors(d,r).some(x=>x.includes('预算')));});
test('未经部署的分离服务不放行',()=>{const r=runtimeDefaults(d,'cloud');r.splitPD=true;r.prefillEndpoint='https://prefill.example.test';r.decodeEndpoint='https://decode.example.test';assert(runtimeErrors(d,r).some(x=>x.includes('连接器')));});
test('保存提交快照和结果复用',()=>{d.runtime=runtimeDefaults(d,'cloud');d.runtime.thinking='off';d.runtime.prefixCache=true;d.runtime.kvPrecision='fp8';const j=submitTrial();assert(j.id);const frozen=JSON.stringify(j.snapshot.runtime);store.settings.device='local';assert(applyRuntime(d,runtimeDefaults(d)).length);assert.equal(JSON.stringify(j.snapshot.runtime),frozen);for(let i=0;i<10;i++)advanceJobs();const result=history()[0];d.runtime=runtimeDefaults(d,'local');reuseResult(result);assert.equal(d.runtime.device,'cloud');assert.equal(d.runtime.kvPrecision,'fp8');});
test('切换模型不会携带旧思考策略',()=>{d.model='qwen-vl';assert.equal(runtimeFor(d).thinking,'default');assert.equal(runtimeFor(d).modelId,'qwen-vl');});
test('媒体专属数值限制',()=>{const x=defaultDraft('video'),r=runtimeDefaults(x);r.frames='-1';assert(runtimeErrors(x,r).some(x=>x.includes('帧数')));});
console.log(checks+' 组运行优化专项验证通过');
`,ctx);
