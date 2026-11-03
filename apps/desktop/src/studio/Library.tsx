import { useEffect, useRef, useState } from 'react';
import { ImagePlus, Film, Image, X, ChevronDown, Filter, Play, Expand, Check, Trash2 } from 'lucide-react';
import { errorMessage } from '../api';
import { Empty, Error, request } from './common';
import type { Material } from './types';

export async function importMaterial(file: File, progress?: (value: number) => void): Promise<Material> {
  const upload = await request<{ id: string }>('POST', '/materials/uploads', { name: file.name, size: file.size });
  for (let offset = 0; offset < file.size; offset += 524288) {
    const bytes = new Uint8Array(await file.slice(offset, offset + 524288).arrayBuffer());
    let binary = ''; for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
    await request('POST', `/materials/uploads/${upload.id}/chunk`, { offset, data: btoa(binary) });
    progress?.(Math.round(Math.min(offset + bytes.length, file.size) / file.size * 100));
  }
  return request<Material>('POST', `/materials/uploads/${upload.id}/complete`, {});
}

export function MediaPreview({ id, empty = '生成结果将在这里显示', onDimensions }: { id?: string; empty?: string; onDimensions?: (width: number, height: number) => void }) {
  const [url, setUrl] = useState(''); const [mime, setMime] = useState(''); const [error, setError] = useState(''); const [progress, setProgress] = useState(0);
  useEffect(() => { let alive = true; let owned = ''; setUrl(''); setError(''); setProgress(0);
    if (id) void (async () => {
      const parts: BlobPart[] = []; let offset = 0; let size = 1; let type = '';
      while (offset < size && alive) {
        const chunk = await request<{ data: string; mime: string; size: number }>('GET', `/materials/${id}/content?offset=${offset}&length=524288`);
        if (chunk.size > 128 * 1024**2) throw new globalThis.Error('素材已保存；超过 128 MB 的文件请在素材文件夹中查看。');
        const bytes = Uint8Array.from(atob(chunk.data), c => c.charCodeAt(0)); if (!bytes.length) throw new globalThis.Error('素材内容不完整');
        parts.push(bytes); offset += bytes.length; size = chunk.size; type = chunk.mime;
        if (alive) setProgress(Math.round(offset / size * 100));
      }
      if (alive) { owned = URL.createObjectURL(new Blob(parts, { type })); setMime(type); setUrl(owned); }
    })().catch(e => { if (alive) setError(errorMessage(e)); });
    return () => { alive = false; if (owned) URL.revokeObjectURL(owned); };
  }, [id]);
  return <div className="st-preview-window"><Error text={error} />{url ? mime.startsWith('video/') ? <video onLoadedMetadata={e => onDimensions?.(e.currentTarget.videoWidth, e.currentTarget.videoHeight)} controls src={url} aria-label="视频预览" /> : <img onLoad={e => onDimensions?.(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)} src={url} alt="素材预览" /> : <Empty>{id ? `正在读取预览 ${progress}%` : empty}</Empty>}</div>;
}

function MaterialCard({ item, onOpen, onHold, selecting, checked, disabled }: { item: Material; onOpen: () => void; onHold?: () => void; selecting: boolean; checked: boolean; disabled: boolean }) {
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined); const held = useRef(false); const origin = useRef({x:0,y:0});
  const clearHold = () => { clearTimeout(timer.current); timer.current = undefined; };
  useEffect(() => clearHold, []);
  const element = useRef<HTMLButtonElement>(null); const [visible, setVisible] = useState(false);
  const [preview, setPreview] = useState(''); const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!element.current) return;
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); } }, { rootMargin: '180px' });
    observer.observe(element.current); return () => observer.disconnect();
  }, []);
  useEffect(() => { let alive = true;
    if (visible) void request<{ data_url: string }>('GET', `/materials/${item.id}/thumbnail`).then(r => { if (alive) setPreview(r.data_url); }).catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [visible, item.id]);
  return <button ref={element} className={`st-material-card${checked ? ' selected' : ''}`} disabled={disabled} aria-pressed={selecting ? checked : undefined}
    onPointerDown={e => { held.current = false; if (e.button !== 0 || !onHold || selecting) return; clearHold(); origin.current = {x:e.clientX,y:e.clientY}; timer.current = setTimeout(() => { held.current = true; onHold(); }, 500); }}
    onPointerMove={e => { if (Math.hypot(e.clientX-origin.current.x,e.clientY-origin.current.y)>8) clearHold(); }} onPointerUp={clearHold} onPointerCancel={clearHold} onPointerLeave={clearHold} onDragStart={e => { e.preventDefault(); clearHold(); }}
    onClick={() => { if (held.current) { held.current = false; return; } onOpen(); }} aria-label={`${selecting ? '选择' : '预览'} ${item.name}`}>
    <span className="st-material-cover">{preview ? <img src={preview} alt={item.name} loading="lazy" /> : <span className="st-thumbnail-placeholder">{item.kind === 'image' ? <Image size={26} /> : <Film size={26} />}<small>{failed ? '点击查看原文件' : '读取预览…'}</small></span>}
      <span className="st-cover-kind">{item.kind === 'image' ? <Image size={12} /> : <Film size={12} />}{item.kind === 'image' ? '图像' : '视频'}</span>
      <span className="st-cover-open" hidden={selecting}>{item.kind === 'video' ? <Play size={22} /> : <Expand size={19} />}</span>
      {selecting && <span className={`st-material-check${checked ? ' checked' : ''}`}>{checked && <Check size={16} />}</span>}
    </span><span className="st-material-caption"><strong title={item.name}>{item.name}</strong><span className="st-material-meta"><span className={`st-material-origin ${item.source}`}>{item.source === 'imported' ? '导入的' : '生成的'}</span><time>{new Date(item.created_at * 1000).toLocaleDateString()}</time></span></span>
  </button>;
}

function MaterialDialog({ item, onClose, onSelect }: { item: Material; onClose: () => void; onSelect?: (material: Material) => void }) {
  const dialog = useRef<HTMLDialogElement>(null); const [ratio, setRatio] = useState<number>();
  useEffect(() => { const node = dialog.current; node?.showModal(); return () => { node?.close(); }; }, []);
  return <dialog ref={dialog} className="st-material-dialog" style={ratio ? {width:`min(94vw, calc(65vh * ${ratio} + 44px))`} : undefined} aria-label={`素材预览：${item.name}`} onCancel={e => { e.preventDefault(); onClose(); }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}><div>
    <header><div><span>{item.kind === 'image' ? '图像' : '视频'} · {item.source === 'imported' ? '导入的' : '生成的'}</span><h2>{item.name}</h2></div><button autoFocus aria-label="关闭素材预览" onClick={onClose}><X size={20} /></button></header>
    <MediaPreview id={item.id} onDimensions={(w,h) => { if (w > 0 && h > 0) setRatio(w/h); }} /><div className="st-material-dialog-info"><time>{new Date(item.created_at * 1000).toLocaleString()}</time><span>{(item.size / 1024**2).toFixed(2)} MB</span>{onSelect && <button className="st-primary" onClick={() => onSelect(item)}>使用此图片</button>}</div>
    {Object.keys(item.parameters).length > 0 && <details><summary>生成参数</summary><pre className="st-code">{JSON.stringify(item.parameters, null, 2)}</pre></details>}
  </div></dialog>;
}

export default function Library({ imagesOnly = false, onSelect }: { imagesOnly?: boolean; onSelect?: (material: Material) => void }) {
  const [items, setItems] = useState<Material[]>([]); const [kind, setKind] = useState('all'); const [source, setSource] = useState('all'); const [selected, setSelected] = useState<Material>(); const [error, setError] = useState(''); const [upload, setUpload] = useState<number>();
  const [multi, setMulti] = useState(false); const [chosen, setChosen] = useState<Set<string>>(new Set()); const [deleting, setDeleting] = useState(false); const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if(confirmDelete) deleteDialog.current?.showModal(); }, [confirmDelete]);
  function toggle(id: string) { setChosen(previous => { const next = new Set(previous); if(next.has(id)) next.delete(id); else next.add(id); return next; }); }
  function exitMulti() { setMulti(false); setChosen(new Set()); setConfirmDelete(false); }
  async function removeSelected() { setDeleting(true); setError(''); const removed = new Set<string>(); const failures: string[] = []; for(const id of chosen) { try { await request('DELETE', `/materials/${id}`); removed.add(id); } catch(e) { failures.push(errorMessage(e)); } } setItems(current => current.filter(m => !removed.has(m.id))); setChosen(current => new Set([...current].filter(id => !removed.has(id)))); setConfirmDelete(false); setDeleting(false); if(!failures.length) exitMulti(); else setError(`已删除 ${removed.size} 项；${failures.join('；')}`); }
  function reload() { void request<{ items: Material[] }>('GET', '/materials').then(r => setItems(r.items)).catch(e => setError(errorMessage(e))); }
  useEffect(reload, []);
  async function ingest(files: FileList | null) { if (!files) return; setError(''); try { for (const file of Array.from(files)) { setUpload(0); await importMaterial(file, setUpload); } reload(); } catch (e) { setError(errorMessage(e)); } finally { setUpload(undefined); } }
  const filtered = items.filter(m => (!imagesOnly || m.kind === 'image') && (kind === 'all' || m.kind === kind) && (source === 'all' || m.source === source));
  return <section className="st-library"><div className="st-library-toolbar"><span className="st-library-count">{imagesOnly ? '选择参考图片 · ' : ''}{filtered.length} 项素材</span><div className="st-library-actions">{!onSelect && multi && <><span>已选 {chosen.size} 项</span><button disabled={deleting} onClick={() => setChosen(new Set(filtered.map(m => m.id)))}>全选当前素材</button><button disabled={deleting || !chosen.size} onClick={() => setConfirmDelete(true)}><Trash2 size={16} />删除所选</button><button disabled={deleting} onClick={exitMulti}>退出多选</button></>}<label className="st-upload st-library-import"><ImagePlus size={16} />{upload === undefined ? '导入素材' : `导入中 ${upload}%`}<input aria-label="导入素材" type="file" multiple disabled={upload !== undefined} accept={imagesOnly ? 'image/png,image/jpeg,image/webp' : 'image/png,image/jpeg,image/webp,video/mp4,video/webm'} onChange={e => { void ingest(e.target.files); e.target.value = ''; }} /></label>
    {!imagesOnly && <label className="st-library-select"><Image size={15} /><select aria-label="素材类型" value={kind} onChange={e => { setKind(e.target.value); exitMulti(); }} disabled={deleting}><option value="all">全部类型</option><option value="image">图像</option><option value="video">视频</option></select><ChevronDown size={14} /></label>}<label className="st-library-select"><Filter size={15} /><select aria-label="素材来源" value={source} onChange={e => { setSource(e.target.value); exitMulti(); }} disabled={deleting}><option value="all">全部来源</option><option value="imported">导入的</option><option value="generated">生成的</option></select><ChevronDown size={14} /></label></div></div><Error text={error} />
    {!filtered.length && <div className="st-library-empty"><ImagePlus size={32} /><Empty>{items.length ? '没有符合筛选条件的素材' : '导入图片或视频，开始整理你的素材'}</Empty></div>}<div className="st-material-grid">{filtered.map(m => <MaterialCard key={m.id} item={m} selecting={multi} checked={chosen.has(m.id)} disabled={deleting} onHold={onSelect ? undefined : () => { setMulti(true); setChosen(new Set([m.id])); }} onOpen={() => multi ? toggle(m.id) : setSelected(m)} />)}</div>
    {confirmDelete && <dialog ref={deleteDialog} className="st-delete-confirm" aria-label="删除所选素材" onCancel={e => { e.preventDefault(); if(!deleting) setConfirmDelete(false); }}><p>删除选中的 {chosen.size} 项素材？仅删除素材库副本，原始文件保留。</p><button disabled={deleting} onClick={() => setConfirmDelete(false)}>取消</button><button className="st-primary" disabled={deleting} onClick={() => void removeSelected()}>{deleting ? '正在删除…' : '确认删除'}</button></dialog>}
    {selected && <MaterialDialog key={selected.id} item={selected} onClose={() => setSelected(undefined)} onSelect={onSelect} />}
  </section>;
}
