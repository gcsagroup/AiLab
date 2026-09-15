import React from 'react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RemoteTransfers } from '../../apps/desktop/src/RemoteTransfer';
import type { ExecutionTarget } from '../../apps/desktop/src/ExecutionTargets';
import type { Attempt } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const target: ExecutionTarget = { id: 'target-one', project_id: 'project-one', name: '回环验证服务', origin: 'http://127.0.0.1:12345', executor_id: 'executor-one', revision: 2, credential_ref: '', credential_status: 'available', validation_scope: 'loopback_protocol_only', connection_state: 'connected', protocol_ready: true, nvidia_ready: false };
const plan = { prepare_id: 'prepare-one', digest: 'f'.repeat(64), target, asset_manifest_digest: 'd'.repeat(64), total_bytes: 16, files: [{ path: 'data.jsonl', size: 16, sha256: 'a'.repeat(64) }] };
let attempt: Attempt; let history: Attempt[]; let calls: { method: string; path: string; body: any; key?: string }[];
let prepareResponse: (() => Promise<Response>) | undefined;
const response = (data: unknown) => ({ ok: true, json: async () => structuredClone(data) }) as Response;
beforeEach(() => {
  calls = []; history = []; prepareResponse = undefined;
  attempt = { id: 'attempt-one', task_id: 'task-one', project_id: 'project-one', state: 'succeeded', state_version: 5, collection_version: 2, collection_state: 'succeeded', compute_outcome: 'succeeded', allowed_actions: [], snapshot: { operation: 'transfer', executor_type: 'remote', execution_target_id: target.id, validation_scope: 'loopback_protocol_only', model_execution: false }, artifacts: [{ name: 'copied-0.bin' }] };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init?.method || 'GET'; const body = init?.body ? JSON.parse(String(init.body)) : undefined; calls.push({ method, path, body, key: (init?.headers as Record<string,string>)?.['Idempotency-Key'] });
    if (method === 'GET') {
      if (path.startsWith('/datasets?')) return response({ items: [{ id: 'dataset-one', name: '已导入测试数据' }] });
      if (path.startsWith('/materials?')) return response({ items: [{ id: 'material-one', name: '已导入测试素材' }] });
      if (path.startsWith('/remote-transfers?')) return response({ items: history });
      if (path.endsWith('/events?after=0')) return response({ items: [] });
      if (path === '/attempts/attempt-one') return response(attempt);
    }
    if (path === '/remote-transfers/prepare') return prepareResponse ? prepareResponse() : response(plan);
    if (path === '/remote-transfers') { history = [attempt]; return response(attempt); }
    if (path === '/attempts/attempt-one/collections') { attempt = { ...attempt, collection_state: 'succeeded', collection_version: 4, allowed_actions: [] }; return response({ state: 'succeeded' }); }
    throw new Error('未声明操作 ' + path);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const mount = (value = target) => render(<RemoteTransfers projectId="project-one" target={value} onChanged={vi.fn()} />);

it('先选择已有文件并检查范围，再明确提交稳定计划；不运行模型', async () => {
  mount(); await screen.findByRole('option', { name: '已导入测试数据' }); expect(calls.every(call => call.method === 'GET')).toBe(true);
  fireEvent.change(screen.getByLabelText('选择验证文件'), { target: { value: 'dataset-one' } }); fireEvent.click(screen.getByRole('button', { name: '检查发送范围' }));
  await screen.findByRole('region', { name: '本次文件发送范围' }); expect(screen.getByText(target.origin)).toBeTruthy(); expect(screen.getByText('data.jsonl · 16 B')).toBeTruthy();
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/remote-transfers/prepare']);
  fireEvent.click(screen.getByRole('button', { name: '开始传输验证' })); await screen.findByText('文件传输验证完成');
  const submitted = calls.find(call => call.path === '/remote-transfers'); expect(submitted?.body).toEqual({ prepare_id: plan.prepare_id, digest: plan.digest }); expect(submitted?.key).toBeTruthy();
  expect(screen.queryByRole('button', { name: '保存作品' })).toBeNull(); expect(screen.queryByRole('button', { name: '保存训练适配器' })).toBeNull();
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/remote-transfers/prepare','/remote-transfers']);
});
it('未验证目标或缺少凭据时不能准备发送', async () => {
  mount({ ...target, protocol_ready: false, credential_status: 'required' }); await screen.findByRole('option', { name: '已导入测试数据' });
  fireEvent.change(screen.getByLabelText('选择验证文件'), { target: { value: 'dataset-one' } }); expect(screen.getByRole('button', { name: '检查发送范围' })).toBeDisabled(); expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('HTTPS 文件预览保留明确接收地址，只有确认开始才提交该计划', async () => {
  const httpsTarget = { ...target, origin: 'https://executor.example', transport: 'https' as const, validation_scope: 'https_protocol_only', network_remote_ready: true };
  prepareResponse = () => Promise.resolve(response({ ...plan, target: httpsTarget, transport: 'https', validation_scope: 'https_protocol_only' }));
  attempt = { ...attempt, snapshot: { ...attempt.snapshot, transport: 'https', validation_scope: 'https_protocol_only' } };
  mount(httpsTarget); await screen.findByRole('option', { name: '已导入测试数据' });
  fireEvent.change(screen.getByLabelText('选择验证文件'), { target: { value: 'dataset-one' } }); fireEvent.click(screen.getByRole('button', { name: '检查发送范围' }));
  const preview = await screen.findByRole('region', { name: '本次文件发送范围' });
  expect(preview).toHaveTextContent('https://executor.example'); expect(preview).toHaveTextContent('data.jsonl');
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/remote-transfers/prepare']);
  fireEvent.click(screen.getByRole('button', { name: '开始传输验证' })); await screen.findByText('文件传输验证完成');
  expect(calls.filter(call => call.path === '/remote-transfers')).toEqual([expect.objectContaining({ method: 'POST', body: { prepare_id: plan.prepare_id, digest: plan.digest } })]);
  expect(screen.queryByRole('button', { name: '保存训练适配器' })).toBeNull();
});
it('准备请求期间目标凭据版本变化，迟到的旧计划不能启用传输', async () => {
  let resolve!: (value: Response) => void; prepareResponse = () => new Promise(done => { resolve = done; });
  const view = mount(); await screen.findByRole('option', { name: '已导入测试数据' }); fireEvent.change(screen.getByLabelText('选择验证文件'), { target: { value: 'dataset-one' } }); fireEvent.click(screen.getByRole('button', { name: '检查发送范围' }));
  await waitFor(() => expect(resolve).toBeTruthy()); view.rerender(<RemoteTransfers projectId="project-one" target={{ ...target, revision: 3 }} onChanged={vi.fn()} />); await act(async () => resolve(response(plan)));
  await screen.findByText('目标或资源已改变，请重新检查发送范围。'); expect(screen.queryByRole('button', { name: '开始传输验证' })).toBeNull();
});
it('重新打开旧传输并补收只调用原attempt集合入口，保留原失败', async () => {
  attempt = { ...attempt, state: 'failed', terminal_reason: 'COLLECTION_FAILED', allowed_actions: ['collect'], collection_state: 'failed', collection_version: 3, output_manifest_ref: { digest: 'e'.repeat(64) } }; history = [attempt];
  mount(); await screen.findByLabelText('查看传输记录'); fireEvent.change(screen.getByLabelText('查看传输记录'), { target: { value: attempt.id } });
  fireEvent.click(await screen.findByRole('button', { name: '只补收已有产物' })); await waitFor(() => expect(calls.some(call => call.path.endsWith('/collections'))).toBe(true));
  expect(calls.filter(call => call.method === 'POST')).toEqual([expect.objectContaining({ path: '/attempts/attempt-one/collections', body: { expected_collection_version: 3, manifest_digest: 'e'.repeat(64) } })]);
  expect(attempt.state).toBe('failed'); expect(screen.queryByText('文件传输验证完成')).toBeNull();
});
it('取消后断连保留停止未知提示，不显示已停止或释放资源', async () => {
  attempt = { ...attempt, state: 'cancelling', executor_type: 'remote', connection_state: 'disconnected', stop_status: 'unknown', allowed_actions: ['reconcile'] }; history = [attempt];
  mount(); await screen.findByLabelText('查看传输记录'); fireEvent.change(screen.getByLabelText('查看传输记录'), { target: { value: attempt.id } });
  await screen.findByText('停止结果尚未确认，不能据此认为任务已经停止或资源已经释放。'); expect(screen.getByRole('button', { name: '重连并核实原执行' })).toBeTruthy();
  expect(screen.queryByText('文件传输已停止')).toBeNull(); expect(screen.queryByText('文件传输验证完成')).toBeNull(); expect(calls.every(call => call.method === 'GET')).toBe(true);
});
it('传输历史按目标请求并明确续页，打开后页不会重提文件', async () => {
  const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((input, init) => {
    const path = String(input);
    if (path.includes('/remote-transfers?')) { expect(path).toContain('project_id=project-one'); expect(path).toContain('execution_target_id=target-one'); return Promise.resolve(response(path.includes('cursor=') ? { items: [attempt], next_cursor: null } : { items: [{ ...attempt, id: 'attempt-recent' }], next_cursor: 'desc:attempt-recent' })); }
    return original(input, init);
  });
  mount(); fireEvent.click(await screen.findByRole('button', { name: '加载更早传输记录' }));
  await screen.findByRole('option', { name: 'empt-one · 已完成' }); expect(screen.queryByRole('button', { name: '加载更早传输记录' })).toBeNull();
  fireEvent.change(screen.getByLabelText('查看传输记录'), { target: { value: attempt.id } }); await screen.findByText('文件传输验证完成');
  expect(calls.every(call => call.method === 'GET')).toBe(true); expect(screen.getByLabelText('查看传输记录')).toHaveValue(attempt.id);
});
