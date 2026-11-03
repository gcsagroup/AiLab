import { useEffect, useRef, useState } from 'react';
import { Database, Download, Search, FolderOpen, RefreshCw, ExternalLink, KeyRound } from 'lucide-react';
import { errorMessage } from '../api';
import { Empty, Error, Field, PathField, request } from './common';
import type { Assets } from './types';

type Provider = 'huggingface' | 'kaggle';
type Source = { id: Provider; name: string; credential_configured: boolean };
type Hit = { id: string; title: string; description: string; downloads: number | null; license: unknown };
type DataFile = { path: string; size: number | null; sha256?: string | null; expected_sha256?: string | null; received?: number; complete?: boolean };
type Selection = { id: string; provider: Provider; dataset: string; title: string; revision: string; requested_revision: string; versions: string[]; description: string; license: unknown; source_url: string; files: DataFile[]; gated: boolean; archive_note?: string };
type Local = { id: string; name: string; path: string; source: string; files: DataFile[]; category: string; purpose: string; managed: boolean; size: number; provenance: { revision: string; license: unknown } | null };
type Transfer = { id: string; state: string; selection: { title: string; revision: string }; directory: string; error: string | null; received_bytes: number; total_bytes: number | null; attempts: number; files: DataFile[] };
type Preview = { text: string; note: string; truncated: boolean };
const labels: Record<string, string> = { queued: '排队中', downloading: '下载中', pausing: '正在暂停', paused: '已暂停', cancelling: '正在取消', cancelled: '已取消', completed: '已完成', failed: '失败', interrupted: '服务中断' };
const printable = (value: unknown) => value ? typeof value === 'string' ? value : JSON.stringify(value) : '来源未声明';
export function bytes(value: number | null | undefined) {
  if (value == null) return '大小未知';
  if (value < 1024) return `${value} B`;
  if (value < 1048576) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1073741824) return `${(value / 1048576).toFixed(1)} MiB`;
  return `${(value / 1073741824).toFixed(2)} GiB`;
}
const trainable = (path: string) => /\.(jsonl|json|parquet)$/i.test(path);

export default function Datasets({ assets, refreshAssets, settings, onUse }: { assets: Assets; refreshAssets: () => void; settings: () => void; onUse: (path: string) => void }) {
  const [tab, setTab] = useState<'market' | 'local' | 'downloads'>('market');
  const [provider, setProvider] = useState<Provider>('huggingface'); const [query, setQuery] = useState(''); const [page, setPage] = useState(1);
  const [hits, setHits] = useState<Hit[]>([]); const [more, setMore] = useState(false); const [searched, setSearched] = useState(false);
  const [selection, setSelection] = useState<Selection>(); const [revision, setRevision] = useState(''); const [chosen, setChosen] = useState<string[]>([]);
  const [sources, setSources] = useState<Source[]>([]); const [credentials, showCredentials] = useState(false); const [token, setToken] = useState(''); const [username, setUsername] = useState('');
  const [downloads, setDownloads] = useState<Transfer[]>([]); const [locals, setLocals] = useState<Local[]>([]); const [directory, setDirectory] = useState(''); const [free, setFree] = useState<number>();
  const [localPath, setLocalPath] = useState(''); const [isDirectory, setIsDirectory] = useState(false); const [category, setCategory] = useState('general'); const [purpose, setPurpose] = useState('research');
  const [openLocal, setOpenLocal] = useState(''); const [preview, setPreview] = useState<Preview>(); const [previewTitle, setPreviewTitle] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const generation = useRef(0); const completed = useRef('');

  useEffect(() => {
    let live = true;
    const reload = async () => {
      try {
        const [jobs, local] = await Promise.all([request<{ items: Transfer[] }>('GET', '/datasets/downloads'), request<{ items: Local[]; directory: string; free_bytes: number }>('GET', '/datasets/local')]);
        if (!live) return;
        setDownloads(jobs.items); setLocals(local.items); setDirectory(local.directory); setFree(local.free_bytes);
        const fingerprint = jobs.items.filter(x => x.state === 'completed').map(x => x.id).sort().join(',');
        if (fingerprint !== completed.current) { completed.current = fingerprint; refreshAssets(); }
      } catch (e) { if (live) setError(errorMessage(e)); }
    };
    void reload();
    void request<{ items: Source[] }>('GET', '/datasets/sources').then(x => { if (live) setSources(x.items); }).catch(e => { if (live) setError(errorMessage(e)); });
    const timer = setInterval(() => { void reload(); }, 1500);
    return () => { live = false; clearInterval(timer); generation.current++; };
  }, [refreshAssets]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function search(next = 1) {
    const stamp = ++generation.current;
    await run(async () => {
      const result = await request<{ items: Hit[]; has_more: boolean }>('POST', '/datasets/search', { provider, query, page: next });
      if (stamp !== generation.current) return;
      setHits(result.items); setMore(result.has_more); setSearched(true); setPage(next); setSelection(undefined);
    });
  }
  async function detail(id: string, version = '') {
    const stamp = ++generation.current;
    await run(async () => {
      const result = await request<Selection>('POST', '/datasets/detail', { provider, dataset: id, revision: version });
      if (stamp !== generation.current) return;
      setSelection(result); setRevision(result.requested_revision);
      setChosen(result.provider === 'kaggle' ? ['dataset.zip'] : result.files.filter(f => trainable(f.path) && !/(^|\/)(dataset_infos?|config|metadata)\.json$/i.test(f.path)).slice(0, 20).map(f => f.path));
    });
  }
  async function localImport(path = localPath) {
    await run(async () => { const result = await request<Local>('POST', '/datasets/local/import', { path, category, purpose }); setLocals(current => [result, ...current]); setLocalPath(''); refreshAssets(); setNotice('已登记本地数据，源文件保持原位'); });
  }
  async function useFile(item: Local, file: DataFile) {
    await run(async () => { const result = await request<{ path: string }>('POST', `/datasets/local/${item.id}/use`, { path: file.path }); onUse(result.path); });
  }
  const source = sources.find(x => x.id === provider);
  return <div className="st-stack st-datasets"><div className="st-dataset-heading"><div><h1>数据集</h1><p>发现训练数据，下载到本机，再用于 SFT。</p></div><button onClick={settings}><FolderOpen size={16} />设置资源目录</button></div>
    <div className="st-tabs" role="tablist" aria-label="数据集视图">{([['market', '数据集市场'], ['local', '本地数据集'], ['downloads', '下载任务']] as const).map(([id, title]) => <button role="tab" key={id} aria-selected={tab === id} onClick={() => { setTab(id); setError(''); setPreview(undefined); }}>{title}{id === 'downloads' && downloads.some(j => ['queued', 'downloading'].includes(j.state)) ? ' · 进行中' : ''}</button>)}</div>
    <Error text={error} />{notice && <p className="st-dataset-notice" role="status">{notice}</p>}
    {tab === 'market' && <><section className="st-panel"><form className="st-dataset-search" onSubmit={e => { e.preventDefault(); void search(); }}><Field title="数据来源"><select value={provider} disabled={busy} onChange={e => { generation.current++; setProvider(e.target.value as Provider); setHits([]); setSearched(false); setSelection(undefined); setToken(''); setUsername(''); }}>{(['huggingface', 'kaggle'] as const).map(x => <option key={x} value={x}>{x === 'huggingface' ? 'Hugging Face' : 'Kaggle'}</option>)}</select></Field><Field title="搜索数据集"><input value={query} maxLength={200} placeholder="关键词，例如 cybersecurity、instruction" onChange={e => setQuery(e.target.value)} /></Field><button className="st-primary" disabled={busy}><Search size={16} />{busy ? '正在读取…' : '搜索'}</button><button type="button" disabled={busy || !/^[^/\s]+\/[^/\s]+$/.test(query)} onClick={() => { void detail(query.trim()); }}>按 ID 打开</button></form>
      <div className="st-dataset-source"><span>{source?.credential_configured ? '已配置访问凭据' : provider === 'huggingface' ? '匿名访问公开数据' : '可配置 Kaggle 访问凭据'}</span><button onClick={() => showCredentials(!credentials)}><KeyRound size={14} />访问凭据</button></div>
      {credentials && <form className="st-dataset-credentials" onSubmit={e => { e.preventDefault(); void run(async () => { const result = await request<{ items: Source[] }>('POST', '/datasets/credentials', { provider, token, username: provider === 'kaggle' ? username : '' }); setSources(result.items); setToken(''); setUsername(''); showCredentials(false); setNotice('凭据仅在本次控制服务会话内生效'); }); }}><p className="st-note">仅保存在当前控制服务内存中，不写入数据索引或浏览器存储。也可由启动环境提供 HF_TOKEN、KAGGLE_API_TOKEN，或 KAGGLE_USERNAME / KAGGLE_KEY。</p>{provider === 'kaggle' && <Field title="Kaggle 用户名（旧版 Key 使用，新版 Token 留空）"><input autoComplete="off" value={username} onChange={e => setUsername(e.target.value)} /></Field>}<Field title="访问 Token / Key"><input type="password" autoComplete="new-password" value={token} maxLength={4096} onChange={e => setToken(e.target.value)} /></Field><button disabled={busy} type="submit">应用到本次会话</button><button disabled={busy} type="button" onClick={() => { void run(async () => { const result = await request<{ items: Source[] }>('POST', '/datasets/credentials', { provider, token: '', username: '' }); setSources(result.items); setToken(''); setNotice('本次会话已改为匿名访问'); }); }}>清除会话凭据</button></form>}
    </section><div className="st-dataset-layout"><section className="st-panel"><header><h2>发现数据集</h2><span className="st-tag">{provider === 'huggingface' ? 'Hugging Face' : 'Kaggle'}</span></header>{!hits.length ? <Empty>{searched ? '没有找到匹配的数据集，请换个关键词。' : '输入关键词搜索，或通过 owner/name 打开数据集。'}</Empty> : <div className="st-dataset-results">{hits.map(hit => <button className={selection?.dataset === hit.id ? 'selected' : ''} key={hit.id} disabled={busy} onClick={() => { void detail(hit.id); }}><strong>{hit.title}</strong><small>{hit.id}</small>{hit.description && <p>{hit.description}</p>}<span>许可：{printable(hit.license)}{hit.downloads != null ? ` · ${hit.downloads.toLocaleString()} 次下载` : ''}</span></button>)}</div>}{searched && <footer><button disabled={busy || page === 1} onClick={() => { void search(page - 1); }}>上一页</button><small>第 {page} 页 · 最多浏览前 100 项</small><button disabled={busy || !more} onClick={() => { void search(page + 1); }}>下一页</button></footer>}</section>
    <section className="st-panel st-dataset-detail">{!selection ? <Empty><Database size={28} /><p>选择一个数据集，查看说明、版本和文件。</p></Empty> : <><header><h2>{selection.title}</h2><a href={selection.source_url} target="_blank" rel="noreferrer">来源页面 <ExternalLink size={13} /></a></header><p className="st-note">许可：{printable(selection.license)}{selection.gated ? ' · 受限数据，需先在来源网站获得访问权限' : ''}</p><div className="st-dataset-revision"><Field title="版本 / Revision"><input value={revision} list="dataset-versions" maxLength={150} onChange={e => setRevision(e.target.value)} /><datalist id="dataset-versions">{selection.versions.map(v => <option key={v} value={v} />)}</datalist></Field><button disabled={busy || !revision.trim()} onClick={() => { void detail(selection.dataset, revision); }}>读取版本</button></div><small className="st-dataset-pin">已固定：{selection.revision}；修改版本后请先“读取版本”，再下载。</small><details open><summary>数据集说明（前 64 KiB）</summary><pre className="st-dataset-description">{selection.description || '来源未提供说明'}</pre></details>{selection.archive_note && <p className="st-note">{selection.archive_note}</p>}
    <div className="st-dataset-files"><div className="st-dataset-files-heading"><strong>文件 · 已选 {chosen.length} / {selection.files.length}</strong><button disabled={busy} onClick={() => setChosen([])}>清空选择</button></div>{selection.files.map(file => <div className="st-dataset-file" key={file.path}><label><input type="checkbox" checked={chosen.includes(file.path)} disabled={busy || (!chosen.includes(file.path) && chosen.length >= 500)} onChange={e => setChosen(current => e.target.checked ? [...current, file.path] : current.filter(f => f !== file.path))} /><span>{file.path}</span></label><small>{bytes(file.size)}</small>{selection.provider === 'huggingface' && /\.(jsonl|json|txt|csv|md)$/i.test(file.path) && <button disabled={busy} onClick={() => { void run(async () => { const p = await request<Preview>('POST', '/datasets/preview', { selection_id: selection.id, path: file.path }); setPreview(p); setPreviewTitle(file.path); }); }}>预览</button>}</div>)}</div>
    <div className="st-grid"><Field title="保存分类"><input value={category} maxLength={40} onChange={e => setCategory(e.target.value)} /></Field><Field title="数据用途"><select value={purpose} onChange={e => setPurpose(e.target.value)}><option value="research">研究</option><option value="training">训练</option><option value="evaluation">评测</option></select></Field></div><p className="st-note">根目录：{directory || '读取中…'} · 可用 {bytes(free)}。按分类分目录保存，许可按来源声明展示。</p><button className="st-primary" disabled={busy || !chosen.length || !category.trim() || revision !== selection.requested_revision} onClick={() => { void run(async () => { await request('POST', '/datasets/downloads', { selection_id: selection.id, files: chosen, category, purpose }); setTab('downloads'); setNotice('已加入下载队列'); }); }}><Download size={16} />下载所选文件</button></>}</section></div></>}
    {tab === 'local' && <><section className="st-panel"><header><h2>导入本地数据集</h2><button onClick={refreshAssets}><RefreshCw size={15} />刷新资源</button></header><form onSubmit={e => { e.preventDefault(); void localImport(); }}><PathField title={isDirectory ? '本地数据目录' : '本地数据文件'} value={localPath} onChange={setLocalPath} directory={isDirectory} /><label className="st-check"><input type="checkbox" checked={isDirectory} onChange={e => setIsDirectory(e.target.checked)} />选择整个目录</label><div className="st-grid"><Field title="本地分类"><input value={category} maxLength={40} onChange={e => setCategory(e.target.value)} /></Field><Field title="本地用途"><input value={purpose} maxLength={100} onChange={e => setPurpose(e.target.value)} /></Field></div><button disabled={busy || !localPath.trim()} className="st-primary">登记本地数据</button><p className="st-note">只建立索引，不搬移源文件。JSON、JSONL、Parquet 可选入 SFT；CSV/TXT 需先转换，ZIP 需先解压。</p></form></section><section className="st-panel"><header><h2>已登记数据集 · {locals.length}</h2><small>下载目录可用 {bytes(free)}</small></header>{!locals.length && <Empty>下载完成或导入后，数据会出现在这里。</Empty>}{locals.map(item => <article className="st-dataset-local" key={item.id}><header><div><h3>{item.name}</h3><small>{item.source} · {item.category} · {item.purpose} · {bytes(item.size)}</small></div><button onClick={() => setOpenLocal(openLocal === item.id ? '' : item.id)}>{openLocal === item.id ? '收起文件' : '查看文件'}</button><button disabled={busy} onClick={() => { void run(async () => { await request('POST', `/datasets/local/${item.id}/remove`, { delete_files: false }); setLocals(current => current.filter(x => x.id !== item.id)); refreshAssets(); }); }}>移除索引</button></header><p>{item.path}</p>{item.provenance && <small>固定版本：{item.provenance.revision} · 许可：{printable(item.provenance.license)}</small>}{openLocal === item.id && <div className="st-dataset-files">{item.files.map(file => <div className="st-dataset-file" key={file.path}><span>{file.path}</span><small>{bytes(file.size)}</small><button disabled={busy} onClick={() => { void run(async () => { setPreview(await request<Preview>('POST', `/datasets/local/${item.id}/preview`, { path: file.path })); setPreviewTitle(file.path); }); }}>预览</button>{trainable(file.path) && <button className="st-primary" disabled={busy} onClick={() => { void useFile(item, file); }}>用于 SFT</button>}{file.sha256 && <small title={file.sha256}>SHA256 {file.sha256.slice(0, 12)}…</small>}</div>)}</div>}</article>)}</section><section className="st-panel"><header><h2>资源目录扫描结果</h2></header><Error text={assets.datasets_error || ''} />{!assets.datasets.length && <Empty>资源目录暂无可识别数据。</Empty>}{assets.datasets.map(asset => <div className="st-dataset-file" key={asset.path}><span>{asset.name}<small className="st-dataset-pin">{asset.path}</small></span><small>{asset.format}</small><button disabled={busy} onClick={() => { void localImport(asset.path); }}>登记与预览</button></div>)}</section></>}
    {tab === 'downloads' && <section className="st-panel"><header><h2>下载队列</h2><small>单任务下载 · 部分文件保留以便继续</small></header>{!downloads.length && <Empty>尚无下载任务。前往市场选择数据和文件。</Empty>}{downloads.map(job => <article className="st-dataset-transfer" key={job.id}><header><div><h3>{job.selection.title}</h3><small>版本 {job.selection.revision} · {job.files.length} 个文件 · 尝试 {job.attempts} 次</small></div><span className="st-tag">{labels[job.state] || job.state}</span></header><progress aria-label={`${job.selection.title}下载进度`} max={job.total_bytes || undefined} value={job.total_bytes ? job.received_bytes : undefined} /><p>{bytes(job.received_bytes)} / {bytes(job.total_bytes)}</p><small className="st-dataset-pin">{job.directory}</small><Error text={job.error || ''} /><div className="st-actions">{(job.state === 'queued' || job.state === 'downloading') && <><button disabled={busy} onClick={() => { void run(async () => { await request('POST', `/datasets/downloads/${job.id}/pause`); }); }}>暂停</button><button disabled={busy} onClick={() => { void run(async () => { await request('POST', `/datasets/downloads/${job.id}/cancel`); }); }}>取消</button></>}{['paused', 'failed', 'cancelled', 'interrupted'].includes(job.state) && <button disabled={busy} onClick={() => { void run(async () => { await request('POST', `/datasets/downloads/${job.id}/resume`); }); }}>继续 / 重试</button>}{job.state === 'completed' && <button onClick={() => { setTab('local'); setOpenLocal(job.id); }}>查看本地数据</button>}{['paused', 'failed', 'cancelled', 'interrupted', 'completed'].includes(job.state) && <button disabled={busy} onClick={() => { if (window.confirm('删除该任务下载的文件及索引？本地导入源文件不会受影响。')) void run(async () => { await request('POST', `/datasets/downloads/${job.id}/cleanup`); setDownloads(current => current.filter(x => x.id !== job.id)); refreshAssets(); }); }}>清理下载文件</button>}</div></article>)}</section>}
    {preview && <section className="st-panel" aria-label="文件预览"><header><h2>{previewTitle}</h2><button onClick={() => setPreview(undefined)}>关闭预览</button></header><p className="st-note">{preview.note}{preview.truncated ? ' · 内容已截断' : ''}</p><pre className="st-dataset-preview">{preview.text}</pre></section>}
  </div>;
}
