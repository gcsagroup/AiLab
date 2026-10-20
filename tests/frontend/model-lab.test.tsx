import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ModelLabDialog } from '../../apps/desktop/src/ModelLab';
import { FormatDialog } from '../../apps/desktop/src/FormatConversion';
import type { Adapter, Dataset, Model } from '../../apps/desktop/src/types';
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const base: Model = { id: 'base', name: '原始模型', format: 'safetensors', modality: 'text', model_config: { model_type: 'qwen2', hidden_size: 896, num_hidden_layers: 24 } };
const adapters = [{ id: 'matching', name: '同基座适配器', base_model_id: 'base' }, { id: 'foreign', name: '其他基座适配器', base_model_id: 'other' }] as Adapter[];
const datasets = [{ id: 'train', name: '派生训练集', schema: 'sft', dataset_split_role: 'train' }, { id: 'heldout', name: '留出验证集', schema: 'sft', dataset_split_role: 'validation' }] as Dataset[];
let calls: { path: string; body: Record<string, unknown> }[];
beforeEach(() => {
  calls = [];
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => { calls.push({ path: String(input).replace('/api/v1', ''), body: JSON.parse(String(init.body)) }); return { ok: true, json: async () => ({ id: 'created' }) }; }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('合并只显示匹配适配器，创建草稿不会自动执行', async () => {
  const created = vi.fn();
  render(<ModelLabDialog operation="merge" projectId="p" models={[base]} adapters={adapters} datasets={datasets} onClose={() => {}} onCreated={created} />);
  expect(screen.queryByRole('option', { name: '其他基座适配器' })).toBeNull();
  fireEvent.change(screen.getByLabelText('适配器'), { target: { value: 'matching' } });
  fireEvent.change(screen.getByLabelText('融合比例（0.01—1）'), { target: { value: '0.75' } });
  fireEvent.click(screen.getByRole('button', { name: '创建合并任务' }));
  await waitFor(() => expect(created).toHaveBeenCalled());
  expect(calls).toEqual([{ path: '/model-lab/tasks', body: { project_id: 'p', operation: 'merge', model_id: 'base', adapter_id: 'matching', merge_weight: 0.75 } }]);
});
it('蒸馏不提供留出验证集，并拒绝小数训练步数', async () => {
  render(<ModelLabDialog operation="distill" projectId="p" models={[base]} adapters={adapters} datasets={datasets} onClose={() => {}} onCreated={() => {}} />);
  expect(screen.queryByRole('option', { name: '留出验证集' })).toBeNull();
  fireEvent.change(screen.getByLabelText('学生训练步数（1—200）'), { target: { value: '1.5' } });
  fireEvent.click(screen.getByRole('button', { name: '创建蒸馏任务' }));
  expect(await screen.findByText('请在标明范围内填写完整数值；步数与词元数必须为整数。')).toBeTruthy();
  expect(calls).toHaveLength(0);
});
it.each(['coreml', 'onnx', 'torchscript'])('格式 %s 提交真实目标并标明固定 CPU 范围', async target => {
  const created = vi.fn();
  render(<FormatDialog projectId="p" models={[base]} onClose={() => {}} onCreated={created} />);
  expect(screen.getByText(/CPU · FP32 · 固定 128/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('目标格式'), { target: { value: target } });
  fireEvent.click(screen.getByRole('button', { name: '创建转换任务' }));
  await waitFor(() => expect(created).toHaveBeenCalled());
  expect(calls).toEqual([{ path: '/format-conversions', body: { project_id: 'p', model_id: 'base', target_format: target } }]);
});
it('转换模型试用冻结本身身份，不让用户选错引擎', async () => {
  const created = vi.fn(); const model = { ...base, id: 'converted', format: 'onnx', default_engine: 'onnx' };
  render(<FormatDialog projectId="p" models={[base, model]} trialModel={model} onClose={() => {}} onCreated={created} />);
  expect(screen.queryByLabelText('目标格式')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '创建试用任务' }));
  await waitFor(() => expect(created).toHaveBeenCalled());
  expect(calls[0]).toEqual({ path: '/formatted-model-trials', body: { project_id: 'p', model_id: 'converted', prompt: '只回答一个数字：4加5等于几？', max_tokens: 32 } });
});
