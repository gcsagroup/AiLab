import React from 'react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { WorkRevisions } from '../../apps/desktop/src/WorkRevisions';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('../../apps/desktop/src/Media', () => ({ MediaPreview: () => null }));

const work = { id: 'work-limits', name: '修订边界作品', kind: 'text' as const, artifact_id: 'original', media_type: 'text/plain' };
let view: any;
let posts: any[];

beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  posts = [];
  view = { work_id: work.id, work_revision: 1, current_revision_id: null, content_kind: 'text', duration_ms: null, original: { content: { text: '原生成正文' } }, items: [], has_more: false, next_before_revision: null };
  vi.stubGlobal('fetch', vi.fn(async (_input: string, init: RequestInit) => {
    if (init.method === 'POST') {
      const body = JSON.parse(String(init.body)); posts.push(body);
      const revision = { id: 'revision-saved', revision: view.work_revision + 1, parent_revision_id: body.parent_revision_id, content: body.content, changes: { diff: '边界样本差异' }, created_at: '2026-09-13T00:00:00Z' };
      view = { ...view, work_revision: revision.revision, current_revision_id: revision.id, items: [...view.items, revision] };
      return { ok: true, json: async () => ({ work: { revision: revision.revision, current_revision_id: revision.id }, revision }) };
    }
    return { ok: true, json: async () => structuredClone(view) };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function edit() {
  const mediaWork = view.content_kind === 'subtitles' ? { ...work, kind: 'video' as const, media_type: 'video/mp4' } : work;
  render(<WorkRevisions work={mediaWork} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: '编辑当前版本' }));
}
async function save() {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' })); });
}

it.each([
  ['普通汉字精确上限', 'text', '文'.repeat(16000)],
  ['含扩展汉字的正文精确上限', 'text', '𠮷' + '文'.repeat(15999)],
  ['扩展汉字配音文案', 'voice_script', '𠮷'.repeat(8001)],
])('%s 可完整保存，按与服务端相同的字符计数', async (_name, kind, text) => {
  view.content_kind = kind;
  await edit();
  const field = screen.getByRole('textbox', { name: kind === 'text' ? '修订正文' : '修订配音文案' });
  fireEvent.change(field, { target: { value: text } });
  await save();
  expect(posts).toHaveLength(1);
  expect(posts[0].content.text).toBe(text);
  expect(screen.queryByRole('textbox', { name: /修订正文|修订配音文案/ })).not.toBeInTheDocument();
});

it('真正超出 16000 字符时保留输入并拒绝提交', async () => {
  await edit();
  const text = '𠮷'.repeat(16001);
  const field = screen.getByRole('textbox', { name: '修订正文' });
  fireEvent.change(field, { target: { value: text } });
  await save();
  expect(posts).toHaveLength(0);
  expect(field).toHaveValue(text);
  expect(screen.getByText('修订文字不能为空，最多 16000 字符。')).toBeInTheDocument();
});

it('合法的 500 字符字幕可含扩展汉字，保存不截断', async () => {
  view.content_kind = 'subtitles'; view.duration_ms = 2000;
  view.original.content = { cues: [] };
  await edit();
  fireEvent.click(screen.getByRole('button', { name: '添加字幕' }));
  const text = '𠮷' + '文'.repeat(499);
  fireEvent.change(screen.getByRole('textbox', { name: '第1条字幕文字' }), { target: { value: text } });
  await save();
  expect(posts).toHaveLength(1);
  expect(posts[0].content.cues[0].text).toBe(text);
});

it('199 条字幕可新增到 200 条并保存总计 16000 字符', async () => {
  view.content_kind = 'subtitles'; view.duration_ms = 2000;
  view.original.content = { cues: [] };
  view.work_revision = 2; view.current_revision_id = 'revision-existing-199';
  view.items = [{ id: view.current_revision_id, revision: 2, parent_revision_id: null, content: { cues: Array.from({ length: 199 }, (_, i) => ({ start_ms: i * 10, end_ms: (i + 1) * 10, text: '字'.repeat(80) })) }, changes: { diff: '已有199条人工字幕' }, created_at: '2026-09-13T00:00:00Z' }];
  await edit();
  fireEvent.click(screen.getByRole('button', { name: '添加字幕' }));
  expect(screen.getByRole('button', { name: '添加字幕' })).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox', { name: '第200条字幕文字' }), { target: { value: '𠮷' + '字'.repeat(79) } });
  await save();
  expect(posts).toHaveLength(1);
  expect(posts[0].expected_revision).toBe(2);
  expect(posts[0].parent_revision_id).toBe('revision-existing-199');
  expect(posts[0].content.cues).toHaveLength(200);
  expect(posts[0].content.cues.reduce((total: number, cue: { text: string }) => total + [...cue.text].length, 0)).toBe(16000);
});

it('真正超出每条 500 字符时保留字幕并拒绝提交', async () => {
  view.content_kind = 'subtitles'; view.duration_ms = 2000;
  view.original.content = { cues: [] };
  await edit();
  fireEvent.click(screen.getByRole('button', { name: '添加字幕' }));
  const text = '文'.repeat(501), field = screen.getByRole('textbox', { name: '第1条字幕文字' });
  fireEvent.change(field, { target: { value: text } });
  await save();
  expect(posts).toHaveLength(0);
  expect(field).toHaveValue(text);
});
