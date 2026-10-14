import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createInteractionRecording, inputAction } from '../../apps/desktop/src/InteractionTiming';

let deliver: (values: PerformanceEntry[], options?: { droppedEntriesCount: number }) => void;
let pending: PerformanceEntry[] = [];
let input: (event: Event) => void;
const disconnect = vi.fn();
beforeEach(() => {
  vi.useFakeTimers(); pending = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 16));
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  const add = document.addEventListener.bind(document);
  vi.spyOn(document, 'addEventListener').mockImplementation((name, listener, options) => {
    if (name === 'click') input = listener as (event: Event) => void;
    add(name, listener, options);
  });
  vi.stubGlobal('PerformanceObserver', class {
    static supportedEntryTypes = ['event'];
    constructor(callback: PerformanceObserverCallback) { deliver = (values, options) => (callback as Function)({ getEntries: () => values } as PerformanceObserverEntryList, this, options); }
    observe() {} takeRecords() { const values = pending; pending = []; return values; } disconnect = disconnect;
  });
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); disconnect.mockClear(); document.body.innerHTML = ''; });
function click(timeStamp = 12) {
  const target = document.createElement('button'); target.dataset.timingAction = 'open_task'; target.textContent = '私人任务与路径';
  return { isTrusted: true, type: 'click', timeStamp, target } as unknown as Event;
}
function entry(startTime = 12) { return { name: 'click', startTime, duration: 24, processingStart: 14, processingEnd: 19, interactionId: 7 } as PerformanceEntry; }
describe('本机交互记录', () => {
  it('只收集固定动作；拒绝脚本事件与任意类别', () => {
    expect(inputAction(new MouseEvent('click'))).toBeUndefined();
    const value = click(); (value.target as HTMLElement).dataset.timingAction = '私人操作';
    expect(inputAction(value)).toBeUndefined();
  });
  it('关联原生时间，未收到的输入保留为缺失且不收集文本', () => {
    const done = vi.fn(), recording = createInteractionRecording(done); vi.advanceTimersByTime(32);
    input(click()); input(click(99)); deliver([entry(), entry(1000)]);
    recording.stop(); expect(done).not.toHaveBeenCalled(); vi.runAllTimers();
    const report = JSON.parse(done.mock.calls[0][0]);
    expect(report.entries).toEqual([{ action: 'open_task', name: 'click', startTime: 12, duration: 24, processingStart: 14, processingEnd: 19, interactionId: 7 }]);
    expect(report.schema).toBe(2); expect(report.ready).toBe(true);
    expect(report.droppedEntriesCount).toBeNull(); expect(report.observerMode).toBe('live');
    expect(report.observedInputs).toHaveLength(2); expect(report.countsBefore).toBeNull();
    expect(report.unmatchedEntries).toHaveLength(1);
    expect(report.missing).toEqual([{ action: 'open_task', name: 'click', startTime: 99 }]);
    expect(done.mock.calls[0][0]).not.toContain('私人'); expect(disconnect).toHaveBeenCalledOnce();
  });
  it('停止等待期间不计新动作，重复停止只产生一份记录', () => {
    const done = vi.fn(), recording = createInteractionRecording(done); vi.advanceTimersByTime(32); input(click()); recording.stop(); recording.stop(); input(click(99)); vi.runAllTimers();
    expect(done).toHaveBeenCalledOnce(); expect(JSON.parse(done.mock.calls[0][0]).inputs).toHaveLength(1);
  });
  it('卸载或换库会丢弃待完成记录并移除监听', () => {
    const done = vi.fn(), remove = vi.spyOn(document, 'removeEventListener'); const recording = createInteractionRecording(done); vi.advanceTimersByTime(32);
    recording.stop(); recording.dispose(); vi.runAllTimers(); expect(done).not.toHaveBeenCalled(); expect(remove).toHaveBeenCalledWith('click', expect.any(Function), true);
  });
  it('失去可见性自动停止并标记，不能当作完整样本', () => {
    const done = vi.fn(); createInteractionRecording(done); vi.advanceTimersByTime(32); vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    document.dispatchEvent(new Event('visibilitychange')); vi.runAllTimers(); expect(JSON.parse(done.mock.calls[0][0])).toMatchObject({ hidden: true, reason: 'hidden' });
  });
  it('记录达到容量后明确结束，避免无限收集', () => {
    const done = vi.fn(); createInteractionRecording(done); vi.advanceTimersByTime(32); for (let i = 0; i < 1001; i++) input(click(i)); vi.runAllTimers();
    const report = JSON.parse(done.mock.calls[0][0]); expect(report.reason).toBe('limit'); expect(report.inputs).toHaveLength(1000);
  });
  it('系统不支持时明确失败', () => {
    vi.stubGlobal('PerformanceObserver', { supportedEntryTypes: [] }); expect(() => createInteractionRecording(vi.fn())).toThrow('当前系统未提供');
  });
  it('完成准备后才采样，记录完整浏览器总数与其他可信输入', () => {
    const counts = new Map(['pointerdown', 'pointerup', 'click', 'keydown', 'keyup'].map(name => [name, 0]));
    Object.defineProperty(performance, 'eventCounts', { configurable: true, value: counts });
    const ready = vi.fn(), done = vi.fn(), recording = createInteractionRecording(done, ready);
    expect(ready).not.toHaveBeenCalled(); vi.advanceTimersByTime(32); expect(ready).toHaveBeenCalledOnce();
    const other = click(40); (other.target as HTMLElement).removeAttribute('data-timing-action');
    input(other); counts.set('click', 1); input(click(80)); counts.set('click', 2);
    recording.stop(); vi.runAllTimers(); const report = JSON.parse(done.mock.calls[0][0]);
    expect(report.countsBefore.click).toBe(0); expect(report.countsAfter.click).toBe(2);
    expect(report.inputs).toHaveLength(1); expect(report.observedInputs).toHaveLength(2);
    expect(report.observedInputs[0].action).toBe('other');
    Reflect.deleteProperty(performance, 'eventCounts');
  });
  it('保留丢弃计数并在停止时接收尚未回调的系统事件', () => {
    const done = vi.fn(), recording = createInteractionRecording(done); vi.advanceTimersByTime(32);
    input(click()); deliver([], { droppedEntriesCount: 2 }); pending = [entry()];
    recording.stop(); vi.runAllTimers(); const report = JSON.parse(done.mock.calls[0][0]);
    expect(report.droppedEntriesCount).toBe(2); expect(report.entries).toHaveLength(1); expect(report.missing).toEqual([]);
  });
  it('准备阶段退出不会稍后重新安装监听或回调', () => {
    const done = vi.fn(), ready = vi.fn(), recording = createInteractionRecording(done, ready);
    recording.dispose(); vi.runAllTimers(); expect(ready).not.toHaveBeenCalled(); expect(done).not.toHaveBeenCalled();
  });

});
