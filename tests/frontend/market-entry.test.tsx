import React from 'react';
import trainingContracts from './fixtures/training-contracts.json';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import Workbench, { defaultRuntime, defaultTrainingRuntime } from '../../apps/desktop/src/Workbench';
import { DatasetMarket } from '../../apps/desktop/src/DatasetMarket';
import type { LibraryViews } from '../../apps/desktop/src/ProjectContext';
import type { Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const model = { id: 'model-one', name: '固定模型', format: 'safetensors', modality: 'text' as const };
const dataset = { id: 'dataset-market', name: '市场导入数据', schema: 'sft', status: 'ready', sample_count: 2 };
const time = '2026-09-10T00:00:00Z';
let selection: LibraryViews;
let task: Task; let calls: { path: string; method: string; body: any; key?: string }[]; let conflict: boolean; let saveFailure: boolean; let hasModel: boolean; let modelRegistered: boolean;
const response = (data: unknown, ok = true) => ({ ok, json: async () => structuredClone(data) }) as Response;
beforeEach(() => {
 HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
 selection = { project_id: null, projects: {} };
 conflict = false; saveFailure = false; hasModel = true; modelRegistered = false; calls = [];
 task = { id: 'task-one', project_id: 'project-one', name: '原训练任务', kind: 'text', operation: 'train', draft_revision: 7, draft: { kind: 'text', operation: 'train', model_id: model.id, dataset_id: 'dataset-old', input: { prompt: '保留的原输入' }, runtime: { ...defaultTrainingRuntime, seed: 919 } } };
 vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
  const path = String(input).replace('/api/v1', ''); const method = options?.method || 'GET'; const body = options?.body ? JSON.parse(String(options.body)) : {};
  calls.push({ path, method, body, key: (options?.headers as Record<string,string>)?.['Idempotency-Key'] });
  // 项目选择的持久化独立于本文件检查的市场、任务和模型写入。
  if (path === '/ui-context') {
   if (method === 'PATCH') {
    expect(body.project_id).toBe('project-one');
    expect(body.context.task_id === null || body.context.task_id === task.id).toBe(true);
    selection = { project_id: body.project_id, projects: { ...selection.projects, [body.project_id]: body.context } };
   }
   return response(selection);
  }
  if (method === 'GET') {
   if (path === '/training-contracts') return response(trainingContracts);
   if (path === '/projects') return response({ items: [{ id: 'project-one', name: '独立项目', revision: 1 }] });
   if (path.startsWith('/models?')) return response({ items: hasModel || modelRegistered ? [model] : [] });
   if (path.startsWith('/datasets?')) return response({ items: [dataset] });
   if (path === '/devices') return response({ items: [{ id: 'apple-gpu', name: '本机 Apple GPU' }] });
   if (path === '/capabilities') return response({ items: [{ kind: 'text', operation: 'generate', supported: true }] });
   if (path === '/model-catalog') return response({ items: [{ id: 'catalog-one', name: model.name, repo: 'official/model', revision: 'fixed', source_url: 'https://huggingface.co/official/model', license: 'Apache-2.0', manifest_digest: 'manifest-one', total_bytes: 1024, network_scope: '固定公开来源', capability: '本机语言模型', files: [{ path: 'model.safetensors', size: 1024, sha256: 'a'.repeat(64) }] }] });
   if (path === '/model-downloads/download-model') return response({ id: 'download-model', project_id: 'project-one', name: model.name, state: 'completed', received_bytes: 1024, total_bytes: 1024, current_file: null, cancel_requested: false, model_id: modelRegistered ? model.id : null });
   if (path === '/models/model-one') return response(model);
   if (path === '/market/sources') return response({ items: [{ provider_id: 'fixture-provider', source_label: '受控测试来源' }] });
   if (path.startsWith('/market/catalog?')) return response({ catalog_version: 'one', versions: [{ id: 'version-one', project_id: 'project-one', provider_id: 'fixture-provider', version_digest: 'a'.repeat(64), metadata: { dataset_key: 'dialogue', version: 'v1', name: '市场数据版本', description: '用于入口回归', modality: 'text', schema: 'sft', sample_count: 2, total_bytes: 1024, format: 'jsonl', provider_text: '提供方原文', source_url: null, updated_at: null, access: 'open', license: null, files: [{ path: 'data.jsonl', size: 1024, sha256: 'b'.repeat(64) }] } }] });
   if (path.endsWith('/activity')) return response({ access_requests: [], downloads: [{ id: 'download-one', version_id: 'version-one', state: 'completed', received_bytes: 1024, complete: true, cancel_requested: false, dataset_id: dataset.id, created_at: time }], datasets: [dataset] });
   return response({ items: [] });
  }
  if (path.endsWith('/draft')) {
   if (saveFailure) return response({ error: { code: 'REVISION_CONFLICT', message: '原草稿已由其他操作更新。' } }, false);
   task = { ...task, draft_revision: task.draft_revision + 1, draft: body.draft }; return response(task);
  }
  if (path.endsWith('/preflight')) return response({ preflight_id: 'original-check', can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime });
  if (path.endsWith('/market-contexts')) return response({ id: 'context-one', task_id: task.id, draft_revision: task.draft_revision });
  if (path.endsWith('/use')) {
   if (conflict) return response({ error: { code: 'REVISION_CONFLICT', message: '原任务草稿已改变，未使用市场数据。' } }, false);
   task = { ...task, draft_revision: task.draft_revision + 1, draft: { ...task.draft, dataset_id: dataset.id } }; return response({ task, return_to: { project_id: task.project_id, task_id: task.id, kind: task.kind, step: 'data', highlight_dataset_id: dataset.id }, previous_checks_invalidated: true });
  }
  if (path === '/model-downloads') return response({ id: 'download-model', project_id: 'project-one', name: model.name, state: 'completed', received_bytes: 1024, total_bytes: 1024, current_file: null, cancel_requested: false, model_id: null });
  if (path === '/model-downloads/download-model/models') { modelRegistered = true; return response(model); }
  if (path === '/tasks') { task = { ...task, name: body.name, kind: body.kind, operation: body.operation, draft_revision: 1, draft: { kind: body.kind, operation: body.operation, model_id: null, dataset_id: null, input: { prompt: '' }, runtime: { ...defaultRuntime } } }; return response(task); }
  throw new Error('未声明写请求 ' + path);
 }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function bench() { const changed = vi.fn(); render(<Workbench task={task} models={[model]} datasets={[{ id: 'dataset-old', name: '原数据', schema: 'sft', sample_count: 2 }, dataset]} devices={[]} onBack={vi.fn()} registerLeave={vi.fn()} onTaskChanged={changed} onImport={vi.fn()} onUpdated={vi.fn()} />); return changed; }

it('训练页先保存当前修改再冻结市场上下文，不下载、不改选中数据、不执行训练', async () => {
 const changed = bench(); fireEvent.change(screen.getByLabelText('随机种子'), { target: { value: '2028' } }); fireEvent.click(screen.getByRole('button', { name: '从数据市场选择训练数据' }));
 await screen.findByRole('button', { name: '用于当前任务' }); const writes = calls.filter(value => value.method !== 'GET' && value.path !== '/ui-context');
 expect(writes.map(value => value.path)).toEqual(['/tasks/task-one/draft', '/tasks/task-one/market-contexts']); expect(writes[0].body).toMatchObject({ expected_revision: 7, draft: { runtime: { seed: 2028 }, dataset_id: 'dataset-old', input: { prompt: '保留的原输入' } } }); expect(writes[1].body).toEqual({ expected_revision: 8, step: 'data' }); expect(changed).toHaveBeenCalledTimes(1);
});
it('市场明确使用回到原训练任务、保留参数并令旧技术检查失效', async () => {
 const changed = bench(); await waitFor(() => expect((screen.getByRole('button', { name: '检查配置' }) as HTMLButtonElement).disabled).toBe(false)); fireEvent.click(screen.getByRole('button', { name: '检查配置' })); await screen.findByRole('button', { name: '开始训练' });
 fireEvent.click(screen.getByRole('button', { name: '从数据市场选择训练数据' })); fireEvent.click(await screen.findByRole('button', { name: '用于当前任务' }));
 await screen.findByText('已应用所选市场数据。原检查已失效，请重新检查训练配置。'); expect(screen.queryByRole('dialog', { name: '数据市场' })).toBeNull();
 expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe(dataset.id); expect((screen.getByLabelText('随机种子') as HTMLInputElement).value).toBe('919'); expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
 expect(changed.mock.calls.at(-1)?.[0]).toMatchObject({ id: 'task-one', draft_revision: 8, draft: { input: { prompt: '保留的原输入' }, dataset_id: dataset.id, runtime: { seed: 919 } } }); expect(calls.some(value => value.path.endsWith('/attempts'))).toBe(false);
});
it('市场使用冲突时保留原草稿与已导入数据，返回原任务后不会自动补写', async () => {
 const changed = bench(); conflict = true; fireEvent.click(screen.getByRole('button', { name: '从数据市场选择训练数据' })); fireEvent.click(await screen.findByRole('button', { name: '用于当前任务' }));
 await screen.findByText('原任务草稿已改变，未使用市场数据。'); expect(changed).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: '返回原任务查看新草稿' }));
 expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe('dataset-old'); expect(calls.filter(value => value.method !== 'GET' && value.path !== '/ui-context').map(value => value.path)).toEqual(['/tasks/task-one/market-contexts', '/market/contexts/context-one/use']);
});
it('保存草稿冲突时市场不打开，也不创建上下文', async () => {
 bench(); saveFailure = true; fireEvent.change(screen.getByLabelText('随机种子'), { target: { value: '2028' } }); fireEvent.click(screen.getByRole('button', { name: '从数据市场选择训练数据' }));
 await screen.findByText('原草稿已由其他操作更新。'); expect(screen.queryByRole('dialog', { name: '数据市场' })).toBeNull(); expect(calls.filter(value => value.method !== 'GET' && value.path !== '/ui-context').map(value => value.path)).toEqual(['/tasks/task-one/draft']); expect((screen.getByLabelText('随机种子') as HTMLInputElement).value).toBe('2028');
});
it('App 全局数据页进入市场只读目录，不创建任务上下文', async () => {
 render(<App />); await screen.findByText('从第一个真实结果开始'); fireEvent.click(screen.getByRole('button', { name: '数据集市场' })); fireEvent.click(await screen.findByRole('tab', { name: '数据集市场' }));
 fireEvent.click(screen.getByRole('button', { name: '打开数据市场' })); await screen.findByRole('dialog', { name: '数据市场' }); await screen.findByText('市场数据版本', { selector: 'h3' });
 expect(calls.every(value => value.method === 'GET' || (value.method === 'PATCH' && value.path === '/ui-context'))).toBe(true); expect(screen.queryByRole('button', { name: '用于当前任务' })).toBeNull();
});
it('已有模型的首次示例只创建与保存普通草稿，不自动检查或运行', async () => {
 render(<App />); await screen.findByText('从第一个真实结果开始'); await waitFor(() => expect(calls.some(value => value.path.startsWith('/models?'))).toBe(true));
 fireEvent.click(screen.getByRole('button', { name: '3 · 建立示例草稿' })); await screen.findByLabelText('输入内容');
 expect((screen.getByLabelText('输入内容') as HTMLTextAreaElement).value).toBe('请用三条简短建议说明如何安排一天的学习。'); expect(calls.filter(value => value.method !== 'GET' && value.path !== '/ui-context').map(value => value.path)).toEqual(['/tasks', '/tasks/task-one/draft']); expect(task.draft.model_id).toBe(model.id);
});
it('无模型的首次示例打开准备页，明确下载登记再使用才建立草稿', async () => {
 hasModel = false; render(<App />); await screen.findByText('从第一个真实结果开始'); fireEvent.click(screen.getByRole('button', { name: '3 · 建立示例草稿' }));
 await screen.findByRole('dialog', { name: '准备第一个语言模型' }); expect(calls.every(value => value.method === 'GET' || (value.method === 'PATCH' && value.path === '/ui-context'))).toBe(true);
 fireEvent.click(await screen.findByRole('button', { name: '下载并核对固定模型' })); fireEvent.click(await screen.findByRole('button', { name: '加入当前项目模型库' }));
 await screen.findByRole('button', { name: '用此模型开始试用' }); expect(calls.some(value => value.path === '/tasks')).toBe(false); fireEvent.click(screen.getByRole('button', { name: '用此模型开始试用' }));
 await screen.findByLabelText('输入内容'); expect(calls.filter(value => value.method !== 'GET' && value.path !== '/ui-context').map(value => value.path)).toEqual(['/model-downloads', '/model-downloads/download-model/models', '/tasks', '/tasks/task-one/draft']); expect(task.draft.model_id).toBe(model.id); expect(task.operation).toBe('generate');
});
it('同项目改换任务时重新读取来源，迟到的旧上下文不能覆盖新任务', async () => {
 let finish!: (value: Response) => void; const original = vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/task-one/market-contexts') ? new Promise(resolve => { finish = resolve; }) : original(input, options));
 const props = { projectId: 'project-one', onClose: vi.fn(), onApplied: vi.fn(), onDatasetImported: vi.fn() }; const mounted = render(<DatasetMarket {...props} task={task} />); await waitFor(() => expect(finish).toBeTruthy());
 task = { ...task, id: 'task-two', name: '新训练任务', draft_revision: 11 }; mounted.rerender(<DatasetMarket {...props} task={task} />);
 await screen.findByRole('button', { name: '用于当前任务' }); await act(async () => finish(response({ id: 'context-old', task_id: 'task-one', draft_revision: 7 })));
 fireEvent.click(screen.getByRole('button', { name: '用于当前任务' })); await waitFor(() => expect(props.onApplied).toHaveBeenCalledTimes(1)); expect(calls.find(value => value.path.endsWith('/use'))?.path).toBe('/market/contexts/context-one/use'); expect(calls.filter(value => value.path === '/market/sources')).toHaveLength(2);
});
it('上下文创建失败在目录迟到后仍给出原因，不能只留下无说明的禁用按钮', async () => {
 const original = vi.mocked(fetch).getMockImplementation()!;
 vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/market-contexts') ? response({ error: { code: 'REVISION_CONFLICT', message: '进入市场前原草稿已改变。' } }, false) : original(input, options));
 bench(); fireEvent.click(screen.getByRole('button', { name: '从数据市场选择训练数据' })); await screen.findByRole('button', { name: '用于当前任务' }); expect(screen.getByText('进入市场前原草稿已改变。')).toBeTruthy(); expect(screen.getByRole('button', { name: '用于当前任务' }).hasAttribute('disabled')).toBe(true);
});
