import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ExportDialog, { type ExportRecord } from '../../apps/desktop/src/ExportDialog';
import App from '../../apps/desktop/src/App';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import { defaultProjectView } from '../../apps/desktop/src/ProjectContext';
import { invoke, isTauri } from '@tauri-apps/api/core';

const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { state: string; message: string } }) => void) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: vi.fn(() => false), invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name === 'host-status') host.listener = listener; return () => { if (host.listener === listener) host.listener = undefined; }; }) }));
type Call = { path: string; method: string; body: Record<string, unknown>; key?: string };
let calls: Call[];
let record: ExportRecord;
let intercept: ((call: Call) => Response | Promise<Response> | undefined) | undefined;
const object = { type: 'adapter' as const, id: 'adapter-a', name: '实验适配器A' };
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = []; intercept = undefined; localStorage.clear(); sessionStorage.clear();
  vi.mocked(isTauri).mockReturnValue(false); host.listener = undefined;
  record = { id: 'export-a', task_id: 'task-export', attempt_id: 'attempt-export', object_type: 'adapter', object_id: object.id, state: 'succeeded', state_version: 4, verified_path: '/exports/adapter-a' };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', '');
    const body = init.body ? JSON.parse(String(init.body)) : {};
    const call = { path, method: init.method || 'GET', body, key: (init.headers as Record<string, string>)['Idempotency-Key'] }; calls.push(call);
    const special = intercept?.(call); if (special) return await special;
    let response: unknown = record;
    if (path === '/exports/prepare') response = { id: 'export-plan', plan_digest: 'fixed-digest', can_export: true, blocking: [], total_bytes: 1024, file_count: 2, target_dir: '/exports', files: [{ path: 'adapters.safetensors', size: 900, sha256: 'weights' }, { path: 'adapter_config.json', size: 124, sha256: 'config' }], dependencies: [{ type: 'model', id: 'base-a', included: false, description: '需要固定版本基座 Qwen' }] };
    if (path.endsWith('/cancel')) { record = { ...record, state: 'cancelled', state_version: 4, allowed_actions: [] }; response = record; }
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('用户产物导出', () => {
  it('展示依赖与文件范围，检查不会自行写入；不明响应重试使用原编号', async () => {
    render(<ExportDialog object={object} projectId="project-a" onClose={() => {}} onChanged={() => {}} />);
    fireEvent.change(screen.getByLabelText('导出保存目录'), { target: { value: '/exports' } });
    fireEvent.click(screen.getByRole('button', { name: '检查导出范围' }));
    await screen.findByRole('button', { name: '开始导出' });
    expect(screen.getByText(/需要固定版本基座 Qwen.*不包含在本次包内/)).toBeTruthy();
    expect(calls.map(call => call.path)).toEqual(['/exports/prepare']);
    expect(calls[0].body).toMatchObject({ object_type: 'adapter', object_id: object.id, include_base: false });
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const response = await normalFetch(input, init); if (String(input).endsWith('/exports') && !dropped) { dropped = true; throw new Error('导出请求结果待确认'); } return response; });
    fireEvent.click(screen.getByRole('button', { name: '开始导出' }));
    await screen.findByText('导出请求结果待确认');
    fireEvent.click(screen.getByRole('button', { name: '开始导出' }));
    await screen.findByText('全部文件已写入并通过校验');
    expect(screen.getByText('/exports/adapter-a')).toBeTruthy();
    const submitted = calls.filter(call => call.path === '/exports');
    expect(submitted).toHaveLength(2);
    expect(submitted[1].key).toBe(submitted[0].key);
    expect(calls.some(call => /preflight|\/tasks\//.test(call.path))).toBe(false);
  });
  it('历史导出可直接查看或取消，只控制对应导出尝试', async () => {
    record = { ...record, state: 'running', state_version: 3, verified_path: undefined, allowed_actions: ['cancel'] };
    render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '取消导出' }));
    await screen.findByRole('button', { name: '重新检查导出' });
    expect(calls.find(call => call.path.endsWith('/cancel'))).toMatchObject({ path: '/attempts/attempt-export/cancel', body: { expected_state_version: 3 } });
    expect(calls.some(call => call.path === '/exports' || call.path === '/exports/prepare')).toBe(false);
    expect(screen.queryByText('全部文件已写入并通过校验')).toBeNull();
  });
  it('失败记录重新检查原对象，不把重新导出变成模型重算', async () => {
    record = { ...record, state: 'failed', verified_path: undefined, error: { message: '目标磁盘空间不足' } };
    render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
    await screen.findByText('目标磁盘空间不足');
    fireEvent.click(screen.getByRole('button', { name: '重新检查导出' }));
    fireEvent.change(screen.getByLabelText('导出保存目录'), { target: { value: '/exports' } });
    fireEvent.click(screen.getByRole('button', { name: '检查导出范围' }));
    await waitFor(() => expect(calls.filter(call => call.path === '/exports/prepare')).toHaveLength(1));
    expect(calls.find(call => call.path === '/exports/prepare')?.body.object_id).toBe(object.id);
    expect(calls.some(call => /preflight|\/tasks\//.test(call.path))).toBe(false);
  });

  it('非终态登记失败显示原因并核实原导出，完整包读回成功', async () => {
    record = { ...record, state: 'finalizing', state_version: 3, verified_path: undefined, error: { message: '文件已完成但登记失败，请核实原导出。' }, allowed_actions: ['reconcile'] };
    const normalFetch = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, init) => {
      if (String(input).endsWith('/reconcile')) {
        await normalFetch(input, init);
        record = { ...record, state: 'succeeded', state_version: 4, verified_path: '/exports/adapter-a', error: undefined, allowed_actions: [] };
        return response({ id: record.attempt_id, state: record.state, state_version: record.state_version });
      }
      return normalFetch(input, init);
    });
    const changed = vi.fn();
    render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={changed} />);
    await screen.findByText('文件已完成但登记失败，请核实原导出。');
    fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
    await screen.findByText('全部文件已写入并通过校验');
    const mutation = calls.filter(call => call.method === 'POST');
    expect(mutation).toEqual([{ path: '/attempts/attempt-export/reconcile', method: 'POST', body: { expected_state_version: 3 }, key: expect.any(String) }]);
    expect(calls.at(-1)?.path).toBe('/exports/export-a');
    expect(changed).toHaveBeenCalled();
  });
});

function historyFixture(selection: { work_revision_id?: string | null; selection_warning?: string }) {
  record = { ...record, object_type: 'work', object_id: 'work-a', object_name: '历史作品', state: 'failed', verified_path: undefined, error: { message: '历史导出失败' }, ...selection };
  const normalFetch = vi.mocked(fetch).getMockImplementation()!;
  const projects = [{ id: 'project-a', name: '甲项目', revision: 1 }, { id: 'project-b', name: '乙项目', revision: 1 }];
  const task = { id: 'task-export', project_id: 'project-a', name: '历史作品导出', kind: 'export', operation: 'export', export_id: record.id, latest_attempt: { state: 'failed' } };
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://fixture'); const path = url.pathname.replace('/api/v1', '');
    if (path.startsWith('/exports')) return normalFetch(input, init);
    const call = { path, method: init?.method || 'GET', body: init?.body ? JSON.parse(String(init.body)) : {} }; calls.push(call);
    if (path === '/ui-context') return response({ project_id: 'project-a', projects: { 'project-a': defaultProjectView() } });
    if (call.method !== 'GET') throw new Error(`历史入口不允许额外写入：${path}`);
    if (path === '/projects') return response({ items: projects });
    if (path.startsWith('/projects/')) return response(projects.find(project => path.endsWith(project.id)));
    if (path === '/tasks') return response({ items: url.searchParams.get('project_id') === 'project-a' ? [task] : [] });
    if (path === '/works') return response({ items: [{ id: 'work-a', project_id: 'project-a', name: '历史作品', kind: 'text', current_revision_id: 'revision-newer', text: '后来修订的内容' }] });
    return response({ items: [], next_cursor: null });
  });
}

it.each(['revision-older', null])('任务历史重开版本 %s，失败后重新检查仍指定当时版本', async workRevisionId => {
  historyFixture({ work_revision_id: workRevisionId });
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /^历史作品导出/ }));
  await screen.findByText('历史导出失败');
  fireEvent.click(screen.getByRole('button', { name: '重新检查导出' }));
  fireEvent.change(screen.getByLabelText('导出保存目录'), { target: { value: '/exports' } });
  fireEvent.click(screen.getByRole('button', { name: '检查导出范围' }));
  await screen.findByRole('button', { name: '开始导出' });
  expect(calls.find(call => call.path === '/exports/prepare')?.body).toMatchObject({ object_type: 'work', object_id: 'work-a', work_revision_id: workRevisionId });
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/exports/prepare']);
});

it.each(['原导出的冻结计划不可读取，请回到作品重新选择版本。', undefined])('历史版本缺失时显示原因并阻止重新检查：%s', async selectionWarning => {
  historyFixture({ selection_warning: selectionWarning });
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /^历史作品导出/ }));
  await screen.findByText('历史导出失败');
  expect(screen.getByText(selectionWarning || '无法核实这条历史导出当时选择的作品版本。请回到作品，明确选择原版或人工修订后再导出。')).toBeTruthy();
  expect((screen.getByRole('button', { name: '重新检查导出' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '重新检查导出' }));
  expect(screen.queryByLabelText('导出保存目录')).toBeNull();
  expect(screen.queryByText(/^已选择原生成版本/)).toBeNull();
  expect(calls.some(call => call.method === 'POST')).toBe(false);
});

function recoveryRecord() {
  record = { ...record, state: 'finalizing', state_version: 3, verified_path: undefined, error: { message: '原文件包的登记结果待核实' }, allowed_actions: ['reconcile'] };
  return record;
}

it('核实不完整包只更新原记录为失败，保留原因且不登记成功路径', async () => {
  recoveryRecord();
  intercept = call => {
    if (!call.path.endsWith('/reconcile')) return;
    record = { ...record, state: 'failed', state_version: 4, error: { message: '原文件包缺少清单，未登记为完整包。' }, allowed_actions: [] };
    return response({ id: record.attempt_id, state: record.state, state_version: record.state_version });
  };
  render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
  await screen.findByText('原文件包缺少清单，未登记为完整包。');
  expect(screen.getByText('执行失败')).toBeTruthy(); expect(screen.queryByText('全部文件已写入并通过校验')).toBeNull();
  expect(screen.queryByText('/exports/adapter-a')).toBeNull(); expect(screen.queryByRole('button', { name: '核实原导出' })).toBeNull();
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/attempts/attempt-export/reconcile']);
});

it('仅后端允许核实时显示入口，普通写入中的错误仍可见', async () => {
  recoveryRecord(); record.allowed_actions = ['cancel'];
  render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  await screen.findByText('原文件包的登记结果待核实');
  expect(screen.queryByRole('button', { name: '核实原导出' })).toBeNull();
  expect(screen.getByRole('button', { name: '取消导出' })).toBeTruthy();
  expect(calls.some(call => call.method === 'POST')).toBe(false);
});

it('历史版本未知仍可核实原文件包，但不会新建导出或推定原版', async () => {
  recoveryRecord(); record = { ...record, object_type: 'work', object_id: 'work-a', selection_warning: '历史作品版本不明，请返回作品明确选择。' };
  intercept = call => {
    if (!call.path.endsWith('/reconcile')) return;
    record = { ...record, state: 'failed', state_version: 4, allowed_actions: [], error: { message: '原包不完整，已停止导出' } };
    return response({ id: record.attempt_id });
  };
  render(<ExportDialog object={{ type: 'work', id: 'work-a', name: '历史作品' }} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' })); await screen.findByText('原包不完整，已停止导出');
  expect(screen.getByText('历史作品版本不明，请返回作品明确选择。')).toBeTruthy();
  expect((screen.getByRole('button', { name: '重新检查导出' }) as HTMLButtonElement).disabled).toBe(true);
  expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/attempts/attempt-export/reconcile']);
});

it.each(['响应丢失', '状态冲突', '仍在写入'])('核实%s后读取原状态，避免并发并按状态版本重用请求编号', async outcome => {
  recoveryRecord(); const pending = deferred<Response>();
  intercept = call => call.path.endsWith('/reconcile') ? pending.promise : undefined;
  render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(1));
  const button = screen.getByRole('button', { name: '核实原导出' }); fireEvent.click(button); fireEvent.click(button);
  expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
  await act(async () => {
    if (outcome === '响应丢失') pending.reject(new Error('核实响应未收到'));
    else {
      if (outcome === '状态冲突') record = { ...record, state_version: 5 };
      pending.resolve({ ok: false, json: async () => ({ error: { code: outcome === '状态冲突' ? 'REVISION_CONFLICT' : 'CONTROL_NOT_SUPPORTED', message: outcome === '状态冲突' ? '原导出状态已变化' : '原导出仍在写入，请稍后核实' } }) } as Response);
    }
  });
  await screen.findByText(outcome === '响应丢失' ? '核实响应未收到' : outcome === '状态冲突' ? '原导出状态已变化' : '原导出仍在写入，请稍后核实');
  expect(calls.at(-1)?.path).toBe('/exports/export-a');
  intercept = call => call.path.endsWith('/reconcile') ? response({ id: record.attempt_id }) : undefined;
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '核实原导出' }) as HTMLButtonElement).disabled).toBe(false));
  const posted = calls.filter(call => call.method === 'POST'); expect(posted).toHaveLength(2);
  expect(posted.map(call => call.path)).toEqual(['/attempts/attempt-export/reconcile', '/attempts/attempt-export/reconcile']);
  expect(posted[1].body.expected_state_version).toBe(outcome === '状态冲突' ? 5 : 3);
  if (outcome === '状态冲突') expect(posted[1].key).not.toBe(posted[0].key);
  else expect(posted[1].key).toBe(posted[0].key);
});

it('核实后读回失联仍保留原记录，重试继续使用原状态请求编号', async () => {
  recoveryRecord(); let posted = false;
  intercept = call => {
    if (call.path.endsWith('/reconcile')) { posted = true; return response({ id: record.attempt_id }); }
    if (posted && call.method === 'GET') return Promise.reject(new Error('暂时读不到原导出'));
  };
  render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
  await screen.findByText('暂时读不到原导出');
  expect(screen.getByText('记录编号：export-a')).toBeTruthy();
  intercept = call => call.path.endsWith('/reconcile') ? response({ id: record.attempt_id }) : undefined;
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
  await waitFor(() => expect((screen.getByRole('button', { name: '核实原导出' }) as HTMLButtonElement).disabled).toBe(false));
  const mutations = calls.filter(call => call.method === 'POST'); expect(mutations).toHaveLength(2); expect(mutations[1].key).toBe(mutations[0].key);
});

it.each(['post-success', 'post-failure', 'get-success', 'get-failure'])('工作库失效后迟到的核实 %s 不续读或回填', async phase => {
  recoveryRecord(); const pending = deferred<Response>(); let epoch = 0; let posted = false;
  intercept = call => {
    if (call.path.endsWith('/reconcile')) { posted = true; return phase.startsWith('post') ? pending.promise : response({ id: record.attempt_id }); }
    if (posted && call.method === 'GET' && phase.startsWith('get')) return pending.promise;
  };
  const changed = vi.fn(); const capture = () => { const current = epoch; return () => current === epoch; };
  const node = () => <LibraryReadContext.Provider value={capture}><ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={changed} /></LibraryReadContext.Provider>;
  const view = render(node()); await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' }));
  if (phase.startsWith('get')) await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(2));
  epoch++; view.rerender(node()); const before = calls.length;
  await act(async () => phase.endsWith('success') ? pending.resolve(response({ ...record, state: 'succeeded', state_version: 4, verified_path: '/old-library/export' })) : pending.reject(new Error('旧库核实失败')));
  expect(calls).toHaveLength(before); expect(changed).not.toHaveBeenCalled();
  expect(screen.queryByText('全部文件已写入并通过校验')).toBeNull(); expect(screen.queryByText('旧库核实失败')).toBeNull(); expect(screen.queryByText('/old-library/export')).toBeNull();
  expect(screen.getByText('工作库读取已失效，保存位置保留。请重新核实导出。')).toBeTruthy();
});

it('核实完成后低版本轮询迟到，不把结果退回等待核实', async () => {
  const waiting = recoveryRecord(); const oldRead = deferred<Response>(); let reads = 0;
  intercept = call => {
    if (call.method === 'GET' && ++reads === 1) return oldRead.promise;
    if (call.path.endsWith('/reconcile')) { record = { ...record, state: 'succeeded', state_version: 4, verified_path: '/exports/adapter-a', allowed_actions: [] }; return response({ id: record.attempt_id }); }
  };
  render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={() => {}} />);
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' })); await screen.findByText('全部文件已写入并通过校验');
  await act(async () => oldRead.resolve(response(waiting)));
  expect(screen.getByText('全部文件已写入并通过校验')).toBeTruthy(); expect(screen.queryByRole('button', { name: '核实原导出' })).toBeNull();
});

it.each(['success', 'failure'])('关闭后迟到的核实 %s 不续读或刷新父页面', async outcome => {
  recoveryRecord(); const pending = deferred<Response>(); const changed = vi.fn();
  intercept = call => call.path.endsWith('/reconcile') ? pending.promise : undefined;
  const view = render(<ExportDialog object={object} projectId="project-a" initial={record} onClose={() => {}} onChanged={changed} />);
  await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(1));
  fireEvent.click(screen.getByRole('button', { name: '核实原导出' })); view.unmount(); const count = calls.length;
  await act(async () => outcome === 'success' ? pending.resolve(response({ id: record.attempt_id })) : pending.reject(new Error('关闭后的旧错误')));
  expect(calls).toHaveLength(count); expect(changed).not.toHaveBeenCalled();
});

it.each(['success', 'failure'])('切换项目后历史导出的迟到 %s 不弹窗或显示旧错误', async outcome => {
  historyFixture({ work_revision_id: 'revision-older' }); const pending = deferred<Response>();
  intercept = call => call.path === '/exports/export-a' ? pending.promise : undefined;
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /^历史作品导出/ }));
  fireEvent.change(screen.getByLabelText('当前项目'), { target: { value: 'project-b' } });
  await waitFor(() => expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('project-b'));
  await act(async () => outcome === 'success' ? pending.resolve(response(record)) : pending.reject(new Error('甲项目历史导出读取失败')));
  expect(screen.queryByRole('dialog', { name: '导出历史作品' })).toBeNull(); expect(screen.queryByText('甲项目历史导出读取失败')).toBeNull();
});

it.each(['success', 'failure'])('宿主断连使工作库失效，历史导出的迟到 %s 不弹窗或覆盖断连原因', async outcome => {
  historyFixture({ work_revision_id: 'revision-older' }); const pending = deferred<Response>();
  intercept = call => call.path === '/exports/export-a' ? pending.promise : undefined;
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockImplementation(async (command, args) => {
    if (command !== 'api_request') return {};
    const { request } = args as { request: { path: string; method: string; body?: unknown; idempotency_key?: string } };
    const result = await fetch(request.path, { method: request.method, body: request.body === undefined ? undefined : JSON.stringify(request.body), headers: { 'Idempotency-Key': request.idempotency_key || '' } });
    const value = await result.json(); if (!result.ok) throw value; return value;
  });
  render(<App />); fireEvent.click(await screen.findByRole('button', { name: /^历史作品导出/ }));
  await act(async () => host.listener!({ payload: { state: 'stopped', message: '本机服务连接已中断' } }));
  await act(async () => outcome === 'success' ? pending.resolve(response(record)) : pending.reject(new Error('失效工作库的导出错误')));
  expect(screen.queryByRole('dialog', { name: '导出历史作品' })).toBeNull(); expect(screen.queryByText('失效工作库的导出错误')).toBeNull();
  expect(screen.getByText('本机服务连接已中断')).toBeTruthy();
});

it.each(['success', 'failure'])('同项目先点导出A再点B，A迟到的 %s 不覆盖后选B', async outcome => {
  historyFixture({ work_revision_id: 'revision-a' }); const pending = deferred<Response>();
  const earlier = { ...record, object_name: '先选作品A' };
  const newer = { ...record, id: 'export-b', task_id: 'task-export-b', attempt_id: 'attempt-export-b', object_id: 'work-b', object_name: '后选作品B', work_revision_id: 'revision-b', error: { message: 'B的历史导出结果' } };
  const historyFetch = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://fixture');
    if (url.pathname === '/api/v1/tasks') {
      calls.push({ path: '/tasks', method: init?.method || 'GET', body: {} });
      return response({ items: [earlier, newer].map(item => ({ id: item.task_id, project_id: 'project-a', name: item.object_name, kind: 'export', operation: 'export', export_id: item.id, latest_attempt: { state: 'failed' } })) });
    }
    return historyFetch(input, init);
  });
  intercept = call => call.path === '/exports/export-a' ? pending.promise : call.path === '/exports/export-b' ? response(newer) : undefined;
  render(<App />);
  fireEvent.click(await screen.findByRole('button', { name: /^先选作品A/ }));
  fireEvent.click(screen.getByRole('button', { name: /^后选作品B/ }));
  await screen.findByRole('dialog', { name: '导出后选作品B' }); await screen.findByText('B的历史导出结果');
  await act(async () => outcome === 'success' ? pending.resolve(response(earlier)) : pending.reject(new Error('先选A读取失败')));
  expect(screen.getByRole('dialog', { name: '导出后选作品B' })).toBeTruthy();
  expect(screen.queryByRole('dialog', { name: '导出先选作品A' })).toBeNull(); expect(screen.queryByText('先选A读取失败')).toBeNull();
  expect(calls.filter(call => call.path === '/exports/export-a')).toHaveLength(1);
  expect(calls.some(call => call.method === 'POST')).toBe(false);
});
