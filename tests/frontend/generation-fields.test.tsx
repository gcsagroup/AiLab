import React, { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { GenerationFields } from '../../apps/desktop/src/GenerationFields';
import Workbench, { defaultRuntime, defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import type { Runtime, Task } from '../../apps/desktop/src/types';

const original: Runtime = { ...defaultRuntime };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function Fields({ initial = original, onChange = vi.fn() }: { initial?: Runtime; onChange?: (runtime: Runtime) => void }) {
  const [runtime, setRuntime] = useState(initial);
  return <GenerationFields runtime={runtime} onChange={next => { setRuntime(next); onChange(next); }} />;
}

it('旧草稿显示固定默认值，展示不写入草稿，超限和思考模式没有虚假选项', () => {
  const change = vi.fn(); render(<GenerationFields runtime={original} onChange={change} />);
  expect((screen.getByLabelText('上下文总预算（词元）') as HTMLInputElement).value).toBe('4096');
  expect((screen.getByLabelText('流式显示输出') as HTMLInputElement).checked).toBe(true);
  expect((screen.getByLabelText('输入超限处理') as HTMLSelectElement).disabled).toBe(true);
  expect((screen.getByLabelText('思考模式') as HTMLSelectElement).disabled).toBe(true);
  expect(screen.getByText(/预算包含聊天模板、输入和完整最大输出预留/)).toBeTruthy();
  expect(change).not.toHaveBeenCalled();
});

it('真实键盘 Enter 能继续第二行，其他参数变化不会吞掉待输入换行', async () => {
  const user = userEvent.setup(); const change = vi.fn(); render(<Fields onChange={change} />);
  const textarea = screen.getByLabelText('停止序列') as HTMLTextAreaElement;
  await user.type(textarea, 'END{Enter}');
  expect(textarea.value).toBe('END\n'); expect(change.mock.calls.at(-1)?.[0].stop).toEqual(['END']);
  fireEvent.click(screen.getByLabelText('流式显示输出'));
  expect(textarea.value).toBe('END\n');
  await user.type(textarea, 'DONE');
  expect(textarea.value).toBe('END\nDONE'); expect(change.mock.calls.at(-1)?.[0]).toMatchObject({ stop: ['END', 'DONE'], stream: false });
});

it('停止词只忽略空行，保留首尾空格、空格行和制表符', () => {
  const change = vi.fn(); render(<Fields onChange={change} />);
  fireEvent.change(screen.getByLabelText('停止序列'), { target: { value: ' 完成 \n\n \n\t结束\t\n' } });
  expect(change.mock.calls.at(-1)?.[0].stop).toEqual([' 完成 ', ' ', '\t结束\t']);
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe(' 完成 \n\n \n\t结束\t\n');
  expect(screen.queryByRole('alert')).toBeNull();
});

it('外部 runtime 同值回显保留本地换行，新的停止序列正确同步且不反向提交', () => {
  const change = vi.fn(); const initial = { ...original, stop: ['初始'] };
  const view = render(<GenerationFields runtime={initial} onChange={change} />);
  fireEvent.change(screen.getByLabelText('停止序列'), { target: { value: '初始\n' } });
  view.rerender(<GenerationFields runtime={{ ...initial, stream: false, stop: ['初始'] }} onChange={change} />);
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe('初始\n');
  view.rerender(<GenerationFields runtime={{ ...initial, stop: [' 外部 ', '第二条'], context_limit: 1024 }} onChange={change} />);
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe(' 外部 \n第二条');
  expect((screen.getByLabelText('上下文总预算（词元）') as HTMLInputElement).value).toBe('1024');
  expect(change).toHaveBeenCalledTimes(1);
  view.rerender(<GenerationFields runtime={original} onChange={change} />);
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe('');
});

it.each([127, 4097, 128.5])('上下文越界 %s 显示原因并保留数值，不静默调整', value => {
  const change = vi.fn(); render(<Fields onChange={change} />);
  fireEvent.change(screen.getByLabelText('上下文总预算（词元）'), { target: { value: String(value) } });
  expect(change.mock.calls.at(-1)?.[0].context_limit).toBe(value);
  expect((screen.getByLabelText('上下文总预算（词元）') as HTMLInputElement).value).toBe(String(value));
  expect(screen.getByRole('alert').textContent).toContain('128—4096');
});

it.each([128, 4096])('上下文合法边界 %s 正确传递', value => {
  const change = vi.fn(); render(<Fields initial={{ ...original, context_limit: 256 }} onChange={change} />);
  fireEvent.change(screen.getByLabelText('上下文总预算（词元）'), { target: { value: String(value) } });
  expect(change.mock.calls.at(-1)?.[0].context_limit).toBe(value);
  expect(screen.queryByRole('alert')).toBeNull();
});

it.each([
  [Array.from({ length: 9 }, (_, index) => String(index)).join('\n'), '最多 8 条'],
  ['🙂'.repeat(129), '1—128 个字符'], ['END\nEND', '不能重复'], ['包含\u0000控制', '不能包含控制字符'],
])('停止词不合法时保留全部输入并说明原因', (value, message) => {
  const change = vi.fn(); render(<Fields onChange={change} />);
  fireEvent.change(screen.getByLabelText('停止序列'), { target: { value } });
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe(value);
  expect(change.mock.calls.at(-1)?.[0].stop).toEqual(value.split('\n'));
  expect(screen.getByRole('alert').textContent).toContain(message);
});

it('停止词按 Unicode 字符计数，128 个表情合法；清空后传空数组', () => {
  const change = vi.fn(); render(<Fields onChange={change} />);
  fireEvent.change(screen.getByLabelText('停止序列'), { target: { value: '🙂'.repeat(128) } });
  expect(screen.queryByRole('alert')).toBeNull();
  fireEvent.change(screen.getByLabelText('停止序列'), { target: { value: '\n\n' } });
  expect(change.mock.calls.at(-1)?.[0].stop).toEqual([]);
  expect((screen.getByLabelText('停止序列') as HTMLTextAreaElement).value).toBe('\n\n');
});

it('流式开关传递严格布尔值，并保留所有其他运行参数', () => {
  const initial = { ...original, context_limit: 1024, stop: [' 完成 '], overflow: 'reject' as const, thinking: 'default' as const };
  const change = vi.fn(); render(<Fields initial={initial} onChange={change} />);
  fireEvent.click(screen.getByLabelText('流式显示输出')); expect(change.mock.calls.at(-1)?.[0]).toEqual({ ...initial, stream: false });
  fireEvent.click(screen.getByLabelText('流式显示输出')); expect(change.mock.calls.at(-1)?.[0]).toEqual({ ...initial, stream: true });
});

it('忙碌时所有可编辑字段禁用', () => {
  render(<GenerationFields runtime={original} disabled onChange={vi.fn()} />);
  for (const label of ['上下文总预算（词元）', '停止序列', '流式显示输出']) expect((screen.getByLabelText(label) as HTMLInputElement).disabled).toBe(true);
});

it.each(['context', 'stop', 'stream', 'preset'])('真实工作台 %s 修改清除旧检查，保存本次字段后才重新检查', async action => {
  let task: Task = { id: 'generation-task', project_id: 'project-test', name: '文本参数验证', kind: 'text', operation: 'generate', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: 'model-test', dataset_id: null, input: { prompt: '保留原始输入' }, runtime: { ...original } } };
  const calls: { path: string; body: any }[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = String(url); const body = init.body ? JSON.parse(String(init.body)) : {}; calls.push({ path, body });
    if (path.includes('/execution-targets?')) return { ok: true, json: async () => ({ items: [] }) };
    if (path.endsWith('/draft')) { task = { ...task, draft: body.draft, draft_revision: task.draft_revision + 1 }; return { ok: true, json: async () => task }; }
    return { ok: true, json: async () => ({ preflight_id: 'preflight-test', can_submit: true, blocking: [], warnings: [] }) };
  }));
  render(<Workbench task={task} models={[{ id: 'model-test', name: '测试模型', format: 'safetensors', modality: 'text' }]} datasets={[]} devices={[]} onBack={() => {}} registerLeave={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await screen.findByRole('button', { name: '开始运行' });
  if (action === 'context') fireEvent.change(screen.getByLabelText('上下文总预算（词元）'), { target: { value: '1024' } });
  if (action === 'stop') fireEvent.change(screen.getByLabelText('停止序列'), { target: { value: ' 完成 \nEND\n' } });
  if (action === 'stream') fireEvent.click(screen.getByLabelText('流式显示输出'));
  if (action === 'preset') {
    fireEvent.change(screen.getByLabelText('运行预设'), { target: { value: 'low_memory_v2' } });
    fireEvent.click(screen.getByRole('button', { name: '预览预设差异' })); fireEvent.click(screen.getByRole('button', { name: '应用到草稿' }));
  }
  expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await screen.findByRole('button', { name: '开始运行' });
  expect(task.draft.input.prompt).toBe('保留原始输入');
  expect(task.draft.runtime).toMatchObject(action === 'context' ? { context_limit: 1024 } : action === 'stop' ? { stop: [' 完成 ', 'END'] } : action === 'stream' ? { stream: false } : { kv_precision: 'auto', prefill_step_size: 512 });
  expect(calls.filter(call => !call.path.includes('/execution-targets?')).map(call => call.path.split('/').at(-1))).toEqual(['preflight', 'draft', 'preflight']);
  expect(calls.at(-1)?.body.draft_revision).toBe(2);
});

it('训练任务不混入文本生成设置', () => {
  const task: Task = { id: 'training-task', project_id: 'project-test', name: '训练参数验证', kind: 'text', operation: 'train', draft_revision: 1, draft: { kind: 'text', operation: 'train', model_id: null, dataset_id: null, input: {}, runtime: { ...defaultTrainingRuntime } } };
  render(<Workbench task={task} models={[]} datasets={[]} devices={[]} onBack={() => {}} registerLeave={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
  expect(screen.queryByLabelText('停止序列')).toBeNull(); expect(screen.queryByLabelText('流式显示输出')).toBeNull();
});
