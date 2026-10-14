import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AIAssistance } from '../../apps/desktop/src/AIAssistance';
import type { Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const model = { id: 'model-qwen', name: '本机 Qwen2.5-0.5B', format: 'safetensors', modality: 'text' as const };
const target: Task = { id: 'target-task', project_id: 'project-a', name: '目标生成草稿', kind: 'text', operation: 'generate', draft_revision: 2, draft: { kind: 'text', operation: 'generate', model_id: model.id, dataset_id: null, input: { prompt: '说明模型的适用范围。' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', seed: 0, max_tokens: 128 } } };
const request = { id: 'request-a', target_task_id: target.id, target_revision: 2, generation_task_id: 'suggestion-task', model_id: model.id, status: 'awaiting_generation', proposal_id: null, context: { instruction: '把输出调为 64。', sent_scope: '只发送问题与表单字段', long_prompt_scope: '长提示词仅发送摘要', allowed_fields: { 'runtime.max_tokens': { current: 128 } } }, connection: { type: 'local_process', engine: 'mlx', model_name: model.name, network: false }, parse_failures: [] };
const proposal = { id: 'proposal-a', target_id: target.id, expected_revision: 2, title: '缩短首次输出', changes: [{ field: 'runtime.max_tokens', from: 128, to: 64, reason: '先验证生成流程。', impact: '输出可能提前结束。' }], status: 'proposed', source_attempt_id: 'suggestion-run', source_artifact_id: 'raw-answer', raw_sha256: 'a'.repeat(64), requires_preflight: true, execution_actions: [], application: null };
const appliedTask = { ...target, draft_revision: 3, draft: { ...target.draft, runtime: { ...target.draft.runtime, max_tokens: 64 } } };
let calls: { path: string; method: string; body: any; key?: string }[];
let mode: 'success' | 'invalid' | 'conflict' | 'running';
let failGenerateOnce: boolean;
let failParseOnce: boolean;
let storedProposal: typeof proposal | null;

beforeEach(() => {
  calls = []; mode = 'success'; failGenerateOnce = false; failParseOnce = false; storedProposal = null;
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let result: any = {}; let ok = true;
    if (path.startsWith('/ai/requests?')) result = { items: [] };
    else if (path === '/ai/requests') result = request;
    else if (path === '/tasks/suggestion-task/preflight') result = { preflight_id: 'check-suggestion', can_submit: true, blocking: [], warnings: [] };
    else if (path === '/tasks/suggestion-task/attempts') {
      if (failGenerateOnce) { failGenerateOnce = false; throw new Error('提交回执暂时不可用'); }
      result = { id: 'suggestion-run', state: 'queued', state_version: 1, task_id: 'suggestion-task' };
    } else if (path === '/attempts/suggestion-run') result = { id: 'suggestion-run', state: mode === 'running' ? 'running' : 'succeeded', state_version: 4, task_id: 'suggestion-task', compute_outcome: 'succeeded', collection_state: 'succeeded', output_text: mode === 'invalid' ? '模型回答不是 JSON。' : JSON.stringify(proposal), allowed_actions: ['cancel'] };
    else if (path === '/ai/requests/request-a/proposals') {
      if (mode === 'invalid') { ok = false; result = { error: { code: 'AI_RESPONSE_NOT_STRUCTURED', message: '模型回答无法解析；原回答已保留，没有替代建议。' } }; }
      else {
        storedProposal ||= proposal;
        if (failParseOnce) { failParseOnce = false; throw new Error('建议已经保存，但解析回执暂时不可用'); }
        result = storedProposal;
      }
    } else if (path === '/ai/proposals/proposal-a/apply') {
      if (mode === 'conflict') { ok = false; result = { error: { code: 'REVISION_CONFLICT', message: '草稿已更新，未覆盖后续内容。' } }; }
      else result = { proposal: { ...proposal, status: 'applied', application: { to_revision: 3 } }, task: appliedTask, execution_actions: [], requires_preflight: true };
    } else if (path === '/ai/proposals/proposal-a/undo') result = { proposal: { ...proposal, status: 'undone', application: { to_revision: 3 } }, task: { ...target, draft_revision: 4 }, execution_actions: [], requires_preflight: true };
    else if (path === '/attempts/suggestion-run/cancel') result = { id: 'suggestion-run', task_id: 'suggestion-task', state: 'cancelled', state_version: 5, compute_outcome: 'cancelled', collection_state: 'not_started' };
    return { ok, json: async () => result };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function prepare() {
  await waitFor(() => expect(calls.some(call => call.path.startsWith('/ai/requests?'))).toBe(true));
  fireEvent.change(screen.getByLabelText('建议问题'), { target: { value: '把输出调为 64。' } });
  fireEvent.click(screen.getByRole('button', { name: '检查建议请求' }));
  await screen.findByRole('button', { name: '生成建议（本机）' });
}
async function generate() {
  await prepare(); fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
  await screen.findByRole('button', { name: '应用这些字段' });
}

describe('真实模型建议的人工控制界面', () => {
  it('重开已执行任务的历史建议时只说明应用结果，不误报任务尚未执行', async () => {
    const normal = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const path = String(input).replace('/api/v1', '');
      if (path.startsWith('/ai/requests?')) return { ok: true, json: async () => ({ items: [{ ...request, proposal_id: proposal.id, status: 'applied' }] }) } as Response;
      if (path === '/ai/proposals/proposal-a') return { ok: true, json: async () => ({ ...proposal, status: 'applied', application: { to_revision: 3 } }) } as Response;
      if (path.startsWith('/attempts?task_id=')) return { ok: true, json: async () => ({ items: [{ id: 'suggestion-run', task_id: 'suggestion-task', state: 'succeeded' }] }) } as Response;
      return normal(input, init);
    });
    render(<AIAssistance task={{ ...appliedTask, latest_attempt: { id: 'actual-target-run', task_id: target.id, project_id: target.project_id, state: 'succeeded', state_version: 4 } }} models={[model]} onTaskChanged={() => {}} />);
    await screen.findByText('建议字段已应用到草稿。请在任务记录中查看实际运行状态。');
    expect(screen.queryByText(/任务尚未执行/)).toBeNull();
    expect(calls.some(call => call.method === 'POST')).toBe(false);
  });

  it('检查与明确生成分开，结构化预览后才应用和撤销，不提交目标任务', async () => {
    const changed = vi.fn(); render(<AIAssistance task={target} models={[model]} onTaskChanged={changed} />);
    await prepare();
    expect(screen.getByText('检查通过，尚未调用建议模型')).toBeTruthy();
    expect(screen.getByText(/实际发送范围/)).toBeTruthy();
    expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/ai/requests', '/tasks/suggestion-task/preflight']);
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
    await screen.findByRole('button', { name: '应用这些字段' });
    expect(screen.getByRole('cell', { name: '128' })).toBeTruthy(); expect(screen.getByRole('cell', { name: '64' })).toBeTruthy();
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '应用这些字段' }));
    await screen.findByRole('button', { name: '撤销本次应用' });
    expect(changed).toHaveBeenLastCalledWith(appliedTask);
    fireEvent.click(screen.getByRole('button', { name: '撤销本次应用' }));
    await screen.findByText('已撤销本次建议，恢复原字段值。');
    expect(changed).toHaveBeenLastCalledWith({ ...target, draft_revision: 4 });
    expect(calls.find(call => call.path.endsWith('/undo'))?.body).toEqual({ expected_revision: 3 });
    expect(calls.some(call => call.path === '/tasks/target-task/attempts' || call.path.includes('register') || call.path.includes('exports'))).toBe(false);
    expect(calls.filter(call => ['/ai/requests', '/tasks/suggestion-task/attempts', '/ai/proposals/proposal-a/apply', '/ai/proposals/proposal-a/undo'].includes(call.path)).every(call => call.key)).toBe(true);
  });

  it('解析失败展示原回答与明确错误，未生成假建议或自动应用', async () => {
    mode = 'invalid'; const changed = vi.fn(); render(<AIAssistance task={target} models={[model]} onTaskChanged={changed} />);
    await prepare(); fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
    await screen.findByText('模型回答无法解析；原回答已保留，没有替代建议。');
    expect(screen.getByLabelText('建议模型原始回答').textContent).toBe('模型回答不是 JSON。');
    expect(screen.queryByRole('button', { name: '应用这些字段' })).toBeNull(); expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '重新读取这次建议' }));
    await screen.findByText('模型回答无法解析；原回答已保留，没有替代建议。');
    const parsed = calls.filter(call => call.path === '/ai/requests/request-a/proposals');
    expect(parsed).toHaveLength(2); expect(parsed[0].key).toBe(parsed[1].key);
    expect(calls.filter(call => call.path === '/tasks/suggestion-task/attempts')).toHaveLength(1);
    expect(screen.queryByRole('button', { name: '应用这些字段' })).toBeNull(); expect(changed).not.toHaveBeenCalled();
  });

  it('解析已成功但回执丢失时只重读原回答，复用解析键且不再生成', async () => {
    failParseOnce = true; const changed = vi.fn(); render(<AIAssistance task={target} models={[model]} onTaskChanged={changed} />);
    await prepare(); fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
    await screen.findByText('建议已经保存，但解析回执暂时不可用');
    expect(storedProposal).toEqual(proposal); expect(screen.queryByRole('button', { name: '应用这些字段' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '重新读取这次建议' }));
    await screen.findByRole('button', { name: '应用这些字段' });
    const parsed = calls.filter(call => call.path === '/ai/requests/request-a/proposals');
    expect(parsed).toHaveLength(2); expect(parsed[0].key).toBeTruthy(); expect(parsed[0].key).toBe(parsed[1].key);
    expect(parsed.map(call => call.body)).toEqual([{ attempt_id: 'suggestion-run' }, { attempt_id: 'suggestion-run' }]);
    expect(calls.filter(call => call.path === '/tasks/suggestion-task/attempts')).toHaveLength(1);
    expect(calls.filter(call => call.path === '/ai/requests')).toHaveLength(1);
    expect(changed).not.toHaveBeenCalled(); expect(screen.queryByRole('button', { name: '重新读取这次建议' })).toBeNull();
  });

  it('服务端revision冲突保留预览，不覆盖草稿或继续提交', async () => {
    mode = 'conflict'; const changed = vi.fn(); render(<AIAssistance task={target} models={[model]} onTaskChanged={changed} />);
    await generate(); fireEvent.click(screen.getByRole('button', { name: '应用这些字段' }));
    await screen.findByText('草稿已更新，未覆盖后续内容。');
    expect(changed).not.toHaveBeenCalled(); expect(screen.getByRole('heading', { name: '缩短首次输出' })).toBeTruthy();
  });

  it('后续手动修改与未保存输入会禁用旧建议应用', async () => {
    const changed = vi.fn(); const view = render(<AIAssistance task={target} models={[model]} onTaskChanged={changed} />);
    await generate(); view.rerender(<AIAssistance task={{ ...target, draft_revision: 3 }} models={[model]} hasUnsavedChanges onTaskChanged={changed} />);
    expect((screen.getByRole('button', { name: '应用这些字段' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/当前有未保存的修改/)).toBeTruthy(); expect(changed).not.toHaveBeenCalled();
  });

  it('生成回执不明重试复用原幂等键', async () => {
    failGenerateOnce = true; render(<AIAssistance task={target} models={[model]} onTaskChanged={() => {}} />);
    await prepare(); fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
    await screen.findByText('提交回执暂时不可用');
    fireEvent.click(screen.getByRole('button', { name: '生成建议（本机）' }));
    await screen.findByRole('button', { name: '应用这些字段' });
    const submitted = calls.filter(call => call.path === '/tasks/suggestion-task/attempts'); expect(submitted).toHaveLength(2); expect(submitted[0].key).toBe(submitted[1].key);
  });

  it('媒体和检查点不显示可提交的建议请求', async () => {
    render(<AIAssistance task={{ ...target, kind: 'image' }} models={[model]} onTaskChanged={() => {}} />);
    expect(screen.queryByRole('button', { name: '检查建议请求' })).toBeNull(); expect(calls).toHaveLength(0);
  });
});
