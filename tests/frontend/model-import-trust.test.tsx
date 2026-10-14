import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ImportDialog from '../../apps/desktop/src/ImportDialog';
import { api } from '../../apps/desktop/src/api';
import type { ImportPlan } from '../../apps/desktop/src/types';

vi.mock('../../apps/desktop/src/api', async importOriginal => ({
  ...await importOriginal<typeof import('../../apps/desktop/src/api')>(), api: vi.fn(), canPickFile: () => false,
}));
const boundary = { scope_semantics: 'loader_policy_not_os_permissions', process: 'separate_process', os_sandbox: false, filesystem: 'current_user_permissions', network: 'offline_loader_options_not_os_block', credentials: 'environment_allowlist_not_filesystem_denial', custom_code: 'not_supported' };
const plan: ImportPlan = { id: 'plan-trust', path: '/model', can_import: true, manifest_digest: 'digest', trust_class: 'restricted_weights', loader: 'mlx_lm.local_restricted', execution_boundary: boundary };
beforeEach(() => {
  vi.mocked(api).mockReset();
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(cleanup);

async function inspect(response: ImportPlan, kind: 'model' | 'dataset' = 'model') {
  vi.mocked(api).mockResolvedValueOnce(response).mockResolvedValueOnce({ id: 'imported' });
  const imported = vi.fn();
  render(<ImportDialog kind={kind} projectId="project-trust" onClose={vi.fn()} onImported={imported} />);
  const label = kind === 'model' ? '模型' : '数据集';
  fireEvent.change(screen.getByLabelText(`${label}文件路径`), { target: { value: '/model' } });
  fireEvent.click(screen.getByRole('button', { name: `检查${label}` }));
  const confirm = await screen.findByRole('button', { name: '确认导入' });
  return { confirm: confirm as HTMLButtonElement, imported };
}

it.each([
  ['restricted_weights', 'mlx_lm.local_restricted', '受限权重 · 本机 MLX 加载器'],
  ['restricted_weights', 'diffusers.fixed_local_safetensors', '受限权重 · 固定媒体 safetensors 加载器'],
  ['restricted_official_torch', 'kokoro.fixed_official_weights_only_cpu', '固定官方权重 · Kokoro 受限加载器'],
])('导入前展示 %s / %s 的加载信任，只有明确确认才导入', async (trust_class, loader, label) => {
  const { confirm, imported } = await inspect({ ...plan, trust_class, loader });
  expect(screen.getByText(label)).toBeTruthy();
  expect(screen.getByText(/未启用操作系统沙箱/)).toBeTruthy();
  expect(screen.getByText(/不代表系统已阻断网络/)).toBeTruthy();
  expect(screen.getByText(/不代表系统已阻止读取凭证文件/)).toBeTruthy();
  expect(api).toHaveBeenCalledTimes(1);
  expect(confirm.disabled).toBe(false);
  fireEvent.click(confirm);
  await waitFor(() => expect(imported).toHaveBeenCalledOnce());
  expect(api).toHaveBeenLastCalledWith('POST', '/models/imports', { plan_id: 'plan-trust', manifest_digest: 'digest' }, expect.any(String));
});

it.each([
  { execution_boundary: undefined }, { trust_class: 'unknown' }, { loader: 'custom.loader' },
  { trust_class: 'restricted_official_torch' },
  { execution_boundary: { ...boundary, os_sandbox: true } },
  { execution_boundary: { ...boundary, network: 'unknown' } },
])('说明缺失或未知时不显示已知权限，也不能提交：%j', async override => {
  const { confirm, imported } = await inspect({ ...plan, ...override });
  expect(screen.getByText(/模型加载信任或权限说明缺失、未知/)).toBeTruthy();
  expect(screen.queryByLabelText('模型加载与权限说明')).toBeNull();
  expect(confirm.disabled).toBe(true);
  fireEvent.click(confirm);
  expect(api).toHaveBeenCalledTimes(1); expect(imported).not.toHaveBeenCalled();
});

it('后端拒绝的模型不会因已知加载说明而获准导入', async () => {
  const { confirm } = await inspect({ ...plan, can_import: false, blocking: [{ message: '模型来源未通过检查' }] });
  expect(screen.getByText('模型来源未通过检查')).toBeTruthy();
  expect(confirm.disabled).toBe(true); fireEvent.click(confirm); expect(api).toHaveBeenCalledTimes(1);
});

it('数据导入不要求模型加载说明', async () => {
  const { confirm, imported } = await inspect({ id: 'data-plan', path: '/model', can_import: true }, 'dataset');
  expect(screen.queryByText('加载信任')).toBeNull(); expect(confirm.disabled).toBe(false);
  fireEvent.click(confirm); await waitFor(() => expect(imported).toHaveBeenCalledOnce());
});

it('数据检查显示原文件行号，拒绝导入并保留未编号错误', async () => {
  const { confirm, imported } = await inspect({
    id: 'data-plan', path: '/data.jsonl', can_import: false,
    issues: [{ line: 2, message: 'JSON 格式无效，请检查第 1 列附近的内容。' }, { message: '文件检查未通过' }],
  }, 'dataset');
  expect(screen.getByText('第 2 行：JSON 格式无效，请检查第 1 列附近的内容。')).toBeTruthy();
  expect(screen.getByText('文件检查未通过')).toBeTruthy();
  expect(confirm.disabled).toBe(true);
  fireEvent.click(confirm);
  expect(api).toHaveBeenCalledTimes(1); expect(imported).not.toHaveBeenCalled();
});
