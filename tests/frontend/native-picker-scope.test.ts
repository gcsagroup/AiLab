import { beforeEach, expect, it, vi } from 'vitest';
import { invoke } from '@tauri-apps/api/core';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));
let bridge: typeof import('../../apps/desktop/src/api');
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const changed = { error: { code: 'CONTROL_CONNECTION_CHANGED' } };
const operations = [
  ['pick_import_path', () => bridge.pickImport('dataset'), { kind: 'dataset' }],
  ['pick_import_path', () => bridge.pickImport('source-report'), { kind: 'source-report' }],
  ['pick_export_directory', () => bridge.pickExportDirectory(), {}],
  ['pick_worker_python', () => bridge.pickWorkerPython(), {}],
  ['pick_media_python', () => bridge.pickMediaPython('kokoro'), { engine: 'kokoro' }],
  ['use_bundled_worker', () => bridge.useBundledWorker(), {}],
  ['use_bundled_media', () => bridge.useBundledMedia('diffusers'), { engine: 'diffusers' }],
] as const;

beforeEach(async () => {
  vi.resetModules();
  vi.mocked(invoke).mockReset();
  bridge = await import('../../apps/desktop/src/api');
});

it.each(operations)('%s 在用户操作开始时绑定连接身份', async (command, call, args) => {
  const result = { path: '/test/selection', grant_id: 'grant-a', revision: 1, worker_python: null };
  vi.mocked(invoke).mockImplementation(async name => name === 'host_status'
    ? { state: 'running', connection_id: 'a' } : result);
  await expect(call()).resolves.toEqual(result);
  expect(invoke).toHaveBeenCalledWith(command, { ...args, connectionId: 'a' });
});

it.each(operations)('%s 的迟到成功不会被新连接消费或重发', async (command, call) => {
  const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async name => name === 'host_status'
    ? { state: 'running', connection_id: 'a' } : pending.promise);
  const request = call();
  const rejected = expect(request).rejects.toMatchObject(changed);
  await vi.waitFor(() => expect(vi.mocked(invoke).mock.calls.some(([name]) => name === command)).toBe(true));
  bridge.observeNativeConnection({ state: 'running', connection_id: 'b' });
  pending.resolve({ path: '/old/library/selection', grant_id: 'grant-a', revision: 1 });
  await rejected;
  expect(vi.mocked(invoke).mock.calls.filter(([name]) => name === command)).toHaveLength(1);
});

it.each(operations)('%s 的迟到错误不会作为新连接错误返回', async (command, call) => {
  const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async name => name === 'host_status'
    ? { state: 'running', connection_id: 'a' } : pending.promise);
  const request = call();
  const rejected = expect(request).rejects.toMatchObject(changed);
  await vi.waitFor(() => expect(vi.mocked(invoke).mock.calls.some(([name]) => name === command)).toBe(true));
  bridge.observeNativeConnection({ state: 'running', connection_id: 'a-restarted' });
  pending.reject({ error: { code: 'IMPORT_PATH_INVALID', message: '旧库错误' } });
  await rejected;
});

it.each(operations)('%s 等待身份期间发生切库，不补用新身份调用', async (command, call) => {
  const status = deferred<any>();
  vi.mocked(invoke).mockImplementation(async name => name === 'host_status' ? status.promise : null);
  const request = call();
  const rejected = expect(request).rejects.toMatchObject(changed);
  bridge.invalidateNativeConnection();
  status.resolve({ state: 'running', connection_id: 'b' });
  await rejected;
  expect(vi.mocked(invoke).mock.calls.filter(([name]) => name === command)).toHaveLength(0);
});

it.each(operations)('%s 在宿主切换未结束时不打开选择器或提交配置', async (command, call) => {
  const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async name => name === 'use_restored_library' ? pending.promise : null);
  const switching = bridge.useRestoredLibrary('restore-b');
  await expect(call()).rejects.toMatchObject({ error: { code: 'LIBRARY_SWITCH_PENDING' } });
  expect(vi.mocked(invoke).mock.calls.filter(([name]) => name === command)).toHaveLength(0);
  pending.resolve({});
  await switching;
});

it.each(operations.slice(0, 4))('%s 同连接取消正常返回，不制造后续请求', async (command, call) => {
  vi.mocked(invoke).mockImplementation(async name => name === 'host_status'
    ? { state: 'running', connection_id: 'a' } : null);
  await expect(call()).resolves.toBeNull();
  expect(vi.mocked(invoke).mock.calls.map(([name]) => name)).toEqual(['host_status', command]);
});
