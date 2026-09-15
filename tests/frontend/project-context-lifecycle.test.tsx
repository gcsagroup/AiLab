import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';
import { defaultRuntime } from '../../apps/desktop/src/Workbench';
import { defaultProjectView, type LibraryViews, type ProjectView } from '../../apps/desktop/src/ProjectContext';
import type { Task } from '../../apps/desktop/src/types';

// 保留真实 App、任务表单、选择队列与退出准备，只控制 IPC 和宿主事件顺序。
const host = vi.hoisted(() => ({ listeners: new Map<string, (event: { payload: unknown }) => void>() }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => {
  host.listeners.set(name, listener);
  return () => { if (host.listeners.get(name) === listener) host.listeners.delete(name); };
}) }));

type Request = { method: string; path: string; body?: unknown };
type ContextWrite = { project_id: string; context: ProjectView };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const projects = [{ id: 'project-a', name: '甲项目', revision: 1 }, { id: 'project-b', name: '乙项目', revision: 1 }];
const taskId = (projectId: string) => `task-${projectId}`;
let tasks: Map<string, Task>, saved: LibraryViews, requests: Request[], writes: ContextWrite[];
let getContext: (() => unknown) | undefined;
let modelsB: ReturnType<typeof deferred<unknown>> | undefined;
let saveB: ReturnType<typeof deferred<void>> | undefined;
let acknowledgements: { requestId: number; success: boolean; saved: LibraryViews }[];

beforeEach(() => {
  host.listeners.clear(); requests = []; writes = []; acknowledgements = [];
  getContext = undefined; modelsB = undefined; saveB = undefined;
  saved = { project_id: null, projects: {} };
  tasks = new Map(projects.map(project => {
    const task: Task = { id: taskId(project.id), project_id: project.id, name: `${project.name}语言草稿`,
      kind: 'text', operation: 'generate', draft_revision: 1, attempts: [],
      draft: { kind: 'text', operation: 'generate', model_id: `model-${project.id}`, dataset_id: null,
        input: { prompt: `${project.name}原始正文` }, runtime: { ...defaultRuntime } } };
    return [task.id, task];
  }));
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.mocked(invoke).mockReset().mockImplementation(async (command, args) => {
    if (command === 'complete_exit_preparation') {
      acknowledgements.push({ ...(args as { requestId: number; success: boolean }), saved: structuredClone(saved) });
      return {};
    }
    if (command === 'record_first_frame') return {};
    if (command !== 'api_request') throw new Error(`本用例没有授权额外宿主操作：${command}`);
    const input = (args as { request: Request }).request;
    const request = { ...input, path: input.path.replace('/api/v1', '') };
    requests.push(structuredClone(request));
    const url = new URL(request.path, 'http://fixture');
    const path = url.pathname;
    if (path === '/ui-context') {
      if (request.method === 'GET') return getContext ? await getContext() : structuredClone(saved);
      if (request.method !== 'PATCH') throw new Error('选择接口只允许 GET/PATCH');
      const value = structuredClone(request.body) as ContextWrite;
      writes.push(value);
      if (value.project_id === 'project-b' && saveB) await saveB.promise;
      saved = { project_id: value.project_id, projects: { ...saved.projects, [value.project_id]: value.context } };
      return structuredClone(saved);
    }
    if (request.method === 'PATCH' && /^\/tasks\/[^/]+\/draft$/.test(path)) {
      const id = path.split('/')[2], task = tasks.get(id)!;
      const body = request.body as { expected_revision: number; draft: Task['draft'] };
      if (body.expected_revision !== task.draft_revision) throw { error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突' } };
      const updated = { ...task, draft_revision: task.draft_revision + 1, draft: structuredClone(body.draft) };
      tasks.set(id, updated); return structuredClone(updated);
    }
    if (request.method !== 'GET') throw new Error(`本用例不允许模型运行或其他写入：${request.method} ${path}`);
    if (path === '/projects') return { items: structuredClone(projects) };
    if (path.startsWith('/projects/')) return structuredClone(projects.find(project => project.id === path.split('/')[2]));
    if (path === '/capabilities') return { items: [{ kind: 'text', operation: 'generate', supported: true }] };
    if (path === '/devices') return { items: [{ id: 'apple-gpu', name: '夹具设备', status: 'ready' }] };
    const projectId = url.searchParams.get('project_id');
    if (path === '/models' && projectId === 'project-b' && modelsB) return await modelsB.promise;
    if (path === '/models') return { items: [{ id: `model-${projectId}`, name: '夹具模型身份', modality: 'text', format: 'safetensors', status: 'ready' }] };
    if (path === '/tasks') return { items: [...tasks.values()].filter(task => task.project_id === projectId).map(({ draft, attempts, ...task }) => task) };
    if (path.startsWith('/tasks/')) return structuredClone(tasks.get(path.split('/')[2]));
    return { items: [], next_cursor: null };
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); host.listeners.clear(); });

async function start() {
  render(<App />);
  await screen.findByRole('button', { name: /^甲项目语言草稿/ });
  await waitFor(() => expect(host.listeners.has('prepare-exit')).toBe(true));
}

it('首次选择读取失败仍可编辑任务，迟到重试读取其他项目选择不跳走或覆盖眼前输入', async () => {
  const retry = deferred<LibraryViews>(); let reads = 0;
  const oldB = { ...defaultProjectView(), task_id: taskId('project-b') };
  saved = { project_id: 'project-b', projects: { 'project-b': oldB } };
  getContext = () => {
    reads += 1;
    if (reads === 1) throw { error: { code: 'UI_CONTEXT_INVALID', message: '选择记录暂时不可读' } };
    return retry.promise;
  };
  await start();
  expect(screen.getByText(/上次选择暂未读回，当前页面可继续使用/)).toBeTruthy();
  expect(screen.getByText('本机服务已连接')).toBeTruthy();
  expect(writes).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: /^甲项目语言草稿/ }));
  const input = await screen.findByLabelText('输入内容');
  fireEvent.change(input, { target: { value: '重试前仍在甲项目编辑' } });
  fireEvent.click(screen.getByRole('button', { name: '重试保存当前选择' }));
  await waitFor(() => expect(reads).toBe(2));
  const latest = '选择读取还没返回时继续输入，必须保留这一稿';
  fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: latest } });
  expect(writes).toEqual([]);
  await act(async () => retry.resolve({ project_id: 'project-b', projects: { 'project-b': oldB } }));
  await waitFor(() => expect(saved.projects['project-a']?.task_id).toBe(taskId('project-a')));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-a');
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe(latest);
  expect(screen.getByRole('heading', { name: '甲项目语言草稿', exact: true })).toBeTruthy();
  expect(screen.queryByRole('heading', { name: '乙项目语言草稿', exact: true })).toBeNull();
  expect(saved.project_id).toBe('project-a');
  expect(saved.projects['project-b']).toEqual(oldB);
  expect(writes.every(write => write.project_id === 'project-a' && write.context.task_id === taskId('project-a'))).toBe(true);
  expect(requests.filter(request => request.method !== 'GET').every(request => request.path === '/ui-context' || request.path === `/tasks/${taskId('project-a')}/draft`)).toBe(true);
});

it('选乙项目后模型列表仍待决，退出成功回执必须等乙项目原任务选择保存且不写空对象', async () => {
  const viewB = { ...defaultProjectView(), task_id: taskId('project-b') };
  saved = { project_id: 'project-a', projects: { 'project-a': defaultProjectView(), 'project-b': viewB } };
  modelsB = deferred<unknown>(); saveB = deferred<void>();
  await start();
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect(requests.some(request => request.path === '/models?project_id=project-b')).toBe(true));
  await waitFor(() => expect(writes.some(write => write.project_id === 'project-b')).toBe(true));
  expect(screen.getByText('正在读取项目内容')).toBeTruthy();
  expect(saved.project_id).toBe('project-a');
  await act(async () => { host.listeners.get('prepare-exit')!({ payload: { request_id: 41, cancelled: false } }); });
  expect(acknowledgements).toEqual([]);
  expect(writes.filter(write => write.project_id === 'project-b').every(write => write.context.task_id === taskId('project-b'))).toBe(true);
  await act(async () => saveB!.resolve());
  await waitFor(() => expect(acknowledgements).toHaveLength(1));
  expect(acknowledgements[0]).toEqual({ requestId: 41, success: true,
    saved: { project_id: 'project-b', projects: { 'project-a': defaultProjectView(), 'project-b': viewB } } });
  // 模型列表仍未返回；退出保存不应等待列表，也不能用加载中的 null 覆盖原选择。
  expect(screen.getByText('正在读取项目内容')).toBeTruthy();
  expect(writes.filter(write => write.project_id === 'project-b').every(write => write.context.task_id === taskId('project-b'))).toBe(true);
  expect(requests.filter(request => request.method !== 'GET').every(request => request.path === '/ui-context')).toBe(true);
});
