import { useEffect, useState } from 'react';
import { FileCheck2, RotateCcw, Trash2 } from 'lucide-react';
import { api, errorMessage } from './api';
import { Badge, Button, Dialog, Empty, ErrorNotice, formatDate, readableSize } from './ui';

export type CleanupItem = { asset_id: string; source_path: string; trash_path?: string; total_bytes: number; file_count: number; manifest_digest: string; reason: string };
export type CleanupPlan = { id: string; plan_digest: string; data_root: string; items: CleanupItem[]; asset_count: number; file_count: number; total_bytes: number; retained_asset_count: number; skipped: { path: string; reason: string }[]; destination: string; can_execute: boolean; permanent_delete: false; requires_confirmation: true };
export type CleanupRecord = { id: string; state: 'moving' | 'trashed' | 'restoring' | 'restored'; created_at: string; restored_at?: string; total_bytes: number; asset_count: number; file_count: number; items: CleanupItem[]; can_restore: boolean };
type CleanupHistory = { items: CleanupRecord[]; unreadable_records: string[] };
const stateNames = { moving: '移动结果待核实', trashed: '可以恢复', restoring: '恢复结果待核实', restored: '已恢复' };

function AssetList({ items, showTrash = false }: { items: CleanupItem[]; showTrash?: boolean }) {
  return <ol className="cleanup-assets">{items.map((item, index) => <li key={item.asset_id}>
    <div className="section-title"><strong>资产 {index + 1}</strong><span>{item.file_count} 个文件 · {readableSize(item.total_bytes)}</span></div>
    <p className="break-anywhere"><small>原位置</small>{item.source_path}</p>
    {showTrash && item.trash_path && <p className="break-anywhere"><small>回收位置</small>{item.trash_path}</p>}
    <p className="muted">{item.reason}</p>
  </li>)}</ol>;
}

export default function CleanupDialog({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<'plan' | 'history'>('plan');
  const [plan, setPlan] = useState<CleanupPlan | null>(null);
  const [history, setHistory] = useState<CleanupHistory>({ items: [], unreadable_records: [] });
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [uncertain, setUncertain] = useState(false);
  useEffect(() => {
    let live = true;
    void api<CleanupHistory>('GET', '/cleanups').then(value => { if (live) setHistory(value); }).catch(e => { if (live) setError(errorMessage(e)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, []);
  function record(value: CleanupRecord) { setHistory(current => ({ ...current, items: [value, ...current.items.filter(item => item.id !== value.id)] })); }
  async function inspect() {
    setBusy(true); setError(''); setNotice(''); setPlan(null); setUncertain(false);
    try { setPlan(await api<CleanupPlan>('POST', '/cleanup-plans', {})); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function move() {
    if (!plan?.can_execute || plan.permanent_delete) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await api<CleanupRecord>('POST', '/cleanups', { plan_id: plan.id, plan_digest: plan.plan_digest }, `move-${plan.id}`);
      record(value); setPlan(null); setUncertain(false); setTab('history');
      setNotice(value.state === 'restored' ? '此记录中的资产已恢复到原位置。' : '已移入本库回收区，原文件保留，可在这里恢复。');
    } catch (e) {
      setError(errorMessage(e)); setUncertain(true);
      try { setHistory(await api<CleanupHistory>('GET', '/cleanups')); } catch { /* 保留原操作错误及原命令，稍后仍可核实。 */ }
    } finally { setBusy(false); }
  }
  async function restore(item: CleanupRecord) {
    setBusy(true); setError(''); setNotice('');
    try {
      const value = await api<CleanupRecord>('POST', `/cleanups/${item.id}/restore`, {}, `restore-${item.id}`);
      record(value); setPlan(null); setNotice('资产已恢复到原位置，原文件内容保持不变。');
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function refresh() {
    setBusy(true); setError('');
    try { setHistory(await api<CleanupHistory>('GET', '/cleanups')); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title="存储清理与恢复" wide onClose={onClose} preventClose={busy}>
    <p className="muted">先查看当前工作库中无人引用的资产，再决定是否移入回收区。运行记录、已引用资产与本库外文件会保留。</p>
    <div className="tabs" role="tablist" aria-label="存储管理操作">
      <button role="tab" disabled={busy} aria-selected={tab === 'plan'} onClick={() => setTab('plan')}>检查清理范围</button>
      <button role="tab" disabled={busy} aria-selected={tab === 'history'} onClick={() => setTab('history')}>回收区与历史{history.items.length > 0 ? `（${history.items.length}）` : ''}</button>
    </div>
    <div className="form-stack backup-content">
      {notice && <p className="export-success" role="status">{notice}</p>}
      <ErrorNotice message={error} />
      {tab === 'plan' ? <>
        {!plan ? <Empty title="先检查，再决定" action={<Button primary busy={busy} onClick={inspect}><FileCheck2 size={16} />检查可清理资产</Button>}>检查只生成范围清单。请先完成运行、备份或工作库切换。</Empty> : <section className="review-box" aria-label="已检查的清理范围">
          <div className="section-title"><h3>{plan.asset_count ? '清理范围已检查' : '没有可清理资产'}</h3><Badge>{plan.asset_count} 个资产</Badge></div>
          <dl className="facts"><div><dt>当前工作库</dt><dd>{plan.data_root}</dd></div><div><dt>本次范围</dt><dd>{plan.file_count} 个文件 · {readableSize(plan.total_bytes)}</dd></div><div><dt>保留资产</dt><dd>{plan.retained_asset_count} 个已有引用的资产</dd></div><div><dt>回收位置</dt><dd>{plan.destination}</dd></div></dl>
          {plan.items.length > 0 ? <AssetList items={plan.items} /> : <p className="muted">当前没有符合条件的无引用资产，无需清理。</p>}
          {plan.skipped.length > 0 && <details><summary>{plan.skipped.length} 个对象未纳入清理</summary>{plan.skipped.map(item => <p className="break-anywhere muted" key={item.path}>{item.path}<br />{item.reason}</p>)}</details>}
          {plan.can_execute && !plan.permanent_delete && <Button primary busy={busy} onClick={move}><Trash2 size={16} />{uncertain ? '核实并继续原清理' : `将 ${plan.asset_count} 个资产移入回收区`}</Button>}
          <Button disabled={busy} onClick={inspect}>重新检查范围</Button>
        </section>}
      </> : <>
        <div className="section-title"><h3>本库回收记录</h3><Button disabled={busy || loading} onClick={refresh}>刷新记录</Button></div>
        {loading ? <p className="muted">正在读取回收记录…</p> : history.items.length === 0 ? <Empty title="回收区为空">明确执行清理后，资产原位置与恢复入口会显示在这里。</Empty> : history.items.map(item => <section className="review-box" key={item.id}>
          <div className="section-title"><h3>{formatDate(item.created_at)} 清理</h3><Badge tone={item.state === 'restored' ? 'good' : ''}>{stateNames[item.state]}</Badge></div>
          <p className="muted">{item.asset_count} 个资产 · {item.file_count} 个文件 · {readableSize(item.total_bytes)}</p>
          <details><summary>查看资产与原位置</summary><AssetList items={item.items} showTrash /></details>
          {item.can_restore && <><p className="muted">恢复到记录中的原位置；位置已有其他内容时会停止，不会覆盖。</p><Button busy={busy} onClick={() => restore(item)}><RotateCcw size={16} />{item.state === 'restoring' ? '核实并继续恢复' : '恢复到原位置'}</Button></>}
          {item.state === 'restored' && <p className="muted">{formatDate(item.restored_at)} 已恢复，回收记录保留。</p>}
        </section>)}
        {history.unreadable_records.length > 0 && <ErrorNotice message={`${history.unreadable_records.length} 条回收记录无法读取，文件保持原状。请保留本库并核实记录。`} />}
      </>}
      <p className="muted cleanup-boundary">移入同一磁盘的回收区不会立即释放磁盘空间。当前仅提供可恢复整理，没有永久删除操作。</p>
      {busy && <p className="muted" role="status">正在核对文件或执行移动，请保持此窗口打开。</p>}
    </div>
  </Dialog>;
}
