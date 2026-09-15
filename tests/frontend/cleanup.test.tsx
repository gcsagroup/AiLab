import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import CleanupDialog, { type CleanupPlan, type CleanupRecord } from '../../apps/desktop/src/CleanupDialog';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));
let calls: { path: string; method: string; body: unknown; key?: string }[];
let plan: CleanupPlan; let records: CleanupRecord[];
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = []; records = [];
  plan = { id: 'cleanup-plan-a', plan_digest: 'frozen-plan', data_root: '/isolated/library', asset_count: 1, file_count: 2, total_bytes: 2048, retained_asset_count: 3, skipped: [], destination: '/isolated/library/trash', can_execute: true, permanent_delete: false, requires_confirmation: true,
    items: [{ asset_id: 'asset-a', source_path: '/isolated/library/assets/asset-a', total_bytes: 2048, file_count: 2, manifest_digest: 'manifest-a', reason: '当前项目、运行、检查点、备份与恢复记录均未引用此资产。' }] };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let result: unknown = { items: [] };
    if (path === '/cleanups' && method === 'GET') result = { items: records, unreadable_records: [] };
    if (path === '/cleanup-plans') result = plan;
    if (path === '/cleanups' && method === 'POST') {
      records = [{ id: 'cleanup-a', state: 'trashed', created_at: '2026-09-10T04:00:00Z', asset_count: plan.asset_count, file_count: plan.file_count, total_bytes: plan.total_bytes, can_restore: true,
        items: plan.items.map(item => ({ ...item, trash_path: '/isolated/library/trash/items/cleanup-a/asset-a' })) }];
      result = records[0];
    }
    if (path.endsWith('/restore')) { records = records.map(item => ({ ...item, state: 'restored', can_restore: false, restored_at: '2026-09-10T04:01:00Z' })); result = records[0]; }
    return { ok: true, json: async () => result };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function inspect() {
  fireEvent.click(screen.getByRole('button', { name: '检查可清理资产' }));
  await screen.findByRole('region', { name: '已检查的清理范围' });
}
async function move() {
  await inspect(); fireEvent.click(screen.getByRole('button', { name: '将 1 个资产移入回收区' }));
  await screen.findByRole('button', { name: '恢复到原位置' });
}

describe('本库可恢复清理', () => {
  it('入口位于设备与环境的数据管理区，首次打开只读取历史', async () => {
    render(<App />);
    await waitFor(() => expect(calls.some(call => call.path === '/projects')).toBe(true));
    fireEvent.click(screen.getByRole('button', { name: '设备与环境' }));
    const management = screen.getByRole('region', { name: '本机数据管理' });
    await waitFor(() => expect((within(management).getByRole('button', { name: '存储清理与恢复' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(management).getByRole('button', { name: '存储清理与恢复' }));
    await screen.findByRole('dialog', { name: '存储清理与恢复' });
    await waitFor(() => expect(calls.some(call => call.path === '/cleanups')).toBe(true));
    expect(calls.filter(call => call.method === 'POST')).toEqual([]);
  });
  it('先显示精确位置、大小、理由与保留范围，明确执行后才移动；恢复也是独立点击', async () => {
    render(<CleanupDialog onClose={() => {}} />);
    await inspect();
    expect(screen.getByText('/isolated/library/assets/asset-a')).toBeTruthy();
    expect(screen.getByText(plan.items[0].reason)).toBeTruthy();
    expect(screen.getByText('3 个已有引用的资产')).toBeTruthy();
    expect(screen.getAllByText('2 个文件 · 2.0 KB').length).toBeGreaterThan(0);
    expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/cleanup-plans']);
    fireEvent.click(screen.getByRole('button', { name: '将 1 个资产移入回收区' }));
    await screen.findByText('可以恢复');
    expect(calls.find(call => call.path === '/cleanups' && call.method === 'POST')?.body).toEqual({ plan_id: plan.id, plan_digest: plan.plan_digest });
    expect(calls.some(call => call.path.endsWith('/restore'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: '恢复到原位置' }));
    await screen.findByText('已恢复');
    expect(screen.queryByRole('button', { name: '恢复到原位置' })).toBeNull();
    expect(screen.getByText(/不会立即释放磁盘空间/)).toBeTruthy();
  });
  it('零对象显示无需清理，不展示移动操作', async () => {
    plan = { ...plan, asset_count: 0, file_count: 0, total_bytes: 0, items: [], can_execute: false };
    render(<CleanupDialog onClose={() => {}} />); await inspect();
    expect(screen.getByText('没有可清理资产')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /移入回收区/ })).toBeNull();
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
  });
  it('移动响应丢失时保留冻结范围与原命令，重试核实同一次清理', async () => {
    render(<CleanupDialog onClose={() => {}} />); await inspect();
    const normal = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await normal(input, init); if (String(input).endsWith('/cleanups') && init?.method === 'POST' && !dropped) { dropped = true; throw new Error('移动响应丢失'); } return result; });
    fireEvent.click(screen.getByRole('button', { name: '将 1 个资产移入回收区' }));
    await screen.findByText('移动响应丢失');
    fireEvent.click(screen.getByRole('button', { name: '核实并继续原清理' }));
    await screen.findByText('可以恢复');
    const requests = calls.filter(call => call.path === '/cleanups' && call.method === 'POST');
    expect(requests).toHaveLength(2); expect(requests[0].key).toBe(requests[1].key); expect(requests[0].body).toEqual(requests[1].body);
  });
  it('恢复响应丢失后重新打开窗口仍使用原恢复命令，不新增清理', async () => {
    const first = render(<CleanupDialog onClose={() => {}} />); await move();
    const normal = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await normal(input, init); if (String(input).endsWith('/restore') && !dropped) { dropped = true; records = records.map(item => ({ ...item, state: 'restoring', can_restore: true })); throw new Error('恢复响应丢失'); } return result; });
    fireEvent.click(screen.getByRole('button', { name: '恢复到原位置' })); await screen.findByText('恢复响应丢失');
    first.unmount(); render(<CleanupDialog onClose={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: /回收区与历史/ }));
    fireEvent.click(await screen.findByRole('button', { name: '核实并继续恢复' })); await screen.findByText('已恢复');
    const requests = calls.filter(call => call.path.endsWith('/restore'));
    expect(requests).toHaveLength(2); expect(requests[0].key).toBe(requests[1].key);
    expect(calls.filter(call => call.path === '/cleanups' && call.method === 'POST')).toHaveLength(1);
  });
  it('原位置被占用时展示拒绝原因并保留恢复入口', async () => {
    render(<CleanupDialog onClose={() => {}} />); await move();
    const normal = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) => String(input).endsWith('/restore') ? { ok: false, json: async () => ({ error: { code: 'CLEANUP_TARGET_EXISTS', message: '原位置已有内容，未覆盖文件；回收副本仍保留。' } }) } as Response : normal(input, init));
    fireEvent.click(screen.getByRole('button', { name: '恢复到原位置' }));
    await screen.findByText('原位置已有内容，未覆盖文件；回收副本仍保留。');
    expect(screen.getByRole('button', { name: '恢复到原位置' })).toBeTruthy();
    expect(screen.queryByText('已恢复')).toBeNull();
  });
});
