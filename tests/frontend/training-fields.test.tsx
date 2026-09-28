import React from 'react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Workbench, { defaultRuntime, defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import { trainingParameterErrors } from '../../apps/desktop/src/TrainingFields';
import type { Draft, Task, TrainingContract } from '../../apps/desktop/src/types';
import fixture from './fixtures/training-contracts.json';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
let task: Task, saved: Draft | undefined;
let calls: { path: string; method: string; body: any }[];
let contractResponse: () => Promise<Response>;
const changed = vi.fn();
const updated = vi.fn();
const backed = vi.fn();
let leaveHandler: (() => Promise<boolean>) | null;
beforeEach(() => {
  calls = []; saved = undefined; changed.mockClear(); updated.mockClear(); backed.mockClear(); leaveHandler = null;
  task = { id: 'task-contract', project_id: 'project-contract', name: '训练约束验收', kind: 'text', operation: 'train', draft_revision: 4,
    draft: { kind: 'text', operation: 'train', model_id: null, dataset_id: null, input: {}, runtime: { ...defaultTrainingRuntime, steps: 17, seed: 37 } } };
  contractResponse = async () => response(fixture);
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init?.method || 'GET'; const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body });
    if (path === '/training-contracts') return contractResponse();
    if (path.startsWith('/execution-targets?')) return response({ items: [{ id: 'target-fixture', name: 'NVIDIA 夹具', origin: 'http://127.0.0.1:9', executor_id: 'fixture', nvidia_ready: false }] });
    if (path.endsWith('/draft')) { saved = structuredClone(body.draft); task = { ...task, draft: saved!, draft_revision: task.draft_revision + 1 }; return response(task); }
    if (path.endsWith('/preflight')) return response({ preflight_id: 'preflight-contract', can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime, check_report: { accepted_samples: 64 } });
    if (path.endsWith('/attempts')) return response({ id: 'attempt-contract', state: 'succeeded', state_version: 1, snapshot: { operation: 'train' }, artifacts: [] });
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function view(current = task) { return <Workbench key={current.id} task={current} models={[]} datasets={[]} devices={[]} onBack={backed} registerLeave={handler => { leaveHandler = handler; }} onTaskChanged={changed} onImport={() => {}} onUpdated={updated} />; }
function mount() { return render(view()); }
const input = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const check = () => screen.getByRole('button', { name: '检查配置' });
const ready = () => waitFor(() => expect(check()).not.toBeDisabled());

it('真实静态合同驱动范围和默认说明，读取不改草稿也不探测环境', async () => {
  const wait = deferred<Response>(); contractResponse = () => wait.promise; mount();
  expect(check()).toBeDisabled(); expect(input('训练步数')).toHaveValue(17);
  fireEvent.change(input('训练步数'), { target: { value: '19' } });
  await act(async () => wait.resolve(response(fixture))); await ready();
  expect(input('训练步数')).toHaveValue(19); expect(input('随机种子')).toHaveValue(37);
  expect(input('训练末尾层数')).toHaveAttribute('max', '28');
  expect(input('训练步数')).toHaveAttribute('max', '200'); expect(input('随机种子')).toHaveAttribute('max', '4294967295');
  expect(input('学习率')).toHaveAttribute('min', '1e-7'); expect(input('LoRA Alpha')).toHaveAttribute('step', 'any');
  expect(screen.getByText(/默认值来源：内置 Apple MLX/)).toBeTruthy(); expect(screen.getByText(/每设备批大小 1 × 梯度累积 1 × 数据并行设备 1 = 有效批量 1/)).toBeTruthy();
  expect(changed).not.toHaveBeenCalled(); expect(calls.every(call => call.method === 'GET')).toBe(true);
  expect(calls.some(call => /capabilities|devices|preflight|attempts/.test(call.path))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await waitFor(() => expect(saved?.runtime.steps).toBe(19));
  expect(saved?.runtime.seed).toBe(37);
});

it('参数范围取自返回合同而非组件常量', async () => {
  const changedContract = structuredClone(fixture); changedContract.items[0].parameters.steps.maximum = 16;
  contractResponse = async () => response(changedContract); mount();
  await screen.findByText(/训练步数须为 1—16/); expect(check()).toBeDisabled(); expect(input('训练步数')).toHaveValue(17);
  expect(input('训练步数')).toHaveAttribute('max', '16');
});

it('本机保留小数Alpha和1e-7学习率，切到NVIDIA后按新范围阻断而不调整值', async () => {
  task.draft.runtime = { ...task.draft.runtime, learning_rate: 1e-7, lora_alpha: 8.5 };
  mount(); await ready();
  fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: 'target-fixture' } });
  expect(check()).toBeDisabled(); await screen.findByText(/LoRA Alpha须为 1—64 之间的整数/);
  expect(input('学习率')).toHaveValue(1e-7); expect(input('LoRA Alpha')).toHaveValue(8.5);
  expect(input('学习率')).toHaveAttribute('min', '0.000001'); expect(input('LoRA Alpha')).toHaveAttribute('step', '1');
  fireEvent.change(input('学习率'), { target: { value: '0.000001' } }); fireEvent.change(input('LoRA Alpha'), { target: { value: '8' } }); await ready();
  expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it.each([['随机种子', '4294967296'], ['随机种子', '1.5'], ['训练步数', '200.5'], ['最大序列长度', '31'], ['LoRA 秩', '0'], ['训练末尾层数', '29']])('拒绝当前合同之外的%s=%s，保存输入仍可操作', async (label, value) => {
  mount(); await ready(); fireEvent.change(input(label), { target: { value } });
  expect(check()).toBeDisabled(); expect(input(label)).toHaveAttribute('aria-invalid', 'true');
  fireEvent.click(check()); expect(calls.some(call => call.path.endsWith('/preflight'))).toBe(false);
  expect(screen.getByRole('button', { name: '保存草稿' })).not.toBeDisabled();
});

it('缺失合同和读取失败均阻止检查，重试不覆盖已保存或未保存输入', async () => {
  contractResponse = async () => response({ items: [] }); mount(); await screen.findByText(/无法确认训练参数/);
  fireEvent.change(input('训练步数'), { target: { value: '23' } }); fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(saved?.runtime.steps).toBe(23)); expect(check()).toBeDisabled();
  contractResponse = async () => { throw new Error('合同读取失败'); };
  fireEvent.click(screen.getByRole('button', { name: '重新读取训练参数' })); await screen.findByText(/合同读取失败/);
  fireEvent.change(input('随机种子'), { target: { value: '919' } });
  contractResponse = async () => response(fixture); fireEvent.click(screen.getByRole('button', { name: '重新读取训练参数' })); await ready();
  expect(input('训练步数')).toHaveValue(23); expect(input('随机种子')).toHaveValue(919);
  expect(calls.filter(call => call.method !== 'GET').map(call => call.path)).toEqual(['/tasks/task-contract/draft']);
});

it.each(['source', 'seed', 'schema', 'duplicate', 'scope', 'fixed'])('合同%s缺失或失配时不猜测范围', async kind => {
  const broken: any = structuredClone(fixture);
  if (kind === 'source') delete broken.items[0].source;
  if (kind === 'seed') delete broken.items[0].parameters.seed.maximum;
  if (kind === 'schema') broken.items[0].schema_version = 'unknown-v2';
  if (kind === 'duplicate') broken.items.push(structuredClone(broken.items[0]));
  if (kind === 'scope') broken.items[0].execution_scope = 'remote';
  if (kind === 'fixed') broken.items[0].parameters.batch_size.editable = true;
  contractResponse = async () => response(broken); mount(); await screen.findByText(/无法确认训练参数/);
  expect(check()).toBeDisabled(); expect(input('训练步数')).toHaveValue(17); expect(changed).not.toHaveBeenCalled();
});

it('位置切换后的旧合同响应不能恢复旧范围或放行当前无效参数', async () => {
  const local = deferred<Response>(); const other = deferred<Response>(); let reads = 0;
  contractResponse = () => ++reads === 1 ? local.promise : other.promise;
  task.draft.runtime.learning_rate = 1e-7; mount();
  await screen.findByRole('option', { name: /NVIDIA 夹具/ }); fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: 'target-fixture' } });
  await waitFor(() => expect(reads).toBe(2)); await act(async () => other.resolve(response(fixture)));
  await screen.findByText(/学习率须为 0.000001—0.01/); expect(check()).toBeDisabled();
  await act(async () => local.resolve(response(fixture))); expect(input('学习率')).toHaveAttribute('min', '0.000001'); expect(check()).toBeDisabled();
});

it('切任务忽略旧请求失败，新任务元数据与已存值独立', async () => {
  const old = deferred<Response>(); let reads = 0; contractResponse = () => ++reads === 1 ? old.promise : Promise.resolve(response(fixture));
  const rendered = mount(); const next = { ...task, id: 'task-next', draft: { ...task.draft, runtime: { ...task.draft.runtime, seed: 99 } } };
  rendered.rerender(view(next)); await ready(); await act(async () => old.reject(new Error('旧任务读取失败')));
  expect(input('随机种子')).toHaveValue(99); expect(screen.queryByText(/旧任务读取失败/)).toBeNull(); expect(check()).not.toBeDisabled();
});

it('切库即使任务和项目编号相同，也忽略旧库成功响应', async () => {
  const old = deferred<Response>(); let epoch = 0; let reads = 0;
  const capture = () => { const current = epoch; return () => current === epoch; };
  contractResponse = () => ++reads === 1 ? old.promise : Promise.resolve(response({ items: [] }));
  const rendered = render(<LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>);
  epoch += 1;
  rendered.rerender(<LibraryReadContext.Provider key="new-library" value={capture}>{view()}</LibraryReadContext.Provider>);
  await screen.findByText(/无法确认训练参数/); await act(async () => old.resolve(response(fixture)));
  expect(check()).toBeDisabled(); expect(screen.queryByText(/默认值来源/)).toBeNull();
});

it('库切换已经开始但尚未卸载时，原读取也不能写入结果', async () => {
  const old = deferred<Response>(); let current = true; const capture = () => () => current;
  contractResponse = () => old.promise; render(<LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>);
  current = false; await act(async () => old.resolve(response(fixture)));
  expect(check()).toBeDisabled(); expect(screen.queryByText(/默认值来源/)).toBeNull();
});

it('切库失败后同一任务保持挂载，失效合同可重读且未保存值保持', async () => {
  let epoch = 0; let switching = false;
  const capture = () => { const current = epoch; return () => !switching && current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const rendered = render(content()); await ready();
  fireEvent.change(input('训练步数'), { target: { value: '23' } });
  switching = true; epoch += 1; rendered.rerender(content());
  switching = false; rendered.rerender(content());
  expect(check()).toBeDisabled(); expect(input('训练步数')).toHaveValue(23);
  expect(screen.getByText(/工作库读取已失效/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '重新读取训练参数' })); await ready();
  expect(input('训练步数')).toHaveValue(23); expect(screen.getByRole('button', { name: '保存草稿' })).not.toBeDisabled();
  expect(calls.filter(call => call.path === '/training-contracts')).toHaveLength(2);
  expect(calls.some(call => call.method !== 'GET')).toBe(false);
});

it('切库失败后重读合同，不恢复先前已通过的检查', async () => {
  let epoch = 0; const capture = () => { const current = epoch; return () => current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const rendered = render(content()); await ready(); fireEvent.click(check());
  await screen.findByRole('button', { name: '开始训练' });
  epoch += 1; rendered.rerender(content());
  expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull(); expect(check()).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '重新读取训练参数' })); await ready();
  expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
  expect(calls.filter(call => call.method !== 'GET').map(call => call.path)).toEqual(['/tasks/task-contract/preflight']);
});

it.each([['preflight', 'success'], ['preflight', 'failure'], ['attempts', 'success'], ['attempts', 'failure']])('切库后忽略迟到的%s %s，不写入旧结果或自动重试', async (stage, outcome) => {
  let epoch = 0; const capture = () => { const current = epoch; return () => current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const pending = deferred<Response>(); const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).endsWith('/' + stage)) {
      calls.push({ path: String(url).replace('/api/v1', ''), method: init?.method || 'GET', body: null });
      return pending.promise;
    }
    return original(url, init);
  });
  const rendered = render(content()); await ready(); fireEvent.click(check());
  if (stage === 'attempts') fireEvent.click(await screen.findByRole('button', { name: '开始训练' }));
  await waitFor(() => expect(calls.some(call => call.path.endsWith('/' + stage))).toBe(true));
  epoch += 1; rendered.rerender(content());
  await act(async () => outcome === 'failure' ? pending.reject(new Error('旧库迟到错误')) : pending.resolve(response(stage === 'preflight'
    ? { preflight_id: 'stale-preflight', can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime }
    : { id: 'stale-attempt', state: 'succeeded', state_version: 1, snapshot: { kind: 'text', operation: 'train' }, artifacts: [] })));
  expect(screen.queryByText(/旧库迟到错误/)).toBeNull(); expect(screen.queryByText('stale-attempt')).toBeNull();
  expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull(); expect(updated).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '重新读取训练参数' })); await ready();
  expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
  expect(calls.filter(call => call.path.endsWith('/' + stage))).toHaveLength(1);
});

it('检查先保存草稿时发生切库，迟到保存不覆盖当前输入或继续预检', async () => {
  let epoch = 0; const capture = () => { const current = epoch; return () => current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const pending = deferred<Response>(); const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => String(url).endsWith('/draft') ? pending.promise : original(url, init));
  const rendered = render(content()); await ready(); fireEvent.change(input('训练步数'), { target: { value: '23' } }); fireEvent.click(check());
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/draft'))).toBe(true));
  epoch += 1; rendered.rerender(content());
  await act(async () => pending.resolve(response({ ...task, draft_revision: 5, draft: { ...task.draft, runtime: { ...task.draft.runtime, steps: 23 } } })));
  expect(changed).not.toHaveBeenCalled(); expect(input('训练步数')).toHaveValue(23);
  expect(screen.getByRole('button', { name: '保存草稿' })).not.toBeDisabled();
  expect(calls.some(call => call.path.endsWith('/preflight'))).toBe(false);
});

it.each(['save', 'market', 'back', 'leave'].flatMap(action => ['success', 'failure'].map(outcome => [action, outcome])))('保存路径%s的迟到%s不会回写旧库数据、错误或导航', async (action, outcome) => {
  let epoch = 0; const capture = () => { const current = epoch; return () => current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const pending = deferred<Response>(); const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => String(url).endsWith('/draft') ? pending.promise : original(url, init));
  if (action === 'save') contractResponse = async () => response({ items: [] });
  const rendered = render(content());
  if (action === 'save') await screen.findByText(/无法确认训练参数/); else await ready();
  fireEvent.change(input('训练步数'), { target: { value: '23' } });
  let leaving: Promise<boolean> | undefined;
  if (action === 'leave') await act(async () => { leaving = leaveHandler!(); });
  else fireEvent.click(screen.getByRole('button', { name: action === 'save' ? '保存草稿' : action === 'market' ? '从数据市场选择训练数据' : '工作台', exact: true }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/draft'))).toBe(true));
  epoch += 1; rendered.rerender(content());
  await act(async () => outcome === 'failure' ? pending.reject(new Error('旧保存迟到错误')) : pending.resolve(response({ ...task, draft_revision: 5, draft: { ...task.draft, runtime: { ...task.draft.runtime, steps: 23 } } })));
  expect(changed).not.toHaveBeenCalled(); expect(backed).not.toHaveBeenCalled(); expect(input('训练步数')).toHaveValue(23);
  expect(screen.queryByText(/旧保存迟到错误/)).toBeNull(); expect(screen.queryByRole('dialog', { name: '数据市场' })).toBeNull();
  expect(screen.getByRole('button', { name: '保存草稿' })).not.toBeDisabled();
  if (leaving) expect(await leaving).toBe(false);
});

it('检查后显示样本轮数；修改字段和执行位置仍使旧检查失效', async () => {
  task.draft.runtime.steps = 192; mount(); await ready(); fireEvent.click(check());
  await screen.findByRole('button', { name: '开始训练' }); expect(screen.getByText(/64 条可训练样本，按文件顺序循环约 3 轮/)).toBeTruthy();
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/tasks/task-contract/preflight']);
  fireEvent.change(input('训练步数'), { target: { value: '128' } }); expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
  fireEvent.click(check()); await screen.findByRole('button', { name: '开始训练' });
  expect(saved?.runtime.steps).toBe(128);
  fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: 'target-fixture' } });
  expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull(); await ready();
  expect(calls.some(call => call.path.endsWith('/attempts'))).toBe(false);
});

it('旧草稿固定项不一致时保留原值并阻止运行', async () => {
  task.draft.runtime.batch_size = 2; mount(); await screen.findByText(/批大小当前仅支持 1/);
  expect(check()).toBeDisabled(); expect(task.draft.runtime.batch_size).toBe(2); expect(changed).not.toHaveBeenCalled();
  const contract = fixture.items[0] as TrainingContract;
  expect(trainingParameterErrors(contract, { ...defaultTrainingRuntime, learning_rate: Infinity })).toHaveProperty('learning_rate');
  expect(trainingParameterErrors(contract, { ...defaultTrainingRuntime, seed: true as unknown as number })).toHaveProperty('seed');
});

it('检查点草稿不能改参数，但读取失败后仍可重试合同', async () => {
  task.draft.checkpoint_id = 'checkpoint-fixture'; contractResponse = async () => response({ items: [] });
  mount(); await screen.findByText(/无法确认训练参数/); expect(input('训练步数')).toBeDisabled();
  const retry = screen.getByRole('button', { name: '重新读取训练参数' }); expect(retry).not.toBeDisabled();
  contractResponse = async () => response(fixture); fireEvent.click(retry); await ready();
  expect(input('训练步数')).toBeDisabled();
});

it.each(['draft', 'preflight', 'attempts'])('生成任务的%s迟到成功也不能绕过共享工作库保护', async stage => {
  task = { ...task, operation: 'generate', draft: { ...task.draft, operation: 'generate', runtime: { ...defaultRuntime, seed: 37 } } };
  let epoch = 0; const capture = () => { const current = epoch; return () => current === epoch; };
  const content = () => <LibraryReadContext.Provider value={capture}>{view()}</LibraryReadContext.Provider>;
  const pending = deferred<Response>(); const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (url, init) => String(url).endsWith('/' + stage) ? pending.promise : original(url, init));
  const rendered = render(content()); await ready();
  if (stage === 'draft') fireEvent.change(input('随机种子'), { target: { value: '99' } });
  fireEvent.click(check());
  if (stage === 'attempts') fireEvent.click(await screen.findByRole('button', { name: '开始运行' }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith('/' + stage))).toBe(true));
  epoch += 1; rendered.rerender(content());
  await act(async () => pending.resolve(response(stage === 'draft' ? { ...task, draft_revision: 5, draft: { ...task.draft, runtime: { ...task.draft.runtime, seed: 99 } } }
    : stage === 'preflight' ? { preflight_id: 'stale-preflight', can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime }
    : { id: 'stale-generation', state: 'succeeded', state_version: 1, snapshot: { kind: 'text', operation: 'generate' }, artifacts: [] })));
  expect(changed).not.toHaveBeenCalled(); expect(updated).not.toHaveBeenCalled(); expect(screen.queryByText('stale-generation')).toBeNull();
  if (stage === 'draft') { expect(input('随机种子')).toHaveValue(99); expect(screen.getByRole('button', { name: '保存草稿' })).not.toBeDisabled(); }
  if (stage === 'preflight') expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
  expect(calls.some(call => call.path === '/training-contracts')).toBe(false);
});

it('生成任务不读取训练合同', async () => {
  task = { ...task, operation: 'generate', draft: { ...task.draft, operation: 'generate', runtime: { ...defaultRuntime } } };
  mount(); await waitFor(() => expect(calls.some(call => call.path.startsWith('/execution-targets?'))).toBe(true));
  expect(calls.some(call => call.path === '/training-contracts')).toBe(false); expect(screen.queryByLabelText('训练参数约束')).toBeNull();
});
