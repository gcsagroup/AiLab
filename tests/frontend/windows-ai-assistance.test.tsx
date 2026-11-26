import React, { StrictMode, useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { WindowsAIAssistance } from '../../apps/desktop/src/WindowsAIAssistance';
import { windowsWorkbenchApi as api } from '../../apps/desktop/src/windowsWorkbenchApi';
import type { Model, Task } from '../../apps/desktop/src/types';

vi.mock('../../apps/desktop/src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../../apps/desktop/src/api')>(),
  api: (...args: Parameters<typeof api>) => api(...args),
}));

const language: Model = { id: 'qwen-q4', name: 'Qwen Q4_K_M', format: 'gguf', modality: 'text', execution_available: true };
const models: Model[] = [
  { ...language, id: 'other', name: '另一个语言模型' }, language,
  { ...language, id: 'image', modality: 'image' }, { ...language, id: 'embed', pipeline: 'llama-embedding' },
  { ...language, id: 'missing', execution_available: false },
];
let target: Task, checked: Task, answer: string;
type NativeRequest = { method: string; path: string; task?: Task; idempotencyKey?: string };
beforeEach(async () => {
  localStorage.clear();
  answer = JSON.stringify({ advice: '缩短回答', changes: [{field: 'runtime.max_tokens', to: '64', reason: '限制输出长度'}] });
  vi.stubGlobal('ailabHF', { request: async (_action: string, {method, path, task}: NativeRequest) => {
    let data;
    if (path.endsWith('/preflight')) {
      checked = task!;
      data = {preflight_id: 'plan', can_submit: true, blocking: [], warnings: []};
    } else if (method === 'POST' && path.endsWith('/attempts')) data = {id: 'attempt-1', state: 'queued'};
    else if (path.startsWith('/attempts/attempt-1')) data = {id: 'attempt-1', state: 'succeeded', output_text: answer};
    else if (method === 'GET' && (path.startsWith('/attempts?') || path.startsWith('/workflow-tasks?'))) data = {items: []};
    else throw Error('Unexpected native request ' + path);
    return {ok: true, data: {handled: true, data}};
  }});
  target = await api<Task>('POST', '/tasks', {project_id: 'project-ui-preview', name: '测试任务', kind: 'text', operation: 'generate'});
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Panel() {
  const [task, setTask] = useState(target);
  return <WindowsAIAssistance task={task} models={models} hasUnsavedChanges={false} taskBusy={false}
    onTaskChanged={setTask} onApplyingChange={() => {}} />;
}
async function generate() {
  render(<StrictMode><Panel /></StrictMode>);
  const select = screen.getByRole('combobox', {name: '本地建议模型'}) as HTMLSelectElement;
  expect([...select.options].map(option => option.value)).toEqual(['other', 'qwen-q4']);
  fireEvent.change(select, {target: {value: language.id}});
  fireEvent.change(screen.getByLabelText('建议问题'), {target: {value: '缩短回答'}});
  fireEvent.click(screen.getByRole('button', {name: '检查建议请求'}));
  fireEvent.click(await screen.findByRole('button', {name: '生成建议（本机）'}));
  await screen.findByRole('region', {name: '建议变更预览'});
}
const current = () => api<Task>('GET', '/tasks/' + target.id);

it('uses the selected GGUF in a separate local run and only writes confirmed changes', async () => {
  await generate();
  expect(checked.id).not.toBe(target.id);
  expect(checked.draft.model_id).toBe(language.id);
  expect(checked.draft.runtime).toMatchObject({engine: 'ailab-gguf', device_id: 'cpu'});
  expect((await current()).draft).toEqual(target.draft);
  const tasks = await api<{items: Task[]}>('GET', '/tasks?project_id=' + target.project_id);
  expect(tasks.items.map(task => task.id)).not.toContain(checked.id);
  fireEvent.click(screen.getByRole('button', {name: '应用这些字段'}));
  const undo = await screen.findByRole('button', {name: '撤销本次应用'});
  expect((await current()).draft.runtime.max_tokens).toBe(64);
  fireEvent.click(undo);
  await screen.findByRole('button', {name: '应用这些字段'});
  expect((await current()).draft).toEqual(target.draft);
});

it('refuses to apply a suggestion after an independent edit to the target', async () => {
  await generate();
  const edited = {...target.draft, input: {prompt: '后续输入'}};
  await api('PATCH', '/tasks/' + target.id + '/draft', {expected_revision: target.draft_revision, draft: edited});
  fireEvent.click(screen.getByRole('button', {name: '应用这些字段'}));
  await screen.findByText('任务草稿已改变，请重新生成建议。');
  expect((await current()).draft).toEqual(edited);
});

it.each([
  ['直接用中文回答即可。', '直接用中文回答即可。'],
  [JSON.stringify({advice:'范围不符', changes:[{field:'runtime.max_tokens', to:'9000', reason:'测试'}]}), '范围不符'],
  [JSON.stringify({advice:'类型不明', changes:[{field:'runtime.max_tokens', to:'64 tokens', reason:'测试'}]}), '类型不明'],
  [JSON.stringify({advice:'考虑更换模型', changes:[{field:'model_id', to:'unknown', reason:'测试'}]}), '考虑更换模型'],
])('renders free text or out-of-scope proposals without a write action', async (output, visible) => {
  answer = output;
  await generate();
  expect(screen.getByText(visible)).toBeTruthy();
  expect(screen.queryByRole('button', {name: '应用这些字段'})).toBeNull();
  expect((await current()).draft_revision).toBe(target.draft_revision);
});
