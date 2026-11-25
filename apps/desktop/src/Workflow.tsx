import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ChevronRight, Play, RefreshCw } from 'lucide-react';
import { api, errorMessage } from './api';
import type { Attempt, Draft, Model, Preflight, Runtime, Task, Work } from './types';
import { defaultMediaRuntime, selectMediaRuntime, mainMedia, MediaPreview } from './Media';
import { RunResult } from './Workbench';
import { LibraryReadContext } from './LibraryReadContext';
import { activeStates, Badge, Button, Dialog, Empty, ErrorNotice, formatDate } from './ui';

export type WorkflowStepId = 'image' | 'video' | 'audio';
const stepIds: WorkflowStepId[] = ['image', 'video', 'audio'];
const labels = { image: '商品图片', video: '商品视频', audio: '中文配音' };
function confirmedRejection(error: unknown): boolean {
  if (typeof error !== 'object' || !error || !('error' in error)) return false;
  const code = (error as { error?: { code?: unknown } }).error?.code;
  return typeof code === 'string' && !/^(CONTROL_|LOCAL_BRIDGE|INTERNAL_|NETWORK_|UNKNOWN)/.test(code);
}
type Configuration = { model_id: string; input: Draft['input']; runtime: Runtime };
type Accepted = { step_id: WorkflowStepId; step_attempt_id: string; input_revision: number; attempt_id: string; artifact_id: string; artifact_sha256: string; work_id: string; mode: string; computed: boolean };
type Step = { configuration: Configuration; input_revision: number; input_digest: string | null; task_id: string | null; step_attempt_id: string | null; accepted: Accepted | null; stale: boolean };
type StepAttempt = { id: string; mode: 'compute' | 'reused'; attempt_id: string | null; source: null | { attempt_id: string; artifact_id: string; differences: Record<string, unknown>; selected_at: string } };
export type WorkflowRun = { id: string; project_id: string; name: string; revision: number; definition_version: string; current_step: WorkflowStepId | null; status: string; steps: Record<WorkflowStepId, Step>; step_attempts?: StepAttempt[]; history: { action: string; created_at: string; step_id?: WorkflowStepId; [key: string]: unknown }[]; result_id: string | null; created_at?: string };

function WorkflowInputSummary({ kind, input, current = false }: { kind: WorkflowStepId; input?: Draft['input']; current?: boolean }) {
  return kind === 'video' ? <><p className="muted">{current ? '使用本轮已接受的商品图片。' : '此视频使用原运行固定保存的图片版本。'}选择复用会直接保留旧视频，不按本轮输入重新生成。</p>{input?.prompt && <p className="workflow-input-text">{input.prompt}</p>}</> : <><p className="workflow-input-text">{input?.prompt || '未记录文字内容'}</p>{input?.negative_prompt && <small>不希望出现：{input.negative_prompt}</small>}</>;
}

function ConfigurationFields({ kind, value, models, onChange }: { kind: WorkflowStepId; value: Configuration; models: Model[]; onChange: (value: Configuration) => void }) {
  const windows = Boolean(window.ailabHF);
  const candidates = models.filter(model => model.modality === kind && model.status !== 'experimental' &&
    (!windows || (model.execution_available !== false && model.workflow_eligible !== false &&
      (kind !== 'video' || ['animatediff-sd15', 'h3-video'].includes(model.pipeline || '')))));
  const pipeline = candidates.find(model => model.id === value.model_id)?.pipeline;
  const changeModel = (modelId: string) => {
    const next = candidates.find(model => model.id === modelId)?.pipeline;
    const draft: Draft = { ...value, kind, operation: 'generate', dataset_id: null };
    onChange({ ...value, model_id: modelId, runtime: selectMediaRuntime(draft, next, pipeline) });
  };
  return <div className="form-stack"><label>{labels[kind]}模型<select aria-label={labels[kind] + '模型'} required value={value.model_id} onChange={e => changeModel(e.target.value)}><option value="">请选择已导入模型</option>{candidates.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
    {(kind !== 'video' || windows) && <label>{kind === 'image' ? '画面描述' : kind === 'audio' ? '配音文案' : '视频描述'}<textarea required={kind !== 'video' || pipeline === 'h3-video'} rows={kind === 'image' ? 4 : 3} maxLength={kind === 'audio' ? 120 : 2000} placeholder={kind === 'video' ? '例如：镜头缓慢推近，商品顺时针转动。' : undefined} value={value.input.prompt || ''} onChange={e => onChange({ ...value, input: { ...value.input, prompt: e.target.value } })} /></label>}
    {kind === 'image' && <label>不希望出现的内容<textarea rows={2} maxLength={2000} value={value.input.negative_prompt || ''} onChange={e => onChange({ ...value, input: { ...value.input, negative_prompt: e.target.value } })} /></label>}
    <div className="two-fields"><label>{labels[kind]}随机种子<input type="number" min={0} max={4294967295} value={value.runtime.seed} onChange={e => onChange({ ...value, runtime: { ...value.runtime, seed: Number(e.target.value) } })} /></label>{kind === 'audio' && <label>配音语速<input type="number" min={0.5} max={2} step={0.1} value={value.runtime.speed} onChange={e => onChange({ ...value, runtime: { ...value.runtime, speed: Number(e.target.value) } })} /></label>}</div>
    <small className="muted">{windows ? (kind === 'video' ? '接受的商品图片将作为首帧，可填写动作和镜头变化。' : kind === 'audio' ? '用所选语音模型朗读配音文案。' : '用所选图片模型生成商品图。') : kind === 'image' ? 'Tiny-SD · 本机 Apple GPU · 512×512 · 20 步 · 引导强度 7.5' : kind === 'video' ? 'SVD · 使用本轮接受的图片 · 本机 Apple GPU · 14 帧 / 7 FPS · 约两秒，可能只有轻微运动' : 'Kokoro · 小北中文音色 · 本机 CPU · 24 kHz WAV；中文文案由你填写，不会分析视频或自动混音'}</small></div>;
}

export function WorkflowStartDialog({ projectId, models, onClose, onCreated }: { projectId: string; models: Model[]; onClose: () => void; onCreated: (run: WorkflowRun) => void }) {
  const [name, setName] = useState('商品内容创作');
  const [steps, setSteps] = useState<Record<WorkflowStepId, Configuration>>(() => Object.fromEntries(stepIds.map(kind => [kind, { model_id: '', input: kind === 'video' && !window.ailabHF ? {} : kind === 'image' ? { prompt: '', negative_prompt: '' } : { prompt: '' }, runtime: { ...defaultMediaRuntime(kind, false), ...(window.ailabHF ? {engine: 'ailab-gguf', device_id: 'cpu'} : {}) } }])) as Record<WorkflowStepId, Configuration>);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const pending = useRef<{ payload: unknown; key: string } | null>(null);
  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    pending.current ||= { key: crypto.randomUUID(), payload: { project_id: projectId, name, definition_version: 'product-story-v1', steps } };
    try { onCreated(await api<WorkflowRun>('POST', '/workflow-runs', pending.current.payload, pending.current.key)); }
    catch (e) { if (confirmedRejection(e)) pending.current = null; setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  return <Dialog title="新建商品内容工作流" onClose={onClose} preventClose={busy || Boolean(pending.current)} wide><form className="form-stack" onSubmit={create}><p className="muted">选择三个模型，为各步骤填写描述或文案。每一步完成后先查看结果，再明确带入下一步；创建时不会执行模型。</p><fieldset className="task-fields" disabled={busy || Boolean(pending.current)}><label>工作流名称<input required maxLength={120} value={name} onChange={e => setName(e.target.value)} /></label>{stepIds.map(kind => <section key={kind} className="workflow-setup-step"><h3>{labels[kind]}</h3><ConfigurationFields kind={kind} value={steps[kind]} models={models} onChange={value => setSteps(previous => ({ ...previous, [kind]: value }))} /></section>)}</fieldset><ErrorNotice message={error} /><Button type="submit" primary busy={busy}>{busy ? '正在创建工作流…' : pending.current ? '重试创建并读取原工作流' : '创建工作流草稿'}</Button></form></Dialog>;
}

type Command = { path: string; method: string; body: unknown; key: string; action: 'revise' | 'reuse' | 'advance' | 'save' | 'submit' };
export function WorkflowRunView({ runId, models, works, onBack, onUpdated, registerLeave, onExport }: { runId: string; models: Model[]; works: Work[]; onBack: () => void; onUpdated: () => void; registerLeave: (handler: (() => Promise<boolean>) | null) => void; onExport: (work: Work) => void }) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [selectedStep, setSelectedStep] = useState<WorkflowStepId | null>(null);
  const [task, setTask] = useState<Task | null>(null); const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [configuration, setConfiguration] = useState<Configuration | null>(null);
  const [editing, setEditing] = useState(false); const [reuse, setReuse] = useState(false); const [reuseWork, setReuseWork] = useState('');
  const [reuseSource, setReuseSource] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const [blockingId, setBlockingId] = useState<string | null>(null); const [blockingAttempt, setBlockingAttempt] = useState<Attempt | null>(null);
  const errorTarget = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (error) { errorTarget.current?.focus(); errorTarget.current?.scrollIntoView?.({ block: 'nearest' }); } }, [error]);
  const pending = useRef<Command | null>(null); const mounted = useRef(true); const requestVersion = useRef(0);
  const [refresh, setRefresh] = useState(0);
  const reload = useCallback(() => { if (!pending.current) setRefresh(value => value + 1); onUpdated(); }, [onUpdated]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; requestVersion.current += 1; }; }, []);
  useEffect(() => {
    registerLeave(async () => { if (busy || editing || pending.current) { setError('请先完成当前操作，或取消未保存的输入修改。'); return false; } return true; });
    return () => registerLeave(null);
  }, [busy, editing]);
  useEffect(() => {
    const version = ++requestVersion.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const live = () => mounted.current && version === requestVersion.current;
    function retry() { if (live()) timer = setTimeout(load, 600); }
    setLoading(true); setTask(null); setAttempt(null); setPreflight(null);
    async function load() {
      const isCurrent = captureLibraryRead();
      if (!live()) return;
      if (!isCurrent()) { retry(); return; }
      try {
        const current = await api<WorkflowRun>('GET', `/workflow-runs/${runId}`);
        if (!live()) return;
        if (!isCurrent()) { retry(); return; }
        const kind = selectedStep || current.current_step || 'audio';
        const step = current.steps[kind];
        const record = current.step_attempts?.find(item => item.id === step.step_attempt_id);
        const sourceId = record?.mode === 'reused' ? record.source?.attempt_id : record?.attempt_id;
        const [sourceTask, sourceAttempt] = await Promise.all([step.task_id ? api<Task>('GET', `/tasks/${step.task_id}`) : null, sourceId ? api<Attempt>('GET', `/attempts/${sourceId}`) : null]);
        if (!live()) return;
        if (!isCurrent()) { retry(); return; }
        setRun(current); setTask(sourceTask); setAttempt(sourceAttempt); setLoading(false);
      } catch (e) {
        if (!live()) return;
        if (!isCurrent()) { retry(); return; }
        setError(errorMessage(e)); setLoading(false);
      }
    }
    void load(); return () => { if (timer) clearTimeout(timer); };
  }, [runId, selectedStep, refresh, captureLibraryRead]);
  const kind = selectedStep || run?.current_step || 'audio';
  const step = run?.steps[kind];
  const record = run?.step_attempts?.find(item => item.id === step?.step_attempt_id);
  const active = attempt ? activeStates.has(attempt.state) || Boolean(attempt.recovery_required) : false;
  const artifact = mainMedia(attempt?.artifacts);
  const current = run?.current_step === kind && !step?.stale && !step?.accepted;
  const chosenWork = works.find(item => item.id === reuseWork);
  useEffect(() => {
    let live = true; setReuseSource(null);
    if (reuse && chosenWork) void api<Attempt>('GET', `/attempts/${chosenWork.attempt_id}`).then(source => { if (live) setReuseSource(source); }).catch(e => { if (live) setError(errorMessage(e)); });
    return () => { live = false; };
  }, [reuse, chosenWork?.attempt_id]);
  async function execute(command: Command) {
    pending.current = command; setBusy(true); setError(''); setBlockingId(null); requestVersion.current += 1;
    try {
      const response = await api<WorkflowRun | Attempt | { workflow_run: WorkflowRun }>(command.method, command.path, command.body, command.key);
      if (!mounted.current) return;
      pending.current = null; setPreflight(null); setEditing(false); setReuse(false);
      if (command.action === 'submit') { setAttempt(response as Attempt); }
      else {
        const updated = 'workflow_run' in response ? response.workflow_run : response as WorkflowRun;
        // 新版本或步骤先撤下旧任务与结果，避免刷新回执到达前混用两个版本。
        setRun(updated); setTask(null); setAttempt(null); setLoading(true);
        if (command.action === 'advance') setSelectedStep(updated.current_step || kind);
      }
      setRefresh(value => value + 1); onUpdated();
    } catch (e) {
      if (!mounted.current) return;
      if (confirmedRejection(e)) pending.current = null;
      if (typeof e === 'object' && e && 'error' in e) { const id = (e as { error?: { details?: { attempt_id?: unknown } } }).error?.details?.attempt_id; if (typeof id === 'string') setBlockingId(id); }
      setError(errorMessage(e));
    } finally { if (mounted.current) setBusy(false); }
  }
  function mutate(action: Command['action'], path: string, body: unknown, method = 'POST') { void execute({ action, path, body, method, key: crypto.randomUUID() }); }
  async function check() {
    if (!task || busy || pending.current) return;
    setBusy(true); setError('');
    try { const checked = await api<Preflight>('POST', `/tasks/${task.id}/preflight`, { draft_revision: task.draft_revision }); if (mounted.current) setPreflight(checked); }
    catch (e) { if (mounted.current) setError(errorMessage(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  if (!run) return <><ErrorNotice message={error} /><Empty title={loading ? '正在读取本轮工作流' : '工作流未读取'} action={<Button onClick={reload}>重新读取</Button>} /></>;
  const locked = busy || loading || Boolean(pending.current);
  return <>
    <div className="breadcrumb"><button disabled={locked || editing} onClick={onBack}><ArrowLeft size={15} />工作台</button><ChevronRight size={14} /><span>商品内容工作流</span></div>
    <div className="page-heading"><div><h1>{run.name}</h1><p>先查看本步结果，再带入下一步。图片、视频、配音分别保存。</p></div><Button disabled={locked || editing} onClick={reload}><RefreshCw size={15} />刷新状态</Button></div>
    <nav className="workflow-progress" aria-label="工作流步骤">{stepIds.map((name, index) => <button key={name} disabled={locked || editing || !run.steps[name].input_revision} aria-current={kind === name ? 'step' : undefined} onClick={() => { setSelectedStep(name); setEditing(false); setReuse(false); setError(''); }}><b>{index + 1}</b><span>{labels[name]}<small>{run.steps[name].stale ? '上游已修改 · 结果过期' : run.steps[name].accepted ? run.steps[name].accepted!.computed ? '已接受本轮结果' : '已接受明确复用的结果' : !run.steps[name].input_revision ? '等待上一步' : '待完成'}</small></span></button>)}</nav>
    <div ref={errorTarget} tabIndex={-1}><ErrorNotice message={error} /></div>{blockingId && <Button disabled={locked} onClick={async () => { setBusy(true); try { const result = await api<Attempt>('GET', `/attempts/${blockingId}`); if (mounted.current) setBlockingAttempt(result); } catch (e) { if (mounted.current) setError(errorMessage(e)); } finally { if (mounted.current) setBusy(false); } }}>查看占用任务</Button>}{pending.current && !busy && <div className="review-box"><p>上次操作的响应未确认。重试会读取同一条命令的结果。</p><Button primary onClick={() => void execute(pending.current!)}>重试上次操作</Button></div>}
    {blockingAttempt && <Dialog title="占用任务状态" wide onClose={() => setBlockingAttempt(null)}><p className="muted">{blockingAttempt.project_id === run.project_id ? '该运行属于当前项目。' : '该运行属于另一个项目。'}可等待完成，或在确认后停止。工作流会留在原步骤，请解除占用后重新带入。</p><RunResult key={blockingAttempt.id} initial={blockingAttempt} onChanged={onUpdated} /></Dialog>}
    {run.status === 'saved' && <div className="review-box"><strong>本轮三项作品已保存</strong><p>可在“作品与素材”分别查看和导出。视频与配音尚未合成为一个文件，质量仍需检查。</p></div>}
    {loading ? <Empty title="正在读取当前步骤与原结果" /> : step && <div className="workbench-layout"><section className="composer" aria-label="工作流输入"><div className="section-title"><h2>{labels[kind]}</h2><Badge>输入第 {step.input_revision} 版</Badge></div>
      {step.stale && <p className="warning">此结果已因上游修改而过期。请先完成上游，再回到本步重新计算。</p>}
      {editing && configuration ? <><fieldset className="task-fields" disabled={locked}><ConfigurationFields kind={kind} value={configuration} models={models} onChange={setConfiguration} /></fieldset><p className="warning">保存会创建新输入版本并重做本步；后续旧结果将标为过期，原输入和产物保留。</p><div className="dialog-footer"><Button disabled={locked} onClick={() => { setEditing(false); setConfiguration(null); }}>取消修改</Button><Button primary disabled={locked || !configuration.model_id || (kind !== 'video' && !configuration.input.prompt?.trim())} onClick={() => mutate('revise', `/workflow-runs/${run.id}/steps/${kind}/input`, { expected_revision: run.revision, configuration }, 'PATCH')}>保存新版本并重做</Button></div></> : <>
        <dl className="facts"><div><dt>模型</dt><dd>{models.find(item => item.id === step.configuration.model_id)?.name || step.configuration.model_id}</dd></div><div><dt>执行位置</dt><dd>{window.ailabHF ? '本机 Windows' : kind === 'audio' ? '本机 CPU' : '本机 Apple GPU'}</dd></div></dl>
        {kind === 'video' ? <><p className="muted">使用本轮接受的商品图片作为首帧。</p>{window.ailabHF && <><h4>视频描述</h4><p className="workflow-input-text">{step.configuration.input.prompt || '未填写'}</p></>}</> : <><h4>{kind === 'audio' ? '你的中文配音文案' : '画面描述'}</h4><p className="workflow-input-text">{step.configuration.input.prompt || '尚未填写，请修改输入'}</p>{kind === 'image' && step.configuration.input.negative_prompt && <small>不希望出现：{step.configuration.input.negative_prompt}</small>}</>}
        {kind === 'audio' && <p className="muted">视频作为来源关联保存；此处只朗读你的文案，不会分析视频或自动混音。</p>}
        <div className="dialog-footer"><Button disabled={locked || active || step.stale} onClick={() => { setConfiguration(structuredClone(step.configuration)); setEditing(true); setReuse(false); setPreflight(null); }}>修改输入 / 重做本步</Button>{current && <Button disabled={locked || active} onClick={() => { setReuse(value => !value); setReuseWork(''); setPreflight(null); }}>明确复用旧作品</Button>}</div>
        {reuse && current && <div className="review-box"><label>选择同项目旧作品<select value={reuseWork} disabled={locked} onChange={e => setReuseWork(e.target.value)}><option value="">请选择，不会自动带入</option>{works.filter(item => item.kind === kind && item.artifact_id).map(item => <option key={item.id} value={item.id}>{item.name || item.id} · {formatDate(item.created_at)}</option>)}</select></label>{chosenWork?.artifact_id && <><MediaPreview key={chosenWork.artifact_id} artifact={{ id: chosenWork.artifact_id, media_type: chosenWork.media_type }} name="所选旧作品" /><p className="warning">此结果来自旧运行。本轮不会重新计算；旧输入、原配方、与当前输入的差异会保留，接受后才带入下一步。</p>{reuseSource ? <div className="workflow-reuse-diff"><h4>复用前核对输入</h4><dl className="facts"><div><dt>旧结果模型</dt><dd>{models.find(item => item.id === reuseSource.snapshot?.model_id)?.name || String(reuseSource.snapshot?.model_id || '未记录')}</dd></div><div><dt>当前模型</dt><dd>{models.find(item => item.id === step.configuration.model_id)?.name || step.configuration.model_id}</dd></div></dl><section aria-label="原输入与当前输入"><h4>原结果输入</h4><WorkflowInputSummary kind={kind} input={reuseSource.snapshot?.input as Draft['input']} /><h4>本轮输入</h4><WorkflowInputSummary kind={kind} input={task?.draft.input || step.configuration.input} current /><details><summary>查看输入版本记录</summary><pre>{JSON.stringify({ 原输入: reuseSource.snapshot?.input, 本轮输入: task?.draft.input || step.configuration.input }, null, 2)}</pre></details></section><details><summary>原参数与当前参数</summary><pre>{JSON.stringify({ 原参数: reuseSource.snapshot?.runtime, 当前参数: step.configuration.runtime }, null, 2)}</pre></details></div> : <p className="muted">正在读取旧结果的原输入与配方…</p>}<Button disabled={locked || !reuseSource || reuseSource.id !== chosenWork.attempt_id} onClick={() => mutate('reuse', `/workflow-runs/${run.id}/reuse-output`, { expected_revision: run.revision, step_id: kind, input_revision: step.input_revision, source_attempt_id: chosenWork.attempt_id, artifact_id: chosenWork.artifact_id })}>确认使用这个旧结果</Button></>}</div>}
        {record?.mode === 'reused' && <div className="review-box"><strong>已明确复用旧结果 · 本步未重新计算</strong><details><summary>查看原输入与当前输入的差异</summary><pre>{JSON.stringify(record.source?.differences || {}, null, 2)}</pre></details></div>}
        {preflight && <div className="preflight" aria-label="工作流运行前检查"><strong>{preflight.can_submit ? '检查通过，可以运行' : '请先完成以下准备'}</strong>{preflight.blocking.map((item, i) => <p className="error" key={i}>{item.message}</p>)}{preflight.warnings.map((item, i) => <p className="warning" key={i}>{item.message}</p>)}<details><summary>查看本次实际配置</summary><pre>{JSON.stringify(preflight.effective_config, null, 2)}</pre></details></div>}
        {current && task && !record?.attempt_id && record?.mode !== 'reused' && !reuse && (preflight?.can_submit ? <Button primary className="full" disabled={locked} onClick={() => mutate('submit', `/tasks/${task.id}/attempts`, { expected_revision: task.draft_revision, preflight_id: preflight.preflight_id })}><Play size={15} />开始本步运行</Button> : <Button primary className="full" disabled={locked} onClick={check}>检查本步配置</Button>)}
        {current && artifact?.id && !active && <Button primary className="full" disabled={locked} onClick={() => mutate('advance', `/workflow-runs/${run.id}/advance`, { expected_revision: run.revision, step_attempt_id: step.step_attempt_id, input_revision: step.input_revision, artifact_ids: [artifact.id] })}>{kind === 'image' ? '接受图片并带入视频' : kind === 'video' ? '接受视频并进入配音' : '接受本次配音'}</Button>}
      </>}
      <details className="run-details"><summary>本步固定配方</summary><pre>{JSON.stringify(step.configuration, null, 2)}</pre></details>
    </section><div className="result-column">{attempt ? <RunResult key={attempt.id} initial={attempt} onChanged={() => { if (activeStates.has(attempt.state)) reload(); else onUpdated(); }} /> : <Empty title={step.stale ? '此步骤等待上游新结果' : '本轮尚无结果'}>本轮不会自动取用历史产物。检查后开始计算，或明确选择要复用的旧作品。</Empty>}</div></div>}
    {run.status === 'ready_to_save' && <section className="review-box"><strong>三步结果已接受</strong><p>保存后可从作品与素材找到本轮图片、视频和配音。三个文件分别保留。</p><Button primary disabled={locked || editing} onClick={() => mutate('save', `/workflow-runs/${run.id}/save`, { expected_revision: run.revision })}>保存本轮三项作品</Button></section>}
    {(run.status === 'saved' || run.status === 'ready_to_save') && <div className="workflow-outputs">{stepIds.map(name => { const accepted = run.steps[name].accepted; const work = works.find(item => item.id === accepted?.work_id); return accepted && <article className="resource-card" key={name}><h3>{labels[name]}</h3><Badge>{accepted.computed ? '本轮实际计算' : '明确复用旧结果'}</Badge><MediaPreview artifact={{ id: accepted.artifact_id, media_type: name === 'image' ? 'image/png' : name === 'video' ? 'video/mp4' : 'audio/wav' }} name={`本轮${labels[name]}`} downloadName={window.ailabHF ? run.name + (name === 'image' ? '.png' : name === 'video' ? '.mp4' : '.wav') : undefined} />{!window.ailabHF && work && <Button onClick={() => onExport(work)}>导出{labels[name]}</Button>}</article>; })}</div>}
    <details className="run-details"><summary>本轮来源与操作记录</summary><p>工作流编号：{run.id} · 当前版本 {run.revision}</p><ol className="event-list">{run.history.map((item, index) => <li key={index}><span>{formatDate(item.created_at)}</span><span>{item.step_id ? labels[item.step_id] : '本轮'} · {({ input_created: '保存输入版本', submitted: '明确提交计算', accepted: '接受结果', invalidated: '标为过期', reused: '明确复用旧结果', saved: '保存本轮作品' } as Record<string, string>)[item.action] || item.action}</span></li>)}</ol><pre>{JSON.stringify(run.step_attempts, null, 2)}</pre></details>
  </>;
}
