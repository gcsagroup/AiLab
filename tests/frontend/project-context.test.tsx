import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import { defaultRuntime } from '../../apps/desktop/src/Workbench';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import type { Attempt, Draft, Task } from '../../apps/desktop/src/types';

// 只替换现有传输；真实 App 决定项目、草稿和历史的选择与保存。
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));

const projects = [{ id: 'project-a', name: '甲项目', revision: 1 }, { id: 'project-b', name: '乙项目', revision: 1 }];
const response = (value: unknown, ok = true): Response => ({ ok, json: async () => structuredClone(value) }) as Response;
let tasks: Map<string, Task>;
let history: Map<string, Attempt>;
let writes: { method: string; path: string; body: unknown }[];
let uiContext: { project_id: string | null; projects: Record<string, { page: string; kind: string; module_tab: string; data_tab: string; task_id: string | null; workflow_id: string | null }> };

function taskId(project: string, kind: 'text' | 'image') { return `task-${project}-${kind}`; }
function fixtureTask(project: typeof projects[number], kind: 'text' | 'image'): Task {
  const id = taskId(project.id, kind);
  const name = `${project.name}${kind === 'text' ? '文字' : '图片'}草稿`;
  const draft: Draft = {
    kind, operation: 'generate', model_id: `model-${project.id}-${kind}`, dataset_id: null,
    input: { prompt: `${name}已存输入`, ...(kind === 'image' ? { negative_prompt: '保留原负向输入' } : {}) },
    runtime: kind === 'text' ? { ...defaultRuntime, max_tokens: 64, seed: 17 } : { ...defaultMediaRuntime('image', false), seed: 29 },
  };
  const attempt: Attempt = {
    id: `attempt-${id}`, task_id: id, project_id: project.id, state: 'succeeded', state_version: 4,
    snapshot: { ...structuredClone(draft), task_id: id, project_id: project.id },
    effective_config: structuredClone(draft.runtime), last_event_sequence: 0, allowed_actions: [], artifacts: [],
    output_text: kind === 'text' ? `${name}原历史输出` : '',
  };
  history.set(attempt.id, attempt);
  return { id, project_id: project.id, name, kind, operation: 'generate', draft_revision: 7, draft, latest_attempt: attempt, attempts: [attempt], created_at: '2026-09-13T01:00:00Z' };
}

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  tasks = new Map(); history = new Map(); writes = []; uiContext = { project_id: null, projects: {} };
  for (const project of projects) for (const kind of ['text', 'image'] as const) {
    const task = fixtureTask(project, kind); tasks.set(task.id, task);
  }
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(String(input), 'http://fixture');
    const path = url.pathname.replace('/api/v1', ''); const method = options.method || 'GET';
    const body = typeof options.body === 'string' ? JSON.parse(options.body) : undefined;
    if (method !== 'GET') {
      writes.push({ method, path, body });
      if (path === '/ui-context' && method === 'PATCH') {
        if (body.context.task_id && tasks.get(body.context.task_id)?.project_id !== body.project_id) return response({ error: { code: 'PROJECT_MISMATCH', message: '不能保存其他项目的任务上下文' } }, false);
        uiContext = { project_id: body.project_id, projects: { ...uiContext.projects, [body.project_id]: structuredClone(body.context) } };
        return response(uiContext);
      }
      const id = /^\/tasks\/([^/]+)\/draft$/.exec(path)?.[1];
      if (method === 'PATCH' && id && tasks.has(id)) {
        const task = tasks.get(id)!;
        if (body.expected_revision !== task.draft_revision) return response({ error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突' } }, false);
        const saved = { ...task, draft: structuredClone(body.draft), draft_revision: task.draft_revision + 1 };
        tasks.set(id, saved); return response(saved);
      }
      throw new Error(`本测试不允许额外写操作：${method} ${path}`);
    }
    if (path === '/projects') return response({ items: projects });
    if (path === '/ui-context') return response(uiContext);
    if (path.startsWith('/projects/')) return response(projects.find(project => path === `/projects/${project.id}`));
    if (path === '/capabilities') return response({ items: ['text', 'image'].map(kind => ({ kind, operation: 'generate', supported: true, status: 'ready' })) });
    if (path === '/devices') return response({ items: [{ id: 'apple-gpu', name: '本机 Apple GPU', status: 'ready' }] });
    const projectId = url.searchParams.get('project_id');
    if (path === '/models') return response({ items: ['text', 'image'].map(kind => ({ id: `model-${projectId}-${kind}`, project_id: projectId, name: `${projectId} ${kind} 模型`, modality: kind, format: 'safetensors', status: 'ready' })) });
    if (path === '/tasks') return response({ items: [...tasks.values()].filter(task => task.project_id === projectId).map(({ draft, attempts, ...summary }) => summary) });
    if (path.startsWith('/tasks/')) return response(tasks.get(path.slice('/tasks/'.length)));
    if (path.endsWith('/events')) return response({ items: [], next_cursor: 0 });
    if (path.startsWith('/attempts/')) return response(history.get(path.slice('/attempts/'.length)));
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear(); });

async function start() {
  const mounted = render(<App />);
  await screen.findByRole('option', { name: '甲项目' });
  await screen.findByRole('button', { name: /^甲项目文字草稿/ });
  return mounted;
}
async function chooseProject(id: string) {
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: id } });
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(id));
}
async function openDraft(project: string, kind: 'text' | 'image') {
  const task = tasks.get(taskId(project, kind))!;
  // 已恢复的草稿无需再次点击历史；首次打开仍走真实任务行。
  await waitFor(() => expect(screen.queryByRole('heading', { name: task.name, exact: true }) || screen.queryByRole('button', { name: new RegExp(`^${task.name}`) })).toBeTruthy());
  if (!screen.queryByRole('heading', { name: task.name, exact: true })) fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${task.name}`) }));
  await expectDraft(task);
}
async function expectDraft(task: Task) {
  await screen.findByRole('heading', { name: task.name, exact: true });
  expect((screen.getByLabelText(task.kind === 'text' ? '输入内容' : '画面描述') as HTMLTextAreaElement).value).toBe(task.draft.input.prompt);
  expect((screen.getByLabelText('随机种子') as HTMLInputElement).value).toBe(String(task.draft.runtime.seed));
  if (task.kind === 'image') expect((screen.getByLabelText('不希望出现的内容') as HTMLTextAreaElement).value).toBe(task.draft.input.negative_prompt);
  else expect((screen.getByLabelText('最大输出 token') as HTMLInputElement).value).toBe('64');
  const original = history.get(task.latest_attempt!.id)!;
  expect(screen.getByText(original.id)).toBeTruthy();
  expect(screen.getByText('提交配方').nextElementSibling?.textContent).toBe(JSON.stringify(original.snapshot, null, 2));
}
async function returnHome() {
  fireEvent.click(screen.getAllByRole('button', { name: '工作台', exact: true }).at(-1)!);
  await screen.findByRole('heading', { name: '模型训练与运行' });
}

it('两个项目返回时各自恢复最近选中的语言或图片草稿，原字段和历史不变', async () => {
  const originalTasks = structuredClone([...tasks.values()]); const originalHistory = structuredClone([...history.values()]);
  await start(); await openDraft('project-a', 'image'); await returnHome(); await openDraft('project-a', 'text');
  await chooseProject('project-b'); await openDraft('project-b', 'text'); await returnHome(); await openDraft('project-b', 'image');
  await chooseProject('project-a');
  await expectDraft(tasks.get(taskId('project-a', 'text'))!);
  await chooseProject('project-b');
  await expectDraft(tasks.get(taskId('project-b', 'image'))!);
  expect([...tasks.values()]).toEqual(originalTasks); expect([...history.values()]).toEqual(originalHistory); expect(writes.every(item => item.method === 'PATCH' && item.path === '/ui-context')).toBe(true);
  for (const item of writes) {
    const body = item.body as { project_id: string; context: { task_id: string | null } };
    if (body.context.task_id) expect(tasks.get(body.context.task_id)?.project_id).toBe(body.project_id);
  }
});

it('卸载并重新挂载后恢复非首项目和选中图片草稿，历史快照不变', async () => {
  const originalHistory = structuredClone([...history.values()]);
  const mounted = await start(); await chooseProject('project-b'); await openDraft('project-b', 'image');
  mounted.unmount(); render(<App />);
  await screen.findByRole('option', { name: '乙项目' });
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b'));
  await expectDraft(tasks.get(taskId('project-b', 'image'))!);
  expect([...history.values()]).toEqual(originalHistory); expect(writes.every(item => item.method === 'PATCH' && item.path === '/ui-context')).toBe(true);
});

it('普通草稿原页编辑后自动保存，未点击保存或导航也能重新打开新输入', async () => {
  const originalHistory = structuredClone([...history.values()]);
  const mounted = await start(); await openDraft('project-a', 'text');
  const prompt = '仅本次编辑的新正文：无需手动保存或离开页面';
  fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: prompt } });
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 1500)); });
  expect.soft(writes.filter(item => item.method === 'PATCH' && item.path === `/tasks/${taskId('project-a', 'text')}/draft`)).toHaveLength(1);
  expect.soft(tasks.get(taskId('project-a', 'text'))!.draft.input.prompt).toBe(prompt);
  mounted.unmount(); render(<App />);
  await screen.findByRole('option', { name: '甲项目' });
  // 手动打开同一任务，单独验证落盘，不让选中上下文缺口掩盖自动保存缺口。
  await openDraft('project-a', 'text');
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe(prompt);
  expect(tasks.get(taskId('project-a', 'text'))!.draft_revision).toBe(8);
  expect([...history.values()]).toEqual(originalHistory);
  expect(writes.every(item => item.method === 'PATCH' && (item.path.endsWith('/draft') || item.path === '/ui-context'))).toBe(true);
});

it.each(['failed', 'running', 'unknown'] as const)('工作流历史 %s 入口读取所选运行，不跳到已变化的当前步骤', async state => {
  const task = tasks.get(taskId('project-a', 'image'))!;
  task.workflow_ref = { workflow_run_id: 'workflow-current-image' };
  const attempt = task.latest_attempt!;
  Object.assign(attempt, { state, recovery_required: state === 'unknown', allowed_actions: state === 'running' ? ['cancel'] : [], error: state === 'failed' ? { code: 'WORKER_FAILED', message: '历史图片执行进程异常退出' } : undefined });
  history.set(attempt.id, attempt);
  const before = structuredClone(task);
  await start();
  fireEvent.click(screen.getByRole('button', { name: /^甲项目图片草稿/ }));
  await screen.findByRole('heading', { name: '工作流运行记录' });
  await screen.findByText(attempt.id);
  expect(screen.getByRole('button', { name: '查看工作流当前步骤' })).toBeTruthy();
  expect(screen.queryByLabelText('画面描述')).toBeNull();
  if (state === 'failed') await screen.findByText('历史图片执行进程异常退出');
  if (state === 'running') expect(screen.getByRole('button', { name: '停止运行' })).toBeTruthy();
  expect(tasks.get(task.id)).toEqual(before);
  expect(writes.every(item => item.path === '/ui-context')).toBe(true);
  await chooseProject('project-b');
  await waitFor(() => expect(screen.queryByRole('heading', { name: '工作流运行记录' })).toBeNull());
  expect(screen.queryByText(attempt.id)).toBeNull();
});
