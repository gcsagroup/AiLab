import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import Workbench, { defaultRuntime } from '../../apps/desktop/src/Workbench';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import type { Attempt, Draft, Model, Task, WorkRecipeView } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));

type Call = { method: string; path: string; body: Record<string, unknown> };
type Handler = (call: Call) => Response | Promise<Response> | undefined;
const response = (value: unknown, ok = true) => ({ ok, json: async () => value }) as Response;
const missing = (message: string) => response({ error: { code: 'RESOURCE_NOT_FOUND', message } }, false);
const originalModel = { id: 'model-original', project_id: 'project-a', name: '分页外的原模型', modality: 'text' as const, format: 'safetensors', version_id: 'model-version-1', manifest_digest: 'model-digest-1' };
const alternateModel = { ...originalModel, id: 'model-alternate', name: '另选模型', version_id: 'model-version-2', manifest_digest: 'model-digest-2' };
const originalAdapter = { id: 'adapter-original', project_id: 'project-a', name: '原训练适配器', version_id: 'adapter-version-1', manifest_digest: 'adapter-digest-1', base_model_id: originalModel.id, base_model_version_id: originalModel.version_id, base_manifest_digest: originalModel.manifest_digest, training_recipe_digest: 'train-digest', source_attempt_id: 'train-attempt', status: 'ready' };
const originalTarget = { id: 'target-original', project_id: 'project-a', name: '原远端', origin: 'https://original.example.test', executor_id: 'executor-original', transport: 'https', validation_scope: 'remote', nvidia_ready: true };
let calls: Call[];
let handlers: Handler[];
let resources: Record<string, Record<string, unknown>>;
let views: Record<string, WorkRecipeView>;
let savedTask: Task;
let currentAttempt: Attempt;
let targets: typeof originalTarget[];

function fixture(suffix = 'a'): Task {
  const value: Task = { id: `task-${suffix}`, project_id: `project-${suffix}`, name: `配方新任务 ${suffix}`, kind: 'text', operation: 'generate', draft_revision: 1,
    source_work_id: `work-${suffix}`, source_attempt_id: `source-attempt-${suffix}`, source_recipe_digest: `recipe-digest-${suffix}`,
    draft: { kind: 'text', operation: 'generate', model_id: originalModel.id, dataset_id: null, adapter_id: null, execution_target_id: null, input: { prompt: '封存的原始输入' }, runtime: { ...defaultRuntime } } };
  views[`/works/work-${suffix}/recipe?project_id=project-${suffix}`] = { source_work_id: value.source_work_id!, source_attempt_id: value.source_attempt_id!, source_recipe_digest: value.source_recipe_digest!,
    work: { id: value.source_work_id!, project_id: value.project_id, attempt_id: value.source_attempt_id!, artifact_id: `artifact-${suffix}`, kind: 'text', text: '独立人工修订文本' },
    recipe: { task_id: `original-task-${suffix}`, project_id: value.project_id, attempt_id: value.source_attempt_id, kind: 'text', operation: 'generate', model_id: originalModel.id, model_version_id: originalModel.version_id, model_manifest_digest: originalModel.manifest_digest,
      adapter_id: null, execution_target_id: null, input: { ...value.draft.input }, runtime: { ...value.draft.runtime }, requested_config: { ...value.draft.runtime }, effective_config: { ...value.draft.runtime, seed: 19 } } };
  return value;
}
function source(value = savedTask) { return views[`/works/${value.source_work_id}/recipe?project_id=${value.project_id}`]; }
function writes() { return calls.filter(call => call.method !== 'GET'); }
async function settle(ms = 0) { await act(async () => { await vi.advanceTimersByTimeAsync(ms); }); }
function pending() { let resolve!: (value: Response) => void; const promise = new Promise<Response>(finish => { resolve = finish; }); return { promise, resolve }; }
function mount(value = savedTask, options: { models?: Model[]; leave?: (handler: (() => Promise<boolean>) | null) => void; capture?: () => () => boolean; onSaved?: (task: Task) => void } = {}) {
  const element = (task: Task) => <LibraryReadContext.Provider value={options.capture || stableCapture}><Workbench key={task.id} task={task} models={options.models || [alternateModel]} datasets={[]} adapters={[]} materials={[]} devices={[{ id: 'apple-gpu', name: '本机 Apple GPU' }]} registerLeave={options.leave || (() => {})} onTaskChanged={options.onSaved || (() => {})} onBack={() => {}} onImport={() => {}} onUpdated={() => {}} /></LibraryReadContext.Provider>;
  const rendered = render(element(value));
  return { ...rendered, next: (task: Task) => rendered.rerender(element(task)) };
}
const stableCapture = () => () => true;
function difference(label: string) {
  const scope = within(screen.getByLabelText('配方差异'));
  return scope.getByText(label, { selector: 'dt' }).parentElement!.textContent!;
}

beforeEach(() => {
  vi.useFakeTimers(); calls = []; handlers = []; views = {}; targets = [];
  resources = { '/models/model-original': { ...originalModel }, '/models/model-alternate': { ...alternateModel }, '/adapters/adapter-original': { ...originalAdapter }, '/execution-targets/target-original': { ...originalTarget } };
  savedTask = fixture();
  currentAttempt = { id: 'attempt-new', task_id: savedTask.id, project_id: savedTask.project_id, state: 'running', state_version: 2, snapshot: { kind: 'text', operation: 'generate' }, artifacts: [] };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit = {}) => {
    const call: Call = { path: String(input).replace('/api/v1', ''), method: init.method || 'GET', body: init.body ? JSON.parse(String(init.body)) : {} };
    calls.push(call);
    for (const handler of handlers) { const result = handler(call); if (result) return result; }
    if (views[call.path]) return response(views[call.path]);
    if (resources[call.path]) return response(resources[call.path]);
    if (call.path.startsWith('/execution-targets?')) return response({ items: targets });
    if (call.path.endsWith('/draft') && call.method === 'PATCH') { savedTask = { ...savedTask, draft: call.body.draft as Draft, draft_revision: savedTask.draft_revision + 1 }; return response(savedTask); }
    if (call.path.endsWith('/preflight') && call.method === 'POST') return response({ preflight_id: 'check-new', task_id: savedTask.id, draft_revision: savedTask.draft_revision, can_submit: true, blocking: [], warnings: [], effective_config: savedTask.draft.runtime });
    if (call.path.endsWith('/attempts') && call.method === 'POST') return response({ ...currentAttempt, state: 'queued', state_version: 1 });
    if (call.path === `/attempts/${currentAttempt.id}`) return response(currentAttempt);
    if (call.path.startsWith(`/attempts/${currentAttempt.id}/events?`)) return response({ items: [] });
    throw new Error(`测试未安排的请求：${call.method} ${call.path}`);
  }));
});
afterEach(() => { cleanup(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('复用作品后原配方与当前草稿的可追溯对照', () => {
  it('重开任务从来源作品读取原输入，分页外模型按编号补齐，本机原位置不继承远端默认值', async () => {
    savedTask.draft = { ...savedTask.draft, input: { prompt: '已另行修改的新草稿' } };
    targets = [originalTarget];
    const first = mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe(originalModel.id);
    expect(screen.getByRole('option', { name: originalModel.name }).selected).toBe(true);
    expect(screen.getByLabelText<HTMLSelectElement>('执行位置').value).toBe('');
    expect(screen.getByLabelText<HTMLTextAreaElement>('输入内容').value).toBe('已另行修改的新草稿');
    fireEvent.click(screen.getByText('查看原配方基准'));
    expect(within(screen.getByLabelText('原生成输入')).getByText('封存的原始输入')).toBeTruthy();
    expect(screen.queryByText('独立人工修订文本')).toBeNull();
    expect(difference('输入内容')).toContain('原：封存的原始输入当前：已另行修改的新草稿');
    expect(calls.filter(call => call.path === '/models/model-original')).toHaveLength(1);
    expect(calls.some(call => /execution-default|probe|download/.test(call.path))).toBe(false);
    expect(writes()).toHaveLength(0);
    first.unmount(); mount(); await settle();
    expect(within(screen.getByLabelText('原生成输入')).getByText('封存的原始输入')).toBeTruthy();
    expect(calls.filter(call => call.path.startsWith('/works/'))).toHaveLength(2);
    expect(writes()).toHaveLength(0);
  });

  it('明确改选模型和参数后列出具体版本摘要差异，自动保存保留来源且旧检查失效', async () => {
    const onSaved = vi.fn(); mount(savedTask, { onSaved }); await settle();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await settle();
    expect(screen.getByRole('button', { name: '开始运行' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('选择基座模型'), { target: { value: alternateModel.id } });
    fireEvent.change(screen.getByLabelText('最大输出 token'), { target: { value: '256' } }); await settle();
    expect(difference('模型版本')).toContain('原：model-version-1当前：model-version-2');
    expect(difference('模型文件摘要')).toContain('原：model-digest-1当前：model-digest-2');
    expect(difference('最大输出 token')).toContain('原：128当前：256');
    expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
    await settle(500);
    expect(writes().filter(call => call.method === 'PATCH')).toHaveLength(1);
    expect(savedTask).toMatchObject({ source_work_id: 'work-a', source_attempt_id: 'source-attempt-a', source_recipe_digest: 'recipe-digest-a', draft: { model_id: alternateModel.id, runtime: { max_tokens: 256 }, execution_target_id: null } });
    expect(onSaved.mock.calls[0][0]).toMatchObject({ source_work_id: 'work-a', source_recipe_digest: 'recipe-digest-a' });
    expect(writes().filter(call => call.path.endsWith('/attempts'))).toHaveLength(0);
  });

  it('同编号远端地址与执行器改变时可见差异，只有明确选择本机才保存本机位置', async () => {
    savedTask.draft = { ...savedTask.draft, execution_target_id: originalTarget.id, runtime: { ...defaultRuntime, engine: 'transformers', device_id: 'cuda:0' } };
    source().recipe = { ...source().recipe, execution_target_id: originalTarget.id, execution_target: originalTarget, runtime: { ...savedTask.draft.runtime } };
    resources['/execution-targets/target-original'] = { ...originalTarget, origin: 'https://changed.example.test', executor_id: 'executor-replaced', transport: 'http', validation_scope: 'local' };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('执行位置').value).toBe(originalTarget.id);
    expect(difference('执行地址')).toContain('原：https://original.example.test当前：https://changed.example.test');
    expect(difference('执行器身份')).toContain('原：executor-original当前：executor-replaced');
    expect(difference('执行连接方式')).toContain('原：https当前：http');
    expect(difference('执行验证范围')).toContain('原：remote当前：local');
    expect(writes()).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('执行位置'), { target: { value: '' } }); await settle(500);
    expect(savedTask.draft.execution_target_id).toBeNull();
    expect(difference('执行位置')).toContain('原：target-original当前：本机');
    expect(difference('执行设备')).toContain('原：cuda:0当前：apple-gpu');
    expect(writes()).toHaveLength(1);
  });

  it('适配器版本或基座身份变化保留所选编号，展示不兼容原因和具体差异', async () => {
    savedTask.draft = { ...savedTask.draft, adapter_id: originalAdapter.id };
    source().recipe = { ...source().recipe, adapter_id: originalAdapter.id, adapter_version_id: originalAdapter.version_id, adapter_manifest_digest: originalAdapter.manifest_digest };
    source().recipe.adapter_training_recipe_digest = originalAdapter.training_recipe_digest;
    resources['/adapters/adapter-original'] = { ...originalAdapter, version_id: 'adapter-version-2', manifest_digest: 'adapter-digest-2', base_model_version_id: 'other-base-version', training_recipe_digest: 'changed-training-digest' };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('训练适配器').value).toBe(originalAdapter.id);
    expect(difference('适配器版本')).toContain('原：adapter-version-1当前：adapter-version-2');
    expect(difference('适配器文件摘要')).toContain('原：adapter-digest-1当前：adapter-digest-2');
    expect(difference('适配器基座版本')).toContain('原：model-version-1当前：other-base-version');
    expect(difference('适配器训练配方摘要')).toContain('原：train-digest当前：changed-training-digest');
    expect(screen.getByText(/当前适配器与所选基座不兼容/).textContent).toContain('other-base-version');
    expect(writes()).toHaveLength(0);
  });

  it('旧执行目标未记录 transport 时按后端 loopback_http 合同对照，不误报位置变化', async () => {
    const original = { ...originalTarget, origin: 'http://127.0.0.1:9443', transport: 'loopback_http', validation_scope: 'loopback_only' };
    const { transport, ...legacy } = original; resources['/execution-targets/target-original'] = legacy;
    savedTask.draft = { ...savedTask.draft, execution_target_id: original.id, runtime: { ...defaultRuntime, engine: 'transformers', device_id: 'cuda:0' } };
    source().recipe = { ...source().recipe, execution_target_id: original.id, execution_target: original, runtime: { ...savedTask.draft.runtime } };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('执行位置').value).toBe(original.id);
    expect(screen.queryByLabelText('配方差异')).toBeNull();
    expect(screen.getByText('已读回的选择与原配方一致。执行前仍需检查配置。')).toBeTruthy();
    expect(calls.some(call => /probe|check|download/.test(call.path))).toBe(false);
    expect(writes()).toHaveLength(0);
  });

  it.each(['missing', 'other-project'] as const)('模型引用 %s 时保留旧编号及基准，不采用列表首项或其他项目的记录', async mode => {
    if (mode === 'missing') handlers.push(call => call.path === '/models/model-original' ? missing('原模型已不存在') : undefined);
    else resources['/models/model-original'] = { ...originalModel, project_id: 'project-b', name: '禁止出现的其他项目模型' };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe(originalModel.id);
    expect(screen.getByRole('option', { name: /已保存模型 · 尚未读回/ })).toBeTruthy();
    expect(screen.queryByRole('option', { name: '禁止出现的其他项目模型' })).toBeNull();
    expect(screen.getByText(/原配方和草稿编号保留，请明确重新选择后检查/).textContent).toContain(mode === 'missing' ? '原模型已不存在' : '记录身份或所属项目不符');
    expect(within(screen.getByLabelText('原生成输入')).getByText('封存的原始输入')).toBeTruthy();
    expect(writes()).toHaveLength(0);
  });

  it('远端引用缺失保留原位置，离线设备编号也不会显示为第一个本机设备', async () => {
    savedTask.draft = { ...savedTask.draft, execution_target_id: originalTarget.id, runtime: { ...defaultRuntime, engine: 'transformers', device_id: 'cuda:0' } };
    source().recipe = { ...source().recipe, execution_target_id: originalTarget.id, execution_target: originalTarget, runtime: { ...savedTask.draft.runtime } };
    handlers.push(call => call.path === '/execution-targets/target-original' ? missing('原执行目标已移除') : undefined);
    const first = mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('执行位置').value).toBe(originalTarget.id);
    expect(screen.getByText(/原执行目标已移除/)).toBeTruthy();
    expect(writes()).toHaveLength(0);
    first.unmount();
    savedTask.draft = { ...savedTask.draft, execution_target_id: null, runtime: { ...defaultRuntime, device_id: 'cpu:retired' } };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('执行设备').value).toBe('cpu:retired');
    expect(screen.getByRole('option', { name: '已保存设备 · 待检查（cpu:retired）' })).toBeTruthy();
    expect(writes()).toHaveLength(0);
  });

  it.each(['digest', 'attempt', 'project'] as const)('来源 %s 身份不符时拒绝错误基准，不继续读引用', async field => {
    if (field === 'digest') source().source_recipe_digest = 'changed-digest';
    if (field === 'attempt') source().source_attempt_id = 'changed-attempt';
    if (field === 'project') source().recipe.project_id = 'project-b';
    mount(); await settle();
    expect(screen.getByText('来源作品、运行或配方基准已变化，请重新核对来源。')).toBeTruthy();
    expect(screen.queryByLabelText('原生成输入')).toBeNull();
    expect(calls.some(call => call.path.startsWith('/models/'))).toBe(false);
    expect(writes()).toHaveLength(0);
  });

  it('切换项目后的旧来源迟到响应不能覆盖新项目或继续读取旧引用', async () => {
    const held = pending(); handlers.push(call => call.path === '/works/work-a/recipe?project_id=project-a' ? held.promise : undefined);
    const firstSource = structuredClone(source());
    const page = mount(); await settle();
    const next = fixture('b'); next.draft = { ...next.draft, model_id: 'model-b' };
    source(next).recipe = { ...source(next).recipe, model_id: 'model-b', input: { prompt: '项目 B 的原始输入' } };
    resources['/models/model-b'] = { ...originalModel, id: 'model-b', project_id: 'project-b', name: '项目 B 模型' };
    page.next(next); await settle();
    await act(async () => held.resolve(response(firstSource))); await settle();
    expect(screen.getByText('来源作品编号：work-b')).toBeTruthy();
    expect(within(screen.getByLabelText('原生成输入')).getByText('项目 B 的原始输入')).toBeTruthy();
    expect(screen.queryByText('来源作品编号：work-a')).toBeNull();
    expect(calls.some(call => call.path === '/models/model-original')).toBe(false);
    expect(writes()).toHaveLength(0);
  });

  it('失败切库后的旧来源回执不继续读取引用，原页可明确重新读取恢复', async () => {
    const held = pending(); let generation = 1;
    const capture = () => { const captured = generation; return () => captured === generation; };
    handlers.push(call => call.path.startsWith('/works/') ? held.promise : undefined);
    mount(savedTask, { capture }); await settle(); generation++;
    await act(async () => held.resolve(response(source()))); await settle();
    expect(screen.queryByLabelText('原生成输入')).toBeNull();
    expect(calls.some(call => call.path.startsWith('/models/'))).toBe(false);
    expect(screen.getByText('读取期间工作库已变化，旧结果未采用。请重新读取来源与引用。')).toBeTruthy();
    const retry = screen.getByRole('button', { name: '重新读取来源与引用' }); expect(retry.matches(':disabled')).toBe(false);
    handlers = []; fireEvent.click(retry); await settle();
    expect(within(screen.getByLabelText('原生成输入')).getByText('封存的原始输入')).toBeTruthy();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe(originalModel.id);
    expect(screen.queryByText('读取期间工作库已变化，旧结果未采用。请重新读取来源与引用。')).toBeNull();
    expect(writes()).toHaveLength(0);
  });

  it('失败切库后的旧引用回执不采用，原页可重读并恢复真实引用', async () => {
    const held = pending(); let generation = 1;
    const capture = () => { const captured = generation; return () => captured === generation; };
    handlers.push(call => call.path === '/models/model-original' ? held.promise : undefined);
    mount(savedTask, { capture }); await settle(); generation++;
    await act(async () => held.resolve(response({ ...originalModel, name: '不采用的旧库名称' }))); await settle();
    expect(screen.queryByRole('option', { name: '不采用的旧库名称' })).toBeNull();
    expect(screen.getByText(/读取期间工作库已变化，旧结果未采用/)).toBeTruthy();
    const retry = screen.getByRole('button', { name: '重新读取来源与引用' }); expect(retry.matches(':disabled')).toBe(false);
    handlers = []; fireEvent.click(retry); await settle();
    expect(screen.getByRole('option', { name: originalModel.name })).toBeTruthy();
    expect(screen.queryByText(/读取期间工作库已变化，旧结果未采用/)).toBeNull();
    expect(writes()).toHaveLength(0);
  });

  it('同编号模型类别改变时给出明确原因，保留草稿编号且不自动选择首项', async () => {
    resources['/models/model-original'] = { ...originalModel, modality: 'image' };
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe(originalModel.id);
    expect(screen.getByText(/当前模型类别与原配方不符/).textContent).toContain('当前模型为 image');
    expect(difference('模型类别')).toContain('原：text当前：image');
    expect(writes()).toHaveLength(0);
  });

  it('旧语言模型未记录类别时按后端合同视为 text，不误报类别差异', async () => {
    const { modality, ...legacy } = originalModel; resources['/models/model-original'] = legacy;
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe(originalModel.id);
    expect(screen.queryByText(/当前模型类别与原配方不符/)).toBeNull();
    expect(screen.queryByLabelText('配方差异')).toBeNull();
    expect(screen.getByText('已读回的选择与原配方一致。执行前仍需检查配置。')).toBeTruthy();
    expect(writes()).toHaveLength(0);
  });

  it('普通无作品来源任务不发来源或单项引用读取', async () => {
    const { source_work_id, source_attempt_id, source_recipe_digest, ...ordinary } = savedTask;
    mount(ordinary); await settle();
    expect(screen.queryByLabelText('来源作品与配方对照')).toBeNull();
    expect(calls.map(call => call.path)).toEqual(['/execution-targets?project_id=project-a']);
    expect(writes()).toHaveLength(0);
  });

  it.each(['image', 'video', 'audio'] as const)('%s 任务保留原媒体输入与参数，分页外模型和素材按编号读取', async kind => {
    const model = { ...originalModel, id: `model-${kind}`, modality: kind, name: `原 ${kind} 模型` };
    const material = { id: 'material-original', project_id: 'project-a', name: '原视频输入图片', kind: 'image', media_type: 'image/png', version_id: 'material-version-1', manifest_digest: 'material-digest-1', width: 1024, height: 576, total_bytes: 24 };
    const input = kind === 'video' ? { material_id: material.id } : kind === 'image' ? { prompt: '原图片描述', negative_prompt: '原负面提示' } : { prompt: '原配音文案' };
    const runtime = defaultMediaRuntime(kind, false);
    savedTask = { ...savedTask, kind, draft: { ...savedTask.draft, kind, model_id: model.id, input, runtime } };
    source().recipe = { ...source().recipe, kind, model_id: model.id, input: { ...input }, runtime: { ...runtime }, requested_config: { ...runtime }, effective_config: { ...runtime }, ...(kind === 'video' ? { material_version_id: material.version_id, input_image_manifest_digest: material.manifest_digest } : {}) };
    resources[`/models/${model.id}`] = model; resources[`/materials/${material.id}`] = material;
    mount(); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择媒体模型').value).toBe(model.id);
    expect(screen.getByRole('option', { name: model.name })).toBeTruthy();
    if (kind === 'video') {
      expect(screen.getByLabelText<HTMLSelectElement>('输入图片').value).toBe(material.id);
      expect(screen.getByRole('option', { name: '原视频输入图片 · 1024×576' })).toBeTruthy();
      expect(calls.filter(call => call.path === `/materials/${material.id}`)).toHaveLength(1);
      resources[`/materials/${material.id}`] = { ...material, version_id: 'material-version-2', manifest_digest: 'material-digest-2' };
      fireEvent.click(screen.getByRole('button', { name: '重新读取来源与引用' })); await settle();
      expect(difference('输入素材版本')).toContain('原：material-version-1当前：material-version-2');
      expect(difference('输入素材摘要')).toContain('原：material-digest-1当前：material-digest-2');
    } else {
      expect(screen.getByLabelText<HTMLTextAreaElement>(kind === 'audio' ? '配音文本' : '画面描述').value).toBe(input.prompt);
      expect(within(screen.getByLabelText('原生成输入')).getByText(input.prompt!, { selector: 'p' })).toBeTruthy();
      if (kind === 'image') expect(screen.getByLabelText<HTMLTextAreaElement>('不希望出现的内容').value).toBe('原负面提示');
    }
    expect(savedTask.draft.runtime).toEqual(runtime);
    expect(calls.some(call => /artifacts|probe|download/.test(call.path))).toBe(false);
    expect(writes()).toHaveLength(0);
  });

  it('旧项目引用读取迟到不替换新项目模型或基准', async () => {
    const held = pending(); handlers.push(call => call.path === '/models/model-original' ? held.promise : undefined);
    const page = mount(); await settle();
    const next = fixture('b'); next.draft = { ...next.draft, model_id: 'model-b' };
    source(next).recipe = { ...source(next).recipe, model_id: 'model-b', input: { prompt: 'B 基准' } };
    resources['/models/model-b'] = { ...originalModel, id: 'model-b', project_id: 'project-b', name: '项目 B 模型' };
    page.next(next); await settle(); await act(async () => held.resolve(response(originalModel))); await settle();
    expect(screen.getByLabelText<HTMLSelectElement>('选择基座模型').value).toBe('model-b');
    expect(screen.getByRole('option', { name: '项目 B 模型' })).toBeTruthy();
    expect(screen.queryByRole('option', { name: originalModel.name })).toBeNull();
    expect(within(screen.getByLabelText('原生成输入')).getByText('B 基准')).toBeTruthy();
    expect(writes()).toHaveLength(0);
  });

  it('来源仍可查看，但运行中的任务配置和提交保持只读', async () => {
    savedTask.latest_attempt = currentAttempt; let leave: (() => Promise<boolean>) | null = null;
    mount(savedTask, { leave: handler => { leave = handler; } }); await settle();
    fireEvent.click(screen.getByText('查看原配方基准'));
    expect(within(screen.getByLabelText('原生成输入')).getByText('封存的原始输入')).toBeTruthy();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(true);
    expect(screen.getByLabelText('选择基座模型').matches(':disabled')).toBe(true);
    expect(screen.getByRole('button', { name: '检查配置' }).matches(':disabled')).toBe(true);
    fireEvent.change(screen.getByLabelText('输入内容'), { target: { value: '禁止写入' } }); await settle(500);
    expect(screen.getByLabelText<HTMLTextAreaElement>('输入内容').value).toBe('封存的原始输入');
    expect(await leave!()).toBe(true); expect(writes()).toHaveLength(0);
  });
});

describe('忙碌离开提示仅随本次操作清理', () => {
  const busyMessage = '当前操作尚未完成，请稍后再离开。';
  it('预检在途阻止离开，检查返回后清除临时提示且不自动提交', async () => {
    let leave: (() => Promise<boolean>) | null = null; const held = pending();
    handlers.push(call => call.path.endsWith('/preflight') ? held.promise : undefined);
    mount(savedTask, { leave: handler => { leave = handler; } }); await settle();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await settle();
    await act(async () => expect(await leave!()).toBe(false));
    expect(screen.getByText(busyMessage)).toBeTruthy();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(true);
    await act(async () => held.resolve(response({ preflight_id: 'check-held', can_submit: true, blocking: [], warnings: [] }))); await settle();
    expect(screen.queryByText(busyMessage)).toBeNull();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false);
    expect(screen.getByRole('button', { name: '开始运行' })).toBeTruthy();
    expect(await leave!()).toBe(true);
    expect(writes().map(call => call.path)).toEqual(['/tasks/task-a/preflight']);
  });

  it('提交回执结束忙碌提示后，后端仍运行时继续锁配置；终态才恢复编辑', async () => {
    let leave: (() => Promise<boolean>) | null = null; const held = pending();
    handlers.push(call => call.method === 'POST' && call.path.endsWith('/attempts') ? held.promise : undefined);
    mount(savedTask, { leave: handler => { leave = handler; } }); await settle();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await settle();
    fireEvent.click(screen.getByRole('button', { name: '开始运行' })); await settle();
    await act(async () => expect(await leave!()).toBe(false)); expect(screen.getByText(busyMessage)).toBeTruthy();
    await act(async () => held.resolve(response({ ...currentAttempt, state: 'queued', state_version: 1 }))); await settle();
    expect(screen.queryByText(busyMessage)).toBeNull();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(true);
    expect(screen.getByRole('button', { name: '检查配置' }).matches(':disabled')).toBe(true);
    expect(await leave!()).toBe(true);
    currentAttempt = { ...currentAttempt, state: 'succeeded', state_version: 3, output_text: '后端完成结果' }; await settle(600);
    expect(screen.getByText('后端完成结果')).toBeTruthy();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false);
    expect(screen.queryByText(busyMessage)).toBeNull();
    expect(writes().filter(call => call.path.endsWith('/attempts'))).toHaveLength(1);
  });

  it('忙碌离开后发生真实提交失败，失败原因在解除忙碌后保留', async () => {
    let leave: (() => Promise<boolean>) | null = null; const held = pending();
    handlers.push(call => call.method === 'POST' && call.path.endsWith('/attempts') ? held.promise : undefined);
    mount(savedTask, { leave: handler => { leave = handler; } }); await settle();
    fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await settle();
    fireEvent.click(screen.getByRole('button', { name: '开始运行' })); await settle();
    await act(async () => expect(await leave!()).toBe(false));
    await act(async () => held.resolve(missing('模型文件已改变，提交被拒绝'))); await settle();
    expect(screen.queryByText(busyMessage)).toBeNull();
    expect(screen.getByText('模型文件已改变，提交被拒绝')).toBeTruthy();
    expect(screen.getByLabelText('输入内容').matches(':disabled')).toBe(false);
    expect(writes().filter(call => call.path.endsWith('/attempts'))).toHaveLength(1);
  });
});
