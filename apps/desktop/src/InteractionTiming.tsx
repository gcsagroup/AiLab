import { useEffect, useRef, useState } from 'react';
import { APP_VERSION_LABEL } from './version';
import { Button, ErrorNotice } from './ui';

const actions = new Set(['navigate_models', 'open_settings', 'close_settings', 'open_task', 'preview_preset']);
const eventNames = ['pointerdown', 'pointerup', 'click', 'keydown', 'keyup'];
type Input = { action: string; name: string; startTime: number };
type Timing = Input & { duration: number; processingStart: number; processingEnd: number; interactionId: number };
type CountSnapshot = Record<string, number> | null;
type EventTiming = PerformanceEntry & { processingStart: number; processingEnd: number; interactionId: number };

// 仅固定类别与时间留在内存；不读取控件文字、输入值、对象编号或文件路径。
export function inputAction(event: Event): string | undefined {
  if (!event.isTrusted) return;
  if (event instanceof KeyboardEvent && event.key === 'Escape' && document.querySelector('dialog[open][aria-label="设备与环境"]')) return 'close_settings';
  const action = event.target instanceof Element ? event.target.closest('[data-timing-action]')?.getAttribute('data-timing-action') : null;
  return action && actions.has(action) ? action : undefined;
}

export function createInteractionRecording(onStopped: (report: string) => void, onReady: () => void = () => {}) {
  if (!globalThis.PerformanceObserver?.supportedEntryTypes.includes('event')) throw new Error('当前系统未提供原生事件计时，无法记录响应速度。');
  if (document.visibilityState !== 'visible') throw new Error('请先将应用置于前台，再开始响应记录。');
  const inputs: Input[] = [], observedInputs: Input[] = [], entries: Timing[] = [], unmatchedEntries: Omit<Timing, 'action'>[] = [];
  const countSnapshot = (): CountSnapshot => {
    const counts = (performance as Performance & { eventCounts?: ReadonlyMap<string, number> }).eventCounts;
    return counts && eventNames.every(name => counts.has(name)) ? Object.fromEntries(eventNames.map(name => [name, counts.get(name)!])) : null;
  };
  let countsBefore: CountSnapshot = null;
  let ready = false;
  let frame = 0;
  let droppedEntriesCount: number | null = null;
  const startedAt = new Date().toISOString();
  let finished = false;
  let stopTimer: ReturnType<typeof setTimeout> | undefined;
  let hidden = document.visibilityState !== 'visible';
  let reason = 'manual';
  function receive(values: PerformanceEntry[]) {
    for (const value of values) {
      const entry = value as EventTiming;
      if (!ready || !eventNames.includes(entry.name)) continue;
      const values = { name: entry.name, startTime: entry.startTime, duration: entry.duration, processingStart: entry.processingStart, processingEnd: entry.processingEnd, interactionId: entry.interactionId };
      const input = observedInputs.find(item => item.name === entry.name && Math.abs(item.startTime - entry.startTime) < 0.01);
      if (!input) {
        if (unmatchedEntries.length >= 1000) { reason = 'limit'; stop(); break; }
        unmatchedEntries.push(values); continue;
      }
      if (entries.length >= 1000) { reason = 'limit'; stop(); break; }
      entries.push({ ...input, duration: entry.duration, processingStart: entry.processingStart, processingEnd: entry.processingEnd, interactionId: entry.interactionId });
    }
  }
  const observer = new PerformanceObserver((list: PerformanceObserverEntryList, _observer: PerformanceObserver, options?: { droppedEntriesCount?: number }) => {
    if (options?.droppedEntriesCount !== undefined) droppedEntriesCount = Math.max(droppedEntriesCount ?? 0, options.droppedEntriesCount);
    receive(list.getEntries());
  });
  function input(event: Event) {
    if (finished || !ready || stopTimer !== undefined || !event.isTrusted) return;
    if (observedInputs.length >= 1000) { reason = 'limit'; stop(); return; }
    const action = inputAction(event);
    const value = { action: action ?? 'other', name: event.type, startTime: event.timeStamp };
    observedInputs.push(value);
    if (action) inputs.push(value);
  }
  function visibility() { if (document.visibilityState !== 'visible') { hidden = true; reason = 'hidden'; stop(); } }
  function dispose() {
    finished = true;
    if (stopTimer !== undefined) clearTimeout(stopTimer);
    cancelAnimationFrame(frame);
    observer.disconnect();
    eventNames.forEach(name => document.removeEventListener(name, input, true));
    document.removeEventListener('visibilitychange', visibility);
  }
  function stop() {
    if (finished || stopTimer !== undefined) return;
    // 先等待已有事件分发，再核对浏览器计数；未上报与计数不完整分开保留，均不填零。
    stopTimer = setTimeout(() => {
      receive(observer.takeRecords());
      const countsAfter = countSnapshot();
      dispose();
      const missing = inputs.filter(item => !entries.some(entry => entry.name === item.name && entry.startTime === item.startTime));
      onStopped(JSON.stringify({ schema: 2, version: APP_VERSION_LABEL, startedAt, endedAt: new Date().toISOString(), reason, hidden,
        thresholdMs: 16, note: '事件时长由系统量化。只有总数、匹配与分发完整性全部核对后，分析器才可把未上报事件作为阈值以下区间计算上界；不填零，不给出精确耗时。',
        ready, observerMode: 'live', countsBefore, countsAfter, droppedEntriesCount, observedInputs, inputs, entries, unmatchedEntries, missing }, null, 2));
    }, 250);
  }
  observer.observe({ type: 'event', durationThreshold: 16 } as PerformanceObserverInit);
  // 开始按钮本身也会进入浏览器计数。跨过一次渲染后取基线，避免把它误计为丢失事件。
  frame = requestAnimationFrame(() => { frame = requestAnimationFrame(() => {
    if (finished || stopTimer !== undefined) return;
    observer.takeRecords(); countsBefore = countSnapshot(); ready = true;
    eventNames.forEach(name => document.addEventListener(name, input, true)); onReady();
  }); });
  document.addEventListener('visibilitychange', visibility);
  return { stop, dispose };
}

export function useInteractionTiming() {
  const recording = useRef<ReturnType<typeof createInteractionRecording> | null>(null);
  const [active, setActive] = useState(false), [ready, setReady] = useState(false), [report, setReport] = useState(''), [error, setError] = useState('');
  useEffect(() => () => recording.current?.dispose(), []);
  function start() {
    if (recording.current) return;
    setError(''); setReport(''); setReady(false);
    try { recording.current = createInteractionRecording(value => { recording.current = null; setActive(false); setReport(value); }, () => setReady(true)); setActive(true); }
    catch (e) { setError(e instanceof Error ? e.message : '无法开始本机响应记录。'); }
  }
  return { active, ready, report, error, start, stop: () => recording.current?.stop() };
}

export function InteractionTimingControls({ timing }: { timing: ReturnType<typeof useInteractionTiming> }) {
  return <section aria-label="本机响应记录"><h4>本机响应记录</h4><p className="muted">临时记录模型库、设备窗口、任务和预设预览的响应时间。仅保留操作类别与时间，可选中结果自行保存；关闭应用或切换工作库后清空。</p>
    <Button onClick={timing.active ? timing.stop : timing.start}>{timing.active ? '停止并查看响应记录' : '开始响应记录'}</Button>
    {timing.active && <p role="status">{timing.ready ? '正在记录，可关闭此窗口并执行操作，完成后返回这里停止。' : '正在准备记录，请稍候。'}</p>}<ErrorNotice message={timing.error} />
    {timing.report && <label>响应记录结果<textarea aria-label="响应记录结果" readOnly rows={10} value={timing.report} /></label>}
  </section>;
}
