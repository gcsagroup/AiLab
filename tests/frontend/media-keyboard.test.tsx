import React, { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Workbench from '../../apps/desktop/src/Workbench';
import ImportDialog from '../../apps/desktop/src/ImportDialog';
import { defaultMediaRuntime } from '../../apps/desktop/src/Media';
import type { ImportKind } from '../../apps/desktop/src/api';
import type { Attempt, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
type Variant = 'image' | 'video';
type Call = { method: string; path: string; body?: unknown };
const response = (value: unknown): Response => ({ ok: true, json: async () => structuredClone(value) }) as Response;
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(yes => { resolve = yes; }); return { promise, resolve }; }
const imported = vi.fn(), changed = vi.fn(), draftChanged = vi.fn();
let task: Task, calls: Call[], preflightReply: Promise<Response> | undefined;
let user: ReturnType<typeof userEvent.setup>;

function mediaTask(kind: Variant): Task {
  const operation = kind === 'image' ? 'train' : 'generate';
  return { id: `media-keyboard-${kind}`, project_id: 'media-keyboard-project', name: '媒体入口键盘回归', kind, operation, draft_revision: 4,
    draft: { kind, operation, model_id: null, dataset_id: null, input: kind === 'image' ? { prompt: '', negative_prompt: '' } : { material_id: null }, runtime: defaultMediaRuntime(kind, operation === 'train') } };
}
const entryNames = (kind: Variant) => ['导入模型', kind === 'image' ? '导入图片数据' : '导入图片素材'];
const writes = () => calls.filter(call => call.method !== 'GET');

beforeEach(() => {
  user = userEvent.setup(); calls = []; preflightReply = undefined;
  imported.mockClear(); changed.mockClear(); draftChanged.mockClear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = String(input).replace('/api/v1', ''); const method = options.method || 'GET';
    calls.push({ method, path, body: options.body ? JSON.parse(String(options.body)) : undefined });
    if (method === 'GET' && path === `/attempts/${task.latest_attempt?.id}`) return response(task.latest_attempt);
    if (method === 'GET' && path === `/attempts/${task.latest_attempt?.id}/events?after=0`) return response({ items: [] });
    if (method === 'POST' && path === `/tasks/${task.id}/preflight` && preflightReply) return preflightReply;
    throw new Error(`本专项未授权请求：${method} ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

function Example() {
  const [importKind, setImportKind] = useState<ImportKind | null>(null);
  return <><Workbench task={task} models={[]} datasets={[]} devices={[]}
    onBack={() => {}} registerLeave={() => {}} onTaskChanged={changed} onDraftChanged={draftChanged}
    onImport={kind => { imported(kind); setImportKind(kind); }} onUpdated={() => {}} />
    {importKind && <ImportDialog kind={importKind} projectId={task.project_id} onClose={() => setImportKind(null)} onImported={() => { throw new Error('本专项不允许实际导入'); }} />}</>;
}
async function mount() { await act(async () => { render(<Example />); }); }

it('三个媒体原生入口显式参与宿主 Tab 顺序，保留 button 类型且挂载不抢焦点', async () => {
  for (const kind of ['image', 'video'] as const) {
    task = mediaTask(kind); await mount();
    // 共享的模型入口在图片分支核一次；视频分支核另一源码位置的素材入口。
    for (const name of kind === 'image' ? entryNames(kind) : ['导入图片素材']) {
      const button = screen.getByRole('button', { name });
      expect.soft(button.getAttribute('tabindex'), name).toBe('0');
      expect(button.getAttribute('type')).toBe('button');
    }
    expect(document.activeElement).toBe(document.body); expect(writes()).toEqual([]);
    cleanup();
  }
});

it.each([
  ['image', '导入模型', 'model', '导入本机模型'],
  ['image', '导入图片数据', 'image-dataset', '导入本机数据集'],
  ['video', '导入图片素材', 'material', '导入本机图片素材'],
] as const)('%s 的 %s 只打开正确导入弹窗，关闭回原入口且不改稿', async (kind, name, importKind, title) => {
  task = mediaTask(kind); const before = structuredClone(task); await mount();
  const opener = screen.getByRole('button', { name }); await user.click(opener);
  const dialog = screen.getByRole('dialog', { name: title });
  expect(imported.mock.calls).toEqual([[importKind]]);
  if (importKind === 'image-dataset') expect(dialog.textContent).toContain('dataset.json');
  if (importKind === 'image-dataset') await user.click(screen.getByRole('button', { name: '关闭对话框' }));
  else fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }));
  expect(screen.queryByRole('dialog')).toBeNull(); expect(document.activeElement).toBe(opener);
  expect(task).toEqual(before); expect(draftChanged.mock.calls).toEqual([[before.draft]]);
  expect(changed).not.toHaveBeenCalled(); expect(writes()).toEqual([]);
});

it.each(['busy', 'running', 'recovery', 'checkpoint'] as const)('%s 时媒体三入口继承真实 Workbench fieldset 禁用，普通点击不触发导入', async state => {
  for (const kind of ['image', 'video'] as const) {
    task = mediaTask(kind); calls = []; imported.mockClear(); changed.mockClear(); draftChanged.mockClear();
    const pending = deferred<Response>(); preflightReply = state === 'busy' ? pending.promise : undefined;
    if (state === 'running' || state === 'recovery') task.latest_attempt = {
      id: `media-${kind}-${state}`, project_id: task.project_id, task_id: task.id, state: state === 'running' ? 'running' : 'failed',
      state_version: 2, recovery_required: state === 'recovery', snapshot: { kind, operation: task.operation }, artifacts: [], allowed_actions: [],
    } as Attempt;
    if (state === 'checkpoint') task.draft.checkpoint_id = 'saved-draft-checkpoint';
    const before = structuredClone(task); await mount();
    if (state === 'busy') {
      await user.click(screen.getByRole('button', { name: '检查配置' }));
      await waitFor(() => expect(writes()).toEqual([{ method: 'POST', path: `/tasks/${task.id}/preflight`, body: { draft_revision: 4 } }]));
    }
    const beforeClicks = structuredClone(writes());
    for (const name of entryNames(kind)) {
      const button = screen.getByRole('button', { name });
      expect(button.closest('fieldset')?.disabled).toBe(true); expect(button.matches(':disabled')).toBe(true);
      // 与既有 Workbench 键盘测试一致，使用遵守 fieldset 禁用语义的普通交互。
      await user.click(button);
    }
    expect(imported).not.toHaveBeenCalled(); expect(screen.queryByRole('dialog')).toBeNull();
    expect(task).toEqual(before); expect(draftChanged.mock.calls).toEqual([[before.draft]]);
    expect(changed).not.toHaveBeenCalled(); expect(writes()).toEqual(beforeClicks);
    if (state === 'busy') {
      await act(async () => pending.resolve(response({ preflight_id: 'media-keyboard-check', can_submit: false, blocking: [], warnings: [] })));
      for (const name of entryNames(kind)) expect(screen.getByRole('button', { name }).matches(':disabled')).toBe(false);
    }
    cleanup();
  }
});
