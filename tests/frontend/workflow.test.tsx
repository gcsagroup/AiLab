import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkflowRunView, WorkflowStartDialog, type WorkflowRun } from '../../apps/desktop/src/Workflow';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import type { Attempt, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
// 这里只隔离已有的媒体播放器与轮询合同；本文件检查真实工作流组件的状态和请求。
vi.mock('../../apps/desktop/src/Workbench', () => ({ RunResult: ({ initial }: { initial: Attempt }) => <div data-testid="run-result">{initial.id}</div> }));
const models = ['image', 'video', 'audio'].map(kind => ({ id: 'model-' + kind, name: '模型 ' + kind, modality: kind as 'image' | 'video' | 'audio', format: 'fixed', status: 'ready' }));
const imageArtifact = { id: 'artifact-' + 'a'.repeat(32), name: 'image.png', media_type: 'image/png' };
let run: WorkflowRun;
let tasks: Record<string, Task>;
let attempts: Record<string, Attempt>;
let calls: { path: string; method: string; body: any; key?: string }[];
let failAdvance: 'busy' | 'lost' | null;
let leave: (() => Promise<boolean>) | null;
function makeRun(id = 'flow-one'): WorkflowRun {
  return { id, project_id: 'project-a', name: id, revision: 1, definition_version: 'product-story-v1', current_step: 'image', status: 'active', result_id: null, history: [], steps: Object.fromEntries(['image', 'video', 'audio'].map(kind => [kind, { configuration: { model_id: 'model-' + kind, runtime: defaultMediaRuntime(kind, false), input: kind === 'video' ? {} : { prompt: kind === 'image' ? '蓝杯' : '蓝色陶瓷杯。', ...(kind === 'image' ? { negative_prompt: '模糊' } : {}) } }, input_revision: kind === 'image' ? 1 : 0, input_digest: 'input-sha', task_id: kind === 'image' ? 'task-image' : null, step_attempt_id: kind === 'image' ? 'step-image' : null, accepted: null, stale: false }])) as WorkflowRun['steps'], step_attempts: [{ id: 'step-image', mode: 'compute', attempt_id: null, source: null }] };
}
function newTask(kind: 'image' | 'video' | 'audio'): Task { return { id: 'task-' + kind, project_id: 'project-a', name: kind, kind, operation: 'generate', draft_revision: 1, immutable_draft: true, draft: { ...run.steps[kind].configuration, kind, operation: 'generate', dataset_id: null } }; }
function completeImage() {
  run.step_attempts![0].attempt_id = 'attempt-image'; run.revision += 1;
  attempts['attempt-image'] = { id: 'attempt-image', task_id: 'task-image', project_id: 'project-a', state: 'succeeded', state_version: 5, snapshot: { kind: 'image', operation: 'generate' }, artifacts: [imageArtifact] };
}
const response = (data: unknown, ok = true) => ({ ok, json: async () => structuredClone(data) }) as Response;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  run = makeRun(); tasks = { 'task-image': newTask('image') }; attempts = {}; calls = []; failAdvance = null; leave = null;
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = options?.method || 'GET'; const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ path, method, body, key: (options?.headers as Record<string, string>)?.['Idempotency-Key'] });
    if (method === 'GET' && path.startsWith('/workflow-runs/')) return response(run);
    if (method === 'GET' && path.startsWith('/tasks/')) return response(tasks[path.split('/')[2]]);
    if (method === 'GET' && path.startsWith('/attempts/')) return response(attempts[path.split('/')[2]]);
    if (path.endsWith('/preflight')) return response({ preflight_id: 'checked-image', can_submit: true, blocking: [], warnings: [], effective_config: run.steps.image.configuration.runtime });
    if (path.endsWith('/attempts')) { completeImage(); return response(attempts['attempt-image']); }
    if (path.endsWith('/advance')) {
      if (failAdvance === 'busy') return response({ error: { code: 'WORKFLOW_TARGET_BUSY', message: '视频仍在运行，请先处理。' } }, false);
      if (failAdvance === 'lost') { failAdvance = null; throw new TypeError('响应丢失'); }
      run.current_step = 'video'; run.revision += 1; run.steps.image.accepted = { step_id: 'image', step_attempt_id: 'step-image', input_revision: 1, attempt_id: 'attempt-image', artifact_id: imageArtifact.id, artifact_sha256: 'sha', work_id: 'work-image', mode: 'compute', computed: true };
      run.steps.video = { ...run.steps.video, input_revision: 1, task_id: 'task-video', step_attempt_id: 'step-video' }; run.step_attempts!.push({ id: 'step-video', mode: 'compute', attempt_id: null, source: null }); tasks['task-video'] = newTask('video');
      return response(run);
    }
    if (path.endsWith('/steps/image/input')) { run.revision += 1; run.steps.image.configuration = body.configuration; run.steps.image.input_revision += 1; run.steps.image.task_id = 'task-image-new'; run.steps.image.step_attempt_id = 'step-image-new'; run.steps.image.accepted = null; run.steps.video.stale = true; run.current_step = 'image'; tasks['task-image-new'] = { ...newTask('image'), id: 'task-image-new' }; run.step_attempts!.push({ id: 'step-image-new', mode: 'compute', attempt_id: null, source: null }); return response(run); }
    if (path === '/workflow-runs') return response(run);
    throw new Error('未声明请求 ' + method + ' ' + path);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function view(id = 'flow-one') { return render(<WorkflowRunView key={id} runId={id} models={models} works={[]} onBack={() => {}} onUpdated={() => {}} registerLeave={handler => { leave = handler; }} onExport={() => {}} />); }

it('新建工作流只建草稿，视频无伪提示词，不提交任何计算', async () => {
  const onCreated = vi.fn(); render(<WorkflowStartDialog projectId="project-a" models={models} onClose={() => {}} onCreated={onCreated} />);
  for (const [label, kind] of [['商品图片模型', 'image'], ['商品视频模型', 'video'], ['中文配音模型', 'audio']]) fireEvent.change(screen.getByLabelText(label), { target: { value: 'model-' + kind } });
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '蓝杯' } }); fireEvent.change(screen.getByLabelText('配音文案'), { target: { value: '蓝色陶瓷杯。' } });
  fireEvent.click(screen.getByRole('button', { name: '创建工作流草稿' })); await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(calls).toHaveLength(1); expect(calls[0].body.steps.video.input).toEqual({}); expect(calls[0].key).toBeTruthy();
});

it('Windows 工作流把中文视频描述和所选图生视频模型写入草稿', async () => {
  Object.defineProperty(window, 'ailabHF', { configurable: true, value: { request: vi.fn() } });
  try {
    const windowsModels = models.map(model => model.modality === 'video' ? { ...model, pipeline: 'h3-video' } : model);
    render(<WorkflowStartDialog projectId="project-a" models={windowsModels} onClose={() => {}} onCreated={() => {}} />);
    for (const [label, kind] of [['商品图片模型','image'], ['商品视频模型','video'], ['中文配音模型','audio']])
      fireEvent.change(screen.getByLabelText(label), { target: { value: 'model-' + kind } });
    for (const [label, value] of [['画面描述','白色台灯'], ['视频描述','镜头缓慢推近。'], ['配音文案','一盏台灯。']])
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole('button', {name: '创建工作流草稿'}));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.steps.video).toMatchObject({ model_id:'model-video', input:{prompt:'镜头缓慢推近。'},
      runtime:{engine:'ailab-gguf',device_id:'cpu',frames:22,fps:24} });
  } finally { delete window.ailabHF; }
});

it('检查通过仍需明确开始；每次计算绑定当前步骤任务', async () => {
  view(); fireEvent.click(await screen.findByRole('button', { name: '检查本步配置' })); await screen.findByRole('button', { name: '开始本步运行' });
  expect(calls.filter(call => call.method !== 'GET').map(call => call.path)).toEqual(['/tasks/task-image/preflight']);
  fireEvent.click(screen.getByRole('button', { name: '开始本步运行' })); await screen.findByRole('button', { name: '接受图片并带入视频' });
  expect(calls.find(call => call.path.endsWith('/attempts'))?.body).toEqual({ expected_revision: 1, preflight_id: 'checked-image' });
  expect(calls.some(call => call.path.endsWith('/advance'))).toBe(false);
});

it('目标忙时留在当前步骤，不写下一步或自动回退到旧产物', async () => {
  completeImage(); failAdvance = 'busy'; view(); fireEvent.click(await screen.findByRole('button', { name: '接受图片并带入视频' }));
  expect((await screen.findByRole('alert')).textContent).toContain('视频仍在运行');
  expect(screen.getByRole('button', { name: /1商品图片/ }).getAttribute('aria-current')).toBe('step');
  expect(calls.some(call => call.path === '/tasks/task-video')).toBe(false); expect(run.steps.image.accepted).toBeNull();
});

it('推进回执丢失时复用原 key 与原版本，不再创建一轮或改变来源', async () => {
  completeImage(); failAdvance = 'lost'; view(); fireEvent.click(await screen.findByRole('button', { name: '接受图片并带入视频' }));
  fireEvent.click(await screen.findByRole('button', { name: '重试上次操作' }));
  await screen.findByRole('heading', { name: '商品视频' });
  const requests = calls.filter(call => call.path.endsWith('/advance')); expect(requests).toHaveLength(2); expect(requests[1]).toEqual(requests[0]);
  expect(calls.filter(call => call.method !== 'GET' && !call.path.endsWith('/advance'))).toHaveLength(0);
});

it('第二轮无结果时不读上一轮成功运行', async () => {
  attempts['attempt-old'] = { id: 'attempt-old', task_id: 'old', project_id: 'project-a', state: 'succeeded', state_version: 5, artifacts: [imageArtifact] };
  run = makeRun('flow-two'); view('flow-two'); await screen.findByRole('button', { name: '检查本步配置' });
  expect(screen.queryByTestId('run-result')).toBeNull(); expect(screen.queryByRole('button', { name: '接受图片并带入视频' })).toBeNull(); expect(calls.some(call => call.path.includes('attempt-old'))).toBe(false);
});

it('修改上游输入产生新版本，原结果不作为新版本可接受结果', async () => {
  completeImage(); run.steps.video.input_revision = 1; view(); fireEvent.click(await screen.findByRole('button', { name: '修改输入 / 重做本步' }));
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '红色陶瓷杯' } });
  expect(await leave!()).toBe(false); fireEvent.click(screen.getByRole('button', { name: '保存新版本并重做' }));
  await screen.findByText('输入第 2 版'); await screen.findByRole('button', { name: '检查本步配置' });
  expect(screen.queryByTestId('run-result')).toBeNull(); expect(screen.queryByRole('button', { name: '接受图片并带入视频' })).toBeNull(); expect(screen.getByText('上游已修改 · 结果过期')).toBeTruthy();
  const request = calls.find(call => call.method === 'PATCH')!; expect(request.body.configuration).toMatchObject({ input: { prompt: '红色陶瓷杯', negative_prompt: '模糊' }, runtime: defaultMediaRuntime('image', false) }); expect(request.path.endsWith('/draft')).toBe(false);
});

it('前一页面迟到的工作流响应不能覆盖新轮次', async () => {
  let finish!: (value: Response) => void; const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const old = makeRun('flow-one'); const rendered = view(); run = makeRun('flow-two');
  rendered.rerender(<WorkflowRunView key="flow-two" runId="flow-two" models={models} works={[]} onBack={() => {}} onUpdated={() => {}} registerLeave={() => {}} onExport={() => {}} />);
  await screen.findByRole('heading', { name: 'flow-two' }); await act(async () => finish(response(old)));
  expect(screen.queryByRole('heading', { name: 'flow-one' })).toBeNull(); expect(original).toBeTruthy();
});

it.each(['CONTROL_UNAVAILABLE', 'CONTROL_RESPONSE_INVALID', 'CONTROL_RESPONSE_TOO_LARGE', 'LOCAL_BRIDGE', 'INTERNAL_ERROR'])('对象型宿主错误 %s 保留原推进命令', async code => {
  completeImage(); const original = vi.mocked(fetch).getMockImplementation()!; let failed = false;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    if (String(input).endsWith('/advance') && !failed) { failed = true; calls.push({ path: '/workflow-runs/flow-one/advance', method: 'POST', body: JSON.parse(String(options?.body)), key: (options?.headers as Record<string, string>)['Idempotency-Key'] }); return response({ error: { code, message: '写入回执未确认' } }, false); }
    return original(input, options);
  });
  view(); fireEvent.click(await screen.findByRole('button', { name: '接受图片并带入视频' })); fireEvent.click(await screen.findByRole('button', { name: '重试上次操作' })); await screen.findByRole('heading', { name: '商品视频' });
  const requests = calls.filter(call => call.path.endsWith('/advance')); expect(requests).toHaveLength(2); expect(requests[1]).toEqual(requests[0]);
});

it('原生创建回执丢失后表单冻结，重试原 body 与 key', async () => {
  let first = true; const payloads: unknown[] = []; const keys: unknown[] = []; const created = vi.fn();
  vi.mocked(fetch).mockImplementation(async (_input, options) => { payloads.push(options?.body); keys.push((options?.headers as Record<string, string>)['Idempotency-Key']); if (first) { first = false; return response({ error: { code: 'CONTROL_UNAVAILABLE', message: '未确认' } }, false); } return response(run); });
  render(<WorkflowStartDialog projectId="project-a" models={models} onClose={() => {}} onCreated={created} />);
  for (const [label, kind] of [['商品图片模型', 'image'], ['商品视频模型', 'video'], ['中文配音模型', 'audio']]) fireEvent.change(screen.getByLabelText(label), { target: { value: 'model-' + kind } });
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '蓝杯' } }); fireEvent.change(screen.getByLabelText('配音文案'), { target: { value: '蓝杯。' } }); fireEvent.click(screen.getByRole('button', { name: '创建工作流草稿' }));
  fireEvent.click(await screen.findByRole('button', { name: '重试创建并读取原工作流' })); await waitFor(() => expect(created).toHaveBeenCalledTimes(1)); expect(payloads[0]).toEqual(payloads[1]); expect(keys[0]).toBe(keys[1]);
});

it('旧作品先读取原输入，明确复用只登记来源，不自动推进', async () => {
  const oldId = 'attempt-old'; const old = { id: oldId, task_id: 'old-task', project_id: 'project-a', state: 'succeeded', state_version: 5, snapshot: { kind: 'image', model_id: 'model-image', input: { prompt: '旧红杯输入' }, runtime: defaultMediaRuntime('image', false) }, artifacts: [imageArtifact] };
  attempts[oldId] = old; const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    if (String(input).endsWith('/reuse-output')) {
      const body = JSON.parse(String(options?.body)); calls.push({ path: '/workflow-runs/flow-one/reuse-output', method: 'POST', body });
      run.revision += 1; run.steps.image.task_id = null; run.steps.image.step_attempt_id = 'reused-step'; run.step_attempts!.push({ id: 'reused-step', mode: 'reused', attempt_id: null, source: { attempt_id: oldId, artifact_id: imageArtifact.id, differences: { input: { current: '蓝杯', source: '旧红杯输入' } }, selected_at: '2026-09-10T00:00:00Z' } }); return response(run);
    }
    return original(input, options);
  });
  render(<WorkflowRunView runId="flow-one" models={models} works={[{ id: 'old-work', name: '旧红杯', attempt_id: oldId, kind: 'image', artifact_id: imageArtifact.id, media_type: 'image/png' }]} onBack={() => {}} onUpdated={() => {}} registerLeave={() => {}} onExport={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: '明确复用旧作品' })); fireEvent.change(screen.getByLabelText('选择同项目旧作品'), { target: { value: 'old-work' } });
  await screen.findByText('复用前核对输入'); expect(calls.some(call => call.method !== 'GET')).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '确认使用这个旧结果' })); await screen.findByText('已明确复用旧结果 · 本步未重新计算');
  expect(calls.filter(call => call.method !== 'GET').map(call => call.path)).toEqual(['/workflow-runs/flow-one/reuse-output']); expect(run.current_step).toBe('image');
  expect(run.step_attempts![0].mode).toBe('compute'); expect(await screen.findByRole('button', { name: '接受图片并带入视频' })).toBeTruthy();
});


it('保存新输入后读取被延迟时立即撤下旧结果和旧任务入口', async () => {
  completeImage(); view(); fireEvent.click(await screen.findByRole('button', { name: '修改输入 / 重做本步' }));
  fireEvent.change(screen.getByLabelText('画面描述'), { target: { value: '新版本画面' } });
  const original = vi.mocked(fetch).getMockImplementation()!;
  let resolveRead!: (value: Response) => void;
  vi.mocked(fetch).mockImplementation((input, options = {}) => {
    if (String(input).endsWith('/workflow-runs/flow-one') && (!options.method || options.method === 'GET')) return new Promise(resolve => { resolveRead = resolve; });
    return original(input, options);
  });
  fireEvent.click(screen.getByRole('button', { name: '保存新版本并重做' }));
  await screen.findByRole('heading', { name: '正在读取当前步骤与原结果' });
  expect(run.steps.image.input_revision).toBe(2);
  expect(screen.queryByTestId('run-result')).toBeNull();
  expect(screen.queryByRole('button', { name: '接受图片并带入视频' })).toBeNull();
  expect(screen.queryByRole('button', { name: '检查本步配置' })).toBeNull();
  await waitFor(() => expect(resolveRead).toBeTypeOf('function'));
  await act(async () => resolveRead(response(run)));
  expect(await screen.findByRole('button', { name: '检查本步配置' })).toBeTruthy();
  expect(screen.queryByTestId('run-result')).toBeNull();
});
