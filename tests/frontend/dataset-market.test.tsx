import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DatasetMarket, type MarketAccess, type MarketDownload, type MarketVersion } from '../../apps/desktop/src/DatasetMarket';
import type { Dataset, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
// 请求替身只验证真实组件的调用合同。独立 HTTP 下载和浏览器证据另行验收。
const moment = '2026-09-10T00:00:00Z';
const task: Task = { id: 'task-one', project_id: 'project-one', name: '原训练草稿', kind: 'text', operation: 'train', draft_revision: 7, draft: { kind: 'text', operation: 'train', model_id: 'model-one', dataset_id: 'old-data', input: { prompt: '原输入' }, runtime: { engine: 'mlx', device_id: 'local', seed: 919 } } };
const dataset: Dataset = { id: 'dataset-new', name: '已验证数据', schema: 'sft', status: 'ready', sample_count: 2 };
function version(id = 'version-one', extra: Partial<MarketVersion['metadata']> = {}): MarketVersion { return { id, project_id: 'project-one', provider_id: 'fixture-provider', version_digest: 'a'.repeat(64), metadata: { dataset_key: 'dialogue', version: id, name: '受控对话数据', description: '本机受控示例', modality: 'text', schema: 'sft', sample_count: 2, total_bytes: 1024, format: 'jsonl', provider_text: '提供方原始说明', source_url: null, updated_at: null, access: 'open', license: null, files: [{ path: 'data.jsonl', size: 1024, sha256: 'b'.repeat(64) }], ...extra } }; }
function download(extra: Partial<MarketDownload> = {}): MarketDownload { return { id: 'download-one', version_id: 'version-one', state: 'completed', received_bytes: 1024, complete: true, cancel_requested: false, dataset_id: null, created_at: moment, updated_at: moment, ...extra }; }
function access(status: MarketAccess['provider_response']['status'] = 'waiting', revision = 1): MarketAccess { const provider_response = { status, revision, provider_text: '提供方回复：' + status, updated_at: moment, expires_at: null }; return { id: 'access-one', version_id: 'version-one', created_at: moment, sent: { purpose: '本地测试用途', user_statement: '仅在本机验证' }, provider_response, response_history: [{ received_at: moment, response: provider_response }] }; }
let versions: MarketVersion[]; let downloads: MarketDownload[]; let accesses: MarketAccess[]; let datasets: Dataset[];
let requests: { path: string; method: string; body: any; key?: string }[]; let rejection: string | null; let applyConflict: boolean; let sources: { provider_id: string; source_label: string }[];
const response = (value: unknown, ok = true) => ({ ok, json: async () => structuredClone(value) }) as Response;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  versions = [version()]; downloads = []; accesses = []; datasets = []; requests = []; rejection = null; applyConflict = false; sources = [{ provider_id: 'fixture-provider', source_label: '受控测试来源' }];
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = options?.method || 'GET'; const body = options?.body ? JSON.parse(String(options.body)) : {};
    requests.push({ path, method, body, key: (options?.headers as Record<string, string>)?.['Idempotency-Key'] });
    if (method === 'GET') {
      if (path === '/market/sources') return response({ items: sources });
      if (path.startsWith('/market/catalog?')) return response({ versions, catalog_version: 'catalog-v1' });
      if (path.endsWith('/activity')) return response({ access_requests: accesses, downloads, datasets });
      if (path.startsWith('/market/downloads/')) return response(downloads.find(item => item.id === path.split('/').at(-1)));
    }
    if (path.endsWith('/market-contexts')) return response({ id: 'context-one', task_id: task.id, draft_revision: 7 });
    if (rejection) { const code = rejection; rejection = null; return response({ error: { code, message: '上次回执未确认' } }, false); }
    if (path === '/market/access-requests') { accesses = [access()]; return response(accesses[0]); }
    if (path.endsWith('/refresh')) return response(accesses[0]);
    if (path === '/market/downloads') { downloads = [download()]; return response(downloads[0]); }
    if (path.endsWith('/cancel')) { downloads = [download({ state: 'cancelled', complete: false, received_bytes: 256, cancel_requested: true, updated_at: '2026-09-10T00:00:01Z' })]; return response(downloads[0]); }
    if (path.endsWith('/resume')) { downloads = [download({ updated_at: '2026-09-10T00:00:02Z' })]; return response(downloads[0]); }
    if (path.endsWith('/datasets')) { datasets = [dataset]; downloads = [download({ dataset_id: dataset.id })]; return response(dataset); }
    if (path.endsWith('/use')) {
      if (applyConflict) return response({ error: { code: 'REVISION_CONFLICT', message: '原草稿已经改变，请返回核对。' } }, false);
      return response({ task: { ...task, draft_revision: 8, draft: { ...task.draft, dataset_id: dataset.id } }, return_to: { project_id: task.project_id, task_id: task.id, kind: 'text', step: 'data', highlight_dataset_id: dataset.id }, previous_checks_invalidated: true });
    }
    throw new Error('未声明请求 ' + method + ' ' + path);
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function view(withTask = false, strict = false) { const callbacks = { onClose: vi.fn(), onApplied: vi.fn(), onDatasetImported: vi.fn() }; const component = <DatasetMarket projectId="project-one" task={withTask ? task : undefined} {...callbacks} />; return { ...render(strict ? <React.StrictMode>{component}</React.StrictMode> : component), ...callbacks }; }
async function statement(value = '仅在本机验证') { fireEvent.change(await screen.findByLabelText('你的使用范围声明'), { target: { value } }); }
async function importDataset() { await statement(); fireEvent.click(await screen.findByRole('button', { name: '下载此版本' })); fireEvent.click(await screen.findByRole('button', { name: '检查并导入当前项目' })); await screen.findByText('已导入当前项目'); }

it('全局入口只读取目录，未公开的许可与样例不补写，无自动建任务或下载', async () => {
  view(); await statement(); expect(requests.every(item => item.method === 'GET')).toBe(true);
  expect(screen.getByText('未提供许可原文')).toBeTruthy(); expect(screen.getByText(/下载前样例：提供方尚未公开/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: '用于当前任务' })).toBeNull();
});
it('任务入口冻结原修订号，StrictMode 重复初始化保留相同命令编号', async () => {
  view(true, true); await statement(); const entries = requests.filter(item => item.path.endsWith('/market-contexts'));
  expect(entries.length).toBeGreaterThanOrEqual(1); expect(entries.every(item => JSON.stringify(item) === JSON.stringify(entries[0]))).toBe(true);
  expect(entries[0].body).toEqual({ expected_revision: 7, step: 'data' }); expect(entries[0].key).toBeTruthy();
});
it('下载与导入独立，导入后明确使用才改变原任务并返回数据步骤', async () => {
  const rendered = view(true); await importDataset(); expect(rendered.onDatasetImported).toHaveBeenCalledWith(dataset); expect(rendered.onApplied).not.toHaveBeenCalled();
  expect(requests.some(item => item.path.endsWith('/use'))).toBe(false); fireEvent.click(screen.getByRole('button', { name: '用于当前任务' }));
  await waitFor(() => expect(rendered.onApplied).toHaveBeenCalledTimes(1)); expect(rendered.onApplied.mock.calls[0][0]).toMatchObject({ task: { draft: { dataset_id: dataset.id, input: task.draft.input, runtime: task.draft.runtime } }, return_to: { step: 'data', highlight_dataset_id: dataset.id } });
  expect(requests.find(item => item.path.endsWith('/use'))?.body).toEqual({ dataset_id: dataset.id });
});
it('全局导入回我的数据，始终不创建任务上下文', async () => {
  const rendered = view(); await importDataset(); expect(rendered.onApplied).not.toHaveBeenCalled(); expect(requests.some(item => item.path.includes('/tasks/') || item.path.endsWith('/use'))).toBe(false);
});
it('受限数据仅发送最小申请字段，等待不下载，提供方批准后手动刷新才能继续', async () => {
  versions = [version('version-one', { access: 'restricted' })]; view(true); await statement(); fireEvent.change(screen.getByLabelText('申请用途'), { target: { value: '本地测试用途' } }); fireEvent.click(screen.getByRole('button', { name: '提交访问申请' }));
  await screen.findByText('等待提供方处理'); expect(screen.getByRole('button', { name: '下载此版本' }).hasAttribute('disabled')).toBe(true);
  expect(requests.find(item => item.path === '/market/access-requests')?.body).toEqual({ version_id: 'version-one', purpose: '本地测试用途', user_statement: '仅在本机验证' });
  expect(requests.some(item => /approve|decision/.test(item.path))).toBe(false); accesses = [access('approved', 2)]; fireEvent.click(screen.getByRole('button', { name: '刷新提供方状态' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '下载此版本' }).hasAttribute('disabled')).toBe(false)); expect(screen.getByText('提供方回复：approved')).toBeTruthy();
});
it.each(['denied', 'expired', 'revoked'] as const)('提供方 %s 状态不可下载，但可重新申请且保留原文', async status => {
  versions = [version('version-one', { access: 'restricted' })]; accesses = [access(status)]; view(); await statement(); expect(screen.getByRole('button', { name: '下载此版本' }).hasAttribute('disabled')).toBe(true); expect(screen.getByRole('button', { name: '重新提交访问申请' })).toBeTruthy(); expect(screen.getByText('提供方回复：' + status)).toBeTruthy();
});
it('显示实际字节进度，取消保留原下载编号，明确续传原文件后才可导入', async () => {
  downloads = [download({ state: 'downloading', complete: false, received_bytes: 256 })]; view(); await statement(); expect(screen.getByRole('progressbar').getAttribute('value')).toBe('256'); expect(screen.getByText(/25.0%/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: '取消下载并保留原字节' })); fireEvent.click(await screen.findByRole('button', { name: '继续下载保留的文件' })); await screen.findByRole('button', { name: '检查并导入当前项目' });
  expect(requests.filter(item => item.method === 'POST').map(item => item.path)).toEqual(['/market/downloads/download-one/cancel', '/market/downloads/download-one/resume']);
});
it.each(['CONTROL_UNAVAILABLE', 'LOCAL_BRIDGE', 'INTERNAL_ERROR', 'MARKET_PROVIDER_UNAVAILABLE'])('%s 后重试保留原 body 和 key，表单冻结', async code => {
  view(); await statement(); rejection = code; fireEvent.click(screen.getByRole('button', { name: '下载此版本' })); await screen.findByRole('button', { name: '重试并读取原结果' }); expect(screen.getByLabelText('你的使用范围声明').hasAttribute('disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '重试并读取原结果' })); await screen.findByRole('button', { name: '检查并导入当前项目' }); const sent = requests.filter(item => item.path === '/market/downloads'); expect(sent).toHaveLength(2); expect(sent[0]).toEqual(sent[1]);
});
it('草稿 CAS 冲突保留下载与导入结果，禁止再次使用并提示返回核对', async () => {
  const rendered = view(true); await importDataset(); applyConflict = true; fireEvent.click(screen.getByRole('button', { name: '用于当前任务' })); await screen.findByRole('button', { name: '返回原任务查看新草稿' });
  expect(rendered.onApplied).not.toHaveBeenCalled(); expect(screen.getByRole('button', { name: '用于当前任务' }).hasAttribute('disabled')).toBe(true); expect(screen.getByText('已导入当前项目')).toBeTruthy();
});
it('筛选其它类型后仍不能把图片数据用于文本任务', async () => {
  versions = [version('version-one', { modality: 'image', schema: 'image_caption_v1', name: '图片示例' })]; downloads = [download({ dataset_id: dataset.id })]; datasets = [{ ...dataset, schema: 'image_caption_v1' }]; view(true); await statement();
  expect(screen.getByRole('button', { name: '用于当前任务' }).hasAttribute('disabled')).toBe(true); expect(screen.getByText(/原任务需要文本 SFT/)).toBeTruthy();
});
it('版本切换后的迟到记录不能覆盖新版本', async () => {
  versions = [version(), version('version-two')]; let finish!: (value: Response) => void; const original = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/version-two/activity') ? new Promise(resolve => { finish = resolve; }) : original(input, options));
  view(); await screen.findByLabelText('数据版本'); await waitFor(() => expect(finish).toBeTruthy());
  // 切换版本控件在读取中锁定；通过刷新目录拿到新版本后，旧请求必须失效。
  versions = [version()]; fireEvent.click(screen.getByRole('button', { name: '刷新目录' })); await statement();
  await act(async () => finish(response({ access_requests: [], downloads: [download({ dataset_id: 'wrong-old' })], datasets: [] })));
  expect(screen.getByLabelText('数据版本').getAttribute('value') || (screen.getByLabelText('数据版本') as HTMLSelectElement).value).toBe('version-one'); expect(screen.queryByText('已导入当前项目')).toBeNull();
});
it('默认来源空白有可操作重新读取入口，不创建虚构目录', async () => {
  sources = []; view(); await screen.findByRole('heading', { name: '尚未登记受控数据来源' }); expect(screen.getByRole('button', { name: '重新读取来源' })).toBeTruthy(); expect(requests.filter(item => item.method === 'GET').map(item => item.path)).toEqual(['/market/sources']);
});
