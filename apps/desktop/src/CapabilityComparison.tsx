import { useContext, useEffect, useRef, useState } from 'react';
import { LibraryReadContext } from './LibraryReadContext';
import { api, errorMessage } from './api';
import type { Model, Task } from './types';
import { Button, Dialog, ErrorNotice } from './ui';
import type { EvaluationReport } from './Evaluation';

function useCurrentView() {
  const captureLibraryRead = useContext(LibraryReadContext); const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  return () => { const libraryCurrent = captureLibraryRead(); return () => live.current && libraryCurrent(); };
}

export function CapabilityDialog({ projectId, models, onClose, onCreated }: { projectId: string; models: Model[]; onClose: () => void; onCreated: (task: Task) => void }) {
  const capture = useCurrentView();
  const supported = models.filter(model => model.modality === 'text' && ['safetensors', 'mlx-safetensors'].includes(model.format) && (!model.default_engine || model.default_engine === 'mlx') && model.model_config?.model_type === 'qwen2' && model.model_config.hidden_size === 896 && model.model_config.num_hidden_layers === 24);
  const baselines = supported.filter(model => !model.model_config?.quantization && !model.model_config?.quantization_config);
  const [baseline, setBaseline] = useState(baselines[0]?.id || ''); const [candidate, setCandidate] = useState(supported.find(model => model.id !== baselines[0]?.id)?.id || '');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const key = useRef<string | null>(null);
  async function create() { const isCurrent = capture(); setBusy(true); setError(''); key.current ||= crypto.randomUUID(); try { const task = await api<Task>('POST', '/evaluations/capability', { project_id: projectId, model_id: baseline, candidate_model_id: candidate }, key.current); if (isCurrent()) onCreated(task); } catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { if (isCurrent()) setBusy(false); } }
  return <Dialog title="新建普通能力对照" wide preventClose={busy} onClose={onClose}><div className="form-stack"><p>使用固定 8 题：3 道整数数学题、2 道格式题、1 道排序题和 2 道普通日常题。两模型分别加载，参数相同，逐题保留实际回答。</p><p className="muted">当前支持 Qwen2.5-0.5B，基线为未量化权重，候选可为合并、蒸馏或 MLX 4-bit 模型；两侧分词器和模板须一致。人工复核独立保存，本对照不用于质量准入。</p><p className="muted">模型未列出时，请检查模型库中是否已有符合条件的 Qwen2.5-0.5B 权重。</p><fieldset className="task-fields" disabled={busy}>{([['基线模型', baseline, setBaseline], ['候选模型', candidate, setCandidate]] as const).map(([label, value, setter]) => <label key={label}>{label}<select value={value} onChange={e => { setter(e.target.value); key.current = null; }}><option value="">请选择模型</option>{(label === '基线模型' ? baselines : supported).map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>)}</fieldset><ErrorNotice message={error} /><Button primary busy={busy} disabled={!baseline || !candidate || baseline === candidate} onClick={create}>冻结题集并创建对照</Button></div></Dialog>;
}

export type Reviews = { revision: number; items: { id: string; revision: number; sample_id: string; variant: 'baseline' | 'candidate'; verdict: string; note: string; created_at: string }[] };
const verdicts = { normal: '正常协助', false_refusal: '确认误拒绝', uncertain: '无法确定' };
export function CapabilityReviews({ attemptId, report, reviews, onSaved }: { attemptId: string; report: EvaluationReport; reviews: Reviews; onSaved: (value: Reviews) => void }) {
  const capture = useCurrentView();
  const [sample, setSample] = useState(report.samples[0]?.id || ''); const [variant, setVariant] = useState<'baseline' | 'candidate'>('candidate');
  const [verdict, setVerdict] = useState<keyof typeof verdicts>('uncertain'); const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const key = useRef<string | null>(null);
  const selected = report.samples.find(item => item.id === sample);
  const latest = new Map<string, Reviews['items'][number]>(); reviews.items.forEach(item => latest.set(`${item.sample_id}:${item.variant}`, item));
  async function save() { const isCurrent = capture(); setBusy(true); setError(''); key.current ||= crypto.randomUUID(); try { const value = await api<Reviews>('POST', `/evaluations/${attemptId}/reviews`, { expected_revision: reviews.revision, sample_id: sample, variant, verdict, note: note.trim() }, key.current); if (isCurrent()) { onSaved(value); setNote(''); key.current = null; } } catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { if (isCurrent()) setBusy(false); } }
  return <section className="result-card capability-reviews" aria-label="普通任务人工复核"><h3>普通任务人工复核</h3><p className="muted">正常协助不代表答案正确；这里只记录是否拒绝普通任务及理由。记录保留历史，不能覆盖原始回答和自动评分。</p><p>已复核 {latest.size} / {report.samples.length * 2} 项 · 确认误拒绝 {[...latest.values()].filter(item => item.verdict === 'false_refusal').length} 项</p><fieldset className="task-fields" disabled={busy}><label>复核题目<select value={sample} onChange={e => { setSample(e.target.value); key.current = null; }}>{report.samples.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label><label>复核对象<select value={variant} onChange={e => { setVariant(e.target.value as typeof variant); key.current = null; }}><option value="baseline">基线</option><option value="candidate">候选</option></select></label>{selected && <><p>{selected.prompt}</p><pre>{selected[variant].output ?? '缺少输出'}</pre></>}<label>人工结论<select value={verdict} onChange={e => { setVerdict(e.target.value as typeof verdict); key.current = null; }}>{Object.entries(verdicts).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>复核理由<textarea maxLength={2000} value={note} onChange={e => { setNote(e.target.value); key.current = null; }} /></label></fieldset><ErrorNotice message={error} /><Button busy={busy} disabled={!note.trim() || !selected} onClick={save}>保存人工复核</Button><details><summary>查看复核历史（{reviews.items.length} 条）</summary>{reviews.items.map(item => <article key={item.id}><strong>第 {item.revision} 次 · {item.sample_id} · {item.variant === 'baseline' ? '基线' : '候选'} · {verdicts[item.verdict as keyof typeof verdicts]}</strong><p>{item.note}</p></article>)}</details></section>;
}
