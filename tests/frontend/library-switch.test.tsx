import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';
import type { LibraryViews } from '../../apps/desktop/src/ProjectContext';

// 使用真实 App、BackupDialog、Workbench 和 API，仅替换宿主事件及传输。
const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { state: string; message: string } }) => void) }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name !== 'host-status') return () => {}; host.listener = listener; return () => { if (host.listener === listener) host.listener = undefined; }; }) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('../../apps/desktop/src/api', async importOriginal => ({ ...await importOriginal<object>(), canPickFile: () => true }));

type Bank = 'a' | 'b';
const response = (value: unknown, ok = true) => ({ ok, json: async () => value }) as Response;
const failed = (message: string) => response({ error: { code: 'FIXTURE_FAILURE', message } }, false);
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const caps = (supported = true) => ({ items: [{ kind: 'text', operation: 'generate', supported, reason: supported ? '' : '迟到旧库能力' }] });
const restore = { id: 'restore-fixture', state: 'succeeded', verified: true, restored_path: '/fixture/restored', file_count: 1, changes_current_library: false, message: '' };
let bank: Bank, nextBank: Bank, sameId: boolean, emptyB: boolean, pagedProjects: boolean, missingReference: boolean;
let requests: { bank: Bank; path: string }[], intercept: undefined | ((library: Bank, path: string) => Promise<Response> | Response | undefined);
let switchGate: ReturnType<typeof deferred<unknown>> | undefined, switchFailure: boolean;
let frames: Map<number, FrameRequestCallback>, nextFrame: number;
const projectId = (library: Bank) => library === 'a' || sameId ? 'project-shared' : 'project-b';
const name = (library: Bank, suffix: string) => `${library === 'a' ? '旧库' : '新库'}${suffix}`;
const project = (library: Bank) => ({ id: projectId(library), name: name(library, '项目名称') });
const model = (library: Bank, id = 'model-shared') => ({ id, project_id: projectId(library), name: name(library, '模型内容'), modality: 'text', format: 'mlx-safetensors', default_engine: 'mlx', status: 'ready' });
const initialTask = (library: Bank) => ({ id: 'task-shared', project_id: projectId(library), name: name(library, '任务名称'), kind: 'text', operation: 'generate', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: library === 'a' && missingReference ? 'model-reference' : 'model-shared', input: { prompt: name(library, '已存草稿') }, runtime: { engine: 'mlx', device_id: 'apple-gpu', max_tokens: 32, temperature: 0, top_p: 1, seed: 0 } } });
let savedTasks: Map<Bank, ReturnType<typeof initialTask>>, contexts: Record<Bank, LibraryViews>;
const task = (library: Bank) => savedTasks.get(library) || initialTask(library);
function emitRunning() { host.listener?.({ payload: { state: 'running', message: '' } }); }
function frame() { const pending = [...frames.values()]; frames.clear(); act(() => pending.forEach(callback => callback(0))); }

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  bank = 'a'; nextBank = 'b'; sameId = false; emptyB = false; pagedProjects = false; missingReference = false;
  savedTasks = new Map(); contexts = { a: { project_id: null, projects: {} }, b: { project_id: null, projects: {} } };
  requests = []; intercept = undefined; switchGate = undefined; switchFailure = false; frames = new Map(); nextFrame = 1;
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { const id = nextFrame++; frames.set(id, callback); return id; });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  vi.mocked(invoke).mockReset().mockImplementation(async command => {
    if (command === 'use_restored_library') {
      if (!switchFailure) bank = nextBank;
      emitRunning();
      if (switchGate) return await switchGate.promise;
      if (switchFailure) throw new Error('切换失败，原库继续使用');
    }
    return {};
  });
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = String(url).replace('/api/v1', ''); const library = bank;
    requests.push({ bank: library, path });
    const special = intercept?.(library, path); if (special) return await special;
    const body = options.body ? JSON.parse(String(options.body)) : undefined;
    if (path === '/ui-context') {
      if (options.method === 'PATCH') contexts[library] = { project_id: body.project_id, projects: { ...contexts[library].projects, [body.project_id]: body.context } };
      return response(structuredClone(contexts[library]));
    }
    if (path === '/tasks/task-shared/draft' && options.method === 'PATCH') {
      const previous = task(library);
      if (body.expected_revision !== previous.draft_revision) return failed('草稿版本冲突');
      const saved = { ...previous, draft_revision: previous.draft_revision + 1, draft: body.draft };
      savedTasks.set(library, saved); return response(saved);
    }
    if (path === '/projects') return response({ items: library === 'b' && emptyB ? [] : [project(library)], next_cursor: library === 'a' ? 'projects-a' : null });
    if (path === '/projects?cursor=projects-a') return response({ items: pagedProjects ? [{ id: 'project-second', name: '旧库后页项目' }] : [{ id: 'project-late', name: '迟到旧库项目' }] });
    if (path === '/projects/project-second' && library === 'a') return response({ id: 'project-second', name: '旧库后页项目' });
    if (path.startsWith('/projects/')) return failed('记录不存在');
    if (path.startsWith('/capabilities')) return response(caps());
    if (path === '/devices') return response({ items: [{ id: 'apple-gpu', name: name(library, '设备'), status: 'ready' }] });
    if (path === '/restores') return response({ items: [restore] });
    if (path === '/restores/restore-fixture') return response(restore);
    if (path.includes('project_id=') && ![projectId(library), ...(library === 'a' && pagedProjects ? ['project-second'] : [])].includes(new URL(`http://fixture${path}`).searchParams.get('project_id') || '')) return failed('记录不存在');
    if (path.startsWith('/models?')) return response({ items: [model(library)], next_cursor: library === 'a' ? 'models-a' : null });
    if (path === '/models/model-reference') return response(model(library, 'model-reference'));
    if (path.startsWith('/tasks?')) return response({ items: [task(library)] });
    if (path === '/tasks/task-shared') return response(task(library));
    if (path.startsWith('/works?')) return response({ items: [{ id: 'work-shared', name: name(library, '作品名称'), text: name(library, '作品内容'), kind: 'text', attempt_id: 'attempt-shared' }] });
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function loadOriginal() {
  render(<App />); await screen.findByRole('option', { name: '旧库项目名称' });
  await screen.findByRole('button', { name: /旧库任务名称/ });
}
async function beginSwitch() {
  fireEvent.click(screen.getByRole('button', { name: '设备与环境', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: '备份与恢复', exact: true }));
  fireEvent.click(screen.getByRole('tab', { name: '从备份恢复' }));
  fireEvent.click(await screen.findByRole('button', { name: '查看恢复结果' }));
  fireEvent.click(await screen.findByRole('button', { name: '切换到恢复的工作库' }));
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('use_restored_library', { restoreId: 'restore-fixture' }));
}
async function completedSwitch() { await beginSwitch(); await waitFor(() => expect(screen.queryByRole('dialog', { name: '备份与恢复' })).toBeNull()); }
async function expectB() {
  await screen.findByRole('option', { name: '新库项目名称' });
  await screen.findByRole('button', { name: /新库任务名称/ });
  expect(screen.queryByRole('option', { name: '旧库项目名称' })).toBeNull();
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(projectId('b'));
  expect(screen.queryByText('记录不存在')).toBeNull();
  expect(screen.queryByText('迟到旧库错误')).toBeNull();
}
async function editDraft() {
  fireEvent.click(screen.getByRole('button', { name: /旧库任务名称/ }));
  const input = await screen.findByLabelText('输入内容');
  fireEvent.change(input, { target: { value: '旧库未保存草稿' } });
  return input;
}

it('不同 ID 成功切库后只选择新库首项目，模型、任务、作品和游标都属于新库', async () => {
  await loadOriginal(); await completedSwitch(); await expectB();
  expect(screen.queryByRole('button', { name: '加载更多项目' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '模型库', exact: true })); await screen.findByText('新库模型内容');
  expect(screen.queryByText('旧库模型内容')).toBeNull(); expect(screen.queryByRole('button', { name: '加载更多模型' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '作品与素材', exact: true })); await screen.findByText('新库作品内容');
  expect(screen.queryByText('旧库作品内容')).toBeNull();
  expect(requests.some(item => item.bank === 'b' && (item.path.includes('project-shared') || item.path.includes('cursor=')))).toBe(false);
});

it('相同项目、模型和任务 ID 仍重新读取新库名称与草稿，清除旧草稿', async () => {
  sameId = true; await loadOriginal(); await editDraft(); await completedSwitch(); await expectB();
  expect(screen.queryByLabelText('输入内容')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: /新库任务名称/ }));
  expect((await screen.findByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('新库已存草稿');
  expect(screen.getByRole('option', { name: '新库模型内容' })).toBeTruthy();
  expect(screen.queryByRole('option', { name: '旧库模型内容' })).toBeNull();
});

it('成功读取空库后才显示空库，空库也可以切回有项目的库', async () => {
  emptyB = true; await loadOriginal(); await completedSwitch();
  await screen.findByText('建立你的第一个项目'); expect(screen.queryByRole('option', { name: '旧库项目名称' })).toBeNull();
  nextBank = 'a'; await completedSwitch(); await screen.findByRole('option', { name: '旧库项目名称' });
  await screen.findByRole('button', { name: /旧库任务名称/ });
});

it('新库项目列表等待与失败时清空旧身份，不误报空库，重试成功只显示新库', async () => {
  const pending = deferred<Response>(); intercept = (library, path) => library === 'b' && path === '/projects' ? pending.promise : undefined;
  await loadOriginal(); await completedSwitch();
  expect(screen.queryByRole('option', { name: '旧库项目名称' })).toBeNull();
  expect(screen.queryByText('尚未创建项目')).toBeNull(); expect(screen.queryByText('建立你的第一个项目')).toBeNull();
  await act(async () => pending.resolve(failed('新库项目列表读取失败')));
  await screen.findByText('新库项目列表读取失败'); expect(screen.queryByText('建立你的第一个项目')).toBeNull();
  intercept = undefined; fireEvent.click(screen.getByRole('button', { name: '重新连接' })); await expectB();
});

it('新库资源等待与失败时保留新项目名称并给出重试，就绪前不发送首屏回执', async () => {
  const pending = deferred<Response>(); intercept = (library, path) => library === 'b' && path.startsWith('/models?') ? pending.promise : undefined;
  await loadOriginal(); frame(); frame(); vi.mocked(invoke).mockClear(); await completedSwitch();
  await screen.findByRole('option', { name: '新库项目名称' }); await screen.findByText('正在读取项目内容'); frame(); frame();
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'record_first_frame')).toHaveLength(0);
  await act(async () => pending.resolve(failed('新库模型读取失败')));
  await screen.findByText('新库模型读取失败'); expect(screen.getByRole('option', { name: '新库项目名称' })).toBeTruthy();
  expect(screen.queryByText('旧库模型内容')).toBeNull(); frame(); frame();
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'record_first_frame')).toHaveLength(0);
  intercept = undefined; fireEvent.click(screen.getByRole('button', { name: '重试加载' })); await expectB(); frame(); frame();
  expect(vi.mocked(invoke).mock.calls.filter(([command]) => command === 'record_first_frame')).toHaveLength(1);
});

it('切库失败保留当前项目与未保存草稿，并继续处理之后的普通刷新', async () => {
  await loadOriginal(); await editDraft(); switchFailure = true; await beginSwitch();
  await screen.findByText('切换失败，原库继续使用');
  expect(screen.getByRole('option', { name: '旧库项目名称' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
  const before = requests.filter(item => item.path === '/projects').length;
  act(emitRunning); await waitFor(() => expect(requests.filter(item => item.path === '/projects').length).toBeGreaterThan(before));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
});

it('切库失败且原库项目读取暂不可用时不自动卸载草稿，旧环境读失效后可恢复', async () => {
  const pending = deferred<Response>(); let capReads = 0;
  intercept = (library, path) => {
    if (library === 'a' && path === '/capabilities' && ++capReads === 1) return pending.promise;
    if (library === 'a' && path === '/projects' && switchFailure) return failed('原库暂时无法读取');
  };
  await loadOriginal(); await editDraft(); switchFailure = true; await beginSwitch();
  await screen.findByText('切换失败，原库继续使用');
  fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
  expect(requests.filter(item => item.path === '/projects')).toHaveLength(1);
  await waitFor(() => expect(capReads).toBe(2));
  await act(async () => pending.resolve(response(caps(false))));
  fireEvent.click(screen.getByRole('button', { name: '设备与环境', exact: true }));
  const settings = within(screen.getByRole('dialog', { name: '设备与环境' })); await settings.findByText('旧库设备');
  expect(settings.queryByText('迟到旧库能力')).toBeNull(); expect(settings.getByRole('button', { name: '刷新环境' }).matches(':disabled')).toBe(false);
});

it('普通 host 刷新保留当前草稿与导航，后续分页项目仍正常补取', async () => {
  pagedProjects = true; await loadOriginal(); await editDraft(); act(emitRunning);
  await waitFor(() => expect(requests.filter(item => item.path === '/projects').length).toBe(2));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
  // 另一个同库实例检查后页选中项目；不绕过真实项目选择事件。
  cleanup(); requests = []; render(<App />);
  await screen.findByRole('heading', { name: '旧库任务名称' });
  fireEvent.click(screen.getAllByRole('button', { name: '工作台', exact: true })[0]);
  await screen.findByRole('button', { name: /旧库任务名称/ });
  fireEvent.click(screen.getByRole('button', { name: '加载更多项目' })); await screen.findByRole('option', { name: '旧库后页项目' });
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-second' } }); act(emitRunning);
  await waitFor(() => expect(requests.some(item => item.path === '/projects/project-second')).toBe(true));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-second');
});

it('同库刷新保持读取捕获函数身份，不重建运行轮询或丢失事件游标', async () => {
  let reads = 0;
  const attempt = { id: 'attempt-cursor', task_id: 'task-shared', state: 'running', state_version: 1, last_event_sequence: 2, artifacts: [], allowed_actions: [], snapshot: { kind: 'text', operation: 'generate' } };
  intercept = (library, path) => {
    if (library === 'a' && path === '/tasks/task-shared') return response({ ...task('a'), latest_attempt: attempt });
    if (path === '/attempts/attempt-cursor') { reads += 1; return response({ ...attempt, state: reads === 1 ? 'running' : 'succeeded' }); }
    if (path === '/attempts/attempt-cursor/events?after=0') return response({ items: [{ sequence: 1, type: 'token', payload: { text: 'A片段一' } }] });
    if (path === '/attempts/attempt-cursor/events?after=1') return response({ items: [{ sequence: 2, type: 'token', payload: { text: 'A片段二' } }] });
  };
  await loadOriginal(); fireEvent.click(screen.getByRole('button', { name: /旧库任务名称/ }));
  const input = await screen.findByLabelText('输入内容');
  expect(input.matches(':disabled')).toBe(true);
  expect((input as HTMLTextAreaElement).value).toBe('旧库已存草稿');
  await screen.findByText('A片段一'); act(emitRunning);
  await waitFor(() => expect(requests.filter(item => item.path === '/projects')).toHaveLength(2)); expect(reads).toBe(1);
  await screen.findByText('A片段一A片段二'); expect(reads).toBe(2);
  expect(requests.filter(item => item.path.includes('attempt-cursor/events')).map(item => item.path)).toEqual(['/attempts/attempt-cursor/events?after=0', '/attempts/attempt-cursor/events?after=1']);
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库已存草稿');
});

it('继续任务读取中宿主断连再连接会释放入口，旧响应不能覆盖新的继续操作', async () => {
  const oldRead = deferred<Response>(); const currentRead = deferred<Response>(); let reads = 0;
  intercept = (library, path) => {
    if (library === 'a' && path === '/tasks/task-shared') return ++reads === 1 ? oldRead.promise : currentRead.promise;
  };
  await loadOriginal(); fireEvent.click(screen.getByRole('button', { name: '直接试用' }));
  await waitFor(() => expect(reads).toBe(1));
  expect(screen.getByRole('button', { name: '直接试用' }).matches(':disabled')).toBe(true);
  act(() => host.listener?.({ payload: { state: 'stopped', message: '测试宿主断连' } }));
  await screen.findByText('本机服务尚未连接');
  act(emitRunning);
  await waitFor(() => expect(requests.filter(item => item.path === '/projects')).toHaveLength(2));
  const entry = await screen.findByRole('button', { name: '直接试用' });
  await waitFor(() => expect(entry.matches(':disabled')).toBe(false));
  fireEvent.click(entry); await waitFor(() => expect(reads).toBe(2));
  // 新读取仍待决时，旧回执既不能打开任务，也不能解除新操作的忙碌状态。
  await act(async () => oldRead.resolve(response({ ...task('a'), name: '迟到的旧任务', draft: { ...task('a').draft, input: { prompt: '迟到的旧草稿' } } })));
  expect(screen.queryByRole('heading', { name: '迟到的旧任务' })).toBeNull();
  expect(screen.queryByLabelText('输入内容')).toBeNull();
  expect(screen.getByRole('button', { name: '直接试用' }).matches(':disabled')).toBe(true);
  await act(async () => currentRead.resolve(response({ ...task('a'), name: '重连后任务', draft: { ...task('a').draft, input: { prompt: '重连后的草稿' } } })));
  await screen.findByRole('heading', { name: '重连后任务' });
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('重连后的草稿');
  expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false);
  expect(requests.filter(item => item.path === '/tasks')).toEqual([]);
});

it('host running 先到而 invoke 仍等待时不向新库读取旧项目，成功回执后再挂载', async () => {
  switchGate = deferred<unknown>(); await loadOriginal(); await editDraft(); await beginSwitch();
  expect(bank).toBe('b'); expect(requests.filter(item => item.bank === 'b')).toEqual([]);
  expect(screen.getByRole('option', { name: '旧库项目名称' })).toBeTruthy();
  await act(async () => switchGate!.resolve({})); await expectB();
  expect(requests.some(item => item.bank === 'b' && item.path.includes('project-shared'))).toBe(false);
});

it('切库等待期旧任务轮询完成的 onUpdated 也不能触发旧视图刷新', async () => {
  const pending = deferred<Response>(); const attempt = { id: 'attempt-a', task_id: 'task-shared', state: 'succeeded', state_version: 1, artifacts: [], allowed_actions: [], snapshot: { kind: 'text', operation: 'generate' } };
  intercept = (library, path) => {
    if (library === 'a' && path === '/tasks/task-shared') return response({ ...task('a'), latest_attempt: attempt });
    if (library === 'a' && path === '/attempts/attempt-a') return response(attempt);
    if (library === 'a' && path === '/attempts/attempt-a/events?after=0') return pending.promise;
  };
  await loadOriginal(); await editDraft();
  await waitFor(() => expect(requests.some(item => item.path === '/attempts/attempt-a/events?after=0')).toBe(true));
  switchGate = deferred<unknown>(); await beginSwitch();
  await act(async () => pending.resolve(response({ items: [] })));
  expect(requests.filter(item => item.bank === 'b')).toEqual([]);
  await act(async () => switchGate!.resolve({})); await expectB();
});

it('切库待决时迟到的旧 attempts 不能把 B 事件带回失败回滚后的 A 草稿', async () => {
  sameId = true; const pending = deferred<Response>(); let attemptReads = 0;
  const attempt = { id: 'attempt-shared', task_id: 'task-shared', state: 'succeeded', state_version: 1, artifacts: [], allowed_actions: [], snapshot: { kind: 'text', operation: 'generate' } };
  intercept = (library, path) => {
    if (library === 'a' && path === '/tasks/task-shared') return response({ ...task('a'), latest_attempt: attempt });
    if (library === 'a' && path === '/attempts/attempt-shared') { attemptReads += 1; return attemptReads === 1 ? pending.promise : response({ ...attempt, output_text: 'A库恢复后的正确输出' }); }
    if (library === 'b' && path === '/attempts/attempt-shared/events?after=0') return response({ items: [{ sequence: 1, type: 'token', payload: { text: 'B库独有事件哨兵' } }] });
  };
  await loadOriginal(); await editDraft();
  await waitFor(() => expect(requests.some(item => item.bank === 'a' && item.path === '/attempts/attempt-shared')).toBe(true));
  switchGate = deferred<unknown>(); await beginSwitch(); expect(bank).toBe('b');
  await act(async () => pending.resolve(response(attempt)));
  // 允许目前未冻结的旧轮询继续运行，真正判定失败回滚后是否出现跨库内容。
  await act(async () => { bank = 'a'; switchGate!.reject(new Error('切换失败，已回滚 A 库')); });
  await screen.findByText('切换失败，已回滚 A 库');
  fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect(screen.getByRole('option', { name: '旧库项目名称' })).toBeTruthy();
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
  expect(screen.queryByText('B库独有事件哨兵')).toBeNull();
  await screen.findByText('A库恢复后的正确输出'); expect(attemptReads).toBe(2);
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('旧库未保存草稿');
});

it('旧工作流首读迟到不得从 B 补取步骤状态并带回回滚后的 A 工作流', async () => {
  sameId = true; const pending = deferred<Response>(); let reads = 0;
  const flow = { id: 'workflow-shared', project_id: projectId('a'), name: 'A库工作流', revision: 1, definition_version: 'product-story-v1', current_step: 'image', status: 'active', result_id: null, history: [], steps: Object.fromEntries(['image', 'video', 'audio'].map(kind => [kind, { configuration: { model_id: 'model-shared', runtime: { engine: 'diffusers', device_id: 'apple-gpu', seed: 0 }, input: { prompt: 'A库工作流画面' } }, input_revision: kind === 'image' ? 1 : 0, input_digest: 'fixed', task_id: kind === 'image' ? 'task-flow' : null, step_attempt_id: kind === 'image' ? 'step-flow' : null, accepted: null, stale: false }])), step_attempts: [{ id: 'step-flow', mode: 'compute', attempt_id: 'attempt-flow', source: null }] };
  intercept = (library, path) => {
    if (path.startsWith('/workflow-runs?')) return response({ items: [flow] });
    if (library === 'a' && path === '/workflow-runs/workflow-shared') { reads += 1; return reads === 1 ? pending.promise : response(flow); }
    if (path === '/tasks/task-flow') return response({ ...task(library), id: 'task-flow', kind: 'image' });
    if (path === '/attempts/attempt-flow') return response({ id: 'attempt-flow', task_id: 'task-flow', state: 'failed', state_version: 1, artifacts: [], allowed_actions: [], snapshot: { kind: 'image', operation: 'generate' }, error: { message: library === 'b' ? 'B工作流独有状态哨兵' : 'A库原工作流状态' } });
  };
  await loadOriginal(); fireEvent.click(screen.getByRole('button', { name: /A库工作流/ }));
  await waitFor(() => expect(reads).toBe(1)); switchGate = deferred<unknown>(); await beginSwitch();
  await act(async () => pending.resolve(response(flow)));
  await act(async () => { bank = 'a'; switchGate!.reject(new Error('工作流切库失败，已回滚 A 库')); });
  await screen.findByText('工作流切库失败，已回滚 A 库'); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect(screen.getByRole('option', { name: '旧库项目名称' })).toBeTruthy(); expect(screen.queryByText('B工作流独有状态哨兵')).toBeNull();
  await screen.findByText('A库原工作流状态'); expect(screen.getByRole('heading', { name: 'A库工作流' })).toBeTruthy();
});

it.each(['切换等待中', '新库已挂载'])('旧能力在%s返回不会接着读取新库设备，新库自己的探测正常', async stage => {
  const pending = deferred<Response>(); intercept = (library, path) => library === 'a' && path === '/capabilities' ? pending.promise : undefined;
  await loadOriginal(); switchGate = deferred<unknown>(); await beginSwitch();
  if (stage === '新库已挂载') { await act(async () => switchGate!.resolve({})); await expectB(); await waitFor(() => expect(requests.filter(item => item.bank === 'b' && item.path === '/devices')).toHaveLength(1)); }
  const deviceReads = requests.filter(item => item.path === '/devices').length;
  await act(async () => pending.resolve(response(caps(false))));
  expect(requests.filter(item => item.path === '/devices')).toHaveLength(deviceReads);
  if (stage === '切换等待中') { await act(async () => switchGate!.resolve({})); await expectB(); }
  fireEvent.click(screen.getByRole('button', { name: '设备与环境', exact: true }));
  const settings = within(screen.getByRole('dialog', { name: '设备与环境' })); await settings.findByText('新库设备');
  expect(settings.queryByText('迟到旧库能力')).toBeNull(); expect(settings.getByText('模型：环境已准备，可选择模型检查')).toBeTruthy();
});

it('切库等待期旧项目首分页返回也不能继续补取旧项目 ID', async () => {
  const pending = deferred<Response>(); await loadOriginal();
  intercept = (library, path) => library === 'a' && path === '/projects' ? pending.promise : undefined;
  act(emitRunning); await waitFor(() => expect(requests.filter(item => item.bank === 'a' && item.path === '/projects')).toHaveLength(2));
  switchGate = deferred<unknown>(); await beginSwitch();
  await act(async () => pending.resolve(response({ items: [] })));
  expect(requests.filter(item => item.bank === 'b')).toEqual([]);
  await act(async () => switchGate!.resolve({})); await expectB();
});

it.each(['projects', 'models'])('旧库 %s 分页的成功与失败迟到均不覆盖新库', async collection => {
  for (const fail of [false, true]) {
    const pending = deferred<Response>(); await loadOriginal();
    intercept = (library, path) => library === 'a' && path.startsWith(`/${collection}?`) && path.includes('cursor=') ? pending.promise : undefined;
    if (collection === 'models') fireEvent.click(screen.getByRole('button', { name: '模型库', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: collection === 'projects' ? '加载更多项目' : '加载更多模型' }));
    await completedSwitch(); await expectB();
    await act(async () => pending.resolve(fail ? failed('迟到旧库错误') : response({ items: [{ id: 'late-a', name: '迟到旧库内容' }], next_cursor: 'late-cursor' })));
    await expectB(); expect(screen.queryByText('迟到旧库内容')).toBeNull(); expect(screen.queryByRole('button', { name: '加载更多项目' })).toBeNull();
    cleanup(); bank = 'a'; requests = []; intercept = undefined;
    // 成功／失败是两份独立库样本；新实现会恢复页面，下一样本需重置夹具存储。
    savedTasks = new Map(); contexts = { a: { project_id: null, projects: {} }, b: { project_id: null, projects: {} } };
  }
});

it.each(['models', 'datasets', 'tasks', 'works', 'adapters', 'evaluation-plans', 'candidates', 'materials', 'workflow-runs', 'model-downloads'])('旧 %s 资源列表成功与失败迟到均属于旧视图', async collection => {
  for (const fail of [false, true]) {
    const pending = deferred<Response>(); await loadOriginal();
    intercept = (library, path) => library === 'a' && path.startsWith(`/${collection}?`) ? pending.promise : undefined;
    const before = requests.length; act(emitRunning);
    await waitFor(() => expect(requests.slice(before).some(item => item.path.startsWith(`/${collection}?`))).toBe(true));
    await completedSwitch(); await expectB();
    await act(async () => pending.resolve(fail ? failed('迟到旧库错误') : response({ items: [{ id: 'late-a', name: '迟到旧库内容' }] })));
    await expectB(); fireEvent.click(screen.getByRole('button', { name: '模型库', exact: true })); await screen.findByText('新库模型内容');
    expect(screen.queryByText('迟到旧库内容')).toBeNull(); expect(screen.queryByText('迟到旧库错误')).toBeNull();
    cleanup(); bank = 'a'; requests = []; intercept = undefined;
    // 成功／失败是两份独立库样本；新实现会恢复页面，下一样本需重置夹具存储。
    savedTasks = new Map(); contexts = { a: { project_id: null, projects: {} }, b: { project_id: null, projects: {} } };
  }
});

it.each([false, true])('旧草稿引用补取迟到（失败=%s）不能回填新库', async fail => {
  missingReference = true; const pending = deferred<Response>(); intercept = (library, path) => library === 'a' && path === '/models/model-reference' ? pending.promise : undefined;
  await loadOriginal(); await editDraft(); await waitFor(() => expect(requests.some(item => item.path === '/models/model-reference')).toBe(true));
  await completedSwitch(); await expectB(); await act(async () => pending.resolve(fail ? failed('迟到旧库错误') : response({ ...model('a', 'model-reference'), name: '迟到旧库内容' })));
  await expectB(); fireEvent.click(screen.getByRole('button', { name: '模型库', exact: true })); await screen.findByText('新库模型内容');
  expect(screen.queryByText('迟到旧库内容')).toBeNull(); expect(screen.queryByText('迟到旧库错误')).toBeNull();
});

it.each([false, true])('原导出弹窗轮询迟到（失败=%s）不会重开或污染新库', async fail => {
  const pending = deferred<Response>(); let reads = 0;
  intercept = (library, path) => {
    if (library === 'a' && path.startsWith('/tasks?')) return response({ items: [{ ...task('a'), operation: 'export', export_id: 'export-a', name: '旧库导出任务' }] });
    if (library === 'a' && path === '/exports/export-a') { reads += 1; return reads === 1 ? response({ id: 'export-a', object_id: 'work-shared', object_type: 'work', object_name: '旧库作品', state: 'succeeded', state_version: 1, verified_path: '/fixture/a' }) : pending.promise; }
  };
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /旧库导出任务/ }));
  await screen.findByRole('dialog', { name: '导出旧库作品' }); await waitFor(() => expect(reads).toBe(2));
  await completedSwitch(); await expectB();
  await act(async () => pending.resolve(fail ? failed('迟到旧库错误') : response({ id: 'export-a', state: 'failed', error: { message: '迟到旧库错误' } })));
  expect(screen.queryByRole('dialog')).toBeNull(); await expectB();
});

it('AC22 真实App切库待决期间，旧控制POST迟到不能向B补GET或回填B输出', async () => {
  sameId = true; const pending = deferred<Response>();
  const attempt = { id: 'attempt-action-shared', task_id: 'task-shared', state: 'failed', state_version: 3,
    compute_outcome: 'succeeded', collection_state: 'failed', collection_version: 0,
    output_manifest_ref: { digest: 'fixture-manifest' }, output_text: 'A库控制前输出', artifacts: [],
    allowed_actions: ['collect'], snapshot: { kind: 'text', operation: 'generate' } };
  intercept = (library, path) => {
    if (path === '/tasks/task-shared') return response({ ...task(library), latest_attempt: attempt });
    if (path === '/attempts/attempt-action-shared/collections') return pending.promise;
    if (path === '/attempts/attempt-action-shared') return response({ ...attempt,
      output_text: library === 'a' ? 'A库控制前输出' : 'B库迟到控制输出哨兵' });
    if (path === '/attempts/attempt-action-shared/events?after=0') return response({ items: [] });
  };
  await loadOriginal(); fireEvent.click(screen.getByRole('button', { name: /旧库任务名称/ }));
  fireEvent.click(await screen.findByRole('button', { name: '只补收已有产物' }));
  await waitFor(() => expect(requests.filter(item => item.path.endsWith('/collections'))).toHaveLength(1));
  switchGate = deferred<unknown>(); await beginSwitch(); expect(bank).toBe('b');
  await act(async () => pending.resolve(response({ state: 'succeeded' })));
  expect.soft(requests.filter(item => item.bank === 'b')).toEqual([]);
  expect.soft(screen.queryByText('B库迟到控制输出哨兵')).toBeNull();
  await act(async () => switchGate!.resolve({})); await expectB();
});

it('AC22 同库保存作品在途时进入作品页，保存成功后列表应出现新作品', async () => {
  const pending = deferred<Response>(); let saved = false;
  const work = { id: 'work-just-saved', name: '刚保存的同库作品', text: '同库保存完成后的正文', kind: 'text', attempt_id: 'attempt-save-navigation' };
  const attempt = { id: 'attempt-save-navigation', task_id: 'task-shared', project_id: projectId('a'),
    state: 'succeeded', state_version: 3, output_text: '本次生成正文', allowed_actions: [],
    artifacts: [{ id: 'artifact-result', name: 'result.txt', media_type: 'text/plain' }],
    snapshot: { kind: 'text', operation: 'generate' } };
  intercept = (library, path) => {
    if (path === '/tasks/task-shared') return response({ ...task(library), latest_attempt: attempt });
    if (path === '/attempts/attempt-save-navigation') return response(attempt);
    if (path === '/attempts/attempt-save-navigation/events?after=0') return response({ items: [] });
    if (path === '/works') return pending.promise;
    if (path.startsWith('/works?')) return response({ items: saved ? [work] : [] });
  };
  await loadOriginal(); fireEvent.click(screen.getByRole('button', { name: /旧库任务名称/ }));
  fireEvent.click(await screen.findByRole('button', { name: '保存作品', exact: true }));
  await waitFor(() => expect(requests.filter(item => item.path === '/works')).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', { name: '作品与素材', exact: true }));
  await screen.findByRole('heading', { name: '作品与素材', exact: true });
  expect(screen.queryByLabelText('运行结果')).toBeNull();
  expect(screen.queryByText(work.name)).toBeNull(); expect(bank).toBe('a');
  const beforeSuccess = requests.length;
  await act(async () => { saved = true; pending.resolve(response(work)); });
  await screen.findByText(work.name);
  expect(requests.slice(beforeSuccess).some(item => item.bank === 'a' && item.path.startsWith('/works?'))).toBe(true);
});
