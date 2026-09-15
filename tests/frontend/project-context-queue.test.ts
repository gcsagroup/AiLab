import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ProjectContexts, defaultProjectView } from '../../apps/desktop/src/ProjectContext';

const response = (value: unknown, ok = true) => ({ ok, json: async () => value }) as Response;
const deferred = () => { let resolve!: (value: Response) => void; const promise = new Promise<Response>(done => { resolve = done; }); return { promise, resolve }; };
let writes: { project_id: string; context: ReturnType<typeof defaultProjectView> }[];
beforeEach(() => { writes = []; vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => { writes.push(JSON.parse(String(init.body))); return response({}); })); });
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const open = (canWrite = () => true) => { const contexts = new ProjectContexts(canWrite); contexts.load({ project_id: null, projects: {} }); return contexts; };

it('读取已有选择不产生写入；另一库实例不继承旧库的同编号任务', async () => {
  const first = open(); const view = { ...defaultProjectView(), task_id: 'task-a' };
  first.load({ project_id: 'project-a', projects: { 'project-a': view } });
  await first.remember('project-a', view);
  const second = open();
  expect(second.view('project-a').task_id).toBeNull(); expect(second.value.project_id).toBeNull(); expect(writes).toEqual([]);
});

it('快速 A→B→A 等待同一保存队列，每个项目保留最后选择，最终选择仍为 A', async () => {
  const gate = deferred();
  vi.mocked(fetch).mockImplementationOnce(async (_url, init) => { writes.push(JSON.parse(String(init?.body))); return gate.promise; });
  const contexts = open();
  const first = contexts.remember('project-a', { ...defaultProjectView(), task_id: 'task-old' });
  const second = contexts.remember('project-b', { ...defaultProjectView(), task_id: 'task-b' });
  const last = contexts.remember('project-a', { ...defaultProjectView(), task_id: 'task-new' });
  expect(writes.map(item => item.context.task_id)).toEqual(['task-old']);
  gate.resolve(response({})); await Promise.all([first, second, last]); await contexts.flush();
  expect(writes.map(item => [item.project_id, item.context.task_id])).toEqual([['project-a', 'task-old'], ['project-b', 'task-b'], ['project-a', 'task-new']]);
  expect(contexts.value.project_id).toBe('project-a'); expect(contexts.view('project-b').task_id).toBe('task-b');
});

it('写入失败保留待存选择；显式重试成功前 flush 不能假报已保存', async () => {
  const contexts = open();
  vi.mocked(fetch).mockResolvedValueOnce(response({ error: { code: 'CLEANUP_BUSY', message: '正在备份' } }, false));
  await expect(contexts.remember('project-a', { ...defaultProjectView(), page: 'assets' })).rejects.toMatchObject({ error: { code: 'CLEANUP_BUSY' } });
  expect(contexts.view('project-a').page).toBe('assets');
  await contexts.flush(); expect(writes).toHaveLength(1); expect(writes[0].context.page).toBe('assets');
});

it('工作库失效后不向新连接补发排队的旧项目选择', async () => {
  const gate = deferred(); let current = true;
  vi.mocked(fetch).mockImplementationOnce(async (_url, init) => { writes.push(JSON.parse(String(init?.body))); return gate.promise; });
  const contexts = open(() => current);
  const first = contexts.remember('project-a', defaultProjectView());
  const next = contexts.remember('project-b', { ...defaultProjectView(), task_id: 'task-b' });
  current = false; gate.resolve(response({}));
  const results = await Promise.allSettled([first, next]);
  expect(results.every(item => item.status === 'rejected')).toBe(true);
  expect(writes.map(item => item.project_id)).toEqual(['project-a']);
});

it('已完成回执和清理之间的新选择也须落盘，不能仅更新内存后返回成功', async () => {
  const contexts = open();
  // JSON 读取会多出微任务，循环覆盖快速响应的各个交界。
  for (let gap = 0; gap < 8; gap += 1) {
    const first = contexts.remember(`project-${gap}-a`, defaultProjectView());
    for (let tick = 0; tick < gap; tick += 1) await Promise.resolve();
    const second = contexts.remember(`project-${gap}-b`, { ...defaultProjectView(), page: 'assets' });
    await Promise.all([first, second]);
    expect(writes.at(-1)?.project_id).toBe(`project-${gap}-b`);
  }
});
