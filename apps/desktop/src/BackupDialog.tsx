import { useEffect, useRef, useState } from 'react';
import { Database, FolderOpen, FileCheck2 } from 'lucide-react';
import { api, collection, mergeRecords, canPickFile, errorMessage, pickExportDirectory, pickImport, useRestoredLibrary, type ImportSelection } from './api';
import { Badge, Button, Dialog, Empty, ErrorNotice, formatDate, readableSize } from './ui';

type BackupRecord = { id: string; backup_path: string; created_at: string; file_count: number; total_bytes: number; manifest_digest: string; contains_asset_files: boolean };
type RestorePlan = { id: string; plan_digest: string; manifest_digest: string; can_restore: boolean; blocking: { message: string }[]; file_count: number; total_bytes: number; restored_path: string; changes_current_library: boolean; evidence_policy: string };
type RestoreRecord = { id: string; state: string; restored_path: string; file_count: number; changes_current_library: boolean; message: string; verified?: boolean; verification_required?: boolean };

export default function BackupDialog({ onClose, onLibraryChanged, onBeforeBackup, onLibrarySwitchStart, onLibrarySwitchFailed }: { onClose: () => void; onLibraryChanged: () => void; onBeforeBackup?: () => Promise<void>; onLibrarySwitchStart?: () => void | Promise<void>; onLibrarySwitchFailed?: () => void }) {
  const [tab, setTab] = useState<'backup' | 'restore'>('backup');
  const [backups, setBackups] = useState<BackupRecord[]>([]); const [restores, setRestores] = useState<RestoreRecord[]>([]);
  const [source, setSource] = useState<ImportSelection>({ path: '' }); const [target, setTarget] = useState<ImportSelection>({ path: '' });
  const [plan, setPlan] = useState<RestorePlan | null>(null); const [restored, setRestored] = useState<RestoreRecord | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [backupCursor, setBackupCursor] = useState<string | null>(); const [restoreCursor, setRestoreCursor] = useState<string | null>();
  const backupKey = useRef<string | null>(null); const restoreKey = useRef<string | null>(null);
  useEffect(() => { let live = true; void Promise.all([collection<BackupRecord>('/backups'), collection<RestoreRecord>('/restores')]).then(([b, r]) => { if (live) { setBackups(b.items); setRestores(r.items); setBackupCursor(b.next_cursor); setRestoreCursor(r.next_cursor); } }).catch(e => { if (live) setError(errorMessage(e)); }); return () => { live = false; }; }, []);
  async function more(which: 'backups' | 'restores') {
    const cursor = which === 'backups' ? backupCursor : restoreCursor;
    if (!cursor || busy) return;
    setBusy(true); setError('');
    try {
      if (which === 'backups') { const page = await collection<BackupRecord>('/backups', cursor); setBackups(items => mergeRecords(items, page.items)); setBackupCursor(page.next_cursor); }
      else { const page = await collection<RestoreRecord>('/restores', cursor); setRestores(items => mergeRecords(items, page.items)); setRestoreCursor(page.next_cursor); }
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function createBackup() {
    setBusy(true); setError(''); setNotice(''); backupKey.current ||= crypto.randomUUID();
    try { await onBeforeBackup?.(); const result = await api<BackupRecord>('POST', '/backups', undefined, backupKey.current); setBackups(items => [result, ...items.filter(item => item.id !== result.id)]); backupKey.current = null; setNotice('数据库、引用资产和原运行记录已完整备份。'); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  function edited() { setPlan(null); setRestored(null); restoreKey.current = null; setError(''); }
  async function choose(which: 'source' | 'target') {
    setBusy(true); setError('');
    try { const value = which === 'source' ? await pickImport('backup') : await pickExportDirectory(); if (value) { if (which === 'source') setSource(value); else setTarget(value); edited(); } }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function inspect() {
    setBusy(true); setError('');
    try { setPlan(await api<RestorePlan>('POST', '/restore-plans', { backup_path: source.path, backup_grant_id: source.grant_id, target_dir: target.path, target_grant_id: target.grant_id })); restoreKey.current = null; }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function restore() {
    if (!plan?.can_restore) return; setBusy(true); setError(''); restoreKey.current ||= crypto.randomUUID();
    try { const result = await api<RestoreRecord>('POST', '/restores', { plan_id: plan.id, plan_digest: plan.plan_digest }, restoreKey.current); setRestored(result); setRestores(items => [result, ...items.filter(item => item.id !== result.id)]); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function switchLibrary() {
    if (!restored || restored.state !== 'succeeded' || !restored.verified) return; setBusy(true); setError('');
    let started = false;
    try { await onLibrarySwitchStart?.(); started = true; await useRestoredLibrary(restored.id); onLibraryChanged(); onClose(); }
    catch (e) { if (started) onLibrarySwitchFailed?.(); setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function openRestore(id: string) {
    setBusy(true); setError('');
    try { setRestored(await api<RestoreRecord>('GET', `/restores/${id}`)); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title="备份与恢复" wide onClose={onClose} preventClose={busy}><div className="tabs" role="tablist" aria-label="备份与恢复操作"><button disabled={busy} role="tab" aria-selected={tab === 'backup'} onClick={() => { setTab('backup'); setError(''); }}>创建与查看备份</button><button disabled={busy} role="tab" aria-selected={tab === 'restore'} onClick={() => { setTab('restore'); setError(''); }}>从备份恢复</button></div>
    {tab === 'backup' ? <div className="form-stack backup-content"><p className="muted">保存数据库、引用的模型与数据、适配器、原运行证据及停止后的下载缓存。请先完成任务或停止下载；备份期间可以查看记录，新的写入操作会暂时等待。</p><Button primary busy={busy} onClick={createBackup}><Database size={16} />创建完整备份</Button>{notice && <p className="export-success">{notice}</p>}{backups.length ? backups.map(item => <section className="review-box" key={item.id}><div className="section-title"><h3>{formatDate(item.created_at)} 备份</h3><Badge>{item.contains_asset_files ? '包含资产文件' : '仅元数据'}</Badge></div><p className="muted">{item.file_count} 个文件 · {readableSize(item.total_bytes)}</p><p className="break-anywhere muted">{item.backup_path}</p><Button disabled={busy || !item.contains_asset_files} onClick={() => { setSource({ path: item.backup_path }); edited(); setTab('restore'); }}>使用此备份恢复</Button></section>) : <Empty title="尚无完整备份">完成首次试用后，可以在这里保存一份可恢复的本机副本。</Empty>}{backupCursor && <Button busy={busy} onClick={() => void more('backups')}>加载更多备份记录</Button>}</div> : <div className="form-stack backup-content">
      {restored ? <section className="review-box"><div className="section-title"><h3>{restored.state === 'succeeded' && restored.verified ? '已恢复到独立目录' : '恢复尚未完成'}</h3><Badge tone={restored.state === 'succeeded' && restored.verified ? 'good' : ''}>{restored.state === 'succeeded' && restored.verified ? '文件已校验' : '待核对'}</Badge></div><p className="break-anywhere">{restored.restored_path}</p><p className="muted">当前工作库仍在使用。切换后将显示恢复库中的项目与历史，原库保留。</p>{canPickFile() && <Button primary busy={busy} disabled={restored.state !== 'succeeded' || !restored.verified} onClick={switchLibrary}>切换到恢复的工作库</Button>}<Button disabled={busy} onClick={() => { setRestored(null); setPlan(null); }}>恢复另一份备份</Button></section> : <><p className="muted">先检查备份完整性与保存位置。恢复会创建独立的新目录，完成后可选择切换工作库。</p><fieldset className="task-fields" disabled={busy}><label>备份包目录<div className="input-action"><input aria-label="备份包目录" readOnly={canPickFile()} value={source.path} onChange={e => { setSource({ path: e.target.value }); edited(); }} />{canPickFile() && <Button onClick={() => choose('source')}><FolderOpen size={15} />选择备份</Button>}</div></label><label>恢复保存目录<div className="input-action"><input aria-label="恢复保存目录" readOnly={canPickFile()} value={target.path} onChange={e => { setTarget({ path: e.target.value }); edited(); }} />{canPickFile() && <Button onClick={() => choose('target')}><FolderOpen size={15} />选择位置</Button>}</div></label></fieldset>{plan ? <section className="review-box" aria-label="恢复范围检查"><h3>恢复范围已检查</h3><dl className="facts"><div><dt>文件范围</dt><dd>{plan.file_count} 个文件 · {readableSize(plan.total_bytes)}</dd></div><div><dt>新工作库目录</dt><dd>{plan.restored_path}</dd></div></dl><p className="muted">{plan.evidence_policy}</p>{plan.blocking.map((item, index) => <ErrorNotice key={index} message={item.message} />)}<Button primary busy={busy} disabled={!plan.can_restore || plan.blocking.length > 0 || plan.changes_current_library} onClick={restore}>恢复到新目录</Button></section> : <Button primary busy={busy} disabled={!source.path || !target.path} onClick={inspect}><FileCheck2 size={15} />检查恢复范围</Button>}</>}
      {!restored && restores.length > 0 && <details><summary>已恢复的工作库</summary>{restores.map(item => <section className="review-box" key={item.id}><p className="break-anywhere muted">{item.restored_path}</p><Button disabled={busy} onClick={() => openRestore(item.id)}>{item.verification_required ? '核实恢复结果' : '查看恢复结果'}</Button></section>)}</details>}
      {restoreCursor && <Button busy={busy} onClick={() => void more('restores')}>加载更多恢复记录</Button>}
    </div>}<ErrorNotice message={error} />{busy && <p className="muted">正在校验或复制文件，大型模型需要更长时间。请保持此窗口打开。</p>}
  </Dialog>;
}
