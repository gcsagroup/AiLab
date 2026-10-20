import { beforeEach, expect, test, vi } from 'vitest';
import type { Task } from '../../apps/desktop/src/types';

beforeEach(() => { localStorage.clear(); vi.resetModules(); });

test('preview opens with a project and requires no network calls', async () => {
  const network = vi.spyOn(globalThis, 'fetch');
  try {
    const { previewApi } = await import('../../apps/desktop/src/previewApi');
    const projects = await previewApi<{ items: { id: string }[] }>('GET', '/projects');
    expect(projects.items).toHaveLength(1);
    expect(await previewApi('GET', '/models?project_id=project-ui-preview')).toEqual({ items: [], next_cursor: null });
    expect(network).not.toHaveBeenCalled();
  } finally { network.mockRestore(); }
});

test('project and draft edits survive a new adapter instance', async () => {
  let { previewApi } = await import('../../apps/desktop/src/previewApi');
  const project = await previewApi<{ id: string }>('POST', '/projects', { name: '测试项目' });
  const task = await previewApi<Task>('POST', '/tasks', { project_id: project.id, name: '测试草稿', kind: 'text', operation: 'generate' });
  task.draft.input.prompt = '重开后保留';
  await previewApi('PATCH', `/tasks/${task.id}/draft`, { expected_revision: 1, draft: task.draft });
  vi.resetModules();
  ({ previewApi } = await import('../../apps/desktop/src/previewApi'));
  const stored = await previewApi<Task>('GET', `/tasks/${task.id}`);
  expect(stored.draft.input.prompt).toBe('重开后保留');
  expect(stored.draft_revision).toBe(2);
  const other = await previewApi<{ items: Task[] }>('GET', '/tasks?project_id=project-ui-preview');
  expect(other.items).toHaveLength(0);
});

test('returned records do not mutate storage and stale saves are rejected', async () => {
  const { previewApi } = await import('../../apps/desktop/src/previewApi');
  const task = await previewApi<Task>('POST', '/tasks', { project_id: 'project-ui-preview', name: '草稿', kind: 'text', operation: 'generate' });
  task.draft.input.prompt = '未保存';
  expect((await previewApi<Task>('GET', `/tasks/${task.id}`)).draft.input.prompt).toBe('');
  await expect(previewApi('PATCH', `/tasks/${task.id}/draft`, { expected_revision: 99, draft: task.draft })).rejects.toMatchObject({ error: { code: 'REVISION_CONFLICT' } });
});

test('all execution capabilities stay disabled and submission is rejected', async () => {
  const { previewApi } = await import('../../apps/desktop/src/previewApi');
  const capabilities = await previewApi<{ items: { supported: boolean }[] }>('GET', '/capabilities');
  expect(capabilities.items).toHaveLength(8);
  expect(capabilities.items.every(item => !item.supported)).toBe(true);
  expect(await previewApi('POST', '/tasks/task-preview/preflight', { draft_revision: 1 })).toMatchObject({ can_submit: false });
  await expect(previewApi('POST', '/tasks/task-preview/attempts', {})).rejects.toMatchObject({ error: { code: 'UI_PREVIEW_ONLY' } });
  await expect(previewApi('POST', '/model-downloads', {})).rejects.toMatchObject({ error: { code: 'UI_PREVIEW_ONLY' } });
});
