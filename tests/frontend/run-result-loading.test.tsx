import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { RunResult } from '../../apps/desktop/src/Workbench';
import type { Attempt } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

// 与公开列表一致：摘要不包含 snapshot、artifacts 或 output_text。
const summary: Attempt = { id: 'loading-attempt', task_id: 'task-a', project_id: 'project-a', state: 'succeeded', state_version: 4, allowed_actions: [] };
const response = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(yes => { resolve = yes; });
  return { promise, resolve };
}

it.each([
  ['evaluate', '评测执行完成'],
  ['train', '训练产物已保存'],
  ['quantize', '量化产物已保存'],
  ['generate', '本次没有可显示的媒体结果'],
])('运行摘要等待 %s 详情和事件时不提前判定空输出', async (operation, title) => {
  const detail = deferred(), events = deferred();
  vi.stubGlobal('fetch', vi.fn((url: string) => String(url).includes('/events?') ? events.promise : detail.promise));
  const updated = vi.fn();
  render(<RunResult initial={summary} onChanged={vi.fn()} onAttemptUpdated={updated} />);
  expect(screen.getByText('正在读取运行记录')).toBeTruthy();
  expect(screen.queryByText('本次没有文本输出')).toBeNull();
  expect(screen.queryByText('运行详情与配方')).toBeNull();
  await act(async () => detail.resolve(response({ ...summary, snapshot: { kind: 'image', operation }, artifacts: [] })));
  expect(screen.getByText('正在读取运行记录')).toBeTruthy();
  expect(updated).not.toHaveBeenCalled();
  await act(async () => events.resolve(response({ items: [] })));
  expect(screen.getByText(title)).toBeTruthy();
  expect(screen.queryByText('正在读取运行记录')).toBeNull();
  expect(screen.getByText('运行详情与配方')).toBeTruthy();
  expect(updated).toHaveBeenCalledTimes(1);
});

it('详情读取失败显示读取错误，自动重试后展示实际输出', async () => {
  vi.useFakeTimers(); let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/events?')) return response({ items: [] });
    if (++reads === 1) throw new Error('测试读取断线');
    return response({ ...summary, snapshot: { kind: 'text', operation: 'generate' }, output_text: '历史真实正文', artifacts: [] });
  }));
  render(<RunResult initial={summary} onChanged={vi.fn()} />);
  await act(async () => {});
  expect(screen.getByText('运行记录暂时无法读取')).toBeTruthy();
  expect(screen.getByText('测试读取断线')).toBeTruthy();
  expect(screen.queryByText('本次没有文本输出')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByText('历史真实正文')).toBeTruthy();
  expect(screen.queryByText('运行记录暂时无法读取')).toBeNull();
  expect(screen.queryByText('测试读取断线')).toBeNull();
});

it('等待详情时仍保留摘要允许的停止操作', () => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})));
  render(<RunResult initial={{ ...summary, state: 'running', allowed_actions: ['cancel'] }} onChanged={vi.fn()} />);
  expect(screen.getByText('正在读取运行记录')).toBeTruthy();
  expect(screen.getByRole('button', { name: '停止运行' }).matches(':disabled')).toBe(false);
  expect(screen.queryByText('本次没有文本输出')).toBeNull();
});

it('本机停止待核实不假定控制服务曾经退出，核实入口仍可用', async () => {
  const interrupted: Attempt = { ...summary, state: 'running', recovery_required: true, stop_status: 'unknown',
    snapshot: { kind: 'video', operation: 'generate' }, artifacts: [], allowed_actions: ['reconcile'] };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => response(String(url).includes('/events?') ? { items: [] } : interrupted)));
  render(<RunResult initial={interrupted} onChanged={vi.fn()} />);
  await act(async () => {});
  expect(screen.getByText('本机执行状态待核实，需要确认原进程是否退出。核实不会重新执行任务。')).toBeTruthy();
  expect(screen.queryByText(/控制服务曾中断/)).toBeNull();
  expect(screen.getByRole('button', { name: '核实原进程' }).matches(':disabled')).toBe(false);
  expect(screen.queryByRole('button', { name: '保存作品' })).toBeNull();
});

it.each(['image', 'video', 'audio'])('%s 失败时说明没有媒体结果并保留实际失败原因', async kind => {
  const failed: Attempt = { ...summary, state: 'failed', snapshot: { kind, operation: 'generate' }, artifacts: [],
    error: { message: '已核实原执行进程退出；保留中断事实，可创建新的运行。' } };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => response(String(url).includes('/events?') ? { items: [] } : failed)));
  render(<RunResult initial={failed} onChanged={vi.fn()} />);
  await act(async () => {});
  const body = screen.getByRole('heading', { name: '本次没有可显示的媒体结果' }).parentElement!;
  expect(body.textContent).toContain(failed.error!.message);
  expect(screen.queryByText('本次没有文本输出')).toBeNull();
  expect(screen.queryByRole('button', { name: '保存作品' })).toBeNull();
});
