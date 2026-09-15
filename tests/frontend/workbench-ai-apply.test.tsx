import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Workbench, { defaultRuntime } from '../../apps/desktop/src/Workbench';
import type { Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const model = { id: 'qwen-fixture', name: '本机建议模型', format: 'safetensors', modality: 'text' as const };
const response = (value: unknown, ok = true): Response => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; }
let task: Task;
let proposal: Record<string, unknown>;
let restoredProposal: boolean;
let actionReply: Promise<Response> | undefined;
let writes: { path: string; method: string; body: any }[];
let leave: (() => Promise<boolean>) | null;
let panel: HTMLDivElement;
const changed = vi.fn();

const request = () => ({ id: 'request-fixture', target_task_id: task.id, target_revision: 7, generation_task_id: 'suggestion-task', model_id: model.id, status: 'awaiting_generation', proposal_id: restoredProposal ? 'proposal-fixture' : null, context: { instruction: '缩短首次输出。', sent_scope: '仅问题和当前草稿字段', long_prompt_scope: '长正文仅发送摘要', allowed_fields: { 'runtime.max_tokens': { current: 128 } } }, connection: { type: 'local_process', engine: 'mlx', model_name: model.name, network: false }, parse_failures: [] });
beforeEach(() => {
  restoredProposal = true; actionReply = undefined; writes = []; leave = null; changed.mockClear(); panel = document.createElement('div'); document.body.append(panel);
  task = { id: 'ai-target', project_id: 'project-a', name: '建议与草稿互斥验证', kind: 'text', operation: 'generate', draft_revision: 7, draft: { kind: 'text', operation: 'generate', model_id: model.id, dataset_id: null, input: { prompt: '保留当前输入' }, runtime: { ...defaultRuntime } } };
  proposal = { id: 'proposal-fixture', target_id: task.id, expected_revision: 7, title: '缩短首次输出', changes: [{ field: 'runtime.max_tokens', from: 128, to: 64, reason: '先检查输出。', impact: '输出可能更短。' }], status: 'proposed', source_attempt_id: 'suggestion-run', source_artifact_id: 'answer-json', raw_sha256: 'b'.repeat(64), requires_preflight: true, execution_actions: [], application: null };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = String(input).replace('/api/v1', ''); const method = options.method || 'GET';
    const body = options.body ? JSON.parse(String(options.body)) : undefined;
    if (method !== 'GET') writes.push({ path, method, body });
    if (path.startsWith('/ai/requests?')) return response({ items: restoredProposal ? [request()] : [] });
    if (path === '/ai/proposals/proposal-fixture') return response(proposal);
    if (path === '/ai/requests' && method === 'POST') return response(request());
    if (path === '/tasks/suggestion-task/preflight') return response({ preflight_id: 'ai-check', can_submit: true, blocking: [], warnings: [] });
    if (path === '/tasks/suggestion-task/attempts') return response({ id: 'suggestion-run', task_id: 'suggestion-task', state: 'queued', state_version: 1 });
    if (path === '/attempts/suggestion-run') return response({ id: 'suggestion-run', task_id: 'suggestion-task', state: 'running', state_version: 2, allowed_actions: [] });
    if (path.endsWith('/apply') || path.endsWith('/undo')) return actionReply || response({ error: { code: 'UNEXPECTED_ACTION', message: '未准备建议写回' } }, false);
    if (path === '/tasks/ai-target/draft' && method === 'PATCH') {
      if (body.expected_revision !== task.draft_revision) return response({ error: { code: 'REVISION_CONFLICT', message: '草稿版本冲突' } }, false);
      task = { ...task, draft_revision: task.draft_revision + 1, draft: structuredClone(body.draft) }; return response(task);
    }
    if (method !== 'GET') throw new Error(`意外写操作：${method} ${path}`);
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); panel.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function mount() { return render(<Workbench task={task} models={[model]} datasets={[]} devices={[]} aiPanelTarget={panel} onBack={() => {}} registerLeave={handler => { leave = handler; }} onTaskChanged={changed} onImport={() => {}} onUpdated={() => {}} />); }
function prepareUndo() { task = { ...task, draft_revision: 8, draft: { ...task.draft, runtime: { ...task.draft.runtime, max_tokens: 64 } } }; proposal = { ...proposal, status: 'applied', application: { to_revision: 8 } }; }
const input = () => screen.getByLabelText('输入内容') as HTMLTextAreaElement;
const patches = () => writes.filter(call => call.method === 'PATCH');

it.each(['apply', 'undo'])('真实建议%s在途时禁用表单并拒绝离开，回执后新输入按最新revision自动保存', async action => {
  if (action === 'undo') prepareUndo();
  const pending = deferred<Response>(); actionReply = pending.promise; const user = userEvent.setup(); const originalRevision = task.draft_revision; mount();
  fireEvent.click(await screen.findByRole('button', { name: action === 'apply' ? '应用这些字段' : '撤销本次应用' }));
  expect(input().matches(':disabled')).toBe(true);
  await user.type(input(), '不应写入'); expect(input().value).toBe('保留当前输入');
  await act(async () => { expect(await leave!()).toBe(false); }); expect(patches()).toHaveLength(0);
  task = { ...task, draft_revision: originalRevision + 1, draft: { ...task.draft, runtime: { ...task.draft.runtime, max_tokens: action === 'apply' ? 64 : 128 } } };
  await act(async () => pending.resolve(response({ proposal: { ...proposal, status: action === 'apply' ? 'applied' : 'undone', application: { to_revision: task.draft_revision } }, task, requires_preflight: true, execution_actions: [] })));
  await waitFor(() => expect(input().matches(':disabled')).toBe(false)); expect(changed).toHaveBeenLastCalledWith(task);
  fireEvent.change(input(), { target: { value: '接纳回执后的新输入' } });
  await waitFor(() => expect(patches()).toHaveLength(1)); expect(patches()[0].body.expected_revision).toBe(originalRevision + 1);
  expect(task.draft.input.prompt).toBe('接纳回执后的新输入'); expect(task.draft.runtime.max_tokens).toBe(action === 'apply' ? 64 : 128);
  expect(writes.some(call => /\/tasks\/ai-target\/(preflight|attempts)$/.test(call.path))).toBe(false);
});

it.each(['apply', 'undo'])('真实建议%s失败后释放表单和离开保护，保留原版本供后续自动保存', async action => {
  if (action === 'undo') prepareUndo();
  const pending = deferred<Response>(); actionReply = pending.promise; const originalRevision = task.draft_revision; mount();
  fireEvent.click(await screen.findByRole('button', { name: action === 'apply' ? '应用这些字段' : '撤销本次应用' })); expect(input().matches(':disabled')).toBe(true);
  await act(async () => pending.resolve(response({ error: { code: 'TEMPORARY_FAILURE', message: '建议写回暂时失败' } }, false)));
  await screen.findByText('建议写回暂时失败'); expect(input().matches(':disabled')).toBe(false); expect(changed).not.toHaveBeenCalled();
  await act(async () => { expect(await leave!()).toBe(true); });
  fireEvent.change(input(), { target: { value: '失败后仍能编辑' } }); await waitFor(() => expect(patches()).toHaveLength(1));
  expect(patches()[0].body.expected_revision).toBe(originalRevision); expect(task.draft.input.prompt).toBe('失败后仍能编辑');
});

it('真实建议生成期间仍允许编辑目标草稿，不把模型生成当作应用互斥', async () => {
  restoredProposal = false; mount();
  fireEvent.change(await screen.findByLabelText('建议问题'), { target: { value: '缩短首次输出' } }); fireEvent.click(screen.getByRole('button', { name: '检查建议请求' }));
  fireEvent.click(await screen.findByRole('button', { name: '生成建议（本机）' })); await screen.findByText('建议模型：运行中');
  expect(input().matches(':disabled')).toBe(false); fireEvent.change(input(), { target: { value: '建议生成时的新输入' } });
  await waitFor(() => expect(patches()).toHaveLength(1)); expect(task.draft.input.prompt).toBe('建议生成时的新输入'); expect(patches()[0].body.expected_revision).toBe(7);
  expect(writes.some(call => call.path.endsWith('/apply') || call.path.endsWith('/undo'))).toBe(false);
});
