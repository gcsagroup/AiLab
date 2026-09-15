import { useEffect, useRef, useState } from 'react';
import { api, collection, errorMessage, mergeRecords } from './api';
import type { ExecutionTarget } from './ExecutionTargets';
import type { Attempt, Dataset, Material, Task } from './types';
import { RunResult } from './Workbench';
import { Button, ErrorNotice, readableSize, stateNames } from './ui';

type TransferPlan = { prepare_id: string; digest: string; files: { path: string; size: number; sha256: string }[]; total_bytes: number; target: Pick<ExecutionTarget, 'id' | 'name' | 'origin' | 'executor_id' | 'revision'>; asset_manifest_digest: string };
export function TransferResult({ initial, onChanged }: { initial: Attempt; onChanged: () => void }) {
  return <><p className="muted">本次只传输已选文件并核对回读内容，没有运行模型。取消、断连与补收记录单独保留。</p><RunResult key={initial.id} initial={initial} onChanged={onChanged} /></>;
}

export function RemoteTransfers({ projectId, target, onChanged }: { projectId: string; target: ExecutionTarget; onChanged: () => void }) {
  const [kind, setKind] = useState<'dataset' | 'material'>('dataset'); const [assetId, setAssetId] = useState('');
  const [assets, setAssets] = useState<(Dataset | Material)[]>([]); const [next, setNext] = useState<string | null>(null);
  const [history, setHistory] = useState<Attempt[]>([]); const [plan, setPlan] = useState<TransferPlan | null>(null); const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [historyNext, setHistoryNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const epoch = useRef(0); const key = useRef(crypto.randomUUID());
  const configuration = useRef(''); configuration.current = `${target.id}:${target.revision}:${kind}:${assetId}`;
  const assetPath = `/${kind === 'dataset' ? 'datasets' : 'materials'}?project_id=${encodeURIComponent(projectId)}`;
  async function loadHistory(current: number, cursor?: string) {
    const result = await collection<Attempt>(`/remote-transfers?project_id=${encodeURIComponent(projectId)}&execution_target_id=${encodeURIComponent(target.id)}`, cursor);
    if (epoch.current === current) { setHistory(items => cursor ? mergeRecords(items, result.items) : result.items); setHistoryNext(result.next_cursor || null); }
  }
  useEffect(() => {
    const current = ++epoch.current; setAssetId(''); setAssets([]); setNext(null); setHistory([]); setHistoryNext(null); setPlan(null); setAttempt(null); setError(''); setBusy(true);
    void Promise.all([collection<Dataset | Material>(assetPath), loadHistory(current)]).then(([result]) => { if (epoch.current === current) { setAssets(result.items); setNext(result.next_cursor || null); } }).catch(e => { if (epoch.current === current) setError(errorMessage(e)); }).finally(() => { if (epoch.current === current) setBusy(false); });
    return () => { ++epoch.current; };
  }, [projectId, target.id, kind]);
  useEffect(() => { setPlan(null); key.current = crypto.randomUUID(); }, [target.revision, assetId]);
  async function perform(action: (current: number) => Promise<void>) { const current = epoch.current; setBusy(true); setError(''); try { await action(current); } catch (e) { if (epoch.current === current) setError(errorMessage(e)); } finally { if (epoch.current === current) setBusy(false); } }
  async function prepare() {
    const identity = configuration.current; setPlan(null);
    await perform(async current => { const result = await api<TransferPlan>('POST', '/remote-transfers/prepare', { project_id: projectId, execution_target_id: target.id, asset_kind: kind, asset_id: assetId }); if (epoch.current === current) { if (configuration.current !== identity || result.target.id !== target.id || result.target.revision !== target.revision) throw new Error('目标或资源已改变，请重新检查发送范围。'); setPlan(result); key.current = crypto.randomUUID(); } });
  }
  async function start() {
    if (!plan) return;
    await perform(async current => { const result = await api<Attempt>('POST', '/remote-transfers', { prepare_id: plan.prepare_id, digest: plan.digest }, key.current); if (epoch.current === current) { setAttempt(result); setPlan(null); await loadHistory(current); onChanged(); } });
  }
  function refreshResult() { const current = epoch.current; void loadHistory(current).catch(e => { if (epoch.current === current) setError(errorMessage(e)); }); onChanged(); }
  return <section className="data-management" aria-label="文件传输验证"><h4>文件传输验证 · {target.name}</h4><p className="muted">先检查将发送的文件、大小和目标，再明确开始。验证服务会保存副本，项目原文件保留。</p>
    <div className="form-stack"><label>文件类别<select disabled={busy} value={kind} onChange={e => setKind(e.target.value as 'dataset' | 'material')}><option value="dataset">已导入数据</option><option value="material">已导入素材</option></select></label><label>选择验证文件<select value={assetId} disabled={busy} onChange={e => setAssetId(e.target.value)}><option value="">选择当前项目的文件</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.name}</option>)}</select></label></div>
    {next && <Button disabled={busy} onClick={() => void perform(async current => { const result = await collection<Dataset | Material>(assetPath, next); if (epoch.current === current) { setAssets(old => mergeRecords(old, result.items)); setNext(result.next_cursor || null); } })}>加载更多文件</Button>}
    <Button disabled={busy || !assetId || !target.protocol_ready || target.credential_status === 'required'} onClick={() => void prepare()}>检查发送范围</Button>
    {plan && <section className="preflight" aria-label="本次文件发送范围"><strong>接收目标：{plan.target.name}</strong><p>{plan.target.origin}</p><p>共 {plan.files.length} 个文件 · {readableSize(plan.total_bytes)}</p><p className="muted">只发送以下已登记文件，不发送其他项目资源或凭据。此步骤没有模型计算。</p><ul>{plan.files.map(file => <li key={file.path}>{file.path} · {readableSize(file.size)}</li>)}</ul><details><summary>查看输入摘要与目标身份</summary><pre>{JSON.stringify({ executor_id: plan.target.executor_id, target_revision: plan.target.revision, asset_manifest_digest: plan.asset_manifest_digest, files: plan.files }, null, 2)}</pre></details><Button primary busy={busy} onClick={() => void start()}>开始传输验证</Button></section>}
    <ErrorNotice message={error} />
    {(history.length > 0 || attempt) && <label>查看传输记录<select disabled={busy} value={attempt?.id || ''} onChange={e => { const id = e.target.value; if (id) void perform(async current => { const value = await api<Attempt>('GET', `/attempts/${id}`); if (epoch.current === current) setAttempt(value); }); else setAttempt(null); }}><option value="">选择已保存的传输记录</option>{attempt && !history.some(item => item.id === attempt.id) && <option value={attempt.id}>当前记录 · {attempt.id.slice(-8)}</option>}{history.map(item => <option key={item.id} value={item.id}>{item.id.slice(-8)} · {stateNames[item.state] || item.state}</option>)}</select></label>}
    {historyNext && <Button disabled={busy} onClick={() => void perform(current => loadHistory(current, historyNext))}>加载更早传输记录</Button>}
    {attempt && <TransferResult initial={attempt} onChanged={refreshResult} />}
  </section>;
}

export function RemoteTransferTask({ task, onBack, onChanged }: { task: Task; onBack: () => void; onChanged: () => void }) {
  const [attempt, setAttempt] = useState<Attempt | null>(null); const [error, setError] = useState('');
  useEffect(() => { let live = true; const id = task.latest_attempt?.id || task.attempts?.[0]?.id; if (id) void api<Attempt>('GET', `/attempts/${id}`).then(value => { if (live) setAttempt(value); }).catch(e => { if (live) setError(errorMessage(e)); }); return () => { live = false; }; }, [task.id]);
  return <><Button onClick={onBack}>返回任务列表</Button><h1>{task.name}</h1><ErrorNotice message={error} />{attempt ? <TransferResult initial={attempt} onChanged={onChanged} /> : <p className="muted">正在读取已保存的文件传输记录。</p>}</>;
}
