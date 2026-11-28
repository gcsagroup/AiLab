import { TrialTextOutput, outputPreviewLimit } from './TrialTextOutput';
import { InferencePerformance } from './InferencePerformance';
import { useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, Check, ChevronRight, FileCheck2, Play, Save, Square, Settings2, Clock3 } from 'lucide-react';
import { api, collection, mergeRecords, errorMessage, type ImportKind } from './api';
import { LibraryReadContext } from './LibraryReadContext';
import { defaultMediaRuntime, mainMedia, MediaFields, MediaPreview } from './Media';
import { Checkpoints } from './Checkpoints';
import { AIAssistance } from './AIAssistance';
import { libraryModelKind, preferredTextGpu } from './types';
import { WindowsAIAssistance } from './WindowsAIAssistance';
import { DatasetMarket } from './DatasetMarket';
import DatasetSplitDialog, { DatasetSplitBinding } from './DatasetSplitDialog';
import { CpuThreadsField } from './CpuThreadsField';
import { RuntimePresets } from './RuntimePresets';
import { GenerationFields, GenerationNumericFields, generationNumericErrors } from './GenerationFields';
import { TrainingFields, trainingParameterErrors, useTrainingContract } from './TrainingFields';
import type { EvaluationPlan } from './Evaluation';
import type { ExportObject } from './ExportDialog';
import { ExecutionLocation, UploadSummary } from './ExecutionLocation';
import { useWorkRecipeContext, WorkRecipeContext } from './WorkRecipeContext';
import { TaskRuntimeNotice, taskLibraries, type TaskRuntime } from './WindowsTaskRuntime';
import type { Adapter, Attempt, CheckReport, Dataset, Device, Draft, Kind, Material, Model, Preflight, RunEvent, Runtime, Task } from './types';
import { activeStates, Badge, Button, Dialog, Empty, ErrorNotice, readableSize, stateNames } from './ui';

export const kindLabels: Record<string, string> = { text: '模型', image: '图片', video: '视频', audio: '音频', export: '文件' };
const phaseNames: Record<string, string> = { loading: '加载模型', generating: '生成文本', tokenizing: '检查分词', training: '训练模型', quantizing: '量化模型', evaluating: '独立评测', preparing: '准备输入', saving: '保存产物', uploading: '上传输入' };
export const defaultRuntime = { engine: 'mlx', device_id: 'apple-gpu', max_tokens: 128, temperature: 0, top_p: 1, seed: 0 };
export const defaultTrainingRuntime: Runtime = { engine: 'mlx', device_id: 'apple-gpu', seed: 0, training_type: 'sft', update_method: 'lora', recipe_id: 'qwen25-assistant-only-v1', steps: 4, learning_rate: 0.0001, max_seq_length: 512, lora_rank: 4, lora_alpha: 8, num_layers: 2, batch_size: 1, gradient_accumulation: 1, optimizer: 'adamw', weight_decay: 0, lora_dropout: 0 };
const leaveWhileBusyMessage = '当前操作尚未完成，请稍后再离开。';
export function displayOutput(attempt: Attempt | null, events: RunEvent[]): string {
  if (attempt?.snapshot?.operation !== 'generate' || (attempt.snapshot.kind && attempt.snapshot.kind !== 'text')) return '';
  if (attempt.output_text) return attempt.output_text;
  return events.filter(event => event.type === 'token').map(event => event.payload.text || '').join('');
}

function DataCheck({ report }: { report?: CheckReport }) {
  if (report?.input_samples === undefined) return null;
  const reasons: Record<string, string> = { SEQUENCE_TOO_LONG: '超过最大序列长度', EMPTY_CONTENT: '消息或回答为空', NO_SUPERVISION: '没有有效监督 token', INVALID_ROLES: '对话角色顺序不完整' };
  return <section className="data-check" aria-label="训练数据检查"><strong>本次训练数据</strong><dl className="facts"><div><dt>输入样本</dt><dd>{report.input_samples} 条</dd></div><div><dt>可训练样本</dt><dd>{report.accepted_samples} 条</dd></div><div><dt>已排除样本</dt><dd>{report.excluded_samples} 条</dd></div><div><dt>监督 token</dt><dd>{report.supervised_tokens}</dd></div></dl>{Object.entries(report.exclusion_counts || {}).map(([code, count]) => <p className="warning" key={code}>{reasons[code] || code}：{count} 条</p>)}{Boolean(report.excluded_samples) && <details><summary>查看被排除样本</summary><pre>{JSON.stringify(report.exclusions || [], null, 2)}</pre></details>}</section>;
}

export function RunResult({ initial, onChanged, onAttemptUpdated, onExport, onRestoreTask }: { initial: Attempt; onChanged: () => void; onAttemptUpdated?: (attempt: Attempt) => void; onExport?: (object: ExportObject) => void; onRestoreTask?: (task: Task) => void }) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [attempt, setAttempt] = useState(initial);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [adapterSaved, setAdapterSaved] = useState(false);
  const [convertedSaved, setConvertedSaved] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const lifetime = useRef(0);
  const cursor = useRef(0);
  const workKey = useRef(crypto.randomUUID());
  const adapterKey = useRef(crypto.randomUUID());
  const convertedKey = useRef(crypto.randomUUID());
  const actionKeys = useRef(new Map<string, string>());
  const attemptUpdated = useRef(onAttemptUpdated);
  attemptUpdated.current = onAttemptUpdated;
  useEffect(() => {
    let live = true;
    lifetime.current += 1;
    let timer: ReturnType<typeof setTimeout>;
    setAttempt(initial); setEvents([]); setSaved(false); setError(''); setBusy(false); cursor.current = 0;
    function retry() { if (live) timer = setTimeout(poll, 600); }
    async function poll() {
      const isCurrent = captureLibraryRead();
      if (!live) return;
      if (!isCurrent()) { retry(); return; }
      try {
        const current = await api<Attempt>('GET', `/attempts/${initial.id}`);
        if (!live) return;
        if (!isCurrent()) { retry(); return; }
        const batch = await api<{ items: RunEvent[]; next_cursor?: number }>('GET', `/attempts/${initial.id}/events?after=${cursor.current}`);
        if (!live) return;
        if (!isCurrent()) { retry(); return; }
        setAttempt(current); setError(''); attemptUpdated.current?.(current);
        setEvents(old => {
          const bySequence = new Map(old.map(event => [event.sequence, event]));
          for (const event of batch.items) bySequence.set(event.sequence, event);
          const all = [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
          cursor.current = all.at(-1)?.sequence || 0;
          return all;
        });
        if (activeStates.has(current.state) || (batch.items.at(-1)?.sequence || cursor.current) < (current.last_event_sequence || 0)) timer = setTimeout(poll, 600);
        else onChanged();
      } catch (e) {
        if (live && !isCurrent()) { retry(); return; }
        if (live) { setError(errorMessage(e)); timer = setTimeout(poll, 2000); }
      }
    }
    void poll();
    return () => { live = false; lifetime.current += 1; clearTimeout(timer); };
    // 运行身份固定；页面更新不会重新提交或替换正在读取的尝试。
  }, [initial.id, captureLibraryRead]);
  // 列表摘要没有配方或产物，不能据此判定本次没有输出。
  const detailsLoaded = Boolean(attempt.snapshot);
  const active = activeStates.has(attempt.state);
  const training = attempt.snapshot?.operation === 'train';
  const evaluating = attempt.snapshot?.operation === 'evaluate';
  const transferring = attempt.snapshot?.operation === 'transfer';
  const mediaGeneration = attempt.snapshot?.operation === 'generate' && ['image', 'video', 'audio'].includes(String(attempt.snapshot.kind));
  const quantizing = attempt.snapshot?.operation === 'quantize';
  const converting = ['quantize', 'merge', 'distill', 'convert'].includes(String(attempt.snapshot?.operation));
  const metrics = events.filter(event => event.type === 'metric' && (typeof event.payload.step === 'number' || typeof event.payload.completed_steps === 'number') && typeof event.payload.loss === 'number');
  const lastMetric = metrics.at(-1)?.payload;
  const warning = [...events].reverse().find(event => event.type === 'warning' && typeof event.payload.message === 'string');
  const terminal = [...events].reverse().find(event => event.type === 'terminal' && typeof event.payload.message === 'string');
  const failureMessage = attempt.error?.message || (terminal?.payload.message as string | undefined) || (warning?.payload.message as string | undefined) || '执行未成功，完整记录已保留。';
  const remote = attempt.executor_type === 'remote' || attempt.snapshot?.executor_type === 'remote';
  const recoveryMessage = remote ? attempt.remote_submission_started === false
    ? '上传已中断，本次尚未提交计算。核实后可重新检查并开始新的传输。'
    : '远端连接或同步中断，需要核实原执行状态。核实不会重新提交计算。'
    : '本机执行状态待核实，需要确认原进程是否退出。核实不会重新执行任务。';
  const output = displayOutput(attempt, events);
  const reasoning = attempt.reasoning_text;
  const config = attempt.effective_config;
  // Earlier native trials recorded the architecture, before they recorded the template prefix.
  const prefilled = config?.reasoning_prefilled === true || (config?.type === 'config' && config.thinking !== 'disabled' &&
    (config.architecture === 'qwen35' || (config.architecture === 'qwen4exp' && output.includes('</think>'))));
  function captureAction() {
    const currentLifetime = lifetime.current; const libraryCurrent = captureLibraryRead();
    const isMounted = () => currentLifetime === lifetime.current;
    // 切库后丢弃旧动作；同库离开结果页后，成功通知仍需刷新作品或模型列表。
    return { isMounted, isLibraryCurrent: libraryCurrent, isCurrent: () => isMounted() && libraryCurrent() };
  }
  async function control(action: 'cancel' | 'force-stop' | 'reconcile' | 'collect' | 'pause' | 'resume') {
    const scope = captureAction(); if (!scope.isCurrent()) return;
    setBusy(true); setError('');
    const identity = `${action}:${attempt.state_version}:${attempt.collection_version}`;
    if (!actionKeys.current.has(identity)) actionKeys.current.set(identity, crypto.randomUUID());
    try {
      const body = action === 'collect' ? { expected_collection_version: attempt.collection_version, manifest_digest: attempt.output_manifest_ref?.digest } : { expected_state_version: attempt.state_version };
      await api('POST', `/attempts/${attempt.id}/${action === 'collect' ? 'collections' : action}`, body, actionKeys.current.get(identity));
      if (!scope.isCurrent()) { if (scope.isLibraryCurrent()) onChanged(); return; }
      const current = await api<Attempt>('GET', `/attempts/${attempt.id}`);
      if (!scope.isCurrent()) { if (scope.isLibraryCurrent()) onChanged(); return; }
      setAttempt(current); attemptUpdated.current?.(current); setConfirmStop(false); onChanged();
    }
    catch (e) { if (scope.isCurrent()) setError(errorMessage(e)); }
    finally { if (scope.isMounted()) setBusy(false); }
  }
  const textArtifact = attempt.snapshot?.operation === 'generate' ? attempt.artifacts?.find(item => item.media_type === 'text/plain' && item.name === 'result.txt') : undefined;
  const mediaArtifact = attempt.snapshot?.operation === 'generate' ? mainMedia(attempt.artifacts) : undefined;
  const workArtifact = mediaArtifact || textArtifact;
  const workSaved = saved || Boolean(workArtifact?.id && attempt.saved_work_artifact_ids?.includes(workArtifact.id));
  async function saveWork() {
    const scope = captureAction(); if (!scope.isCurrent()) return;
    setBusy(true); setError('');
    try { await api('POST', '/works', { attempt_id: attempt.id, artifact_id: workArtifact?.id }, workKey.current); if (!scope.isLibraryCurrent()) return; if (scope.isMounted()) setSaved(true); onChanged(); }
    catch (e) { if (scope.isCurrent()) setError(errorMessage(e)); }
    finally { if (scope.isMounted()) setBusy(false); }
  }
  async function saveAdapter() {
    const scope = captureAction(); if (!scope.isCurrent()) return;
    setBusy(true); setError('');
    try { await api<Adapter>('POST', `/attempts/${attempt.id}/adapters`, {}, adapterKey.current); if (!scope.isLibraryCurrent()) return; if (scope.isMounted()) setAdapterSaved(true); onChanged(); }
    catch (e) { if (scope.isCurrent()) setError(errorMessage(e)); }
    finally { if (scope.isMounted()) setBusy(false); }
  }
  async function saveConverted() {
    const scope = captureAction(); if (!scope.isCurrent()) return;
    setBusy(true); setError('');
    try { await api('POST', `/attempts/${attempt.id}/converted-models`, {}, convertedKey.current); if (!scope.isLibraryCurrent()) return; if (scope.isMounted()) setConvertedSaved(true); onChanged(); }
    catch (e) { if (scope.isCurrent()) setError(errorMessage(e)); } finally { if (scope.isMounted()) setBusy(false); }
  }
  return <section className={`result-card${evaluating ? ' evaluation-run' : ''}`} aria-label="运行结果">
    <div className="result-header"><h3>{!detailsLoaded ? '运行记录' : transferring ? '文件传输记录' : training ? '训练记录与产物' : evaluating ? '评测执行记录' : converting ? quantizing ? '量化记录与产物' : '模型实验记录与产物' : '运行结果'}</h3><Badge tone={attempt.state === 'succeeded' ? 'good' : attempt.state === 'failed' ? 'danger' : ''}>{attempt.recovery_required ? '停止状态待核实' : stateNames[attempt.state] || attempt.state}</Badge></div>
    <InferencePerformance attempt={attempt} engineMetric={events.filter(event => event.type === 'metric').at(-1)?.payload} />
    {lastMetric && <section className="training-metrics" aria-label="训练指标"><dl className="facts"><div><dt>训练步数</dt><dd>{String(lastMetric.step ?? lastMetric.completed_steps)} / {String(lastMetric.total_steps)}</dd></div><div><dt>当前损失</dt><dd>{typeof lastMetric.loss === 'number' ? lastMetric.loss.toFixed(5) : '待上报'}</dd></div></dl><p className="muted">损失仅反映本次训练过程，候选质量需要独立评测。</p></section>}
    {!detailsLoaded ? <Empty title={error ? '运行记录暂时无法读取' : '正在读取运行记录'}>读取完成后显示本次执行的产物与详情，原运行记录保留。</Empty> : transferring ? <Empty title={attempt.recovery_required ? '传输状态待核实' : active ? '正在验证文件传输' : attempt.state === 'succeeded' ? '文件传输验证完成' : attempt.state === 'cancelled' ? '文件传输已停止' : '文件传输未完成'}>{attempt.state === 'failed' ? failureMessage : '本次仅处理已选文件，原始文件与传输记录保留。'}</Empty> : mediaArtifact ? <MediaPreview key={mediaArtifact.id} artifact={mediaArtifact} autoLoad name="本次生成结果" /> : output || reasoning ? <TrialTextOutput key={attempt.id} text={output} reasoning={reasoning} prefilled={prefilled} active={active} /> : training && attempt.state === 'succeeded' ? <Empty title="训练产物已保存">已生成独立 LoRA 适配器，可以保存到模型库进行试用和评测。原始基座文件保留。</Empty> : converting && attempt.state === 'succeeded' ? <Empty title={quantizing ? '量化产物已保存' : '独立模型产物已保存'}>独立模型文件已生成。保存到模型库后可用对应引擎试用，质量尚未通过验收。</Empty> : evaluating && attempt.state === 'succeeded' ? <Empty title="评测执行完成">实际输出与判定已记录，质量结论请查看下方评测报告。</Empty> : <Empty title={attempt.recovery_required ? '原执行状态待核实' : active ? attempt.state === 'paused' ? '训练已暂停' : attempt.state === 'resuming' ? '正在恢复训练状态' : training ? '正在训练模型' : '模型正在处理本次任务' : attempt.state === 'cancelled' ? '本次执行已停止' : mediaGeneration ? '本次没有可显示的媒体结果' : '本次没有文本输出'}>{active ? '记录将随运行持续更新，离开此页不会重复提交任务。' : attempt.state === 'failed' ? failureMessage : '原任务、输入与运行记录已保留。'}</Empty>}
    {converting && typeof attempt.effective_config?.source_weight_bytes === 'number' && typeof attempt.effective_config?.output_weight_bytes === 'number' && <section className="training-metrics"><dl className="facts"><div><dt>原权重体积</dt><dd>{readableSize(attempt.effective_config.source_weight_bytes)}</dd></div><div><dt>{quantizing ? '量化权重体积' : '新权重体积'}</dt><dd>{readableSize(attempt.effective_config.output_weight_bytes)}</dd></div></dl><p className="muted">体积来自实际文件，不代表速度提高或质量通过。</p></section>}
    {(attempt.output_text_truncated || output.length >= outputPreviewLimit) && <p className="muted">正文较长，此处仅展示部分内容，完整文本可保存为作品并导出。</p>}
    {attempt.state === 'failed' && (output || reasoning) && <ErrorNotice message={failureMessage} />}
    <ErrorNotice message={error} />
    {attempt.connection_state === 'disconnected' && <p className="warning">连接已中断，当前显示最后取得的运行状态。重连核实不会再次提交执行。</p>}{attempt.stop_status === 'unknown' && <p className="warning">停止结果尚未确认，不能据此认为任务已经停止或资源已经释放。</p>}
    {!active && attempt.state !== 'succeeded' && attempt.compute_outcome === 'succeeded' && attempt.collection_state === 'succeeded' && <p className="muted recovery-notice">已有计算产物已补收完成，原中断或取消记录仍保留。</p>}{attempt.recovery_required && <p className="warning recovery-notice">{recoveryMessage}</p>}
    <div className="result-actions"><small>{attempt.state === 'paused' ? '已停在安全检查点，等待继续训练' : active && attempt.phase ? `当前阶段：${phaseNames[attempt.phase] || '处理中'}` : '运行记录自动保存在本机'}</small>{(attempt.allowed_actions || (active ? ['cancel'] : [])).map(action => action === 'cancel' ? <Button key={action} busy={busy} onClick={() => control('cancel')}><Square size={14} />停止运行</Button> : action === 'force-stop' ? <Button key={action} busy={busy} onClick={() => setConfirmStop(true)}>强制停止</Button> : action === 'reconcile' ? <Button key={action} busy={busy} onClick={() => control('reconcile')}>{(attempt.executor_type === 'remote' || attempt.snapshot?.executor_type === 'remote') ? '重连并核实原执行' : '核实原进程'}</Button> : action === 'pause' ? <Button key={action} busy={busy} onClick={() => control('pause')}>保存检查点并暂停</Button> : action === 'resume' ? <Button key={action} busy={busy} onClick={() => control('resume')}>继续训练</Button> : action === 'collect' ? <Button key={action} busy={busy} onClick={() => control('collect')}>只补收已有产物</Button> : null)}{!active && workArtifact && <Button busy={busy} disabled={workSaved} onClick={saveWork}>{workSaved ? <Check size={15} /> : <Save size={15} />}{workSaved ? '已保存作品' : '保存作品'}</Button>}</div>
    {confirmStop && <Dialog title="强制停止本次运行" onClose={() => setConfirmStop(false)}><p>正常停止尚未完成。强制停止可能丢失尚未保存的训练进度，原运行记录会保留。</p><div className="dialog-footer"><Button onClick={() => setConfirmStop(false)}>继续等待</Button><Button busy={busy} onClick={() => control('force-stop')}>确认强制停止</Button></div></Dialog>}
    {!active && Boolean(attempt.artifacts?.length) && <div className="result-actions">{attempt.artifacts?.some(item => ['adapters.safetensors', 'pytorch_lora_weights.safetensors'].includes(item.name || '')) && <Button busy={busy} disabled={adapterSaved} onClick={saveAdapter}>{adapterSaved ? '已保存实验适配器' : '保存训练适配器'}</Button>}{converting && attempt.artifacts?.some(item => item.name === 'conversion.json') && <Button busy={busy} disabled={convertedSaved} onClick={saveConverted}>{convertedSaved ? quantizing ? '已保存实验量化模型' : '已保存实验模型' : quantizing ? '保存实验量化模型' : '保存实验模型'}</Button>}{onExport && <Button onClick={() => onExport({ type: 'report', id: attempt.id, name: '本次执行报告' })}>导出执行报告</Button>}</div>}
    {training && attempt.snapshot?.kind !== 'image' && <Checkpoints attempt={attempt} onRestoreTask={onRestoreTask} />}
    {detailsLoaded && <details className="run-details"><summary>运行详情与配方</summary><dl className="facts"><div><dt>运行编号</dt><dd>{attempt.id}</dd></div><div><dt>产物文件</dt><dd>{attempt.artifacts?.length || 0}</dd></div></dl><h4>提交配方</h4><pre>{JSON.stringify(attempt.snapshot || {}, null, 2)}</pre>{attempt.effective_config && <><h4>执行器实际配置</h4><pre>{JSON.stringify(attempt.effective_config, null, 2)}</pre></>}<ol className="event-list">{events.filter(event => event.type !== 'token' && event.type !== 'reasoning').map(event => <li key={event.sequence}><span>{event.type}</span><span>{String(event.payload.message || event.payload.phase || event.payload.state || '')}</span></li>)}</ol></details>}
  </section>;
}

export default function Workbench({ task, taskRuntime, models: listedModels, datasets, devices, materials: listedMaterials = [], adapters: listedAdapters = [], evaluationPlans = [], aiPanelTarget, onCreateEvaluationPlan, onExport, onRestoreTask, onBack, registerLeave, onTaskChanged, onDraftChanged, onImport, onUpdated }: { task: Task; taskRuntime?: TaskRuntime; models: Model[]; datasets: Dataset[]; devices: Device[]; materials?: Material[]; adapters?: Adapter[]; evaluationPlans?: EvaluationPlan[]; aiPanelTarget?: HTMLElement | null; onCreateEvaluationPlan?: () => void; onRestoreTask?: (task: Task) => void; onExport?: (object: ExportObject) => void; onBack: () => void; registerLeave: (handler: (() => Promise<boolean>) | null) => void; onTaskChanged: (task: Task) => void; onDraftChanged?: (draft: Draft) => void; onImport: (kind: ImportKind) => void; onUpdated: () => void }) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [draft, setDraft] = useState<Draft>(task.draft);
  const recipeContext = useWorkRecipeContext(task, draft);
  const models = mergeRecords(listedModels, recipeContext.models);
  const AdvicePanel = window.ailabHF ? WindowsAIAssistance : AIAssistance;
  const adapters = mergeRecords(listedAdapters, recipeContext.adapters);
  const materials = mergeRecords(listedMaterials, recipeContext.materials);
  const [revision, setRevision] = useState(task.draft_revision);
  useEffect(() => { onDraftChanged?.(draft); }, [draft]);
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(task.latest_attempt || task.attempts?.[0] || null);
  const [latestAttempt, setLatestAttempt] = useState<Attempt | null>(task.latest_attempt || task.attempts?.[0] || null);
  const latestAttemptRef = useRef(latestAttempt);
  const taskHeadId = useRef(latestAttempt?.id);
  const [attempts, setAttempts] = useState<Attempt[]>(task.attempts || (task.latest_attempt ? [task.latest_attempt] : []));
  const [attemptCursor, setAttemptCursor] = useState(task.attempts_next_cursor);
  const [historyBusy, setHistoryBusy] = useState(false);
  async function loadMoreAttempts() {
    if (!attemptCursor || historyBusy) return;
    setHistoryBusy(true); setError('');
    try {
      const result = await collection<Attempt>(`/attempts?project_id=${encodeURIComponent(task.project_id)}&task_id=${encodeURIComponent(task.id)}`, attemptCursor);
      setAttempts(previous => mergeRecords(previous, result.items)); setAttemptCursor(result.next_cursor);
    } catch (e) { setError(errorMessage(e)); }
    finally { setHistoryBusy(false); }
  }
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const preflightSummary = useRef<HTMLElement>(null);
  const checkFocus = useRef<{ origin: HTMLElement; result: Preflight | null } | null>(null);
  useEffect(() => {
    // 等待期间一旦用户聚焦别处，就取消交接，避免异步回执抢走焦点。
    const moved = (event: FocusEvent) => {
      if (checkFocus.current && event.target !== checkFocus.current.origin) checkFocus.current = null;
    };
    document.addEventListener('focusin', moved);
    return () => document.removeEventListener('focusin', moved);
  }, []);
  useLayoutEffect(() => {
    if (busy) return;
    const pending = checkFocus.current; checkFocus.current = null;
    if (pending?.result && pending.result === preflight &&
      (document.activeElement === document.body || document.activeElement === pending.origin)) {
      preflightSummary.current?.focus();
    }
  }, [busy, preflight]);
  useEffect(() => {
    if (!busy) setError(current => current === leaveWhileBusyMessage ? '' : current);
  }, [busy]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const latestDraft = useRef(task.draft);
  const latestRevision = useRef(task.draft_revision);
  const editVersion = useRef(0);
  const savedVersion = useRef(0);
  const savedBaseline = useRef(0);
  const savingPromise = useRef<Promise<Task | null> | null>(null);
  const autosaveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const autosaveFailed = useRef(false);
  const savingOnly = useRef(false);
  const lifetime = useRef(0);
  useEffect(() => {
    lifetime.current += 1;
    return () => { lifetime.current += 1; clearTimeout(autosaveTimer.current); };
  }, []);
  const [marketTask, setMarketTask] = useState<Task | null>(null);
  const [splittingDataset, setSplittingDataset] = useState<Dataset | null>(null);
  const [marketNotice, setMarketNotice] = useState('');
  const composer = useRef<HTMLElement>(null);
  useEffect(() => {
    if (marketNotice && !marketTask) {
      const field = composer.current?.querySelector<HTMLSelectElement>('#training-data, #image-data');
      field?.focus({ preventScroll: true }); field?.scrollIntoView?.({ block: 'center' });
    }
  }, [marketNotice, marketTask]);
  const localChanged = useRef(false);
  const submitKey = useRef<string | null>(null);
  const currentModel = models.find(model => model.id === draft.model_id);
  const currentDataset = datasets.find(dataset => dataset.id === draft.dataset_id);
  const runningReadonly = Boolean(latestAttempt && (activeStates.has(latestAttempt.state) || latestAttempt.recovery_required));
  const editingDisabled = busy || runningReadonly;
  const showingLatest = attempt?.id === latestAttempt?.id;
  function configurationReadonly() {
    const current = latestAttemptRef.current;
    return Boolean(current && (activeStates.has(current.state) || current.recovery_required));
  }
  function rememberLatest(next: Attempt) {
    if (next.task_id !== task.id || next.project_id !== task.project_id) return;
    const previous = latestAttemptRef.current;
    if (previous?.id === next.id && next.state_version < previous.state_version) return;
    const current = previous?.id === next.id ? { ...previous, ...next } : next;
    latestAttemptRef.current = current; setLatestAttempt(current);
    setAttempts(items => [current, ...items.filter(item => item.id !== current.id)]);
    setAttempt(selected => !selected || selected.id === previous?.id ? current : selected);
  }
  function observeAttempt(current: Attempt) {
    // 查看旧历史不能解除当前执行的配置保护。
    if (current.id === latestAttemptRef.current?.id) rememberLatest(current);
  }
  useEffect(() => {
    const current = task.latest_attempt || task.attempts?.[0];
    if (task.attempts) setAttempts(previous => mergeRecords(task.attempts!, previous));
    setAttemptCursor(task.attempts_next_cursor);
    if (!current) return;
    if (taskHeadId.current !== current.id) { taskHeadId.current = current.id; rememberLatest(current); }
    else observeAttempt(current);
  }, [task.latest_attempt, task.attempts, task.attempts_next_cursor]);
  useEffect(() => {
    if (!runningReadonly) return;
    clearTimeout(autosaveTimer.current); setPreflight(null); submitKey.current = null;
    setMarketTask(null); setSplittingDataset(null);
  }, [runningReadonly]);
  function captureDraftRead() {
    const currentLifetime = lifetime.current; const libraryCurrent = captureLibraryRead();
    return () => currentLifetime === lifetime.current && libraryCurrent();
  }
  async function attachMaterial(file: File) {
    const path = window.ailabHF?.filePath?.(file);
    if (!path || configurationReadonly()) return;
    const current = captureDraftRead(), modelId = latestDraft.current.model_id;
    try {
      const plan=await api<{id:string;manifest_digest:string}>('POST','/materials/import-plans',{project_id:task.project_id,path});
      if(!current() || latestDraft.current.model_id!==modelId) return;
      const item=await api<{id:string}>('POST','/materials/imports',{plan_id:plan.id,manifest_digest:plan.manifest_digest},crypto.randomUUID());
      if(!current() || latestDraft.current.model_id!==modelId || configurationReadonly()) return;
      const live=latestDraft.current, prompt=(live.input.prompt || '').replace(/^@素材[^\r\n]*\r?\n/,'');
      change({...live,input:{...live.input,prompt:'@素材 '+item.id+'\n'+prompt}});
    } catch(e){ if(current()) setError(errorMessage(e)); }
  }
  function change(next: Draft) {
    if (configurationReadonly()) return;
    if (taskRuntime && window.ailabHF?.runtime && next.operation === 'generate' && !next.execution_target_id &&
      (next.model_id !== draft.model_id || next.runtime.device_id !== draft.runtime.device_id || draft.execution_target_id)) {
      const group = taskLibraries(next.kind, models.find(item => item.id === next.model_id)?.pipeline);
      void taskRuntime.prepare(next.runtime.device_id?.startsWith('CUDA') ? group.cuda : group.standard);
    }
    setMarketNotice(''); localChanged.current = true; latestDraft.current = next; editVersion.current += 1;
    setDraft(next); setDirty(true); setPreflight(null); submitKey.current = null;
    clearTimeout(autosaveTimer.current);
    const isCurrent = captureDraftRead(); const version = editVersion.current;
    if (!autosaveFailed.current) autosaveTimer.current = setTimeout(() => {
      if (!isCurrent()) return;
      void save(isCurrent, false, version).catch(e => { if (isCurrent()) setError(`草稿自动保存失败：${errorMessage(e)} 请点击“保存草稿”重试。`); });
    }, 500);
  }
  async function save(isCurrent = captureDraftRead(), flush = true, scheduledVersion = editVersion.current): Promise<Task> {
    if (flush) clearTimeout(autosaveTimer.current);
    const current = () => ({ ...task, draft: latestDraft.current, draft_revision: latestRevision.current });
    while (isCurrent()) {
      if (configurationReadonly()) {
        if (flush && savedVersion.current !== editVersion.current) throw new Error('当前执行尚未结束，未保存的输入已保留；请在执行结束后保存。');
        return current();
      }
      if (!flush && scheduledVersion !== editVersion.current) return current();
      // 所有入口共用在途保存；下一稿只能使用前一稿确认的版本。
      if (savingPromise.current) {
        const confirmed = await savingPromise.current;
        if (!confirmed && isCurrent()) { autosaveFailed.current = true; clearTimeout(autosaveTimer.current); throw new Error('草稿保存状态已变化，当前输入已保留；请核对已保存版本后再继续。'); }
        continue;
      }
      if (savedVersion.current === editVersion.current) return current();
      const version = editVersion.current; const baseline = savedBaseline.current;
      setSaving(true);
      const pending = api<Task>('PATCH', `/tasks/${task.id}/draft`, { draft: latestDraft.current, expected_revision: latestRevision.current }).then(saved => {
        if (!isCurrent()) return null;
        if (baseline !== savedBaseline.current) return current();
        if (!saved?.draft || saved.id !== task.id || !Number.isInteger(saved.draft_revision))
          throw new Error('保存响应缺少当前任务的草稿或版本。');
        latestRevision.current = saved.draft_revision; savedVersion.current = version; autosaveFailed.current = false; setRevision(saved.draft_revision);
        // 迟到的回执不能覆盖保存期间继续输入的内容。
        if (version === editVersion.current) {
          latestDraft.current = saved.draft; setDraft(saved.draft); setDirty(false); localChanged.current = false;
          setMarketNotice(notice => notice === '已选择训练子集，其他未保存输入保留。请保存并重新检查配置。' ? '' : notice);
        }
        onTaskChanged(saved); return saved;
      }).catch(e => {
        if (!isCurrent()) return null;
        if (baseline !== savedBaseline.current) return current();
        autosaveFailed.current = true; clearTimeout(autosaveTimer.current); throw e;
      });
      savingPromise.current = pending;
      try { await pending; }
      finally { if (savingPromise.current === pending) savingPromise.current = null; setSaving(false); }
      if (!flush) return current();
    }
    return current();
  }
  function acceptSaved(saved: Task) {
    if (configurationReadonly()) { setError('当前执行尚未结束，不能更换任务配置。'); return false; }
    if (localChanged.current || saved.draft_revision < latestRevision.current) { setError('已保存版本已更新，当前未保存的输入仍保留；请先核对差异再继续。'); return false; }
    clearTimeout(autosaveTimer.current); savedBaseline.current += 1; editVersion.current += 1; savedVersion.current = editVersion.current;
    latestDraft.current = saved.draft; latestRevision.current = saved.draft_revision; autosaveFailed.current = false;
    setDraft(saved.draft); setRevision(saved.draft_revision); setDirty(false); localChanged.current = false; setPreflight(null); submitKey.current = null;
    onTaskChanged(saved); return true;
  }
  useEffect(() => {
    registerLeave(async () => {
      if (busy && !savingOnly.current) { setError(leaveWhileBusyMessage); return false; }
      const isCurrent = captureDraftRead();
      try { await save(isCurrent); return isCurrent(); }
      catch (e) { if (isCurrent()) setError(errorMessage(e)); return false; }
    });
    return () => registerLeave(null);
  }, [draft, revision, dirty, busy, captureLibraryRead]);
  async function check(event: React.MouseEvent<HTMLButtonElement>) {
    const textTraining = task.kind === 'text' && train; const read = trainingContract;
    const libraryCurrent = captureDraftRead(); const isCurrent = () => libraryCurrent() && (!textTraining || read.isCurrent());
    if (configurationReadonly() || trainingBlocked || generationBlocked || !isCurrent()) return;
    checkFocus.current = document.activeElement === event.currentTarget ? { origin: event.currentTarget, result: null } : null;
    setBusy(true); setError('');
    try {
      const saved = await save(isCurrent);
      if (!isCurrent() || configurationReadonly()) return;
      const checked = await api<Preflight>('POST', `/tasks/${task.id}/preflight`, { draft_revision: saved.draft_revision });
      if (isCurrent() && !configurationReadonly()) {
        if (checkFocus.current) checkFocus.current.result = checked;
        setPreflight(checked);
      }
    }
    catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function submit() {
    const textTraining = task.kind === 'text' && train; const read = trainingContract;
    const libraryCurrent = captureDraftRead(); const isCurrent = () => libraryCurrent() && (!textTraining || read.isCurrent());
    if (configurationReadonly() || !preflight?.can_submit || dirty || trainingBlocked || generationBlocked || !isCurrent()) return;
    setBusy(true); setError('');
    submitKey.current ||= crypto.randomUUID();
    try {
      const result = await api<Attempt>('POST', `/tasks/${task.id}/attempts`, { preflight_id: preflight.preflight_id, expected_revision: revision }, submitKey.current);
      if (!isCurrent()) return;
      rememberLatest(result); setAttempt(result); submitKey.current = null; setPreflight(null); onUpdated();
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  async function openMarket() {
    if (configurationReadonly()) return;
    const isCurrent = captureDraftRead();
    setBusy(true); setError('');
    try { const saved = await save(isCurrent); if (isCurrent() && !configurationReadonly()) setMarketTask(saved); }
    catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function saveOnly() {
    if (configurationReadonly()) return;
    const isCurrent = captureDraftRead(); savingOnly.current = true; setBusy(true); setError('');
    try { await save(isCurrent); } catch (e) { if (isCurrent()) setError(errorMessage(e)); } finally { savingOnly.current = false; setBusy(false); }
  }
  async function back() {
    if (busy && !savingOnly.current) return; const isCurrent = captureDraftRead();
    try { await save(isCurrent); } catch (e) { if (isCurrent()) setError(errorMessage(e)); return; }
    if (isCurrent()) onBack();
  }
  const remote = Boolean(draft.execution_target_id);
  const train = draft.operation === 'train';
  const windowsTrial = Boolean(window.ailabHF) && !train;
  const draftModels = windowsTrial ? listedModels : models;
  const available = draftModels.filter(model => windowsTrial
    ? libraryModelKind(model) === task.kind && model.execution_available !== false
    : !model.modality || model.modality === task.kind);
  const runtime: Runtime = { ...(task.kind !== 'text' ? defaultMediaRuntime(task.kind, train) : train ? defaultTrainingRuntime : defaultRuntime), ...draft.runtime };
  const trainingContract = useTrainingContract({ taskId: task.id, projectId: task.project_id, targetId: draft.execution_target_id, engine: runtime.engine, deviceId: runtime.device_id, enabled: task.kind === 'text' && train });
  const [loadStatus,setLoadStatus]=useState('');
  const localText=windowsTrial && !remote && task.kind==='text' && !draft.adapter_id && !draft.checkpoint_id;
  useEffect(()=>{
    if (!localText || !draft.model_id) { setLoadStatus(''); return; }
    let live=true;
    const owner={owner:crypto.randomUUID(),project_id:task.project_id,task_id:task.id};
    const settings={device_id:runtime.device_id,context_limit:runtime.context_limit,kv_precision:runtime.kv_precision,
      cpu_threads:runtime.cpu_threads,prefill_step_size:runtime.prefill_step_size};
    setLoadStatus('正在准备运行库并加载基座模型…');
    void api<{device_id:string;device_name:string;fallback:boolean}>('POST','/models/resident',{...owner,model_id:draft.model_id,runtime:settings}).then(result=>{
      if (live) setLoadStatus(result.fallback ? '显存不足，模型已加载到内存，使用 CPU 推理。' :
        result.device_id==='cpu' ? '基座模型已加载到内存。' : '基座模型已加载到显存 · '+result.device_name);
    }).catch(e=>{if(live)setLoadStatus('基座模型加载失败：'+errorMessage(e));});
    return ()=>{live=false;void api('DELETE','/models/resident',owner).catch(()=>{});};
  },[localText,draft.model_id,task.id,task.project_id,runtime.device_id,runtime.context_limit,runtime.kv_precision,runtime.cpu_threads,runtime.prefill_step_size]);
  const generationBlocked = task.kind === 'text' && !train && Object.keys(generationNumericErrors(runtime, remote)).length > 0;
  const trainingBlocked = task.kind === 'text' && train && (!trainingContract.contract || !trainingContract.isCurrent() || Object.keys(trainingParameterErrors(trainingContract.contract, runtime)).length > 0);
  useEffect(() => {
    if (task.kind === 'text' && train && !trainingContract.contract) { setPreflight(null); submitKey.current = null; }
  }, [task.kind, train, trainingContract.contract]);
  function changeLocation(id: string | null) {
    const next = { ...runtime }; delete next.cpu_threads; delete next.kv_precision; delete next.prefill_step_size; delete next.precision;
    next.engine = id ? 'transformers' : window.ailabHF ? 'ailab-gguf' : 'mlx'; next.device_id = id ? 'cuda:0' : window.ailabHF ? 'cpu' : 'apple-gpu'; if (id) next.precision = 'bfloat16';
    change({ ...draft, execution_target_id: id, adapter_id: id ? null : draft.adapter_id, runtime: next });
    if (id && draft.adapter_id) setMarketNotice('NVIDIA 首期使用原权重，已清除本次实验适配器选择；原适配器与历史记录保留。');
  }
  function selectBase(model: string | null) {
    const gpu = localText && model && !draft.model_id && !runtime.device_selected_by_user && runtime.device_id==='cpu' ? preferredTextGpu(devices) : undefined;
    change({ ...draft, model_id: model, adapter_id: null, ...(gpu ? { runtime: { ...runtime, device_id: gpu.id } } : {}) });
  }
  const updateRuntime = (field: keyof Runtime, value: number | string) => change({ ...draft, runtime: { ...runtime, [field]: value, ...(localText && field==='device_id' ? {device_selected_by_user:true} : {}) } });
  const checkedDeviceId = typeof preflight?.effective_config?.device_id === 'string' ? preflight.effective_config.device_id : runtime.device_id;
  const checkedDeviceName = devices.find(device => device.id === checkedDeviceId)?.name || ({ cpu: '本机 CPU', 'apple-gpu': '本机 Apple GPU' } as Record<string, string>)[checkedDeviceId] || checkedDeviceId;
  return <>
    {!runningReadonly && splittingDataset && <DatasetSplitDialog key={splittingDataset.id} dataset={splittingDataset} models={models} projectId={task.project_id} initialModelId={draft.model_id} initialMaxSeqLength={runtime.max_seq_length} onClose={() => setSplittingDataset(null)} onChanged={() => onUpdated()} onUseTraining={dataset => { if (configurationReadonly()) return; change({ ...draft, dataset_id: dataset.id }); setSplittingDataset(null); setMarketNotice('已选择训练子集，其他未保存输入保留。请保存并重新检查配置。'); onUpdated(); }} onExport={onExport ? object => { setSplittingDataset(null); onExport(object); } : undefined} />}
    {!runningReadonly && marketTask && <DatasetMarket projectId={task.project_id} task={marketTask} onClose={() => setMarketTask(null)} onDatasetImported={onUpdated} onApplied={result => {
      if (!acceptSaved(result.task)) return;
      setMarketNotice('已应用所选市场数据。原检查已失效，请重新检查训练配置。'); onUpdated();
    }} />}
    {aiPanelTarget && createPortal(<AdvicePanel key={task.id} task={{ ...task, draft, draft_revision: revision }} models={models} hasUnsavedChanges={dirty} taskBusy={editingDisabled} onApplyingChange={setBusy} onTaskChanged={saved => {
      if (acceptSaved(saved)) onUpdated();
    }} />, aiPanelTarget)}
    <div className="breadcrumb"><button tabIndex={0} onClick={() => void back()}><ArrowLeft size={15} />工作台</button><ChevronRight size={14} /><span>{kindLabels[task.kind]}{train ? '训练 / 微调' : '运行 / 试用'}</span></div>
    <div className="page-heading"><div><h1>{task.name}</h1><p>选择模型、准备输入，检查配置后开始本次{train ? '训练' : '运行'}。</p>{saving && !busy && <small role="status">正在自动保存草稿…</small>}</div><Button busy={busy} disabled={!dirty || runningReadonly} onClick={saveOnly}><Save size={15} />{dirty ? '保存草稿' : '草稿已保存'}</Button></div>
    {taskRuntime && windowsTrial && !remote && <TaskRuntimeNotice runtime={taskRuntime} kind={draft.kind} pipeline={currentModel?.pipeline} />}
    <WorkRecipeContext state={recipeContext} draft={draft} />
    {runningReadonly && <div className="warning" role="status"><p>{latestAttempt?.recovery_required ? '当前执行的停止状态待核实，配置暂时只读。请先核实原执行。' : latestAttempt?.state === 'paused' ? '当前训练已暂停，配置保持只读。可以继续训练或停止。' : '当前任务正在执行，配置只读。执行结束后可继续修改。'}</p><Button disabled={showingLatest} onClick={() => setAttempt(latestAttempt)}>查看当前执行</Button></div>}
    <div className="workbench-layout"><section ref={composer} className={`composer${marketNotice ? ' market-selection-applied' : ''}`} aria-label="任务配置">
      {draft.checkpoint_id && <p className="warning">此任务从完整检查点继续原优化轨迹，模型、数据和训练参数已固定。检查通过后明确开始，原运行终态保留。</p>}
      <div className="section-title"><h2>{train ? '训练配置' : '输入与模型'}</h2><Badge>{kindLabels[task.kind]}</Badge></div>
      <fieldset className="task-fields" disabled={editingDisabled || Boolean(draft.checkpoint_id)}>
      {task.kind === 'text' ? <>
      <div className="field"><div className="label-action"><label htmlFor="base-model">基座模型</label><button tabIndex={0} type="button" onClick={() => onImport('model')}>导入模型</button></div><select id="base-model" aria-label="选择基座模型" value={draft.model_id || ''} onChange={e => selectBase(e.target.value || null)}><option value="">请选择已导入的模型</option>{draft.model_id && !available.some(model => model.id === draft.model_id) && <option value={draft.model_id} disabled={windowsTrial}>已保存模型 · 尚未读回（{draft.model_id}）</option>}{available.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select>{localText && draft.model_id && <small role="status" className="muted">{loadStatus}</small>}</div>
      {currentModel && <small className="muted">{currentModel.format} · 本机文件已登记</small>}{!train && !remote && (Boolean(draft.adapter_id) || adapters.some(item => item.base_model_id === draft.model_id)) && <label>训练适配器<select aria-label="训练适配器" value={draft.adapter_id || ''} onChange={e => change({ ...draft, adapter_id: e.target.value || null })}><option value="">仅使用基座模型</option>{draft.adapter_id && !adapters.some(item => item.id === draft.adapter_id && item.base_model_id === draft.model_id) && <option value={draft.adapter_id}>已保存适配器 · 待核实（{draft.adapter_id}）</option>}{adapters.filter(item => item.base_model_id === draft.model_id).map(item => <option key={item.id} value={item.id}>{item.name} · 实验产物</option>)}</select><small className="warning">实验适配器用于比较训练前后的输出，质量尚未通过验收。</small></label>}
      {train ? <><div className="field"><div className="label-action"><label htmlFor="training-data">训练数据</label><button tabIndex={0} type="button" onClick={() => onImport('dataset')}>导入数据</button></div><select id="training-data" aria-label="选择训练数据" value={draft.dataset_id || ''} onChange={e => change({ ...draft, dataset_id: e.target.value || null })}><option value="">请选择已检查的数据集</option>{currentDataset?.dataset_split_role === 'validation' && <option value={currentDataset.id} disabled>{currentDataset.name} · 验证子集（不可训练）</option>}{datasets.filter(dataset => dataset.schema !== 'image_caption_v1' && dataset.dataset_split_role !== 'validation').map(dataset => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.sample_count || 0} 条{dataset.dataset_split_role === 'train' ? ' · 训练子集' : ''}</option>)}</select></div>{currentDataset && <DatasetSplitBinding dataset={currentDataset} projectId={task.project_id} model={currentModel} maxSeqLength={runtime.max_seq_length ?? 512} onInspect={() => setSplittingDataset(currentDataset)} />}<div className="field"><div className="label-action"><label htmlFor="training-evaluation-plan">训练前冻结评测方案</label>{onCreateEvaluationPlan && <button tabIndex={0} type="button" onClick={onCreateEvaluationPlan}>新建评测方案</button>}</div><select id="training-evaluation-plan" value={draft.evaluation_plan_id || ''} onChange={e => change({ ...draft, evaluation_plan_id: e.target.value || null })}><option value="">暂不绑定 · 仅生成实验产物</option>{evaluationPlans.map(plan => <option key={plan.id} value={plan.id}>{plan.name} · {plan.sample_count} 条</option>)}</select><small className={draft.evaluation_plan_id ? 'muted' : 'warning'}>{draft.evaluation_plan_id ? '提交时固定此评测方案的版本，用于训练后的独立质量验收。' : '未提前绑定评测方案的训练产物可以试用与对照，不能直接登记为已验收候选。'}</small></div><div className="two-fields"><label>训练类型<input value="SFT 监督微调" readOnly /></label><label>更新方式<input value="LoRA" readOnly /></label></div><p className="muted">训练将生成独立适配器，保留原始模型与数据版本。提交前会检查实际监督内容与运行环境。</p></> : <label>输入内容<textarea aria-label="输入内容" onDragOver={e=>{if(currentModel?.supports_media && e.dataTransfer.types.includes("Files"))e.preventDefault();}} onDrop={e=>{if(!currentModel?.supports_media || !e.dataTransfer.files.length)return; e.preventDefault(); if(e.dataTransfer.files.length!==1){setError("每次可拖入一份素材。");return;} void attachMaterial(e.dataTransfer.files[0]);}} rows={7} value={draft.input.prompt} placeholder={currentModel?.pipeline === 'llama-ocr' ? '拖入含文字的 PNG 图片，在素材引用下一行输入“Free OCR.”。' : currentModel?.pipeline === 'llama-rerank' ? '首行输入查询，之后每行输入一份候选文本。' : currentModel?.pipeline === 'llama-decision' ? '输入含 state 和 questions 的 JSON。' : currentModel?.supports_media ? "可拖入一份本机素材并输入问题；也可在首行写 @素材 加项目素材名称或编号。" : "输入你希望模型处理的内容…"} onChange={e => change({ ...draft, input: { ...draft.input, prompt: e.target.value } })} /></label>}
      <details className="runtime-settings" open><summary><Settings2 size={15} />运行设置</summary><div className="form-stack"><ExecutionLocation projectId={task.project_id} value={draft.execution_target_id} disabled={editingDisabled || Boolean(draft.checkpoint_id)} onChange={changeLocation} />{!train && !remote && <RuntimePresets runtime={runtime} disabled={editingDisabled} onApply={value => change({ ...draft, runtime: value })} />}{remote ? <label>执行设备<input readOnly value="NVIDIA CUDA · BF16" /></label> : <label>执行设备<select value={runtime.device_id} onChange={e => updateRuntime('device_id', e.target.value)}>{!devices.some(device => device.id === runtime.device_id) && (devices.length > 0 || runtime.device_id !== 'apple-gpu') && <option value={runtime.device_id}>已保存设备 · 待检查（{runtime.device_id}）</option>}{devices.length ? devices.map(device => <option key={device.id} value={device.id}>{device.name}</option>) : <option value={window.ailabHF ? 'cpu' : 'apple-gpu'}>{window.ailabHF ? '本机 CPU' : '本机 Apple GPU'}</option>}</select></label>}
      {windowsTrial && !remote && runtime.device_id === 'cpu' && <CpuThreadsField devices={devices} value={runtime.cpu_threads} onChange={threads => updateRuntime('cpu_threads', threads)} />}
      {train ? <TrainingFields runtime={runtime} state={trainingContract} disabled={editingDisabled || Boolean(draft.checkpoint_id)} acceptedSamples={preflight?.check_report?.accepted_samples} onChange={updateRuntime} /> : <div className="two-fields">{!remote && <><label>KV 缓存精度<select value={runtime.kv_precision ?? (windowsTrial ? 'f16' : 'auto')} onChange={e => updateRuntime('kv_precision', e.target.value)}><option value="auto">模型精度</option>{window.ailabHF ? <><option value="f16">FP16 · 16 位（默认）</option><option value="q8">Q8_0 · 8-bit</option><option value="q4">Q4_0 · 4-bit</option></> : <option value="q4" disabled>4-bit · 质量未通过</option>}</select></label><label>提示词分块上限<select value={runtime.prefill_step_size ?? 2048} onChange={e => updateRuntime('prefill_step_size', Number(e.target.value))}><option value={512}>512 词元</option><option value={2048}>2048 词元</option><option value={4096}>4096 词元</option></select></label></>}<GenerationNumericFields runtime={runtime} remote={remote} onChange={updateRuntime} /></div>}{!train && <GenerationFields key={task.id} supportsThinking={Boolean(window.ailabHF && models.find(m=>m.id===draft.model_id)?.supports_thinking)} runtime={runtime} disabled={editingDisabled} onChange={value => change({ ...draft, runtime: value })} />}{train && <small>仅监督助手回答；超长样本排除，不拼接。检查时会列出有效监督量。</small>}</div></details>
      </> : <MediaFields devices={devices} deviceName={checkedDeviceName} draft={draft} models={draftModels} datasets={datasets} adapters={adapters} materials={materials} onChange={change} onImport={onImport} />}
      {train && ['text', 'image'].includes(task.kind) && <Button disabled={editingDisabled || Boolean(draft.checkpoint_id)} onClick={openMarket}>从数据市场选择训练数据</Button>}
      </fieldset>
      {marketNotice && <p className="market-notice" role="status">{marketNotice}</p>}
      {task.kind === 'text' && train && trainingContract.error && <Button disabled={busy} onClick={trainingContract.retry}>重新读取训练参数</Button>}
      <ErrorNotice message={error} />
      {preflight && <div className="preflight" aria-label="运行前检查"><strong ref={preflightSummary} tabIndex={-1}>{preflight.can_submit ? '检查通过，可以运行' : '请先完成以下准备'}</strong>{preflight.blocking.map((issue, index) => <p key={index} className="error">{issue.message}</p>)}{preflight.warnings.map((issue, index) => <p key={index} className="warning">{issue.message}</p>)}<UploadSummary preflight={preflight} /><DataCheck report={preflight.check_report} /><details><summary>查看本次已应用配置</summary><pre>{JSON.stringify(preflight.effective_config || {}, null, 2)}</pre></details>{preflight.can_submit && <p className="muted">{currentModel?.name} · {preflight.execution_target?.name || checkedDeviceName}<br />本次输入在所选设备处理；运行配方将固定保存。</p>}</div>}
      {preflight?.can_submit ? <Button primary className="full" onClick={submit} busy={busy} disabled={trainingBlocked || generationBlocked || runningReadonly}><Play size={16} />{remote ? '确认发送并开始' : '开始'}{train ? '训练' : '运行'}</Button> : <Button primary className="full" onClick={check} busy={busy} disabled={trainingBlocked || generationBlocked || runningReadonly}><FileCheck2 size={16} />检查配置</Button>}
    </section><div className="result-column">{attempts.length > 1 && <label>查看运行记录<select aria-label="查看运行记录" value={attempt?.id || ''} onChange={e => setAttempt(attempts.find(item => item.id === e.target.value) || null)}>{attempts.map((item, i) => <option key={item.id} value={item.id}>{i === 0 ? '最近一次' : `历史运行 ${attempts.length - i}`} · {item.id.slice(-8)}</option>)}</select></label>}{attemptCursor && <Button busy={historyBusy} onClick={() => void loadMoreAttempts()}>加载更早运行记录</Button>}{/* 查看旧记录时保留当前执行的同一个 RunResult，继续接收实际状态，不另建轮询器。 */}
      {latestAttempt && (runningReadonly || showingLatest) && <div hidden={!showingLatest}><RunResult key={latestAttempt.id} initial={latestAttempt} onChanged={onUpdated} onAttemptUpdated={observeAttempt} onExport={onExport} onRestoreTask={onRestoreTask} /></div>}
      {attempt && !showingLatest && <RunResult key={attempt.id} initial={attempt} onChanged={onUpdated} onAttemptUpdated={observeAttempt} onExport={onExport} onRestoreTask={onRestoreTask} />}
      {!attempt && <section className="result-card"><div className="result-header"><h3>{train ? '训练记录' : '运行结果'}</h3><Badge>尚未开始</Badge></div><Empty title={train ? '准备好数据后开始训练' : '模型输出会显示在这里'}>{train ? '实际训练指标、检查点与最终产物会保留在当前任务。' : '运行记录自动保存。完成后可查看配方，或保存到作品与素材。'}</Empty></section>}<div className="hint"><Clock3 size={16} /><span>任务归属于当前项目，历史结果保留原模型与配置。</span></div></div></div>
  </>;
}
