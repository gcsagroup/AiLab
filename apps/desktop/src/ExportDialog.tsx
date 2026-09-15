import { useContext, useEffect, useRef, useState } from 'react';
import { Check, Download, FolderOpen, Square } from 'lucide-react';
import { api, canPickFile, errorMessage, pickExportDirectory, type ImportSelection } from './api';
import { Badge, Button, Dialog, ErrorNotice, readableSize, stateNames } from './ui';
import { LibraryReadContext } from './LibraryReadContext';

export type ExportObject = { work_revision_id?: string | null; type: 'model' | 'adapter' | 'work' | 'report' | 'dataset-split'; id: string; name: string };
type ExportPlan = { id: string; plan_digest: string; can_export: boolean; blocking: { message: string }[]; disclosures?: string[]; total_bytes: number; file_count: number; target_dir: string; files: { path: string; size: number; sha256: string }[]; dependencies: { type: string; id: string; included: boolean; description: string }[] };
export type ExportRecord = { id: string; task_id: string; attempt_id: string; object_type: ExportObject['type']; object_id: string; object_name?: string; work_revision_id?: string | null; selection_warning?: string; state: string; state_version: number; progress?: number | null; verified_path?: string; error?: { message: string }; allowed_actions?: string[] };
const terminal = new Set(['succeeded', 'failed', 'cancelled']);

export default function ExportDialog({ object, projectId, initial, onClose, onChanged }: { object: ExportObject; projectId: string; initial?: ExportRecord; onClose: () => void; onChanged: () => void }) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [selection, setSelection] = useState<ImportSelection>({ path: '' });
  const [plan, setPlan] = useState<ExportPlan | null>(null);
  const [record, setRecord] = useState<ExportRecord | null>(initial || null);
  const [workSelection, setWorkSelection] = useState(initial ? initial.work_revision_id : object.work_revision_id ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitKey = useRef<string | null>(null);
  const cancelKeys = useRef(new Map<number, string>());
  const reconcileKeys = useRef(new Map<string, string>()); const reconcileInFlight = useRef(false);
  const live = useRef(true); const scope = useRef<(() => boolean) | null>(null); const [refresh, setRefresh] = useState(0);
  const identity = `${projectId}:${object.type}:${object.id}:${object.work_revision_id || ''}`;
  const identityRef = useRef(identity); identityRef.current = identity;
  const stale = Boolean(scope.current && !scope.current()); const working = busy && !stale;
  const selectedRevision = record ? record.work_revision_id : workSelection;
  const unknownSelection = object.type === 'work' && selectedRevision !== null && !(typeof selectedRevision === 'string' && selectedRevision.trim());
  const selectionWarning = unknownSelection ? record?.selection_warning || initial?.selection_warning || '无法核实这条历史导出当时选择的作品版本。请回到作品，明确选择原版或人工修订后再导出。' : '';
  function capture() { const libraryCurrent = captureLibraryRead(); return () => live.current && identityRef.current === identity && libraryCurrent(); }
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  function acceptRecord(value: ExportRecord) { setRecord(previous => previous?.id === value.id && previous.state_version > value.state_version ? previous : value); }
  useEffect(() => {
    if (!record) return;
    if (scope.current && !scope.current()) return;
    let current = true; const captured = capture(); const isCurrent = () => current && captured(); scope.current = captured;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api<ExportRecord>('GET', `/exports/${record!.id}`);
        if (!isCurrent()) return;
        acceptRecord(current); setError('');
        if (terminal.has(current.state)) onChanged();
        else timer = setTimeout(poll, 700);
      } catch (e) { if (isCurrent()) { setError(errorMessage(e)); timer = setTimeout(poll, 2000); } }
    }
    void poll();
    return () => { current = false; clearTimeout(timer); };
  }, [record?.id, identity, refresh]);
  async function choose() {
    const isCurrent = capture(); scope.current = isCurrent;
    setError('');
    try { const chosen = await pickExportDirectory(); if (isCurrent() && chosen) { setSelection(chosen); setPlan(null); submitKey.current = null; } }
    catch (e) { if (isCurrent()) setError(errorMessage(e)); }
  }
  async function inspect() {
    if (unknownSelection) { setError(selectionWarning); return; }
    const isCurrent = capture(); scope.current = isCurrent;
    setBusy(true); setError('');
    try {
      const prepared = await api<ExportPlan>('POST', '/exports/prepare', { project_id: projectId, object_type: object.type, object_id: object.id, ...(object.type === 'work' ? { work_revision_id: selectedRevision } : {}), target_dir: selection.path, grant_id: selection.grant_id, include_base: false });
      if (!isCurrent()) return;
      setPlan(prepared);
      submitKey.current = null;
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  async function submit(retryAfterInvalidation = false) {
    if (stale && !retryAfterInvalidation) return;
    if (!plan?.can_export) return;
    const isCurrent = capture(); scope.current = isCurrent;
    setBusy(true); setError('');
    submitKey.current ||= crypto.randomUUID();
    try { const exported = await api<ExportRecord>('POST', '/exports', { plan_id: plan.id, plan_digest: plan.plan_digest }, submitKey.current); if (isCurrent()) { acceptRecord(exported); onChanged(); } }
    catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  async function cancel() {
    if (!record || stale) return;
    const isCurrent = capture(); scope.current = isCurrent;
    setBusy(true); setError('');
    if (!cancelKeys.current.has(record.state_version)) cancelKeys.current.set(record.state_version, crypto.randomUUID());
    try {
      await api('POST', `/attempts/${record.attempt_id}/cancel`, { expected_state_version: record.state_version }, cancelKeys.current.get(record.state_version));
      if (!isCurrent()) return;
      const updated = await api<ExportRecord>('GET', `/exports/${record.id}`);
      if (isCurrent()) acceptRecord(updated);
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (isCurrent()) setBusy(false); }
  }
  async function reconcile() {
    if (!record || stale || reconcileInFlight.current || !record.allowed_actions?.includes('reconcile')) return;
    const isCurrent = capture(); scope.current = isCurrent;
    const key = `${record.attempt_id}:${record.state_version}`;
    if (!reconcileKeys.current.has(key)) reconcileKeys.current.set(key, crypto.randomUUID());
    reconcileInFlight.current = true; setBusy(true); setError('');
    let failure = '';
    try {
      try { await api('POST', `/attempts/${record.attempt_id}/reconcile`, { expected_state_version: record.state_version }, reconcileKeys.current.get(key)); }
      catch (e) { failure = errorMessage(e); }
      if (!isCurrent()) return;
      const updated = await api<ExportRecord>('GET', `/exports/${record.id}`);
      if (!isCurrent()) return;
      acceptRecord(updated); setError(terminal.has(updated.state) ? '' : failure); onChanged();
    } catch (e) { if (isCurrent()) setError(failure ? `${failure} 当前导出状态暂未读回：${errorMessage(e)}` : errorMessage(e)); }
    finally { reconcileInFlight.current = false; if (isCurrent()) setBusy(false); }
  }
  return <Dialog title={`导出${object.name}`} wide onClose={onClose} preventClose={working}>
    <p className="muted">保存独立文件包及来源清单。导出只读取已有产物，不重新运行模型。</p>
    {object.type === 'dataset-split' && <p className="muted">本次包含原始数据、训练与验证两个子集及来源组证明。留出验证子集用于隔离检查，本包未包含验证损失结果；导出不会启动训练或重新划分。</p>}
    {object.type === 'work' && (unknownSelection ? <ErrorNotice message={selectionWarning} /> : <p className="muted">{selectedRevision ? '已选择固定人工修订：原媒体与修订文字分别导出，原生成配方保留。' : '已选择原生成版本；如需导出修订文字或字幕，请从作品的修订记录选择版本。'}</p>)}
    {stale ? <><ErrorNotice message="工作库读取已失效，保存位置保留。请重新核实导出。" /><Button onClick={() => { if (record) { scope.current = capture(); setBusy(false); setError(''); setRefresh(value => value + 1); } else if (plan && submitKey.current) void submit(true); else void inspect(); }}>重新核实导出</Button></> : record ? <section className="export-result"><div className="section-title"><h3>导出记录</h3><Badge tone={record.state === 'succeeded' ? 'good' : record.state === 'failed' ? 'danger' : ''}>{stateNames[record.state] || record.state}</Badge></div>
      {record.state === 'succeeded' && record.verified_path ? <><p className="export-success"><Check size={18} />全部文件已写入并通过校验</p><dl className="facts"><div><dt>保存位置</dt><dd>{record.verified_path}</dd></div></dl></> : terminal.has(record.state) ? <p>{record.error?.message || '导出已停止，未登记不完整文件包。'}</p> : <><p>{record.allowed_actions?.includes('reconcile') ? '导出结果待核实。核实会检查原文件包并更新这条记录。' : '正在准备或写入文件。可以关闭此窗口，稍后从任务记录查看。'}</p><ErrorNotice message={record.error?.message || ''} /></>}
      {record.allowed_actions?.includes('cancel') && <Button busy={busy} onClick={cancel}><Square size={14} />取消导出</Button>}
      {record.allowed_actions?.includes('reconcile') && <Button busy={busy} onClick={reconcile}>核实原导出</Button>}
      {terminal.has(record.state) && record.state !== 'succeeded' && <Button busy={busy} disabled={unknownSelection} onClick={() => { setWorkSelection(record.work_revision_id); setRecord(null); setPlan(null); setError(''); }}>重新检查导出</Button>}
      <small className="muted">记录编号：{record.id}</small>
    </section> : <div className="form-stack">
      <label>保存目录<div className="input-action"><input aria-label="导出保存目录" value={selection.path} readOnly={canPickFile()} disabled={busy} onChange={e => { setSelection({ path: e.target.value }); setPlan(null); }} placeholder={canPickFile() ? '选择本机保存目录' : '输入开发环境已授权的导出目录'} />{canPickFile() && <Button disabled={busy} onClick={choose}><FolderOpen size={15} />选择目录</Button>}</div></label>
      {!plan && <Button primary busy={busy} disabled={!selection.path.trim()} onClick={inspect}>检查导出范围</Button>}
      {plan && <section className="review-box" aria-label="导出范围检查"><h3>{object.name}</h3><dl className="facts"><div><dt>文件数</dt><dd>{plan.file_count}</dd></div><div><dt>预计占用</dt><dd>{readableSize(plan.total_bytes)}</dd></div><div><dt>目标目录</dt><dd>{plan.target_dir}</dd></div></dl>
        {plan.dependencies.map(dependency => <p className={dependency.included ? 'muted' : 'warning'} key={`${dependency.type}:${dependency.id}`}>{dependency.description} · {dependency.included ? '包含在本次包内' : '需要另行准备，不包含在本次包内'}</p>)}
        {plan.disclosures?.map((disclosure, index) => <p className="warning" key={index}>{disclosure}</p>)}
        {object.type === 'report' && <p className="muted">本次导出执行证据与配置。质量评测是否通过，以对应评测报告为准。</p>}
        {plan.blocking.map((issue, index) => <ErrorNotice key={index} message={issue.message} />)}
        <details><summary>查看文件清单</summary><ul className="export-file-list">{plan.files.map(file => <li key={file.path}>{file.path}<small>{readableSize(file.size)}</small></li>)}</ul></details>
        <Button primary busy={busy} disabled={!plan.can_export || plan.blocking.length > 0} onClick={() => void submit()}><Download size={16} />开始导出</Button>
      </section>}
    </div>}
    <ErrorNotice message={stale ? '' : error} />
  </Dialog>;
}
