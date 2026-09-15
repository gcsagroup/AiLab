import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';

const response = (value: unknown) => ({ ok: true, json: async () => value }) as Response;
async function readyButton(name: string) { const button = await screen.findByRole('button', { name }); await waitFor(() => expect(button.matches(':disabled')).toBe(false)); return button; }
const model = (id: string) => ({ id, project_id: 'project-a', name: id, format: 'safetensors', modality: 'text' });
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('刷新第一页等待时不能继续消费旧项目游标', async () => {
  let initialReads = 0; let finish!: (value: Response) => void;
  const requests: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url); requests.push(path);
    if (path === '/api/v1/projects') return response({ items: [{ id: 'project-a', name: '项目A' }] });
    if (path.startsWith('/api/v1/models?')) {
      if (path.includes('cursor=model-100')) return response({ items: [model('model-200')], next_cursor: 'model-200' });
      if (path.includes('cursor=model-200')) return response({ items: [model('model-300')], next_cursor: 'model-300' });
      initialReads += 1;
      if (initialReads > 1) return new Promise(resolve => { finish = resolve; });
      return response({ items: [model('model-100')], next_cursor: 'model-100' });
    }
    return response({ items: [] });
  }));
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  fireEvent.click(await readyButton('加载更多模型')); await screen.findByText('model-200');
  fireEvent.click(screen.getByRole('button', { name: '设备与环境' })); fireEvent.click(await readyButton('刷新执行目标'));
  await waitFor(() => expect(initialReads).toBe(2)); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  const more = screen.queryByRole('button', { name: '加载更多模型' }); if (more) fireEvent.click(more);
  const oldCursorRequests = requests.filter(path => path.includes('cursor=model-200'));
  await act(async () => finish(response({ items: [model('model-100')], next_cursor: 'model-100' })));
  expect(oldCursorRequests).toEqual([]);
});

it.each(['success', 'failure'])('补全旧项目迟到 %s 期间切换首屏外项目，不丢当前选择或连接', async outcome => {
  let finish!: (value: Response) => void; let waiting = false;
  const projects = [{ id: 'project-a', name: '项目A' }, { id: 'project-b', name: '项目B' }, { id: 'project-c', name: '项目C' }];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url);
    if (path === '/api/v1/projects') return response({ items: [projects[0]], next_cursor: 'project-a' });
    if (path === '/api/v1/projects?cursor=project-a') return response({ items: projects.slice(1) });
    if (path === '/api/v1/projects/project-b') { waiting = true; return new Promise(resolve => { finish = resolve; }); }
    if (path === '/api/v1/projects/project-c') return response(projects[2]);
    return response({ items: [] });
  }));
  render(<App />); fireEvent.click(await readyButton('加载更多项目'));
  await screen.findByRole('option', { name: '项目C' });
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  fireEvent.click(screen.getByRole('button', { name: '设备与环境' })); fireEvent.click(await readyButton('刷新执行目标'));
  await waitFor(() => expect(waiting).toBe(true)); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-c' } });
  await act(async () => finish(outcome === 'success' ? response(projects[1]) : { ok: false, json: async () => ({ error: { code: 'RESOURCE_NOT_FOUND', message: '旧项目已不存在' } }) } as Response));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-c');
  expect(screen.getByRole('option', { name: '项目C' })).toBeTruthy();
  expect(screen.queryByText('本机服务尚未连接')).toBeNull();
});

it('项目第一页刷新等待时也不能继续消费旧项目列表游标', async () => {
  let initialReads = 0; let finish!: (value: Response) => void;
  const requests: string[] = [];
  const project = (id: string) => ({ id, name: id });
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url); requests.push(path);
    if (path === '/api/v1/projects?cursor=project-a') return response({ items: [project('project-b')], next_cursor: 'project-b' });
    if (path === '/api/v1/projects?cursor=project-b') return response({ items: [project('project-c')], next_cursor: null });
    if (path === '/api/v1/projects') {
      initialReads += 1;
      if (initialReads > 1) return new Promise(resolve => { finish = resolve; });
      return response({ items: [project('project-a')], next_cursor: 'project-a' });
    }
    return response({ items: [] });
  }));
  render(<App />); fireEvent.click(await readyButton('加载更多项目')); await screen.findByRole('option', { name: 'project-b' });
  fireEvent.click(screen.getByRole('button', { name: '设备与环境' })); fireEvent.click(await readyButton('刷新执行目标'));
  await waitFor(() => expect(initialReads).toBe(2)); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  const more = screen.queryByRole('button', { name: '加载更多项目' }); if (more) fireEvent.click(more);
  const oldCursorRequests = requests.filter(path => path.includes('cursor=project-b'));
  await act(async () => finish(response({ items: [project('project-a')], next_cursor: 'project-a' })));
  expect(oldCursorRequests).toEqual([]);
});

it('未保存的模型选择来自第二页，刷新环境后仍显示原选择', async () => {
  let modelReads = 0;
  const currentTask = { id: 'task-one', project_id: 'project-a', name: '已有模型任务', kind: 'text', operation: 'generate', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: 'model-one', dataset_id: null, input: { prompt: '原提示词' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', max_tokens: 128, temperature: 0, top_p: 1, seed: 0 } } };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url);
    if (path === '/api/v1/projects') return response({ items: [{ id: 'project-a', name: '项目A' }] });
    if (path.startsWith('/api/v1/models?')) {
      if (path.includes('cursor=model-one')) return response({ items: [model('model-two')], next_cursor: null });
      modelReads += 1; return response({ items: [model('model-one')], next_cursor: 'model-one' });
    }
    if (path === '/api/v1/models/model-two') return response(model('model-two'));
    if (path.startsWith('/api/v1/tasks?')) return response({ items: [currentTask] });
    if (path === '/api/v1/tasks/task-one') return response(currentTask);
    return response({ items: [] });
  }));
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /已有模型任务/ }));
  const selector = await screen.findByLabelText('选择基座模型');
  fireEvent.click(screen.getByRole('button', { name: '加载更多模型' })); await screen.findByRole('option', { name: 'model-two' });
  fireEvent.change(selector, { target: { value: 'model-two' } });
  expect((selector as HTMLSelectElement).value).toBe('model-two');
  fireEvent.click(screen.getByRole('button', { name: '设备与环境' })); fireEvent.click(await readyButton('刷新环境'));
  await readyButton('刷新环境'); expect(modelReads).toBe(1); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  await waitFor(() => expect((screen.getByLabelText('选择基座模型') as HTMLSelectElement).value).toBe('model-two'));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('原提示词');
});
