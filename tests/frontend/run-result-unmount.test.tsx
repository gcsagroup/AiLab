import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RunResult } from '../../apps/desktop/src/Workbench';
import type { Attempt } from '../../apps/desktop/src/types';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('旧 RunResult 卸载后迟到的 attempts 响应不能继续启动 events 请求', async () => {
  const attempt = { id: 'attempt-a', task_id: 'task-a', state: 'succeeded', state_version: 1, artifacts: [], allowed_actions: [], snapshot: { kind: 'text', operation: 'generate' } } as unknown as Attempt;
  const calls: string[] = []; let finish!: (response: Response) => void;
  const response = (value: unknown) => ({ ok: true, json: async () => value }) as Response;
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    calls.push(String(input));
    if (String(input) === '/api/v1/attempts/attempt-a') return await new Promise<Response>(resolve => { finish = resolve; });
    return response({ items: [] });
  }));
  const changed = vi.fn(); const app = render(<RunResult initial={attempt} onChanged={changed} />);
  await waitFor(() => expect(finish).toBeTypeOf('function')); app.unmount();
  await act(async () => finish(response(attempt)));
  expect(calls).toEqual(['/api/v1/attempts/attempt-a']); expect(changed).not.toHaveBeenCalled();
});

it('共享运行结果拒绝失效事件，待决期间不启动新读，解门禁后恢复 A 轮询', async () => {
  vi.useFakeTimers(); let epoch = 0; let switching = false; let reads = 0; let finish!: (value: Response) => void;
  const capture = () => { const expected = epoch; return () => !switching && expected === epoch; };
  const attempt = { id: 'attempt-scope', state: 'succeeded', state_version: 1, artifacts: [], allowed_actions: [], snapshot: { kind: 'text', operation: 'generate' } } as unknown as Attempt;
  const response = (value: unknown) => ({ ok: true, json: async () => value }) as Response;
  const paths: string[] = []; const changed = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    paths.push(String(input));
    if (String(input) === '/api/v1/attempts/attempt-scope') { reads += 1; return response(reads === 1 ? attempt : { ...attempt, output_text: 'A共享结果恢复' }); }
    if (reads === 1) return await new Promise<Response>(resolve => { finish = resolve; });
    return response({ items: [] });
  }));
  render(<LibraryReadContext.Provider value={capture}><RunResult initial={attempt} onChanged={changed} /></LibraryReadContext.Provider>);
  await act(async () => {}); expect(finish).toBeTypeOf('function'); switching = true; epoch += 1;
  await act(async () => finish(response({ items: [{ sequence: 9, type: 'token', payload: { text: 'B共享事件哨兵' } }] })));
  await act(async () => { await vi.advanceTimersByTimeAsync(1200); });
  expect(paths).toHaveLength(2); expect(screen.queryByText('B共享事件哨兵')).toBeNull(); expect(changed).not.toHaveBeenCalled();
  switching = false; await act(async () => { await vi.advanceTimersByTimeAsync(600); });
  expect(screen.getByText('A共享结果恢复')).toBeTruthy(); expect(changed).toHaveBeenCalledTimes(1);
  expect(paths.at(-1)).toBe('/api/v1/attempts/attempt-scope/events?after=0');
});

// AC-22：已完成计算但尚待补收/登记的合成记录；以下操作不会启动模型。
const lateActionAttempt = {
  id: 'attempt-late-action', task_id: 'task-late-action', state: 'failed', state_version: 3,
  compute_outcome: 'succeeded', collection_state: 'failed', collection_version: 0,
  output_manifest_ref: { digest: 'fixture-manifest' }, output_text: 'A库原输出',
  artifacts: [{ id: 'artifact-fixture', name: 'result.txt', media_type: 'text/plain' }],
  allowed_actions: ['collect'], snapshot: { kind: 'text', operation: 'generate' },
} as unknown as Attempt;
function heldResponse() {
  let resolve!: (value: Response) => void; let reject!: (error: Error) => void;
  const promise = new Promise<Response>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const jsonResponse = (value: unknown) => ({ ok: true, json: async () => value }) as Response;

it('AC22 控制POST在库代次失效后返回，不得补GET新库或回写父回调', async () => {
  let bank = 'a', epoch = 0, switching = false;
  const capture = () => { const current = epoch; return () => !switching && current === epoch; };
  const pending = heldResponse(); const calls: { bank: string; path: string; method: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = String(url), method = options.method || 'GET'; calls.push({ bank, path, method });
    if (method === 'POST') return pending.promise;
    if (path.endsWith('/events?after=0')) return jsonResponse({ items: [] });
    return jsonResponse({ ...lateActionAttempt, output_text: bank === 'a' ? 'A库原输出' : 'B库迟到动作哨兵' });
  }));
  const changed = vi.fn(), updated = vi.fn();
  render(<LibraryReadContext.Provider value={capture}><RunResult initial={lateActionAttempt} onChanged={changed} onAttemptUpdated={updated} /></LibraryReadContext.Provider>);
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1)); changed.mockClear(); updated.mockClear();
  fireEvent.click(screen.getByRole('button', { name: '只补收已有产物' }));
  await waitFor(() => expect(calls.filter(item => item.method === 'POST')).toHaveLength(1));
  switching = true; epoch += 1; bank = 'b';
  await act(async () => pending.resolve(jsonResponse({ state: 'succeeded' })));
  expect.soft(calls.filter(item => item.bank === 'b')).toEqual([]);
  expect.soft(updated).not.toHaveBeenCalled(); expect.soft(changed).not.toHaveBeenCalled();
  expect.soft(screen.queryByText('B库迟到动作哨兵')).toBeNull();
  switching = false; bank = 'a';
  expect.soft(screen.getByRole('button', { name: '只补收已有产物' }).matches(':disabled')).toBe(false);
});

it('AC22 控制POST失效后的失败不回写错误，回滚原树后按钮可继续使用', async () => {
  let epoch = 0, switching = false;
  const capture = () => { const current = epoch; return () => !switching && current === epoch; };
  const pending = heldResponse(); let posts = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    if (options.method === 'POST') { posts += 1; return pending.promise; }
    return jsonResponse(String(url).endsWith('/events?after=0') ? { items: [] } : lateActionAttempt);
  }));
  const changed = vi.fn();
  render(<LibraryReadContext.Provider value={capture}><RunResult initial={lateActionAttempt} onChanged={changed} /></LibraryReadContext.Provider>);
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1)); changed.mockClear();
  fireEvent.click(screen.getByRole('button', { name: '只补收已有产物' }));
  await waitFor(() => expect(posts).toBe(1)); switching = true; epoch += 1;
  await act(async () => pending.reject(new Error('失效旧控制错误哨兵')));
  expect.soft(screen.queryByText('失效旧控制错误哨兵')).toBeNull();
  expect.soft(changed).not.toHaveBeenCalled(); switching = false;
  expect.soft(screen.getByRole('button', { name: '只补收已有产物' }).matches(':disabled')).toBe(false);
});

it('AC22 控制POST已成功但后续GET跨库迟到，不回写结果或父回调', async () => {
  let epoch = 0, switching = false, bank = 'a', gets = 0;
  const capture = () => { const current = epoch; return () => !switching && current === epoch; };
  const pending = heldResponse(); const calls: { bank: string; path: string; method: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = String(url), method = options.method || 'GET'; calls.push({ bank, path, method });
    if (method === 'POST') return jsonResponse({ state: 'succeeded' });
    if (path.endsWith('/events?after=0')) return jsonResponse({ items: [] });
    gets += 1; return gets === 1 ? jsonResponse(lateActionAttempt) : pending.promise;
  }));
  const changed = vi.fn(), updated = vi.fn();
  render(<LibraryReadContext.Provider value={capture}><RunResult initial={lateActionAttempt} onChanged={changed} onAttemptUpdated={updated} /></LibraryReadContext.Provider>);
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1)); changed.mockClear(); updated.mockClear();
  fireEvent.click(screen.getByRole('button', { name: '只补收已有产物' }));
  await waitFor(() => expect(gets).toBe(2));
  expect(calls.at(-1)).toEqual({ bank: 'a', path: '/api/v1/attempts/attempt-late-action', method: 'GET' });
  switching = true; epoch += 1; bank = 'b';
  await act(async () => pending.resolve(jsonResponse({ ...lateActionAttempt, output_text: '旧库控制GET迟到哨兵' })));
  expect(calls.filter(item => item.bank === 'b')).toEqual([]);
  expect(screen.queryByText('旧库控制GET迟到哨兵')).toBeNull();
  expect(updated).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled();
  switching = false; bank = 'a';
  expect(screen.getByRole('button', { name: '只补收已有产物' }).matches(':disabled')).toBe(false);
});

// 真实 App 导航反例证实：同库卸载后仍需刷新父列表；跨库时不得调用旧库回调。
it.each(([
  ['控制', '只补收已有产物', undefined],
  ['保存作品', '保存作品', undefined],
  ['保存适配器', '保存训练适配器', 'adapters.safetensors'],
  ['保存量化模型', '保存实验量化模型', 'conversion.json'],
] as const).flatMap(([kind, button, artifactName]) => [false, true].map(libraryChanges => ({
  kind, button, artifactName, libraryChanges, scope: libraryChanges ? '跨库' : '同库',
}))))('AC22 $scope 卸载后的 $kind 成功不补GET或回写尝试，父刷新遵守库身份', async ({ button, artifactName, libraryChanges }) => {
  let epoch = 0;
  const capture = () => { const current = epoch; return () => current === epoch; };
  const attempt = artifactName ? { ...lateActionAttempt,
    snapshot: { kind: artifactName === 'conversion.json' ? 'text' : 'image', operation: artifactName === 'conversion.json' ? 'quantize' : 'train' },
    artifacts: [{ id: 'artifact-fixture', name: artifactName, media_type: 'application/octet-stream' }],
  } as unknown as Attempt : lateActionAttempt;
  const pending = heldResponse(); const calls: { path: string; method: string }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = String(url), method = options.method || 'GET'; calls.push({ path, method });
    if (method === 'POST') return pending.promise;
    return jsonResponse(path.endsWith('/events?after=0') ? { items: [] } : attempt);
  }));
  const changed = vi.fn(), updated = vi.fn();
  const view = render(<LibraryReadContext.Provider value={capture}><RunResult initial={attempt} onChanged={changed} onAttemptUpdated={updated} /></LibraryReadContext.Provider>);
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1)); changed.mockClear(); updated.mockClear(); calls.length = 0;
  fireEvent.click(screen.getByRole('button', { name: button }));
  await waitFor(() => expect(calls.filter(item => item.method === 'POST')).toHaveLength(1)); view.unmount();
  if (libraryChanges) epoch += 1;
  await act(async () => pending.resolve(jsonResponse({ id: 'saved-fixture' })));
  expect.soft(calls.filter(item => item.method === 'GET')).toEqual([]);
  expect.soft(changed).toHaveBeenCalledTimes(libraryChanges ? 0 : 1); expect.soft(updated).not.toHaveBeenCalled();
});
