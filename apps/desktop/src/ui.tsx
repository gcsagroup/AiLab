import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { X, LoaderCircle } from 'lucide-react';

export function Button({ children, busy, primary, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean; primary?: boolean }) {
  // 显式参与宿主键盘顺序，同时保留调用方指定的顺序或排除值。
  return <button {...props} tabIndex={props.tabIndex ?? 0} type={props.type || 'button'} className={`button ${primary ? 'primary' : ''} ${props.className || ''}`} disabled={props.disabled || busy}>
    {busy && <LoaderCircle size={16} className="spin" aria-hidden="true" />}{children}
  </button>;
}
export function PaginationButton({ label, hasMore, busy, onLoad }: { label: string; hasMore: boolean; busy: boolean; onLoad: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const wasBusy = useRef(false);
  const [requested, setRequested] = useState(false);
  useLayoutEffect(() => {
    // 只跟随仍在入口上的焦点，不打断用户在等待期间进行的其他操作。
    if (wasBusy.current && !busy && document.activeElement === ref.current) {
      ref.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
    wasBusy.current = busy;
  }, [busy, hasMore]);
  if (!hasMore && !requested) return null;
  return <button ref={ref} type="button" tabIndex={0} className="button" aria-disabled={busy || !hasMore} aria-busy={busy} onClick={() => {
    if (busy || !hasMore) return;
    setRequested(true); onLoad();
  }}>{hasMore ? '加载更多' : '已加载全部'}{label}</button>;
}
export function Dialog({ title, children, onClose, wide, preventClose }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean; preventClose?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal();
    return () => { dialog.close(); if (opener?.isConnected) opener.focus(); };
  }, []);
  return <dialog ref={ref} tabIndex={-1} className={wide ? 'dialog wide' : 'dialog'} onKeyDown={event => {
    if (event.key !== 'Tab') return;
    const dialog = event.currentTarget;
    const controls = Array.from(dialog.querySelectorAll<HTMLElement>('a[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]'))
      .filter(element => element.tabIndex >= 0 && !element.matches(':disabled') && !element.closest('[inert]') && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden');
    const first = controls[0], last = controls[controls.length - 1];
    if (!first) { event.preventDefault(); dialog.focus(); }
    else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) { event.preventDefault(); first.focus(); }
  }} onCancel={event => { event.preventDefault(); if (!preventClose) onClose(); }} aria-label={title}>
    <div className="dialog-title"><h2>{title}</h2><button tabIndex={0} type="button" className="icon-button" aria-label="关闭对话框" data-timing-action={title === '设备与环境' ? 'close_settings' : undefined} disabled={preventClose} onClick={onClose}><X size={18} /></button></div>
    <div className="dialog-content">{children}</div>
  </dialog>;
}
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty"><span className="empty-mark" aria-hidden="true">◇</span><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>;
}
export function ErrorNotice({ message }: { message: string }) { return message ? <div className="error" role="alert">{message}</div> : null; }
export function Badge({ children, tone = '' }: { children: ReactNode; tone?: string }) { return <span className={`badge ${tone}`}>{children}</span>; }
export const stateNames: Record<string, string> = { queued: '排队中', preparing: '准备中', running: '运行中', pausing: '正在暂停', paused: '已暂停', resuming: '正在继续', cancelling: '正在停止', finalizing: '保存产物中', succeeded: '已完成', failed: '执行失败', cancelled: '已取消', draft: '草稿' };
export const activeStates = new Set(['queued', 'preparing', 'running', 'pausing', 'paused', 'resuming', 'cancelling', 'finalizing']);
export const formatDate = (value?: string) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
export function readableSize(bytes?: number) {
  if (bytes === undefined || !Number.isFinite(bytes)) return '待核对';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}
