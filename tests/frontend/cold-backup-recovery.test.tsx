import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';
import { invalidateNativeConnection, type NativeStatus } from '../../apps/desktop/src/api';

const host = vi.hoisted(() => ({ listeners: new Map<string, (event: { payload: any }) => void>() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { host.listeners.set(name, listener); return () => { if (host.listeners.get(name) === listener) host.listeners.delete(name); }; }) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => true, invoke: vi.fn() }));
let status: NativeStatus, requests: { path: string; method: string; body: any; recovery: boolean }[];
let source: string, inspectionFailure: boolean, switchFailure: boolean;
let beginGate: Promise<void> | undefined, copyGate: Promise<void> | undefined;
const restored = { id: 'restore-a', state: 'succeeded', verified: true, restored_path: '/target/restored-a', file_count: 2, changes_current_library: false };
async function emit(name: string, payload: unknown) { await act(async () => { host.listeners.get(name)?.({ payload }); }); }
beforeEach(() => {
  invalidateNativeConnection(); host.listeners.clear(); requests = []; source = '/backup/a'; inspectionFailure = false; switchFailure = false; beginGate = undefined; copyGate = undefined;
  status = { state: 'failed', message: '迁移未完成，原数据已保留', recovery_mode: false };
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
  vi.mocked(invoke).mockReset().mockImplementation(async (command, args) => {
    if (command === 'host_status') return { ...status };
    if (command === 'begin_backup_recovery') {
      status = { state: 'running', recovery_mode: true, connection_id: 'scratch' };
      host.listeners.get('host-status')?.({ payload: { ...status } });
      await beginGate; return { ...status };
    }
    if (command === 'pick_import_path') return { path: source, grant_id: source };
    if (command === 'pick_export_directory') return { path: '/target', grant_id: 'target' };
    if (command === 'use_restored_library') {
      if (switchFailure) throw new Error('恢复库启动失败，继续保留恢复区');
      status = { state: 'running', recovery_mode: false, connection_id: 'restored' };
      host.listeners.get('host-status')?.({ payload: { ...status } });
      return {};
    }
    if (command !== 'api_request') return {};
    const input = (args as any).request;
    const request = { path: input.path.replace('/api/v1', ''), method: input.method, body: input.body, recovery: status.recovery_mode === true };
    requests.push(request);
    if (request.path === '/restore-plans') {
      if (inspectionFailure) throw new Error('备份不完整，请重新选择');
      return { id: 'plan-a', plan_digest: 'digest', can_restore: true, blocking: [], file_count: 2, total_bytes: 300, restored_path: restored.restored_path, changes_current_library: false, evidence_policy: '保留原证据' };
    }
    if (request.path === '/restores' && request.method === 'POST') { await copyGate; return restored; }
    if (request.path === '/ui-context') return { project_id: null, projects: {} };
    return { items: [] };
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const commands = (name: string) => vi.mocked(invoke).mock.calls.filter(([command]) => command === name);
function expectRecoveryOnly() {
  expect(requests.filter(request => request.recovery).every(request => ['/restores', '/restore-plans'].includes(request.path))).toBe(true);
  expect(screen.queryByRole('navigation', { name: '主导航' })).toBeNull();
  expect(screen.queryByRole('button', { name: '新建项目' })).toBeNull();
  expect(screen.queryByRole('button', { name: '设备与环境' })).toBeNull();
  expect(screen.queryByRole('tab', { name: '创建与查看备份' })).toBeNull();
}
async function openRecovery() {
  render(<App />);
  await screen.findByText('迁移未完成，原数据已保留');
  fireEvent.click(screen.getByRole('button', { name: '从备份恢复' }));
  await screen.findByRole('dialog', { name: '备份与恢复' });
}
async function selectAndInspect() {
  fireEvent.click(screen.getByRole('button', { name: '选择备份' }));
  await waitFor(() => expect((screen.getByLabelText('备份包目录') as HTMLInputElement).value).toBe(source));
  fireEvent.click(screen.getByRole('button', { name: '选择位置' }));
  await waitFor(() => expect((screen.getByLabelText('恢复保存目录') as HTMLInputElement).value).toBe('/target'));
  fireEvent.click(screen.getByRole('button', { name: '检查恢复范围' }));
}
it('冷启动失败可明确进入恢复；提前健康事件与待决命令不会启动普通读取', async () => {
  let finish!: () => void; beginGate = new Promise<void>(resolve => { finish = resolve; });
  render(<App />); await screen.findByText('迁移未完成，原数据已保留');
  expect(requests).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: '从备份恢复' }));
  await waitFor(() => expect(commands('begin_backup_recovery')).toHaveLength(1));
  expect(requests).toEqual([]);
  await act(async () => finish());
  await screen.findByRole('dialog', { name: '备份与恢复' });
  await waitFor(() => expect(requests.map(request => request.path)).toEqual(['/restores']));
  expectRecoveryOnly();
});
it('冷启动已处于恢复模式时不读取项目、偏好或环境，关闭后能重开', async () => {
  status = { state: 'running', recovery_mode: true, connection_id: 'scratch' };
  render(<App />); await screen.findByRole('heading', { name: '从备份恢复工作库' });
  expect(requests).toEqual([]); expectRecoveryOnly();
  fireEvent.click(screen.getByRole('button', { name: '选择备份继续恢复' }));
  await screen.findByRole('dialog', { name: '备份与恢复' });
  fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect(screen.queryByRole('dialog')).toBeNull(); expectRecoveryOnly();
  fireEvent.click(screen.getByRole('button', { name: '选择备份继续恢复' }));
  await screen.findByRole('dialog', { name: '备份与恢复' });
  expect(commands('begin_backup_recovery')).toHaveLength(0); expectRecoveryOnly();
});
it('恢复检查失败后可重选；成功恢复仍需明确切库，之后才加载普通工作台', async () => {
  await openRecovery(); inspectionFailure = true; await selectAndInspect();
  await screen.findByText('备份不完整，请重新选择');
  source = '/backup/b'; inspectionFailure = false;
  await selectAndInspect();
  fireEvent.click(await screen.findByRole('button', { name: '恢复到新目录' }));
  await screen.findByText('已恢复到独立目录');
  expect(commands('use_restored_library')).toHaveLength(0); expectRecoveryOnly();
  expect(requests.filter(request => request.path === '/restore-plans').map(request => request.body.backup_path)).toEqual(['/backup/a', '/backup/b']);
  fireEvent.click(screen.getByRole('button', { name: '切换到恢复的工作库' }));
  await screen.findByText('建立你的第一个项目');
  expect(screen.queryByRole('heading', { name: '从备份恢复工作库' })).toBeNull();
  expect(requests.some(request => !request.recovery && request.path === '/projects')).toBe(true);
  expect(requests.filter(request => request.recovery).map(request => request.path)).toEqual(['/restores', '/restore-plans', '/restore-plans', '/restores']);
});
it('切库失败保留恢复区和重选入口，不补发环境或偏好请求', async () => {
  await openRecovery(); await selectAndInspect();
  fireEvent.click(await screen.findByRole('button', { name: '恢复到新目录' }));
  switchFailure = true;
  fireEvent.click(await screen.findByRole('button', { name: '切换到恢复的工作库' }));
  await screen.findByText('恢复库启动失败，继续保留恢复区'); expectRecoveryOnly();
  fireEvent.click(screen.getByRole('button', { name: '恢复另一份备份' }));
  await screen.findByRole('button', { name: '选择备份' }); expectRecoveryOnly();
});
it('冷启动失败且从未载入工作库时可直接退出，不要求先恢复或保存选择', async () => {
  render(<App />); await screen.findByText('迁移未完成，原数据已保留');
  await emit('prepare-exit', { request_id: 40, cancelled: false });
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 40, success: true }));
  expect(requests).toEqual([]);
  expect(commands('begin_backup_recovery')).toHaveLength(0);
});
it('恢复区原生退出完成应答，不保存普通工作库偏好', async () => {
  await openRecovery(); await emit('prepare-exit', { request_id: 41, cancelled: false });
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 41, success: true }));
  expect(requests.map(request => request.path)).toEqual(['/restores']);
});
it('恢复服务停止后重开入口重新启动恢复服务', async () => {
  await openRecovery(); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  status = { state: 'failed', recovery_mode: true, message: '恢复服务已停止' };
  await emit('host-status', status);
  fireEvent.click(screen.getByRole('button', { name: '选择备份继续恢复' }));
  await screen.findByRole('dialog', { name: '备份与恢复' });
  expect(commands('begin_backup_recovery')).toHaveLength(2); expectRecoveryOnly();
});

it('恢复复制未结束时禁止关闭并拒绝原生退出，复制结束后可正常退出', async () => {
  let finish!: () => void; copyGate = new Promise<void>(resolve => { finish = resolve; });
  await openRecovery(); await selectAndInspect();
  fireEvent.click(await screen.findByRole('button', { name: '恢复到新目录' }));
  await waitFor(() => expect(requests.some(request => request.path === '/restores' && request.method === 'POST')).toBe(true));
  expect((screen.getByRole('button', { name: '关闭对话框' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect(screen.getByRole('dialog', { name: '备份与恢复' })).toBeTruthy();
  await emit('prepare-exit', { request_id: 51, cancelled: false });
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 51, success: false }));
  await screen.findByText(/备份恢复操作尚未完成/);
  expectRecoveryOnly();
  await act(async () => finish());
  await screen.findByText('已恢复到独立目录');
  await emit('prepare-exit', { request_id: 52, cancelled: false });
  await waitFor(() => expect(invoke).toHaveBeenCalledWith('complete_exit_preparation', { requestId: 52, success: true }));
  expectRecoveryOnly();
});
it('恢复启动响应失败仍核实已建立的恢复区，重开不加载普通库', async () => {
  let reject!: (error: Error) => void; beginGate = new Promise<void>((_, fail) => { reject = fail; });
  render(<App />); await screen.findByText('迁移未完成，原数据已保留');
  fireEvent.click(screen.getByRole('button', { name: '从备份恢复' }));
  await waitFor(() => expect(commands('begin_backup_recovery')).toHaveLength(1));
  await act(async () => reject(new Error('启动响应丢失')));
  await screen.findByRole('heading', { name: '从备份恢复工作库' });
  await screen.findByText('启动响应丢失'); expect(requests).toEqual([]); expectRecoveryOnly();
  fireEvent.click(screen.getByRole('button', { name: '选择备份继续恢复' }));
  await screen.findByRole('dialog', { name: '备份与恢复' });
  expect(commands('begin_backup_recovery')).toHaveLength(1); expectRecoveryOnly();
});
