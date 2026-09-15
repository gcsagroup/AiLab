import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import ModelDownloadDialog, { type ModelDownload } from '../../apps/desktop/src/ModelDownloadDialog';
import { MarketSourceSettings } from '../../apps/desktop/src/MarketSourceSettings';

let native = false;
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => native, invoke: vi.fn() }));
const catalog = { id: 'fixed-model-v1', name: '固定官方模型', repo: 'official/model', revision: 'fixed-revision', source_url: 'https://huggingface.co/official/model/tree/fixed-revision', license: 'Apache-2.0', manifest_digest: 'fixed-digest', total_bytes: 1024, network_scope: '只请求已列出的固定文件。', capability: '文本生成与训练，质量需要实际核对。', files: [{ path: 'model.safetensors', size: 1024, sha256: 'a'.repeat(64) }] };
const model = { id: 'model-new', name: '新登记模型', format: 'safetensors', modality: 'text' };
let record: ModelDownload; let requests: { path: string; method: string; body: unknown; key?: string }[]; let failure: string | null; let providerOrigin: string | null;
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
beforeEach(() => {
 HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
 native = false; requests = []; failure = null; providerOrigin = null; record = { id: 'download-one', project_id: 'project-one', name: '固定官方模型', state: 'completed', received_bytes: 1024, total_bytes: 1024, current_file: null, cancel_requested: false, model_id: null };
 vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
  const path = String(input).replace('/api/v1', ''); const method = options?.method || 'GET'; const body = options?.body ? JSON.parse(String(options.body)) : {};
  requests.push({ path, method, body, key: (options?.headers as Record<string, string>)?.['Idempotency-Key'] });
  if (method === 'GET') {
   if (path === '/model-catalog') return response({ items: [catalog] });
   if (path === '/model-downloads/download-one') return response(record);
   if (path === '/models/model-new') return response(model);
   if (path === '/market/sources') return response({ items: providerOrigin ? [{ provider_id: 'fixture-provider', origin: providerOrigin, source_label: '受控测试来源' }] : [] });
  }
  if (failure) { const code = failure; failure = null; return response({ error: { code, message: '写入回执未确认' } }, false); }
  if (path === '/model-downloads' || path.endsWith('/resume')) { record = { ...record, state: 'completed', received_bytes: 1024, cancel_requested: false }; return response(record); }
  if (path.endsWith('/cancel')) { record = { ...record, state: 'cancelled', cancel_requested: true }; return response(record); }
  if (path.endsWith('/models')) { record = { ...record, model_id: model.id }; return response(model); }
  throw new Error('未声明请求：' + method + ' ' + path);
 }));
 vi.mocked(invoke).mockImplementation(async (name, args: any) => {
  if (name === 'host_status') return { market_fixture_origin: providerOrigin } as any;
  if (name === 'configure_market_fixture') { providerOrigin = args.origin; return { market_fixture_origin: providerOrigin } as any; }
  throw new Error('未声明宿主命令：' + name);
 });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function view(initial?: ModelDownload) { const callbacks = { onClose: vi.fn(), onChanged: vi.fn(), onUse: vi.fn() }; render(<ModelDownloadDialog projectId="project-one" initial={initial} {...callbacks} />); return callbacks; }
async function readyDownload() { const button = await screen.findByRole('button', { name: '下载并核对固定模型' }); await waitFor(() => expect(button.matches(':disabled')).toBe(false)); return button; }

it('打开模型准备页只读固定目录，明确按钮才请求下载', async () => {
 view(); await screen.findByText('只请求已列出的固定文件。'); expect(requests.map(value => value.method)).toEqual(['GET']);
 fireEvent.click(screen.getByRole('button', { name: '下载并核对固定模型' })); await screen.findByRole('button', { name: '加入当前项目模型库' });
 expect(requests.find(value => value.method === 'POST')?.body).toEqual({ project_id: 'project-one', catalog_id: catalog.id, manifest_digest: catalog.manifest_digest });
 expect(requests.some(value => value.path.includes('/tasks') || value.path.includes('/attempts'))).toBe(false);
});
it('下载完整后仍需明确登记，再由试用按钮交给上层建立草稿', async () => {
 const callbacks = view(); fireEvent.click(await readyDownload());
 expect(callbacks.onUse).not.toHaveBeenCalled(); fireEvent.click(await screen.findByRole('button', { name: '加入当前项目模型库' }));
 await screen.findByRole('status'); expect(callbacks.onUse).not.toHaveBeenCalled(); expect(requests.filter(value => value.method === 'POST').map(value => value.path)).toEqual(['/model-downloads', '/model-downloads/download-one/models']);
 fireEvent.click(screen.getByRole('button', { name: '用此模型开始试用' })); expect(callbacks.onUse).toHaveBeenCalledWith(model);
});
it.each(['CONTROL_UNAVAILABLE', 'CONTROL_RESPONSE_INVALID', 'LOCAL_BRIDGE', 'INTERNAL_ERROR'])('模型下载 %s 响应不明后保留 body/key', async code => {
 view(); failure = code; fireEvent.click(await readyDownload()); fireEvent.click(await screen.findByRole('button', { name: '重试上次操作' }));
 await screen.findByRole('button', { name: '加入当前项目模型库' }); const sent = requests.filter(value => value.path === '/model-downloads'); expect(sent).toHaveLength(2); expect(sent[0]).toEqual(sent[1]);
});
it('线程启动失败以持久记录显示，仅明确续传原编号', async () => {
 record = { ...record, state: 'failed', received_bytes: 0, error: { code: 'MODEL_DOWNLOAD_START_FAILED', message: '线程未启动，原记录保留' } }; view(record);
 await screen.findByText('线程未启动，原记录保留'); expect(requests.every(value => value.method === 'GET')).toBe(true);
 fireEvent.click(screen.getByRole('button', { name: '继续下载并核对' })); await screen.findByRole('button', { name: '加入当前项目模型库' }); expect(requests.find(value => value.method === 'POST')?.path).toBe('/model-downloads/download-one/resume');
});
it('下载中显示实际字节，明确停止后允许继续且保持原编号', async () => {
 record = { ...record, state: 'downloading', received_bytes: 256, current_file: 'model.safetensors' }; view(record);
 expect(screen.getByRole('progressbar').getAttribute('value')).toBe('256'); await screen.findByText(/256 B/);
 fireEvent.click(screen.getByRole('button', { name: '停止下载，保留进度' })); await screen.findByRole('button', { name: '继续下载并核对' }); expect(requests.find(value => value.method === 'POST')?.path).toBe('/model-downloads/download-one/cancel');
});
it('原完成记录已登记时只读取原模型，不再次写登记请求', async () => {
 record.model_id = model.id; const callbacks = view(record); fireEvent.click(await screen.findByRole('button', { name: '用此模型开始试用' })); expect(callbacks.onUse).toHaveBeenCalledWith(model); expect(requests.every(value => value.method === 'GET')).toBe(true);
});
it('浏览器来源设置只读当前注册来源，不提供任意地址写入口', async () => {
 providerOrigin = 'http://127.0.0.1:54001'; render(<MarketSourceSettings onChanged={vi.fn()} />); await screen.findByText('当前来源：http://127.0.0.1:54001');
 expect(screen.queryByRole('button', { name: '连接受控来源' })).toBeNull(); expect(vi.mocked(invoke)).not.toHaveBeenCalled();
});
it('桌面设置只接收有效端口，明确连接与断开才更改固定回环来源', async () => {
 native = true; const changed = vi.fn(); render(<MarketSourceSettings onChanged={changed} />); await screen.findByText('当前来源：未连接'); expect(vi.mocked(invoke).mock.calls.map(value => value[0])).toEqual(['host_status']);
 for (const invalid of ['0', '0123', '65536', 'https', '-1']) { fireEvent.change(screen.getByLabelText('本机提供方端口'), { target: { value: invalid } }); expect(screen.getByRole('button', { name: '连接受控来源' }).hasAttribute('disabled')).toBe(true); }
 fireEvent.change(screen.getByLabelText('本机提供方端口'), { target: { value: '54001' } }); fireEvent.click(screen.getByRole('button', { name: '连接受控来源' })); await screen.findByText('当前来源：http://127.0.0.1:54001');
 expect(vi.mocked(invoke)).toHaveBeenCalledWith('configure_market_fixture', { origin: 'http://127.0.0.1:54001' }); fireEvent.click(screen.getByRole('button', { name: '断开来源' })); await screen.findByText('当前来源：未连接'); expect(vi.mocked(invoke)).toHaveBeenCalledWith('configure_market_fixture', { origin: null }); expect(changed).toHaveBeenCalledTimes(2);
});
it('宿主配置回执不明时冻结修改，重新读取真实状态而非重复发送写操作', async () => {
 native = true; render(<MarketSourceSettings onChanged={vi.fn()} />); await screen.findByText('当前来源：未连接');
 vi.mocked(invoke).mockImplementation(async (name, args: any) => { if (name === 'configure_market_fixture') { providerOrigin = args.origin; throw { error: { code: 'CONTROL_UNAVAILABLE', message: '回执尚未确认' } }; } return { market_fixture_origin: providerOrigin } as any; });
 fireEvent.change(screen.getByLabelText('本机提供方端口'), { target: { value: '54001' } }); fireEvent.click(screen.getByRole('button', { name: '连接受控来源' })); await screen.findByText('当前来源：状态待确认'); expect(screen.getByLabelText('本机提供方端口').hasAttribute('disabled')).toBe(true);
 fireEvent.click(screen.getByRole('button', { name: '重新读取连接状态' })); await screen.findByText('当前来源：http://127.0.0.1:54001'); expect(vi.mocked(invoke).mock.calls.filter(value => value[0] === 'configure_market_fixture')).toHaveLength(1);
});
