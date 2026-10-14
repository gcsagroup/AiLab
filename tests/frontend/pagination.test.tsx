import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import Workbench, { defaultRuntime } from '../../apps/desktop/src/Workbench';
import type { Attempt, Task } from '../../apps/desktop/src/types';
import { defaultProjectView, type LibraryViews, type ProjectView } from '../../apps/desktop/src/ProjectContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
let reads: string[]; let writes: string[]; let delayed: ((value: Response) => void) | null;
let contexts: LibraryViews;
const response = (value: unknown): Response => ({ ok: true, json: async () => structuredClone(value) }) as Response;
const projects = [{ id: 'p1', name: '分页项目', revision: 1 }, { id: 'p2', name: '另一个项目', revision: 1 }];
const firstModel = { id: 'm1', name: '第一页模型', project_id: 'p1', format: 'safetensors', modality: 'text' };
const chosenModel = { ...firstModel, id: 'm2', name: '原任务后页模型' };
const chosenData = { id: 'd2', project_id: 'p1', name: '原任务后页数据', sample_count: 2, schema: 'sft' };
const task: Task = { id: 't1', project_id: 'p1', name: '原任务', draft_revision: 4, kind: 'text', operation: 'train', draft: { kind: 'text', operation: 'train', model_id: 'm2', dataset_id: 'd2', input: { prompt: '' }, runtime: { ...defaultRuntime, steps: 6 } } };
beforeEach(() => {
  reads = []; writes = []; delayed = null;
  // 两个项目各有自己的页面；切换后仍在模型库验证迟到的旧游标。
  contexts = { project_id: 'p1', projects: { p1: defaultProjectView(), p2: { ...defaultProjectView(), page: 'models' } } };
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit) => {
    const url = String(input).replace('/api/v1', ''); const method = options.method || 'GET';
    if (url === '/ui-context') {
      if (method === 'GET') { reads.push(url); return response(contexts); }
      expect(method).toBe('PATCH');
      const body = JSON.parse(String(options.body)) as { project_id: string; context: ProjectView };
      expect(Object.keys(body).sort()).toEqual(['context', 'project_id']);
      expect(Object.keys(body.context).sort()).toEqual(Object.keys(defaultProjectView()).sort());
      expect(projects.some(project => project.id === body.project_id)).toBe(true);
      expect(body.context.workflow_id).toBeNull();
      expect(body.context.task_id === null || (body.project_id === 'p1' && body.context.task_id === task.id)).toBe(true);
      contexts = { project_id: body.project_id, projects: { ...contexts.projects, [body.project_id]: body.context } };
      return response(contexts);
    }
    if (method !== 'GET') { writes.push(url); throw new Error('本验证不得写草稿或执行'); }
    reads.push(url);
    if (url === '/projects') return response({ items: projects });
    if (url === '/models?project_id=p1') return response({ items: [firstModel], next_cursor: 'models-first' });
    if (url === '/models?project_id=p1&cursor=models-first') return response({ items: [firstModel, chosenModel], next_cursor: null });
    if (url === '/datasets?project_id=p1') return response({ items: [], next_cursor: 'data-first' });
    if (url === '/tasks?project_id=p1') { const { draft, ...summary } = task; return response({ items: [summary] }); }
    if (url === '/tasks/t1') return response(task);
    if (url === '/models/m2') return response(chosenModel);
    if (url === '/datasets/d2') return response(chosenData);
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it.each(['evaluate', 'quantize'] as const)('实验室 %s 尚在后页时说明未加载，加载后显示真实记录', async operation => {
  const normal = vi.mocked(fetch).getMockImplementation()!;
  const older = { ...task, id: 'older-task', name: '后页实验记录', operation };
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    const url = String(input);
    if (url === '/api/v1/tasks?project_id=p1') return response({ items: [task], next_cursor: 'older-tasks' });
    if (url === '/api/v1/tasks?project_id=p1&cursor=older-tasks') { reads.push(url); return response({ items: [older], next_cursor: null }); }
    return normal(input, options);
  });
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型实验室' }));
  await screen.findAllByRole('heading', { name: '已加载记录中暂无此类任务' });
  expect(screen.queryByRole('heading', { name: '还没有任务记录' })).toBeNull();
  expect(reads.some(path => path.includes('cursor=older-tasks'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '加载更多任务' }));
  await screen.findByRole('button', { name: /^后页实验记录/ });
  expect(screen.queryByRole('heading', { name: '已加载记录中暂无此类任务' })).toBeNull();
  expect(screen.getAllByRole('heading', { name: '还没有任务记录' })).toHaveLength(1);
  expect(writes).toEqual([]);
});

it('分类历史先显示尚有未加载记录，末页仍无同类任务才显示空态', async () => {
  const normal = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    const url = String(input);
    if (url === '/api/v1/tasks?project_id=p1') return response({ items: [task], next_cursor: 'older-tasks' });
    if (url === '/api/v1/tasks?project_id=p1&cursor=older-tasks') return response({ items: [], next_cursor: null });
    return normal(input, options);
  });
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /图片训练/ }));
  fireEvent.click(screen.getByRole('tab', { name: '任务与结果' }));
  await screen.findByRole('heading', { name: '已加载记录中暂无此类任务' });
  expect(screen.queryByRole('heading', { name: '还没有任务记录' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '加载更多任务' }));
  await screen.findByRole('heading', { name: '还没有任务记录' });
  expect(screen.queryByRole('heading', { name: '已加载记录中暂无此类任务' })).toBeNull();
  expect(writes).toEqual([]);
});

it('首屏不追随更多页；明确加载后按ID合并并隐藏已结束的入口', async () => {
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  await screen.findByText('第一页模型'); expect(screen.queryByText('原任务后页模型')).toBeNull();
  expect(reads.some(path => path.includes('cursor='))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '加载更多模型' })); await screen.findByText('原任务后页模型');
  expect(screen.getAllByRole('heading', { name: '第一页模型' })).toHaveLength(1);
  expect(screen.queryByRole('button', { name: '加载更多模型' })).toBeNull(); expect(writes).toEqual([]);
});
it('打开摘要任务按ID补回后页引用，不取其余页，也不改原选择', async () => {
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /^原任务/ }));
  await waitFor(() => expect((screen.getByLabelText('选择基座模型') as HTMLSelectElement).value).toBe('m2'));
  await waitFor(() => expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe('d2'));
  expect(reads).toContain('/tasks/t1'); expect(reads).toContain('/models/m2'); expect(reads).toContain('/datasets/d2');
  expect(reads.some(path => path.includes('cursor='))).toBe(false); expect(writes).toEqual([]);
  expect((screen.getByLabelText('训练步数') as HTMLInputElement).value).toBe('6');
});
it('项目切换后丢弃迟到的原项目后页，游标不能混入新项目', async () => {
  const normal = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => String(input).includes('cursor=models-first') ? new Promise(resolve => { delayed = resolve; }) : normal(input, options));
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' })); fireEvent.click(await screen.findByRole('button', { name: '加载更多模型' }));
  await waitFor(() => expect(delayed).toBeTruthy()); fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'p2' } });
  await screen.findByRole('heading', { name: '导入第一个模型' });
  await act(async () => delayed!(response({ items: [chosenModel], next_cursor: 'bad-next' })));
  expect(screen.queryByText('原任务后页模型')).toBeNull(); expect(screen.queryByRole('button', { name: '加载更多模型' })).toBeNull();
});
it('单任务历史只加载当前页，继续取更早记录时保留正在查看的运行', async () => {
  const attempt: Attempt = { id: 'attempt-new', project_id: 'p1', task_id: 't1', state: 'cancelled', state_version: 2 };
  const older = { ...attempt, id: 'attempt-old' }; const normal = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    if (String(input) === '/api/v1/attempts/attempt-new') return response(attempt);
    if (String(input).includes('task_id=t1&cursor=older')) { reads.push(String(input)); return response({ items: [older], next_cursor: null }); }
    return normal(input, options);
  });
  render(<Workbench task={{ ...task, attempts: [attempt], latest_attempt: attempt, attempts_next_cursor: 'older' }} models={[]} datasets={[]} devices={[]} onBack={vi.fn()} registerLeave={vi.fn()} onTaskChanged={vi.fn()} onImport={vi.fn()} onUpdated={vi.fn()} />);
  expect(reads.some(path => path.includes('cursor='))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '加载更早运行记录' }));
  await screen.findByLabelText('查看运行记录'); expect((screen.getByLabelText('查看运行记录') as HTMLSelectElement).value).toBe(attempt.id);
  expect(screen.getAllByRole('option').some(option => option.getAttribute('value') === older.id)).toBe(true);
  expect(screen.queryByRole('button', { name: '加载更早运行记录' })).toBeNull(); expect(writes).toEqual([]);
});

it('分页等待保留键盘焦点并拒绝重复请求，下一页仍可连续加载', async () => {
  const normal = vi.mocked(fetch).getMockImplementation()!; let calls = 0;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    if (String(input).includes('cursor=models-first')) {
      calls += 1;
      return new Promise(resolve => { delayed = resolve; });
    }
    return normal(input, options);
  });
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  const more = await screen.findByRole('button', { name: '加载更多模型' });
  more.focus(); fireEvent.click(more);
  await waitFor(() => expect(delayed).toBeTruthy());
  expect((more as HTMLButtonElement).disabled).toBe(false); expect(more.getAttribute('aria-disabled')).toBe('true');
  expect(more.getAttribute('aria-busy')).toBe('true'); expect(document.activeElement).toBe(more);
  fireEvent.click(more); expect(calls).toBe(1);
  await act(async () => delayed!(response({ items: [chosenModel], next_cursor: 'models-next' })));
  expect(document.activeElement).toBe(more); expect(more.getAttribute('aria-disabled')).toBe('false');
  expect(more.getAttribute('aria-busy')).toBe('false');
});

it('末页保留完成入口和焦点，并将仍聚焦的入口滚入视口', async () => {
  const normal = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => String(input).includes('cursor=models-first') ? new Promise(resolve => { delayed = resolve; }) : normal(input, options));
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  const more = await screen.findByRole('button', { name: '加载更多模型' });
  const scroll = vi.fn(); more.scrollIntoView = scroll;
  more.focus(); fireEvent.click(more);
  await waitFor(() => expect(delayed).toBeTruthy());
  await act(async () => delayed!(response({ items: [chosenModel], next_cursor: null })));
  const completed = screen.getByRole('button', { name: '已加载全部模型' });
  expect(completed).toBe(more); expect(document.activeElement).toBe(completed);
  expect(completed.getAttribute('aria-disabled')).toBe('true');
  expect(scroll).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
  const count = reads.length; fireEvent.click(completed); expect(reads.length).toBe(count);
});

it('分页等待期间焦点移到别处，完成后不滚动或抢回焦点', async () => {
  const normal = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => String(input).includes('cursor=models-first') ? new Promise(resolve => { delayed = resolve; }) : normal(input, options));
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  const more = await screen.findByRole('button', { name: '加载更多模型' });
  const scroll = vi.fn(); more.scrollIntoView = scroll;
  more.focus(); fireEvent.click(more);
  await waitFor(() => expect(delayed).toBeTruthy());
  const elsewhere = screen.getByRole('button', { name: '工作台' }); elsewhere.focus();
  await act(async () => delayed!(response({ items: [chosenModel], next_cursor: 'next' })));
  expect(document.activeElement).toBe(elsewhere); expect(scroll).not.toHaveBeenCalled();
});
