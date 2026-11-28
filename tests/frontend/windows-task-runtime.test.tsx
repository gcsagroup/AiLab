import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { useState } from 'react';
import { TaskRuntimeNotice, taskLibraries, useTaskRuntime } from '../../apps/desktop/src/WindowsTaskRuntime';
import type { RuntimeAction, RuntimeStatus } from '../../apps/desktop/src/windowsWorkbenchApi';
import type { Kind } from '../../apps/desktop/src/types';

const original = window.ailabHF;
const installed = vi.fn();
afterEach(() => { cleanup(); window.ailabHF = original; installed.mockClear(); });

function Harness() {
  const [kind, select] = useState<Kind>('text');
  const runtime = useTaskRuntime(installed);
  return <>{(['text', 'image', 'audio'] as const).map(k =>
    <button key={k} onClick={() => { select(k); void runtime.prepare(taskLibraries(k).standard); }}>{k}</button>
  )}<TaskRuntimeNotice runtime={runtime} kind={kind} /></>;
}

function status(ready: string[], busy?: string): RuntimeStatus {
  return { root: 'runtime', nextRoot: 'runtime', selected: false, busy: !!busy, id: busy,
    phase: '正在下载', received: 1, total: 4,
    components: ['base','image-video','audio','text-cuda'].map(id => ({id, label:id, installed:ready.includes(id), detail:''})) };
}

test('a click reuses a ready component and each media pipeline selects the matching engine', async () => {
  const bridge = vi.fn(async () => status(['base','image-video','audio']));
  window.ailabHF = { runtime: bridge, request: vi.fn() };
  render(<Harness />);
  expect(bridge).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('image'));
  expect(await screen.findByText('已就绪，可在本机使用。')).toBeTruthy();
  expect(bridge.mock.calls).toEqual([['status']]);
  expect(taskLibraries('image')).toEqual(taskLibraries('video'));
  expect(taskLibraries('audio', 'llama-tts')).toEqual(taskLibraries('text'));
  expect(taskLibraries('audio', 'audiocpp-tts').cuda).toBe('audio-cuda');
});

test('missing components start automatically, display progress, cancel and retry on the task', async () => {
  let busy = false;
  let rejectDownload!: (error: Error) => void;
  let attempts = 0;
  const bridge = vi.fn(async (action: RuntimeAction, id?: string) => {
    if (action === 'cancel') { busy = false; rejectDownload(Error('已取消')); }
    if (action === 'prepare') {
      expect(id).toBe('base');
      if (++attempts > 1) return status(['base']);
      busy = true;
      return new Promise<RuntimeStatus>((_, reject) => { rejectDownload = reject; });
    }
    return status([], busy ? 'base' : undefined);
  });
  window.ailabHF = { runtime: bridge, request: vi.fn() };
  render(<Harness />);
  fireEvent.click(screen.getByText('text'));
  expect(await screen.findByText('正在下载 · 25%')).toBeTruthy();
  fireEvent.click(screen.getByText('text'));
  expect(attempts).toBe(1);
  fireEvent.click(screen.getByText('取消下载'));
  fireEvent.click(await screen.findByText('重试准备运行库'));
  expect(await screen.findByText('已就绪，可在本机使用。')).toBeTruthy();
  expect(bridge).toHaveBeenCalledWith('cancel', 'base');
  expect(installed).toHaveBeenCalledTimes(1);
});

test('the task can prepare its CUDA component before a CUDA device appears', async () => {
  const bridge = vi.fn(async (action: RuntimeAction, id?: string) =>
    status(action === 'prepare' && id === 'text-cuda' ? ['base','text-cuda'] : ['base']));
  window.ailabHF = { runtime: bridge, request: vi.fn() };
  render(<Harness />);
  fireEvent.click(screen.getByText('text'));
  fireEvent.click(await screen.findByText('准备 NVIDIA CUDA 加速库'));
  await screen.findByText('text-cuda');
  expect(bridge).toHaveBeenCalledWith('prepare', 'text-cuda');
  expect(await screen.findByText('已就绪，可在本机使用。')).toBeTruthy();
});

test('a late status response for the previous task cannot start its download or replace the current notice', async () => {
  let release!: (value: RuntimeStatus) => void;
  const bridge = vi.fn().mockImplementationOnce(() => new Promise(resolve => { release = resolve; }))
    .mockResolvedValue(status(['audio']));
  window.ailabHF = { runtime: bridge, request: vi.fn() };
  render(<Harness />);
  fireEvent.click(screen.getByText('text'));
  fireEvent.click(screen.getByText('audio'));
  await screen.findByText('已就绪，可在本机使用。');
  release(status([]));
  await waitFor(() => expect(bridge.mock.calls).toEqual([['status'],['status']]));
  expect(screen.getByRole('region', {name:'试用运行库'}).textContent).toContain('audio');
});
