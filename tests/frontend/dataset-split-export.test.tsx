import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ExportDialog, { type ExportRecord } from '../../apps/desktop/src/ExportDialog';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const object = { type: 'dataset-split' as const, id: 'split-a', name: '来源组划分' };
const disclosure = '包含原始样本、来源标识、训练与验证子集及逐行划分证据；请确认接收方适合查看这些内容。';
const exportPlan = { id: 'export-plan', plan_digest: 'a'.repeat(64), can_export: true, blocking: [], disclosures: [disclosure], total_bytes: 1024, file_count: 6, target_dir: '/fixture/exports', files: [{ path: 'source.jsonl', size: 120, sha256: 'source' }, { path: 'train.jsonl', size: 100, sha256: 'train' }], dependencies: [{ type: 'model', id: 'qwen', included: false, description: '分词检查模型需要另行准备' }] };
const done: ExportRecord = { id: 'export-split', object_type: 'dataset-split', object_id: object.id, task_id: 'task-export', attempt_id: 'attempt-export', state: 'succeeded', state_version: 4, verified_path: '/fixture/exports/split-a' };
type Call = { path: string; method: string; body: Record<string, unknown>; key?: string };
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; let reject!: (reason: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
let epoch: number, calls: Call[], intercept: ((call: Call) => Response | Promise<Response> | undefined) | undefined;
const capture = () => { const current = epoch; return () => current === epoch; };
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  epoch = 0; calls = []; intercept = undefined;
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const call = { path: String(input).replace('/api/v1', ''), method: init.method || 'GET', body: init.body ? JSON.parse(String(init.body)) : {}, key: (init.headers as Record<string, string>)['Idempotency-Key'] }; calls.push(call);
    const special = intercept?.(call); if (special) return await special;
    if (call.path === '/exports/prepare') return response(exportPlan);
    if (call.path === '/exports' || call.path === '/exports/export-split') return response(done);
    if (call.path.endsWith('/cancel')) return response({});
    throw new Error(`未授权请求：${call.path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function setup(initial?: ExportRecord) {
  const onChanged = vi.fn(); const node = () => <LibraryReadContext.Provider value={capture}><ExportDialog object={object} projectId="project-a" initial={initial} onClose={() => {}} onChanged={onChanged} /></LibraryReadContext.Provider>;
  const view = render(node()); return { ...view, onChanged, redraw: () => view.rerender(node()) };
}
async function prepare() { fireEvent.change(screen.getByLabelText('导出保存目录'), { target: { value: '/fixture/exports' } }); fireEvent.click(screen.getByRole('button', { name: '检查导出范围' })); await screen.findByRole('button', { name: '开始导出' }); }

it('明确展示原文与来源标识披露和外部模型依赖后，才允许导出划分包', async () => {
  setup(); await prepare(); expect(screen.getByText(disclosure)).toBeTruthy(); expect(screen.getByText(/分词检查模型需要另行准备.*不包含在本次包内/)).toBeTruthy();
  expect(calls).toHaveLength(1); expect(calls[0].body).toMatchObject({ object_type: 'dataset-split', object_id: object.id, include_base: false });
  fireEvent.click(screen.getByRole('button', { name: '开始导出' })); await screen.findByText('全部文件已写入并通过校验');
  expect(calls.some(call => /split-plans|\/datasets\/splits|preflight/.test(call.path))).toBe(false);
});

it.each(['success', 'failure'])('工作库失效后迟到的导出预览%s不能显示或启用写入', async outcome => {
  const pending = deferred<Response>(); intercept = call => call.path === '/exports/prepare' ? pending.promise : undefined;
  const view = setup(); fireEvent.change(screen.getByLabelText('导出保存目录'), { target: { value: '/fixture/exports' } }); fireEvent.click(screen.getByRole('button', { name: '检查导出范围' })); epoch++; view.redraw();
  await act(async () => outcome === 'success' ? pending.resolve(response(exportPlan)) : pending.reject(new Error('旧库预览错误')));
  expect(screen.queryByRole('button', { name: '开始导出' })).toBeNull(); expect(screen.queryByText('旧库预览错误')).toBeNull(); expect(view.onChanged).not.toHaveBeenCalled();
  intercept = undefined; fireEvent.click(screen.getByRole('button', { name: '重新核实导出' })); await screen.findByRole('button', { name: '开始导出' }); expect((screen.getByLabelText('导出保存目录') as HTMLInputElement).value).toBe('/fixture/exports');
});

it.each(['success', 'failure'])('工作库失效后的导出提交%s不污染当前列表', async outcome => {
  const pending = deferred<Response>(); intercept = call => call.path === '/exports' ? pending.promise : undefined;
  const view = setup(); await prepare(); fireEvent.click(screen.getByRole('button', { name: '开始导出' })); epoch++; view.redraw();
  await act(async () => outcome === 'success' ? pending.resolve(response(done)) : pending.reject(new Error('旧库导出错误')));
  expect(view.onChanged).not.toHaveBeenCalled(); expect(screen.queryByText('全部文件已写入并通过校验')).toBeNull(); expect(screen.queryByText('旧库导出错误')).toBeNull();
  intercept = undefined; fireEvent.click(screen.getByRole('button', { name: '重新核实导出' })); await screen.findByText('全部文件已写入并通过校验');
  const submitted = calls.filter(call => call.path === '/exports'); expect(submitted[1].key).toBe(submitted[0].key); expect(submitted[1].body).toEqual(submitted[0].body);
});

it('取消确认在切库后迟到时，不继续向当前库读取旧导出', async () => {
  const pending = deferred<Response>(); const running = { ...done, state: 'running', state_version: 2, allowed_actions: ['cancel'], verified_path: undefined };
  intercept = call => call.path.endsWith('/cancel') ? pending.promise : call.path === '/exports/export-split' ? response(running) : undefined;
  const view = setup(running); await waitFor(() => expect(calls.filter(call => call.method === 'GET')).toHaveLength(1)); fireEvent.click(screen.getByRole('button', { name: '取消导出' })); epoch++; view.redraw();
  const reads = calls.filter(call => call.method === 'GET').length; await act(async () => pending.resolve(response({})));
  expect(calls.filter(call => call.method === 'GET')).toHaveLength(reads); expect(view.onChanged).not.toHaveBeenCalled();
});

it('关闭后迟到的导出完成不会刷新父页面', async () => {
  const pending = deferred<Response>(); intercept = call => call.path === '/exports' ? pending.promise : undefined;
  const view = setup(); await prepare(); fireEvent.click(screen.getByRole('button', { name: '开始导出' })); view.unmount(); await act(async () => pending.resolve(response(done))); expect(view.onChanged).not.toHaveBeenCalled();
});
