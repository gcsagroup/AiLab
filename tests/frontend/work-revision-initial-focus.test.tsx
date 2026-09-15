import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { WorkRevisions } from '../../apps/desktop/src/WorkRevisions';
import type { Work } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));

const work: Work = { id: 'work-a', name: '甲作品', attempt_id: 'attempt-a', kind: 'video', artifact_id: 'original-artifact', media_type: 'video/mp4' };
const other: Work = { ...work, id: 'work-b', name: '乙作品' };
const dialogDescriptors = {
  showModal: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'),
  close: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close'),
};
let requests: { method: string; path: string }[];
let reads: Map<string, (value: Response) => void>;
let bodyTabIndex: string | null;

function savedView(selected: Work) {
  return { work_id: selected.id, work_revision: 1, current_revision_id: null, content_kind: 'subtitles', duration_ms: 2000,
    original: { revision_id: null, artifact_id: selected.artifact_id, sha256: 'a'.repeat(64), content: { cues: [{ start_ms: 0, end_ms: 1000, text: `${selected.name}原字幕` }] }, basis: 'generated_subtitles' },
    items: [], has_more: false, next_before_revision: null, media_policy: '原媒体不变' };
}
function response(value: unknown, ok = true): Response {
  return { ok, json: async () => structuredClone(value) } as Response;
}
async function finish(selected: Work, failed = false) {
  const release = reads.get(selected.id);
  expect(release).toBeTypeOf('function');
  await act(async () => release!(failed
    ? response({ error: { code: 'READ_FAILED', message: '首次版本读取失败' } }, false)
    : response(savedView(selected))));
}
function revisions(selected = work) {
  return <WorkRevisions work={selected} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />;
}

beforeEach(() => {
  requests = []; reads = new Map(); bodyTabIndex = document.body.getAttribute('tabindex');
  // 只补 jsdom 缺少的原生模态首次聚焦；不会在 busy 或 GET 完成时替产品回焦。
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) {
    this.open = true; this.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, options: RequestInit = {}) => {
    const path = String(input), method = options.method || 'GET'; requests.push({ method, path });
    const selected = [work, other].find(item => path === `/api/v1/works/${item.id}/revisions?limit=100`);
    if (method !== 'GET' || !selected || reads.has(selected.id)) throw new Error('未声明或重复的请求：' + method + ' ' + path);
    return new Promise<Response>(resolve => reads.set(selected.id, resolve));
  }));
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  if (bodyTabIndex === null) document.body.removeAttribute('tabindex');
  else document.body.setAttribute('tabindex', bodyTabIndex);
  for (const [name, descriptor] of Object.entries(dialogDescriptors)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  }
});

async function pendingClose() {
  const close = screen.getByRole('button', { name: '关闭对话框' }) as HTMLButtonElement;
  await waitFor(() => expect(close.disabled).toBe(true));
  expect(screen.getByRole('status').textContent).toContain('正在读取作品版本');
  return close;
}
function simulateHostFocusLoss() {
  // 显式模拟 WebKit 将禁用控件焦点移到 BODY 的前置；不是对浏览器根因的证明。
  document.body.setAttribute('tabindex', '-1'); document.body.focus();
  expect(document.activeElement).toBe(document.body);
}

it.each([false, true])('首次 GET %s（false成功／true失败）结束后，失效焦点回到可用关闭按钮且不滚动', async failed => {
  render(revisions());
  const close = await pendingClose(); simulateHostFocusLoss();
  const focus = vi.spyOn(close, 'focus');
  await finish(work, failed);
  await waitFor(() => expect(close.disabled).toBe(false));
  expect(screen.getByRole('dialog').textContent).toContain(failed ? '首次版本读取失败' : '甲作品原字幕');
  expect(document.activeElement === close, `首次读取结束后应回到关闭按钮；实际为 ${document.activeElement?.tagName}`).toBe(true);
  expect(focus).toHaveBeenCalledWith({ preventScroll: true });
  expect(requests).toEqual([{ method: 'GET', path: '/api/v1/works/work-a/revisions?limit=100' }]);
});

it('读取期间用户已聚焦真实播放器的可用按钮，完成后保留焦点和滚动位置', async () => {
  render(revisions()); await pendingClose();
  const dialog = screen.getByRole('dialog'), play = screen.getByRole('button', { name: '播放视频' });
  play.focus(); dialog.scrollTop = 240;
  expect(document.activeElement).toBe(play); expect((play as HTMLButtonElement).disabled).toBe(false);
  await finish(work);
  expect(document.activeElement).toBe(play); expect(dialog.scrollTop).toBe(240);
  expect(requests).toHaveLength(1); // 未点击播放，不读取媒体；真实 MediaPreview 保持挂载。
});

it('首次 GET 未完成时卸载，旧响应不抢走后续页面焦点', async () => {
  const mounted = render(<><button>页面后续操作</button>{revisions()}</>);
  await pendingClose(); simulateHostFocusLoss();
  mounted.rerender(<button>页面后续操作</button>);
  const next = screen.getByRole('button', { name: '页面后续操作' }); next.focus();
  await finish(work);
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.activeElement).toBe(next);
  expect(requests).toHaveLength(1);
});

it('切换作品后旧 GET 不结束新读取、不覆盖正文或抢新播放器焦点', async () => {
  const mounted = render(revisions()); await pendingClose(); simulateHostFocusLoss();
  mounted.rerender(revisions(other));
  const close = await pendingClose(), play = screen.getByRole('button', { name: '播放视频' }); play.focus();
  await finish(work);
  expect(close.disabled).toBe(true); expect(document.activeElement).toBe(play);
  expect(screen.getByRole('dialog').textContent).not.toContain('甲作品原字幕');
  await finish(other);
  expect(close.disabled).toBe(false); expect(document.activeElement).toBe(play);
  expect(screen.getByRole('dialog').textContent).toContain('乙作品原字幕');
  expect(requests).toEqual(['work-a', 'work-b'].map(id => ({ method: 'GET', path: `/api/v1/works/${id}/revisions?limit=100` })));
});
