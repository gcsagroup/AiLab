import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import Workbench, { defaultRuntime, defaultTrainingRuntime, RunResult } from '../../apps/desktop/src/Workbench';
import ImportDialog from '../../apps/desktop/src/ImportDialog';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import { collection } from '../../apps/desktop/src/api';
import type { Attempt, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));

let calls: { method: string; path: string; body: Record<string, unknown>; key?: string }[];
let task: Task;
const projectList = [{ id: 'project-a', name: '中文测试项目', revision: 1 }, { id: 'project-b', name: '第二个项目', revision: 1 }];
const models = [{ id: 'model-a', name: '本机测试模型', format: 'safetensors', modality: 'text' as const }];

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = [];
  task = { id: 'task-a', project_id: 'project-a', name: '测试试用', kind: 'text', operation: 'generate', draft_revision: 1, draft: { kind: 'text', operation: 'generate', model_id: 'model-a', dataset_id: null, input: { prompt: '原输入' }, runtime: { ...defaultRuntime } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', '');
    const method = init.method || 'GET';
    const body = init.body ? JSON.parse(String(init.body)) : {};
    calls.push({ method, path, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let response: unknown = { items: [] };
    if (path === '/projects') response = { items: projectList };
    if (path.startsWith('/models?')) response = { items: path.includes('project-b') ? [] : models };
    if (path === '/devices') response = { items: [{ id: 'apple-gpu', name: '本机 Apple GPU' }] };
    if (path === '/tasks' && method === 'POST') { task = { ...task, project_id: body.project_id, kind: body.kind, operation: body.operation, draft: { ...task.draft, kind: body.kind, operation: body.operation, runtime: body.kind === 'text' ? body.operation === 'train' ? defaultTrainingRuntime : defaultRuntime : defaultMediaRuntime(body.kind, body.operation === 'train') } }; response = task; }
    if (path.endsWith('/draft') && method === 'PATCH') { task = { ...task, draft: body.draft, draft_revision: task.draft_revision + 1 }; response = task; }
    if (path.endsWith('/preflight')) response = { preflight_id: 'check-a', task_id: task.id, draft_revision: task.draft_revision, can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime };
    if (path.endsWith('/attempts') && method === 'POST') response = { id: 'attempt-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, output_text: '持久结果', artifacts: [] };
    if (path === '/attempts/attempt-a') response = { id: 'attempt-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, output_text: '持久结果', artifacts: [] };
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function renderWorkbench(value = task, leave?: (handler: (() => Promise<boolean>) | null) => void) {
  return render(<Workbench task={value} models={models} datasets={[]} devices={[{ id: 'apple-gpu', name: '本机 Apple GPU' }]} onBack={() => {}} registerLeave={leave || (() => {})} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
}

describe('任务输入、检查与明确提交', () => {
  it('修改后先保存再检查，检查成功不会自行运行，正式按钮才创建尝试', async () => {
    renderWorkbench();
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '新的输入内容' } });
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByRole('button', { name: '开始运行' });
    expect(calls.filter(call => call.method === 'POST' && call.path.endsWith('/attempts'))).toHaveLength(0);
    const commands = calls.filter(call => call.method !== 'GET');
    expect(commands[0].path).toBe('/tasks/task-a/draft');
    expect(commands[1]).toMatchObject({ path: '/tasks/task-a/preflight', body: { draft_revision: 2 } });
    fireEvent.click(screen.getByRole('button', { name: '开始运行' }));
    await screen.findByText('持久结果');
    expect(calls.find(call => call.path.endsWith('/attempts') && call.method === 'POST')?.body).toEqual({ preflight_id: 'check-a', expected_revision: 2 });
  });
  it('更改已通过检查的输入会使旧检查失效', async () => {
    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByRole('button', { name: '开始运行' });
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '第二份输入' } });
    expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
    expect(screen.getByRole('button', { name: '检查配置' })).toBeTruthy();
  });
  it('同一配方再次检查并运行使用新提交编号，响应不明时保留原编号', async () => {
    renderWorkbench();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    fireEvent.click(await screen.findByRole('button', { name: '开始运行' }));
    await screen.findByText('持久结果');
    const firstKey = calls.find(call => call.path.endsWith('/attempts') && call.method === 'POST')?.key;
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByRole('button', { name: '开始运行' });
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const result = await normalFetch(input, init);
      if (!dropped && String(input).endsWith('/attempts') && init?.method === 'POST') { dropped = true; throw new Error('响应丢失'); }
      return result;
    });
    fireEvent.click(screen.getByRole('button', { name: '开始运行' }));
    await screen.findByText('响应丢失');
    fireEvent.click(screen.getByRole('button', { name: '开始运行' }));
    await waitFor(() => expect(screen.queryByText('响应丢失')).toBeNull());
    const keys = calls.filter(call => call.path.endsWith('/attempts') && call.method === 'POST').map(call => call.key);
    expect(keys).toHaveLength(3);
    expect(keys[1]).not.toBe(firstKey);
    expect(keys[2]).toBe(keys[1]);
  });
  it('手动保存请求未完成时锁住输入，离页等待同一次保存完成', async () => {
    let leave: (() => Promise<boolean>) | null = null;
    let finish!: (response: Response) => void;
    renderWorkbench(task, handler => { leave = handler; });
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '本次输入' } });
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(true);
    // PRD-018：正常离开须等待最后草稿保存，避免用户重复点击。
    let leaving!: Promise<boolean>; let left = false;
    await act(async () => { leaving = leave!().then(value => { left = value; return value; }); });
    expect(left).toBe(false);
    await act(async () => finish({ ok: true, json: async () => ({ ...task, draft_revision: 2, draft: { ...task.draft, input: { prompt: '本次输入' } } }) } as Response));
    expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('本次输入');
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false);
    expect(await leaving).toBe(true);
  });
  it('显示训练检查中可训练与排除样本，允许检查通过但不隐藏数据损失', async () => {
    renderWorkbench();
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ preflight_id: 'checked', can_submit: true, blocking: [], warnings: [], check_report: { input_samples: 3, accepted_samples: 2, excluded_samples: 1, supervised_tokens: 36, exclusion_counts: { SEQUENCE_TOO_LONG: 1 } } }) } as Response);
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByText('本次训练数据');
    expect(screen.getByText('3 条')).toBeTruthy();
    expect(screen.getByText('2 条')).toBeTruthy();
    expect(screen.getByText('超过最大序列长度：1 条')).toBeTruthy();
    expect(screen.getByText('36')).toBeTruthy();
  });
  it('离开任务前持久保存草稿，保存冲突会阻止离开', async () => {
    let leave: (() => Promise<boolean>) | null = null;
    renderWorkbench(task, handler => { leave = handler; });
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '尚未手动保存的输入' } });
    expect(await leave!()).toBe(true);
    expect(task.draft.input.prompt).toBe('尚未手动保存的输入');
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '冲突输入' } });
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, json: async () => ({ error: { code: 'REVISION_CONFLICT', message: '草稿已被更新' } }) } as Response);
    expect(await leave!()).toBe(false);
    await screen.findByText('草稿已被更新');
  });
  it('训练表单使用独立参数，修改训练步数不会混入生成采样字段', async () => {
    task = { ...task, operation: 'train', draft: { ...task.draft, operation: 'train', runtime: { ...defaultTrainingRuntime } } };
    renderWorkbench();
    expect(screen.queryByLabelText('最大输出 token')).toBeNull();
    fireEvent.change(screen.getByLabelText('训练步数'), { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
    await waitFor(() => expect(task.draft.runtime.steps).toBe(8));
    expect(task.draft.runtime).not.toHaveProperty('max_tokens');
    expect(task.draft.runtime).not.toHaveProperty('temperature');
  });
});

describe('普通用户入口与项目边界', () => {
  it('在已选择的图片类别直接试用，创建图片任务并进入对应表单', async () => {
    render(<App />);
    await screen.findByText('模型训练与运行', { selector: 'h1' });
    fireEvent.click(screen.getByRole('button', { name: /图片训练 \/ 微调/ }));
    await waitFor(() => expect((screen.getByRole('button', { name: '直接试用' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '直接试用' }));
    await screen.findByLabelText('画面描述');
    expect(calls.find(call => call.path === '/tasks' && call.method === 'POST')?.body.kind).toBe('image');
    expect(screen.queryByLabelText('输入内容')).toBeNull();
  });
  it('切换项目先保存旧草稿，新项目不保留旧模型和任务页面', async () => {
    render(<App />);
    await screen.findByRole('button', { name: '直接试用' });
    fireEvent.click(screen.getByRole('button', { name: '直接试用' }));
    await screen.findByLabelText('输入内容');
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '项目A的私有草稿' } });
    fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
    await waitFor(() => expect(screen.queryByLabelText('输入内容')).toBeNull());
    expect(task.draft.input.prompt).toBe('项目A的私有草稿');
    expect(screen.queryByText('本机测试模型')).toBeNull();
  });
  it('列表只读当前页，明确提供游标后才读取下一页，重复游标报错', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'a' }], next_cursor: 'a' }) } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [{ id: 'b' }], next_cursor: null }) } as Response);
    expect(await collection('/models')).toEqual({ items: [{ id: 'a' }], next_cursor: 'a' });
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1);
    expect(await collection('/models', 'a')).toEqual({ items: [{ id: 'b' }], next_cursor: null });
    vi.mocked(fetch).mockResolvedValue({ ok: true, json: async () => ({ items: [{ id: 'a' }], next_cursor: 'a' }) } as Response);
    await expect(collection('/models', 'a')).rejects.toThrow('列表游标重复');
  });
  it('创建任务期间切换项目，迟到响应不会把旧项目任务放进新项目', async () => {
    render(<App />);
    await screen.findByRole('button', { name: '直接试用' });
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    let finish!: (response: Response) => void;
    vi.mocked(fetch).mockImplementation(async (input, init) => String(input) === '/api/v1/tasks' && init?.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : normalFetch(input, init));
    await waitFor(() => expect((screen.getByRole('button', { name: '直接试用' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '直接试用' }));
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
    await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b'));
    await act(async () => finish({ ok: true, json: async () => task } as Response));
    expect(screen.queryByLabelText('输入内容')).toBeNull();
  });
  it('新建项目成功后立即清空旧资源，不等待新项目慢列表', async () => {
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    const created = { id: 'project-new', name: '全新媒体项目', revision: 1 };
    let wasCreated = false;
    let finishModels!: (response: Response) => void;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/projects') {
        if (init?.method === 'POST') { wasCreated = true; return { ok: true, json: async () => created } as Response; }
        return { ok: true, json: async () => ({ items: wasCreated ? [...projectList, created] : projectList }) } as Response;
      }
      if (String(input).startsWith('/api/v1/models?project_id=project-new')) return new Promise(resolve => { finishModels = resolve; });
      return normalFetch(input, init);
    });
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: '模型库' }));
    await screen.findByText('本机测试模型');
    fireEvent.click(screen.getByRole('button', { name: '新建项目' }));
    fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: created.name } });
    fireEvent.click(screen.getByRole('button', { name: '创建项目' }));
    await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(created.id));
    fireEvent.click(screen.getByRole('button', { name: '模型库' }));
    expect(screen.queryByText('本机测试模型')).toBeNull();
    await act(async () => finishModels({ ok: true, json: async () => ({ items: [] }) } as Response));
  });
  it('新建项目后旧项目创建任务的迟到响应不能重新打开旧任务', async () => {
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    const created = { id: 'project-new', name: '新项目隔离迟到任务', revision: 1 };
    let wasCreated = false;
    let finishTask!: (response: Response) => void;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input) === '/api/v1/projects') {
        if (init?.method === 'POST') { wasCreated = true; return { ok: true, json: async () => created } as Response; }
        return { ok: true, json: async () => ({ items: wasCreated ? [...projectList, created] : projectList }) } as Response;
      }
      if (String(input) === '/api/v1/tasks' && init?.method === 'POST') return new Promise(resolve => { finishTask = resolve; });
      return normalFetch(input, init);
    });
    render(<App />);
    await screen.findByRole('button', { name: '直接试用' });
    await waitFor(() => expect((screen.getByRole('button', { name: '直接试用' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '直接试用' }));
    await waitFor(() => expect(finishTask).toBeTypeOf('function'));
    fireEvent.click(screen.getByRole('button', { name: '新建项目' }));
    fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: created.name } });
    fireEvent.click(screen.getByRole('button', { name: '创建项目' }));
    await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe(created.id));
    await act(async () => finishTask({ ok: true, json: async () => task } as Response));
    expect(screen.queryByLabelText('输入内容')).toBeNull();
  });
});

describe('作品与导入重试', () => {
  it('图片训练显示执行桥真实 completed_steps 与损失事件', async () => {
    const attempt: Attempt = { id: 'attempt-image', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 4, snapshot: { kind: 'image', operation: 'train' }, last_event_sequence: 1, artifacts: [] };
    vi.mocked(fetch).mockImplementation(async input => ({ ok: true, json: async () => String(input).includes('/events?') ? { items: [{ sequence: 1, type: 'metric', payload: { completed_steps: 12, total_steps: 12, loss: 0.12567, grad_norm: 0.02 } }] } : attempt } as Response));
    render(<RunResult initial={attempt} onChanged={() => {}} />);
    const metrics = await screen.findByLabelText('训练指标');
    expect(metrics.textContent).toContain('12 / 12');
    expect(metrics.textContent).toContain('0.12567');
    expect(metrics.textContent).not.toContain('undefined');
  });
  it('生成速度指标不会被显示为训练损失或未定义训练步数', async () => {
    const attempt: Attempt = { id: 'attempt-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, last_event_sequence: 1, output_text: '生成正文', artifacts: [] };
    vi.mocked(fetch).mockImplementation(async (input) => ({ ok: true, json: async () => String(input).includes('/events?') ? { items: [{ sequence: 1, type: 'metric', payload: { generation_tokens: 20, generation_tps: 80 } }] } : attempt } as Response));
    render(<RunResult initial={attempt} onChanged={() => {}} />);
    await screen.findByText('生成正文');
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.queryByLabelText('训练指标')).toBeNull();
    expect(screen.queryByText(/undefined/)).toBeNull();
  });
  it('保存文本作品选择实际结果文件，不选择排在前面的配置JSON', async () => {
    const attempt: Attempt = { id: 'attempt-a', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 1, snapshot: { operation: 'generate' }, output_text: '作品正文', artifacts: [{ id: 'config', name: 'effective-config.json', media_type: 'application/json' }, { id: 'result', name: 'result.txt', media_type: 'text/plain' }] };
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((input, init) => String(input) === '/api/v1/attempts/attempt-a' ? Promise.resolve({ ok: true, json: async () => attempt } as Response) : normalFetch(input, init));
    render(<RunResult initial={attempt} onChanged={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '保存作品' }));
    await screen.findByRole('button', { name: '已保存作品' });
    expect(calls.find(call => call.path === '/works')?.body.artifact_id).toBe('result');
  });
  it('导入响应丢失后重试使用同一编号，避免生成重复资产', async () => {
    const imported = vi.fn();
    render(<ImportDialog kind="model" projectId="project-a" onClose={() => {}} onImported={imported} />);
    fireEvent.change(screen.getByLabelText('模型文件路径'), { target: { value: '/models/example' } });
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ id: 'plan-a', can_import: true, manifest_digest: 'abc', issues: [], trust_class: 'restricted_weights', loader: 'mlx_lm.local_restricted', execution_boundary: { scope_semantics: 'loader_policy_not_os_permissions', process: 'separate_process', os_sandbox: false, filesystem: 'current_user_permissions', network: 'offline_loader_options_not_os_block', credentials: 'environment_allowlist_not_filesystem_denial', custom_code: 'not_supported' } }) } as Response);
    fireEvent.click(screen.getByRole('button', { name: '检查模型' }));
    await screen.findByRole('button', { name: '确认导入' });
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await normalFetch(input, init); if (!dropped) { dropped = true; throw new Error('导入响应丢失'); } return result; });
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));
    await screen.findByText('导入响应丢失');
    fireEvent.click(screen.getByRole('button', { name: '确认导入' }));
    await waitFor(() => expect(imported).toHaveBeenCalledOnce());
    const keys = calls.filter(call => call.path === '/models/imports').map(call => call.key);
    expect(keys).toHaveLength(2); expect(keys[0]).toBeTruthy(); expect(keys[1]).toBe(keys[0]);
  });
});
