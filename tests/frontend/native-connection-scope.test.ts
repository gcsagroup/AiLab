import { beforeEach, expect, it, vi } from 'vitest';
import { invoke } from '@tauri-apps/api/core';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const changed = { error: { code: 'CONTROL_CONNECTION_CHANGED' } };
let bridge: typeof import('../../apps/desktop/src/api');
beforeEach(async () => {
  vi.resetModules();
  vi.mocked(invoke).mockReset();
  bridge = await import('../../apps/desktop/src/api');
});

it('普通写入携带从宿主取得的连接身份，不把身份放进业务正文', async () => {
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status'
    ? { state: 'running', connection_id: 'connection-a' } : { saved: true });
  const body = { project_id: 'project-shared', context: { page: 'home' } };
  await expect(bridge.api('PATCH', '/ui-context', body, 'request-a')).resolves.toEqual({ saved: true });
  expect(invoke).toHaveBeenCalledWith('api_request', { request: {
    connection_id: 'connection-a', method: 'PATCH', path: '/api/v1/ui-context', body, idempotency_key: 'request-a',
  } });
});

it('宿主没有可用连接身份时不发送普通请求', async () => {
  vi.mocked(invoke).mockResolvedValue({ state: 'stopped' });
  await expect(bridge.api('GET', '/projects')).rejects.toMatchObject({ error: { code: 'CONTROL_UNAVAILABLE' } });
  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual(['host_status']);
});

it('媒体读取也携带同一连接身份', async () => {
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status'
    ? { state: 'running', connection_id: 'connection-a' } : { media_type: 'image/png', base64: 'YQ==' });
  const artifactId = 'artifact-' + 'a'.repeat(32);
  await expect(bridge.mediaBlob(artifactId)).resolves.toMatchObject({ size: 1, type: 'image/png' });
  expect(invoke).toHaveBeenCalledWith('api_media', { artifactId, connectionId: 'connection-a' });
});

it('同一作用域的并行读取共享一次宿主身份读取', async () => {
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status'
    ? { state: 'running', connection_id: 'a' } : { items: [] });
  await Promise.all([bridge.api('GET', '/projects'), bridge.api('GET', '/devices'), bridge.api('GET', '/capabilities')]);
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'host_status')).toHaveLength(1);
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'api_request').map(([, args]) => (args as any).request.connection_id)).toEqual(['a', 'a', 'a']);
});

it('迟到的身份读取不能为旧写入补上新库身份', async () => {
  const status = deferred<any>();
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status' ? status.promise : {});
  const old = bridge.api('PATCH', '/ui-context', { project_id: 'project-shared' });
  const rejected = expect(old).rejects.toMatchObject(changed);
  bridge.invalidateNativeConnection();
  status.resolve({ state: 'running', connection_id: 'b' });
  await rejected;
  expect(vi.mocked(invoke).mock.calls.map(([command]) => command)).toEqual(['host_status']);
});

it('已排队的IPC固定旧身份，切库后不以新身份自动重发写入', async () => {
  const queued = deferred<any>(); let current = 'a'; let received: any;
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: current };
    received = (args as any).request; return queued.promise;
  });
  const old = bridge.api('PATCH', '/ui-context', { project_id: 'project-shared' });
  const rejected = expect(old).rejects.toMatchObject(changed);
  await vi.waitFor(() => expect(received?.connection_id).toBe('a'));
  current = 'b'; bridge.observeNativeConnection({ state: 'running', connection_id: current });
  expect(received.connection_id).not.toBe(current);
  queued.reject(changed); await rejected;
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'api_request')).toHaveLength(1);
});

it.each(['api', 'media'] as const)('%s旧响应在连接变更后不会交给新工作库', async mode => {
  const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status' ? { state: 'running', connection_id: 'a' } : pending.promise);
  const old = mode === 'api' ? bridge.api('GET', '/projects') : bridge.mediaBlob('artifact-' + 'a'.repeat(32));
  const rejected = expect(old).rejects.toMatchObject(changed);
  await vi.waitFor(() => expect(vi.mocked(invoke).mock.calls).toHaveLength(2));
  bridge.observeNativeConnection({ state: 'running', connection_id: 'b' });
  pending.resolve(mode === 'api' ? { items: ['旧库'] } : { media_type: 'image/png', base64: 'YQ==' });
  await rejected;
});

it('相同连接的重复running事件不作废当前正常读取', async () => {
  const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status' ? { state: 'running', connection_id: 'a' } : pending.promise);
  const read = bridge.api('GET', '/projects');
  await vi.waitFor(() => expect(vi.mocked(invoke).mock.calls).toHaveLength(2));
  bridge.observeNativeConnection({ state: 'running', connection_id: 'a' });
  pending.resolve({ items: ['本库'] });
  await expect(read).resolves.toEqual({ items: ['本库'] });
});

it.each(['success', 'rollback'] as const)('切库%s结束后才允许新请求重新绑定', async outcome => {
  let current = 'a'; const pending = deferred<any>();
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: current };
    if (command === 'use_restored_library') return pending.promise;
    return { received: (args as any).request.connection_id };
  });
  await bridge.api('GET', '/projects');
  const switching = bridge.useRestoredLibrary('restore-fixed');
  const finished = outcome === 'success' ? expect(switching).resolves.toEqual({}) : expect(switching).rejects.toEqual('恢复失败，已回到原库');
  await expect(bridge.api('PATCH', '/ui-context', {})).rejects.toMatchObject({ error: { code: 'LIBRARY_SWITCH_PENDING' } });
  current = outcome === 'success' ? 'b' : 'a-restarted';
  if (outcome === 'success') pending.resolve({}); else pending.reject('恢复失败，已回到原库');
  await finished;
  await expect(bridge.api('GET', '/projects')).resolves.toEqual({ received: current });
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'api_request')).toHaveLength(2);
});

it.each(['restart', 'market'] as const)('%s重连后旧身份失效，失败请求不自动重试', async operation => {
  let current = 'a';
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: current };
    if (command === 'restart_control' || command === 'configure_market_fixture') { current = 'new'; return {}; }
    if ((args as any).request.method === 'PATCH') throw { error: { code: 'REVISION_CONFLICT' } };
    return { received: (args as any).request.connection_id };
  });
  await bridge.api('GET', '/projects');
  if (operation === 'restart') await bridge.restartControl(); else await bridge.configureMarketFixture(null);
  await expect(bridge.api('GET', '/projects')).resolves.toEqual({ received: 'new' });
  await expect(bridge.api('PATCH', '/ui-context', {})).rejects.toMatchObject({ error: { code: 'REVISION_CONFLICT' } });
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'api_request')).toHaveLength(3);
});

it('身份读取失败可以在下一次显式请求重试，不复用失败缓存', async () => {
  let ready = false;
  vi.mocked(invoke).mockImplementation(async command => {
    if (command === 'host_status') { if (!ready) throw '尚未连接'; return { state: 'running', connection_id: 'a' }; }
    return { items: [] };
  });
  await expect(bridge.api('GET', '/projects')).rejects.toEqual('尚未连接');
  ready = true;
  await expect(bridge.api('GET', '/projects')).resolves.toEqual({ items: [] });
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'host_status')).toHaveLength(2);
});


it('身份读取尚未完成时，同连接 running 事件保留在途请求', async () => {
  const status = deferred<any>();
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status' ? status.promise : { items: ['本库'] });
  const read = bridge.api('GET', '/capabilities');
  bridge.observeNativeConnection({ state: 'running', connection_id: 'a' });
  status.resolve({ state: 'running', connection_id: 'a' });
  await expect(read).resolves.toEqual({ items: ['本库'] });
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'host_status')).toHaveLength(1);
});

it.each([['a', 'b'], ['b', 'a']])('身份读取与早期事件不同（%s → %s）时拒绝旧请求', async (eventId, statusId) => {
  const status = deferred<any>();
  vi.mocked(invoke).mockImplementation(async command => command === 'host_status' ? status.promise : {});
  const read = bridge.api('PATCH', '/ui-context', { project_id: 'shared' });
  const rejected = expect(read).rejects.toMatchObject(changed);
  bridge.observeNativeConnection({ state: 'running', connection_id: eventId });
  status.resolve({ state: 'running', connection_id: statusId });
  await rejected;
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'api_request')).toHaveLength(0);
});
