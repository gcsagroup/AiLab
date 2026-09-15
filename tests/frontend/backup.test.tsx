import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import BackupDialog from '../../apps/desktop/src/BackupDialog';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
let calls: { path: string; method: string; body: unknown; key?: string }[];
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let response: unknown = { items: [] };
    if (method === 'POST' && path === '/backups') response = { id: 'backup-a', backup_path: '/backups/a', created_at: '2026-09-10T04:00:00Z', file_count: 8, total_bytes: 2048, manifest_digest: 'fixed', contains_asset_files: true };
    if (path === '/restore-plans') response = { id: 'plan-a', plan_digest: 'planned', manifest_digest: 'fixed', can_restore: true, blocking: [], file_count: 8, total_bytes: 2048, restored_path: '/target/ailab-restored-a', changes_current_library: false, evidence_policy: '原运行证据保留' };
    if (method === 'POST' && path === '/restores') response = { id: 'restore-a', state: 'succeeded', restored_path: '/target/ailab-restored-a', file_count: 8, changes_current_library: false, verified: true };
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('完整备份与隔离恢复', () => {
  it('创建备份响应丢失可复用同一命令，成功后选择备份进入恢复准备', async () => {
    render(<BackupDialog onClose={() => {}} onLibraryChanged={() => {}} />);
    await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(2));
    const normal = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const response = await normal(input, init); if (init?.method === 'POST' && !dropped) { dropped = true; throw new Error('备份响应丢失'); } return response; });
    fireEvent.click(screen.getByRole('button', { name: '创建完整备份' }));
    await screen.findByText('备份响应丢失');
    fireEvent.click(screen.getByRole('button', { name: '创建完整备份' }));
    fireEvent.click(await screen.findByRole('button', { name: '使用此备份恢复' }));
    expect((screen.getByLabelText('备份包目录') as HTMLInputElement).value).toBe('/backups/a');
    const requests = calls.filter(call => call.method === 'POST');
    expect(requests).toHaveLength(2); expect(requests[1].key).toBe(requests[0].key);
  });
  it('恢复检查不复制或切库，明确恢复后展示新目录；浏览器不具有宿主切库入口', async () => {
    const changed = vi.fn(); render(<BackupDialog onClose={() => {}} onLibraryChanged={changed} />);
    fireEvent.click(screen.getByRole('tab', { name: '从备份恢复' }));
    fireEvent.change(screen.getByLabelText('备份包目录'), { target: { value: '/backups/a' } });
    fireEvent.change(screen.getByLabelText('恢复保存目录'), { target: { value: '/target' } });
    fireEvent.click(screen.getByRole('button', { name: '检查恢复范围' }));
    await screen.findByRole('button', { name: '恢复到新目录' });
    expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/restore-plans']);
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '恢复到新目录' }));
    await screen.findByText('已恢复到独立目录');
    expect(screen.getByText('/target/ailab-restored-a')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '切换到恢复的工作库' })).toBeNull();
    expect(calls.find(call => call.path === '/restores' && call.method === 'POST')?.body).toEqual({ plan_id: 'plan-a', plan_digest: 'planned' });
    expect(changed).not.toHaveBeenCalled();
  });
  it('恢复请求未明时保持计划和命令编号，重试不新建另一个恢复目标', async () => {
    render(<BackupDialog onClose={() => {}} onLibraryChanged={() => {}} />);
    fireEvent.click(screen.getByRole('tab', { name: '从备份恢复' }));
    fireEvent.change(screen.getByLabelText('备份包目录'), { target: { value: '/backups/a' } });
    fireEvent.change(screen.getByLabelText('恢复保存目录'), { target: { value: '/target' } });
    fireEvent.click(screen.getByRole('button', { name: '检查恢复范围' }));
    await screen.findByRole('button', { name: '恢复到新目录' });
    const normal = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const response = await normal(input, init); if (String(input).endsWith('/restores') && init?.method === 'POST' && !dropped) { dropped = true; throw new Error('恢复响应待确认'); } return response; });
    fireEvent.click(screen.getByRole('button', { name: '恢复到新目录' }));
    await screen.findByText('恢复响应待确认');
    fireEvent.click(screen.getByRole('button', { name: '恢复到新目录' }));
    await screen.findByText('已恢复到独立目录');
    const requests = calls.filter(call => call.method === 'POST' && call.path === '/restores');
    expect(requests).toHaveLength(2); expect(requests[1].key).toBe(requests[0].key); expect(requests[1].body).toEqual(requests[0].body);
  });
});
