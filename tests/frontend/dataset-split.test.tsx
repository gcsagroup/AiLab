import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DatasetSplitDialog, { DatasetSplitBinding } from '../../apps/desktop/src/DatasetSplitDialog';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import { applied, counts, model, source, split, splitPlan, trainDataset } from './fixtures/dataset-split';
import type { Dataset, DatasetSplitPlan } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
type Call = { method: string; path: string; body: Record<string, unknown>; key?: string };
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
let calls: Call[], plan: DatasetSplitPlan, intercept: ((call: Call) => Response | Promise<Response> | undefined) | undefined;
let epoch: number, historyPlans: DatasetSplitPlan[];
const captureLibraryRead = () => { const current = epoch; return () => current === epoch; };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  calls = []; plan = splitPlan(); historyPlans = []; intercept = undefined; epoch = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const call = { method: init.method || 'GET', path: String(url).replace('/api/v1', ''), body: init.body ? JSON.parse(String(init.body)) : {}, key: (init.headers as Record<string, string>)['Idempotency-Key'] };
    calls.push(call); const special = intercept?.(call); if (special) return await special;
    if (call.path.startsWith('/datasets/split-plans?')) return response({ items: historyPlans, next_cursor: null });
    if (call.path === '/datasets/split-plans') { plan = { ...plan, ...call.body } as DatasetSplitPlan; return response(plan); }
    if (call.path === '/datasets/split-plans/split-plan') return response(plan);
    if (call.path === '/datasets/split-plans/split-plan/cancel') { plan = { ...plan, status: 'cancelled' }; return response(plan); }
    if (call.path === '/datasets/splits') { plan = { ...plan, status: 'applied', applied_split_id: split.id, train_dataset_id: trainDataset.id, validation_dataset_id: split.validation_dataset_id }; return response(applied); }
    if (call.path === '/datasets/splits/split-a') return response(split);
    if (call.path === '/datasets/dataset-train') return response(trainDataset);
    throw new Error(`未授权夹具请求：${call.method} ${call.path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function setup(dataset: Dataset = source) {
  if (dataset.dataset_split_id) plan = splitPlan({ status: 'applied', applied_split_id: split.id, train_dataset_id: trainDataset.id, validation_dataset_id: split.validation_dataset_id });
  const onClose = vi.fn(), onChanged = vi.fn(), onUseTraining = vi.fn(), onExport = vi.fn();
  const node = () => <LibraryReadContext.Provider value={captureLibraryRead}><DatasetSplitDialog dataset={dataset} models={[model]} projectId="project-a" onClose={onClose} onChanged={onChanged} onUseTraining={onUseTraining} onExport={onExport} /></LibraryReadContext.Provider>;
  const result = render(node());
  return { ...result, redraw: () => result.rerender(node()), onClose, onChanged, onUseTraining, onExport };
}
async function preview() {
  fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } });
  fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  await screen.findByRole('button', { name: '应用划分，生成新版本' });
}

it('先展示原件、两侧计数和实际比例，预览不创建子集或选择训练数据', async () => {
  const callbacks = setup(); expect(calls.every(call => call.method === 'GET')).toBe(true); await preview();
  const summary = screen.getByLabelText('划分数量与比例');
  expect(within(summary).getByText('6 条 · 3 组')).toBeTruthy(); expect(within(summary).getByText('2 条 · 1 组')).toBeTruthy();
  expect(within(summary).getByText('请求 20.00% · 实际样本 25.00%')).toBeTruthy();
  expect(screen.getByText(/语义近似尚未检查/)).toBeTruthy(); expect(screen.getByText(/尚未计算验证损失/)).toBeTruthy();
  expect(screen.getByText('5 个文件 · 4.0 KB')).toBeTruthy(); expect(screen.getByText(/没有有效监督内容 1 条；超过最大序列长度 1 条/)).toBeTruthy();
  expect(screen.getByLabelText('第 1 行词元与监督标签').textContent).toContain('监督标签：[-100,20,30]');
  expect(calls.filter(call => call.method === 'POST')).toEqual([{ method: 'POST', path: '/datasets/split-plans', body: { project_id: 'project-a', source_dataset_id: source.id, model_id: model.id, max_seq_length: 512, split_seed: 0, validation_fraction_bps: 2000 }, key: expect.any(String) }]);
  expect(callbacks.onUseTraining).not.toHaveBeenCalled(); expect(callbacks.onChanged).not.toHaveBeenCalled();
});

it('只有明确应用才生成新版本，随后仍须明确选择训练侧', async () => {
  const callbacks = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' }));
  await screen.findByRole('button', { name: '使用训练子集' });
  expect(callbacks.onChanged).toHaveBeenCalledWith(applied); expect(callbacks.onUseTraining).not.toHaveBeenCalled();
  const write = calls.find(call => call.path === '/datasets/splits')!; expect(write.body).toEqual({ plan_id: plan.id, plan_digest: plan.plan_digest }); expect(write.key).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '使用训练子集' })); await waitFor(() => expect(callbacks.onUseTraining).toHaveBeenCalledWith(trainDataset));
  expect(calls.some(call => /\/tasks|preflight|attempt|capabilities|devices/.test(call.path))).toBe(false);
});

it('修改预览参数立即使旧计划失效，保留输入但不自行创建下一计划', async () => {
  setup(); await preview(); fireEvent.change(screen.getByLabelText('固定划分种子'), { target: { value: '919' } });
  expect(screen.queryByRole('button', { name: '应用划分，生成新版本' })).toBeNull(); expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).value).toBe('919');
  expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' })); await waitFor(() => expect(calls.filter(call => call.method === 'POST')).toHaveLength(2));
  expect(calls.filter(call => call.method === 'POST')[1].body.split_seed).toBe(919);
});

it('关闭后重开能找回已有ready计划，只读后仍须明确应用', async () => {
  const first = setup(); await preview(); first.unmount(); historyPlans = [plan];
  const second = setup(); fireEvent.click(await screen.findByRole('button', { name: '读取已有记录 1' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(false));
  expect(calls.filter(call => call.method === 'POST')).toHaveLength(1); expect(second.onUseTraining).not.toHaveBeenCalled(); expect(second.onChanged).not.toHaveBeenCalled();
});

it('恢复库中的中断计划可找回并取消，不自动重跑CPU', async () => {
  plan = splitPlan({ status: 'recovery_required', split_seed: 919, counts: null, plan_digest: null }); historyPlans = [plan]; setup();
  fireEvent.click(await screen.findByRole('button', { name: '读取已有记录 1' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '取消本次检查与预览' }) as HTMLButtonElement).disabled).toBe(false));
  expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).value).toBe('919'); expect(calls.every(call => call.method === 'GET')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '取消本次检查与预览' })); await screen.findByText('本次检查已停止');
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/datasets/split-plans/split-plan/cancel']);
});

it('已有记录分页保留前页，选后页会读取其固定计划', async () => {
  const second = splitPlan({ id: 'split-plan-2', split_seed: 919 });
  intercept = call => call.path.startsWith('/datasets/split-plans?') ? response(call.path.includes('cursor=') ? { items: [second], next_cursor: null } : { items: [plan], next_cursor: 'page-next' }) : call.path === '/datasets/split-plans/split-plan-2' ? response(second) : undefined;
  setup(); fireEvent.click(await screen.findByRole('button', { name: '载入更多已有记录' })); fireEvent.click(await screen.findByRole('button', { name: '读取已有记录 2' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByRole('button', { name: '读取已有记录 1' })).toBeTruthy(); expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).value).toBe('919'); expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('已有计划再读取失败时保留参数并禁止应用，重读成功才恢复', async () => {
  historyPlans = [plan]; let failing = true;
  intercept = call => call.path === '/datasets/split-plans/split-plan' && failing ? Promise.reject(new Error('已有计划读取失败')) : undefined;
  setup(); fireEvent.click(await screen.findByRole('button', { name: '读取已有记录 1' })); await screen.findByText('已有计划读取失败');
  expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(true); expect((screen.getByLabelText('划分最大序列长度') as HTMLInputElement).value).toBe('512');
  failing = false; fireEvent.click(screen.getByRole('button', { name: '重新读取划分' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(false)); expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('切库失败后迟到的已有计划列表不显示，可重新读取且保留新输入', async () => {
  const pending = deferred<Response>(); let first = true;
  historyPlans = [plan]; intercept = call => { if (call.path.startsWith('/datasets/split-plans?') && first) { first = false; return pending.promise; } };
  const view = setup(); fireEvent.change(screen.getByLabelText('固定划分种子'), { target: { value: '919' } }); epoch++; view.redraw(); await act(async () => pending.resolve(response({ items: [plan], next_cursor: null })));
  expect(screen.queryByRole('button', { name: '读取已有记录 1' })).toBeNull(); fireEvent.click(screen.getByRole('button', { name: '重新读取已有记录' })); await screen.findByRole('button', { name: '读取已有记录 1' });
  expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).value).toBe('919'); expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('未知创建响应尚未核实时不能切换到另一个已有计划', async () => {
  historyPlans = [plan]; intercept = call => call.method === 'POST' && call.path === '/datasets/split-plans' ? Promise.reject(new Error('创建结果待确认')) : undefined;
  setup(); await screen.findByRole('button', { name: '读取已有记录 1' }); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' })); await screen.findByText('创建结果待确认');
  expect((screen.getByRole('button', { name: '读取已有记录 1' }) as HTMLButtonElement).disabled).toBe(true);
});

it('已有列表混入其他项目记录时拒绝展示或选择', async () => {
  historyPlans = [splitPlan({ project_id: 'other-project' })]; setup(); await screen.findByText('已有计划与当前原件不一致，请重新读取。'); expect(screen.queryByRole('button', { name: '读取已有记录 1' })).toBeNull();
});

it('已有计划模型不在当前列表页时显示固定模型编号而非空白', async () => {
  plan = splitPlan({ model_id: 'model-outside-current-page' }); historyPlans = [plan]; setup(); fireEvent.click(await screen.findByRole('button', { name: '读取已有记录 1' }));
  const selector = screen.getByLabelText('划分检查模型') as HTMLSelectElement;
  expect(selector.value).toBe(plan.model_id); expect(selector.selectedOptions[0].textContent).toBe('已保存检查模型 · model-outside-current-page'); expect(selector.selectedOptions[0].disabled).toBe(true);
  expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it.each([['固定划分种子', '-1'], ['固定划分种子', '1.5'], ['固定划分种子', '4294967296'], ['划分最大序列长度', '31'], ['划分最大序列长度', '2049'], ['验证集比例（%）', '0'], ['验证集比例（%）', '100'], ['验证集比例（%）', '20.001']])('输入%s=%s不发起后台检查', async (field, value) => {
  setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.change(screen.getByLabelText(field), { target: { value } });
  expect((screen.getByRole('button', { name: '检查并预览划分' }) as HTMLButtonElement).disabled).toBe(true); expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('被来源组或空子集阻断时展示原因，不提供应用入口', async () => {
  plan = splitPlan({ status: 'blocked', counts: { ...counts, train_samples: 8, validation_samples: 0, validation_groups: 0 }, blocking: [{ code: 'EMPTY_VALIDATION_SPLIT', message: '验证侧没有有效样本，不能应用。' }] });
  setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  await screen.findByText('验证侧没有有效样本，不能应用。'); expect(screen.queryByRole('button', { name: '应用划分，生成新版本' })).toBeNull();
  expect(calls.some(call => call.path === '/datasets/splits')).toBe(false);
});

it('只收到ready但计数为空侧或摘要无效，不能应用', async () => {
  plan = splitPlan({ plan_digest: 'invalid', counts: { ...counts, validation_samples: 0 } }); setup(); await preview();
  expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(true);
});

it('没有新增文件预览时不能仅凭ready应用', async () => {
  plan = splitPlan({ preview: null }); setup(); await preview();
  expect((screen.getByRole('button', { name: '应用划分，生成新版本' }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.some(call => call.path === '/datasets/splits')).toBe(false);
});

it.each(['source_version_id', 'plan_id', 'plan_digest', 'model_id'])('应用响应的%s偏离本次预览时不回写或选择训练', async field => {
  intercept = call => call.path === '/datasets/splits' ? response({ ...applied, split: { ...split, [field]: '其他身份' } }) : undefined;
  const view = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' }));
  await screen.findByText('划分结果与本次预览参数不一致，请重新读取。');
  expect(view.onChanged).not.toHaveBeenCalled(); expect(view.onUseTraining).not.toHaveBeenCalled(); expect(screen.queryByRole('button', { name: '使用训练子集' })).toBeNull();
});

it.each(['source_dataset_id', 'version_id', 'project_id', 'schema', 'status', 'manifest_digest'])('应用结果中训练子集的%s不匹配时不回写列表', async field => {
  intercept = call => call.path === '/datasets/splits' ? response({ ...applied, train_dataset: { ...trainDataset, [field]: '其他身份' } }) : undefined;
  const view = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' }));
  await screen.findByText('划分结果的子集身份或版本不一致，请重新读取。'); expect(view.onChanged).not.toHaveBeenCalled();
});

it('查看既有划分时所选子集版本必须与证明一致', async () => {
  const view = setup({ ...trainDataset, version_id: '其他版本' });
  await screen.findByText('划分结果的子集身份或版本不一致，请重新读取。'); expect(view.onChanged).not.toHaveBeenCalled(); expect(screen.queryByRole('button', { name: '使用训练子集' })).toBeNull();
});

it('读取训练侧时版本被替换则不将其选入草稿', async () => {
  intercept = call => call.path === '/datasets/dataset-train' ? response({ ...trainDataset, version_id: '其他版本' }) : undefined;
  const view = setup(trainDataset); fireEvent.click(await screen.findByRole('button', { name: '使用训练子集' }));
  await screen.findByText('划分结果的子集身份或版本不一致，请重新读取。'); expect(view.onUseTraining).not.toHaveBeenCalled();
});

it('创建响应丢失后固定原参数与幂等键重试，不另起检查', async () => {
  let dropped = false; intercept = call => { if (call.path === '/datasets/split-plans' && !dropped) { dropped = true; throw new Error('检查响应待确认'); } };
  setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  await screen.findByText('检查响应待确认'); expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '重试上次操作' })); await screen.findByRole('button', { name: '应用划分，生成新版本' });
  const writes = calls.filter(call => call.path === '/datasets/split-plans'); expect(writes).toHaveLength(2); expect(writes[0].key).toBe(writes[1].key); expect(writes[0].body).toEqual(writes[1].body);
});

it('应用响应丢失后重试沿原键，不能重复选草稿或创建第二次预览', async () => {
  let dropped = false; intercept = call => { if (call.path === '/datasets/splits' && !dropped) { dropped = true; throw new Error('应用响应待确认'); } };
  const callbacks = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' })); await screen.findByText('应用响应待确认');
  fireEvent.click(screen.getByRole('button', { name: '重试上次操作' })); await screen.findByRole('button', { name: '使用训练子集' });
  const writes = calls.filter(call => call.path === '/datasets/splits'); expect(writes).toHaveLength(2); expect(writes[0].key).toBe(writes[1].key); expect(writes[0].body).toEqual(writes[1].body);
  expect(calls.filter(call => call.path === '/datasets/split-plans')).toHaveLength(1); expect(callbacks.onUseTraining).not.toHaveBeenCalled();
});

it('应用响应未知后GET确认已应用，只读取现有子集而不重发应用', async () => {
  intercept = call => { if (call.path === '/datasets/splits') { plan = splitPlan({ status: 'applied', applied_split_id: split.id, train_dataset_id: trainDataset.id, validation_dataset_id: split.validation_dataset_id }); throw new Error('应用响应待确认'); } };
  setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' })); await screen.findByText('应用响应待确认');
  fireEvent.click(screen.getByRole('button', { name: '重新读取划分' })); await screen.findByRole('button', { name: '使用训练子集' });
  expect(screen.queryByRole('button', { name: '重试上次操作' })).toBeNull(); expect(calls.filter(call => call.path === '/datasets/splits')).toHaveLength(1);
});

it('取消检查等待后台确认，迟到的ready轮询不能重新启用应用', async () => {
  plan = splitPlan({ status: 'preparing', counts: null, plan_digest: null }); const oldRead = deferred<Response>(); let cancelSent = false;
  intercept = call => {
    if (call.path === '/datasets/split-plans/split-plan' && !cancelSent) return oldRead.promise;
    if (call.path.endsWith('/cancel')) { cancelSent = true; plan = splitPlan({ status: 'cancelled' }); return response({ ...plan, status: 'cancelling' }); }
  };
  setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  fireEvent.click(await screen.findByRole('button', { name: '取消本次检查与预览' })); await screen.findByText('本次检查已停止');
  await act(async () => oldRead.resolve(response(splitPlan()))); expect(screen.queryByRole('button', { name: '应用划分，生成新版本' })).toBeNull();
  expect(calls.find(call => call.path.endsWith('/cancel'))).toMatchObject({ method: 'POST', body: {}, key: expect.any(String) });
});

it('控制服务中断不自动复跑，重新预览保留参数', async () => {
  plan = splitPlan({ status: 'recovery_required', counts: null, plan_digest: null }); setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.change(screen.getByLabelText('固定划分种子'), { target: { value: '919' } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  fireEvent.click(await screen.findByRole('button', { name: '保留参数，重新预览' }));
  expect((screen.getByLabelText('固定划分种子') as HTMLInputElement).value).toBe('919'); expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
});

it('库代次失效后的旧预览不显示，重试仍保留原请求参数和编号', async () => {
  const pending = deferred<Response>(); let first = true; intercept = call => { if (call.path === '/datasets/split-plans' && first) { first = false; return pending.promise; } };
  const view = setup(); fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } }); fireEvent.change(screen.getByLabelText('固定划分种子'), { target: { value: '919' } }); fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  epoch++; view.redraw(); await act(async () => pending.resolve(response(splitPlan())));
  expect(screen.queryByRole('button', { name: '应用划分，生成新版本' })).toBeNull(); await screen.findByText(/工作库读取已失效/);
  fireEvent.click(screen.getByRole('button', { name: '保留输入，重新检查' })); await screen.findByRole('button', { name: '应用划分，生成新版本' });
  const writes = calls.filter(call => call.path === '/datasets/split-plans'); expect(writes[1].key).toBe(writes[0].key); expect(writes[1].body.split_seed).toBe(919);
});

it.each(['success', 'failure'])('库代次失效后的应用%s不回写列表、草稿或错误', async outcome => {
  const pending = deferred<Response>(); intercept = call => call.path === '/datasets/splits' ? pending.promise : undefined;
  const view = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' })); epoch++; view.redraw();
  await act(async () => outcome === 'success' ? pending.resolve(response(applied)) : pending.reject(new Error('迟到旧库应用错误')));
  expect(view.onChanged).not.toHaveBeenCalled(); expect(view.onUseTraining).not.toHaveBeenCalled(); expect(screen.queryByText('迟到旧库应用错误')).toBeNull(); expect(screen.queryByRole('button', { name: '使用训练子集' })).toBeNull();
});

it('关闭后迟到的应用结果不触发父级更新', async () => {
  const pending = deferred<Response>(); intercept = call => call.path === '/datasets/splits' ? pending.promise : undefined;
  const view = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' })); view.unmount(); await act(async () => pending.resolve(response(applied))); expect(view.onChanged).not.toHaveBeenCalled();
});

it('已应用划分只GET现有记录，导出指向整份划分且不自动训练', async () => {
  const view = setup(trainDataset); await screen.findByRole('button', { name: '导出原件、子集与证明' });
  fireEvent.click(screen.getByRole('button', { name: '导出原件、子集与证明' })); expect(view.onExport).toHaveBeenCalledWith({ type: 'dataset-split', id: split.id, name: `${trainDataset.name}的数据划分` });
  expect(calls.every(call => call.method === 'GET')).toBe(true); expect(view.onUseTraining).not.toHaveBeenCalled();
});

it('应用已登记但暂存清理待重试时保留子集，重试固定原应用请求', async () => {
  let writes = 0;
  intercept = call => { if (call.path === '/datasets/splits') { writes++; plan = splitPlan({ status: 'applied', applied_split_id: split.id, stage_cleanup_status: writes === 1 ? 'pending' : 'completed' }); return response(applied); } };
  const view = setup(); await preview(); fireEvent.click(screen.getByRole('button', { name: '应用划分，生成新版本' }));
  fireEvent.click(await screen.findByRole('button', { name: '重试清理暂存' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: '重试清理暂存' })).toBeNull());
  expect(screen.getByRole('button', { name: '使用训练子集' })).toBeTruthy(); expect(view.onUseTraining).not.toHaveBeenCalled();
  const commands = calls.filter(call => call.path === '/datasets/splits'); expect(commands).toHaveLength(2); expect(commands[1].key).toBe(commands[0].key); expect(commands[1].body).toEqual(commands[0].body);
  expect(calls.filter(call => call.path === '/datasets/split-plans')).toHaveLength(1);
});

it('重新打开已有划分也能发现并重试暂存清理，失败不撤销已应用数据', async () => {
  const pendingPlan = splitPlan({ status: 'applied', applied_split_id: split.id, stage_cleanup_status: 'pending' });
  intercept = call => call.path === '/datasets/split-plans/split-plan' ? response(pendingPlan) : call.path === '/datasets/splits' ? Promise.reject(new Error('清理响应待确认')) : undefined;
  const view = setup(trainDataset); fireEvent.click(await screen.findByRole('button', { name: '重试清理暂存' }));
  await screen.findByText('清理响应待确认'); expect(screen.getByRole('button', { name: '使用训练子集' })).toBeTruthy(); expect(screen.getByText('已生成训练与验证两个独立版本')).toBeTruthy(); expect(view.onUseTraining).not.toHaveBeenCalled();
  expect(calls.some(call => call.path === '/datasets/split-plans')).toBe(false);
});

it('训练绑定展示精确版本与种子，参数改变后提示重新划分', async () => {
  const view = render(<DatasetSplitBinding dataset={trainDataset} projectId="project-a" model={model} maxSeqLength={512} onInspect={() => {}} />);
  await screen.findByText('查看划分绑定'); expect(screen.getByText('source-version')).toBeTruthy();
  view.rerender(<DatasetSplitBinding dataset={trainDataset} projectId="project-a" model={model} maxSeqLength={768} onInspect={() => {}} />);
  expect(screen.getByText(/当前模型或最大序列长度与划分检查不一致/)).toBeTruthy(); expect(calls.filter(call => call.method === 'POST')).toHaveLength(0);
});

it('相同模型字节的另一登记名称仍兼容已有划分证明', async () => {
  render(<DatasetSplitBinding dataset={trainDataset} projectId="project-a" model={{ ...model, id: 'same-bytes-model-alias' }} maxSeqLength={512} onInspect={() => {}} />);
  await screen.findByText('查看划分绑定'); expect(screen.queryByText(/当前模型或最大序列长度与划分检查不一致/)).toBeNull();
});

it.each(['project_id', 'manifest_digest'])('已选数据的%s变更后立即撤下旧绑定证明', async field => {
  const view = render(<DatasetSplitBinding dataset={trainDataset} projectId="project-a" model={model} maxSeqLength={512} onInspect={() => {}} />);
  await screen.findByText('查看划分绑定'); view.rerender(<DatasetSplitBinding dataset={{ ...trainDataset, [field]: '其他身份' }} projectId="project-a" model={model} maxSeqLength={512} onInspect={() => {}} />);
  expect(screen.queryByText('查看划分绑定')).toBeNull(); await screen.findByText('划分证明与当前数据不一致，请重新读取。');
});

it('训练绑定在切库失败后可重新读取，迟到旧结果不冒充有效证明', async () => {
  const pending = deferred<Response>(); let first = true; intercept = call => { if (call.path === '/datasets/splits/split-a' && first) { first = false; return pending.promise; } };
  const node = () => <LibraryReadContext.Provider value={captureLibraryRead}><DatasetSplitBinding dataset={trainDataset} projectId="project-a" model={model} maxSeqLength={512} onInspect={() => {}} /></LibraryReadContext.Provider>;
  const view = render(node()); epoch++; view.rerender(node()); await act(async () => pending.resolve(response(split))); expect(screen.queryByText('查看划分绑定')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '重新读取来源证明' })); await screen.findByText('查看划分绑定'); expect(calls).toHaveLength(2);
});
