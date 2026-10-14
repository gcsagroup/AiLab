import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ImportDialog from '../../apps/desktop/src/ImportDialog';
import { api, canPickFile, pickImport } from '../../apps/desktop/src/api';

vi.mock('../../apps/desktop/src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../../apps/desktop/src/api')>(),
  api: vi.fn(), canPickFile: vi.fn(), pickImport: vi.fn(),
}));
const rejected = { id: 'bad', can_import: false, issues: [{ line: 1, message: 'JSON 格式无效，请检查第 15 列附近的内容。' }] };
const accepted = { id: 'good', can_import: true, sample_count: 1 };
const path = '/中文路径/带 空格 的目录/样本.jsonl';
beforeEach(() => {
  vi.mocked(api).mockReset(); vi.mocked(pickImport).mockReset(); vi.mocked(canPickFile).mockReturnValue(false);
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(cleanup);
function mount() {
  render(<ImportDialog kind="dataset" projectId="forms-project" onClose={vi.fn()} onImported={vi.fn()} />);
  const field = screen.getByLabelText('数据集文件路径');
  if (!canPickFile()) fireEvent.change(field, { target: { value: path } });
  return field;
}
function description(element: HTMLElement) {
  return (element.getAttribute('aria-describedby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ');
}

it('检查失败后焦点进入结果，路径关联行号错误，确认仍被禁止', async () => {
  vi.mocked(api).mockResolvedValue(rejected); const field = mount();
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('region', { name: '导入检查结果' })));
  expect(field.getAttribute('aria-invalid')).toBe('true');
  expect(description(field)).toContain('第 1 行：JSON 格式无效');
  expect((screen.getByRole('button', { name: '确认导入' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('button', { name: '重新检查数据集' })).toBeTruthy();
});

it('源文件修正后可原位重新检查，旧错误关联清除且仍需明确确认导入', async () => {
  vi.mocked(api).mockResolvedValueOnce(rejected).mockResolvedValueOnce(accepted); const field = mount();
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  await userEvent.click(await screen.findByRole('button', { name: '重新检查数据集' }));
  await waitFor(() => expect(field.getAttribute('aria-invalid')).toBe('false'));
  expect(description(field)).toBe(''); expect(screen.queryByRole('alert')).toBeNull();
  expect((screen.getByRole('button', { name: '确认导入' }) as HTMLButtonElement).disabled).toBe(false);
  expect(api).toHaveBeenCalledTimes(2);
  expect(api).toHaveBeenLastCalledWith('POST', '/datasets/import-plans', expect.objectContaining({ path }));
});

it('用户已经把焦点移开时，异步检查结果不抢走焦点', async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(api).mockImplementationOnce(() => new Promise(done => { resolve = done; })); mount();
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  const dialog = screen.getByRole('dialog'); dialog.focus();
  resolve(rejected); await screen.findByText(/第 1 行：JSON 格式无效/);
  expect(document.activeElement).toBe(dialog);
});

it('服务失败时保留检查入口焦点，不把连接错误标为文件错误', async () => {
  vi.mocked(api).mockRejectedValue(new Error('服务连接中断')); const field = mount();
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  await screen.findByText('服务连接中断');
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '检查数据集' }));
  expect(field.getAttribute('aria-invalid')).toBe('false');
});

it('重新检查失败时撤销旧的可导入结论，不能继续确认旧计划', async () => {
  vi.mocked(api).mockResolvedValueOnce(accepted).mockRejectedValueOnce(new Error('服务连接中断')); mount();
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  await userEvent.click(await screen.findByRole('button', { name: '重新检查数据集' }));
  await screen.findByText('服务连接中断');
  expect(screen.queryByRole('button', { name: '确认导入' })).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '检查数据集' }));
});

it('原生选择按钮名称明确并关联错误；取消选择保留错误，换文件清除错误', async () => {
  vi.mocked(canPickFile).mockReturnValue(true);
  vi.mocked(pickImport).mockResolvedValueOnce({ path }).mockResolvedValueOnce(null).mockResolvedValueOnce({ path: '/新目录/有效样本.jsonl' });
  vi.mocked(api).mockResolvedValueOnce(rejected); const field = mount();
  await userEvent.click(screen.getByRole('button', { name: '选择数据集文件' }));
  await userEvent.click(screen.getByRole('button', { name: '检查数据集' }));
  const choose = screen.getByRole('button', { name: '选择数据集文件' });
  expect(description(choose)).toContain('第 1 行：JSON 格式无效');
  await userEvent.click(choose); expect(description(field)).toContain('JSON 格式无效');
  await userEvent.click(choose);
  expect((field as HTMLInputElement).value).toBe('/新目录/有效样本.jsonl');
  expect(field.getAttribute('aria-invalid')).toBe('false'); expect(description(field)).toBe('');
});

it('检查期间入口保持可聚焦但不能重复提交', async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(api).mockImplementationOnce(() => new Promise(done => { resolve = done; })); mount();
  const button = screen.getByRole('button', { name: '检查数据集' });
  await userEvent.click(button); await userEvent.click(button);
  expect(document.activeElement).toBe(button); expect(button.getAttribute('aria-disabled')).toBe('true');
  expect(api).toHaveBeenCalledTimes(1);
  resolve(accepted); await screen.findByRole('button', { name: '确认导入' });
});
