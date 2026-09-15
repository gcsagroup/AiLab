import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { Model } from './types';
import { Badge, Button, Dialog, ErrorNotice, readableSize } from './ui';

type Catalog = { id: string; name: string; repo: string; revision: string; source_url: string; license: string; manifest_digest: string; total_bytes: number; network_scope: string; capability: string; files: { path: string; size: number; sha256: string }[] };
export type ModelDownload = { id: string; project_id: string; name: string; state: string; received_bytes: number; total_bytes: number; current_file: string | null; cancel_requested: boolean; model_id: string | null; error?: { code: string; message: string }; created_at?: string };
export const modelDownloadStates: Record<string, string> = { queued: '等待下载', downloading: '下载中', verifying: '核对文件与结构', completed: '文件已完整', failed: '需要处理', cancelled: '已停止' };
const active = new Set(['queued', 'downloading', 'verifying']);
type Command = { path: string; body: unknown; key: string; register: boolean };
function rejected(error: unknown): boolean {
  if (typeof error === 'string') { try { return rejected(JSON.parse(error)); } catch { return false; } }
  const code = (error as { error?: { code?: string } })?.error?.code;
  return typeof code === 'string' && !/^(CONTROL_|LOCAL_BRIDGE|INTERNAL_|NETWORK_|UNKNOWN)/.test(code);
}

export default function ModelDownloadDialog({ projectId, initial, onClose, onChanged, onUse }: { projectId: string; initial?: ModelDownload; onClose: () => void; onChanged: () => void; onUse: (model: Model) => void }) {
  const [catalog, setCatalog] = useState<Catalog | null>(null); const [record, setRecord] = useState<ModelDownload | null>(initial || null);
  const [model, setModel] = useState<Model | null>(null); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true); const [error, setError] = useState('');
  const pending = useRef<Command | null>(null); const live = useRef(true);
  useEffect(() => {
    live.current = true;
    api<{ items: Catalog[] }>('GET', '/model-catalog').then(result => { if (live.current) { setCatalog(result.items[0] || null); setLoading(false); } }).catch(e => { if (live.current) { setError(errorMessage(e)); setLoading(false); } });
    return () => { live.current = false; };
  }, []);
  useEffect(() => {
    if (!record) return;
    let current = true; let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const value = await api<ModelDownload>('GET', `/model-downloads/${record!.id}`);
        if (!current) return;
        setRecord(value);
        if (value.model_id) { const prepared = await api<Model>('GET', `/models/${value.model_id}`); if (current) setModel(prepared); }
        if (active.has(value.state)) timer = setTimeout(poll, 1000); else onChanged();
      } catch (e) { if (current) { setError(errorMessage(e)); timer = setTimeout(poll, 2000); } }
    }
    void poll(); return () => { current = false; clearTimeout(timer); };
  }, [record?.id, record?.state]);
  async function execute(command: Command) {
    pending.current = command; setBusy(true); setError('');
    try {
      const result = await api<ModelDownload | Model>('POST', command.path, command.body, command.key);
      if (!live.current) return;
      pending.current = null;
      if (command.register) { setModel(result as Model); setRecord(current => current ? { ...current, model_id: result.id } : current); }
      else setRecord(result as ModelDownload);
      onChanged();
    } catch (e) { if (live.current) { if (rejected(e)) pending.current = null; setError(errorMessage(e)); } }
    finally { if (live.current) setBusy(false); }
  }
  function command(action: string) {
    if (!catalog || busy || pending.current) return;
    void execute({ path: action === 'start' ? '/model-downloads' : `/model-downloads/${record!.id}/${action}`, body: action === 'start' ? { project_id: projectId, catalog_id: catalog.id, manifest_digest: catalog.manifest_digest } : {}, key: crypto.randomUUID(), register: action === 'models' });
  }
  return <Dialog title="准备第一个语言模型" wide onClose={onClose} preventClose={busy || Boolean(pending.current)}>
    <p>下载固定官方模型，核对文件后加入当前项目。运行环境由桌面 App 提供；首次生成仍需检查配置并明确开始。</p>
    {loading ? <p>正在读取支持的模型…</p> : catalog && <section className="review-box" aria-label="固定模型来源"><h3>{catalog.name}</h3><p>{catalog.capability}</p><dl className="facts"><div><dt>来源</dt><dd>{catalog.repo}</dd></div><div><dt>下载量</dt><dd>{readableSize(catalog.total_bytes)} · 建议预留约 2 GiB</dd></div><div><dt>许可文件</dt><dd>{catalog.license} · 随模型保留</dd></div></dl><p className="muted">{catalog.network_scope}</p><details><summary>固定版本与文件清单</summary><p>版本：{catalog.revision}</p><p>来源：{catalog.source_url}</p><ul className="export-file-list">{catalog.files.map(file => <li key={file.path}>{file.path}<small>{readableSize(file.size)}</small></li>)}</ul><p>每个文件均核对 SHA256；不执行下载文件中的代码。</p></details></section>}
    {record && <section className="data-management" aria-label="模型下载进度"><div className="section-title"><h3>{record.name}</h3><Badge>{modelDownloadStates[record.state] || record.state}</Badge></div><p>{readableSize(record.received_bytes)} / {readableSize(record.total_bytes)}{record.current_file ? ` · ${record.current_file}` : ''}</p><progress aria-label="模型下载进度" max={record.total_bytes} value={record.received_bytes} />{record.cancel_requested && active.has(record.state) && <p>正在停止传输，已下载部分会保留。</p>}<ErrorNotice message={record.error?.message || ''} /><p className="muted">可以关闭此窗口，随后从模型库的“模型准备记录”继续。</p></section>}
    <ErrorNotice message={error} /><div className="dialog-actions">
      {pending.current && !busy ? <Button primary onClick={() => void execute(pending.current!)}>重试上次操作</Button> : !record ? <Button primary busy={busy} disabled={!catalog} onClick={() => command('start')}>下载并核对固定模型</Button> : active.has(record.state) ? <Button busy={busy} disabled={record.cancel_requested} onClick={() => command('cancel')}>停止下载，保留进度</Button> : record.state !== 'completed' ? <Button primary busy={busy} onClick={() => command('resume')}>继续下载并核对</Button> : model ? <Button primary disabled={busy} onClick={() => onUse(model)}>用此模型开始试用</Button> : <Button primary busy={busy} onClick={() => command('models')}>加入当前项目模型库</Button>}
    </div>{model && <p role="status">模型已登记到当前项目，尚未运行。可以输入自己的问题，或使用首次试用示例。</p>}
  </Dialog>;
}
