import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../../apps/desktop/src/App';
import Workbench from '../../apps/desktop/src/Workbench';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import type { Dataset, Task } from '../../apps/desktop/src/types';
import type { LibraryViews, ProjectView } from '../../apps/desktop/src/ProjectContext';
import contracts from './fixtures/training-contracts.json';
import { applied, model, source, split, splitPlan, trainDataset, validationDataset } from './fixtures/dataset-split';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
type Call = { path: string; method: string; body: Record<string, unknown> };
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
const trainingTask = (): Task => ({ id: 'task-train', project_id: 'project-a', name: '保留未保存训练参数', kind: 'text', operation: 'train', draft_revision: 1, draft: { kind: 'text', operation: 'train', model_id: model.id, dataset_id: source.id, input: { prompt: '' }, runtime: { engine: 'mlx', device_id: 'apple-gpu', seed: 0, steps: 4, learning_rate: .0001, max_seq_length: 512, lora_rank: 4, lora_alpha: 8, num_layers: 2, batch_size: 1, gradient_accumulation: 1, optimizer: 'adamw', weight_decay: 0, lora_dropout: 0 } } });
let datasets: Dataset[], calls: Call[], storedTask: Task | null, intercept: ((call: Call) => Response | Promise<Response> | undefined) | undefined;
let selection: LibraryViews;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  datasets = [source]; calls = []; storedTask = null; intercept = undefined;
  selection = { project_id: null, projects: {} };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const call = { path: String(input).replace('/api/v1', ''), method: init.method || 'GET', body: init.body ? JSON.parse(String(init.body)) : {} }; calls.push(call); const special = intercept?.(call); if (special) return await special;
    if (call.path === '/ui-context') {
      expect(['GET', 'PATCH']).toContain(call.method);
      if (call.method === 'PATCH') {
        const body = call.body as { project_id: string; context: ProjectView };
        expect(['project-a', 'project-b']).toContain(body.project_id);
        expect(body.context.task_id === null || (body.project_id === 'project-a' && body.context.task_id === storedTask?.id)).toBe(true);
        selection = { project_id: body.project_id, projects: { ...selection.projects, [body.project_id]: body.context } };
      }
      return response(selection);
    }
    if (call.path === '/projects') return response({ items: [{ id: 'project-a', name: '划分入口项目', revision: 1 }, { id: 'project-b', name: '另一个项目', revision: 1 }] });
    if (call.path.startsWith('/models?')) return response({ items: [model] });
    if (call.path.startsWith('/datasets?')) return response({ items: call.path.includes('project-b') ? [] : datasets });
    if (call.path.startsWith('/tasks?')) return response({ items: [] });
    if (call.path === '/training-contracts') return response(contracts);
    if (call.path === '/datasets/split-plans' || call.path === '/datasets/split-plans/split-plan') return response(datasets.some(item => item.dataset_split_id) ? splitPlan({ status: 'applied', applied_split_id: split.id }) : splitPlan());
    if (call.path === '/datasets/splits') { datasets = [source, trainDataset, validationDataset]; return response(applied); }
    if (call.path === '/datasets/splits/split-a') return response(split);
    if (call.path === '/datasets/dataset-train') return response(trainDataset);
    if (call.path === '/tasks' && call.method === 'POST') { storedTask = trainingTask(); return response(storedTask); }
    if (call.path === '/tasks/task-train/draft') { storedTask = { ...(storedTask || trainingTask()), draft: call.body.draft as Task['draft'], draft_revision: 2 }; return response(storedTask); }
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
async function openData() { render(<App />); await screen.findByRole('option', { name: '划分入口项目' }); fireEvent.click(screen.getByRole('button', { name: '数据集市场', exact: true })); await screen.findByRole('heading', { name: source.name }); }
const card = (name: string) => screen.getAllByRole('article').find(item => within(item).queryByRole('heading', { name }))!;

it('原数据保留直接用于训练，新增划分入口没有藏起旧操作', async () => {
  await openData(); expect(within(card(source.name)).getByRole('button', { name: '划分训练与验证' })).toBeTruthy();
  fireEvent.click(within(card(source.name)).getByRole('button', { name: '用于训练' })); await screen.findByRole('heading', { name: '保留未保存训练参数' });
  expect(storedTask?.draft.dataset_id).toBe(source.id); expect(screen.getByText(/新训练需要先按来源组划分/)).toBeTruthy();
  // 保存界面选择不应被算作训练操作；其他业务写入仍逐项核对。
  expect(calls.filter(call => call.method !== 'GET' && call.path !== '/ui-context').map(call => call.path)).toEqual(['/tasks', '/tasks/task-train/draft']);
});

it('数据列表应用后新增两侧资源，验证侧不能新建训练，原件仍在', async () => {
  await openData(); fireEvent.click(within(card(source.name)).getByRole('button', { name: '划分训练与验证' })); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  fireEvent.click(await screen.findByRole('button', { name: '应用划分，生成新版本' })); await screen.findByRole('button', { name: '使用训练子集' });
  expect(calls.some(call => call.path === '/tasks')).toBe(false); fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '关闭对话框' }));
  await screen.findByRole('heading', { name: trainDataset.name }); expect(card(source.name)).toBeTruthy();
  expect((within(card(validationDataset.name)).getByRole('button', { name: '验证子集不用于训练' }) as HTMLButtonElement).disabled).toBe(true);
  expect(within(card(trainDataset.name)).getByRole('button', { name: '用于训练' })).toBeTruthy(); expect(within(card(validationDataset.name)).getByRole('button', { name: '导出划分' })).toBeTruthy();
});

it('图片数据不显示当前只支持语言数据的划分入口', async () => {
  datasets = [source, { id: 'image-data', name: '图片数据', schema: 'image_caption_v1', sample_count: 2 }]; await openData();
  expect(within(card('图片数据')).queryByRole('button', { name: '划分训练与验证' })).toBeNull(); expect(within(card('图片数据')).getByRole('button', { name: '用于训练' })).toBeTruthy();
});

it('切换项目后迟到的创建结果不继续PATCH旧任务，也不打开旧草稿', async () => {
  const pending = deferred<Response>(); intercept = call => call.path === '/tasks' && call.method === 'POST' ? pending.promise : undefined;
  await openData(); fireEvent.click(within(card(source.name)).getByRole('button', { name: '用于训练' })); fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b'));
  await act(async () => pending.resolve(response(trainingTask())));
  expect(calls.some(call => call.path.endsWith('/draft'))).toBe(false); expect(screen.queryByRole('heading', { name: '保留未保存训练参数' })).toBeNull();
});

it('草稿划分保留未存参数，明确使用训练侧并保存成功后清除选择提示', async () => {
  const task = trainingTask(), onTaskChanged = vi.fn(), pending = deferred<Response>();
  intercept = call => call.path === '/tasks/task-train/draft' ? pending.promise : undefined;
  render(<Workbench task={task} models={[model]} datasets={[source, trainDataset, validationDataset]} devices={[]} registerLeave={() => {}} onBack={() => {}} onTaskChanged={onTaskChanged} onImport={() => {}} onUpdated={() => {}} />);
  fireEvent.change(screen.getByLabelText('训练步数'), { target: { value: 53 } }); fireEvent.click(screen.getByRole('button', { name: '划分训练与验证' }));
  expect((screen.getByLabelText('划分检查模型') as HTMLSelectElement).value).toBe(model.id); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  fireEvent.click(await screen.findByRole('button', { name: '应用划分，生成新版本' })); fireEvent.click(await screen.findByRole('button', { name: '使用训练子集' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull()); expect((screen.getByLabelText('训练步数') as HTMLInputElement).value).toBe('53'); expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe(trainDataset.id);
  expect(screen.queryByRole('option', { name: new RegExp(validationDataset.name) })).toBeNull(); expect(onTaskChanged).not.toHaveBeenCalled(); expect(calls.some(call => call.path.endsWith('/draft') || /preflight|attempt/.test(call.path))).toBe(false);
  const notice = '已选择训练子集，其他未保存输入保留。请保存并重新检查配置。'; expect(screen.getByText(notice)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await waitFor(() => expect(calls.filter(call => call.path.endsWith('/draft'))).toHaveLength(1)); expect(screen.getByText(notice)).toBeTruthy();
  const saved = { ...task, draft_revision: 2, draft: { ...task.draft, dataset_id: trainDataset.id, runtime: { ...task.draft.runtime, training_type: 'sft', update_method: 'lora', recipe_id: 'qwen25-assistant-only-v1', steps: 53 } } };
  await act(async () => pending.resolve(response(saved)));
  await waitFor(() => expect(screen.queryByText(notice)).toBeNull()); expect((screen.getByRole('button', { name: '草稿已保存' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByLabelText('训练步数') as HTMLInputElement).value).toBe('53'); expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe(trainDataset.id);
  expect(onTaskChanged).toHaveBeenCalledTimes(1); expect(onTaskChanged).toHaveBeenCalledWith(saved); expect(calls.filter(call => call.path.endsWith('/draft'))).toEqual([{ path: '/tasks/task-train/draft', method: 'PATCH', body: { draft: saved.draft, expected_revision: 1 } }]); expect(calls.some(call => /preflight|attempt/.test(call.path))).toBe(false);
});

it.each(['保存冲突', '工作库已切换'] as const)('%s后的保存响应不清选择提示或未保存输入', async state => {
  const task = trainingTask(), onTaskChanged = vi.fn(), pending = deferred<Response>(); let epoch = 0;
  const captureLibraryRead = () => { const current = epoch; return () => current === epoch; };
  intercept = call => call.path === '/tasks/task-train/draft' ? pending.promise : undefined;
  render(<LibraryReadContext.Provider value={captureLibraryRead}><Workbench task={task} models={[model]} datasets={[source, trainDataset, validationDataset]} devices={[]} registerLeave={() => {}} onBack={() => {}} onTaskChanged={onTaskChanged} onImport={() => {}} onUpdated={() => {}} /></LibraryReadContext.Provider>);
  fireEvent.change(screen.getByLabelText('训练步数'), { target: { value: 53 } }); fireEvent.click(screen.getByRole('button', { name: '划分训练与验证' })); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  fireEvent.click(await screen.findByRole('button', { name: '应用划分，生成新版本' })); fireEvent.click(await screen.findByRole('button', { name: '使用训练子集' })); await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  const notice = '已选择训练子集，其他未保存输入保留。请保存并重新检查配置。'; expect(screen.getByText(notice)).toBeTruthy(); fireEvent.click(screen.getByRole('button', { name: '保存草稿' })); await waitFor(() => expect(calls.filter(call => call.path.endsWith('/draft'))).toHaveLength(1));
  if (state === '工作库已切换') epoch += 1;
  const saved = { ...task, draft_revision: 2, draft: { ...task.draft, dataset_id: trainDataset.id, runtime: { ...task.draft.runtime, training_type: 'sft', update_method: 'lora', recipe_id: 'qwen25-assistant-only-v1', steps: 53 } } };
  await act(async () => pending.resolve(state === '保存冲突' ? response({ error: { code: 'REVISION_CONFLICT', message: '草稿保存发生冲突。' } }, false) : response(saved)));
  await waitFor(() => expect((screen.getByRole('button', { name: '保存草稿' }) as HTMLButtonElement).disabled).toBe(false)); expect(screen.getByText(notice)).toBeTruthy(); expect(screen.queryByRole('button', { name: '草稿已保存' })).toBeNull();
  expect((screen.getByLabelText('训练步数') as HTMLInputElement).value).toBe('53'); expect((screen.getByLabelText('选择训练数据') as HTMLSelectElement).value).toBe(trainDataset.id); expect(onTaskChanged).not.toHaveBeenCalled(); expect(calls.some(call => /preflight|attempt/.test(call.path))).toBe(false);
  if (state === '保存冲突') expect(screen.getByText('草稿保存发生冲突。')).toBeTruthy();
});
