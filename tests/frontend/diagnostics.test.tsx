import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import DiagnosticsDialog from '../../apps/desktop/src/DiagnosticsDialog';
import { pickExportDirectory } from '../../apps/desktop/src/api';
import type { Attempt } from '../../apps/desktop/src/types';

let nativePicker = false;
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
// 独立检查系统选择器回执与 UI/API 合同；真正的系统目录对话框由桌面验收覆盖。
vi.mock('../../apps/desktop/src/api', async importOriginal => ({ ...await importOriginal<typeof import('../../apps/desktop/src/api')>(), canPickFile: () => nativePicker, pickExportDirectory: vi.fn() }));
const identifier = 'diagnostic-preview-' + 'a'.repeat(32);
const ready = { id: identifier, status: 'ready', included: ['已知错误代码与版本计数'], excluded: ['提示词、正文、路径与令牌'], files: [{ path: 'diagnostics.json', size: 128, sha256: 'a'.repeat(64) }, { path: 'manifest.json', size: 128, sha256: 'b'.repeat(64) }], total_bytes: 256, archive_bytes: 512, archive_sha256: 'c'.repeat(64), diagnostics: { schema_version: 'ailab-diagnostics-v1', selected_attempts: [] }, can_export: true, can_cancel: true };
const attempts: Attempt[] = Array.from({ length: 22 }, (_, index) => ({ id: 'attempt-' + String(index).padStart(32, '0'), project_id: 'project-one', task_id: 'task-one', state: 'failed', state_version: 2, created_at: '2026-09-10T00:00:00Z', snapshot: { input: { prompt: '私有正文不得发送' } } }));
const response = (data: unknown, ok = true) => ({ ok, json: async () => structuredClone(data) }) as Response;
let requests: { path: string; method: string; body: any; key?: string }[]; let record: any; let exportFailure: string | null; let cancelFailure: string | null;
beforeEach(() => {
 HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
 nativePicker = false; requests = []; record = structuredClone(ready); exportFailure = null; cancelFailure = null; vi.mocked(pickExportDirectory).mockResolvedValue({ path: '/明确选择的诊断目录', grant_id: 'native-grant' });
 vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
  const path = String(input).replace('/api/v1', ''); const method = options?.method || 'GET'; const body = options?.body ? JSON.parse(String(options.body)) : {};
  requests.push({ path, method, body, key: (options?.headers as Record<string,string>)?.['Idempotency-Key'] });
  if (method === 'GET') return response(record);
  if (path === '/diagnostics/previews') return response(ready);
  if (path === '/diagnostics/exports') {
   if (exportFailure) { const code = exportFailure; exportFailure = null; return response({ error: { code, message: '导出回执未确认' } }, false); }
   record = { ...ready, status: 'succeeded', can_export: false, can_cancel: false, saved_path: '/明确选择的诊断目录/' + identifier + '.zip' }; return response(record);
  }
  if (path.endsWith('/cancel')) {
   if (cancelFailure) { const code = cancelFailure; cancelFailure = null; return response({ error: { code, message: '取消回执未确认' } }, false); }
   record = { ...ready, status: 'cancelled', can_export: false, can_cancel: false }; return response(record);
  }
  throw new Error('未声明请求 ' + method + ' ' + path);
 }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function view(projectId = 'project-one') { const onClose = vi.fn(); return { ...render(<DiagnosticsDialog projectId={projectId} attempts={attempts} onClose={onClose} />), onClose }; }
async function inspect() { fireEvent.click(screen.getByRole('button', { name: '预览诊断范围' })); await screen.findByText('范围已冻结'); }
async function target() { await inspect(); fireEvent.change(screen.getByLabelText('诊断保存目录'), { target: { value: '/明确选择的诊断目录' } }); }

it('打开不自动预览或写文件，明确预览只发固定项目与运行编号', async () => {
 view(); expect(requests).toHaveLength(0); fireEvent.click(screen.getAllByRole('checkbox')[0]); await inspect();
 expect(requests).toHaveLength(1); expect(requests[0]).toMatchObject({ method: 'POST', path: '/diagnostics/previews', body: { project_id: 'project-one', attempt_ids: [attempts[0].id] } });
 expect(JSON.stringify(requests)).not.toContain('私有正文不得发送'); expect(screen.getByText('提示词、正文、路径与令牌')).toBeTruthy(); expect(screen.getByLabelText('诊断范围').closest('fieldset')?.disabled).toBe(true); expect(screen.getByRole('button', { name: '保存诊断 ZIP' }).hasAttribute('disabled')).toBe(true);
});
it('最多20个指定运行，整个库预览仍只发送已选择的编号', async () => {
 view(); fireEvent.change(screen.getByLabelText('诊断范围'), { target: { value: 'all' } }); const boxes = screen.getAllByRole('checkbox');
 for (const box of boxes.slice(0, 20)) fireEvent.click(box);
 expect(boxes[20].hasAttribute('disabled')).toBe(true); await inspect(); expect(requests[0].body).toEqual({ project_id: null, attempt_ids: attempts.slice(0,20).map(value => value.id) });
});
it('选择原生保存目录后带宿主授权，只有明确保存才创建ZIP', async () => {
 nativePicker = true; view(); await inspect(); expect(screen.getByLabelText('诊断保存目录').hasAttribute('readonly')).toBe(true); fireEvent.click(screen.getByRole('button', { name: '选择位置' }));
 await waitFor(() => expect((screen.getByLabelText('诊断保存目录') as HTMLInputElement).value).toBe('/明确选择的诊断目录')); expect(requests).toHaveLength(1);
 fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await screen.findByText('诊断 ZIP 已保存，文件完整性已核对。');
 expect(requests.find(value => value.path === '/diagnostics/exports')?.body).toEqual({ preview_id: identifier, target_dir: '/明确选择的诊断目录', grant_id: 'native-grant' });
});
it.each(['CONTROL_UNAVAILABLE', 'LOCAL_BRIDGE', 'INTERNAL_ERROR', 'NETWORK_FAILURE'])('导出 %s 响应不明保留原body/key，冻结目录与范围', async code => {
 const rendered = view(); await target(); exportFailure = code; fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await screen.findByRole('button', { name: '重试原导出请求' });
 expect(screen.getByLabelText('诊断保存目录').hasAttribute('disabled')).toBe(true); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' })); expect(rendered.onClose).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button', { name: '重试原导出请求' })); await screen.findByText('诊断 ZIP 已保存，文件完整性已核对。'); const sent = requests.filter(value => value.path === '/diagnostics/exports'); expect(sent).toHaveLength(2); expect(sent[0]).toEqual(sent[1]);
});
it('明确的路径拒绝允许修正目标，用新key提交新目标', async () => {
 view(); await target(); exportFailure = 'PATH_NOT_ALLOWED'; fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await screen.findByText('导出回执未确认'); expect(screen.getByLabelText('诊断保存目录').hasAttribute('disabled')).toBe(false);
 fireEvent.change(screen.getByLabelText('诊断保存目录'), { target: { value: '/新授权目录' } }); fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await screen.findByText('诊断 ZIP 已保存，文件完整性已核对。');
 const sent = requests.filter(value => value.path === '/diagnostics/exports'); expect(sent[0].key).not.toBe(sent[1].key); expect(sent[1].body.target_dir).toBe('/新授权目录');
});
it('取消确认后迟到的writing导出回执不能回滚终态或保留重试出口', async () => {
 const original = vi.mocked(fetch).getMockImplementation()!; let finish!: (value: Response) => void;
 vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/diagnostics/exports') ? new Promise(resolve => { finish = resolve; }) : original(input, options));
 view(); await target(); fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await waitFor(() => expect(finish).toBeTruthy());
 fireEvent.click(screen.getByRole('button', { name: '取消此次诊断导出' })); await screen.findByText('已取消'); await act(async () => finish(response({ ...ready, status: 'writing', can_export: false })));
 expect(screen.getByText('已取消')).toBeTruthy(); expect(screen.queryByText('正在保存')).toBeNull(); expect(screen.queryByRole('button', { name: '重试原导出请求' })).toBeNull(); expect(screen.getByRole('button', { name: '关闭对话框' }).hasAttribute('disabled')).toBe(false);
});
it('取消确认后迟到的状态读取也不能把终态变回进行中', async () => {
 const original = vi.mocked(fetch).getMockImplementation()!; let finish!: (value: Response) => void;
 view(); await target(); exportFailure = 'CONTROL_UNAVAILABLE'; fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); await screen.findByRole('button', { name: '读取原导出状态' });
 vi.mocked(fetch).mockImplementation(async (input, options) => options?.method === 'GET' ? new Promise(resolve => { finish = resolve; }) : original(input, options));
 fireEvent.click(screen.getByRole('button', { name: '读取原导出状态' })); fireEvent.click(screen.getByRole('button', { name: '取消此次诊断导出' })); await screen.findByText('已取消');
 await act(async () => finish(response({ ...ready, status: 'writing', can_export: false }))); expect(screen.getByText('已取消')).toBeTruthy(); expect(screen.queryByText('正在保存')).toBeNull();
});
it('取消响应不明保留原取消请求编号并冻结范围，明确重试后显示终态', async () => {
 view(); await inspect(); cancelFailure = 'CONTROL_UNAVAILABLE'; fireEvent.click(screen.getByRole('button', { name: '取消此次诊断导出' })); await screen.findByRole('button', { name: '重试原取消请求' });
 expect(screen.getByRole('button', { name: '关闭对话框' }).hasAttribute('disabled')).toBe(true); expect(screen.queryByRole('button', { name: '重新选择范围' })).toBeNull(); fireEvent.click(screen.getByRole('button', { name: '重试原取消请求' })); await screen.findByText('已取消');
 const sent = requests.filter(value => value.path.endsWith('/cancel')); expect(sent).toHaveLength(2); expect(sent[0]).toEqual(sent[1]);
});
it('取消时服务已发布则读取原状态，显示待核实而不显示假取消', async () => {
 view(); await inspect(); record = { ...ready, status: 'registration_pending', can_export: false, can_cancel: false, saved_path: '/已有文件.zip', error: { code: 'DIAGNOSTICS_REGISTRATION_PENDING', message: '原文件状态待核实' } }; cancelFailure = 'DIAGNOSTICS_ALREADY_PUBLISHED';
 fireEvent.click(screen.getByRole('button', { name: '取消此次诊断导出' })); await screen.findByText('文件状态待核实'); expect(screen.queryByText('已取消')).toBeNull(); expect(screen.getByText('/已有文件.zip')).toBeTruthy(); expect(screen.queryByText('诊断 ZIP 已保存，文件完整性已核对。')).toBeNull();
 expect(requests.filter(value => value.method === 'GET').map(value => value.path)).toEqual(['/diagnostics/previews/' + identifier]);
});
it('项目切换后迟到的原预览不能进入新范围，选择与目标同时重置', async () => {
 let finish!: (value: Response) => void; vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
 const rendered = view(); fireEvent.click(screen.getAllByRole('checkbox')[0]); fireEvent.click(screen.getByRole('button', { name: '预览诊断范围' }));
 rendered.rerender(<DiagnosticsDialog projectId="project-two" attempts={[]} onClose={rendered.onClose} />); await act(async () => finish(response(ready)));
 expect(screen.queryByLabelText('诊断范围预览')).toBeNull(); expect(screen.getByRole('button', { name: '预览诊断范围' }).hasAttribute('disabled')).toBe(false); await inspect(); expect(requests.at(-1)?.body).toEqual({ project_id: 'project-two', attempt_ids: [] });
});

it('取消已确认后迟到的原导出网络错误不重新宣称响应未知', async () => {
 const original = vi.mocked(fetch).getMockImplementation()!; let fail!: (reason: unknown) => void;
 vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/diagnostics/exports') ? new Promise((_resolve, reject) => { fail = reject; }) : original(input, options));
 view(); await target(); fireEvent.click(screen.getByRole('button', { name: '保存诊断 ZIP' })); fireEvent.click(screen.getByRole('button', { name: '取消此次诊断导出' })); await screen.findByText('已取消');
 await act(async () => fail(new TypeError('迟到的网络失败'))); expect(screen.getByText('已取消')).toBeTruthy(); expect(screen.queryByText('迟到的网络失败')).toBeNull(); expect(screen.queryByRole('button', { name: '重试原导出请求' })).toBeNull();
});
