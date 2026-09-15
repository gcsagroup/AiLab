import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Download, RefreshCw, Search } from 'lucide-react';
import { api, errorMessage } from './api';
import type { Dataset, Task } from './types';
import { Badge, Button, Dialog, Empty, ErrorNotice, formatDate, readableSize } from './ui';
import './DatasetMarket.css';

type Source = { provider_id: string; source_label: string };
export type MarketVersion = { id: string; project_id: string; provider_id: string; version_digest: string; metadata: { dataset_key: string; version: string; name: string; description: string; modality: 'text' | 'image'; schema: 'sft' | 'image_caption_v1'; sample_count: number | null; total_bytes: number; format: string; provider_text: string; source_url: string | null; updated_at: string | null; access: 'open' | 'restricted'; license: { reference: string | null; provider_text: string | null } | null; files: { path: string; size: number; sha256: string }[] } };
type Catalog = { versions: MarketVersion[]; catalog_version: string };
type Context = { id: string; task_id: string; draft_revision: number };
type AccessStatus = 'waiting' | 'approved' | 'denied' | 'expired' | 'revoked';
type ProviderResponse = { status: AccessStatus; provider_text: string; revision: number; updated_at: string; expires_at: string | null };
export type MarketAccess = { id: string; version_id: string; created_at: string; sent: { purpose: string; user_statement: string }; provider_response: ProviderResponse; response_history: { received_at: string; response: ProviderResponse }[] };
export type MarketDownload = { id: string; version_id: string; state: 'queued' | 'downloading' | 'completed' | 'cancelled' | 'failed'; received_bytes: number; complete: boolean; cancel_requested: boolean; dataset_id: string | null; error?: { code: string; message: string } | null; created_at: string; updated_at?: string };
type Activity = { access_requests: MarketAccess[]; downloads: MarketDownload[]; datasets: Dataset[] };
export type MarketApplied = { task: Task; return_to: { project_id: string; task_id: string; kind: string; step: 'data'; highlight_dataset_id: string }; previous_checks_invalidated: true };
type Props = { projectId: string; task?: Task; onClose: () => void; onApplied: (result: MarketApplied) => void; onDatasetImported: (dataset: Dataset) => void };
type Command = { path: string; body: unknown; key: string; action: 'context' | 'access' | 'refresh' | 'start' | 'cancel' | 'resume' | 'register' | 'apply'; downloadId?: string };
const emptyActivity = (): Activity => ({ access_requests: [], downloads: [], datasets: [] });
const accessNames: Record<AccessStatus, string> = { waiting: '等待提供方处理', approved: '访问获准', denied: '访问拒绝', expired: '访问已到期', revoked: '访问已撤销' };
const downloadNames = { queued: '等待下载', downloading: '正在下载', completed: '文件下载完整', cancelled: '已取消 · 原字节保留', failed: '下载未完成' };
const kindNames = { text: '文本', image: '图片' };
function failureCode(value: unknown): string | undefined {
  if (typeof value === 'string') { try { return failureCode(JSON.parse(value)); } catch { return undefined; } }
  return value && typeof value === 'object' && 'error' in value ? (value as { error?: { code?: string } }).error?.code : undefined;
}
function confirmedRejection(value: unknown) {
  const code = failureCode(value);
  return code && !/^(LOCAL_BRIDGE|NETWORK_|INTERNAL_|CONTROL_|UNKNOWN|MARKET_PROVIDER_UNAVAILABLE|MARKET_THREAD_START_FAILED)/.test(code);
}
function replace<T extends { id: string }>(items: T[], item: T): T[] { return [...items.filter(value => value.id !== item.id), item]; }
function mergeDownload(items: MarketDownload[], item: MarketDownload) {
  const existing = items.find(value => value.id === item.id);
  if (existing && (existing.updated_at || existing.created_at) > (item.updated_at || item.created_at)) return items;
  return replace(items, item);
}

export function DatasetMarket({ projectId, task, onClose, onApplied, onDatasetImported }: Props) {
  const [sources, setSources] = useState<Source[]>([]); const [sourceId, setSourceId] = useState('');
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [selectedId, setSelectedId] = useState('');
  const [query, setQuery] = useState(''); const [filter, setFilter] = useState('all');
  const [context, setContext] = useState<Context | null>(null); const [activity, setActivity] = useState<Activity>(emptyActivity);
  const [accessId, setAccessId] = useState(''); const [downloadId, setDownloadId] = useState('');
  const [forms, setForms] = useState<Record<string, { purpose: string; statement: string }>>({});
  const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [activityLoading, setActivityLoading] = useState(false);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [conflict, setConflict] = useState(false);
  const [contextError, setContextError] = useState('');
  const [sourceReload, setSourceReload] = useState(0); const [catalogReload, setCatalogReload] = useState(0); const [activityReload, setActivityReload] = useState(0);
  const epoch = useRef(0); const busyRef = useRef(false); const pending = useRef<Command | null>(null);
  const contextCommand = useRef<{ scope: string; command: Command } | null>(null);
  const selected = catalog?.versions.find(item => item.id === selectedId);
  const form = forms[selectedId] || { purpose: '', statement: '' };
  const access = activity.access_requests.find(item => item.id === accessId);
  const download = activity.downloads.find(item => item.id === downloadId);
  const dataset = activity.datasets.find(item => item.id === download?.dataset_id);
  const locked = busy || Boolean(pending.current);
  const activeIds = activity.downloads.filter(item => item.state === 'queued' || item.state === 'downloading').map(item => item.id).sort().join(',');

  async function execute(command: Command, generation = epoch.current) {
    if (busyRef.current) return;
    busyRef.current = true; pending.current = command; setBusy(true); setError(''); setNotice('');
    try {
      const result = await api<Context | MarketAccess | MarketDownload | Dataset | MarketApplied>('POST', command.path, command.body, command.key);
      if (generation !== epoch.current) return;
      pending.current = null;
      if (command.action === 'context') { setContext(result as Context); setContextError(''); }
      else if (command.action === 'access' || command.action === 'refresh') {
        const value = result as MarketAccess;
        setActivity(previous => ({ ...previous, access_requests: replace(previous.access_requests, value) })); setAccessId(value.id);
        setNotice(command.action === 'access' ? '申请已发送给受控提供方，当前状态以提供方回复为准。' : '已读取提供方的当前回复。');
      } else if (command.action === 'register') {
        const value = result as Dataset;
        setActivity(previous => ({ ...previous, datasets: replace(previous.datasets, value), downloads: previous.downloads.map(item => item.id === command.downloadId ? { ...item, dataset_id: value.id } : item) }));
        setNotice('数据已检查并导入当前项目。'); onDatasetImported(value);
      } else if (command.action === 'apply') { onApplied(result as MarketApplied); onClose(); }
      else {
        const value = result as MarketDownload;
        setActivity(previous => ({ ...previous, downloads: mergeDownload(previous.downloads, value) })); setDownloadId(value.id);
      }
    } catch (failure) {
      if (generation !== epoch.current) return;
      if (confirmedRejection(failure)) pending.current = null;
      if (command.action === 'context') setContextError(errorMessage(failure));
      if (command.action === 'apply' && failureCode(failure) === 'REVISION_CONFLICT') setConflict(true);
      setError(errorMessage(failure));
    } finally { if (generation === epoch.current) { busyRef.current = false; setBusy(false); } }
  }
  function mutate(action: Command['action'], path: string, body: unknown, targetDownloadId?: string) {
    if (busyRef.current || pending.current) return;
    void execute({ action, path, body, key: crypto.randomUUID(), downloadId: targetDownloadId });
  }
  useEffect(() => {
    const generation = ++epoch.current;
    busyRef.current = false; pending.current = null; setBusy(false); setContext(null); setConflict(false); setContextError(''); setError(''); setNotice('');
    setSources([]); setSourceId(''); setCatalog(null); setSelectedId(''); setActivity(emptyActivity()); setForms({}); setQuery('');
    setFilter(task?.kind === 'text' || task?.kind === 'image' ? task.kind : 'all');
    if (task) {
      if (task.project_id !== projectId || task.operation !== 'train' || !['text', 'image'].includes(task.kind)) setError('此入口不属于当前项目的文本或图片训练任务。');
      else {
        const scope = `${projectId}/${task.id}`;
        if (contextCommand.current?.scope !== scope) contextCommand.current = { scope, command: { action: 'context', path: `/tasks/${task.id}/market-contexts`, body: { expected_revision: task.draft_revision, step: 'data' }, key: crypto.randomUUID() } };
        void execute(contextCommand.current.command, generation);
      }
    }
    return () => { epoch.current++; };
  }, [projectId, task?.id]);
  useEffect(() => {
    let live = true; setLoading(true);
    api<{ items: Source[] }>('GET', '/market/sources').then(value => { if (live) { setSources(value.items); setSourceId(current => value.items.some(item => item.provider_id === current) ? current : value.items[0]?.provider_id || ''); } }).catch(failure => { if (live) setError(errorMessage(failure)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [projectId, task?.id, sourceReload]);
  useEffect(() => {
    if (!sourceId) return;
    let live = true; setLoading(true); setCatalog(null); setSelectedId(''); setActivity(emptyActivity()); setError('');
    api<Catalog>('GET', `/market/catalog?project_id=${encodeURIComponent(projectId)}&provider_id=${encodeURIComponent(sourceId)}`).then(value => {
      if (!live) return;
      setCatalog(value);
      const preferred = value.versions.filter(item => !task || item.metadata.modality === task.kind);
      setSelectedId(preferred.at(-1)?.id || value.versions.at(-1)?.id || '');
    }).catch(failure => { if (live) setError(errorMessage(failure)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [projectId, sourceId, catalogReload]);
  useEffect(() => {
    setActivity(emptyActivity()); setAccessId(''); setDownloadId(''); setNotice('');
    if (!selectedId) return;
    let live = true; setActivityLoading(true);
    api<Activity>('GET', `/market/versions/${selectedId}/activity`).then(value => {
      if (!live) return;
      setActivity(value); setAccessId(value.access_requests.at(-1)?.id || ''); setDownloadId(value.downloads.at(-1)?.id || '');
    }).catch(failure => { if (live) setError(errorMessage(failure)); }).finally(() => { if (live) setActivityLoading(false); });
    return () => { live = false; };
  }, [selectedId, activityReload]);
  useEffect(() => {
    if (!activeIds) return;
    let live = true; let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const values = await Promise.all(activeIds.split(',').map(id => api<MarketDownload>('GET', `/market/downloads/${id}`)));
        if (!live) return;
        setActivity(previous => ({ ...previous, downloads: values.reduce(mergeDownload, previous.downloads) }));
      } catch (failure) { if (live) setError('下载状态暂未读取：' + errorMessage(failure)); }
      if (live) timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [selectedId, activeIds]);

  function changeForm(field: 'purpose' | 'statement', value: string) { setForms(previous => ({ ...previous, [selectedId]: { ...form, [field]: value } })); }
  const visible = (catalog?.versions || []).filter(item => (filter === 'all' || item.metadata.modality === filter) && `${item.metadata.name} ${item.metadata.description} ${item.metadata.dataset_key}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const groups = visible.filter((item, index) => visible.findIndex(other => other.metadata.dataset_key === item.metadata.dataset_key) === index);
  const data = selected?.metadata;
  const compatible = !!task && !!data && ((task.kind === 'text' && data.schema === 'sft') || (task.kind === 'image' && data.schema === 'image_caption_v1'));
  const expired = Boolean(access?.provider_response.expires_at && Date.parse(access.provider_response.expires_at) <= Date.now());
  const granted = data?.access === 'open' || (access?.provider_response.status === 'approved' && !expired);
  const activeDownload = activity.downloads.some(item => item.state === 'queued' || item.state === 'downloading');
  const selectedActive = download?.state === 'queued' || download?.state === 'downloading';
  const percent = data && download ? Math.min(100, Math.max(0, 100 * download.received_bytes / data.total_bytes)) : 0;

  return <Dialog title="数据市场" wide onClose={onClose} preventClose={locked}><div className="dataset-market">
    <div className="market-intro"><Badge tone="warning">受控测试来源</Badge><p>{task ? <>返回 <strong>{task.name}</strong> 的训练数据步骤；原草稿只在你选择“用于当前任务”时更新。</> : '浏览当前项目的数据来源，下载并检查后导入“我的数据”。'}</p><small>访问状态由提供方处理；许可原文与使用声明分别保留。</small></div>
    <ErrorNotice message={contextError || error} />{notice && <p className="market-notice" role="status">{notice}</p>}
    {pending.current && !busy && <div className="review-box"><p>上次操作的响应尚未确认。重试会使用原请求，不会重复创建申请或重新开始下载。</p><Button primary onClick={() => void execute(pending.current!)}>重试并读取原结果</Button></div>}
    {!sources.length ? <Empty title={loading ? '正在读取来源' : '尚未登记受控数据来源'} action={<Button disabled={locked} onClick={() => setSourceReload(value => value + 1)}><RefreshCw size={15} />重新读取来源</Button>}>此版本需要由本机宿主准备固定的测试提供方。</Empty> : <>
      <div className="market-toolbar"><label>数据来源<select aria-label="数据来源" disabled={locked || loading} value={sourceId} onChange={event => setSourceId(event.target.value)}>{sources.map(item => <option key={item.provider_id} value={item.provider_id}>{item.source_label} · {item.provider_id}</option>)}</select></label><Button disabled={locked || loading} onClick={() => setCatalogReload(value => value + 1)}><RefreshCw size={15} />刷新目录</Button></div>
      {loading ? <Empty title="正在读取提供方目录" /> : !catalog ? <Empty title="目录暂未读取" /> : <div className="market-columns"><section className="market-catalog" aria-label="数据目录"><div className="market-search"><Search size={16} /><input aria-label="搜索数据集" placeholder="搜索名称或描述" value={query} disabled={locked} onChange={event => setQuery(event.target.value)} /></div><label className="market-filter">数据类型<select aria-label="数据类型" disabled={locked} value={filter} onChange={event => setFilter(event.target.value)}><option value="all">全部类型</option><option value="text">文本</option><option value="image">图片</option></select></label><div className="market-list">{groups.length ? groups.map(item => { const versions = visible.filter(value => value.metadata.dataset_key === item.metadata.dataset_key); return <button className={data?.dataset_key === item.metadata.dataset_key ? 'selected' : ''} disabled={locked} key={item.metadata.dataset_key} onClick={() => { setSelectedId(versions.at(-1)!.id); setError(''); }}><strong>{item.metadata.name}</strong><span>{kindNames[item.metadata.modality]} · {versions.length} 个版本</span><small>{item.metadata.description}</small></button>; }) : <p className="muted">没有匹配的数据集。</p>}</div></section>
      <section className="market-detail" aria-label="数据版本详情">{!selected || !data ? <Empty title="选择一个数据集查看版本" /> : <>
        <div className="section-title"><h3>{data.name}</h3><Badge>{kindNames[data.modality]}</Badge></div><p className="muted">{data.description}</p>
        <label>数据版本<select aria-label="数据版本" value={selectedId} disabled={locked || activityLoading} onChange={event => { setSelectedId(event.target.value); setError(''); }}>{catalog.versions.filter(item => item.metadata.dataset_key === data.dataset_key).map(item => <option key={item.id} value={item.id}>{item.metadata.version}</option>)}</select></label>
        <dl className="facts"><div><dt>数据格式</dt><dd>{data.format} · {data.schema === 'sft' ? '对话训练 SFT' : '图片与描述'}</dd></div><div><dt>样本数量</dt><dd>{data.sample_count === null ? '提供方未填写' : `${data.sample_count} 条`}</dd></div><div><dt>下载大小</dt><dd>{readableSize(data.total_bytes)} · {data.files.length} 个文件</dd></div><div><dt>更新时间</dt><dd>{data.updated_at ? formatDate(data.updated_at) : '提供方未填写'}</dd></div><div><dt>来源记录</dt><dd>{data.source_url || '提供方未填写链接'}</dd></div></dl>
        <details><summary>查看提供方原文与完整性信息</summary><h4>提供方说明</h4><p className="market-original">{data.provider_text || '提供方未填写'}</p><h4>原始许可材料</h4><p className="market-original">{data.license?.provider_text || '未提供许可原文'}</p><p className="muted">引用：{data.license?.reference || '未提供'}</p><p className="muted">下载前样例：提供方尚未公开；导入时会检查实际文件。</p><dl className="facts"><div><dt>版本摘要</dt><dd><code>{selected.version_digest}</code></dd></div></dl>{data.files.map(item => <p className="market-file" key={item.path}><strong>{item.path}</strong> · {readableSize(item.size)}<code>{item.sha256}</code></p>)}</details>
        {activityLoading ? <Empty title="正在读取此版本的申请与下载记录" /> : <>
          <section className="market-access"><h4>访问与下载</h4>{data.access === 'open' ? <Badge tone="success">提供方开放下载</Badge> : <>
            <Badge tone={access?.provider_response.status === 'approved' && !expired ? 'success' : 'warning'}>{access ? accessNames[access.provider_response.status] : '需要申请访问'}</Badge>
            {activity.access_requests.length > 1 && <label>申请记录<select aria-label="申请记录" value={accessId} disabled={locked} onChange={event => setAccessId(event.target.value)}>{activity.access_requests.map(item => <option key={item.id} value={item.id}>{formatDate(item.created_at)} · {accessNames[item.provider_response.status]}</option>)}</select></label>}
            {access && <div className="market-provider-response"><p className="market-original">{access.provider_response.provider_text || '提供方没有附加说明。'}</p><small>提供方回复第 {access.provider_response.revision} 版 · {formatDate(access.provider_response.updated_at)}{access.provider_response.expires_at && <> · 有效期至 {formatDate(access.provider_response.expires_at)}</>}</small>{expired && <p className="warning">此回复的有效期已结束，当前不能下载。</p>}<Button disabled={locked} onClick={() => mutate('refresh', `/market/access-requests/${access.id}/refresh`, {})}><RefreshCw size={14} />刷新提供方状态</Button><details><summary>已提交内容与历史回复</summary><p className="market-original">用途：{access.sent.purpose}</p><p className="market-original">使用声明：{access.sent.user_statement}</p>{access.response_history.map((item, index) => <p key={index} className="market-original">第 {item.response.revision} 版 · {accessNames[item.response.status]}：{item.response.provider_text}</p>)}</details></div>}
            {(!access || ['denied', 'expired', 'revoked'].includes(access.provider_response.status) || expired) && <label>申请用途<textarea aria-label="申请用途" rows={2} maxLength={2000} disabled={locked} value={form.purpose} onChange={event => changeForm('purpose', event.target.value)} placeholder="说明这份数据将用于什么任务" /></label>}
          </>}
          <label>你的使用范围声明<textarea aria-label="你的使用范围声明" rows={2} maxLength={2000} disabled={locked} value={form.statement} onChange={event => changeForm('statement', event.target.value)} placeholder="由你填写本次数据使用范围" /></label>
          {data.access === 'restricted' && (!access || ['denied', 'expired', 'revoked'].includes(access.provider_response.status) || expired) && <><small className="muted">提交只发送提供方和数据版本、填写的用途与声明，以及用于避免重复申请的请求编号。</small><Button disabled={locked || !form.purpose.trim() || !form.statement.trim()} onClick={() => mutate('access', '/market/access-requests', { version_id: selected.id, purpose: form.purpose, user_statement: form.statement })}>{access ? '重新提交访问申请' : '提交访问申请'}</Button></>}
          <Button primary disabled={locked || !granted || !form.statement.trim() || activeDownload} onClick={() => mutate('start', '/market/downloads', { version_id: selected.id, user_statement: form.statement, ...(data.access === 'restricted' && access ? { access_id: access.id } : {}) })}><Download size={15} />{activity.downloads.length ? '新建一次下载' : '下载此版本'}</Button>
          {!granted && <small className="muted">提供方批准且仍在有效期内时才可下载，应用不会代为批准。</small>}
          </section>
          {activity.downloads.length > 0 && <section className="market-download" aria-label="下载与导入"><label>下载记录<select aria-label="下载记录" value={downloadId} disabled={locked} onChange={event => setDownloadId(event.target.value)}>{activity.downloads.map(item => <option key={item.id} value={item.id}>{formatDate(item.created_at)} · {downloadNames[item.state]}</option>)}</select></label>{download && <>
            <strong>{download.cancel_requested && selectedActive ? '正在停止下载，保留原字节' : downloadNames[download.state]}</strong><progress aria-label="下载进度" max={data.total_bytes} value={download.received_bytes} /><small>{readableSize(download.received_bytes)} / {readableSize(data.total_bytes)} · {percent.toFixed(1)}%</small>
            {download.error && <p className="warning">{download.error.message}</p>}
            {selectedActive && <><Button disabled={locked || download.cancel_requested} onClick={() => mutate('cancel', `/market/downloads/${download.id}/cancel`, {})}>取消下载并保留原字节</Button><small className="muted">关闭市场后下载仍在本机继续，可回到此版本查看。</small></>}
            {['cancelled', 'failed'].includes(download.state) && <Button disabled={locked || !granted || activeDownload} onClick={() => mutate('resume', `/market/downloads/${download.id}/resume`, {})}>继续下载保留的文件</Button>}
            {download.complete && !download.dataset_id && <><p className="muted">文件大小与摘要已核对；数据格式仍需检查后才能导入。</p><Button primary disabled={locked} onClick={() => mutate('register', `/market/downloads/${download.id}/datasets`, {}, download.id)}>检查并导入当前项目</Button></>}
            {download.dataset_id && <div className="market-imported"><Badge tone="success">已导入当前项目</Badge><p>{dataset?.name || data.name}</p>{task ? <><p className="muted">{compatible ? '使用后只更换原任务的数据版本，并要求重新进行技术检查。' : `原任务需要${task.kind === 'text' ? '文本 SFT' : '图片与描述'}格式。此数据已保留在它所属的类型中。`}</p><Button primary disabled={locked || !compatible || !context || conflict} onClick={() => mutate('apply', `/market/contexts/${context!.id}/use`, { dataset_id: download.dataset_id })}>用于当前任务</Button>{conflict && <Button disabled={locked} onClick={onClose}>返回原任务查看新草稿</Button>}</> : <Button primary disabled={locked} onClick={onClose}>返回我的数据</Button>}</div>}
          </>}</section>}
          <Button disabled={locked} onClick={() => { setActivityReload(value => value + 1); setError(''); }}><RefreshCw size={14} />重新读取本版记录</Button>
        </>}
      </>}</section></div>}
    </>}
    <div className="dialog-footer"><Button disabled={locked} onClick={onClose}><ArrowLeft size={15} />{task ? '返回原任务' : '返回我的数据'}</Button><small className="muted">下载、导入和使用均保留来源版本。</small></div>
  </div></Dialog>;
}
