import { configureMarketFixture, invalidateNativeConnection } from '../../apps/desktop/src/api';
import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';
import { defaultProjectView, type LibraryViews, type ProjectView } from '../../apps/desktop/src/ProjectContext';

// 保留真实 App、API 和双帧回执，只控制宿主事件、IPC 返回顺序与绘制帧。
const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { state: string; message: string; connection_id?: string } }) => void) }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name !== 'host-status') return () => {}; host.listener = listener; return () => { if (host.listener === listener) host.listener = undefined; }; }) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));

type Library = 'a' | 'b';
type Request = { library: Library; path: string; method: string };
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const project = (library: Library) => ({ id: `project-${library}`, name: library === 'a' ? '甲库项目' : '乙库项目' });
const capabilities = (reason = '', supported = true) => ({ items: [{ kind: 'text', operation: 'generate', supported, reason }] });
const devices = (name: string) => ({ items: [{ id: 'apple-gpu', name, status: 'ready' }] });
const restored = { id: 'restore-fixture', state: 'succeeded', verified: true, restored_path: '/fixture/b', file_count: 1, changes_current_library: false, message: '' };
let connectionGeneration: number;
const connectionId = () => `fixture-${library}${connectionGeneration ? `-${connectionGeneration}` : ''}`;
let library: Library, requests: Request[], intercept: ((request: Request) => unknown) | undefined;
let contexts: Record<Library, LibraryViews>;
let switchResult: ReturnType<typeof deferred<unknown>> | undefined;
let frames: Map<number, FrameRequestCallback>, nextFrame: number;
const reads = (path: string, bank?: Library) => requests.filter(request => request.path === path && (!bank || request.library === bank));
const receipts = () => vi.mocked(invoke).mock.calls.filter(([command]) => command === 'record_first_frame');
async function emit(state: string, message = '') { await act(async () => { host.listener!({ payload: { state, message, connection_id: state === 'running' ? connectionId() : undefined } }); }); }
function frame() { const pending = [...frames.values()]; frames.clear(); act(() => pending.forEach(callback => callback(0))); }

beforeEach(() => {
  invalidateNativeConnection();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  library = 'a'; connectionGeneration = 0; requests = []; intercept = undefined; switchResult = undefined; frames = new Map(); nextFrame = 1;
  contexts = { a: { project_id: null, projects: {} }, b: { project_id: null, projects: {} } };
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { const id = nextFrame++; frames.set(id, callback); return id; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  vi.mocked(invoke).mockReset().mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: connectionId() };
    if (command === 'use_restored_library') return await switchResult!.promise;
    if (command !== 'api_request') return {};
    const input = (args as { request: { path: string; method: string; body?: unknown } }).request;
    const request = { library, path: input.path.replace('/api/v1', ''), method: input.method };
    requests.push(request);
    const special = intercept?.(request); if (special !== undefined) return await special;
    if (request.path === '/ui-context') {
      if (request.method === 'GET') return structuredClone(contexts[request.library]);
      expect(request.method).toBe('PATCH');
      const body = input.body as { project_id: string; context: ProjectView };
      expect(Object.keys(body).sort()).toEqual(['context', 'project_id']);
      expect(Object.keys(body.context).sort()).toEqual(Object.keys(defaultProjectView()).sort());
      expect(body.project_id).toBe(project(request.library).id);
      expect(body.context.task_id).toBeNull(); expect(body.context.workflow_id).toBeNull();
      contexts[request.library] = { project_id: body.project_id, projects: { ...contexts[request.library].projects, [body.project_id]: body.context } };
      return structuredClone(contexts[request.library]);
    }
    if (request.path === '/projects') return { items: [project(request.library)] };
    if (request.path.startsWith('/capabilities')) return capabilities();
    if (request.path === '/devices') return devices(request.library === 'a' ? '甲库设备' : '乙库设备');
    if (request.path === '/restores') return { items: [restored] };
    if (request.path === `/restores/${restored.id}`) return restored;
    return { items: [] };
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function startHealthy() {
  render(<App />); await emit('running');
  await screen.findByRole('option', { name: '甲库项目' });
  await waitFor(() => expect(reads('/devices')).toHaveLength(1));
}
function openSettings() {
  fireEvent.click(screen.getByRole('button', { name: '设备与环境', exact: true }));
  return within(screen.getByRole('dialog', { name: '设备与环境' }));
}
async function beginSwitch() {
  fireEvent.click(screen.getByRole('button', { name: '备份与恢复', exact: true }));
  fireEvent.click(screen.getByRole('tab', { name: '从备份恢复' }));
  fireEvent.click(await screen.findByText('已恢复的工作库'));
  fireEvent.click(await screen.findByRole('button', { name: '查看恢复结果' }));
  fireEvent.click(await screen.findByRole('button', { name: '切换到恢复的工作库' }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('use_restored_library', { restoreId: restored.id }));
}

it('宿主健康时环境与待决项目并行，项目和资源未齐不发回执，齐备后仍等待双帧', async () => {
  const projects = deferred<unknown>(), models = deferred<unknown>();
  intercept = request => request.path === '/projects' ? projects.promise : request.path.startsWith('/models?') ? models.promise : undefined;
  render(<App />);
  await waitFor(() => expect(reads('/projects')).toHaveLength(1)); expect(reads('/capabilities')).toHaveLength(0);
  await emit('running');
  await waitFor(() => expect(reads('/devices')).toHaveLength(1));
  expect(reads('/capabilities')).toHaveLength(1);
  expect(screen.getByText('本机服务未连接')).toBeTruthy();
  expect(screen.queryByRole('option', { name: '甲库项目' })).toBeNull();
  frame(); frame(); expect(receipts()).toHaveLength(0);
  await act(async () => projects.resolve({ items: [project('a')] }));
  await screen.findByRole('option', { name: '甲库项目' });
  expect(screen.getByText('正在读取项目内容')).toBeTruthy();
  frame(); frame(); expect(receipts()).toHaveLength(0);
  expect(reads('/capabilities')).toHaveLength(1); expect(reads('/devices')).toHaveLength(1);
  await act(async () => models.resolve({ items: [] }));
  await waitFor(() => expect(frames.size).toBe(1));
  frame(); expect(receipts()).toHaveLength(0); frame();
  expect(receipts()).toEqual([['record_first_frame', { view: 'project_home', frontend: expect.objectContaining({ events: expect.any(Array) }) }]]);
  const events = (receipts()[0][1] as { frontend: { events: { stage: string; at_ms: number }[] } }).frontend.events;
  const stages = events.map(event => event.stage);
  // 用真实 App 的待决请求验证计时能定位最后的项目资源等待，不能由环境完成代签。
  expect(stages.indexOf('environment_started')).toBeLessThan(stages.indexOf('projects_ready'));
  expect(stages.indexOf('devices_ready')).toBeLessThan(stages.lastIndexOf('resources_ready'));
  expect(stages.lastIndexOf('resources_ready')).toBeLessThan(stages.indexOf('all_conditions_ready'));
  expect(stages.at(-1)).toBe('second_animation_frame');
});

it.each(['/capabilities', '/devices'])('项目返回及普通刷新不会重开或丢弃先启动的%s', async pendingPath => {
  const projects = deferred<unknown>(), environment = deferred<unknown>();
  intercept = request => request.path === '/projects' ? projects.promise : request.path === pendingPath ? environment.promise : undefined;
  render(<App />); await emit('running');
  await waitFor(() => expect(reads(pendingPath)).toHaveLength(1));
  await act(async () => projects.resolve({ items: [project('a')] }));
  await screen.findByRole('option', { name: '甲库项目' });
  await emit('running');
  expect(reads(pendingPath)).toHaveLength(1); expect(reads('/capabilities')).toHaveLength(1);
  frame(); frame(); expect(receipts()).toHaveLength(0);
  await act(async () => environment.resolve(pendingPath === '/capabilities' ? capabilities() : devices('首次在途设备')));
  await waitFor(() => expect(frames.size).toBe(1));
  expect(reads('/capabilities')).toHaveLength(1); expect(reads('/devices')).toHaveLength(1);
  frame(); frame(); expect(receipts()).toHaveLength(1);
  const settings = openSettings();
  expect(await settings.findByText(pendingPath === '/devices' ? '首次在途设备' : '甲库设备')).toBeTruthy();
});

it('漏接宿主健康事件时保留项目成功后的环境兜底，空库也需环境完成及双帧', async () => {
  const environment = deferred<unknown>();
  intercept = request => request.path === '/projects' ? { items: [] } : request.path === '/capabilities' ? environment.promise : undefined;
  render(<App />);
  await screen.findByText('建立你的第一个项目');
  // 文案先出现，随后 effect 发出环境兜底；实际请求仍必须恰好一次。
  await waitFor(() => expect(reads('/capabilities')).toHaveLength(1));
  frame(); frame(); expect(receipts()).toHaveLength(0);
  await act(async () => environment.resolve(capabilities()));
  await waitFor(() => expect(frames.size).toBe(1));
  frame(); expect(receipts()).toHaveLength(0); frame();
  expect(receipts()).toEqual([['record_first_frame', { view: 'empty_library', frontend: expect.objectContaining({ events: expect.any(Array) }) }]]);
});

it('宿主健康和环境完成不替代项目读取成功', async () => {
  const projects = deferred<unknown>();
  intercept = request => request.path === '/projects' ? projects.promise : undefined;
  render(<App />); await emit('running');
  await waitFor(() => expect(reads('/devices')).toHaveLength(1));
  await act(async () => projects.reject(new Error('当前项目读取失败')));
  expect(screen.getByText('当前项目读取失败')).toBeTruthy();
  expect(screen.getByRole('heading', { name: '本机服务尚未连接' })).toBeTruthy();
  frame(); frame(); expect(receipts()).toHaveLength(0);
});

it.each(['成功', '失败'])('宿主断连后旧项目%s和旧环境迟到不恢复连接或覆盖断连原因', async outcome => {
  const projects = deferred<unknown>(), environment = deferred<unknown>();
  intercept = request => request.path === '/projects' ? projects.promise : request.path === '/capabilities' ? environment.promise : undefined;
  render(<App />); await emit('running');
  const environmentReads = reads('/capabilities').length;
  await emit('stopped', '宿主明确断连');
  await act(async () => {
    if (outcome === '成功') projects.resolve({ items: [project('a')] }); else projects.reject(new Error('旧项目迟到错误'));
    environment.resolve(capabilities('旧环境迟到能力', false));
  });
  expect(screen.getByRole('heading', { name: '本机服务尚未连接' })).toBeTruthy();
  expect(screen.getByText('宿主明确断连')).toBeTruthy();
  expect(screen.queryByRole('option', { name: '甲库项目' })).toBeNull();
  expect(screen.queryByText('旧项目迟到错误')).toBeNull();
  expect(reads('/capabilities')).toHaveLength(environmentReads); expect(reads('/devices')).toHaveLength(0);
  frame(); frame(); expect(receipts()).toHaveLength(0);
});

it.each(['/capabilities', '/devices'])('同批断连再健康也使旧%s失效，旧完成不能污染新环境', async pendingPath => {
  const old = deferred<unknown>(); let seen = 0;
  intercept = request => request.path === pendingPath && ++seen === 1 ? old.promise : undefined;
  render(<App />); await emit('running');
  await screen.findByRole('option', { name: '甲库项目' });
  await waitFor(() => expect(reads(pendingPath)).toHaveLength(1));
  await act(async () => {
    host.listener!({ payload: { state: 'stopped', message: '本轮断连' } });
    host.listener!({ payload: { state: 'running', message: '', connection_id: connectionId() } });
  });
  await waitFor(() => expect(reads(pendingPath)).toHaveLength(2));
  const settings = openSettings(); await settings.findByText('甲库设备');
  const deviceCount = reads('/devices').length;
  await act(async () => old.resolve(pendingPath === '/capabilities' ? capabilities('旧环境迟到能力', false) : devices('旧环境迟到设备')));
  expect(settings.queryByText('旧环境迟到能力')).toBeNull(); expect(settings.queryByText('旧环境迟到设备')).toBeNull();
  expect(settings.getByText('甲库设备')).toBeTruthy(); expect(reads('/devices')).toHaveLength(deviceCount);
  expect(settings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(false);
  frame(); frame();
  expect(receipts()).toHaveLength(1);
  const phases = (receipts()[0][1] as { frontend: { events: { stage: string }[] } }).frontend.events;
  expect(phases.filter(event => event.stage === 'devices_ready')).toHaveLength(1);
});

it('显式刷新与健康事件重叠仍只有一次在途探测，项目刷新不撤销它', async () => {
  await startHealthy(); const settings = openSettings(); await settings.findByText('甲库设备');
  const forced = deferred<unknown>();
  intercept = request => request.path === '/capabilities?refresh=true' ? forced.promise : undefined;
  const button = settings.getByRole('button', { name: '刷新环境' });
  const projectCount = reads('/projects').length, cachedCount = reads('/capabilities').length;
  fireEvent.click(button); fireEvent.click(button);
  expect(reads('/projects')).toHaveLength(projectCount);
  await emit('running');
  expect(reads('/projects')).toHaveLength(projectCount + 1);
  expect(reads('/capabilities?refresh=true')).toHaveLength(1); expect(reads('/capabilities')).toHaveLength(cachedCount);
  expect(button.matches(':disabled')).toBe(true);
  await act(async () => forced.resolve(capabilities()));
  await waitFor(() => expect(button.matches(':disabled')).toBe(false));
  expect(reads('/devices')).toHaveLength(2);
});

it.each(['成功', '失败'])('切库%s时保留原环境隔离，旧探测及其finally不影响新一轮', async outcome => {
  await startHealthy(); const settings = openSettings(); await settings.findByText('甲库设备');
  const old = deferred<unknown>(), fresh = deferred<unknown>();
  intercept = request => request.path === '/capabilities?refresh=true' ? old.promise : request.path === '/capabilities' ? fresh.promise : undefined;
  fireEvent.click(settings.getByRole('button', { name: '刷新环境' }));
  switchResult = deferred<unknown>(); await beginSwitch();
  const projectCount = reads('/projects').length;
  await emit('running'); expect(reads('/projects')).toHaveLength(projectCount);
  await act(async () => {
    if (outcome === '成功') { library = 'b'; switchResult!.resolve({}); }
    else switchResult!.reject(new Error('切换失败，已恢复原工作库'));
  });
  if (outcome === '失败') {
    await screen.findByText('切换失败，已恢复原工作库');
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  } else await waitFor(() => expect(screen.queryByRole('dialog', { name: '备份与恢复' })).toBeNull());
  await waitFor(() => expect(reads('/capabilities')).toHaveLength(2));
  const currentSettings = openSettings();
  expect(currentSettings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(true);
  const deviceCount = reads('/devices').length;
  await act(async () => old.resolve(capabilities('旧库迟到探测', false)));
  expect(reads('/devices')).toHaveLength(deviceCount);
  expect(currentSettings.queryByText('旧库迟到探测')).toBeNull();
  expect(currentSettings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(true);
  await act(async () => fresh.resolve(capabilities()));
  await currentSettings.findByText(outcome === '成功' ? '乙库设备' : '甲库设备');
  await waitFor(() => expect(currentSettings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(false));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(outcome === '成功' ? 'project-b' : 'project-a');
});

it('连接身份尚待决时重复同库健康事件仍能完成环境启动', async () => {
  const status = deferred<unknown>();
  const normal = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (command, args) => command === 'host_status' ? status.promise : normal(command, args));
  render(<App />);
  await emit('running');
  await emit('running');
  expect(reads('/capabilities')).toHaveLength(0);
  await act(async () => status.resolve({ state: 'running', connection_id: 'fixture-a' }));
  await screen.findByRole('option', { name: '甲库项目' });
  await waitFor(() => expect(reads('/devices')).toHaveLength(1));
  expect(reads('/capabilities')).toHaveLength(1);
  expect(screen.queryByText('工作库连接已变化，请重新读取后再操作。')).toBeNull();
});


it.each(['event', 'market'] as const)('仅新连接 running 事件能恢复环境，%s 过程的旧响应不占用新检查', async mode => {
  const old = deferred<unknown>(), command = deferred<any>();
  let seen = 0;
  intercept = request => request.path === '/capabilities' && ++seen === 1 ? old.promise : undefined;
  const normal = vi.mocked(invoke).getMockImplementation()!;
  vi.mocked(invoke).mockImplementation(async (name, args) => name === 'configure_market_fixture' ? command.promise : normal(name, args));
  render(<App />); await emit('running');
  await screen.findByRole('option', { name: '甲库项目' });
  await waitFor(() => expect(reads('/capabilities')).toHaveLength(1));
  let reconnect: Promise<unknown> | undefined;
  if (mode === 'market') reconnect = configureMarketFixture(null);
  connectionGeneration += 1;
  await emit('running');
  if (mode === 'market') {
    expect(reads('/capabilities')).toHaveLength(1);
    await act(async () => { command.resolve({ market_fixture_origin: null }); await reconnect; });
  }
  await waitFor(() => expect(reads('/capabilities')).toHaveLength(2));
  const settings = openSettings(); await settings.findByText('甲库设备');
  const deviceCount = reads('/devices').length;
  await act(async () => old.resolve(capabilities('旧连接迟到能力', false)));
  expect(settings.queryByText('旧连接迟到能力')).toBeNull();
  expect(settings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(false);
  expect(reads('/devices')).toHaveLength(deviceCount);
});
