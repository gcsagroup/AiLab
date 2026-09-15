import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import { defaultRuntime, defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import { defaultProjectView, type ProjectView } from '../../apps/desktop/src/ProjectContext';
import type { Kind, Operation, Task } from '../../apps/desktop/src/types';
import trainingContracts from './fixtures/training-contracts.json';

// 仅替换 JSON 传输；分类、任务选择、分页与持久化队列均由真实 App 决定。
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));

type Slot = `${Kind}:${Operation}`;
type View = ProjectView & { recent_tasks?: Partial<Record<Slot, string>> };
type Request = { method: string; path: string; body?: unknown };
type Page = { items: Partial<Task>[]; next_cursor: string | null };
let projects: { id: string; name: string; revision: number }[];
const categoryNames: Record<Kind, RegExp> = { text: /^模型训练 \/ 微调/, image: /^图片训练 \/ 微调/, video: /^视频训练 \/ 微调/, audio: /^音频训练 \/ 微调/ };
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const response = (value: unknown, ok = true): Response => ({ ok, json: async () => clone(value) }) as Response;
let tasks: Map<string, Task>, requests: Request[];
let saved: { project_id: string | null; projects: Record<string, View> };
let taskPages: Map<string, Page[]>;
let taskRead: ((id: string) => Promise<Response> | Response | undefined) | undefined;
let created: number;

function makeTask(id: string, kind: Kind = 'text', operation: Operation = 'generate', projectId = 'project-a'): Task {
  return { id, project_id: projectId, name: `草稿 ${id}`, kind, operation, draft_revision: 7,
    created_at: '2026-09-13T01:00:00Z', attempts: [], draft: {
      kind, operation, model_id: null, dataset_id: null,
      input: kind === 'video' ? { material_id: null } : { prompt: `原始输入 ${id}` },
      runtime: { ...(kind === 'text' ? operation === 'train' ? defaultTrainingRuntime : defaultRuntime : defaultMediaRuntime(kind, operation === 'train')), seed: 37 },
    } };
}
function summary(task: Task): Partial<Task> { const { draft, attempts, ...value } = task; return value; }
function add(...values: Task[]) { values.forEach(task => tasks.set(task.id, clone(task))); }
function remember(projectId: string, recent: Partial<Record<Slot, string>>, operation: Operation = 'generate') {
  saved.project_id = projectId;
  saved.projects[projectId] = { ...defaultProjectView(), module_tab: operation, recent_tasks: recent };
}
function checkView(projectId: string, view: View) {
  expect(Object.keys(view).sort()).toEqual(expect.arrayContaining(['page', 'kind', 'module_tab', 'data_tab', 'task_id', 'workflow_id']));
  expect(Object.keys(view).every(key => ['page', 'kind', 'module_tab', 'data_tab', 'task_id', 'workflow_id', 'recent_tasks'].includes(key))).toBe(true);
  expect(['home', 'models', 'data', 'lab', 'assets']).toContain(view.page);
  expect(['text', 'image', 'video', 'audio']).toContain(view.kind);
  expect(['train', 'generate', 'history']).toContain(view.module_tab);
  expect(['local', 'market']).toContain(view.data_tab);
  for (const field of ['task_id', 'workflow_id'] as const) expect(view[field] === null || typeof view[field] === 'string').toBe(true);
  if (view.task_id) expect(tasks.get(view.task_id)?.project_id).toBe(projectId);
  if (view.recent_tasks !== undefined) {
    expect(view.recent_tasks && typeof view.recent_tasks === 'object' && !Array.isArray(view.recent_tasks)).toBe(true);
    for (const [slot, id] of Object.entries(view.recent_tasks)) {
      expect(slot).toMatch(/^(text|image|video|audio):(train|generate)$/);
      expect(typeof id).toBe('string'); expect(id.length).toBeGreaterThan(0);
      // 允许已删除编号留待 GET 返回 404；现存编号必须归属正确项目与槽位。
      const task = tasks.get(id);
      if (task) { expect(task.project_id).toBe(projectId); expect(`${task.kind}:${task.operation}`).toBe(slot); }
    }
  }
}

beforeEach(() => {
  projects = [{ id: 'project-a', name: '甲项目', revision: 1 }, { id: 'project-b', name: '乙项目', revision: 1 }];
  tasks = new Map(); requests = []; saved = { project_id: null, projects: {} }; taskPages = new Map(); taskRead = undefined; created = 0;
  localStorage.clear(); sessionStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(String(input), 'http://fixture');
    const path = url.pathname.replace('/api/v1', '');
    const method = options.method || 'GET';
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : undefined;
    requests.push({ method, path: `${path}${url.search}`, ...(body === undefined ? {} : { body: clone(body) }) });
    if (path === '/ui-context') {
      if (method === 'GET') return response(saved);
      if (method !== 'PATCH') throw new Error(`选择接口不支持 ${method}`);
      expect(Object.keys(body).sort()).toEqual(['context', 'project_id']);
      expect(projects.some(project => project.id === body.project_id)).toBe(true);
      checkView(body.project_id, body.context);
      saved = { project_id: body.project_id, projects: { ...saved.projects, [body.project_id]: clone(body.context) } };
      return response(saved);
    }
    if (method === 'POST' && path === '/projects') {
      expect(Object.keys(body)).toEqual(['name']); expect(typeof body.name).toBe('string');
      const project = { id: 'project-created-c', name: body.name, revision: 1 };
      expect(projects.some(item => item.id === project.id)).toBe(false);
      projects.push(project); return response(project);
    }
    if (method === 'POST' && path === '/tasks') {
      expect(Object.keys(body).sort()).toEqual(['kind', 'name', 'operation', 'project_id']);
      expect(projects.some(project => project.id === body.project_id)).toBe(true);
      expect(['text', 'image', 'video', 'audio']).toContain(body.kind); expect(['train', 'generate']).toContain(body.operation);
      const task = { ...makeTask(`task-created-${++created}`, body.kind, body.operation, body.project_id), name: body.name, draft_revision: 1 };
      add(task); return response(task);
    }
    if (method !== 'GET') throw new Error(`续做不得修改草稿、检查配置或开始运行：${method} ${path}`);
    if (path === '/projects') return response({ items: projects, next_cursor: null });
    if (/^\/projects\/[^/]+$/.test(path)) return response(projects.find(project => path === `/projects/${project.id}`));
    if (path === '/capabilities') return response({ items: ['text', 'image', 'video', 'audio'].flatMap(kind => ['train', 'generate'].map(operation => ({ kind, operation, supported: operation === 'generate' || ['text', 'image'].includes(kind), status: 'ready' }))) });
    if (path === '/devices') return response({ items: [{ id: 'apple-gpu', name: '夹具设备', status: 'ready' }] });
    if (path === '/training-contracts') return response(trainingContracts);
    if (path === '/tasks') {
      const projectId = url.searchParams.get('project_id')!;
      expect(projects.some(project => project.id === projectId)).toBe(true);
      const pages = taskPages.get(projectId);
      if (!pages) return response({ items: [...tasks.values()].filter(task => task.project_id === projectId).map(summary), next_cursor: null });
      const index = url.searchParams.has('cursor') ? Number(url.searchParams.get('cursor')!.replace('page-', '')) : 0;
      expect(Number.isInteger(index) && index >= 0 && index < pages.length).toBe(true);
      return response(pages[index]);
    }
    const id = /^\/tasks\/([^/]+)$/.exec(path)?.[1];
    if (id) {
      const overridden = taskRead?.(id); if (overridden !== undefined) return await overridden;
      return tasks.has(id) ? response(tasks.get(id)) : response({ error: { code: 'RESOURCE_NOT_FOUND', message: '任务已不存在' } }, false);
    }
    if (['/models', '/datasets', '/works', '/adapters', '/evaluation-plans', '/candidates', '/materials', '/workflow-runs', '/model-downloads', '/execution-targets', '/ai/requests'].includes(path)) return response({ items: [], next_cursor: null });
    throw new Error(`本测试没有登记读取接口：${path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear(); });

async function start() {
  const mounted = render(<App />);
  await screen.findByRole('heading', { name: '模型训练与运行', exact: true });
  return mounted;
}
async function home() {
  fireEvent.click(screen.getAllByRole('button', { name: '工作台', exact: true }).at(-1)!);
  await screen.findByRole('heading', { name: '模型训练与运行', exact: true });
}
function category(kind: Kind, operation: Operation) {
  fireEvent.click(screen.getByRole('button', { name: categoryNames[kind] }));
  fireEvent.click(screen.getByRole('tab', { name: operation === 'train' ? '训练 / 微调' : '运行 / 试用', exact: true }));
}
async function expectOpened(task: Task) {
  await screen.findByRole('heading', { name: task.name, exact: true });
  await waitFor(() => expect(saved.projects[task.project_id]?.task_id).toBe(task.id));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(task.project_id);
  expect((screen.getByLabelText('随机种子') as HTMLInputElement).value).toBe('37');
  if (task.operation === 'generate' && task.kind !== 'video') expect((screen.getByLabelText(task.kind === 'text' ? '输入内容' : task.kind === 'image' ? '画面描述' : '配音文本') as HTMLTextAreaElement).value).toBe(task.draft.input.prompt);
}
function onlySelectionWrites() { expect(requests.filter(request => request.method !== 'GET').every(request => request.method === 'PATCH' && request.path === '/ui-context')).toBe(true); }

it('选择较早语言任务后返回首页、切换项目及重挂载仍续做该编号，不按列表首项重建', async () => {
  const newer = makeTask('task-newer'), older = makeTask('task-older'); older.created_at = '2026-09-12T01:00:00Z'; add(newer, older);
  const original = clone([...tasks.values()]); const mounted = await start();
  fireEvent.click(screen.getByRole('button', { name: /^草稿 task-older/ })); await expectOpened(older); await home();
  await waitFor(() => expect(saved.projects['project-a'].recent_tasks?.['text:generate']).toBe(older.id));
  expect(saved.projects['project-a'].task_id).toBeNull();
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect(saved.project_id).toBe('project-b'));
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-a' } });
  await waitFor(() => expect(saved.project_id).toBe('project-a'));
  mounted.unmount(); await start(); category('text', 'generate');
  fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await expectOpened(older);
  expect([...tasks.values()]).toEqual(original); expect(requests.some(request => request.path === `/tasks/${older.id}`)).toBe(true); onlySelectionWrites();
});

it('四类运行和语言图片训练各记自己的槽位，分类续做不串任务或执行计算', async () => {
  const combinations: [Kind, Operation][] = [['text', 'generate'], ['image', 'generate'], ['video', 'generate'], ['audio', 'generate'], ['text', 'train'], ['image', 'train']];
  const values = combinations.map(([kind, operation]) => makeTask(`task-${kind}-${operation}`, kind, operation)); add(...values);
  const original = clone([...tasks.values()]); await start();
  for (const task of values) {
    category(task.kind as Kind, task.operation as Operation);
    fireEvent.click(screen.getByRole('tab', { name: '任务与结果', exact: true }));
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${task.name}`) })); await expectOpened(task); await home();
    category(task.kind as Kind, task.operation as Operation);
    fireEvent.click(await screen.findByRole('button', { name: task.operation === 'train' ? '继续上次训练' : '继续上次运行', exact: true }));
    await expectOpened(task); await home();
  }
  expect(saved.projects['project-a'].recent_tasks).toEqual(Object.fromEntries(values.map(task => [`${task.kind}:${task.operation}`, task.id])));
  expect([...tasks.values()]).toEqual(original); onlySelectionWrites();
});

it('槽位任务不在首屏时直接读取完整编号，不因首屏缺失创建任务', async () => {
  const target = makeTask('task-offscreen'), unrelated = makeTask('task-first-image', 'image'); add(target, unrelated);
  remember('project-a', { 'text:generate': target.id });
  taskPages.set('project-a', [{ items: [summary(unrelated)], next_cursor: 'page-1' }, { items: [summary(target)], next_cursor: null }]);
  await start(); fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await expectOpened(target);
  expect(requests.some(request => request.path === `/tasks/${target.id}`)).toBe(true);
  expect(requests.some(request => request.path.includes('cursor=page-1'))).toBe(false); onlySelectionWrites();
});

it('无槽位时跨页跳过其他类别操作、工作流和只读草稿，读取首个普通同类任务', async () => {
  const target = makeTask('task-page-two'), wrongKind = makeTask('task-image', 'image'), wrongOperation = makeTask('task-training', 'text', 'train');
  const workflow = { ...makeTask('task-workflow'), workflow_ref: { workflow_run_id: 'workflow-one' } };
  const immutable = { ...makeTask('task-immutable'), immutable_draft: true }; add(wrongKind, wrongOperation, workflow, immutable, target);
  taskPages.set('project-a', [{ items: [wrongKind, wrongOperation, workflow, immutable].map(summary), next_cursor: 'page-1' }, { items: [summary(target)], next_cursor: null }]);
  await start(); category('text', 'generate');
  fireEvent.click(await screen.findByRole('button', { name: '运行 / 试用', exact: true })); await expectOpened(target);
  expect(requests.some(request => request.path === '/tasks?project_id=project-a&cursor=page-1')).toBe(true);
  expect(requests.some(request => request.path === `/tasks/${target.id}`)).toBe(true);
  expect(saved.projects['project-a'].recent_tasks?.['text:generate']).toBe(target.id); onlySelectionWrites();
});

it('显式新建训练与新建试用每次只创建一份，已有任务保留且新编号记入对应槽', async () => {
  const old = makeTask('task-existing'); add(old); const original = clone(old); await start();
  expect(screen.getByRole('button', { name: '开始训练 / 微调', exact: true })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '新建训练', exact: true }));
  await waitFor(() => expect(saved.projects['project-a'].recent_tasks?.['text:train']).toBe('task-created-1'));
  await home(); category('text', 'generate');
  expect(screen.getByRole('button', { name: '继续上次运行', exact: true })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '新建试用', exact: true }));
  await waitFor(() => expect(saved.projects['project-a'].recent_tasks?.['text:generate']).toBe('task-created-2'));
  expect(tasks.get(old.id)).toEqual(original);
  expect(requests.filter(request => request.method !== 'GET' && request.path !== '/ui-context').map(request => [request.method, request.path, (request.body as { operation: string }).operation])).toEqual([['POST', '/tasks', 'train'], ['POST', '/tasks', 'generate']]);
});

it('上次编号返回不存在时分页回退至现存同类任务，不把一次404当作新建指令', async () => {
  const target = makeTask('task-surviving'), other = makeTask('task-other-kind', 'audio'); add(target, other);
  remember('project-a', { 'text:generate': 'task-deleted' });
  taskPages.set('project-a', [{ items: [summary(other)], next_cursor: 'page-1' }, { items: [summary(target)], next_cursor: null }]);
  await start(); fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await expectOpened(target);
  expect(requests.some(request => request.path === '/tasks/task-deleted')).toBe(true);
  expect(requests.some(request => request.path.includes('cursor=page-1'))).toBe(true);
  expect(saved.projects['project-a'].recent_tasks?.['text:generate']).toBe(target.id); onlySelectionWrites();
});

it('续做读取错误显示原错误并保留槽位，不回退列表或自动新建', async () => {
  const target = makeTask('task-unreadable'); add(target); remember('project-a', { 'text:generate': target.id });
  taskRead = id => id === target.id ? response({ error: { code: 'READ_FAILED', message: '原任务暂时无法读取，请稍后重试' } }, false) : undefined;
  await start(); const readsBefore = requests.filter(request => request.path.startsWith('/tasks?')).length;
  fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true }));
  await screen.findByText('原任务暂时无法读取，请稍后重试');
  expect(requests.filter(request => request.path.startsWith('/tasks?'))).toHaveLength(readsBefore);
  expect(saved.projects['project-a'].recent_tasks?.['text:generate']).toBe(target.id);
  expect(saved.projects['project-a'].task_id).toBeNull(); onlySelectionWrites();
});

it('甲项目续做请求迟到时不污染已切换的乙项目选择与正文', async () => {
  const old = makeTask('task-late-a'), current = makeTask('task-current-b', 'text', 'generate', 'project-b'); add(old, current);
  remember('project-b', { 'text:generate': current.id }); remember('project-a', { 'text:generate': old.id });
  let finish!: (value: Response) => void;
  taskRead = id => id === old.id ? new Promise<Response>(resolve => { finish = resolve; }) : undefined;
  await start(); fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await waitFor(() => expect(finish).toBeTruthy());
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect(saved.project_id).toBe('project-b'));
  fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await expectOpened(current);
  await act(async () => finish(response(old)));
  expect(screen.queryByRole('heading', { name: old.name, exact: true })).toBeNull();
  await expectOpened(current); expect(saved.project_id).toBe('project-b');
  expect(saved.projects['project-b'].recent_tasks).toEqual({ 'text:generate': current.id });
  expect(saved.projects['project-a'].recent_tasks).toEqual({ 'text:generate': old.id }); onlySelectionWrites();
});

it('甲项目续做尚未返回时新建丙项目可建立首任务，旧响应不覆盖丙项目', async () => {
  const old = makeTask('task-pending-before-create'); add(old); remember('project-a', { 'text:generate': old.id });
  let finish!: (value: Response) => void;
  taskRead = id => id === old.id ? new Promise<Response>(resolve => { finish = resolve; }) : undefined;
  await start(); fireEvent.click(await screen.findByRole('button', { name: '继续上次运行', exact: true })); await waitFor(() => expect(finish).toBeTruthy());
  fireEvent.click(screen.getByRole('button', { name: '新建项目', exact: true }));
  fireEvent.change(await screen.findByLabelText('项目名称'), { target: { value: '丙项目' } });
  fireEvent.click(screen.getByRole('button', { name: '创建项目', exact: true }));
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-created-c'));
  const entry = await screen.findByRole('button', { name: '开始训练 / 微调', exact: true });
  expect((entry as HTMLButtonElement).disabled).toBe(false); fireEvent.click(entry);
  await waitFor(() => expect(tasks.get('task-created-1')?.project_id).toBe('project-created-c'));
  const current = clone(tasks.get('task-created-1')!); await expectOpened(current);
  await act(async () => finish(response(old)));
  await expectOpened(current); expect(screen.queryByRole('heading', { name: old.name, exact: true })).toBeNull();
  expect(saved.project_id).toBe('project-created-c');
  expect(saved.projects['project-created-c'].recent_tasks).toEqual({ 'text:train': current.id });
  expect(tasks.get(old.id)).toEqual(old);
  expect(requests.filter(request => request.method !== 'GET' && request.path !== '/ui-context').map(request => [request.method, request.path])).toEqual([['POST', '/projects'], ['POST', '/tasks']]);
});
