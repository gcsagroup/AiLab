import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import type { Task } from '../../apps/desktop/src/types';
import { defaultProjectView } from '../../apps/desktop/src/ProjectContext';

// 本文件验证 App 的作品入口、项目选择和重开；配方字段和差异由专项 Workbench 测试覆盖。
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));
vi.mock('../../apps/desktop/src/Workbench', () => ({
  kindLabels: { text: '语言', image: '图片', video: '视频', audio: '音频' },
  default: ({ task }: { task: Task }) => <section aria-label="打开的作品草稿"><h1>{task.name}</h1><p>{task.id} · {task.project_id} · {task.source_work_id}</p><p>{task.draft.input.prompt}</p></section>,
}));
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
const projects = [{ id: 'project-a', name: '甲项目', revision: 1 }, { id: 'project-b', name: '乙项目', revision: 1 }];
const work = { id: 'work-original', project_id: 'project-a', name: '原图片作品', kind: 'image', attempt_id: 'attempt-original', text: '旧预览' };
const task: Task = { id: 'task-from-work', project_id: 'project-a', name: '原图片作品 · 配方复用', kind: 'image', operation: 'generate', draft_revision: 1,
  source_work_id: work.id, source_attempt_id: work.attempt_id, source_recipe_digest: 'a'.repeat(64),
  draft: { kind: 'image', operation: 'generate', model_id: 'model-original', dataset_id: null, adapter_id: null, execution_target_id: null, input: { prompt: '原图正向输入', negative_prompt: '原图负向输入' }, runtime: { engine: 'diffusers', device_id: 'apple-gpu', seed: 2027, size: 512, steps: 20, cfg: 7.5 } },
};
let saved: any, requests: { method: string; path: string; body: any }[], tasks: Task[];
let resolveReuse: (() => void) | null;
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); requests = []; tasks = []; resolveReuse = null;
  saved = { project_id: 'project-a', projects: { 'project-a': { ...defaultProjectView(), page: 'assets' } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(String(input), 'http://fixture'); const path = url.pathname.replace('/api/v1', ''), method = options.method || 'GET';
    const body = options.body ? JSON.parse(String(options.body)) : undefined; requests.push({ method, path, body });
    if (path === '/ui-context') {
      if (method === 'PATCH') saved = { project_id: body.project_id, projects: { ...saved.projects, [body.project_id]: body.context } };
      return response(saved);
    }
    if (path === '/works/work-original/reuse-task') {
      if (resolveReuse) await new Promise<void>(resolve => { resolveReuse = resolve; });
      tasks = [structuredClone(task)]; return response(task);
    }
    if (method !== 'GET') throw new Error('入口验证不允许额外写入：' + path);
    if (path === '/projects') return response({ items: projects });
    if (path.startsWith('/projects/')) return response(projects.find(item => path.endsWith(item.id)));
    if (path === '/works') return response({ items: url.searchParams.get('project_id') === 'project-a' ? [work] : [] });
    if (path === '/tasks') return response({ items: tasks.filter(item => item.project_id === url.searchParams.get('project_id')) });
    if (path === '/tasks/task-from-work') return response(task);
    if (path === '/capabilities') return response({ items: [{ kind: 'image', operation: 'generate', supported: true }] });
    if (path === '/models') return response({ items: [{ id: 'model-original', project_id: url.searchParams.get('project_id'), name: '原模型', format: 'safetensors', modality: 'image' }] });
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('作品卡直接载入普通草稿并保存正确类别，重开仍选同一草稿且不再次新建', async () => {
  const mounted = render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: '用此配方新建任务' }));
  expect((await screen.findByRole('region', { name: '打开的作品草稿' })).textContent).toContain('task-from-work · project-a · work-original');
  await waitFor(() => expect(saved.projects['project-a']).toMatchObject({ page: 'home', kind: 'image', module_tab: 'generate', task_id: task.id, recent_tasks: { 'image:generate': task.id } }));
  mounted.unmount(); render(<App />);
  expect((await screen.findByRole('region', { name: '打开的作品草稿' })).textContent).toContain('原图正向输入');
  const mutations = requests.filter(item => item.method !== 'GET' && item.path !== '/ui-context');
  expect(mutations).toEqual([{ method: 'POST', path: '/works/work-original/reuse-task', body: { project_id: 'project-a' } }]);
});

it('新建途中切到乙项目，甲的迟到草稿不能抢走当前项目或保存乙的选择', async () => {
  resolveReuse = () => {}; render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: '用此配方新建任务' }));
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b'));
  await act(async () => { resolveReuse!(); });
  expect(screen.queryByRole('region', { name: '打开的作品草稿' })).toBeNull();
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b');
  expect(saved.projects['project-b']?.task_id ?? null).toBeNull();
  expect(requests.filter(item => item.path === '/works/work-original/reuse-task')).toHaveLength(1);
});
