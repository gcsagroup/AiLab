import { useContext, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import { LibraryReadContext } from './LibraryReadContext';
import type { Dataset, DatasetSplit, DatasetSplitCounts, DatasetSplitPlan, DatasetSplitPreview, DatasetSplitResult, Model } from './types';
import { Badge, Button, Dialog, ErrorNotice, readableSize } from './ui';
import type { ExportObject } from './ExportDialog';

const active = new Set<DatasetSplitPlan['status']>(['preparing', 'cancelling']);
const stateLabels: Record<DatasetSplitPlan['status'], string> = { preparing: '正在检查与划分', cancelling: '正在停止检查', ready: '预览已准备，尚未应用', blocked: '检查完成，需要调整', failed: '检查未完成', cancelled: '本次检查已停止', recovery_required: '上次检查被中断', applied: '已生成独立数据版本' };
type Command = { kind: 'prepare' | 'cancel' | 'apply'; path: string; body: unknown; key: string };
const staleMessage = '工作库读取已失效，当前输入保留。请重新读取后继续。';

function rejected(error: unknown): boolean {
  if (typeof error === 'string') { try { return rejected(JSON.parse(error)); } catch { return false; } }
  const code = (error as { error?: { code?: string } })?.error?.code;
  return typeof code === 'string' && !/^(CONTROL_|LOCAL_BRIDGE|INTERNAL_|NETWORK_|UNKNOWN)/.test(code);
}
function countsValid(counts: DatasetSplitCounts | null): boolean {
  return Boolean(counts && ['input_samples', 'accepted_samples', 'excluded_samples', 'ignored_lines', 'source_groups', 'train_samples', 'validation_samples', 'train_groups', 'validation_groups', 'supervised_tokens', 'shifted_supervised_tokens'].every(key => Number.isInteger(counts[key as keyof DatasetSplitCounts]) && counts[key as keyof DatasetSplitCounts] >= 0));
}
function subsetMatches(value: Dataset, record: DatasetSplit, role = value.dataset_split_role): boolean {
  return Boolean(role && value.project_id === record.project_id && value.schema === 'sft' && value.status === 'ready' && value.dataset_split_role === role && value.dataset_split_id === record.id && value.source_dataset_id === record.source_dataset_id && value.id === (role === 'train' ? record.train_dataset_id : record.validation_dataset_id) && value.version_id === (role === 'train' ? record.train_version_id : record.validation_version_id) && value.manifest_digest === (role === 'train' ? record.train_manifest_digest : record.validation_manifest_digest));
}
function applicable(plan: DatasetSplitPlan): boolean {
  const counts = plan.counts;
  return plan.status === 'ready' && /^[a-f0-9]{64}$/.test(plan.plan_digest || '') && Boolean(plan.preview && plan.preview.new_files > 0 && plan.preview.new_bytes > 0) && plan.blocking.length === 0 && countsValid(counts) && Boolean(counts && counts.train_samples > 0 && counts.validation_samples > 0 && counts.train_groups > 0 && counts.validation_groups > 0 && counts.train_samples + counts.validation_samples === counts.accepted_samples);
}
function PreviewEvidence({ preview }: { preview: DatasetSplitPreview }) {
  const exclusions: Record<string, string> = { INVALID_SAMPLE: '样本结构无效', NO_SUPERVISION: '没有有效监督内容', MEDIA_OR_TOOLS_UNSUPPORTED: '不支持媒体或工具消息', EMPTY_CONTENT: '消息内容为空', RESERVED_TOKEN: '包含保留词元', INVALID_ROLES: '消息角色顺序无效', SEQUENCE_TOO_LONG: '超过最大序列长度' };
  return <>
    <dl className="facts"><div><dt>原数据版本</dt><dd>{preview.source_version_id}</dd></div><div><dt>应用后新增</dt><dd>{preview.new_files} 个文件 · {readableSize(preview.new_bytes)}</dd></div></dl>
    <p className="muted">排除原因：{Object.entries(preview.exclusion_counts).length ? Object.entries(preview.exclusion_counts).map(([code, count]) => `${exclusions[code] || code} ${count} 条`).join('；') : '没有排除样本。'}</p>
    <details><summary>查看分词与监督证据（最多 3 条）</summary>
      <p className="muted">以下是原始行号对应的词元编号和监督标签。标签 -100 不参与损失；这里只展示已检查样本，不代表验证损失已运行。</p>
      {preview.token_labels_examples.map(example => <details key={example.line}><summary>原始第 {example.line} 行 · 监督 {example.supervised_tokens} 个 · 移位后 {example.shifted_supervised_tokens} 个</summary>
        <p className="muted">助手范围：{example.assistant_spans.map(span => `消息 ${span.message_index}，词元 ${span.start}–${span.end}（不含结尾位置）`).join('；')}</p>
        <pre aria-label={`第 ${example.line} 行词元与监督标签`} style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 240, overflow: 'auto' }}>{`词元编号：${JSON.stringify(example.input_ids)}\n监督标签：${JSON.stringify(example.labels)}`}</pre>
      </details>)}
      {!preview.token_labels_examples.length && <p>没有可展示的有效监督样本。</p>}
      <details><summary>查看固定摘要</summary><dl className="facts"><div><dt>原件清单</dt><dd>{preview.source_manifest_digest}</dd></div><div><dt>模型清单</dt><dd>{preview.model_manifest_digest}</dd></div><div><dt>检查身份</dt><dd>{preview.check_identity_digest}</dd></div><div><dt>分词配方</dt><dd>{preview.tokenization_recipe_digest}</dd></div><div><dt>监督配方实现</dt><dd>{preview.recipe_implementation_sha256}</dd></div>{Object.entries(preview.tokenizer_files).map(([name, digest]) => <div key={name}><dt>{name}</dt><dd>{digest}</dd></div>)}</dl></details>
    </details>
  </>;
}
export function DatasetSplitSummary({ counts, validationFractionBps }: { counts: DatasetSplitCounts; validationFractionBps: number }) {
  const fraction = counts.accepted_samples ? (counts.validation_samples / counts.accepted_samples * 100).toFixed(2) : '0.00';
  return <>
    <dl className="facts" aria-label="划分数量与比例">
      <div><dt>原始样本</dt><dd>{counts.input_samples} 条 · 忽略空行 {counts.ignored_lines} 行</dd></div>
      <div><dt>有效样本</dt><dd>{counts.accepted_samples} 条 · 排除 {counts.excluded_samples} 条</dd></div>
      <div><dt>来源组</dt><dd>{counts.source_groups} 组</dd></div>
      <div><dt>训练子集</dt><dd>{counts.train_samples} 条 · {counts.train_groups} 组</dd></div>
      <div><dt>验证子集</dt><dd>{counts.validation_samples} 条 · {counts.validation_groups} 组</dd></div>
      <div><dt>验证比例</dt><dd>请求 {(validationFractionBps / 100).toFixed(2)}% · 实际样本 {fraction}%</dd></div>
      <div><dt>监督词元</dt><dd>{counts.supervised_tokens} 个 · 移位后 {counts.shifted_supervised_tokens} 个</dd></div>
    </dl>
    <p className="muted">按来源组分配，实际样本比例可能与请求不同。零监督和超长等无效样本先排除；具体原因见检查说明。</p>
    <p className="warning">语义近似尚未检查。验证子集用于隔离与检查，尚未计算验证损失，也不证明模型质量；默认 NVIDIA 上传只包含训练子集。</p>
  </>;
}

export function DatasetSplitBinding({ dataset, projectId, model, maxSeqLength, onInspect }: { dataset: Dataset; projectId: string; model?: Model; maxSeqLength: number; onInspect: () => void }) {
  const captureLibraryRead = useContext(LibraryReadContext); const [revision, setRevision] = useState(0);
  const key = `${projectId}:${dataset.id}:${dataset.version_id || ''}:${dataset.dataset_split_id || ''}:${dataset.dataset_split_role || ''}:${dataset.source_dataset_id || ''}:${dataset.project_id || ''}:${dataset.manifest_digest || ''}:${dataset.schema || ''}:${dataset.status || ''}`;
  const [read, setRead] = useState<{ key: string; value?: DatasetSplit; error?: string; isCurrent: () => boolean } | null>(null);
  useEffect(() => {
    if (!dataset.dataset_split_id) { setRead(null); return; }
    let live = true; const libraryCurrent = captureLibraryRead(); const isCurrent = () => live && libraryCurrent();
    setRead({ key, isCurrent });
    api<DatasetSplit>('GET', `/datasets/splits/${encodeURIComponent(dataset.dataset_split_id)}`).then(value => {
      if (!isCurrent()) return;
      if (value.resource_type !== 'dataset-split' || value.status !== 'ready' || value.id !== dataset.dataset_split_id || value.project_id !== projectId || !subsetMatches(dataset, value) || !countsValid(value.counts)) throw new Error('划分证明与当前数据不一致，请重新读取。');
      setRead({ key, value, isCurrent });
    }).catch(e => { if (isCurrent()) setRead({ key, error: errorMessage(e), isCurrent }); });
    return () => { live = false; };
  }, [key, revision, captureLibraryRead]);
  if (!dataset.dataset_split_id) return <div><p className="warning">新训练需要先按来源组划分训练与验证数据。原件保留，未应用的预览不能用于训练。</p><Button onClick={onInspect}>划分训练与验证</Button></div>;
  const current = read?.key === key && read.isCurrent(); const value = current ? read.value : undefined;
  const error = read?.key === key && !read.isCurrent() ? staleMessage : current ? read.error : undefined;
  const incompatible = value && (Boolean(model && (model.manifest_digest ? model.manifest_digest !== value.model_manifest_digest : model.id !== value.model_id)) || maxSeqLength !== value.max_seq_length);
  return <section aria-label="训练数据划分绑定">
    <p>{dataset.dataset_split_role === 'train' ? '已选择训练子集，提交时固定来源组证明。' : '当前是验证子集，不能用于训练。请选择对应的训练子集。'}</p>
    {incompatible && <p className="warning">当前模型或最大序列长度与划分检查不一致，请从原数据重新划分；检查配置会阻止提交。</p>}
    {!value && !error && <p className="muted">正在读取来源组证明…</p>}
    {value && <details><summary>查看划分绑定</summary><dl className="facts"><div><dt>原数据版本</dt><dd>{value.source_version_id}</dd></div><div><dt>划分种子</dt><dd>{value.split_seed}</dd></div><div><dt>检查模型</dt><dd>{model?.id === value.model_id ? model.name : value.model_id}</dd></div><div><dt>最大序列长度</dt><dd>{value.max_seq_length}</dd></div></dl><DatasetSplitSummary counts={value.counts} validationFractionBps={value.validation_fraction_bps} /></details>}
    <ErrorNotice message={error || ''} />{error && <Button onClick={() => setRevision(value => value + 1)}>重新读取来源证明</Button>}
    <Button onClick={onInspect}>查看划分与子集</Button>
  </section>;
}

function DatasetSplitHistory({ projectId, datasetId, refreshKey, disabled, onSelect }: { projectId: string; datasetId: string; refreshKey: string; disabled: boolean; onSelect: (plan: DatasetSplitPlan) => void }) {
  const captureLibraryRead = useContext(LibraryReadContext), [revision, setRevision] = useState(0);
  const [read, setRead] = useState<{ items: DatasetSplitPlan[]; next: string | null; busy: boolean; error: string; isCurrent: () => boolean } | null>(null);
  const live = useRef(true), readGeneration = useRef(0), identity = `${projectId}:${datasetId}`, identityRef = useRef(identity); identityRef.current = identity;
  async function load(cursor?: string) {
    const previousItems = cursor && read?.isCurrent() ? read.items : [];
    const libraryCurrent = captureLibraryRead(), currentGeneration = ++readGeneration.current;
    const isCurrent = () => live.current && identityRef.current === identity && currentGeneration === readGeneration.current && libraryCurrent();
    setRead({ items: previousItems, next: null, busy: true, error: '', isCurrent });
    try {
      const page = await api<{ items: DatasetSplitPlan[]; next_cursor?: string | null }>('GET', `/datasets/split-plans?project_id=${encodeURIComponent(projectId)}&source_dataset_id=${encodeURIComponent(datasetId)}&limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`);
      if (!isCurrent()) return;
      if (!Array.isArray(page.items) || page.items.some(item => item.resource_type !== 'dataset-split-plan' || item.project_id !== projectId || item.source_dataset_id !== datasetId || !(item.status in stateLabels))) throw new Error('已有计划与当前原件不一致，请重新读取。');
      setRead(previous => ({ items: [...(cursor ? previous?.items || [] : []), ...page.items].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index), next: page.next_cursor || null, busy: false, error: '', isCurrent }));
    } catch (e) { if (isCurrent()) setRead(previous => ({ items: previous?.items || [], next: cursor || null, busy: false, error: errorMessage(e), isCurrent })); }
  }
  useEffect(() => { live.current = true; void load(); return () => { live.current = false; readGeneration.current += 1; }; }, [identity, refreshKey, revision, captureLibraryRead]);
  const current = Boolean(read?.isCurrent());
  return <section aria-label="已有划分检查与预览" style={{ marginTop: 16 }}>
    <h3>已有检查与预览</h3><p className="muted">可找回关闭窗口、重启或恢复工作库前的记录。读取记录不会重新分词、应用划分或启动训练。</p>
    {!current && read ? <><ErrorNotice message="已有计划读取已失效，当前输入保留。" /><Button disabled={disabled} onClick={() => setRevision(value => value + 1)}>重新读取已有记录</Button></> : read && <>
      {read.busy && <p role="status">正在读取已有记录…</p>}
      {!read.busy && !read.error && !read.items.length && <p className="muted">这份原件尚无划分记录。</p>}
      {read.items.map((item, index) => <div key={item.id} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 8 }}><span className="muted">{index + 1}. {stateLabels[item.status]} · 种子 {item.split_seed} · 验证 {(item.validation_fraction_bps / 100).toFixed(2)}% · 长度 {item.max_seq_length}</span><Button disabled={disabled || read.busy} onClick={() => onSelect(item)}>读取已有记录 {index + 1}</Button></div>)}
      <ErrorNotice message={read.error} />{read.error && <Button disabled={disabled || read.busy} onClick={() => void load(read.next || undefined)}>重试读取已有记录</Button>}
      {read.next && !read.error && <Button busy={read.busy} disabled={disabled} onClick={() => void load(read.next!)}>载入更多已有记录</Button>}
    </>}
  </section>;
}

export default function DatasetSplitDialog({ dataset, models, projectId, initialModelId, initialMaxSeqLength, onClose, onChanged, onUseTraining, onExport }: {
  dataset: Dataset; models: Model[]; projectId: string; initialModelId?: string | null; initialMaxSeqLength?: number;
  onClose: () => void; onChanged: (result?: DatasetSplitResult) => void; onUseTraining?: (dataset: Dataset) => void; onExport?: (object: ExportObject) => void;
}) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [modelId, setModelId] = useState(initialModelId || '');
  const [maxSequence, setMaxSequence] = useState(String(initialMaxSeqLength ?? 512));
  const [seed, setSeed] = useState('0'); const [validationPercent, setValidationPercent] = useState('20');
  const [plan, setPlan] = useState<DatasetSplitPlan | null>(null); const [split, setSplit] = useState<DatasetSplit | null>(null); const [cleanupPlan, setCleanupPlan] = useState<DatasetSplitPlan | null>(null);
  const [trainDataset, setTrainDataset] = useState<Dataset | null>(null);
  const [pending, setPending] = useState<Command | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [readVersion, setReadVersion] = useState(0);
  const live = useRef(true); const generation = useRef(0); const scope = useRef<(() => boolean) | null>(null); const applyCommand = useRef<Command | null>(null);
  const identity = `${projectId}:${dataset.id}:${dataset.version_id || ''}:${dataset.dataset_split_id || ''}`;
  const identityRef = useRef(identity); identityRef.current = identity;
  const stale = Boolean(scope.current && !scope.current()); const working = busy && !stale;
  const activePlan = Boolean(plan && active.has(plan.status) && !stale);
  function capture() {
    const currentGeneration = generation.current; const libraryCurrent = captureLibraryRead();
    return () => live.current && identityRef.current === identity && generation.current === currentGeneration && libraryCurrent();
  }
  useEffect(() => { live.current = true; return () => { live.current = false; generation.current += 1; }; }, []);
  function verifySplit(value: DatasetSplit) {
    const expectedSource = dataset.source_dataset_id || dataset.id;
    if (value.resource_type !== 'dataset-split' || value.project_id !== projectId || value.source_dataset_id !== expectedSource || value.status !== 'ready' || !countsValid(value.counts) || value.train_dataset_id === value.validation_dataset_id || (dataset.dataset_split_id && value.id !== dataset.dataset_split_id)) throw new Error('划分记录与当前数据不一致，请重新读取。');
    if (!dataset.dataset_split_id && ((dataset.version_id && value.source_version_id !== dataset.version_id) || value.model_id !== modelId || value.max_seq_length !== Number(maxSequence) || value.split_seed !== Number(seed) || value.validation_fraction_bps !== Math.round(Number(validationPercent) * 100) || (plan && (value.plan_id !== plan.id || value.plan_digest !== plan.plan_digest)))) throw new Error('划分结果与本次预览参数不一致，请重新读取。');
    if (dataset.dataset_split_id) verifySubset(dataset, value, dataset.dataset_split_role);
  }
  function verifySubset(value: Dataset, record: DatasetSplit, role: Dataset['dataset_split_role']) {
    if (!subsetMatches(value, record, role)) throw new Error('划分结果的子集身份或版本不一致，请重新读取。');
  }
  function acceptCleanupPlan(value: DatasetSplitPlan, record: DatasetSplit) {
    if (value.id !== record.plan_id || value.project_id !== record.project_id || value.source_dataset_id !== record.source_dataset_id || value.status !== 'applied' || value.applied_split_id !== record.id || value.plan_digest !== record.plan_digest) throw new Error('已应用计划与划分结果不一致，请重新读取。');
    setCleanupPlan(value);
  }
  async function readSplit(id: string, isCurrent: () => boolean, knownPlan?: DatasetSplitPlan) {
    const value = await api<DatasetSplit>('GET', `/datasets/splits/${encodeURIComponent(id)}`);
    if (!isCurrent()) return;
    verifySplit(value); setSplit(value); setError(''); onChanged();
    const appliedPlan = knownPlan || await api<DatasetSplitPlan>('GET', `/datasets/split-plans/${encodeURIComponent(value.plan_id)}`);
    if (isCurrent()) acceptCleanupPlan(appliedPlan, value);
  }
  function verifyPlan(value: DatasetSplitPlan) {
    if (value.resource_type !== 'dataset-split-plan' || value.project_id !== projectId || value.source_dataset_id !== dataset.id || value.model_id !== modelId || value.max_seq_length !== Number(maxSequence) || value.split_seed !== Number(seed) || value.validation_fraction_bps !== Math.round(Number(validationPercent) * 100) || !(value.status in stateLabels) || !Array.isArray(value.blocking) || !Array.isArray(value.warnings) || (value.counts !== null && !countsValid(value.counts))) throw new Error('划分预览与当前数据或参数不一致，请重新读取。');
  }
  async function acceptPlan(value: DatasetSplitPlan, isCurrent: () => boolean) {
    if (!isCurrent()) return;
    verifyPlan(value); setPlan(value);
    if (value.status === 'applied') {
      if (!value.applied_split_id) throw new Error('划分已应用，但缺少新版本编号，请重新读取。');
      setPending(null);
      await readSplit(value.applied_split_id, isCurrent, value);
    }
  }
  // 读取属于产生它的那次渲染，延后启动也不能借用新操作的代次。
  const readGeneration = generation.current;
  useEffect(() => {
    if (readGeneration !== generation.current) return;
    if (!dataset.dataset_split_id && !plan) return;
    if (scope.current && !scope.current()) return;
    let current = true; let timer: ReturnType<typeof setTimeout>;
    const captured = capture(); const isCurrent = () => current && captured(); scope.current = captured;
    async function read() {
      try {
        if (dataset.dataset_split_id) await readSplit(dataset.dataset_split_id, isCurrent);
        else if (plan) {
          const value = await api<DatasetSplitPlan>('GET', `/datasets/split-plans/${encodeURIComponent(plan.id)}`);
          if (!isCurrent()) return;
          await acceptPlan(value, isCurrent); if (!isCurrent()) return;
          setError(''); if (active.has(value.status)) timer = setTimeout(read, 700);
        }
      } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
      finally { if (isCurrent()) setBusy(false); }
    }
    void read(); return () => { current = false; clearTimeout(timer); };
  }, [identity, plan?.id, plan?.status, readVersion]);
  function retryRead() { generation.current += 1; scope.current = capture(); setBusy(false); setError(''); setReadVersion(value => value + 1); }
  function edit(change: () => void) { generation.current += 1; scope.current = null; setPlan(null); setPending(null); setError(''); change(); }
  function selectExisting(value: DatasetSplitPlan) {
    if (working || pending || activePlan) return;
    generation.current += 1; scope.current = capture(); setBusy(true); setError(''); setPending(null); setSplit(null); setTrainDataset(null); setCleanupPlan(null); applyCommand.current = null;
    setModelId(value.model_id); setMaxSequence(String(value.max_seq_length)); setSeed(String(value.split_seed)); setValidationPercent(String(value.validation_fraction_bps / 100)); setPlan(value); setReadVersion(version => version + 1);
  }
  async function execute(command: Command) {
    generation.current += 1; const isCurrent = capture(); scope.current = isCurrent;
    setPending(command); setBusy(true); setError('');
    try {
      if (command.kind === 'apply') {
        applyCommand.current = command;
        const result = await api<DatasetSplitResult>('POST', command.path, command.body, command.key);
        if (!isCurrent()) return;
        verifySplit(result.split);
        verifySubset(result.train_dataset, result.split, 'train'); verifySubset(result.validation_dataset, result.split, 'validation');
        setSplit(result.split); setTrainDataset(result.train_dataset); setPlan(value => value ? { ...value, status: 'applied', applied_split_id: result.split.id, train_dataset_id: result.train_dataset.id, validation_dataset_id: result.validation_dataset.id } : value); setPending(null); onChanged(result);
        const appliedPlan = await api<DatasetSplitPlan>('GET', `/datasets/split-plans/${encodeURIComponent(result.split.plan_id)}`);
        if (isCurrent()) acceptCleanupPlan(appliedPlan, result.split);
      } else {
        const value = await api<DatasetSplitPlan>('POST', command.path, command.body, command.key);
        if (!isCurrent()) return;
        await acceptPlan(value, isCurrent); if (isCurrent()) setPending(null);
      }
    } catch (e) { if (isCurrent()) { if (rejected(e)) setPending(null); setError(errorMessage(e)); } }
    finally { if (isCurrent()) setBusy(false); }
  }
  const numericSequence = Number(maxSequence), numericSeed = Number(seed), bps = Math.round(Number(validationPercent) * 100);
  const inputValid = Boolean(modelId && /^\d+$/.test(maxSequence) && Number.isInteger(numericSequence) && numericSequence >= 32 && numericSequence <= 2048 && /^\d+$/.test(seed) && Number.isInteger(numericSeed) && numericSeed >= 0 && numericSeed <= 4294967295 && /^\d+(\.\d{1,2})?$/.test(validationPercent) && bps >= 1 && bps <= 9999);
  function prepare() {
    if (!inputValid || working || pending || activePlan) return;
    void execute({ kind: 'prepare', path: '/datasets/split-plans', body: { project_id: projectId, source_dataset_id: dataset.id, model_id: modelId, max_seq_length: numericSequence, split_seed: numericSeed, validation_fraction_bps: bps }, key: crypto.randomUUID() });
  }
  async function useTraining() {
    if (!split || working || stale) return;
    const isCurrent = capture(); setBusy(true); setError('');
    try {
      const value = trainDataset || await api<Dataset>('GET', `/datasets/${encodeURIComponent(split.train_dataset_id)}`);
      if (!isCurrent()) return;
      verifySubset(value, split, 'train');
      onUseTraining?.(value);
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  const lockedInputs = working || Boolean(pending) || activePlan;
  const textModels = models.filter(model => !model.modality || model.modality === 'text');
  return <Dialog title={dataset.dataset_split_id ? '查看数据划分' : '划分训练与验证数据'} wide onClose={onClose} preventClose={working || Boolean(pending && !stale) || activePlan}>
    <p>{dataset.name} · {dataset.sample_count || 0} 条样本</p>
    <p className="muted">按原始记录的 source_id 分组，同一来源组完整保留在一侧。先排除无效监督样本，再预览影响；明确应用才生成新版本，原件保留。</p>
    {!dataset.dataset_split_id && !split && <DatasetSplitHistory projectId={projectId} datasetId={dataset.id} refreshKey={plan ? `${plan.id}:${plan.status}` : ''} disabled={working || Boolean(pending) || activePlan} onSelect={selectExisting} />}
    {split && !stale ? <section className="review-box" aria-label="已应用数据划分"><h3>已生成训练与验证两个独立版本</h3>
      <DatasetSplitSummary counts={split.counts} validationFractionBps={split.validation_fraction_bps} />
      <dl className="facts"><div><dt>原数据版本</dt><dd>{split.source_version_id}</dd></div><div><dt>划分种子</dt><dd>{split.split_seed}</dd></div><div><dt>分词模型</dt><dd>{models.find(model => model.id === split.model_id)?.name || split.model_id}</dd></div><div><dt>最大序列长度</dt><dd>{split.max_seq_length}</dd></div></dl>
      <p className="muted">草稿尚未自动更改。训练需要使用训练子集，并保持检查时的模型与最大序列长度；换模型或改变长度后应重新划分。</p>
      {cleanupPlan?.stage_cleanup_status === 'pending' && <><p className="warning">正式数据已完整登记。部分检查暂存尚未清理，可重试清理，不会生成第二份划分。</p><Button busy={working} disabled={Boolean(pending)} onClick={() => void execute(applyCommand.current || { kind: 'apply', path: '/datasets/splits', body: { plan_id: cleanupPlan.id, plan_digest: cleanupPlan.plan_digest }, key: crypto.randomUUID() })}>重试清理暂存</Button></>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>{onUseTraining && <Button primary busy={working} onClick={() => void useTraining()}>使用训练子集</Button>}{onExport && <Button disabled={working} onClick={() => onExport({ type: 'dataset-split', id: split.id, name: `${dataset.name}的数据划分` })}>导出原件、子集与证明</Button>}</div>
    </section> : !dataset.dataset_split_id && <div className="form-stack" style={{ marginTop: 16 }}>
      <label>用于分词检查的模型<select aria-label="划分检查模型" value={modelId} disabled={lockedInputs} onChange={e => edit(() => setModelId(e.target.value))}><option value="">请选择已导入的原权重模型</option>{modelId && !textModels.some(model => model.id === modelId) && <option value={modelId} disabled>已保存检查模型 · {modelId}</option>}{textModels.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
      <p className="muted">当前支持已适配的 Qwen2.5 文本基座分词资料；检查不加载模型权重，不进行训练。</p>
      <div className="two-fields" style={{ alignItems: 'start' }}><label>最大序列长度<input aria-label="划分最大序列长度" type="number" min={32} max={2048} step={1} value={maxSequence} disabled={lockedInputs} onChange={e => edit(() => setMaxSequence(e.target.value))} /><small>32–2048；与之后的训练配置一致。</small></label><label>固定划分种子<input aria-label="固定划分种子" type="number" min={0} max={4294967295} step={1} value={seed} disabled={lockedInputs} onChange={e => edit(() => setSeed(e.target.value))} /><small>同一输入、参数与种子可重现划分。</small></label></div>
      <label>验证集比例（%）<input aria-label="验证集比例（%）" type="number" min={0.01} max={99.99} step={0.01} value={validationPercent} disabled={lockedInputs} onChange={e => edit(() => setValidationPercent(e.target.value))} /><small>按来源组分配；两侧都必须保留有效样本。</small></label>
      {!plan && !pending && <Button primary busy={working} disabled={!inputValid} onClick={prepare}>检查并预览划分</Button>}
      {plan && !stale && <section className="review-box" aria-label="数据划分预览"><div className="section-title"><h3>本次划分预览</h3><Badge>{stateLabels[plan.status]}</Badge></div>
        {active.has(plan.status) && <p role="status">{plan.status === 'cancelling' ? '等待检查进程确认停止。' : '正在检查有效监督内容和来源组，请稍候。可以取消检查。'}</p>}
        {plan.counts && <DatasetSplitSummary counts={plan.counts} validationFractionBps={plan.validation_fraction_bps} />}
        {plan.preview && <PreviewEvidence preview={plan.preview} />}
        {plan.blocking.map((issue, index) => <ErrorNotice key={index} message={`${issue.line ? `第 ${issue.line} 行：` : ''}${issue.message}`} />)}
        {plan.warnings.map((issue, index) => <p className="warning" key={index}>{issue.line ? `第 ${issue.line} 行：` : ''}{issue.message}</p>)}
        {plan.status === 'recovery_required' && <p className="warning">上次检查已中断，不会自动重跑。可以取消旧计划，或保留输入新建预览。</p>}
        {plan.status === 'ready' && <><p>应用将登记两个新数据集和来源证明，不会修改原件或自动选择训练草稿。</p><Button primary busy={working} disabled={Boolean(pending) || Boolean(error) || !applicable(plan)} onClick={() => void execute({ kind: 'apply', path: '/datasets/splits', body: { plan_id: plan.id, plan_digest: plan.plan_digest }, key: crypto.randomUUID() })}>应用划分，生成新版本</Button></>}
        {!['applied', 'cancelled'].includes(plan.status) && <Button busy={working} disabled={Boolean(pending) || plan.status === 'cancelling'} onClick={() => void execute({ kind: 'cancel', path: `/datasets/split-plans/${encodeURIComponent(plan.id)}/cancel`, body: {}, key: crypto.randomUUID() })}>取消本次检查与预览</Button>}
        {['blocked', 'failed', 'cancelled', 'recovery_required'].includes(plan.status) && !pending && <Button busy={working} onClick={() => edit(() => {})}>保留参数，重新预览</Button>}
      </section>}
    </div>}
    {dataset.dataset_split_id && !split && !error && !stale && <p role="status">正在读取划分与子集记录…</p>}
    <ErrorNotice message={stale ? staleMessage : error} />
    {(stale || error) && (plan || dataset.dataset_split_id) && <Button disabled={working} onClick={retryRead}>重新读取划分</Button>}
    {pending && !working && !stale && <Button primary onClick={() => void execute(pending)}>重试上次操作</Button>}
    {stale && !plan && !dataset.dataset_split_id && <Button onClick={() => { if (pending) { void execute(pending); return; } generation.current += 1; scope.current = null; setBusy(false); setError(''); }}>保留输入，重新检查</Button>}
  </Dialog>;
}
