import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { WorkRevisions } from '../../apps/desktop/src/WorkRevisions';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));

const work = { id: 'work-a', name: '百次修订作品', attempt_id: 'attempt-a', kind: 'text' as const, artifact_id: 'original-artifact', media_type: 'text/plain' };
function revision(number: number) {
  return { id: `revision-${number}`, work_id: work.id, parent_revision_id: number === 2 ? null : `revision-${number - 1}`, revision: number, content_kind: 'text', content: { text: `已保存正文 ${number}` }, artifact_id: `artifact-${number}`, editor: 'user_action', created_at: '2026-09-10T01:00:00Z', changes: { diff: `-正文 ${number - 1}\n+正文 ${number}` }, source_artifact_sha256: 'a'.repeat(64) };
}
const history = Array.from({ length: 101 }, (_, index) => revision(index + 2));
function page(before?: number, current = 102) {
  const all = current === 102 ? history : [...history, revision(current)];
  const eligible = all.filter(item => before === undefined || item.revision < before);
  const items = eligible.slice(-100), has_more = eligible.length > items.length;
  return { work_id: work.id, work_revision: current, current_revision_id: `revision-${current}`, content_kind: 'text', duration_ms: null, original: { revision_id: null, artifact_id: 'original-artifact', sha256: 'a'.repeat(64), content: { text: '不可变原输出' }, basis: 'generated_text' }, items, has_more, next_before_revision: has_more ? items[0].revision : null, media_policy: '原媒体不变' };
}
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) });
let requests: string[];

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  requests = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    expect(init.method).toBe('GET');
    const url = new URL(String(input), 'http://localhost'); requests.push(url.pathname + url.search);
    return response(page(url.searchParams.has('before_revision') ? Number(url.searchParams.get('before_revision')) : undefined));
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('作品修订历史分页', () => {
  it('第101次修订之后仍可查看最早正文、父版本和差异，导出固定所选旧编号', async () => {
    const exported = vi.fn(), updated = vi.fn();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={updated} onExport={exported} />);
    expect(await screen.findByText('已保存正文 102')).toBeTruthy();
    expect(screen.queryByRole('option', { name: /^修订版 2 ·/ })).toBeNull();
    fireEvent.change(screen.getByLabelText('查看作品版本'), { target: { value: 'revision-3' } });
    fireEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await screen.findByRole('option', { name: /^修订版 2 ·/ });
    expect((screen.getByLabelText('查看作品版本') as HTMLSelectElement).value).toBe('revision-3');
    expect(screen.getByText('修订版 2', { selector: 'dd' })).toBeTruthy();
    expect(screen.getAllByRole('option')).toHaveLength(102);
    expect(screen.queryByRole('button', { name: '加载更早版本' })).toBeNull();
    fireEvent.change(screen.getByLabelText('查看作品版本'), { target: { value: 'revision-2' } });
    expect(screen.getByText('已保存正文 2')).toBeTruthy();
    expect(screen.getByText('原版', { selector: 'dd' })).toBeTruthy();
    expect(screen.getByLabelText('修订差异').textContent).toBe('-正文 1\n+正文 2');
    fireEvent.click(screen.getByRole('button', { name: '导出所选修订版 2' }));
    expect(exported).toHaveBeenCalledWith({ work_revision_id: 'revision-2', name: '百次修订作品 · 修订版 2' });
    expect(screen.getByRole('option', { name: /^修订版 102 · 当前/ })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('查看作品版本'), { target: { value: 'original' } });
    expect(screen.getByText('不可变原输出')).toBeTruthy();
    expect(updated).not.toHaveBeenCalled();
    expect(requests).toEqual(['/api/v1/works/work-a/revisions?limit=100', '/api/v1/works/work-a/revisions?limit=100&before_revision=3']);
  });

  it('更早页读取失败保留原选择和游标，重试不重复版本', async () => {
    const fetcher = vi.mocked(fetch), initial = fetcher.getMockImplementation()!;
    let fail = true;
    fetcher.mockImplementation(async (...args) => {
      if (String(args[0]).includes('before_revision') && fail) { fail = false; throw new Error('更早版本读取中断'); }
      return initial(...args);
    });
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await screen.findByText('已保存正文 102');
    fireEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await screen.findByText('更早版本读取中断');
    expect(screen.getByText('已保存正文 102')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await screen.findByRole('option', { name: /^修订版 2 ·/ });
    expect(screen.getAllByRole('option')).toHaveLength(102);
    expect((screen.getByLabelText('查看作品版本') as HTMLSelectElement).value).toBe('revision-102');
  });

  it('读取期间作品已有新修订时保留选择并要求刷新，不能把旧页标成当前版本', async () => {
    let current = 102;
    vi.mocked(fetch).mockImplementation(async input => {
      const url = new URL(String(input), 'http://localhost');
      if (url.searchParams.has('before_revision')) current = 103;
      return response(page(url.searchParams.has('before_revision') ? Number(url.searchParams.get('before_revision')) : undefined, current)) as Response;
    });
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await screen.findByText('已保存正文 102');
    fireEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await screen.findByText('作品已有新修订，请重新读取当前版本后继续。');
    expect((screen.getByLabelText('查看作品版本') as HTMLSelectElement).value).toBe('revision-102');
    expect(screen.getByText('待重新读取')).toBeTruthy();
    expect(screen.queryByText('当前版本', { selector: '.badge' })).toBeNull();
    expect(screen.queryByRole('option', { name: /· 当前/ })).toBeNull();
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '重新读取作品版本' }));
    await screen.findByText('已保存正文 103');
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('切换作品后丢弃上一作品的分页响应', async () => {
    let finish: (value: unknown) => void = () => {};
    vi.mocked(fetch).mockImplementation(async input => {
      const url = new URL(String(input), 'http://localhost');
      if (url.searchParams.has('before_revision')) return response(await new Promise(resolve => { finish = resolve; })) as Response;
      if (url.pathname.includes('work-b')) return response({ ...page(), work_id: 'work-b', current_revision_id: null, items: [], has_more: false, next_before_revision: null, original: { ...page().original, content: { text: '乙作品原输出' } } }) as Response;
      return response(page()) as Response;
    });
    const rendered = render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await screen.findByText('已保存正文 102');
    fireEvent.click(screen.getByRole('button', { name: '加载更早版本' }));
    await waitFor(() => expect((screen.getByLabelText('查看作品版本') as HTMLSelectElement).disabled).toBe(true));
    rendered.rerender(<WorkRevisions work={{ ...work, id: 'work-b' }} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await screen.findByText('乙作品原输出');
    await act(async () => { finish(page(3)); });
    expect(screen.getByText('乙作品原输出')).toBeTruthy();
    expect(screen.queryByRole('option', { name: /^修订版 2 ·/ })).toBeNull();
  });
});
