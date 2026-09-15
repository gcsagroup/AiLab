import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import { useExitPreparation } from '../../apps/desktop/src/ExitPreparation';

const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { request_id: number; cancelled: boolean } }) => void) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn(async () => ({})) }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name === 'prepare-exit') host.listener = listener; return () => { host.listener = undefined; }; }) }));
function View({ prepare }: { prepare: () => Promise<void> }) { const state = useExitPreparation(prepare); return <div><span>{state.preparing ? '保存中' : '可编辑'}</span><p>{state.error}</p></div>; }
const deferred = () => { let resolve!: () => void; let reject!: (error: Error) => void; const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
async function emit(id: number, cancelled = false) { await act(async () => { host.listener!({ payload: { request_id: id, cancelled } }); }); }
beforeEach(() => { vi.mocked(invoke).mockClear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('宿主确认退出后等待保存，成功前不发送退出回执', async () => {
  const gate = deferred(); const save = vi.fn(() => gate.promise); render(<View prepare={save} />);
  await emit(1); expect(screen.getByText('保存中')).toBeTruthy(); expect(invoke).not.toHaveBeenCalled();
  await emit(1); expect(save).toHaveBeenCalledTimes(1);
  await act(async () => gate.resolve());
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 1, success: true }));
});

it('保存失败告诉宿主保留应用，恢复编辑并显示可处理的错误', async () => {
  render(<View prepare={async () => { throw new Error('磁盘暂不可写'); }} />);
  await emit(2);
  await screen.findByText('尚未退出：磁盘暂不可写'); expect(screen.getByText('可编辑')).toBeTruthy();
  expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 2, success: false });
});

it('宿主取消或超时后，迟到的保存成功不能继续退出', async () => {
  const gate = deferred(); render(<View prepare={() => gate.promise} />);
  await emit(3); await emit(3, true); expect(screen.getByText('可编辑')).toBeTruthy();
  await act(async () => gate.resolve()); expect(invoke).not.toHaveBeenCalled();
});

it('使用最新任务的保存函数；卸载后不发送旧请求回执', async () => {
  const first = vi.fn(async () => {}); const gate = deferred(); const second = vi.fn(() => gate.promise);
  const view = render(<View prepare={first} />); view.rerender(<View prepare={second} />);
  await emit(4); expect(first).not.toHaveBeenCalled(); expect(second).toHaveBeenCalledTimes(1);
  view.unmount(); await act(async () => gate.resolve()); expect(invoke).not.toHaveBeenCalled();
});
