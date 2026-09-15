import { useEffect, useRef, useState } from 'react';
import { Download, Pencil, Plus, Save } from 'lucide-react';
import { api, errorMessage } from './api';
import { MediaPreview } from './Media';
import type { Work } from './types';
import { Badge, Button, Dialog, ErrorNotice, formatDate } from './ui';

type Cue = { start_ms: number; end_ms: number; text: string };
type Content = { text: string } | { cues: Cue[] };
type Revision = { id: string; work_id: string; parent_revision_id: string | null; revision: number; content_kind: ContentKind; content: Content; artifact_id: string; editor: 'user_action'; created_at: string; changes: { diff: string }; source_artifact_sha256: string };
type ContentKind = 'text' | 'voice_script' | 'subtitles';
type View = { work_id: string; work_revision: number; current_revision_id: string | null; content_kind: ContentKind; duration_ms: number | null; original: { revision_id: null; artifact_id: string; sha256: string; content: Content; basis: string }; items: Revision[]; has_more: boolean; next_before_revision: number | null; media_policy: string };
type SaveBody = { expected_revision: number; parent_revision_id: string | null; content_kind: ContentKind; content: Content };
type Saved = { work: { revision: number; current_revision_id: string | null }; revision: Revision };
type EditorCue = { start: string; end: string; text: string };
export type WorkRevisionExport = { work_revision_id: string | null; name: string };
const labels: Record<ContentKind, string> = { text: '正文', voice_script: '配音文案', subtitles: '外置字幕' };
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const characterCount = (value: string) => Array.from(value).length;

function failureCode(value: unknown): string | undefined {
  if (typeof value === 'string') { try { return failureCode(JSON.parse(value)); } catch { return undefined; } }
  return value && typeof value === 'object' && 'error' in value ? (value as { error?: { code?: string } }).error?.code : undefined;
}
function seconds(value: number) { return (value / 1000).toFixed(3); }
function milliseconds(value: string) {
  if (!/^\d+(\.\d{1,3})?$/.test(value)) throw new Error('字幕时间请输入非负秒数，最多三位小数。');
  const [whole, fraction = ''] = value.split('.');
  const result = Number(whole) * 1000 + Number(fraction.padEnd(3, '0'));
  if (!Number.isSafeInteger(result)) throw new Error('字幕时间超出范围。');
  return result;
}

export function WorkRevisions({ work, onClose, onUpdated, onExport }: { work: Work; onClose: () => void; onUpdated: () => void; onExport: (selection: WorkRevisionExport) => void }) {
  const [view, setView] = useState<View | null>(null);
  const [selected, setSelected] = useState('original');
  const [text, setText] = useState(''); const [cues, setCues] = useState<EditorCue[]>([]);
  const [editing, setEditing] = useState(false); const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false); const [conflict, setConflict] = useState(false); const [refreshNeeded, setRefreshNeeded] = useState(false);
  const [error, setError] = useState(''); const [message, setMessage] = useState(''); const [confirmClose, setConfirmClose] = useState(false);
  const pending = useRef<{ body: SaveBody; key: string } | null>(null); const epoch = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null); const editorRef = useRef<HTMLElement>(null);
  const lastEditorInput = useRef<HTMLElement | null>(null);
  const requestedFocus = useRef<'initial' | 'editor' | 'view' | 'confirm' | 'resume' | null>(null);
  const revision = view?.items.find(item => item.id === selected);
  const chosenContent = revision?.content || view?.original.content;
  const isCurrent = !!view && selected === (view.current_revision_id || 'original');
  const locked = busy || uncertain;

  function focusControl(target: HTMLElement | null) {
    if (!target?.isConnected || target.matches(':disabled')) return;
    target.focus(); target.scrollIntoView?.({ block: 'nearest' });
  }
  useEffect(() => {
    if (busy || !requestedFocus.current) return;
    const request = requestedFocus.current; requestedFocus.current = null;
    const root = contentRef.current, editor = editorRef.current, previous = lastEditorInput.current;
    const firstEditorControl = editor?.querySelector<HTMLElement>('input:not(:disabled), textarea:not(:disabled), button:not(:disabled)') || null;
    if (request === 'initial') {
      const dialog = root?.closest('dialog'), active = document.activeElement;
      // 首次读取会暂时禁用关闭按钮；只补救由此失效的焦点，不抢走用户已选的控件。
      if (dialog?.open && (active === document.body || active === document.documentElement
        || (active instanceof HTMLElement && dialog.contains(active) && active.matches(':disabled')))) {
        dialog.querySelector<HTMLButtonElement>('.dialog-title button:not(:disabled)')?.focus({ preventScroll: true });
      }
    } else if (request === 'confirm') focusControl(root?.querySelector('[data-revision-action="continue"]') || null);
    else if (request === 'view') focusControl(root?.querySelector('[data-revision-action="edit"]:not(:disabled), [data-revision-action="refresh"]:not(:disabled)') || root?.querySelector('select:not(:disabled)') || null);
    else focusControl(request === 'resume' && previous && editor?.contains(previous) && !previous.matches(':disabled') ? previous : firstEditorControl);
  }, [busy, editing, confirmClose, refreshNeeded, selected, view]);

  function fill(content: Content) {
    setText('text' in content ? content.text : '');
    setCues('cues' in content ? content.cues.map(cue => ({ start: seconds(cue.start_ms), end: seconds(cue.end_ms), text: cue.text })) : []);
  }
  useEffect(() => {
    const generation = ++epoch.current;
    setView(null); setSelected('original'); setEditing(false); setBusy(true); setUncertain(false); setConflict(false); setRefreshNeeded(false); setError(''); setMessage(''); setConfirmClose(false); pending.current = null;
    requestedFocus.current = null; lastEditorInput.current = null;
    api<View>('GET', `/works/${work.id}/revisions?limit=100`).then(value => {
      if (epoch.current !== generation) return;
      setView(value); setSelected(value.current_revision_id || 'original');
    }).catch(value => { if (epoch.current === generation) setError(errorMessage(value)); }).finally(() => {
      if (epoch.current === generation) { requestedFocus.current = 'initial'; setBusy(false); }
    });
    return () => { epoch.current++; };
  }, [work.id]);

  async function refresh() {
    const generation = epoch.current; setBusy(true); setError('');
    try {
      const value = await api<View>('GET', `/works/${work.id}/revisions?limit=100`);
      if (generation !== epoch.current) return;
      requestedFocus.current = 'view'; setConfirmClose(false);
      setView(value); setSelected(value.current_revision_id || 'original'); setEditing(false); setConflict(false); setRefreshNeeded(false); setMessage('已读取当前保存版本。');
    } catch (value) { if (generation === epoch.current) setError(errorMessage(value)); }
    finally { if (generation === epoch.current) setBusy(false); }
  }
  async function loadEarlier() {
    if (!view || !view.has_more || view.next_before_revision == null || locked || editing || refreshNeeded) return;
    const generation = epoch.current; setBusy(true); setError('');
    try {
      const value = await api<View>('GET', `/works/${work.id}/revisions?limit=100&before_revision=${view.next_before_revision}`);
      if (generation !== epoch.current) return;
      if (value.work_id !== view.work_id || value.work_revision !== view.work_revision || value.current_revision_id !== view.current_revision_id) {
        setRefreshNeeded(true); setError('作品已有新修订，请重新读取当前版本后继续。'); return;
      }
      // 只补较早记录，保留用户正在查看的版本和首次读取的当前版本身份。
      const loaded = new Set(view.items.map(item => item.id));
      setView({ ...view, items: [...value.items.filter(item => !loaded.has(item.id)), ...view.items], has_more: value.has_more, next_before_revision: value.next_before_revision });
    } catch (value) { if (generation === epoch.current) setError(errorMessage(value)); }
    finally { if (generation === epoch.current) setBusy(false); }
  }
  function startEditing() {
    if (!view || !isCurrent || locked || refreshNeeded) return;
    requestedFocus.current = 'editor'; lastEditorInput.current = null; setConfirmClose(false);
    fill(chosenContent!); setEditing(true); setConflict(false); setError(''); setMessage(''); pending.current = null;
  }
  function cancelEditing() {
    if (locked) return;
    requestedFocus.current = 'view'; lastEditorInput.current = null; setConfirmClose(false);
    setEditing(false); setConflict(false); setError(''); pending.current = null;
  }
  function content(): Content {
    if (!view) throw new Error('请先读取作品版本。');
    if (view.content_kind !== 'subtitles') {
      if (!text.trim() || characterCount(text) > 16000) throw new Error('修订文字不能为空，最多 16000 字符。');
      return { text };
    }
    let end = 0; let total = 0;
    const result = cues.map(cue => {
      const start_ms = milliseconds(cue.start), end_ms = milliseconds(cue.end);
      if (start_ms < end || start_ms >= end_ms || view.duration_ms === null || end_ms > view.duration_ms) throw new Error('字幕须按时间排序、不重叠，并在原视频时长内。');
      if (!cue.text.trim() || characterCount(cue.text) > 500) throw new Error('每条字幕不能为空，最多 500 字符。');
      end = end_ms; total += characterCount(cue.text);
      return { start_ms, end_ms, text: cue.text };
    });
    if (result.length > 200 || total > 16000) throw new Error('最多 200 条字幕，总文字最多 16000 字符。');
    return { cues: result };
  }
  async function save() {
    if (!view || busy || conflict || refreshNeeded) return;
    const generation = epoch.current; setBusy(true); setError(''); setMessage('');
    try {
      pending.current ||= { body: { expected_revision: view.work_revision, parent_revision_id: view.current_revision_id, content_kind: view.content_kind, content: clone(content()) }, key: crypto.randomUUID() };
      const saved = await api<Saved>('POST', `/works/${work.id}/revisions`, pending.current.body, pending.current.key);
      if (generation !== epoch.current) return;
      pending.current = null; requestedFocus.current = 'view'; setConfirmClose(false); setUncertain(false); setEditing(false);
      setView(current => current ? { ...current, items: [...current.items.filter(item => item.id !== saved.revision.id), saved.revision] } : current);
      setSelected(saved.revision.id); setMessage('独立修订版本已保存，原生成输出与配方保持原样。'); onUpdated();
      try {
        const current = await api<View>('GET', `/works/${work.id}/revisions?limit=100`);
        if (generation === epoch.current) { setView(current); setRefreshNeeded(false); }
      } catch (value) {
        if (generation === epoch.current) { setRefreshNeeded(true); setError('修订已保存，但当前版本读取失败。' + errorMessage(value)); }
      }
    } catch (value) {
      if (generation !== epoch.current) return;
      const code = failureCode(value);
      if (code) { pending.current = null; setUncertain(false); setConflict(code === 'REVISION_CONFLICT'); }
      else if (pending.current) setUncertain(true);
      setError(errorMessage(value));
    } finally { if (generation === epoch.current) setBusy(false); }
  }
  function addCue() {
    if (!view || view.duration_ms === null || cues.length >= 200) return;
    let start = 0;
    try { if (cues.length) start = milliseconds(cues.at(-1)!.end); } catch { setError('请先填好上一条字幕的结束时间。'); return; }
    if (start >= view.duration_ms) { setError('已到视频末尾，请先调整上一条字幕的结束时间。'); return; }
    setCues([...cues, { start: seconds(start), end: seconds(Math.min(start + 1000, view.duration_ms)), text: '' }]);
  }
  function updateCue(index: number, field: keyof EditorCue, value: string) { setCues(current => current.map((cue, at) => at === index ? { ...cue, [field]: value } : cue)); }
  function close() {
    if (editing || uncertain) {
      if (confirmClose) focusControl(contentRef.current?.querySelector('[data-revision-action="continue"]') || null);
      else { requestedFocus.current = 'confirm'; setConfirmClose(true); }
    } else onClose();
  }
  const versionName = revision ? `修订版 ${revision.revision}` : '原版';

  return <Dialog title={`${work.name || '作品'} · 人工修订`} wide preventClose={busy} onClose={close}>
    <div ref={contentRef} className="form-stack work-revisions">
      <p className="muted">查看原版和人工修订记录。保存修订不会运行模型；载入生成配方仍使用原始生成参数。</p>
      {work.artifact_id && (work.media_type === 'video/mp4' || work.media_type === 'audio/wav') && <><MediaPreview artifact={{ id: work.artifact_id, media_type: work.media_type }} name="原始生成媒体" /><p className="warning">播放器始终播放原始媒体。修改配音文案不会改变声音；字幕以独立文件保存，不会烧录进视频。</p></>}
      {!view && busy && <p role="status">正在读取作品版本…</p>}
      {view && <>
        <div className="section-title"><h3>{labels[view.content_kind]}</h3><Badge>{refreshNeeded ? '待重新读取' : isCurrent ? '当前版本' : '历史查看'}</Badge></div>
        <label>查看版本<select aria-label="查看作品版本" value={selected} disabled={editing || locked} onChange={event => { setSelected(event.target.value); setMessage(''); setError(''); }}>
          <option value="original">原版{view.content_kind === 'voice_script' ? '（生成时的配音文案）' : view.content_kind === 'subtitles' ? '（没有独立字幕）' : '（模型输出）'}{!refreshNeeded && !view.current_revision_id ? ' · 当前' : ''}</option>
          {view.items.map(item => <option value={item.id} key={item.id}>修订版 {item.revision}{!refreshNeeded && item.id === view.current_revision_id ? ' · 当前' : ''} · {formatDate(item.created_at)}</option>)}
        </select></label>
        {view.has_more && <Button disabled={editing || locked || refreshNeeded || view.next_before_revision == null} onClick={loadEarlier}>加载更早版本</Button>}
        {view.content_kind === 'subtitles' && <p className="muted">原视频时长：{view.duration_ms === null ? '无法确认，不能编辑时间' : `${seconds(view.duration_ms)} 秒`}。原版没有独立字幕文件，新增内容记为人工字幕。</p>}
        {chosenContent && <section className="review-box" aria-label="已保存版本内容"><h3>{versionName}</h3>{'text' in chosenContent ? <pre>{chosenContent.text || '（原版没有文字）'}</pre> : chosenContent.cues.length ? <ol>{chosenContent.cues.map((cue, index) => <li key={index}><strong>{seconds(cue.start_ms)}—{seconds(cue.end_ms)} 秒</strong><pre>{cue.text}</pre></li>)}</ol> : <p>原版没有独立字幕。</p>}</section>}
        {revision && <><dl className="facts"><div><dt>父版本</dt><dd>{revision.parent_revision_id ? `修订版 ${view.items.find(item => item.id === revision.parent_revision_id)?.revision || revision.parent_revision_id}` : '原版'}</dd></div><div><dt>编辑者</dt><dd>本人手动编辑</dd></div><div><dt>保存时间</dt><dd>{formatDate(revision.created_at)}</dd></div></dl><details open><summary>与父版本的差异</summary><pre aria-label="修订差异">{revision.changes.diff}</pre></details></>}
        {!editing && <><Button data-revision-action="edit" disabled={locked || !isCurrent || refreshNeeded} onClick={startEditing}><Pencil size={16} />编辑当前版本</Button>{!isCurrent && <p className="muted">当前正在查看历史内容。请先选择当前版本，再继续修订；旧版本不会自动改挂为新版本的父版本。</p>}</>}
        {editing && <section ref={editorRef} onFocusCapture={event => { if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) lastEditorInput.current = event.target; }} className="review-box form-stack" aria-label="修订编辑器"><h3>编辑{labels[view.content_kind]}</h3><p className="muted">本次父版本：{view.current_revision_id ? `修订版 ${view.work_revision}` : '原版'}。保存后会新增独立版本。</p>
          <p className="muted">超出上限时输入会完整保留，调整后才能保存。</p>
          {view.content_kind !== 'subtitles' ? <label>修订{labels[view.content_kind]}<textarea aria-label={`修订${labels[view.content_kind]}`} rows={8} value={text} disabled={locked} onChange={event => setText(event.target.value)} /><small className="muted">{characterCount(text)} / 16000 字符</small></label> : <>
            <p className="muted">{cues.length} / 200 条字幕，总文字 {cues.reduce((total, cue) => total + characterCount(cue.text), 0)} / 16000 字符。</p>
            {cues.map((cue, index) => <fieldset key={index} disabled={locked}><legend>第 {index + 1} 条字幕</legend><label>开始（秒）<input aria-label={`第${index + 1}条字幕开始（秒）`} type="number" min="0" step="0.001" value={cue.start} onChange={event => updateCue(index, 'start', event.target.value)} /></label><label>结束（秒）<input aria-label={`第${index + 1}条字幕结束（秒）`} type="number" min="0" step="0.001" value={cue.end} onChange={event => updateCue(index, 'end', event.target.value)} /></label><label>字幕文字<textarea aria-label={`第${index + 1}条字幕文字`} rows={2} value={cue.text} onChange={event => updateCue(index, 'text', event.target.value)} /><small className="muted">{characterCount(cue.text)} / 500 字符</small></label><Button onClick={() => setCues(current => current.filter((_, at) => at !== index))}>移除第 {index + 1} 条</Button></fieldset>)}
            <Button disabled={locked || cues.length >= 200} onClick={addCue}><Plus size={16} />添加字幕</Button>
          </>}
          {uncertain && <p className="warning">保存回执尚未确认。输入已保留；重试只核实同一次保存，不创建重复版本。</p>}
          <Button primary busy={busy} disabled={conflict || refreshNeeded} onClick={save}><Save size={16} />{uncertain ? '重试保存回执' : '保存独立修订版本'}</Button>
          {conflict ? <><p className="warning">已有其他修订，本次输入保留。不能覆盖当前版本或自动更换父版本。</p><Button disabled={locked} onClick={refresh}>放弃本次编辑，读取当前版本</Button></> : <Button disabled={locked} onClick={cancelEditing}>取消本次编辑</Button>}
        </section>}
        <Button disabled={busy || editing || uncertain || refreshNeeded} onClick={() => onExport({ work_revision_id: selected === 'original' ? null : selected, name: `${work.name || '作品'} · ${versionName}` })}><Download size={16} />导出所选{versionName}</Button>
        <p className="muted">原版导出只包含原输出。修订版导出保留原媒体和独立文字／字幕文件及修订记录。</p>
      </>}
      {message && <p role="status">{message}</p>}
      <ErrorNotice message={error} />
      {(!view || refreshNeeded) && !busy && <Button data-revision-action="refresh" onClick={refresh}>重新读取作品版本</Button>}
      {confirmClose && <section className="review-box" role="alert"><p>{uncertain ? '保存结果尚未确认；关闭后可重新打开查看服务器保存的版本。' : '还有未保存的编辑。'}</p><Button data-revision-action="continue" disabled={busy} onClick={() => { requestedFocus.current = 'resume'; setConfirmClose(false); }}>继续核对</Button><Button disabled={busy} onClick={onClose}>{uncertain ? '关闭窗口，稍后核实' : '放弃未保存编辑并关闭'}</Button></section>}
    </div>
  </Dialog>;
}
