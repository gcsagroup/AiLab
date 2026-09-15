import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import ImportDialog from '../../apps/desktop/src/ImportDialog';
import { EvaluationPlanDialog } from '../../apps/desktop/src/Evaluation';
import { api, pickImport } from '../../apps/desktop/src/api';

vi.mock('../../apps/desktop/src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../../apps/desktop/src/api')>(),
  api: vi.fn(), pickImport: vi.fn(), canPickFile: () => true,
}));
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const selection = { path: '/old/data.jsonl', grant_id: 'grant-old' };
const plan = { id: 'plan-old', plan_id: 'plan-old', manifest_digest: 'digest', can_import: true, blocking: [], issues: [], name: '旧检查结果' };
beforeEach(() => {
  vi.mocked(api).mockReset(); vi.mocked(pickImport).mockReset();
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
});
afterEach(cleanup);

it.each(['import', 'evaluation'] as const)('%s：旧项目 picker 的迟到选择不会填进新项目表单', async kind => {
  const pending = deferred<typeof selection>(); vi.mocked(pickImport).mockReturnValue(pending.promise);
  const component = (projectId: string) => kind === 'import'
    ? <ImportDialog kind="dataset" projectId={projectId} onClose={() => {}} onImported={() => {}} />
    : <EvaluationPlanDialog projectId={projectId} onClose={() => {}} onCreated={() => {}} />;
  const view = render(component('project-a'));
  fireEvent.click(screen.getByRole('button', { name: kind === 'import' ? '选择' : '选择文件' }));
  view.rerender(component('project-b'));
  await act(async () => pending.resolve(selection));
  expect((screen.getByLabelText(kind === 'import' ? '数据集文件路径' : '评测 JSONL 文件') as HTMLInputElement).value).toBe('');
  expect(api).not.toHaveBeenCalled();
});

it.each(['success', 'error'] as const)('导入检查的迟到%s不会覆盖新项目', async outcome => {
  vi.mocked(pickImport).mockResolvedValue(selection);
  const pending = deferred<typeof plan>(); vi.mocked(api).mockReturnValue(pending.promise);
  const component = (projectId: string) => <ImportDialog kind="dataset" projectId={projectId} onClose={() => {}} onImported={() => {}} />;
  const view = render(component('project-a'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '选择' })));
  fireEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  view.rerender(component('project-b'));
  await act(async () => outcome === 'success' ? pending.resolve(plan) : pending.reject(new Error('旧项目检查错误')));
  expect(screen.queryByText('旧检查结果')).toBeNull();
  expect(screen.queryByText('旧项目检查错误')).toBeNull();
  expect(screen.queryByRole('button', { name: /确认导入/ })).toBeNull();
});

it('导入保存迟到时不触发旧实例的 onImported 或关闭新表单', async () => {
  vi.mocked(pickImport).mockResolvedValue(selection);
  const pending = deferred<unknown>(); vi.mocked(api).mockResolvedValueOnce(plan).mockReturnValueOnce(pending.promise);
  const imported = vi.fn(); const closed = vi.fn();
  const component = (projectId: string) => <ImportDialog key={projectId} kind="dataset" projectId={projectId} onClose={closed} onImported={imported} />;
  const view = render(component('project-a'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '选择' })));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '检查数据集' })));
  fireEvent.click(screen.getByRole('button', { name: /确认导入/ }));
  view.rerender(component('project-b'));
  await act(async () => pending.resolve({ id: 'dataset-old' }));
  expect(imported).not.toHaveBeenCalled(); expect(closed).not.toHaveBeenCalled();
  expect((screen.getByLabelText('数据集文件路径') as HTMLInputElement).value).toBe('');
});

it('评测保存迟到时不触发旧实例的 onCreated 或关闭新表单', async () => {
  vi.mocked(pickImport).mockResolvedValue(selection);
  const pending = deferred<unknown>(); vi.mocked(api).mockReturnValue(pending.promise);
  const created = vi.fn(); const closed = vi.fn();
  const component = (projectId: string) => <EvaluationPlanDialog key={projectId} projectId={projectId} onClose={closed} onCreated={created} />;
  const view = render(component('project-a'));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '选择文件' })));
  fireEvent.click(screen.getByRole('button', { name: '检查并冻结方案' }));
  view.rerender(component('project-b'));
  await act(async () => pending.resolve({ id: 'evaluation-old' }));
  expect(created).not.toHaveBeenCalled(); expect(closed).not.toHaveBeenCalled();
  expect(screen.queryByText('评测数据与规则已保存为独立版本')).toBeNull();
});

it('同项目正常导入的重试保留幂等编号并只在成功后回调', async () => {
  vi.mocked(pickImport).mockResolvedValue(selection);
  vi.mocked(api).mockResolvedValueOnce(plan).mockRejectedValueOnce(new Error('回执待确认')).mockResolvedValueOnce({ id: 'dataset-new' });
  const imported = vi.fn(); render(<ImportDialog kind="dataset" projectId="project-a" onClose={() => {}} onImported={imported} />);
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '选择' })));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '检查数据集' })));
  await act(async () => fireEvent.click(screen.getByRole('button', { name: /确认导入/ })));
  expect(imported).not.toHaveBeenCalled();
  await act(async () => fireEvent.click(screen.getByRole('button', { name: /确认导入/ })));
  expect(imported).toHaveBeenCalledTimes(1);
  expect(vi.mocked(api).mock.calls[0]).toMatchObject(['POST', '/datasets/import-plans', { project_id: 'project-a', ...selection }]);
  expect(vi.mocked(api).mock.calls[1][3]).toBeTruthy();
  expect(vi.mocked(api).mock.calls[1][3]).toBe(vi.mocked(api).mock.calls[2][3]);
});

it('同项目切换导入类别后拒绝旧选择，新的模型选择仍可继续', async () => {
  const old = deferred<typeof selection>(); vi.mocked(pickImport).mockReturnValueOnce(old.promise).mockResolvedValueOnce({ path: '/models/new', grant_id: 'grant-new' });
  const component = (kind: 'dataset' | 'model') => <ImportDialog key={`project-a:${kind}`} kind={kind} projectId="project-a" onClose={() => {}} onImported={() => {}} />;
  const view = render(component('dataset'));
  fireEvent.click(screen.getByRole('button', { name: '选择' }));
  view.rerender(component('model'));
  await act(async () => old.resolve(selection));
  expect((screen.getByLabelText('模型文件路径') as HTMLInputElement).value).toBe('');
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '选择' })));
  expect((screen.getByLabelText('模型文件路径') as HTMLInputElement).value).toBe('/models/new');
  expect(api).not.toHaveBeenCalled();
});

it.each(['import', 'evaluation'] as const)('%s：同项目取消 picker 不覆盖已有选择或发送写入', async kind => {
  vi.mocked(pickImport).mockResolvedValueOnce(selection).mockResolvedValueOnce(null);
  render(kind === 'import'
    ? <ImportDialog kind="dataset" projectId="project-a" onClose={() => {}} onImported={() => {}} />
    : <EvaluationPlanDialog projectId="project-a" onClose={() => {}} onCreated={() => {}} />);
  const button = screen.getByRole('button', { name: kind === 'import' ? '选择' : '选择文件' });
  await act(async () => fireEvent.click(button));
  await act(async () => fireEvent.click(button));
  expect((screen.getByLabelText(kind === 'import' ? '数据集文件路径' : '评测 JSONL 文件') as HTMLInputElement).value).toBe(selection.path);
  expect(api).not.toHaveBeenCalled();
  expect(button.matches(':disabled')).toBe(false);
});
