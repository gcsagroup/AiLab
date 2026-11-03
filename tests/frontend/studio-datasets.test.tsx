import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Datasets from '../../apps/desktop/src/studio/Datasets';
import StudioApp from '../../apps/desktop/src/studio/StudioApp';

const api = vi.hoisted(() => vi.fn());
vi.mock('../../apps/desktop/src/api', () => ({ api, canPickFile: () => false, pickStudioPath: vi.fn(), errorMessage: (e: unknown) => String(e) }));
vi.mock('../../apps/desktop/src/ExitPreparation', () => ({ useExitPreparation: () => ({ error: '' }) }));
const local = { id: 'data', name: 'Download', source: 'huggingface', path: 'C:/data', size: 80, category: 'sft', purpose: 'training', managed: true,
  provenance: { revision: 'abc', license: 'mit' }, files: [{ path: 'train.jsonl', size: 80, sha256: 'abc' }, { path: 'test.jsonl', size: 30, sha256: 'def' }] };
const detail = { id: 'selection', provider: 'huggingface', dataset: 'owner/data', title: 'My data', revision: 'a'.repeat(40), requested_revision: 'main', versions: ['main', 'v1'], license: 'mit', description: 'A dataset description', source_url: 'https://huggingface.co/datasets/owner/data', files: [{ path: 'train.jsonl', size: 80 }, { path: 'README.md', size: 20 }] };
beforeEach(() => {
  localStorage.clear(); api.mockReset();
  api.mockImplementation(async (method: string, path: string, body: unknown) => {
    if (path.endsWith('/datasets/local')) return { items: [local], directory: 'C:/data', free_bytes: 1048576 };
    if (path.endsWith('/datasets/downloads')) return method === 'GET' ? { items: [] } : { id: 'job' };
    if (path.endsWith('/datasets/sources')) return { items: [{ id: 'huggingface', name: 'Hugging Face', credential_configured: false }] };
    if (path.endsWith('/datasets/search')) return { items: [{ id: 'owner/data', title: 'My data', description: 'Search result', downloads: 10, license: 'mit' }], has_more: false };
    if (path.endsWith('/datasets/detail')) return detail;
    if (path.endsWith('/use')) return { path: 'C:/data/train.jsonl' };
    if (path.endsWith('/status')) return { hardware: { os: 'Windows', gpus: [], memory_gb: 16 }, runtimes: [], paths: {} };
    if (path.endsWith('/assets')) return { models: [], datasets: [] };
    if (path.endsWith('/settings')) return { max_concurrent_tasks: 1 };
    return body || { items: [] };
  });
});
afterEach(cleanup);
const mount = () => render(<Datasets assets={{ models: [], datasets: [] }} refreshAssets={vi.fn()} settings={vi.fn()} onUse={vi.fn()} />);

it('searches the actual provider API and downloads the fixed selection, not edited revision text', async () => {
  mount();
  fireEvent.change(screen.getByLabelText('搜索数据集'), { target: { value: 'cyber' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }));
  fireEvent.click(await screen.findByRole('button', { name: /My data/ }));
  await screen.findByText('A dataset description');
  fireEvent.change(screen.getByLabelText('版本 / Revision'), { target: { value: 'v1' } });
  expect(screen.getByRole('button', { name: '下载所选文件' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('版本 / Revision'), { target: { value: 'main' } });
  fireEvent.click(screen.getByRole('button', { name: '下载所选文件' }));
  await waitFor(() => expect(api).toHaveBeenCalledWith('POST', '/studio/datasets/downloads', { selection_id: 'selection', files: ['train.jsonl'], category: 'general', purpose: 'research' }));
  expect(api).toHaveBeenCalledWith('POST', '/studio/datasets/search', { provider: 'huggingface', query: 'cyber', page: 1 });
});

it('takes the chosen local file into the existing SFT form without starting training', async () => {
  render(<StudioApp />);
  fireEvent.click(screen.getByRole('button', { name: '数据集', exact: true }));
  fireEvent.click(await screen.findByRole('tab', { name: '本地数据集' }));
  fireEvent.click(await screen.findByRole('button', { name: '查看文件' }));
  fireEvent.click(screen.getAllByRole('button', { name: '用于 SFT' })[0]);
  await waitFor(() => expect(screen.getByLabelText('数据集文件或目录')).toHaveValue('C:/data/train.jsonl'));
  expect(api.mock.calls.some(call => call[1] === '/studio/sft')).toBe(false);
  expect(screen.getByRole('button', { name: '开始训练' })).toBeDisabled();
});

it('does not put credentials in browser drafts', async () => {
  mount();
  fireEvent.click(screen.getByRole('button', { name: '访问凭据' }));
  fireEvent.change(screen.getByLabelText('访问 Token / Key'), { target: { value: 'only-in-memory' } });
  api.mockResolvedValueOnce({ items: [] });
  fireEvent.click(screen.getByRole('button', { name: '应用到本次会话' }));
  await waitFor(() => expect(api).toHaveBeenCalledWith('POST', '/studio/datasets/credentials', { provider: 'huggingface', token: 'only-in-memory', username: '' }));
  expect(JSON.stringify(localStorage)).not.toContain('only-in-memory');
});

it('shows provider failures instead of populating a fake marketplace', async () => {
  mount();
  await screen.findByText('匿名访问公开数据');
  api.mockImplementation(async (_m: string, path: string) => { if (path.endsWith('/search')) throw new Error('network offline'); return { items: [] }; });
  fireEvent.click(screen.getByRole('button', { name: '搜索', exact: true }));
  expect(await screen.findByRole('alert')).toHaveTextContent('network offline');
  expect(screen.queryByRole('button', { name: /My data/ })).not.toBeInTheDocument();
});
