import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import Workbench, { defaultRuntime, defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import type { Attempt, Task } from '../../apps/desktop/src/types';
import contracts from './fixtures/training-contracts.json';
import { model, source } from './fixtures/dataset-split';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
type Call = { method: string; path: string; body: any };
const response = (value: unknown): Response => ({ ok: true, json: async () => structuredClone(value) }) as Response;
let task: Task, current: Attempt, previous: Attempt, calls: Call[], panel: HTMLDivElement;
let leave: (() => Promise<boolean>) | null;
const updated = vi.fn();

beforeEach(() => {
  vi.useFakeTimers(); calls = []; leave = null; updated.mockClear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  panel = document.createElement('div'); document.body.append(panel);
  task = { id: 'readonly-task', project_id: 'project-a', name: '保留当前执行与旧结果', kind: 'text', operation: 'generate', draft_revision: 7,
    draft: { kind: 'text', operation: 'generate', model_id: model.id, dataset_id: null, input: { prompt: '已保存的任务输入' }, runtime: { ...defaultRuntime } } };
  previous = { id: 'attempt-old', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 3,
    snapshot: { kind: 'text', operation: 'generate' }, output_text: '旧运行结果', artifacts: [], allowed_actions: [] };
  current = { id: 'attempt-current', task_id: task.id, project_id: task.project_id, state: 'running', state_version: 4,
    snapshot: { kind: 'text', operation: 'generate' }, allowed_actions: ['cancel'], artifacts: [] };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const call = { method: options.method || 'GET', path: String(input).replace('/api/v1', ''), body: options.body ? JSON.parse(String(options.body)) : {} };
    calls.push(call);
    if (call.path === '/training-contracts') return response(contracts);
    if (call.path.startsWith('/ai/requests?')) return response({ items: [{ id: 'ai-request', target_task_id: task.id, target_revision: 7,
      generation_task_id: 'separate-ai-task', model_id: model.id, status: 'awaiting_generation', proposal_id: 'ai-proposal',
      context: { instruction: '缩短首次输出', sent_scope: '当前草稿', allowed_fields: {} }, connection: { type: 'local_process', engine: 'mlx', model_name: model.name, network: false }, parse_failures: [] }] });
    if (call.path === '/ai/proposals/ai-proposal') return response({ id: 'ai-proposal', target_id: task.id, expected_revision: 7,
      title: '缩短输出建议', changes: [{ field: 'runtime.max_tokens', from: 128, to: 64, reason: '便于检查', impact: '输出较短' }],
      status: 'proposed', source_attempt_id: 'ai-attempt', source_artifact_id: 'ai-artifact', raw_sha256: 'a'.repeat(64), requires_preflight: true, execution_actions: [], application: null });
    if (call.path === `/attempts/${current.id}` && call.method === 'GET') return response(current);
    if (call.path === `/attempts/${previous.id}` && call.method === 'GET') return response(previous);
    if (call.path.endsWith('/events?after=0')) return response({ items: [] });
    if (call.path === `/attempts/${current.id}/reconcile`) {
      current = { ...current, recovery_required: false, stop_status: 'stopped', state_version: current.state_version + 1, allowed_actions: [] };
      return response(current);
    }
    if (call.path === `/tasks/${task.id}/draft` && call.method === 'PATCH') {
      expect(call.body.expected_revision).toBe(task.draft_revision);
      task = { ...task, draft: call.body.draft, draft_revision: task.draft_revision + 1 }; return response(task);
    }
    if (call.path === `/tasks/${task.id}/preflight`) return response({ preflight_id: 'target-check', can_submit: true, blocking: [], warnings: [] });
    if (call.path === `/tasks/${task.id}/market-contexts`) return response({ id: 'market-context', task_id: task.id, draft_revision: task.draft_revision });
    if (call.method !== 'GET') throw new Error(`本专项不应发生写入：${call.method} ${call.path}`);
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); panel.remove(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function content() {
  return <Workbench task={task} models={[model]} datasets={[source]} devices={[]} aiPanelTarget={panel}
    onBack={() => {}} registerLeave={value => { leave = value; }} onTaskChanged={() => {}} onImport={() => {}} onUpdated={updated} />;
}
function training() {
  task = { ...task, operation: 'train', draft: { ...task.draft, operation: 'train', dataset_id: source.id, runtime: { ...defaultTrainingRuntime } } };
  current = { ...current, snapshot: { kind: 'text', operation: 'train' } };
}
function attachCurrent() { task = { ...task, latest_attempt: structuredClone(current), attempts: [structuredClone(current), previous] }; }
const tick = (milliseconds = 0) => act(async () => { await vi.advanceTimersByTimeAsync(milliseconds); });
const writes = () => calls.filter(call => call.method !== 'GET');
const input = () => screen.getByLabelText('输入内容') as HTMLTextAreaElement;

it.each(['运行中', '训练暂停', '停止待核实'])('%s的当前任务配置只读，AI写回和预检禁用，原运行控制保留', async scenario => {
  if (scenario === '训练暂停') { training(); current = { ...current, state: 'paused', allowed_actions: ['resume', 'cancel'] }; }
  if (scenario === '停止待核实') current = { ...current, state: 'failed', recovery_required: true, stop_status: 'unknown', allowed_actions: ['reconcile'] };
  attachCurrent(); render(content()); await tick();
  expect(screen.getByLabelText('选择基座模型').matches(':disabled')).toBe(true);
  expect(screen.getByRole('button', { name: '检查配置' }).matches(':disabled')).toBe(true);
  expect(screen.getByRole('button', { name: '应用这些字段' }).matches(':disabled')).toBe(true);
  fireEvent.change(screen.getByLabelText('随机种子'), { target: { value: '999' } });
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); fireEvent.click(screen.getByRole('button', { name: '应用这些字段' }));
  await tick(1200); expect((screen.getByLabelText('随机种子') as HTMLInputElement).value).toBe('0'); expect(writes()).toEqual([]);
  const control = scenario === '训练暂停' ? '继续训练' : scenario === '停止待核实' ? '核实原进程' : '停止运行';
  expect(screen.getByRole('button', { name: control }).matches(':disabled')).toBe(false);
  await act(async () => { expect(await leave!()).toBe(true); });
  expect(writes()).toEqual([]);
});

it('查看旧成功历史不能解锁，当前原有轮询读到终态后恢复编辑且不切走旧结果', async () => {
  attachCurrent(); render(content()); await tick();
  fireEvent.change(screen.getByLabelText('查看运行记录'), { target: { value: previous.id } }); await tick();
  expect(screen.getByText('旧运行结果')).toBeTruthy(); expect(input().matches(':disabled')).toBe(true);
  expect(screen.getByRole('button', { name: '查看当前执行' }).matches(':disabled')).toBe(false);
  fireEvent.change(input(), { target: { value: '旧历史不能改当前草稿' } }); expect(input().value).toBe('已保存的任务输入');
  expect(writes()).toEqual([]);
  current = { ...current, state: 'succeeded', state_version: 5, allowed_actions: [], output_text: '本次真实结束' };
  await tick(600);
  expect(input().matches(':disabled')).toBe(false); expect(screen.getByText('旧运行结果')).toBeTruthy();
  expect((screen.getByLabelText('查看运行记录') as HTMLSelectElement).value).toBe(previous.id);
  expect(calls.filter(call => call.path === '/attempts/attempt-current')).toHaveLength(2);
  fireEvent.change(input(), { target: { value: '当前执行结束后的新稿' } }); await tick(500);
  expect(writes()).toEqual([{ method: 'PATCH', path: '/tasks/readonly-task/draft', body: { expected_revision: 7, draft: task.draft } }]);
  expect(task.draft.input.prompt).toBe('当前执行结束后的新稿');
});

it('项目刷新带来最新执行时撤销旧检查，终态回执不能被较旧状态版本重新锁住', async () => {
  task = { ...task, latest_attempt: previous, attempts: [previous] }; const rendered = render(content()); await tick();
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await tick(); expect(screen.getByRole('button', { name: '开始运行' })).toBeTruthy();
  attachCurrent(); rendered.rerender(content()); await tick();
  expect(input().matches(':disabled')).toBe(true); expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  expect(writes().map(call => call.path)).toEqual(['/tasks/readonly-task/preflight']);
  const stale = structuredClone(current); current = { ...current, state: 'succeeded', state_version: 8, allowed_actions: [] }; await tick(600);
  task = { ...task, latest_attempt: stale, attempts: [stale, previous] }; rendered.rerender(content()); await tick();
  expect(input().matches(':disabled')).toBe(false); expect(writes().map(call => call.path)).toEqual(['/tasks/readonly-task/preflight']);
});

it('锁定前尚未触发的自动保存不会写入活动任务，也不会把未保存输入当成已保存而离开', async () => {
  const rendered = render(content()); await tick(); fireEvent.change(input(), { target: { value: '运行开始前尚未保存的输入' } }); await tick(250);
  attachCurrent(); rendered.rerender(content()); await tick(1000);
  expect(input().matches(':disabled')).toBe(true); expect(writes()).toEqual([]);
  await act(async () => { expect(await leave!()).toBe(false); }); expect(input().value).toBe('运行开始前尚未保存的输入'); expect(writes()).toEqual([]);
  current = { ...current, state: 'succeeded', state_version: 5, allowed_actions: [] }; await tick(600);
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await tick();
  expect(task.draft.input.prompt).toBe('运行开始前尚未保存的输入'); expect(writes().map(call => call.path)).toEqual(['/tasks/readonly-task/draft']);
});

it('终态但停止待核实不增加持续轮询，明确核实的真实回执解除只读', async () => {
  current = { ...current, state: 'failed', recovery_required: true, stop_status: 'unknown', allowed_actions: ['reconcile'] };
  attachCurrent(); render(content()); await tick(1800);
  expect(input().matches(':disabled')).toBe(true); expect(calls.filter(call => call.path === '/attempts/attempt-current')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: '核实原进程' })); await tick();
  expect(input().matches(':disabled')).toBe(false); expect(writes().map(call => call.path)).toEqual(['/attempts/attempt-current/reconcile']);
  expect(screen.queryByText('当前执行的停止状态待核实，配置暂时只读。请先核实原执行。')).toBeNull();
});

it.each(['市场', '划分'])('任务变为活动状态时关闭已打开的%s草稿入口，不能继续写入', async entry => {
  training(); const rendered = render(content()); await tick();
  fireEvent.click(screen.getByRole('button', { name: entry === '市场' ? '从数据市场选择训练数据' : '划分训练与验证' })); await tick();
  expect(screen.getByRole('dialog')).toBeTruthy(); calls = [];
  current = { ...current, state: 'paused', allowed_actions: ['resume', 'cancel'] }; attachCurrent(); rendered.rerender(content()); await tick();
  expect(screen.queryByRole('dialog')).toBeNull();
  for (const label of ['从数据市场选择训练数据', '划分训练与验证']) {
    const button = screen.getByRole('button', { name: label }); expect(button.matches(':disabled')).toBe(true); fireEvent.click(button);
  }
  await tick(600); expect(writes()).toEqual([]); expect(screen.queryByRole('dialog')).toBeNull();
});
