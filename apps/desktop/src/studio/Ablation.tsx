import { useEffect, useState } from 'react';
import { FileCheck, ChevronDown } from 'lucide-react';
import { errorMessage } from '../api';
import { Error, Field, PathField, request, useDraft } from './common';
import TaskPanel from './TaskPanel';
import { HeaderJobAction } from './JobActions';
import type { Assets, Job } from './types';

type Value = string | number | boolean | (string | number)[];
type Template = { fields: Record<string, Value>; reference: string; advanced: string };
const labels: Record<string, string> = {
  seed: '随机种子', 'model.dtype_fallback_order': '优先精度', 'model.backend': '推理后端',
  'inference.batch_size': '批大小', 'inference.max_batch_size': '最大批大小',
  'steering.vector_method': '方向向量方法', 'steering.steering_mode': '修改方式', 'steering.decay_kernel': '衰减核',
  'steering.orthogonal_projection': '正交投影', 'steering.projected_abliteration': '投影消融', 'steering.winsorize_vectors': '向量缩尾处理',
  'steering.weight_normalization': '权重归一化', 'steering.strength_range': '强度范围', 'steering.fixed_vector_scope': '固定向量范围',
  'optimization.num_trials': '试验次数', 'optimization.num_warmup_trials': '预热次数', 'optimization.checkpoint_dir': '检查点目录（留空自动创建）',
  'kl.target': 'KL 目标', 'detection.llm_judge': '启用 LLM 裁判', 'detection.llm_judge_model': '裁判模型',
  'detection.llm_judge_base_url': '裁判服务地址', 'detection.llm_judge_api_key_env': '裁判 API Key 环境变量名',
};
const groups: Record<string, string> = { basic: '基本设置', inference: '推理', steering: '消融参数', optimization: '优化', detection: '检测与裁判' };

export default function Ablation({ assets, vllmReady = false }: { assets: Assets; vllmReady?: boolean }) {
  const [template, setTemplate] = useState<Template>(); const [form, set] = useDraft('ablation', { model: '', toml: '', fields: {} as Record<string, Value> });
  const [job, setJob] = useDraft('ablation-job', { id: '' }); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [preview, setPreview] = useState('');
  useEffect(() => { let alive = true; void request<Template>('GET', '/ablation/template').then(t => { if (alive) setTemplate(t); }).catch(e => { if (alive) setError(errorMessage(e)); }); return () => { alive = false; }; }, []);
  const [checking, setChecking] = useState(false); const [check, setCheck] = useState<{ architectures: string[]; backends: { backend: string; status: string; detail: string; version?: string }[]; note: string }>();
  const fields = { ...template?.fields, ...form.fields };
  function update(key: string, value: Value) { set({ ...form, fields: { ...form.fields, [key]: value } }); setPreview(''); }
  async function submit(start: boolean) {
    setBusy(true); setError('');
    try { const body = { ...form, fields }; if (start) { const j = await request<Job>('POST', '/ablation', body); setJob({ id: j.id }); } else { const result = await request<{ toml: string }>('POST', '/ablation/validate', body); setPreview(result.toml); } }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <div className="st-ablation-layout"><HeaderJobAction id={job.id} form="ablation-form" label="开始消融" disabled={busy || !template || !form.model} /><section className="st-panel st-ablation-form"><form id="ablation-form" onSubmit={e => { e.preventDefault(); void submit(true); }}>
    <div className="st-model-check"><PathField title="Safetensors 模型目录" value={form.model} onChange={model => { set({ ...form, model }); setCheck(undefined); }} items={assets.models.filter(m => m.format === 'safetensors')} /><button type="button" disabled={checking || !form.model} onClick={async () => { setChecking(true); setError(''); try { setCheck(await request('POST', '/ablation/compatibility', { model: form.model })); } catch (e) { setError(errorMessage(e)); } finally { setChecking(false); } }}>{checking ? '检查中…' : '兼容性检查'}</button></div>
    {check && <div className="st-compatibility"><strong>{check.architectures.join(', ')}</strong>{check.backends.map(b => <p key={b.backend}><span className="st-tag">{b.backend.toUpperCase()} {b.version}</span> {b.detail}</p>)}<small>{check.note}</small></div>}
    {Object.entries(groups).map(([group, title]) => { const entries = Object.entries(fields).sort((a, b) => Number(typeof a[1] === 'boolean') - Number(typeof b[1] === 'boolean')).filter(([key]) => (key === 'seed' || key.startsWith('model.') ? 'basic' : key.startsWith('kl.') ? 'steering' : key.split('.')[0]) === group); return entries.length ? <fieldset className={`st-ablation-group st-ablation-${group}`} key={group}><legend>{title}</legend><div className="st-ablation-fields">{entries.filter(([,value]) => typeof value !== 'boolean').map(([key, value]) => key === 'model.dtype_fallback_order' ? <div className="st-field" key={key}><span className="st-field-title">优先精度</span><details className="st-multiselect"><summary><span>{Array.isArray(value) && value.length ? value.map(v => ({float32:'Float32',bfloat16:'Bfloat16',float16:'Float16'}[String(v)] || v)).join(' → ') : 'Auto'}</span><ChevronDown size={14} /></summary><div className="st-precision-options">{[['', 'Auto（自动）'], ['float32', 'Float32'], ['bfloat16', 'Bfloat16'], ['float16', 'Float16']].map(([v, label]) => <label className="st-check" key={v}><input type="checkbox" checked={Array.isArray(value) && (v ? value.includes(v) : !value.length)} onChange={e => update(key, !v ? [] : e.target.checked ? [...(Array.isArray(value) ? value : []), v] : (Array.isArray(value) ? value : []).filter(x => x !== v))} />{label}</label>)}</div></details></div> : key === 'model.backend' || key === 'steering.steering_mode' ? <Field key={key} title={labels[key]}><select value={String(value)} onChange={e => update(key, e.target.value)}>{(key === 'model.backend' ? ['hf', 'vllm'] : ['direct', 'lora']).map(v => <option value={v} key={v} disabled={v === 'vllm' && !vllmReady}>{v === 'vllm' ? `vLLM${vllmReady ? '' : '（未安装）'}` : v === 'hf' ? 'HF' : v}</option>)}</select></Field> : typeof value === 'boolean' ? <label className="st-check st-ablation-toggle" key={key}><input type="checkbox" checked={value} onChange={e => update(key, e.target.checked)} />{labels[key] || key}</label> : <Field key={key} title={labels[key] || key}><input required={key !== 'optimization.checkpoint_dir'} disabled={key === 'model.backend'} type={typeof value === 'number' ? 'number' : 'text'} step="any" value={Array.isArray(value) ? value.join(', ') : String(value)} onChange={e => { const raw = e.target.value; update(key, Array.isArray(value) ? raw.split(',').map(v => typeof value[0] === 'number' ? Number(v.trim()) : v.trim()) : typeof value === 'number' ? Number(raw) : raw); }} /></Field>)}</div><div className="st-ablation-toggles">{entries.filter(([,value]) => typeof value === 'boolean').map(([key,value]) => <label className="st-check" key={key}><input type="checkbox" checked={Boolean(value)} onChange={e => update(key,e.target.checked)} />{labels[key] || key}</label>)}</div></fieldset> : null; })}
    <details><summary>高级 TOML 配置</summary><p className="st-note">表单覆盖同名字段；模型位置和导出目录由任务绑定。参考模板包含历史路径，请检查后使用。</p><button type="button" onClick={() => { if (template) set({ ...form, toml: template.reference }); }}>载入 abliterix_all.toml 参考</button><Field title="附加 TOML"><textarea className="st-code" rows={18} value={form.toml} spellCheck={false} onChange={e => set({ ...form, toml: e.target.value })} /></Field></details>
    <Error text={error} /><footer><button type="button" disabled={busy || !template} onClick={() => void submit(false)}><FileCheck size={16} />检查配置</button></footer>
    {preview && <details open><summary>最终执行配置预览</summary><pre className="st-code">{preview}</pre></details>}
  </form></section><div>{job.id ? <TaskPanel key={job.id} id={job.id} /> : <section className="st-panel st-ablation-monitor"><header><h2>消融进度与日志</h2></header><div className="st-empty">等待开始消融</div></section>}</div></div>;
}
