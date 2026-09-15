import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import Workbench, { defaultRuntime } from '../../apps/desktop/src/Workbench';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import type { Draft, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
// 外部草稿回调由组件边界触发，实际保存和表单仍走 Workbench。
vi.mock('../../apps/desktop/src/AIAssistance', () => ({ AIAssistance: ({ onTaskChanged }: { onTaskChanged: (task: Task) => void }) => <button onClick={() => onTaskChanged(externalTask)}>接纳外部已存草稿</button> }));

type Write = { method: string; path: string; body: { draft: Draft; expected_revision: number; draft_revision?: number } };
const response = (value: unknown, ok = true): Response => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (error: Error) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
let task: Task;
let externalTask: Task;
let writes: Write[];
let patchReply: ((call: Write) => Promise<Response>) | undefined;
let preflightReply: Promise<Response> | undefined;
let leave: (() => Promise<boolean>) | null;
let epoch: number;
const changed = vi.fn(); const backed = vi.fn();

beforeEach(() => {
  vi.useFakeTimers(); writes = []; leave = null; epoch = 0; patchReply = undefined; preflightReply = undefined; changed.mockClear(); backed.mockClear();
  task = { id: 'autosave-task', project_id: 'project-a', name: '自动保存试用', kind: 'text', operation: 'generate', draft_revision: 7, draft: { kind: 'text', operation: 'generate', model_id: null, dataset_id: null, input: { prompt: '原输入' }, runtime: { ...defaultRuntime } } };
  externalTask = { ...task, draft_revision: 10, draft: { ...task.draft, input: { prompt: '外部已保存输入' }, runtime: { ...task.draft.runtime, seed: 39 } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = String(input).replace('/api/v1', ''); const method = options.method || 'GET';
    if (method === 'GET') return response({ items: [] });
    const call: Write = { method, path, body: JSON.parse(String(options.body)) }; writes.push(call);
    if (path.endsWith('/draft') && method === 'PATCH') {
      if (patchReply) return patchReply(call);
      if (call.body.expected_revision !== task.draft_revision) return response({ error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突' } }, false);
      task = { ...task, draft: call.body.draft, draft_revision: task.draft_revision + 1 }; return response(task);
    }
    if (path.endsWith('/preflight')) return preflightReply || response({ preflight_id: 'checked-latest', can_submit: true, blocking: [], warnings: [], draft_revision: call.body.draft_revision });
    throw new Error(`未授权的测试写操作：${method} ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const capture = () => { const captured = epoch; return () => epoch === captured; };
function mount(panel?: HTMLElement) {
  return render(<LibraryReadContext.Provider value={capture}><Workbench task={task} models={[]} datasets={[]} devices={[]} aiPanelTarget={panel} onBack={backed} registerLeave={handler => { leave = handler; }} onTaskChanged={changed} onImport={() => {}} onUpdated={() => {}} /></LibraryReadContext.Provider>);
}
function edit(text: string) { fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: text } }); }
const tick = (time: number) => act(async () => { await vi.advanceTimersByTimeAsync(time); });
const patches = () => writes.filter(call => call.method === 'PATCH');

it('停顿500毫秒只保存最后输入；原页重挂载能读回，且没有预检或运行', async () => {
  const rendered = mount(); edit('第一段'); await tick(300); edit('最后一段'); await tick(499);
  expect(patches()).toHaveLength(0); await tick(1);
  expect(patches()).toHaveLength(1); expect(task.draft.input.prompt).toBe('最后一段'); expect(task.draft_revision).toBe(8);
  expect(writes.every(call => call.method === 'PATCH' && call.path.endsWith('/draft'))).toBe(true);
  expect(screen.getByRole('button', { name: '草稿已保存' }).matches(':disabled')).toBe(true);
  rendered.unmount(); mount(); await tick(0); expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('最后一段');
});

it('保存期间输入不中断，迟到回执保留新正文，下一稿使用新revision且仍等输入停顿', async () => {
  const first = deferred<Response>(); patchReply = () => first.promise; mount(); edit('第一稿'); await tick(500);
  expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false); expect(screen.getByText('正在自动保存草稿…')).toBeTruthy();
  edit('第二稿'); await tick(100);
  const firstSaved = { ...task, draft_revision: 8, draft: structuredClone(patches()[0].body.draft) }; task = firstSaved; patchReply = undefined;
  await act(async () => first.resolve(response(firstSaved)));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('第二稿'); expect(screen.getByRole('button', { name: '保存草稿' })).toBeTruthy();
  expect(changed).toHaveBeenLastCalledWith(firstSaved); await tick(399); expect(patches()).toHaveLength(1); await tick(1);
  expect(patches()).toHaveLength(2); expect(patches()[1].body.expected_revision).toBe(8); expect(task.draft.input.prompt).toBe('第二稿');
});

it.each(['检查', '手动保存', '离开'])('自动保存进行中%s共用在途请求，flush保存最新稿后才继续', async action => {
  const first = deferred<Response>(); patchReply = () => first.promise; mount(); edit('在途稿'); await tick(500); edit('最后稿');
  let leaving: Promise<boolean> | undefined;
  if (action === '离开') await act(async () => { leaving = leave!(); });
  else fireEvent.click(screen.getByRole('button', { name: action === '检查' ? '检查配置' : '保存草稿' }));
  expect(patches()).toHaveLength(1);
  task = { ...task, draft_revision: 8, draft: structuredClone(patches()[0].body.draft) }; patchReply = undefined;
  await act(async () => first.resolve(response(task)));
  expect(patches()).toHaveLength(2); expect(patches().map(call => call.body.expected_revision)).toEqual([7, 8]); expect(task.draft.input.prompt).toBe('最后稿');
  if (leaving) expect(await leaving).toBe(true);
  if (action === '检查') expect(writes.at(-1)).toMatchObject({ path: '/tasks/autosave-task/preflight', body: { draft_revision: 9 } });
  await tick(1000); expect(patches()).toHaveLength(2); expect(writes.some(call => call.path.endsWith('/attempts'))).toBe(false);
});

it('旧自动保存排队期间又输入新稿，旧等待者不能跳过新稿的500毫秒停顿', async () => {
  const first = deferred<Response>(); patchReply = () => first.promise; mount(); edit('在途稿'); await tick(500);
  edit('已排队稿'); await tick(500); edit('刚输入的新稿'); await tick(100);
  task = { ...task, draft_revision: 8, draft: patches()[0].body.draft }; patchReply = undefined;
  await act(async () => first.resolve(response(task)));
  expect(patches()).toHaveLength(1); await tick(399); expect(patches()).toHaveLength(1); await tick(1);
  expect(patches()).toHaveLength(2); expect(task.draft.input.prompt).toBe('刚输入的新稿'); expect(patches()[1].body.expected_revision).toBe(8);
});

it('自动保存失败保留输入并停止自动重试，手动保存恢复后可继续自动保存', async () => {
  patchReply = async () => { throw new Error('连接中断'); }; mount(); edit('保留失败输入'); await tick(500);
  expect(screen.getByText(/草稿自动保存失败：连接中断/)).toBeTruthy(); expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('保留失败输入');
  await tick(5000); edit('失败后继续写'); await tick(2000); expect(patches()).toHaveLength(1);
  patchReply = undefined; fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await tick(0);
  expect(task.draft.input.prompt).toBe('失败后继续写'); expect(patches()[1].body.expected_revision).toBe(7);
  expect(screen.queryByText(/连接中断/)).toBeNull(); edit('恢复自动保存'); await tick(500); expect(task.draft.input.prompt).toBe('恢复自动保存'); expect(patches()).toHaveLength(3);
});

it('等待自动保存的检查遇到冲突时，不继续预检且输入仍可重试', async () => {
  const pending = deferred<Response>(); patchReply = () => pending.promise; mount(); edit('冲突稿'); await tick(500);
  fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  await act(async () => pending.resolve(response({ error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突' } }, false)));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('冲突稿'); expect(screen.getByRole('button', { name: '保存草稿' }).matches(':disabled')).toBe(false);
  expect(writes.some(call => call.path.endsWith('/preflight'))).toBe(false); await tick(2000); expect(patches()).toHaveLength(1);
});

it.each(['切库', '卸载'])('%s会撤销尚未开始的自动保存', async action => {
  const rendered = mount(); edit('旧页面未发出的稿'); if (action === '切库') epoch += 1; else rendered.unmount();
  await tick(1000); expect(patches()).toHaveLength(0); expect(changed).not.toHaveBeenCalled();
});

it.each(['切库', '卸载'])('%s发生于保存中，晚回执不回填、不继续下一稿或检查', async action => {
  const pending = deferred<Response>(); patchReply = () => pending.promise; const rendered = mount(); edit('在途旧稿'); await tick(500); edit('排队旧稿');
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); if (action === '切库') epoch += 1; else rendered.unmount();
  await act(async () => pending.resolve(response({ ...task, draft_revision: 8, draft: patches()[0].body.draft })));
  await tick(1000); expect(patches()).toHaveLength(1); expect(changed).not.toHaveBeenCalled(); expect(writes.some(call => call.path.endsWith('/preflight'))).toBe(false);
  if (action === '切库') expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('排队旧稿');
});

it('旧flight资格失效后，新代次的保存等待者不能用未确认revision续发', async () => {
  const pending = deferred<Response>(); patchReply = () => pending.promise; mount(); edit('旧代次在途稿'); await tick(500);
  epoch += 1; edit('原页面保留的新输入'); fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await act(async () => pending.resolve(response({ ...task, draft_revision: 8, draft: patches()[0].body.draft })));
  expect(patches()).toHaveLength(1); expect(changed).not.toHaveBeenCalled(); expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('原页面保留的新输入');
  expect(screen.getByText(/草稿保存状态已变化/)).toBeTruthy(); await tick(2000); expect(patches()).toHaveLength(1);
});

it('外部已存草稿同步自动保存基线，较旧回调和未保存输入均不能被覆盖', async () => {
  const panel = document.createElement('div'); document.body.append(panel); const rendered = mount(panel);
  fireEvent.click(screen.getByRole('button', { name: '接纳外部已存草稿' })); task = structuredClone(externalTask);
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('外部已保存输入'); await tick(1000); expect(patches()).toHaveLength(0);
  externalTask = { ...externalTask, draft_revision: 8, draft: { ...externalTask.draft, input: { prompt: '迟到旧草稿' } } };
  fireEvent.click(screen.getByRole('button', { name: '接纳外部已存草稿' })); expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('外部已保存输入');
  edit('外部基线上继续写'); externalTask = { ...externalTask, draft_revision: 12 }; fireEvent.click(screen.getByRole('button', { name: '接纳外部已存草稿' }));
  expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('外部基线上继续写'); await tick(500);
  expect(patches()[0].body.expected_revision).toBe(10); expect(task.draft.input.prompt).toBe('外部基线上继续写'); rendered.unmount(); panel.remove();
});

it('真正预检尚未结束时仍拒绝离开，不把预检当作普通草稿保存', async () => {
  const pending = deferred<Response>(); preflightReply = pending.promise; mount(); fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await tick(0);
  await act(async () => { expect(await leave!()).toBe(false); }); expect(screen.getByText('当前操作尚未完成，请稍后再离开。')).toBeTruthy();
  await act(async () => pending.resolve(response({ preflight_id: 'checked', can_submit: true, blocking: [], warnings: [] })));
});
