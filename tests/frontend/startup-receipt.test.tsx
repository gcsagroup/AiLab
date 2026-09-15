import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { useStartupReceipt } from '../../apps/desktop/src/Startup';
import { canPickFile, recordFirstFrame } from '../../apps/desktop/src/api';

vi.mock('../../apps/desktop/src/api', () => ({ canPickFile: vi.fn(), recordFirstFrame: vi.fn() }));
let callbacks: Map<number, FrameRequestCallback>, nextId: number, visibility: DocumentVisibilityState;
function Example({ ready, view = 'project_home' }: { ready: boolean; view?: 'project_home' | 'empty_library' }) { useStartupReceipt(ready, view); return <main>{ready ? '首屏已加载' : '正在加载'}</main>; }
function frame() { const pending = [...callbacks.values()]; callbacks.clear(); act(() => pending.forEach(callback => callback(0))); }
beforeEach(() => {
  callbacks = new Map(); nextId = 1; visibility = 'visible';
  vi.mocked(canPickFile).mockReturnValue(true); vi.mocked(recordFirstFrame).mockResolvedValue({});
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { const id = nextId++; callbacks.set(id, callback); return id; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => { callbacks.delete(id); });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it('数据完成并经过两帧后只记录首次首屏，后续刷新不覆盖', () => {
  const app = render(<Example ready={false} />); frame(); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
  app.rerender(<Example ready />); frame(); expect(recordFirstFrame).not.toHaveBeenCalled(); frame();
  expect(recordFirstFrame).toHaveBeenCalledExactlyOnceWith('project_home', expect.objectContaining({ events: expect.any(Array) }));
  app.rerender(<Example ready={false} />); app.rerender(<Example ready view="empty_library" />); frame(); frame();
  expect(recordFirstFrame).toHaveBeenCalledTimes(1);
});
it('隐藏窗口不记就绪，显示后重新等两帧', () => {
  visibility = 'hidden'; render(<Example ready view="empty_library" />); frame(); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
  visibility = 'visible'; act(() => document.dispatchEvent(new Event('visibilitychange'))); frame();
  expect(recordFirstFrame).not.toHaveBeenCalled(); frame(); expect(recordFirstFrame).toHaveBeenCalledExactlyOnceWith('empty_library', expect.objectContaining({ events: expect.any(Array) }));
});
it('第二帧前失去就绪或卸载时取消回执', () => {
  const app = render(<Example ready />); frame(); app.rerender(<Example ready={false} />); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
  app.rerender(<Example ready />); frame(); app.unmount(); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
});
it('普通浏览器不发送原生首屏计时命令', () => {
  vi.mocked(canPickFile).mockReturnValue(false); render(<Example ready />); frame(); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
});

it('同次记录区分数据等待、隐藏等待和两帧，计时采用前端单调时钟', () => {
  let elapsed = 10; vi.spyOn(performance, 'now').mockImplementation(() => elapsed);
  const app = render(<Example ready={false} />);
  elapsed = 20; visibility = 'hidden'; app.rerender(<Example ready />);
  elapsed = 30; visibility = 'visible'; act(() => document.dispatchEvent(new Event('visibilitychange')));
  elapsed = 40; frame(); elapsed = 50; frame();
  expect(recordFirstFrame).toHaveBeenCalledExactlyOnceWith('project_home', {
    time_origin_unix_ms: performance.timeOrigin, omitted_events: 0,
    events: [
      { stage: 'frontend_mounted', at_ms: 10 }, { stage: 'conditions_not_ready', at_ms: 10 },
      { stage: 'all_conditions_ready', at_ms: 20 }, { stage: 'hidden', at_ms: 20 },
      { stage: 'visible', at_ms: 30 }, { stage: 'first_animation_frame', at_ms: 40 },
      { stage: 'second_animation_frame', at_ms: 50 },
    ],
  });
});

it('反复失去就绪的记录有界且显式报告截断，仍需最后一次可见双帧', () => {
  const app = render(<Example ready={false} />);
  for (let i = 0; i < 40; i++) { app.rerender(<Example ready />); app.rerender(<Example ready={false} />); }
  frame(); frame(); expect(recordFirstFrame).not.toHaveBeenCalled();
  app.rerender(<Example ready />); frame(); frame();
  const detail = vi.mocked(recordFirstFrame).mock.calls[0][1];
  expect(detail.events).toHaveLength(64); expect(detail.omitted_events).toBeGreaterThan(0);
});
