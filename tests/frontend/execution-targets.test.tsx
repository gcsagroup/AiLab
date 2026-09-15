import { invalidateNativeConnection } from '../../apps/desktop/src/api';
import React from 'react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ExecutionTargets, validExecutionOrigin, type ExecutionTarget } from '../../apps/desktop/src/ExecutionTargets';
import addressCases from '../fixtures/execution-origin-cases.json';

const host = vi.hoisted(() => ({ native: false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => host.native, invoke: host.invoke }));
const credential = 'fake-credential-for-ui-test-only-0123456789';
const executor = `executor-${'a'.repeat(32)}`;
const base: ExecutionTarget = { id: `execution-target-${'b'.repeat(32)}`, project_id: 'project-one', name: '独立验证服务', origin: 'http://127.0.0.1:12345', executor_id: executor, revision: 3, credential_ref: 'ref-test', credential_status: 'available', validation_scope: 'loopback_protocol_only', connection_state: 'unknown', nvidia_ready: false };
let targets: ExecutionTarget[]; let calls: { method: string; path: string; body: any; key?: string }[]; let conflict: boolean;
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
beforeEach(() => {
  invalidateNativeConnection();
  targets = []; calls = []; conflict = false; host.native = false; host.invoke.mockReset();
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init?.method || 'GET'; const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init?.headers as Record<string,string>)?.['Idempotency-Key'] });
    if (method === 'GET') return response(path.endsWith('/execution-default') ? { execution_target_id: null, revision: 1 } : { items: targets.filter(target => path.includes(target.project_id)) });
    if (path === '/execution-targets') { targets = [{ ...base, revision: 1, name: body.name, origin: body.origin.toLowerCase().replace(':443/', '').replace(/\/$/, ''), ...(body.origin.toLowerCase().startsWith('https://') ? { transport: 'https' as const, validation_scope: 'https_protocol_only', network_remote_ready: true } : {}) }]; return response(targets[0]); }
    if (path.endsWith('/credentials')) {
      if (conflict) return response({ error: { code: 'REVISION_CONFLICT', message: `凭据版本冲突。${credential}` } }, false);
      targets = targets.map(target => ({ ...target, revision: target.revision + 1, credential_status: 'available' })); return response(targets[0]);
    }
    if (path.endsWith('/check')) { targets = targets.map(target => ({ ...target, connection_state: 'connected', protocol_ready: true })); return response(targets[0]); }
    throw new Error('未声明请求 ' + path);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const mount = (projectId = 'project-one') => render(<ExecutionTargets projectId={projectId} onChanged={vi.fn()} />);

it('与控制端共同地址样本一致，UI仅裁去粘贴的首尾空白并从地址指定方式', () => {
  const comparable = addressCases.cases.filter(item => item.origin === item.origin.trim() && item.transport === (item.origin.toLowerCase().startsWith('https://') ? 'https' : 'loopback_http'));
  expect(comparable).toHaveLength(46);
  for (const item of comparable) expect(validExecutionOrigin(item.origin), item.origin).toBe(item.accepted);
  expect(validExecutionOrigin(' HTTP://127.0.0.1:12345/ ')).toBe(true);
  expect(validExecutionOrigin(' https://example.com\n')).toBe(true);
});
async function form() { const register = await screen.findByRole('button', { name: '登记执行目标' }); await waitFor(() => expect(register).not.toBeDisabled()); fireEvent.click(register); fireEvent.change(await screen.findByLabelText('目标名称'), { target: { value: '独立验证服务' } }); fireEvent.change(screen.getByLabelText('连接地址'), { target: { value: base.origin } }); fireEvent.change(screen.getByLabelText('执行器编号'), { target: { value: executor } }); fireEvent.change(screen.getByLabelText('访问凭据'), { target: { value: credential } }); }

it('打开目标设置只读列表；没有项目时不请求、不登记', async () => {
  const view = mount(''); expect(screen.getByText('创建或选择项目后再登记执行目标。')).toBeTruthy(); expect(calls).toEqual([]);
  view.rerender(<ExecutionTargets projectId="project-one" onChanged={vi.fn()} />); await screen.findByText('当前项目尚未登记执行目标。');
  expect(calls.every(call => call.method === 'GET')).toBe(true); expect(calls.some(call => call.path.endsWith('/execution-default'))).toBe(true); expect(screen.getByText('HTTPS / 本机回环')).toBeTruthy();
});
it('字面回环和固定编号通过后才登记，保存与验证均不提交任何模型计算', async () => {
  mount(); await form(); const submit = screen.getByRole('button', { name: '保存并验证连接' });
  for (const origin of ['http://localhost:12345', 'http://192.168.1.5:12345', 'http://127.0.0.1:65536', 'http://127.0.0.1:12345/path']) { fireEvent.change(screen.getByLabelText('连接地址'), { target: { value: origin } }); expect(submit).toBeDisabled(); }
  fireEvent.change(screen.getByLabelText('连接地址'), { target: { value: base.origin } }); fireEvent.click(submit);
  await screen.findByText('目标身份和回环协议已验证。模型运行能力仍以任务检查为准。');
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/execution-targets', `/execution-targets/${base.id}/check`]);
  expect(calls.find(call => call.method === 'POST')).toMatchObject({ body: { project_id: 'project-one', origin: base.origin, executor_id: executor, credential_token: credential } });
  expect(calls.find(call => call.method === 'POST')?.key).toBeTruthy(); expect(screen.queryByLabelText('访问凭据')).toBeNull(); expect(document.body.textContent).not.toContain(credential);
  expect(screen.getByText('NVIDIA 尚未通过实机验证。')).toBeTruthy();
});
it('失效凭据必须重新输入，版本冲突清除表单秘密并保留原身份', async () => {
  targets = [{ ...base, credential_status: 'required' }]; conflict = true; mount();
  expect(await screen.findByRole('button', { name: '验证连接' })).toBeDisabled(); fireEvent.click(screen.getByRole('button', { name: '重新输入凭据' }));
  expect(screen.queryByLabelText('连接地址')).toBeNull(); fireEvent.change(screen.getByLabelText('访问凭据'), { target: { value: credential } }); fireEvent.click(screen.getByRole('button', { name: '保存并验证连接' }));
  await screen.findByText('凭据版本冲突。[凭据已隐藏]'); expect((screen.getByLabelText('访问凭据') as HTMLInputElement).value).toBe('');
  expect(calls.find(call => call.method === 'POST')?.body).toEqual({ credential_token: credential, expected_revision: 3 });
  expect(calls.some(call => call.path.endsWith('/check'))).toBe(false); expect(document.body.textContent).not.toContain(credential);
});
it('凭据长度和可见字符与执行服务一致，拒绝空白及非ASCII字符', async () => {
  mount(); await form(); const input = screen.getByLabelText('访问凭据'); const submit = screen.getByRole('button', { name: '保存并验证连接' });
  expect(input).toHaveAttribute('maxlength', '512');
  for (const value of ['a'.repeat(31), 'a'.repeat(513), 'a'.repeat(31) + ' ', 'a'.repeat(31) + '\n', 'a'.repeat(31) + '密']) { fireEvent.change(input, { target: { value } }); expect(submit).toBeDisabled(); }
  for (const value of ['a'.repeat(32), 'a'.repeat(257), 'a'.repeat(512), '!~'.repeat(16)]) { fireEvent.change(input, { target: { value } }); expect(submit).toBeEnabled(); }
  expect(calls.every(call => call.method === 'GET')).toBe(true);
});
it('切换项目后迟到的列表响应不进入新项目', async () => {
  let resolveOld!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn((input: string) => input.includes('project-one') ? new Promise<Response>(resolve => { resolveOld = resolve; }) : Promise.resolve(response({ items: [] }))));
  const view = mount(); await waitFor(() => expect(resolveOld).toBeTruthy()); view.rerender(<ExecutionTargets projectId="project-two" onChanged={vi.fn()} />);
  await screen.findByText('当前项目尚未登记执行目标。'); await act(async () => resolveOld(response({ items: [base] })));
  expect(screen.queryByRole('article', { name: '执行目标：独立验证服务' })).toBeNull();
});
it('原生登记只用专用宿主命令保存凭据，通用HTTP不收到秘密', async () => {
  host.native = true;
  host.invoke.mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: 'fixture-a' };
    if (command === 'api_request') return { items: targets };
    if (command === 'create_execution_target') { expect(args.input.credential_token).toBe(credential); targets = [{ ...base, revision: 1 }]; return targets[0]; }
    if (command === 'connect_remote_target') { targets = targets.map(target => ({ ...target, protocol_ready: true, connection_state: 'connected' })); return targets[0]; }
    throw new Error(command);
  });
  mount(); await form(); fireEvent.click(screen.getByRole('button', { name: '保存并验证连接' })); await screen.findByText('目标身份和回环协议已验证。模型运行能力仍以任务检查为准。');
  expect(host.invoke.mock.calls.filter(([command]) => command === 'api_request').every(([,args]) => !JSON.stringify(args).includes(credential))).toBe(true);
  expect(host.invoke.mock.calls.filter(([command]) => command === 'create_execution_target')).toHaveLength(1);
  expect(host.invoke).toHaveBeenCalledWith('connect_remote_target', { targetId: base.id, expectedRevision: 1 }); expect(calls).toEqual([]);
});
it('原生清除凭据保留目标记录，随后显示需要凭据', async () => {
  host.native = true; targets = [base]; host.invoke.mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: 'fixture-a' };
    if (command === 'api_request') return { items: targets };
    if (command === 'forget_remote_target') { expect(args).toEqual({ targetId: base.id, expectedRevision: 3 }); targets = [{ ...base, credential_status: 'required', revision: 4 }]; return targets[0]; }
    throw new Error(command);
  });
  mount(); fireEvent.click(await screen.findByRole('button', { name: '清除保存的凭据' })); await screen.findByText('已清除本目标保存的凭据。连接记录保留，重新连接需要输入凭据。');
  expect(screen.getByText('需要凭据')).toBeTruthy(); expect(screen.getByRole('article', { name: '执行目标：独立验证服务' })).toBeTruthy();
});

it('HTTPS 接受标准地址并提交原输入，卡片展示控制端返回的规范地址', async () => {
  mount(); await form(); const address = screen.getByLabelText('连接地址'); const submit = screen.getByRole('button', { name: '保存并验证连接' });
  for (const origin of ['https://executor.example', 'HTTPS://Executor.Example:443/', 'https://127.0.0.1:8443', 'https://[::1]:8443', 'https://[2001:db8::1]', 'https://localhost:8443']) {
    fireEvent.change(address, { target: { value: origin } }); expect(submit).toBeEnabled();
  }
  const entered = 'HTTPS://Executor.Example:443/'; fireEvent.change(address, { target: { value: entered } }); fireEvent.click(submit);
  await screen.findByText('目标身份和HTTPS 协议已验证。模型运行能力仍以任务检查为准。');
  expect(screen.getByText('https://executor.example')).toBeTruthy(); expect(screen.getByText('HTTPS（校验服务器证书）')).toBeTruthy();
  expect(screen.getByText('NVIDIA 尚未通过实机验证。')).toBeTruthy();
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/execution-targets', `/execution-targets/${base.id}/check`]);
  expect(calls.find(call => call.path === '/execution-targets')?.body.origin).toBe(entered);
  expect(calls.find(call => call.path === '/execution-targets')?.body.transport).toBe('https');
  expect(document.body.textContent).not.toContain(credential);
});

it('原生 HTTPS 登记通过专用命令传输方式，并使用返回的规范地址', async () => {
  host.native = true;
  host.invoke.mockImplementation(async (command, args) => {
    if (command === 'host_status') return { state: 'running', connection_id: 'fixture-a' };
    if (command === 'api_request') return args.request.path.endsWith('/execution-default') ? { execution_target_id: null, revision: 1 } : { items: targets };
    if (command === 'create_execution_target') {
      expect(args.input).toMatchObject({ origin: 'HTTPS://Executor.Example:443/', transport: 'https', credential_token: credential });
      targets = [{ ...base, origin: 'https://executor.example', transport: 'https', validation_scope: 'https_protocol_only', revision: 1 }]; return targets[0];
    }
    if (command === 'connect_remote_target') { targets = targets.map(target => ({ ...target, protocol_ready: true, network_remote_ready: true, connection_state: 'connected' })); return targets[0]; }
    throw new Error(command);
  });
  mount(); await form(); fireEvent.change(screen.getByLabelText('连接地址'), { target: { value: 'HTTPS://Executor.Example:443/' } });
  fireEvent.click(screen.getByRole('button', { name: '保存并验证连接' })); await screen.findByText('目标身份和HTTPS 协议已验证。模型运行能力仍以任务检查为准。');
  expect(screen.getByText('https://executor.example')).toBeTruthy();
  expect(host.invoke.mock.calls.filter(([command]) => command === 'api_request').every(([, args]) => !JSON.stringify(args).includes(credential))).toBe(true);
  expect(host.invoke).toHaveBeenCalledWith('connect_remote_target', { targetId: base.id, expectedRevision: 1 });
  expect(calls).toEqual([]);
});

it('HTTPS 拒绝 URL 中的额外目的地和解析器自动修正的地址', async () => {
  mount(); await form(); const address = screen.getByLabelText('连接地址'); const submit = screen.getByRole('button', { name: '保存并验证连接' });
  for (const origin of ['https://user:pass@executor.example', 'https://executor.example/path', 'https://executor.example/?q=1', 'https://executor.example/#x', 'https://executor.example:0', 'https://executor.example:65536', 'https://executor.example:0443', 'https://executor.example\\other', 'https://%65xecutor.example', 'https://例子.example', 'https://bad_name.example', 'https://127.1', 'https://2130706433', 'https://0x7f000001', 'https://0177.0.0.1', 'https://127.0.0.1.', 'https://[::1%25lo0]', 'https://[not-ip]', 'https://executor..example', 'https://-executor.example']) {
    fireEvent.change(address, { target: { value: origin } }); expect(submit, origin).toBeDisabled();
  }
  expect(calls.every(call => call.method === 'GET')).toBe(true);
});

it('证书校验失败保留目标和错误状态，不能开始文件传输', async () => {
  targets = [{ ...base, origin: 'https://executor.example', transport: 'https', validation_scope: 'https_protocol_only', connection_state: 'disconnected', protocol_ready: false }];
  const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((input, init) => {
    if (!String(input).endsWith('/check')) return original(input, init);
    targets = [{ ...targets[0], last_error: { code: 'TLS_CERTIFICATE_INVALID', message: '服务器证书校验失败。' } }];
    return Promise.resolve(response(targets[0]));
  });
  mount(); fireEvent.click(await screen.findByRole('button', { name: '验证连接' }));
  await screen.findByText('执行能力尚未通过检查。');
  expect(await screen.findByText('服务器证书校验失败。')).toBeTruthy();
  expect(screen.getByRole('button', { name: '验证文件传输' })).toBeDisabled();
  expect(screen.queryByText('HTTPS 协议连接已验证')).toBeNull();
  expect(calls.some(call => call.path.startsWith('/remote-transfers'))).toBe(false);
});
