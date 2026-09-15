import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../apps/desktop/src/App';
import { defaultProjectView } from '../../apps/desktop/src/ProjectContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));

const project = { id: 'project-a', name: '甲项目', revision: 1 };
const work = { id: 'work-original', project_id: project.id, name: '原正文作品', kind: 'text', attempt_id: 'attempt-original', artifact_id: 'original-artifact', media_type: 'text/plain', text: '原保存正文' };
const originalView = { work_id: work.id, work_revision: 1, current_revision_id: null, content_kind: 'text', duration_ms: null,
  original: { revision_id: null, artifact_id: work.artifact_id, sha256: 'a'.repeat(64), content: { text: work.text }, basis: 'generated_text' },
  items: [], has_more: false, next_before_revision: null, media_policy: '原媒体不变' };
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
const dialogDescriptors = {
  showModal: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'),
  close: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close'),
};
let requests: { method: string; path: string }[];

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); requests = [];
  let saved = { project_id: project.id, projects: { [project.id]: { ...defaultProjectView(), page: 'assets' } } };
  // 只补jsdom缺失的模态宿主行为，不替产品聚焦入口或关闭后回焦。
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) {
    this.setAttribute('open', '');
    this.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.removeAttribute('open'); } });
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{ width: 20, height: 20 }] as unknown as DOMRectList);
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const url = new URL(String(input), 'http://fixture'), path = url.pathname.replace('/api/v1', ''), method = options.method || 'GET';
    requests.push({ method, path });
    if (path === '/ui-context') {
      if (method === 'PATCH') {
        const body = JSON.parse(String(options.body));
        saved = { project_id: body.project_id, projects: { ...saved.projects, [body.project_id]: body.context } };
      }
      return response(saved);
    }
    if (method !== 'GET') throw new Error('入口焦点验证不允许业务写入：' + path);
    if (path === '/projects') return response({ items: [project] });
    if (path === `/projects/${project.id}`) return response(project);
    if (path === '/works') return response({ items: [work] });
    if (path === `/works/${work.id}/revisions`) {
      expect(url.search).toBe('?limit=100');
      return response(originalView);
    }
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  for (const [name, descriptor] of Object.entries(dialogDescriptors)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  }
});

async function openFromUnfocusedEntry(initial: 'BODY' | '其他按钮') {
  render(<App />);
  const opener = await screen.findByRole('button', { name: '文字修订' });
  if (initial === '其他按钮') {
    const other = screen.getByRole('button', { name: '导出原作品' });
    other.focus(); expect(document.activeElement).toBe(other);
  } else {
    expect(document.activeElement).toBe(document.body);
  }
  expect(document.activeElement).not.toBe(opener);
  // Safari鼠标入口可能不先聚焦；userEvent.click会预先focus，从而掩盖这个缺口。
  fireEvent.click(opener);
  await screen.findByRole('button', { name: '编辑当前版本' });
  return opener;
}

async function escape(user: ReturnType<typeof userEvent.setup>) {
  await user.keyboard('{Escape}');
  // jsdom没有Escape产生原生cancel的默认动作；事件仍交给真实Dialog处理。
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
}

async function expectReturnAndReopen(opener: HTMLElement, user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  const actual = document.activeElement;
  expect(actual === opener, `关闭后应回到同一修订入口；实际焦点=${actual?.tagName}/${actual?.textContent?.slice(0, 30)}`).toBe(true);
  await user.keyboard('{Enter}');
  await screen.findByRole('button', { name: '编辑当前版本' });
  expect(screen.getByRole('dialog').textContent).toContain(work.text);
  expect(requests.filter(item => item.path === `/works/${work.id}/revisions`)).toEqual([
    { method: 'GET', path: `/works/${work.id}/revisions` }, { method: 'GET', path: `/works/${work.id}/revisions` },
  ]);
  expect(requests.filter(item => item.method !== 'GET' && item.path !== '/ui-context')).toEqual([]);
  expect(originalView.original.content.text).toBe('原保存正文');
}

it.each(['BODY', '其他按钮'] as const)('鼠标入口未聚焦且原焦点为%s时，关闭后回同一入口并可按Enter重开', async initial => {
  const user = userEvent.setup(), opener = await openFromUnfocusedEntry(initial);
  if (initial === 'BODY') await escape(user);
  else await user.click(screen.getByRole('button', { name: '关闭对话框' }));
  await expectReturnAndReopen(opener, user);
});

it('真实作品入口编辑后继续核对保留原输入，明确放弃关闭后回入口，Enter重开仍是原保存正文', async () => {
  const user = userEvent.setup(), opener = await openFromUnfocusedEntry('BODY');
  await user.click(screen.getByRole('button', { name: '编辑当前版本' }));
  const input = screen.getByLabelText('修订正文') as HTMLTextAreaElement;
  await user.clear(input); await user.type(input, '尚未保存的编辑');
  await escape(user);
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '继续核对' }));
  await user.keyboard('{Enter}');
  expect(document.activeElement).toBe(input); expect(input.value).toBe('尚未保存的编辑');
  expect(screen.queryByText('还有未保存的编辑。')).toBeNull();
  await escape(user);
  await user.click(screen.getByRole('button', { name: '放弃未保存编辑并关闭' }));
  await expectReturnAndReopen(opener, user);
  expect(screen.queryByDisplayValue('尚未保存的编辑')).toBeNull();
});
