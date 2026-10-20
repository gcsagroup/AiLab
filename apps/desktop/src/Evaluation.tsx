import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, FileCheck2, FolderOpen, Play } from 'lucide-react';
import { api, canPickFile, errorMessage, pickImport, type ImportSelection } from './api';
import type { Adapter, Attempt, Candidate, Model, Preflight, Task } from './types';
import type { ExportObject } from './ExportDialog';
import { RunResult } from './Workbench';
import { CapabilityReviews, type Reviews } from './CapabilityComparison';
import { Badge, Button, Dialog, Empty, ErrorNotice } from './ui';

export const evaluationCategories = { business: '业务任务', format: '输出格式', regression: '能力回归', behavior: '行为对照' };
type Category = keyof typeof evaluationCategories;
type Criteria = { schema_version: 'text-rules-v1'; category_min_pass_rate: Record<Category, number>; regression_tolerance: number; generation: { max_tokens: number; temperature: 0; top_p: 1; seed: number } };
export type EvaluationPlan = { id: string; name: string; sample_count: number; category_counts: Record<Category, number>; evaluation_plan_digest?: string; manifest_digest?: string; criteria: Criteria };
type Score = { manual_pending?: number; passed: number; total: number; pass_rate: number | null };
type Output = { output: string | null; status: string; reason: string };
export type EvaluationReport = { status: string; eligible: boolean; prospective_plan_bound: boolean; evaluation_kind?: 'quantized_model' | 'capability_comparison'; model_comparison?: { baseline_model_id: string; candidate_model_id: string; baseline_model_manifest_digest: string; candidate_model_manifest_digest: string; candidate_default_engine: string }; counts: Record<'baseline' | 'candidate', Record<Category, Score>>; criteria: Criteria; regression_pass_rate_delta: number; manual_pending: number; unknown: number; blocking: { code: string; category?: Category; message?: string; count?: number }[]; samples: { id: string; category: Category; prompt: string; rule: unknown; baseline: Output; candidate: Output }[]; quality_scope: string };
type EvaluationRecord = Attempt & { reviews?: Reviews; adapter_id: string | null; candidate_model_id?: string; evaluation_plan_id: string; report: EvaluationReport | null; report_error?: { message: string } | null };
const statusLabels: Record<string, string> = { passed: '通过', failed: '未通过', needs_review: '需要人工评审', unknown: '证据不完整', pending: '待人工评审' };
const blockingLabels: Record<string, string> = { CATEGORY_THRESHOLD_FAILED: '未达到该类别最低通过率', REGRESSION_LIMIT_FAILED: '回归退步超过允许范围', MANUAL_REVIEW_PENDING: '人工评审尚未完成', EVALUATION_OUTPUT_MISSING: '缺少实际输出', POSTHOC_EVALUATION: '来源训练未提前绑定同一评测方案，事后评测不能用于准入', MODEL_QUALITY_PLAN_MISMATCH: '本次没有使用该量化模型首次固定的方案，只能查看对照结果' };

export function EvaluationPlanDialog({ projectId, onClose, onCreated }: { projectId: string; onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('文本质量评测');
  const [selection, setSelection] = useState<ImportSelection>({ path: '' });
  const [criteria, setCriteria] = useState<Criteria>({ schema_version: 'text-rules-v1', category_min_pass_rate: { business: 1, format: 1, regression: 1, behavior: 1 }, regression_tolerance: 0, generation: { max_tokens: 64, temperature: 0, top_p: 1, seed: 0 } });
  const [created, setCreated] = useState<EvaluationPlan | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const requestKey = useRef<string | null>(null);
  const live = useRef(true);
  const scope = useRef({ projectId });
  if (scope.current.projectId !== projectId) scope.current = { projectId };
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  function capture() { const started = scope.current; return () => live.current && scope.current === started; }
  function edited() { requestKey.current = null; setError(''); }
  async function choose() {
    const isCurrent = capture(); setBusy(true);
    try { const chosen = await pickImport('dataset'); if (isCurrent() && chosen) { setSelection(chosen); edited(); } }
    catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { if (isCurrent()) setBusy(false); }
  }
  async function freeze(event: React.FormEvent) {
    event.preventDefault(); const isCurrent = capture(); setBusy(true); setError(''); requestKey.current ||= crypto.randomUUID();
    try {
      const result = await api<EvaluationPlan>('POST', '/evaluation-plans', { project_id: projectId, name: name.trim(), dataset_path: selection.path, dataset_grant_id: selection.grant_id, criteria }, requestKey.current);
      if (isCurrent()) { setCreated(result); onCreated(); }
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { if (isCurrent()) setBusy(false); }
  }
  return <Dialog title="冻结评测方案" wide onClose={onClose} preventClose={busy}>
    {created ? <><p className="export-success">评测数据与规则已保存为独立版本</p><PlanSummary plan={created} /><p className="muted">适配器需在训练前选择此方案；量化模型在首次创建评测时固定准入方案。后续更换方案只能做对照。</p><Button primary onClick={onClose}>完成</Button></> : <form className="form-stack" onSubmit={freeze}>
      <p className="muted">先确定测试问题和通过标准。适配器需在训练前冻结，量化模型需在首次评测前冻结。冻结后不能覆盖修改。</p>
      <fieldset className="task-fields" disabled={busy}>
        <label>方案名称<input required maxLength={80} value={name} onChange={e => { setName(e.target.value); edited(); }} /></label>
        <label>评测 JSONL 文件<div className="input-action"><input required aria-label="评测 JSONL 文件" readOnly={canPickFile()} value={selection.path} onChange={e => { setSelection({ path: e.target.value }); edited(); }} placeholder="选择包含四类评测问题的本机文件" />{canPickFile() && <Button onClick={choose}><FolderOpen size={15} />选择文件</Button>}</div></label>
        <details><summary>查看数据格式与规则</summary><p>每行一个对象，包含 id、category、prompt、rule。四个类别都至少有一条问题。测试问题应与训练问题独立。</p><pre>{'{"id":"format-1","category":"format","prompt":"返回仅含 ok:true 的 JSON 对象","rule":{"type":"json_equals","expected":{"ok":true}}}'}</pre><p>类别：business 业务、format 格式、regression 回归、behavior 行为。规则可用 exact 精确答案、contains_all 关键词、json_equals 严格 JSON 或 manual 人工评审；人工项未完成时不能登记候选。</p></details>
        <h3>最低通过率</h3><div className="two-fields">{(Object.entries(evaluationCategories) as [Category, string][]).map(([key, label]) => <label key={key}>{label}（%）<input required type="number" min={1} max={100} value={criteria.category_min_pass_rate[key] * 100} onChange={e => { setCriteria({ ...criteria, category_min_pass_rate: { ...criteria.category_min_pass_rate, [key]: Number(e.target.value) / 100 } }); edited(); }} /></label>)}</div>
        <div className="two-fields"><label>回归允许下降（百分点）<input required type="number" min={0} max={100} value={criteria.regression_tolerance * 100} onChange={e => { setCriteria({ ...criteria, regression_tolerance: Number(e.target.value) / 100 }); edited(); }} /></label><label>每条最大输出 token<input required type="number" min={1} max={512} value={criteria.generation.max_tokens} onChange={e => { setCriteria({ ...criteria, generation: { ...criteria.generation, max_tokens: Number(e.target.value) } }); edited(); }} /></label></div>
        <small className="muted">基线与候选使用相同的确定性生成参数：温度 0、Top-p 1、种子 0，分别在独立进程中加载。</small>
      </fieldset><ErrorNotice message={error} /><Button type="submit" primary busy={busy} disabled={!name.trim() || !selection.path.trim()}><FileCheck2 size={16} />检查并冻结方案</Button>
    </form>}
  </Dialog>;
}

export function PlanSummary({ plan }: { plan: EvaluationPlan }) {
  return <section className="review-box"><h3>{plan.name}</h3><p>{plan.sample_count} 条固定问题</p><dl className="facts">{(Object.entries(evaluationCategories) as [Category, string][]).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{plan.category_counts[key] || 0} 条 · 最低 {plan.criteria.category_min_pass_rate[key] * 100}%</dd></div>)}<div><dt>回归允许下降</dt><dd>{plan.criteria.regression_tolerance * 100} 个百分点</dd></div></dl><details><summary>固定方案编号</summary><p className="break-anywhere">{plan.id}</p><p className="break-anywhere">{plan.evaluation_plan_digest || plan.manifest_digest}</p></details></section>;
}

export function EvaluationStartDialog({ projectId, adapters, models = [], plans, initialAdapter, initialModel, onClose, onCreated }: { projectId: string; adapters: Adapter[]; models?: Model[]; plans: EvaluationPlan[]; initialAdapter?: string; initialModel?: string; onClose: () => void; onCreated: (task: Task) => void }) {
  const quantizedModels = models.filter(item => item.format === 'mlx-safetensors' && item.default_engine === 'mlx' && item.source_model_id);
  const [kind, setKind] = useState<'adapter' | 'quantized_model'>(initialModel || (!adapters.length && quantizedModels.length) ? 'quantized_model' : 'adapter');
  const [adapterId, setAdapterId] = useState(initialAdapter || adapters[0]?.id || ''); const [modelId, setModelId] = useState(initialModel || quantizedModels[0]?.id || ''); const [planId, setPlanId] = useState(plans[0]?.id || '');
  const model = quantizedModels.find(item => item.id === modelId);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const requestKey = useRef<string | null>(null);
  async function create() {
    setBusy(true); setError(''); requestKey.current ||= crypto.randomUUID();
    try { onCreated(await api<Task>('POST', '/evaluations', { project_id: projectId, ...(kind === 'quantized_model' ? { candidate_model_id: modelId } : { adapter_id: adapterId }), evaluation_plan_id: planId }, requestKey.current)); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title="新建独立评测" wide onClose={onClose} preventClose={busy}><div className="form-stack"><p className="muted">{kind === 'quantized_model' ? '比较来源原权重与该量化模型。首次创建任务会固定该模型的准入方案；更换方案只作对照。' : '比较同一基座在训练前后的输出。'}下一步检查资源与来源，再明确开始评测。</p><fieldset className="task-fields" disabled={busy}><label>比较类型<select value={kind} onChange={e => { setKind(e.target.value as typeof kind); requestKey.current = null; }}><option value="adapter">适配器与原基座</option><option value="quantized_model">量化模型与原权重</option></select></label>{kind === 'quantized_model' ? <><label>量化模型<select value={modelId} onChange={e => { setModelId(e.target.value); requestKey.current = null; }}><option value="">选择有转换来源的 MLX 量化模型</option>{quantizedModels.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>{model && <p>原权重：{models.find(item => item.id === model.source_model_id)?.name || model.source_model_id} · MLX 4-bit</p>}{model?.quality_plan_ref && model.quality_plan_ref.evaluation_plan_id !== planId && <p className="warning">所选方案与首次固定方案不同，报告不能用于准入。</p>}</> : <label>评测适配器<select value={adapterId} onChange={e => { setAdapterId(e.target.value); requestKey.current = null; }}>{adapters.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}<label>冻结评测方案<select value={planId} onChange={e => { setPlanId(e.target.value); requestKey.current = null; }}>{plans.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label></fieldset>{plans.find(item => item.id === planId) && <PlanSummary plan={plans.find(item => item.id === planId)!} />}<ErrorNotice message={error} /><Button primary busy={busy} disabled={!(kind === 'quantized_model' ? modelId : adapterId) || !planId} onClick={create}>创建评测任务</Button></div></Dialog>;
}

export function EvaluationResult({ report }: { report: EvaluationReport }) {
  const capability = report.evaluation_kind === 'capability_comparison';
  return <section className="result-card evaluation-report" aria-label={capability ? '普通能力对照报告' : '质量评测报告'}><div className="result-header"><h3>{capability ? '普通能力对照报告' : '质量评测报告'}</h3><Badge tone={report.eligible ? 'good' : 'danger'}>{statusLabels[report.status] || '待核对'}</Badge></div><p className="muted">{report.quality_scope}</p>
    {report.evaluation_kind === 'quantized_model' && <p>比较对象：来源原权重 → MLX 4-bit 量化模型</p>}
    <div className="table-scroll"><table><thead><tr><th>类别</th><th>基线通过</th><th>候选通过</th><th>{capability ? '计分方式' : '最低要求'}</th></tr></thead><tbody>{(Object.entries(evaluationCategories) as [Category, string][]).map(([key, label]) => <tr key={key}><th>{label}</th><td>{report.counts.baseline[key].passed} / {report.counts.baseline[key].total}</td><td>{report.counts.candidate[key].passed} / {report.counts.candidate[key].total}</td><td>{capability ? (key === 'behavior' ? '待人工复核' : '固定规则') : `${report.criteria.category_min_pass_rate[key] * 100}%`}</td></tr>)}</tbody></table></div>
    <p>回归通过率变化：{(report.regression_pass_rate_delta * 100).toFixed(1)} 个百分点</p>
    {report.blocking.map((issue, index) => <p className="warning" key={index}>{issue.category && `${evaluationCategories[issue.category]}：`}{issue.message || blockingLabels[issue.code] || `验收未满足（${issue.code}）`}{issue.count !== undefined && `（${issue.count} 项）`}</p>)}
    {report.evaluation_kind !== 'capability_comparison' && !report.prospective_plan_bound && !report.blocking.some(item => item.code === 'POSTHOC_EVALUATION') && <p className="warning">本次为事后对照，不能用于候选准入。</p>}
    <details><summary>逐条查看问题、实际输出与判定</summary><div className="evaluation-samples">{report.samples.map(sample => <article key={sample.id}><h4>{evaluationCategories[sample.category]} · {sample.id}</h4><p>{sample.prompt}</p><div className="two-fields">{(['baseline', 'candidate'] as const).map(name => <section key={name}><strong>{name === 'baseline' ? '基线输出' : '候选输出'} · {statusLabels[sample[name].status] || '待核对'}</strong><pre>{sample[name].output ?? '未取得输出'}</pre><small>{sample[name].reason}</small></section>)}</div><details><summary>预定判定规则</summary><pre>{JSON.stringify(sample.rule, null, 2)}</pre></details></article>)}</div></details>
  </section>;
}

export function EvaluationTask({ task, plans, adapters, models, candidates = [], onBack, registerLeave, onUpdated, onExport }: { task: Task; plans: EvaluationPlan[]; adapters: Adapter[]; models: Model[]; candidates?: Candidate[]; onBack: () => void; registerLeave: (handler: (() => Promise<boolean>) | null) => void; onUpdated: () => void; onExport: (object: ExportObject) => void }) {
  const [attempts, setAttempts] = useState(task.attempts || (task.latest_attempt ? [task.latest_attempt] : []));
  const [attempt, setAttempt] = useState<Attempt | null>(task.latest_attempt || task.attempts?.[0] || null);
  const [record, setRecord] = useState<EvaluationRecord | null>(null); const [version, setVersion] = useState(0);
  const [preflight, setPreflight] = useState<Preflight | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [registered, setRegistered] = useState(false);
  const submitKey = useRef<string | null>(null); const registerKeys = useRef(new Map<string, string>());
  const plan = plans.find(item => item.id === task.draft.evaluation_plan_id); const adapter = adapters.find(item => item.id === task.draft.adapter_id);
  const capabilityMode = task.draft.evaluation_kind === 'capability_comparison';
  const modelMode = task.draft.evaluation_kind === 'quantized_model' || capabilityMode; const candidateModel = models.find(item => item.id === task.draft.candidate_model_id);
  const targetId = modelMode ? candidateModel?.id : adapter?.id;
  const alreadyRegistered = registered || candidates.some(item => item.quality_status === 'passed' && Boolean(targetId) && (modelMode ? item.candidate_type === 'quantized_model' && item.model_id === targetId : item.adapter_id === targetId));
  useEffect(() => { registerLeave(async () => { if (busy) setError('当前操作尚未完成，请稍后再离开。'); return !busy; }); return () => registerLeave(null); }, [busy]);
  useEffect(() => {
    setRecord(null); setRegistered(false); if (!attempt) return;
    let live = true;
    void api<EvaluationRecord>('GET', `/evaluations/${attempt.id}`).then(value => { if (live) setRecord(value); }).catch(e => { if (live) setError(errorMessage(e)); });
    return () => { live = false; };
  }, [attempt?.id, version]);
  async function check() { setBusy(true); setError(''); try { setPreflight(await api<Preflight>('POST', `/tasks/${task.id}/preflight`, { draft_revision: task.draft_revision })); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function submit() {
    if (!preflight?.can_submit) return; setBusy(true); setError(''); submitKey.current ||= crypto.randomUUID();
    try { const value = await api<Attempt>('POST', `/tasks/${task.id}/attempts`, { preflight_id: preflight.preflight_id, expected_revision: task.draft_revision }, submitKey.current); setAttempt(value); setAttempts(old => [value, ...old.filter(item => item.id !== value.id)]); setPreflight(null); submitKey.current = null; onUpdated(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function register() {
    if (!record || !targetId) return; setBusy(true); setError(''); if (!registerKeys.current.has(record.id)) registerKeys.current.set(record.id, crypto.randomUUID());
    try { await api('POST', `/candidates/${targetId}/register`, { evaluation_ids: [record.id], ...(modelMode ? { candidate_type: 'quantized_model' } : {}) }, registerKeys.current.get(record.id)); setRegistered(true); onUpdated(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <><div className="breadcrumb"><button disabled={busy} onClick={onBack}><ArrowLeft size={15} />模型实验室</button></div><div className="page-heading"><div><h1>{task.name}</h1><p>基线与候选分别独立加载，使用同一冻结问题与规则。</p></div></div><div className="workbench-layout"><section className="composer" aria-label="评测配置"><h2>本次固定对照</h2><dl className="facts"><div><dt>{capabilityMode ? "候选模型" : modelMode ? "量化模型" : "适配器"}</dt><dd>{modelMode ? candidateModel?.name || task.draft.candidate_model_id : adapter?.name || task.draft.adapter_id}</dd></div><div><dt>{capabilityMode ? "基线模型" : modelMode ? "来源原权重" : "基座模型"}</dt><dd>{models.find(item => item.id === task.draft.model_id)?.name || task.draft.model_id}</dd></div></dl>{plan ? <PlanSummary plan={plan} /> : <ErrorNotice message="评测方案未取得，请刷新项目记录后重试。" />}<ErrorNotice message={error} />{preflight && <section className="preflight"><strong>{preflight.can_submit ? '检查通过，可以开始评测' : '请先完成以下准备'}</strong>{preflight.blocking.map((item, i) => <p className="error" key={i}>{item.message}</p>)}{preflight.warnings.map((item, i) => <p className="warning" key={i}>{item.message}</p>)}</section>}{preflight?.can_submit ? <Button primary busy={busy} onClick={submit}><Play size={16} />开始独立评测</Button> : <Button primary busy={busy} onClick={check}><FileCheck2 size={16} />检查评测配置</Button>}<p className="muted">{capabilityMode ? '执行完成后查看逐题结果，并记录人工复核；本对照不能登记质量候选。' : '执行完成仅表示报告已生成，候选登记仍需全部规则和来源检查通过。'}</p></section><div className="result-column">{attempts.length > 1 && <label>查看评测记录<select value={attempt?.id || ''} onChange={e => setAttempt(attempts.find(item => item.id === e.target.value) || null)}>{attempts.map(item => <option key={item.id} value={item.id}>{item.id.slice(-8)}</option>)}</select></label>}{attempt ? <RunResult key={attempt.id} initial={attempt} onChanged={() => { setVersion(value => value + 1); onUpdated(); }} onExport={onExport} /> : <Empty title="评测尚未开始">检查并开始后，将保存逐条实际输出、判定与来源记录。</Empty>}{record?.report_error && <ErrorNotice message={record.report_error.message} />}{record?.report && <><EvaluationResult report={record.report} />{capabilityMode && record.reviews ? <CapabilityReviews key={record.id} attemptId={record.id} report={record.report} reviews={record.reviews} onSaved={reviews => setRecord(old => old?.id === record.id ? { ...old, reviews } : old)} /> : <Button primary busy={busy} disabled={!targetId || alreadyRegistered || record.state !== 'succeeded' || !record.report.eligible || !record.report.prospective_plan_bound} onClick={register}>{alreadyRegistered ? '已登记通过评测的候选' : '登记通过评测的候选'}</Button>}</>}</div></div></>;
}
