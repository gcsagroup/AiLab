import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Workbench, { defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import type { Attempt, Draft, Task } from '../../apps/desktop/src/types';
import contracts from './fixtures/training-contracts.json';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));

type Call = { method: string; path: string; body?: { draft: Draft; expected_revision: number } };
const response = (value: unknown, ok = true): Response => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
const entryNames = ['导入模型', '导入数据', '新建评测方案'];
const imported = vi.fn(), createdPlan = vi.fn(), backed = vi.fn(), changed = vi.fn();
let task: Task, calls: Call[], patchReply: Promise<Response> | undefined, preflightReply: Promise<Response> | undefined;
let user: ReturnType<typeof userEvent.setup>;

beforeEach(() => {
  user = userEvent.setup(); calls = []; patchReply = undefined; preflightReply = undefined;
  imported.mockClear(); createdPlan.mockClear(); backed.mockClear(); changed.mockClear();
  task = { id: 'keyboard-training-task', project_id: 'keyboard-project', name: '训练入口键盘回归', kind: 'text', operation: 'train', draft_revision: 7,
    draft: { kind: 'text', operation: 'train', model_id: null, dataset_id: null, input: { prompt: '' }, runtime: { ...defaultTrainingRuntime } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = String(input).replace('/api/v1', ''); const method = options.method || 'GET';
    const body = options.body ? JSON.parse(String(options.body)) : undefined;
    calls.push({ method, path, body });
    if (method === 'GET' && path === '/training-contracts') return response(contracts);
    if (method === 'GET' && (path.startsWith('/execution-targets?') || path.startsWith('/checkpoints?') || path.endsWith('/events?after=0'))) return response({ items: [] });
    if (method === 'GET' && path === '/attempts/current-running') return response(task.latest_attempt);
    if (method === 'PATCH' && path === `/tasks/${task.id}/draft`) {
      if (patchReply) return patchReply;
      throw new Error('本测试必须明确控制草稿保存回执');
    }
    if (method === 'POST' && path === `/tasks/${task.id}/preflight` && preflightReply) return preflightReply;
    throw new Error(`本专项未授权请求：${method} ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function mount(withPlan = true) {
  await act(async () => {
    render(<Workbench task={task} models={[]} datasets={[]} devices={[]}
      onBack={backed} registerLeave={() => {}} onTaskChanged={changed} onImport={imported}
      onCreateEvaluationPlan={withPlan ? createdPlan : undefined} onUpdated={() => {}} />);
  });
}
const writes = () => calls.filter(call => call.method !== 'GET');
const back = () => screen.getByRole('button', { name: '工作台' });
const steps = () => screen.getByRole('spinbutton', { name: '训练步数' }) as HTMLInputElement;
const finishPreflight = () => response({ preflight_id: 'keyboard-preflight', can_submit: false, blocking: [], warnings: [] });
function editSteps() { fireEvent.change(steps(), { target: { value: '7' } }); }

it('真实训练页面四个原始按钮有显式 Tab 声明，挂载不抢焦点且不改变按钮类型', async () => {
  await mount();
  for (const name of ['工作台', ...entryNames]) expect.soft(screen.getByRole('button', { name }).getAttribute('tabindex'), name).toBe('0');
  for (const name of entryNames) expect(screen.getByRole('button', { name }).getAttribute('type')).toBe('button');
  expect(back().getAttribute('type')).toBeNull();
  expect(document.activeElement).toBe(document.body); expect(writes()).toEqual([]);
});

it('三个启用入口只触发各自回调，缺少评测回调时不渲染该入口', async () => {
  await mount();
  for (const name of entryNames) await user.click(screen.getByRole('button', { name }));
  expect(imported.mock.calls).toEqual([['model'], ['dataset']]); expect(createdPlan).toHaveBeenCalledOnce();
  expect(writes()).toEqual([]); expect(backed).not.toHaveBeenCalled();
  cleanup(); await mount(false); expect(screen.queryByRole('button', { name: '新建评测方案' })).toBeNull();
});

it.each(['busy', 'running', 'checkpoint'])('%s 时三个配置按钮仍继承 fieldset 禁用，普通交互不能触发回调', async state => {
  const pending = deferred<Response>();
  if (state === 'running') task = { ...task, latest_attempt: { id: 'current-running', project_id: task.project_id, task_id: task.id,
    state: 'running', state_version: 2, snapshot: { kind: 'text', operation: 'train' }, artifacts: [], allowed_actions: [] } as Attempt };
  if (state === 'checkpoint') task = { ...task, draft: { ...task.draft, checkpoint_id: 'fixed-checkpoint' } };
  await mount();
  if (state === 'busy') {
    preflightReply = pending.promise;
    await user.click(screen.getByRole('button', { name: '检查配置' }));
    await waitFor(() => expect(writes().map(call => call.path)).toEqual([`/tasks/${task.id}/preflight`]));
  }
  const before = writes().length;
  for (const name of entryNames) {
    const button = screen.getByRole('button', { name });
    expect(button.closest('fieldset')?.disabled).toBe(true);
    expect(button.matches(':disabled')).toBe(true);
    // user-event 遵守 fieldset 的禁用约束；fireEvent 单独派发 click 不能代表正常用户交互。
    await user.click(button);
  }
  expect(imported).not.toHaveBeenCalled(); expect(createdPlan).not.toHaveBeenCalled(); expect(writes()).toHaveLength(before);
  // breadcrumb 本来位于 fieldset 外，此次属性修改不能把它一起禁用。
  expect(back().matches(':disabled')).toBe(false);
  if (state === 'busy') {
    await act(async () => pending.resolve(finishPreflight()));
    for (const name of entryNames) expect(screen.getByRole('button', { name }).matches(':disabled')).toBe(false);
  }
});

it.each(['返回入口', '手动保存在途'])('%s 的草稿保存延迟成功，真实返回按钮等待同一次保存后才离页', async entry => {
  const pending = deferred<Response>(); patchReply = pending.promise; await mount(); editSteps();
  if (entry === '手动保存在途') await user.click(screen.getByRole('button', { name: '保存草稿' }));
  await user.click(back());
  expect(writes()).toHaveLength(1); expect(writes()[0]).toMatchObject({ method: 'PATCH', path: `/tasks/${task.id}/draft`, body: { expected_revision: 7 } });
  expect(backed).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled();
  const saved = { ...task, draft_revision: 8, draft: writes()[0].body!.draft };
  await act(async () => pending.resolve(response(saved)));
  await waitFor(() => expect(backed).toHaveBeenCalledOnce());
  expect(changed).toHaveBeenCalledExactlyOnceWith(saved); expect(saved.draft.runtime.steps).toBe(7);
  expect(writes()).toHaveLength(1); expect(writes().some(call => call.path.endsWith('/attempts') || call.path.endsWith('/preflight'))).toBe(false);
});

it('真实返回入口的延迟保存失败保留输入和错误，不离页、不继续检查或运行', async () => {
  const pending = deferred<Response>(); patchReply = pending.promise; await mount(); editSteps(); await user.click(back());
  expect(writes()).toHaveLength(1); expect(backed).not.toHaveBeenCalled();
  await act(async () => pending.resolve(response({ error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突，输入保留' } }, false)));
  expect(await screen.findByText('草稿版本冲突，输入保留')).toBeTruthy(); expect(steps().value).toBe('7');
  expect(backed).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled(); expect(writes()).toHaveLength(1);
});

it('真正预检 busy 时直接返回被原守卫拒绝，不新增禁用属性或保存请求', async () => {
  const pending = deferred<Response>(); preflightReply = pending.promise; await mount();
  await user.click(screen.getByRole('button', { name: '检查配置' }));
  await waitFor(() => expect(writes().map(call => call.path)).toEqual([`/tasks/${task.id}/preflight`]));
  expect(back().hasAttribute('disabled')).toBe(false); await user.click(back());
  expect(backed).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled(); expect(writes()).toHaveLength(1);
  await act(async () => pending.resolve(finishPreflight()));
  await user.click(back()); expect(backed).toHaveBeenCalledOnce(); expect(writes()).toHaveLength(1);
});
