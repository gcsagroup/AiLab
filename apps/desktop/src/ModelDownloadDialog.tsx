import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { Model, ModelExecutionBoundary } from './types';
import { hasKnownModelBoundary, ModelExecutionNotice } from './ModelExecutionNotice';
import { Badge, Button, Dialog, ErrorNotice, readableSize } from './ui';

const formatNames: Record<string, string> = { gguf: 'GGUF', safetensors: 'Safetensors', pytorch: 'PyTorch（BIN / PT / PTH / CKPT）', onnx: 'ONNX', tensorflow: 'TensorFlow / Keras / TFLite', flax: 'Flax', coreml: 'Core ML', openvino: 'OpenVINO', ggml: 'GGML', snapshot: '完整仓库（所有格式）', file: '指定单个文件（任意格式）' };
type Catalog = { selection_error?: string; format?: string; formats?: string[]; gated?: boolean | string; variants?: string[]; filename?: string; execution_boundary?: ModelExecutionBoundary; id: string; name: string; repo: string; revision: string; source_url: string; license: string; manifest_digest: string; total_bytes: number; network_scope: string; capability: string; files: { path: string; size: number; sha256: string | null; gitOid?: string; url?: string }[] };
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
  const native = Boolean(window.ailabHF);
  const [query, setQuery] = useState('');
  const [choices, setChoices] = useState<string[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [searchPage, setSearchPage] = useState('');
  const [searchError, setSearchError] = useState('');
  const [repo, setRepo] = useState('Qwen/Qwen2.5-0.5B-Instruct-GGUF');
  const [format, setFormat] = useState('');
  const [variant, setVariant] = useState('');
  const [reviewVersion, setReviewVersion] = useState(0);
  const [selectionError, setSelectionError] = useState(false);
  const [reading, setReading] = useState(false);
  const search = query.trim().replace(/^https:\/\/huggingface\.co\//i, '').replace(/\/$/, '');
  const exact = /^[\w.-]+\/[\w.-]+$/.test(search) ? search : '';
  useEffect(() => {
    if (!native || record) return;
    let current = true;
    const args = new URLSearchParams({q: search, cursor: searchPage});
    const timer = setTimeout(() => {
      setReading(true);
      api<{items: string[]; next_cursor: string | null}>('GET', '/model-catalog/search?' + args).then(page => {
        if (current) { setChoices(previous => [...new Set([...(searchPage ? previous : []), ...page.items])]); setCursor(page.next_cursor); setSearchError(''); }
      }).catch(e => { if (current) setSearchError(errorMessage(e)); }).finally(() => { if (current) setReading(false); });
    }, search ? 300 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [native, search, searchPage, Boolean(record)]);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => {
    let current = true;
    if (native && !repo && !initial) { setLoading(false); return; }
    const params = initial ? new URLSearchParams({download: initial.id}) : new URLSearchParams({repo, format, filename: variant});
    setLoading(true); setSelectionError(false);
    setError('');
    api<{ items: Catalog[] }>('GET', '/model-catalog' + (native ? '?' + params : '')).then(result => { if (current) { setCatalog(result.items[0] || null); setLoading(false); } }).catch(e => { if (current) { setError(errorMessage(e)); setSelectionError(true); setLoading(false); } });
    return () => { current = false; };
  }, [repo, format, variant, native, initial?.id, reviewVersion]);
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
    } catch (e) { if (live.current) { if (rejected(e)) pending.current = null; setError(errorMessage(e));
      if (native && command.register && record) {
        try { const latest = await api<ModelDownload>('GET', `/model-downloads/${record.id}`); if (live.current) setRecord(latest); } catch { /* Keep the original error and retry action. */ }
      } } }
    finally { if (live.current) setBusy(false); }
  }
  function command(action: string) {
    if ((action === 'start' && (!catalog || catalog.selection_error)) || busy || pending.current) return;
    void execute({ path: action === 'start' ? '/model-downloads' : `/model-downloads/${record!.id}/${action}`, body: action === 'start' ? { project_id: projectId, catalog_id: catalog!.id, manifest_digest: catalog!.manifest_digest } : {}, key: crypto.randomUUID(), register: action === 'models' });
  }
  return <Dialog title="准备第一个语言模型" wide onClose={onClose} preventClose={busy || Boolean(pending.current)}>
    <p>选择模型，查看许可和下载清单。文件核对完成后，可加入当前项目模型库。</p>
    {native && !record && <fieldset className="form-stack" disabled={busy || Boolean(pending.current)}>
      <label>搜索 Hugging Face 语言模型<input type="search" placeholder="模型名、发布者/模型名或 Hugging Face 仓库网址" value={query} onChange={e => { setQuery(e.target.value); setSelectionError(false); setRepo(''); setFormat(''); setVariant(''); setCatalog(null); setChoices([]); setCursor(null); setSearchPage(''); setError(''); setSearchError(''); }} /></label>
      <label>发布仓库<select value={repo} onChange={e => {
        if (e.target.value === '__next__') { setSearchPage(cursor || ''); return; }
        setCatalog(null); setFormat(''); setVariant(''); setRepo(e.target.value);
      }}><option value="">{reading ? '正在搜索…' : '选择发布者和模型'}</option>
        {[...new Set([repo, exact, ...choices].filter(Boolean))].map(id => <option key={id} value={id}>{id}</option>)}
        {cursor && <option value="__next__">查看更多匹配仓库…</option>}
      </select></label>
      <small className="muted">默认列出模型团队的发布仓库。搜索覆盖社区仓库，请核对发布者与模型卡许可。</small>
      <ErrorNotice message={searchError} />
      {catalog?.formats && <label>下载格式<select value={format || catalog.format} onChange={e => { setFormat(e.target.value); setVariant(''); setLoading(true); }}>{catalog.formats.map(key => <option key={key} value={key}>{formatNames[key] || key}</option>)}</select></label>}
      {catalog?.variants && catalog.variants.length > 1 && <label>{catalog.format === 'file' ? '仓库文件' : '量化文件'}<select value={variant || catalog.filename} onChange={e => { setVariant(e.target.value); setLoading(true); }}>{catalog.variants.map(name => <option key={name}>{name}</option>)}</select></label>}
    </fieldset>}
    {loading ? <p>正在读取支持的模型…</p> : catalog?.selection_error ? <ErrorNotice message={catalog.selection_error} /> : catalog && <section className="review-box" aria-label="固定模型来源"><h3>{catalog.name}</h3><p>{catalog.capability}</p>{catalog.gated && <p>此仓库需要先在 Hugging Face 获得授权，再设置 HF_TOKEN 并重开 AiLab。</p>}<dl className="facts"><div><dt>来源</dt><dd>{catalog.repo}</dd></div><div><dt>下载量</dt><dd>{readableSize(catalog.total_bytes)}</dd></div><div><dt>模型卡许可</dt><dd>{catalog.license}</dd></div></dl><p className="muted">{catalog.network_scope}</p><details><summary>固定版本与文件清单</summary><p>版本：{catalog.revision}</p><p>来源：{catalog.source_url}</p><ul className="export-file-list">{catalog.files.map(file => <li key={file.path}>{file.path}<small>{readableSize(file.size)}</small>{file.url && <small style={{overflowWrap: 'anywhere', userSelect: 'text'}}>{file.url}</small>}</li>)}</ul><p>{native ? '权重按 Hub 的 SHA-256 校验，普通文件按 Git 对象摘要校验。' : '每个文件均核对 SHA256；不执行下载文件中的代码。'}</p></details></section>}
    {!native && catalog && (hasKnownModelBoundary(catalog.execution_boundary) ? <ModelExecutionNotice /> : <ErrorNotice message="当前应用未提供可识别的运行权限说明，请更新应用后核对。下载及登记不代表模型已运行。" />)}
    {record && <section className="data-management" aria-label="模型下载进度"><div className="section-title"><h3>{record.name}</h3><Badge>{modelDownloadStates[record.state] || record.state}</Badge></div><p>{readableSize(record.received_bytes)} / {readableSize(record.total_bytes)}{record.current_file ? ` · ${record.current_file}` : ''}</p><progress aria-label="模型下载进度" max={record.total_bytes} value={record.received_bytes} />{record.cancel_requested && active.has(record.state) && <p>正在停止传输，已下载部分会保留。</p>}<ErrorNotice message={record.error?.message || ''} /><p className="muted">可以关闭此窗口，随后从模型库的“模型准备记录”继续。</p></section>}
    <ErrorNotice message={error} /><div className="dialog-actions">
      {pending.current && !busy ? <Button primary onClick={() => void execute(pending.current!)}>重试上次操作</Button> : !record ? <Button primary busy={busy} disabled={loading || (!selectionError && (!catalog || Boolean(catalog.selection_error)))} onClick={() => selectionError ? setReviewVersion(value => value + 1) : command('start')}>{selectionError ? '重新读取文件清单' : native ? '下载并核对所选文件' : '下载并核对固定模型'}</Button> : active.has(record.state) ? <Button busy={busy} disabled={record.cancel_requested} onClick={() => command('cancel')}>停止下载，保留进度</Button> : record.state !== 'completed' ? <Button primary busy={busy} onClick={() => command('resume')}>继续下载并核对</Button> : model ? <Button primary disabled={busy || (native && !model.execution_available)} onClick={() => onUse(model)}>{native && !model.execution_available ? '已加入当前项目模型库' : '用此模型开始试用'}</Button> : <Button primary busy={busy} onClick={() => command('models')}>加入当前项目模型库</Button>}
    </div>{model && <p role="status">{native ? '模型已登记。保存位置：' + model.path : '模型已登记到当前项目，尚未运行。可以输入自己的问题，或使用首次试用示例。'}</p>}
  </Dialog>;
}
