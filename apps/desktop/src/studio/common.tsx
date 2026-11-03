import { useEffect, useId, useState, type ReactNode, type Dispatch, type SetStateAction } from 'react';
import { FolderOpen } from 'lucide-react';
import { api, canPickFile, errorMessage, pickStudioPath } from '../api';
import type { Asset } from './types';

export const request = <T,>(method: string, path: string, body?: unknown) => api<T>(method, `/studio${path}`, body);
export function useDraft<T>(key: string, fallback: T): [T, Dispatch<SetStateAction<T>>] {
  const [value, set] = useState<T>(() => { try { const saved = localStorage.getItem(`studio:${key}`); return saved ? { ...fallback, ...JSON.parse(saved) } : fallback; } catch { return fallback; } });
  useEffect(() => { localStorage.setItem(`studio:${key}`, JSON.stringify(value)); }, [key, value]);
  return [value, set];
}
export function Field({ title, children, hint }: { title: string; children: ReactNode; hint?: string }) {
  return <div className="st-field"><label><span>{title}</span>{children}</label>{hint && <small>{hint}</small>}</div>;
}
export function NumberField({ title, value, onChange, min, max, step = 1 }: { title: string; value: number; onChange: (v: number) => void; min?: number; max?: number; step?: number | 'any' }) {
  return <Field title={title}><input type="number" required value={value} min={min} max={max} step={step} onChange={e => onChange(e.target.valueAsNumber)} /></Field>;
}
export function PathField({ title, value, onChange, items = [], directory = true }: { title: string; value: string; onChange: (v: string) => void; items?: Asset[]; directory?: boolean }) {
  const id = useId(); const [error, setError] = useState('');
  return <div className="st-path"><Field title={title}><span className="st-input-action"><input value={value} list={id} placeholder="选择已登记资源，或输入本机绝对路径" onChange={e => onChange(e.target.value)} />{(canPickFile() || import.meta.env.DEV) && <button type="button" aria-label={`选择${title}`} onClick={() => { setError(''); void pickStudioPath(directory).then(v => { if (v) onChange(v); }).catch(e => setError(errorMessage(e))); }}><FolderOpen size={16} /></button>}</span><datalist id={id}>{items.map(a => <option key={a.path} value={a.path}>{a.name} · {a.format}</option>)}</datalist></Field>{error && <Error text={error} />}</div>;
}
export function Error({ text }: { text: string }) { return text ? <div className="st-error" role="alert">{text}</div> : null; }
export function Empty({ children }: { children: ReactNode }) { return <div className="st-empty">{children}</div>; }
export async function uploadImage(file: File): Promise<string> {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) throw new globalThis.Error('请选择 PNG、JPEG 或 WebP 图片');
  if (file.size > 20 * 1024 * 1024) throw new globalThis.Error('原始图片请控制在 20 MB 内');
  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * scale); canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL('image/jpeg', 0.82);
    if (data.length > 850000) throw new globalThis.Error('图片压缩后仍过大，请选择更小图片');
    return data;
  } finally { bitmap.close(); }
}
