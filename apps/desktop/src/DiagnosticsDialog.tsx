import { useEffect, useRef, useState } from 'react';
import { api, canPickFile, errorMessage, pickExportDirectory, type ImportSelection } from './api';
import type { Attempt } from './types';
import { Badge, Button, Dialog, ErrorNotice, formatDate, readableSize, stateNames } from './ui';

type Preview = { id: string; status: string; included: string[]; excluded: string[]; files: { path: string; size: number; sha256: string }[]; total_bytes: number; archive_bytes: number; archive_sha256: string; diagnostics: Record<string, unknown>; can_export: boolean; can_cancel: boolean; saved_path?: string; error?: { code: string; message: string } };
type ExportCommand = { body: { preview_id: string; target_dir: string; grant_id?: string }; key: string };
const names: Record<string, string> = { ready: '范围已冻结', writing: '正在保存', succeeded: '已保存并核对', registration_pending: '文件状态待核实', cancelled: '已取消', failed: '导出未完成' };
export default function DiagnosticsDialog({ projectId, attempts, onClose }: { projectId: string; attempts: Attempt[]; onClose: () => void }) {
  const [scope, setScope] = useState(projectId ? 'project' : 'all'); const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null); const [target, setTarget] = useState<ImportSelection>({ path: '' });
  const [busy, setBusy] = useState(false); const [cancelling, setCancelling] = useState(false); const [error, setError] = useState('');
  const pending = useRef<ExportCommand | null>(null); const pendingCancel = useRef<{ previewId: string; key: string } | null>(null);
  const receipt = useRef<Preview | null>(null); const generation = useRef(0); const live = useRef(true); const working = useRef(false); const cancelWorking = useRef(false);
  const terminal = (status: string) => ['succeeded', 'registration_pending', 'cancelled', 'failed'].includes(status);
  function accept(value: Preview) {
    const previous = receipt.current;
    // 取消/发布回执一旦确认，较晚的 ready/writing 响应不能把界面倒退为进行中。
    if (previous?.id === value.id && ((terminal(previous.status) && !terminal(value.status)) || (previous.status === 'registration_pending' && value.status === 'succeeded'))) return previous;
    receipt.current = value; setPreview(value);
    if (terminal(value.status)) { pending.current = null; pendingCancel.current = null; }
    return value;
  }
  function codeOf(value: unknown): string | undefined {
    if (typeof value === 'string') { try { return codeOf(JSON.parse(value)); } catch { return undefined; } }
    return (value as { error?: { code?: string } })?.error?.code;
  }
  function rejected(value: unknown) { const code = codeOf(value); return code && !/^(CONTROL_|LOCAL_BRIDGE|INTERNAL_|NETWORK_|UNKNOWN)/.test(code); }
  function reset() { generation.current++; receipt.current = null; setPreview(null); setError(''); pending.current = null; pendingCancel.current = null; }
  useEffect(() => {
    live.current = true; reset(); setScope(projectId ? 'project' : 'all'); setSelected([]); setTarget({ path: '' });
    working.current = false; cancelWorking.current = false; setBusy(false); setCancelling(false);
    return () => { live.current = false; generation.current++; };
  }, [projectId]);
  const locked = busy || cancelling || Boolean(pending.current) || Boolean(pendingCancel.current);
  const current = (epoch: number) => live.current && generation.current === epoch;
  async function inspect() {
    if (working.current || locked) return;
    const epoch = generation.current; working.current = true; setBusy(true); setError('');
    try { const value = await api<Preview>('POST', '/diagnostics/previews', { project_id: scope === 'project' ? projectId : null, attempt_ids: selected }); if (current(epoch)) accept(value); }
    catch (e) { if (current(epoch)) setError(errorMessage(e)); } finally { if (current(epoch)) { working.current = false; setBusy(false); } }
  }
  async function choose() {
    if (working.current || locked) return;
    const epoch = generation.current; working.current = true; setBusy(true); setError('');
    try { const value = await pickExportDirectory(); if (current(epoch) && value) setTarget(value); }
    catch (e) { if (current(epoch)) setError(errorMessage(e)); } finally { if (current(epoch)) { working.current = false; setBusy(false); } }
  }
  async function exportFile() {
    if (!preview || !target.path || working.current || cancelWorking.current || pendingCancel.current) return;
    pending.current ||= { body: { preview_id: preview.id, target_dir: target.path, ...(target.grant_id ? { grant_id: target.grant_id } : {}) }, key: crypto.randomUUID() };
    const command = pending.current; const epoch = generation.current;
    working.current = true; setBusy(true); setError('');
    try { const value = await api<Preview>('POST', '/diagnostics/exports', command.body, command.key); if (current(epoch)) accept(value); }
    catch (e) { if (current(epoch) && !terminal(receipt.current?.status || '')) { if (rejected(e)) pending.current = null; setError(errorMessage(e)); } } finally { if (current(epoch)) { working.current = false; setBusy(false); } }
  }
  async function cancel() {
    if (!preview || cancelWorking.current) return;
    pendingCancel.current ||= { previewId: preview.id, key: crypto.randomUUID() };
    const command = pendingCancel.current; const epoch = generation.current;
    cancelWorking.current = true; setCancelling(true); setError('');
    try { const value = await api<Preview>('POST', `/diagnostics/previews/${command.previewId}/cancel`, {}, command.key); if (current(epoch)) { accept(value); pendingCancel.current = null; } }
    catch (e) {
      if (!current(epoch)) return;
      setError(errorMessage(e));
      if (codeOf(e) === 'DIAGNOSTICS_ALREADY_PUBLISHED') {
        try { const value = await api<Preview>('GET', `/diagnostics/previews/${command.previewId}`); if (current(epoch)) accept(value); }
        catch (failure) { if (current(epoch)) setError(errorMessage(failure)); }
      } else if (rejected(e)) pendingCancel.current = null;
    } finally { if (current(epoch)) { cancelWorking.current = false; setCancelling(false); } }
  }
  async function refresh() {
    if (!preview || working.current) return;
    const epoch = generation.current; const previewId = preview.id;
    working.current = true; setBusy(true); setError('');
    try { const value = await api<Preview>('GET', `/diagnostics/previews/${previewId}`); if (current(epoch)) accept(value); }
    catch (e) { if (current(epoch)) setError(errorMessage(e)); } finally { if (current(epoch)) { working.current = false; setBusy(false); } }
  }
  return <Dialog title="导出诊断摘要" wide onClose={onClose} preventClose={locked}><p>先查看将保存的摘要，再选择本机位置。诊断文件由你自行保管和分享。</p>
    <fieldset className="task-fields" disabled={locked || Boolean(preview)}><label>诊断范围<select aria-label="诊断范围" value={scope} onChange={e => { setScope(e.target.value); reset(); }}><option value="project" disabled={!projectId}>当前项目</option><option value="all">整个工作库</option></select></label>
      <details><summary>附加指定运行的状态（最多 20 次）</summary><p className="muted">下面列出当前项目的运行；只保存状态和已知错误代码。</p>{attempts.map(item => <label className="check-row" key={item.id}><input type="checkbox" checked={selected.includes(item.id)} disabled={selected.length >= 20 && !selected.includes(item.id)} onChange={e => setSelected(values => e.target.checked ? [...values, item.id] : values.filter(id => id !== item.id))} />{formatDate(item.created_at)} · {stateNames[item.state] || item.state} · {item.id.slice(-8)}</label>)}</details>
    </fieldset>
    {!preview ? <Button primary busy={busy} onClick={inspect}>预览诊断范围</Button> : <section className="review-box" aria-label="诊断范围预览"><div className="section-title"><h3>本次诊断内容</h3><Badge>{names[preview.status] || preview.status}</Badge></div><strong>包含</strong><ul>{preview.included.map(item => <li key={item}>{item}</li>)}</ul><strong>不包含</strong><ul>{preview.excluded.map(item => <li key={item}>{item}</li>)}</ul><p>{preview.files.length} 个文件 · ZIP {readableSize(preview.archive_bytes)}</p><details><summary>查看实际摘要与文件清单</summary><pre>{JSON.stringify(preview.diagnostics, null, 2)}</pre>{preview.files.map(file => <p key={file.path}>{file.path} · {readableSize(file.size)}</p>)}</details>
      {preview.can_export && <label>诊断保存目录<div className="input-action"><input aria-label="诊断保存目录" readOnly={canPickFile()} disabled={locked} value={target.path} onChange={e => setTarget({ path: e.target.value })} />{canPickFile() && <Button disabled={locked} onClick={choose}>选择位置</Button>}</div></label>}
      <ErrorNotice message={preview.error?.message || ''} />{preview.saved_path && <p className="break-anywhere">{preview.saved_path}</p>}{preview.status === 'succeeded' && <p role="status">诊断 ZIP 已保存，文件完整性已核对。</p>}
      <div className="dialog-actions">{(preview.can_export || pending.current) && <Button primary busy={busy} disabled={!target.path || cancelling || Boolean(pendingCancel.current)} onClick={exportFile}>{pending.current ? '重试原导出请求' : '保存诊断 ZIP'}</Button>}{(preview.can_cancel || pendingCancel.current) && <Button busy={cancelling} onClick={cancel}>{pendingCancel.current && !cancelling ? '重试原取消请求' : '取消此次诊断导出'}</Button>}{(pending.current || pendingCancel.current) && !busy && <Button disabled={cancelling} onClick={refresh}>读取原导出状态</Button>}{!locked && <Button onClick={reset}>重新选择范围</Button>}</div>
    </section>}<ErrorNotice message={error} />{pending.current && !busy && <p className="warning">导出响应尚未确认。重试保留原请求编号，不会生成第二份文件。</p>}{pendingCancel.current && !cancelling && <p className="warning">取消响应尚未确认。请读取当前状态，或使用原请求重试取消。</p>}
  </Dialog>;
}
