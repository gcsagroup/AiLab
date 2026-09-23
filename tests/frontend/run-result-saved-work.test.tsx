import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RunResult } from '../../apps/desktop/src/Workbench';
import type { Attempt } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('../../apps/desktop/src/MediaPreview', () => ({ MediaPreview: () => null }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const response = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
const base = { id: 'saved-attempt', project_id: 'project-a', task_id: 'task-a', state: 'succeeded', state_version: 4,
  compute_outcome: 'succeeded', collection_state: 'succeeded', allowed_actions: [] };

it.each([
  ['text', 'result.txt', 'text/plain'], ['image', 'image.png', 'image/png'],
  ['video', 'video.mp4', 'video/mp4'], ['audio', 'speech.wav', 'audio/wav'],
])('%s 保存后重新进入，按当前产物的持久登记恢复已保存，不重新POST', async (kind, name, mediaType) => {
  const detail = { ...base, snapshot: { kind, operation: 'generate' }, artifacts: [{ id: 'primary-artifact', name, media_type: mediaType }], saved_work_artifact_ids: ['primary-artifact'] } as Attempt;
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    calls.push(`${options.method || 'GET'} ${url}`);
    return response(String(url).includes('/events?') ? { items: [] } : detail);
  }));
  const app = render(<RunResult initial={base as Attempt} onChanged={vi.fn()} />);
  expect((await screen.findByRole('button', { name: '已保存作品' })).matches(':disabled')).toBe(true);
  app.unmount(); render(<RunResult initial={base as Attempt} onChanged={vi.fn()} />);
  expect((await screen.findByRole('button', { name: '已保存作品' })).matches(':disabled')).toBe(true);
  expect(calls.every(call => call.startsWith('GET '))).toBe(true);
});

it('其他产物的作品登记不能把当前正文误标为已保存；保存完成不被旧读取覆盖', async () => {
  const detail = { ...base, snapshot: { kind: 'text', operation: 'generate' }, artifacts: [{ id: 'body-artifact', name: 'result.txt', media_type: 'text/plain' }], saved_work_artifact_ids: ['other-artifact'] } as Attempt;
  let posts = 0;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit = {}) => {
    if (options.method === 'POST') { posts += 1; expect(JSON.parse(String(options.body))).toEqual({ attempt_id: base.id, artifact_id: 'body-artifact' }); return response({ id: 'work-a' }); }
    return response(String(url).includes('/events?') ? { items: [] } : detail);
  }));
  render(<RunResult initial={base as Attempt} onChanged={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: '保存作品' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '已保存作品' }).matches(':disabled')).toBe(true));
  expect(posts).toBe(1);
});

it('旧运行的已保存读取在切换后迟到，不污染新的运行', async () => {
  let resolve!: (value: Response) => void;
  const held = new Promise<Response>(yes => { resolve = yes; });
  const detail = { ...base, id: 'new-attempt', snapshot: { kind: 'text', operation: 'generate' }, artifacts: [{ id: 'new-body', name: 'result.txt', media_type: 'text/plain' }], saved_work_artifact_ids: [] } as Attempt;
  vi.stubGlobal('fetch', vi.fn(async (url: string) => String(url).endsWith('/saved-attempt') ? held : response(String(url).includes('/events?') ? { items: [] } : detail)));
  const app = render(<RunResult initial={base as Attempt} onChanged={vi.fn()} />);
  app.rerender(<RunResult initial={{ ...base, id: 'new-attempt' } as Attempt} onChanged={vi.fn()} />);
  await screen.findByRole('button', { name: '保存作品' });
  await act(async () => resolve(response({ ...detail, id: base.id, saved_work_artifact_ids: ['new-body'] })));
  expect(screen.queryByRole('button', { name: '已保存作品' })).toBeNull();
  expect(screen.getByRole('button', { name: '保存作品' }).matches(':disabled')).toBe(false);
});
