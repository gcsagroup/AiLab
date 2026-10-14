import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';
import { invalidateNativeConnection } from '../../apps/desktop/src/api';
import { defaultProjectView } from '../../apps/desktop/src/ProjectContext';
import { defaultRuntime } from '../../apps/desktop/src/Workbench';
import type { Attempt, Task } from '../../apps/desktop/src/types';

// 保留真实 App 与工作台，只控制宿主连接事件及服务返回；重连不得发出新计算请求。
const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { state: string; connection_id?: string; message?: string } }) => void) }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name === 'host-status') host.listener = listener; return () => {}; }) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
let task: Task, attempt: Attempt | undefined, generation: number;
let reads: string[], writes: string[], pendingTask: Promise<unknown> | undefined;
let contexts: any;
const projects = [{ id: 'project-a', name: '原项目' }, { id: 'project-b', name: '另一个项目' }];
const connectionId = () => `reconnect-${generation}`;
async function emit(state: string) { await act(async () => { host.listener!({ payload: { state, connection_id: state === 'running' ? connectionId() : undefined, message: state === 'running' ? '' : '本地服务已意外退出' } }); }); }

beforeEach(() => {
  invalidateNativeConnection(); generation = 0; reads = []; writes = []; attempt = undefined; pendingTask = undefined;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  task = { id: 'task-active', project_id: 'project-a', name: '当前文本任务', kind: 'text', operation: 'generate', draft_revision: 1,
    draft: { kind: 'text', operation: 'generate', model_id: 'model-a', dataset_id: null, input: { prompt: '已经保存的输入' }, runtime: { ...defaultRuntime, max_tokens: 16 } } };
  contexts = { project_id: 'project-a', projects: { 'project-a': { ...defaultProjectView(), module_tab: 'generate', task_id: task.id } } };
  vi.mocked(invoke).mockReset().mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: connectionId() };
    if (command !== 'api_request') return {};
    const request = (args as any).request; const path = request.path.replace('/api/v1', '');
    if (request.method !== 'GET') {
      writes.push(`${request.method} ${path}`);
      if (path === '/ui-context') {
        contexts = { project_id: request.body.project_id, projects: { ...contexts.projects, [request.body.project_id]: request.body.context } };
        return structuredClone(contexts);
      }
      throw new Error(`重连测试不允许业务写入：${request.method} ${path}`);
    }
    reads.push(path);
    if (path === '/projects') return { items: projects };
    if (path === '/ui-context') return structuredClone(contexts);
    if (path === `/tasks/${task.id}`) return pendingTask ? await pendingTask : structuredClone(task);
    if (path.startsWith('/tasks?')) return { items: [] }; // 当前任务可以不在首个列表页，必须直接读它的详情。
    if (path.startsWith('/models?')) return { items: [{ id: 'model-a', project_id: 'project-a', name: '已导入模型', modality: 'text', format: 'safetensors', status: 'ready' }] };
    if (path === '/capabilities') return { items: [{ kind: 'text', operation: 'generate', supported: true }] };
    if (path === '/devices') return { items: [{ id: 'apple-gpu', name: '本机 Apple GPU', status: 'ready' }] };
    if (attempt && path === `/attempts/${attempt.id}`) return structuredClone(attempt);
    if (path.endsWith('/events')) return { items: [], next_cursor: 0 };
    return { items: [] };
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function startDraft() {
  render(<App />);
  await screen.findByRole('heading', { name: task.name });
  await waitFor(() => expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('已经保存的输入'));
  expect(screen.getByText('尚未开始')).toBeTruthy();
  expect(reads.filter(path => path === `/tasks/${task.id}`)).toHaveLength(1);
}
function returnedAttempt(recoveryRequired: boolean) {
  attempt = { id: 'attempt-before-interruption', task_id: task.id, project_id: task.project_id, state: recoveryRequired ? 'running' : 'failed', state_version: 7,
    snapshot: { ...structuredClone(task.draft), task_id: task.id, project_id: task.project_id }, output_text: '中断前实际输出', artifacts: [], last_event_sequence: 0,
    recovery_required: recoveryRequired, stop_status: recoveryRequired ? 'unknown' : 'confirmed', connection_state: recoveryRequired ? 'disconnected' : 'connected',
    compute_outcome: recoveryRequired ? 'pending' : 'succeeded', collection_state: recoveryRequired ? 'not_started' : 'failed', collection_version: 2,
    allowed_actions: recoveryRequired ? ['reconcile'] : ['collect'] } as Attempt;
  task = { ...task, latest_attempt: attempt, attempts: [attempt] };
  return structuredClone(task);
}
async function disconnect() { await emit('failed'); await screen.findByRole('button', { name: '重新连接' }); generation += 1; }

it.each([true, false])('重连直接读回当前任务的真实执行，停止未知=%s，读取完成前不显示可编辑旧草稿', async recoveryRequired => {
  await startDraft(); await disconnect();
  const next = deferred<unknown>(); pendingTask = next.promise; const fresh = returnedAttempt(recoveryRequired);
  await emit('running');
  await waitFor(() => expect(reads.filter(path => path === `/tasks/${task.id}`)).toHaveLength(2));
  expect(screen.queryByText('尚未开始')).toBeNull(); expect(screen.queryByLabelText('输入内容')).toBeNull();
  await act(async () => next.resolve(fresh));
  await screen.findByText('中断前实际输出');
  expect(screen.queryByText('尚未开始')).toBeNull();
  expect(screen.getByRole('button', { name: recoveryRequired ? '核实原进程' : '只补收已有产物' })).toBeTruthy();
  expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(recoveryRequired);
  expect(writes.every(path => path === 'PATCH /ui-context')).toBe(true);
});

it('重连读取当前任务失败时保持错误和重试入口，不用旧草稿冒充无运行记录', async () => {
  await startDraft(); await disconnect();
  const next = deferred<unknown>(); pendingTask = next.promise; returnedAttempt(true);
  await emit('running'); await waitFor(() => expect(reads.filter(path => path === `/tasks/${task.id}`)).toHaveLength(2));
  await act(async () => next.reject(new Error('当前任务暂时无法读取')));
  await screen.findByText('当前任务暂时无法读取');
  expect(screen.queryByText('尚未开始')).toBeNull(); expect(screen.queryByLabelText('输入内容')).toBeNull();
  pendingTask = undefined;
  fireEvent.click(screen.getByRole('button', { name: '重试加载' }));
  await screen.findByRole('button', { name: '核实原进程' });
  expect(writes.every(path => path === 'PATCH /ui-context')).toBe(true);
});

it('重连详情迟到不能把用户切换后的项目拉回原任务', async () => {
  await startDraft(); await disconnect();
  const next = deferred<unknown>(); pendingTask = next.promise; const fresh = returnedAttempt(true);
  await emit('running'); await waitFor(() => expect(reads.filter(path => path === `/tasks/${task.id}`)).toHaveLength(2));
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await screen.findByRole('heading', { name: '模型训练与运行' });
  await act(async () => next.resolve(fresh));
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b');
  expect(screen.queryByRole('heading', { name: task.name })).toBeNull(); expect(screen.queryByText('中断前实际输出')).toBeNull();
  expect(writes.every(path => path === 'PATCH /ui-context')).toBe(true);
});
