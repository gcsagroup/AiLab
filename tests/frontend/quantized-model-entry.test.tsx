import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import type { EvaluationPlan } from '../../apps/desktop/src/Evaluation';
import type { Model, Task } from '../../apps/desktop/src/types';
import type { LibraryViews } from '../../apps/desktop/src/ProjectContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const base: Model = { id: 'base', name: '原始权重', format: 'safetensors', modality: 'text' };
const quantized: Model = { id: 'quantized', name: '独立量化结果', format: 'mlx-safetensors', default_engine: 'mlx', modality: 'text', source_model_id: base.id, source_attempt_id: 'conversion-attempt', status: 'experimental', conversion: { quantization: { bits: 4, group_size: 64, mode: 'affine' }, source_weight_bytes: 1000, output_weight_bytes: 300, independent_use: 'verified' } };
const plan: EvaluationPlan = { id: 'plan', name: '首次冻结规则', sample_count: 16, category_counts: { business: 4, format: 4, regression: 4, behavior: 4 }, criteria: { schema_version: 'text-rules-v1', category_min_pass_rate: { business: .75, format: .75, regression: .75, behavior: .75 }, regression_tolerance: 0, generation: { max_tokens: 64, temperature: 0, top_p: 1, seed: 0 } } };
const task: Task = { id: 'evaluation-task', project_id: 'project', name: '固定量化对照', draft_revision: 1, kind: 'text', operation: 'evaluate', draft: { kind: 'text', operation: 'evaluate', evaluation_kind: 'quantized_model', model_id: base.id, candidate_model_id: quantized.id, dataset_id: null, adapter_id: null, evaluation_plan_id: plan.id, input: { prompt: '' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', seed: 0 } } };
let models: Model[], storedTask: Task | null, paged: boolean;
let selection: LibraryViews;
let reads: string[], writes: { path: string; body: Record<string, unknown> }[];
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
beforeEach(() => {
  models = [base, quantized]; storedTask = null; paged = false; reads = []; writes = [];
  selection = { project_id: null, projects: {} };
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit) => {
    const path = String(input).replace('/api/v1', '');
    // 仅单独处理界面偏好；模型执行、草稿修改等写入仍由下方严格拒绝。
    if (path === '/ui-context') {
      expect(['GET', 'PATCH']).toContain(options.method);
      if (options.method === 'PATCH') {
        const body = JSON.parse(String(options.body));
        expect(body.project_id).toBe('project');
        expect(body.context.task_id === null || body.context.task_id === storedTask?.id).toBe(true);
        selection = { project_id: body.project_id, projects: { ...selection.projects, [body.project_id]: body.context } };
      }
      return response(selection);
    }
    if (options.method !== 'GET') {
      const body = JSON.parse(String(options.body)); writes.push({ path, body });
      if (path === '/evaluations') { storedTask = task; return response(task); }
      throw new Error('此检查不允许执行模型或修改草稿：' + path);
    }
    reads.push(path);
    if (path === '/projects') return response({ items: [{ id: 'project', name: '量化入口验收', revision: 1 }] });
    if (path === '/models?project_id=project') return response({ items: paged ? [base] : models, next_cursor: paged ? 'later-models' : null });
    if (path === '/models/quantized') return response({ ...quantized, project_id: 'project' });
    if (path === '/evaluation-plans?project_id=project') return response({ items: [plan] });
    if (path === '/tasks?project_id=project') return response({ items: storedTask ? [{ ...storedTask, draft: undefined }] : [] });
    if (path === '/tasks/evaluation-task') return response(storedTask);
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('没有适配器时也能从量化卡片创建专用评测，创建后仍需检查和明确开始', async () => {
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  fireEvent.click(await screen.findByRole('button', { name: '量化质量评测' }));
  expect((screen.getByLabelText('比较类型') as HTMLSelectElement).value).toBe('quantized_model');
  expect((screen.getByLabelText('量化模型') as HTMLSelectElement).value).toBe('quantized');
  expect(writes).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: '创建评测任务' }));
  await screen.findByRole('button', { name: '检查评测配置' });
  expect(writes).toEqual([{ path: '/evaluations', body: { project_id: 'project', candidate_model_id: 'quantized', evaluation_plan_id: 'plan' } }]);
  expect(screen.queryByRole('button', { name: '开始独立评测' })).toBeNull();
});

it('已独立加载和已登记文件不代表质量通过；正式通过只显示对应规则范围', async () => {
  models = [quantized, { ...quantized, id: 'passed', name: '已验收量化结果', status: 'quality_approved', quality_status: 'passed', quality_candidate_id: 'candidate-id', quality_scope: '仅覆盖固定的十六条问题' }, { ...quantized, id: 'incomplete', name: '缺少质量登记身份', status: 'quality_approved', quality_status: 'passed' }];
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
  await screen.findByText('已验收量化结果');
  const cards = screen.getAllByRole('article');
  const experimental = cards.find(card => within(card).queryByRole('heading', { name: quantized.name }))!;
  const approved = cards.find(card => within(card).queryByRole('heading', { name: '已验收量化结果' }))!;
  const incomplete = cards.find(card => within(card).queryByRole('heading', { name: '缺少质量登记身份' }))!;
  expect(within(experimental).getByText('实验模型 · 待验收')).toBeTruthy();
  expect(within(incomplete).getByText('实验模型 · 待验收')).toBeTruthy();
  expect(within(approved).getByText('量化候选 · 质量通过')).toBeTruthy();
  expect(within(approved).getByText('仅覆盖固定的十六条问题')).toBeTruthy();
  expect(writes).toEqual([]);
});

it('从历史打开评测补回后页量化模型，不追随其余页或修改原任务', async () => {
  storedTask = task; paged = true;
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /^固定量化对照/ }));
  await screen.findByText('独立量化结果');
  await waitFor(() => expect(reads).toContain('/models/quantized'));
  expect(reads.some(path => path.includes('cursor='))).toBe(false);
  expect(writes).toEqual([]);
});
