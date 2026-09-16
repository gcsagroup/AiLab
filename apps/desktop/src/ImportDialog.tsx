import { useEffect, useRef, useState } from 'react';
import { FolderOpen, ArrowRight, FileCheck2 } from 'lucide-react';
import { api, canPickFile, errorMessage, pickImport, type ImportKind, type ImportSelection } from './api';
import { Button, Dialog, ErrorNotice, readableSize } from './ui';
import type { ImportPlan } from './types';
import { hasKnownModelBoundary, ModelExecutionNotice } from './ModelExecutionNotice';

function modelLoadingLabel(plan: ImportPlan): string | null {
  if (plan.trust_class === 'restricted_weights' && plan.loader === 'mlx_lm.local_restricted') return '受限权重 · 本机 MLX 加载器';
  if (plan.trust_class === 'restricted_weights' && plan.loader === 'diffusers.fixed_local_safetensors') return '受限权重 · 固定媒体 safetensors 加载器';
  if (plan.trust_class === 'restricted_official_torch' && plan.loader === 'kokoro.fixed_official_weights_only_cpu') return '固定官方权重 · Kokoro 受限加载器';
  return null;
}

export default function ImportDialog({ kind, projectId, onClose, onImported }: { kind: ImportKind; projectId: string; onClose: () => void; onImported: () => void }) {
  const label = kind === 'model' ? '模型' : kind === 'material' ? '图片素材' : '数据集';
  const endpoint = kind === 'model' ? 'models' : kind === 'material' ? 'materials' : 'datasets';
  const [selection, setSelection] = useState<ImportSelection>({ path: '' });
  const [name, setName] = useState('');
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const loadingLabel = plan && kind === 'model' ? modelLoadingLabel(plan) : null;
  const modelBoundaryKnown = kind !== 'model' || Boolean(plan && loadingLabel && hasKnownModelBoundary(plan.execution_boundary));
  const importKey = useRef<string | null>(null);
  const live = useRef(true);
  const identity = `${projectId}:${kind}`;
  const scope = useRef({ identity });
  if (scope.current.identity !== identity) scope.current = { identity };
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  function capture() { const started = scope.current; return () => live.current && scope.current === started; }
  async function choose() {
    const isCurrent = capture();
    try {
      const result = await pickImport(kind);
      if (isCurrent() && result) { setSelection(result); setPlan(null); setError(''); }
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
  }
  async function inspect() {
    const isCurrent = capture();
    setBusy(true); setError('');
    try {
      const result = await api<ImportPlan>('POST', `/${endpoint}/import-plans`, { ...selection, name: name.trim() || undefined, project_id: projectId, ...(kind === 'image-dataset' ? { schema: 'image_caption_v1' } : {}) });
      if (isCurrent()) { setPlan(result); importKey.current = null; }
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  async function confirm() {
    if (!plan || plan.can_import !== true || !modelBoundaryKnown) return;
    const isCurrent = capture();
    setBusy(true); setError('');
    try {
      importKey.current ||= crypto.randomUUID();
      await api('POST', `/${endpoint}/imports`, { plan_id: plan.plan_id || plan.id, manifest_digest: plan.manifest_digest }, importKey.current);
      if (isCurrent()) onImported();
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  const issues = plan?.blocking || (plan?.issues || []).filter(issue => issue.severity !== 'warning');
  return <Dialog title={`导入本机${label}`} onClose={onClose} preventClose={busy}>
    <p className="muted">{kind === 'model' ? '选择完整模型文件夹。语言模型需有权重、配置和分词器；媒体模型需为已准备的固定组合，先检查格式与完整性。' : kind === 'material' ? '选择 PNG 静态图片，支持非隔行的 8-bit RGB/RGBA，最多 32 MiB。检查后作为视频的独立输入素材保存。' : kind === 'image-dataset' ? '选择同时包含 dataset.json 和 1—8 张 512×512 RGB PNG 的目录。每张图需有描述、来源说明和摘要；只复制清单引用的文件。' : '选择 JSONL 数据文件，检查样本结构后保存为独立数据版本。'}原文件会保留。</p>
    <div className="form-stack">
      <label>名称（可选）<input disabled={busy} value={name} onChange={e => { setName(e.target.value); setPlan(null); }} placeholder={`沿用${label}文件名`} /></label>
      <label>{label}位置<div className="input-action"><input aria-label={`${label}文件路径`} disabled={busy} readOnly={canPickFile()} value={selection.path} onChange={e => { setSelection({ path: e.target.value }); setPlan(null); }} placeholder={canPickFile() ? '点击选择本机文件' : '输入开发环境已授权目录内的绝对路径'} />{canPickFile() && <Button onClick={choose} disabled={busy}><FolderOpen size={16} />选择</Button>}</div></label>
      {!plan && <Button primary onClick={inspect} busy={busy} disabled={!selection.path.trim()}><FileCheck2 size={16} />检查{label}</Button>}
      {plan && <section className="review-box" aria-label="导入检查结果"><h3>导入检查</h3><dl className="facts"><div><dt>名称</dt><dd>{String(plan.name || name || label)}</dd></div><div><dt>{kind === 'model' ? '模型格式' : '数据结构'}</dt><dd>{String(plan.detected_format || plan.format || plan.schema || '已检查')}</dd></div>{plan.file_count !== undefined && <div><dt>文件数</dt><dd>{plan.file_count}</dd></div>}{plan.total_bytes !== undefined && <div><dt>占用空间</dt><dd>{readableSize(plan.total_bytes)}</dd></div>}{plan.sample_count !== undefined && <div><dt>样本数</dt><dd>{plan.sample_count}</dd></div>}</dl>
        {kind === 'model' && (modelBoundaryKnown ? <ModelExecutionNotice loadingLabel={loadingLabel!} /> : <ErrorNotice message="模型加载信任或权限说明缺失、未知，暂不能确认导入。请更新应用后重新检查。" />)}
        {issues.map((issue, i) => <ErrorNotice key={i} message={issue.message} />)}{(plan.warnings || []).map((warning, i) => <p key={i} className="warning">{warning.message}</p>)}<Button primary busy={busy} onClick={confirm} disabled={plan.can_import !== true || issues.length > 0 || !modelBoundaryKnown}>确认导入<ArrowRight size={16} /></Button></section>}
      {Boolean(plan?.selection_scope) && <p className="muted">{String(plan?.selection_scope)}</p>}
      <ErrorNotice message={error} />
    </div>
  </Dialog>;
}
