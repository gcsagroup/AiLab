import React from 'react';
import trainingContracts from './fixtures/training-contracts.json';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EvaluationPlanDialog, EvaluationTask, type EvaluationPlan, type EvaluationReport } from '../../apps/desktop/src/Evaluation';
import Workbench, { defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import type { Adapter, Candidate, Model, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const plan: EvaluationPlan = { id: 'plan-a', name: '独立评测集', sample_count: 4, category_counts: { business: 1, format: 1, regression: 1, behavior: 1 }, evaluation_plan_digest: 'frozen-digest', criteria: { schema_version: 'text-rules-v1', category_min_pass_rate: { business: 1, format: 1, regression: 1, behavior: 1 }, regression_tolerance: 0, generation: { max_tokens: 64, temperature: 0, top_p: 1, seed: 0 } } };
const adapter: Adapter = { id: 'adapter-a', name: '实验适配器', status: 'experimental', base_model_id: 'model-a', base_model_version_id: 'model-v1', base_manifest_digest: 'base', training_recipe_digest: 'recipe', manifest_digest: 'adapter', source_attempt_id: 'source-attempt' };
const task: Task = { id: 'eval-task', name: '独立文本评测', kind: 'text', operation: 'evaluate', project_id: 'project-a', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: 'model-a', dataset_id: null, adapter_id: adapter.id, evaluation_plan_id: plan.id, input: { prompt: '' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', seed: 0 } } };
const count = { passed: 1, total: 1, pass_rate: 1 };
const counts = { business: count, format: count, regression: count, behavior: count };
let report: EvaluationReport;
let calls: { path: string; method: string; body: Record<string, unknown>; key?: string }[];
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = [];
  report = { status: 'failed', eligible: false, prospective_plan_bound: false, counts: { baseline: counts, candidate: counts }, criteria: plan.criteria, regression_pass_rate_delta: 0, manual_pending: 0, unknown: 0, blocking: [{ code: 'POSTHOC_EVALUATION' }], samples: [{ id: 'business-1', category: 'business', prompt: '独立测试问题', rule: { type: 'exact', expected: '实际回答' }, baseline: { output: '实际回答', status: 'passed', reason: '精确相同' }, candidate: { output: '实际回答', status: 'passed', reason: '精确相同' } }], quality_scope: '仅代表本冻结文本规则集' };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : {};
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    const attempt = { id: 'eval-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4, last_event_sequence: 0, snapshot: { operation: 'evaluate' }, artifacts: [], allowed_actions: [] };
    let response: unknown = attempt;
    if (path === '/training-contracts') response = trainingContracts;
    if (path.startsWith('/execution-targets?')) response = { items: [] };
    if (path === '/evaluation-plans') response = plan;
    if (path.endsWith('/draft')) response = { ...task, draft_revision: 2, draft: body.draft };
    if (path.endsWith('/preflight')) response = { preflight_id: 'check-eval', can_submit: true, blocking: [], warnings: [] };
    if (path.includes('/events?')) response = { items: [], next_cursor: 0 };
    if (path === '/evaluations/eval-a') response = { ...attempt, adapter_id: adapter.id, evaluation_plan_id: plan.id, report };
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('冻结评测与候选准入界面', () => {
  it('明确冻结才保存规则，响应丢失重试保留编号，不创建计算任务', async () => {
    const normalFetch = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await normalFetch(input, init); if (!dropped) { dropped = true; throw new Error('冻结结果待确认'); } return result; });
    render(<EvaluationPlanDialog projectId="project-a" onClose={() => {}} onCreated={() => {}} />);
    fireEvent.change(screen.getByLabelText('评测 JSONL 文件'), { target: { value: '/tests/eval.jsonl' } });
    expect(calls).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: '检查并冻结方案' }));
    await screen.findByText('冻结结果待确认');
    fireEvent.click(screen.getByRole('button', { name: '检查并冻结方案' }));
    await screen.findByText('评测数据与规则已保存为独立版本');
    expect(calls).toHaveLength(2); expect(calls[1].key).toBe(calls[0].key);
    expect(calls.every(call => call.path === '/evaluation-plans')).toBe(true);
    expect(calls[0].body.criteria).toEqual(plan.criteria);
  });
  it('训练先保存所选冻结方案再检查，换方案会使旧检查失效', async () => {
    const training = { ...task, operation: 'train' as const, draft: { ...task.draft, operation: 'train' as const, evaluation_plan_id: null, runtime: defaultTrainingRuntime } };
    render(<Workbench task={training} models={[]} datasets={[]} devices={[]} evaluationPlans={[plan]} onBack={() => {}} registerLeave={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
    fireEvent.change(screen.getByLabelText('训练前冻结评测方案'), { target: { value: plan.id } });
    await waitFor(() => expect((screen.getByRole('button', { name: '检查配置' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByRole('button', { name: '开始训练' });
    const commands = calls.filter(call => call.method !== 'GET');
    expect(commands[0].path).toBe('/tasks/eval-task/draft');
    expect(commands[0].body.draft).toMatchObject({ evaluation_plan_id: plan.id });
    expect(commands[1].body).toEqual({ draft_revision: 2 });
    fireEvent.change(screen.getByLabelText('训练前冻结评测方案'), { target: { value: '' } });
    expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
    expect(screen.getByText(/未提前绑定评测方案的训练产物/)).toBeTruthy();
  });
  it('检查不自动执行；事后对照即使所有问题通过也不能登记', async () => {
    render(<EvaluationTask task={task} plans={[plan]} adapters={[adapter]} models={[]} registerLeave={() => {}} onBack={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: '检查评测配置' }));
    await screen.findByRole('button', { name: '开始独立评测' });
    expect(calls.map(call => call.path)).toEqual(['/tasks/eval-task/preflight']);
    fireEvent.click(screen.getByRole('button', { name: '开始独立评测' }));
    await screen.findByText('质量评测报告');
    expect(screen.getByRole('button', { name: '登记通过评测的候选' }).matches(':disabled')).toBe(true);
    expect(screen.getByText(/事后评测不能用于准入/)).toBeTruthy();
    expect(screen.queryByLabelText('输入内容')).toBeNull();
    expect(calls.some(call => call.path.includes('/register') || call.path.endsWith('/draft'))).toBe(false);
  });
  it('来源与质量均通过才允许显式登记，登记绑定当前评测尝试', async () => {
    report = { ...report, status: 'passed', eligible: true, prospective_plan_bound: true, blocking: [] };
    const current = { id: 'eval-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4 };
    render(<EvaluationTask task={{ ...task, latest_attempt: current }} plans={[plan]} adapters={[adapter]} models={[]} registerLeave={() => {}} onBack={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    const register = await screen.findByRole('button', { name: '登记通过评测的候选' });
    await waitFor(() => expect(register.matches(':disabled')).toBe(false));
    expect(calls.some(call => call.path.includes('/register'))).toBe(false);
    fireEvent.click(register);
    await screen.findByRole('button', { name: '已登记通过评测的候选' });
    expect(calls.find(call => call.path.includes('/register'))).toMatchObject({ path: '/candidates/adapter-a/register', body: { evaluation_ids: ['eval-a'] } });
  });
  it('量化模型登记使用明确模型类型，不会匹配其他空适配器候选', async () => {
    report = { ...report, status: 'passed', eligible: true, prospective_plan_bound: true, blocking: [], evaluation_kind: 'quantized_model' };
    const current = { id: 'eval-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4 };
    const model = { id: 'quantized-a', name: '独立量化模型', status: 'experimental', format: 'mlx-safetensors', default_engine: 'mlx', source_model_id: 'model-a' } as Model;
    const unrelated = { id: 'registered-other', adapter_id: null, candidate_type: 'quantized_model', model_id: 'another-model', quality_status: 'passed' } as Candidate;
    render(<EvaluationTask task={{ ...task, draft: { ...task.draft, operation: 'evaluate', evaluation_kind: 'quantized_model', candidate_model_id: model.id, adapter_id: null }, latest_attempt: current }} plans={[plan]} adapters={[]} models={[model]} candidates={[unrelated]} registerLeave={() => {}} onBack={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    expect(screen.getByText('来源原权重')).toBeTruthy();
    const register = await screen.findByRole('button', { name: '登记通过评测的候选' });
    expect(register.matches(':disabled')).toBe(false);
    fireEvent.click(register);
    await screen.findByRole('button', { name: '已登记通过评测的候选' });
    expect(calls.find(call => call.path.includes('/register'))).toMatchObject({ path: '/candidates/quantized-a/register', body: { candidate_type: 'quantized_model', evaluation_ids: ['eval-a'] } });
  });
  it('量化模型更换首次方案后显示不可准入且不能登记', async () => {
    report = { ...report, evaluation_kind: 'quantized_model', blocking: [{ code: 'MODEL_QUALITY_PLAN_MISMATCH' }] };
    const current = { id: 'eval-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4 };
    const model = { id: 'quantized-a', name: '独立量化模型', status: 'experimental' } as Model;
    render(<EvaluationTask task={{ ...task, draft: { ...task.draft, operation: 'evaluate', evaluation_kind: 'quantized_model', candidate_model_id: model.id, adapter_id: null }, latest_attempt: current }} plans={[plan]} adapters={[]} models={[model]} registerLeave={() => {}} onBack={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await screen.findByText('本次没有使用该量化模型首次固定的方案，只能查看对照结果');
    expect(screen.getByRole('button', { name: '登记通过评测的候选' }).matches(':disabled')).toBe(true);
    expect(calls.some(call => call.path.includes('/register'))).toBe(false);
  });
});
