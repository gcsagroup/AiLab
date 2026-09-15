import React from 'react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Workbench, { defaultRuntime } from '../../apps/desktop/src/Workbench';
import { ExecutionDefault, ExecutionLocation } from '../../apps/desktop/src/ExecutionLocation';
import type { Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const target = { id: 'execution-target-a', name: '验证服务', origin: 'http://127.0.0.1:6000', executor_id: 'executor-a', project_id: 'project-a', nvidia_ready: false };
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
let task: Task; let calls: { path: string; method: string; body: any }[]; let ready: boolean; let savedDefault: { execution_target_id: string | null; revision: number };
beforeEach(() => {
  ready = true; calls = []; savedDefault = { execution_target_id: null, revision: 1 };
  task = { id: 'task-a', project_id: 'project-a', name: '位置核实', kind: 'text', operation: 'generate', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: 'model-a', dataset_id: null, adapter_id: 'adapter-a', input: { prompt: '保留此输入' }, runtime: { ...defaultRuntime, kv_precision: 'auto', prefill_step_size: 2048 } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init?.method || 'GET'; const body = init?.body ? JSON.parse(String(init.body)) : undefined; calls.push({ path, method, body });
    if (path.startsWith('/execution-targets?')) return response({ items: [target] });
    if (path.endsWith('/execution-default')) {
      if (method === 'POST') { expect(body.expected_revision).toBe(savedDefault.revision); savedDefault = { execution_target_id: body.execution_target_id, revision: savedDefault.revision + 1 }; }
      return response(savedDefault);
    }
    if (path.endsWith('/draft')) { task = { ...task, draft: body.draft, draft_revision: task.draft_revision + 1 }; return response(task); }
    if (path.endsWith('/preflight')) return response({ preflight_id: 'check-a', can_submit: ready, blocking: ready ? [] : [{ message: '此目标未探测到可用CUDA，不能运行。' }], warnings: [], effective_config: task.draft.runtime, ...(task.draft.execution_target_id ? { execution_target: target, upload_summary: { files: [{ path: 'model/config.json', size: 123, sha256: 'a'.repeat(64) }], total_bytes: 123 } } : {}) });
    if (path.endsWith('/attempts') && method === 'POST') return response({ id: 'attempt-a', state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, output_text: '已有结果' });
    if (path === '/attempts/attempt-a') return response({ id: 'attempt-a', state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, output_text: '已有结果' });
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function mount() { return render(<Workbench task={task} models={[{ id: 'model-a', name: '固定原权重', format: 'safetensors' }]} datasets={[]} devices={[{ id: 'apple-gpu', name: '本机 Apple GPU' }]} registerLeave={() => {}} onBack={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />); }

it('选择目标清除不适用字段，检查展示发送范围，明确开始才提交', async () => {
  mount(); await screen.findByRole('option', { name: '验证服务 · NVIDIA 尚未就绪' });
  expect(calls.every(call => call.method === 'GET')).toBe(true);
  fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: target.id } });
  const notice = 'NVIDIA 首期使用原权重，已清除本次实验适配器选择；原适配器与历史记录保留。'; expect(screen.getByText(notice)).toBeTruthy();
  expect(screen.queryByLabelText('KV 缓存精度')).toBeNull(); expect(screen.queryByLabelText('提示词分块上限')).toBeNull();
  expect(screen.getByLabelText('最大输出 token')).toHaveAttribute('max', '512');
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await screen.findByRole('button', { name: '确认发送并开始运行' });
  expect(calls.filter(call => call.path.endsWith('/draft') && call.method === 'PATCH')).toHaveLength(1); expect(screen.getByText(notice)).toBeTruthy();
  expect(task.draft).toMatchObject({ execution_target_id: target.id, adapter_id: null, input: { prompt: '保留此输入' }, runtime: { engine: 'transformers', device_id: 'cuda:0', precision: 'bfloat16' } });
  expect(task.draft.runtime).not.toHaveProperty('kv_precision'); expect(task.draft.runtime).not.toHaveProperty('prefill_step_size');
  expect(screen.getByRole('region', { name: '本次发送范围' })).toHaveTextContent('model/config.json');
  expect(calls.some(call => call.path.endsWith('/attempts'))).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '确认发送并开始运行' })); await screen.findByText('已有结果');
  expect(calls.filter(call => call.path.endsWith('/attempts') && call.method === 'POST')).toHaveLength(1);
});
it('从远端切回本机使旧检查失效，远端字段不会进入本机配方', async () => {
  task.draft = { ...task.draft, execution_target_id: target.id, runtime: { ...defaultRuntime, engine: 'transformers', device_id: 'cuda:0', precision: 'bfloat16' } }; mount();
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await screen.findByRole('button', { name: '确认发送并开始运行' });
  fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: '' } }); expect(screen.queryByRole('button', { name: '确认发送并开始运行' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await waitFor(() => expect(task.draft.execution_target_id).toBeNull());
  expect(task.draft.runtime).toMatchObject({ engine: 'mlx', device_id: 'apple-gpu' }); expect(task.draft.runtime).not.toHaveProperty('precision'); expect(screen.getByLabelText('KV 缓存精度')).toBeTruthy();
});
it('CUDA未就绪显示真实阻断，不显示发送开始按钮', async () => {
  ready = false; task.draft.execution_target_id = target.id; mount(); fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  await screen.findByText('此目标未探测到可用CUDA，不能运行。'); expect(screen.queryByRole('button', { name: '确认发送并开始运行' })).toBeNull(); expect(calls.some(call => call.path.endsWith('/attempts'))).toBe(false);
});
it('修改项目默认需要明确保存，设置接口不触碰现有草稿', async () => {
  render(<ExecutionDefault projectId="project-a" onChanged={() => {}} />); await screen.findByRole('option', { name: '验证服务 · NVIDIA 尚未就绪' });
  await waitFor(() => expect(screen.getByLabelText('执行位置')).toBeEnabled()); fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: target.id } });
  expect(calls.every(call => call.method === 'GET')).toBe(true); fireEvent.click(screen.getByRole('button', { name: '保存默认执行位置' }));
  await screen.findByText('已保存。仅以后新建的文本任务使用此默认位置，现有草稿保持原位置。');
  expect(savedDefault.execution_target_id).toBe(target.id); expect(task.draft.execution_target_id).toBeUndefined(); expect(calls.filter(call => call.method === 'POST')).toEqual([{ path: '/projects/project-a/execution-default', method: 'POST', body: { execution_target_id: target.id, expected_revision: 1 } }]);
});
it('已保存的后页目标保留编号，不被首页或项目默认悄悄改回本机', async () => {
  const change = vi.fn(); render(<ExecutionLocation projectId="project-a" value="execution-target-later" disabled={false} onChange={change} />);
  await screen.findByRole('option', { name: '验证服务 · NVIDIA 尚未就绪' }); expect(screen.getByLabelText('执行位置')).toHaveValue('execution-target-later'); expect(change).not.toHaveBeenCalled();
});
it('项目切换后忽略旧默认的迟到响应', async () => {
  let resolveOld!: (value: Response) => void; const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((input, init) => String(input).endsWith('/projects/project-a/execution-default') ? new Promise(resolve => { resolveOld = resolve; }) : original(input, init));
  const view = render(<ExecutionDefault projectId="project-a" onChanged={() => {}} />); await waitFor(() => expect(resolveOld).toBeTruthy());
  view.rerender(<ExecutionDefault projectId="project-b" onChanged={() => {}} />); await waitFor(() => expect(screen.getByLabelText('执行位置')).toBeEnabled());
  await act(async () => resolveOld(response({ execution_target_id: target.id, revision: 99 }))); expect(screen.getByLabelText('执行位置')).toHaveValue('');
});
it('目标列表刷新只更新可选位置，保留尚未保存的默认选择', async () => {
  const view = render(<ExecutionDefault projectId="project-a" refreshKey="" onChanged={() => {}} />); await screen.findByRole('option', { name: '验证服务 · NVIDIA 尚未就绪' });
  await waitFor(() => expect(screen.getByLabelText('执行位置')).toBeEnabled()); fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: target.id } });
  view.rerender(<ExecutionDefault projectId="project-a" refreshKey="new-list" onChanged={() => {}} />); await screen.findByRole('option', { name: '验证服务 · NVIDIA 尚未就绪' });
  expect(screen.getByLabelText('执行位置')).toHaveValue(target.id); expect(screen.getByRole('button', { name: '保存默认执行位置' })).toBeEnabled(); expect(savedDefault.execution_target_id).toBeNull();
});
