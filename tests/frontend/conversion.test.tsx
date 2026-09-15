import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ConversionStartDialog, ConversionTask } from '../../apps/desktop/src/Conversion';
import type { Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const model = { id: 'model-a', name: '本机Qwen', format: 'safetensors', modality: 'text' as const };
const task: Task = { id: 'convert-a', project_id: 'project-a', name: 'MLX 4-bit 量化', kind: 'text', operation: 'quantize', draft_revision: 1, draft: { kind: 'text', operation: 'quantize', model_id: model.id, dataset_id: null, input: { prompt: '' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', seed: 0 } } };
let calls: { path: string; method: string; body: unknown; key?: string }[];
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let response: unknown = { id: 'run-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4, snapshot: { operation: 'quantize' }, output_text: '分词器内部行\n'.repeat(300000), effective_config: { source_weight_bytes: 1000000, output_weight_bytes: 280000 }, last_event_sequence: 0, artifacts: [{ id: 'artifact-conversion', name: 'conversion.json' }], allowed_actions: [] };
    if (path === '/conversions') response = task;
    if (path.endsWith('/preflight')) response = { preflight_id: 'quant-check', can_submit: true, blocking: [], warnings: [] };
    if (path.includes('/events?')) response = { items: [] };
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('量化实验与产物', () => {
  it('创建任务只固定源模型和组合，不自动计算，已量化模型不作为来源选项', async () => {
    const created = vi.fn();
    render(<ConversionStartDialog projectId="project-a" models={[model, { ...model, id: 'quantized', name: '已量化模型', model_config: { quantization: { bits: 4 } } }]} onClose={() => {}} onCreated={created} />);
    expect(screen.queryByRole('option', { name: '已量化模型' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '创建量化任务' }));
    await waitFor(() => expect(created).toHaveBeenCalledWith(task));
    expect(calls.map(call => call.path)).toEqual(['/conversions']);
  });
  it('检查→明确开始→保存实验模型三个独立步骤，不使用生成表单或登记质量候选', async () => {
    render(<ConversionTask task={task} models={[model]} onBack={() => {}} registerLeave={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    expect(screen.queryByLabelText('输入内容')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '检查量化配置' }));
    await screen.findByRole('button', { name: '开始量化' });
    expect(calls.map(call => call.path)).toEqual(['/tasks/convert-a/preflight']);
    fireEvent.click(screen.getByRole('button', { name: '开始量化' }));
    await screen.findByText('量化产物已保存');
    expect(screen.getByText('原权重体积')).toBeTruthy();
    expect(screen.queryByLabelText('模型输出')).toBeNull();
    expect(screen.queryByRole('button', { name: '保存作品' })).toBeNull();
    expect(screen.getByText('量化权重体积')).toBeTruthy();
    expect(calls.some(call => call.path.endsWith('/converted-models'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '保存实验量化模型' }));
    await screen.findByRole('button', { name: '已保存实验量化模型' });
    expect(calls.some(call => call.path.includes('/register'))).toBe(false);
    expect(calls.find(call => call.path.endsWith('/converted-models'))?.path).toBe('/attempts/run-a/converted-models');
  });
});
