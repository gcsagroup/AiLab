import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkRevisions } from '../../apps/desktop/src/WorkRevisions';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('../../apps/desktop/src/Media', () => ({ MediaPreview: ({ artifact, name }: { artifact: { id: string }; name: string }) => <div aria-label={name}>{artifact.id}</div> }));

const work = { id: 'work-a', name: '验证作品', attempt_id: 'attempt-a', kind: 'text' as const, artifact_id: 'original-artifact', media_type: 'text/plain' };
let view: any;
let calls: { path: string; method: string; body: any; key?: string }[];
let receipts: Map<string, any>;
let dropSave: boolean;
let conflictSave: boolean;
let failRefresh: boolean;

function record(id: string, number: number, content: any, parent: string | null = null) {
  return { id, work_id: work.id, parent_revision_id: parent, revision: number, content_kind: view.content_kind, content, artifact_id: 'manual-' + id, editor: 'user_action', created_at: '2026-09-10T01:00:00Z', changes: { diff: '--- parent\n+++ revision\n-原文字\n+修订文字\n' }, source_artifact_sha256: 'a'.repeat(64) };
}
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = []; receipts = new Map(); dropSave = false; conflictSave = false; failRefresh = false;
  view = { work_id: work.id, work_revision: 1, current_revision_id: null, content_kind: 'text', duration_ms: null, original: { revision_id: null, artifact_id: 'original-artifact', sha256: 'a'.repeat(64), content: { text: '原文字' }, basis: 'generated_text' }, items: [], has_more: false, media_policy: '原媒体不变', private_context: 'private-value-not-for-preview' };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    const key = (init.headers as Record<string, string>)['Idempotency-Key']; calls.push({ path, method, body, key });
    if (method === 'GET') {
      if (failRefresh && receipts.size) { failRefresh = false; throw new Error('版本读取连接中断'); }
      return { ok: true, json: async () => structuredClone(view) };
    }
    if (method === 'POST' && path === '/works/work-a/revisions') {
      if (conflictSave) {
        const newer = record('revision-other', 2, { text: '另一处已经保存的正文' });
        view = { ...view, work_revision: 2, current_revision_id: newer.id, items: [newer] };
        return { ok: false, json: async () => ({ error: { code: 'REVISION_CONFLICT', message: '作品已更新，未覆盖当前修订。' } }) };
      }
      let saved = receipts.get(key);
      if (!saved) {
        const revision = record('revision-' + (receipts.size + 1), view.work_revision + 1, body.content, body.parent_revision_id);
        view = { ...view, work_revision: revision.revision, current_revision_id: revision.id, items: [...view.items, revision] };
        saved = { work: { revision: view.work_revision, current_revision_id: revision.id }, revision };
        receipts.set(key, saved);
      }
      if (dropSave) { dropSave = false; throw new Error('保存回执不可用'); }
      return { ok: true, json: async () => saved };
    }
    throw new Error('未声明接口：' + path);
  }));
});

describe('修订编辑焦点', () => {
  beforeEach(() => {
    // jsdom 不实现布局、showModal 首次聚焦或 Escape 的原生 cancel 默认动作。
    // 这里只补这些宿主行为；Tab/Enter 由 userEvent 驱动，可见性与真实模态行为另由浏览器核验。
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{ width: 20, height: 20 }] as unknown as DOMRectList);
    Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; this.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus(); } });
  });
  afterEach(() => vi.restoreAllMocks());

  async function tabTo(user: ReturnType<typeof userEvent.setup>, target: HTMLElement) {
    for (let step = 0; step < 24 && document.activeElement !== target; step++) await user.tab();
    expect(document.activeElement).toBe(target);
  }
  async function start(user: ReturnType<typeof userEvent.setup>) {
    await tabTo(user, await screen.findByRole('button', { name: '编辑当前版本' }));
    await user.keyboard('{Enter}');
  }
  async function escape(user: ReturnType<typeof userEvent.setup>) {
    await user.keyboard('{Escape}');
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
  }
  function subtitles(existing: boolean) {
    view.content_kind = 'subtitles'; view.duration_ms = 5000;
    view.original.content = { cues: [] }; view.original.basis = 'no_original_subtitle_artifact';
    if (existing) {
      const current = record('revision-existing', 2, { cues: [{ start_ms: 0, end_ms: 1000, text: '首条字幕' }, { start_ms: 1000, end_ms: 2000, text: '第二条字幕' }] });
      view = { ...view, work_revision: 2, current_revision_id: current.id, items: [current] };
    }
  }

  it.each(['正文', '已有字幕', '无字幕'] as const)('键盘开始编辑%s后直接聚焦首个可编辑控件', async kind => {
    if (kind !== '正文') subtitles(kind === '已有字幕');
    const user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await start(user);
    const first = kind === '正文' ? screen.getByLabelText('修订正文') : kind === '已有字幕' ? screen.getByLabelText('第1条字幕开始（秒）') : screen.getByRole('button', { name: '添加字幕' });
    expect(document.activeElement).toBe(first);
    expect(calls.map(call => call.method)).toEqual(['GET']);
  });

  it.each(['正文', '字幕'] as const)('%s Escape确认聚焦继续核对，继续后回到此前输入且继续输入不抢焦点', async kind => {
    if (kind === '字幕') subtitles(true);
    const closed = vi.fn(), user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={closed} onUpdated={() => {}} onExport={() => {}} />);
    await start(user);
    const input = screen.getByLabelText(kind === '正文' ? '修订正文' : '第2条字幕文字') as HTMLTextAreaElement;
    await tabTo(user, input); await user.keyboard('补充');
    const edited = input.value;
    await escape(user);
    const resume = screen.getByRole('button', { name: '继续核对' });
    expect(document.activeElement).toBe(resume); expect(closed).not.toHaveBeenCalled();
    await user.keyboard('{Enter}');
    expect(screen.queryByText('还有未保存的编辑。')).toBeNull();
    expect(document.activeElement).toBe(input); expect(input.value).toBe(edited);
    await user.keyboard('继续'); expect(document.activeElement).toBe(input);
    expect(calls.map(call => call.method)).toEqual(['GET']);
  });

  it('确认仍展开时键盘取消编辑回到编辑按钮，新开始不沿用旧确认', async () => {
    const user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await start(user); await escape(user);
    await tabTo(user, screen.getByRole('button', { name: '取消本次编辑' })); await user.keyboard('{Enter}');
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '编辑当前版本' }));
    expect(screen.queryByText('还有未保存的编辑。')).toBeNull();
    await user.keyboard('{Enter}');
    expect(document.activeElement).toBe(screen.getByLabelText('修订正文'));
    expect(screen.queryByRole('button', { name: '继续核对' })).toBeNull();
    expect(calls.map(call => call.method)).toEqual(['GET']);
  });

  it('保存成功等当前版本读取结束后再聚焦可用编辑按钮，不强聚忙碌控件', async () => {
    const originalFetch = globalThis.fetch;
    let finishRead!: () => void;
    const heldRead = new Promise<void>(resolve => { finishRead = resolve; });
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'GET' && receipts.size) await heldRead;
      return originalFetch(input, init);
    }));
    const user = userEvent.setup(), updated = vi.fn();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={updated} onExport={() => {}} />);
    await start(user);
    await tabTo(user, screen.getByRole('button', { name: '保存独立修订版本' })); await user.keyboard('{Enter}');
    const editButton = await screen.findByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement;
    expect(editButton.disabled).toBe(true); expect(document.activeElement).not.toBe(editButton);
    await act(async () => finishRead());
    await waitFor(() => expect(editButton.disabled).toBe(false));
    expect(document.activeElement).toBe(editButton); expect(updated).toHaveBeenCalledTimes(1);
    expect(calls.map(call => call.method)).toEqual(['GET', 'POST', 'GET']);
  });

  it('冲突后键盘放弃本次编辑并刷新，焦点回到当前版本编辑按钮', async () => {
    conflictSave = true; const user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await start(user);
    await tabTo(user, screen.getByRole('button', { name: '保存独立修订版本' })); await user.keyboard('{Enter}');
    await tabTo(user, await screen.findByRole('button', { name: '放弃本次编辑，读取当前版本' })); await user.keyboard('{Enter}');
    await screen.findByText('另一处已经保存的正文');
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '编辑当前版本' }));
    expect(screen.queryByLabelText('修订正文')).toBeNull();
    expect(calls.map(call => call.method)).toEqual(['GET', 'POST', 'GET']);
  });

  it('已保存但重读失败时聚焦重新读取，键盘重读成功后回到编辑按钮', async () => {
    failRefresh = true; const user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await start(user);
    await tabTo(user, screen.getByRole('button', { name: '保存独立修订版本' })); await user.keyboard('{Enter}');
    const reread = await screen.findByRole('button', { name: '重新读取作品版本' });
    expect(document.activeElement).toBe(reread);
    await user.keyboard('{Enter}'); await screen.findByText('已读取当前保存版本。');
    expect(document.activeElement).toBe(screen.getByRole('button', { name: '编辑当前版本' }));
    expect(calls.map(call => call.method)).toEqual(['GET', 'POST', 'GET', 'GET']);
  });

  it('保存回执未知后Escape并继续核对，聚焦可用重试按钮而非禁用输入', async () => {
    dropSave = true; const user = userEvent.setup();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    await start(user); await tabTo(user, screen.getByLabelText('修订正文'));
    await tabTo(user, screen.getByRole('button', { name: '保存独立修订版本' })); await user.keyboard('{Enter}');
    await screen.findByText('保存回执不可用');
    await escape(user); await tabTo(user, screen.getByRole('button', { name: '继续核对' })); await user.keyboard('{Enter}');
    const retry = screen.getByRole('button', { name: '重试保存回执' }) as HTMLButtonElement;
    expect(document.activeElement).toBe(retry); expect(retry.disabled).toBe(false);
    expect((screen.getByLabelText('修订正文') as HTMLTextAreaElement).disabled).toBe(true);
    expect(calls.map(call => call.method)).toEqual(['GET', 'POST']);
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function edit() {
  fireEvent.click(await screen.findByRole('button', { name: '编辑当前版本' }));
  return screen.getByLabelText('修订正文');
}

describe('独立人工作品修订', () => {
  it('从当前版本编辑、按CAS保存，显示父版本与差异，原版可单独导出', async () => {
    const updated = vi.fn(), exported = vi.fn();
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={updated} onExport={exported} />);
    expect(await screen.findByText('原文字')).toBeTruthy();
    expect(screen.queryByText('private-value-not-for-preview')).toBeNull();
    fireEvent.change(await edit(), { target: { value: '人工修订文字' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('独立修订版本已保存，原生成输出与配方保持原样。');
    await waitFor(() => expect(screen.getByText('当前版本')).toBeTruthy());
    expect(screen.getByLabelText('修订差异').textContent).toContain('-原文字');
    expect(calls.find(call => call.method === 'POST')?.body).toEqual({ expected_revision: 1, parent_revision_id: null, content_kind: 'text', content: { text: '人工修订文字' } });
    expect(updated).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '导出所选修订版 2' }));
    expect(exported).toHaveBeenLastCalledWith({ work_revision_id: 'revision-1', name: '验证作品 · 修订版 2' });
    fireEvent.change(screen.getByLabelText('查看作品版本'), { target: { value: 'original' } });
    expect(screen.getByText('原文字')).toBeTruthy();
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '导出所选原版' }));
    expect(exported).toHaveBeenLastCalledWith({ work_revision_id: null, name: '验证作品 · 原版' });
    expect(calls.every(call => call.path.startsWith('/works/work-a/revisions'))).toBe(true);
  });

  it('已保存但回执丢失时锁住原输入，重试复用原key且读取真正当前版本', async () => {
    dropSave = true;
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.change(await edit(), { target: { value: '回执丢失时的文字' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('保存回执不可用');
    expect((screen.getByLabelText('修订正文') as HTMLTextAreaElement).disabled).toBe(true);
    const later = record('revision-external', 3, { text: '另一个保存后的当前版本' }, 'revision-1');
    view = { ...view, work_revision: 3, current_revision_id: later.id, items: [...view.items, later] };
    fireEvent.click(screen.getByRole('button', { name: '重试保存回执' }));
    await screen.findByRole('option', { name: /修订版 3 · 当前/ });
    const posted = calls.filter(call => call.method === 'POST');
    expect(posted).toHaveLength(2); expect(posted[0].key).toBeTruthy(); expect(posted[0].key).toBe(posted[1].key); expect(posted[0].body).toEqual(posted[1].body);
    expect(receipts.size).toBe(1); expect(screen.getByText('历史查看')).toBeTruthy();
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(true);
    const versionSelect = screen.getByLabelText('查看作品版本') as HTMLSelectElement;
    expect(document.activeElement).toBe(versionSelect); expect(versionSelect.disabled).toBe(false);
    expect(calls.map(call => call.method)).toEqual(['GET', 'POST', 'POST', 'GET']);
  });

  it('当前父版本冲突保留本地输入，不自动重挂或再次保存', async () => {
    conflictSave = true;
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.change(await edit(), { target: { value: '应保留给用户核对的编辑' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('作品已更新，未覆盖当前修订。');
    expect((screen.getByLabelText('修订正文') as HTMLTextAreaElement).value).toBe('应保留给用户核对的编辑');
    expect((screen.getByRole('button', { name: '保存独立修订版本' }) as HTMLButtonElement).disabled).toBe(true);
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: '放弃本次编辑，读取当前版本' }));
    await screen.findByText('另一处已经保存的正文');
    expect(screen.queryByLabelText('修订正文')).toBeNull();
  });

  it('字幕按秒编辑并精确转换整数毫秒，越界先阻断，播放器仍使用原视频', async () => {
    view.content_kind = 'subtitles'; view.duration_ms = 2000; view.original.content = { cues: [] }; view.original.basis = 'no_original_subtitle_artifact';
    render(<WorkRevisions work={{ ...work, kind: 'video', media_type: 'video/mp4' }} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    expect(screen.getByLabelText('原始生成媒体').textContent).toBe('original-artifact');
    fireEvent.click(await screen.findByRole('button', { name: '编辑当前版本' }));
    fireEvent.click(screen.getByRole('button', { name: '添加字幕' }));
    fireEvent.change(screen.getByLabelText('第1条字幕文字'), { target: { value: '杯子的温润质感' } });
    fireEvent.change(screen.getByLabelText('第1条字幕结束（秒）'), { target: { value: '2.001' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('字幕须按时间排序、不重叠，并在原视频时长内。');
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(0);
    fireEvent.change(screen.getByLabelText('第1条字幕开始（秒）'), { target: { value: '0.125' } });
    fireEvent.change(screen.getByLabelText('第1条字幕结束（秒）'), { target: { value: '1.875' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('独立修订版本已保存，原生成输出与配方保持原样。');
    expect(calls.find(call => call.method === 'POST')?.body.content).toEqual({ cues: [{ start_ms: 125, end_ms: 1875, text: '杯子的温润质感' }] });
    expect(screen.getByLabelText('原始生成媒体').textContent).toBe('original-artifact');
  });

  it('配音文案修订只保存文字，不请求重新生成或替换原音频', async () => {
    view.content_kind = 'voice_script'; view.original.basis = 'generation_input';
    render(<WorkRevisions work={{ ...work, kind: 'audio', media_type: 'audio/wav' }} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '编辑当前版本' }));
    fireEvent.change(screen.getByLabelText('修订配音文案'), { target: { value: '修正后的配音文案，尚未重新合成。' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('独立修订版本已保存，原生成输出与配方保持原样。');
    expect(calls.find(call => call.method === 'POST')?.body.content_kind).toBe('voice_script');
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
    expect(screen.getByLabelText('原始生成媒体').textContent).toBe('original-artifact');
    expect(screen.getByText(/修改配音文案不会改变声音/)).toBeTruthy();
  });

  it('成功保存后读取当前版本失败时禁止继续编辑，重读不再次写入', async () => {
    failRefresh = true;
    render(<WorkRevisions work={work} onClose={() => {}} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.change(await edit(), { target: { value: '已保存待重新读取' } });
    fireEvent.click(screen.getByRole('button', { name: '保存独立修订版本' }));
    await screen.findByText('修订已保存，但当前版本读取失败。版本读取连接中断');
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '重新读取作品版本' }));
    await screen.findByText('已读取当前保存版本。');
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
    expect((screen.getByRole('button', { name: '编辑当前版本' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('未保存编辑关闭时保留输入，只有显式放弃才关闭', async () => {
    const closed = vi.fn();
    render(<WorkRevisions work={work} onClose={closed} onUpdated={() => {}} onExport={() => {}} />);
    fireEvent.change(await edit(), { target: { value: '未保存的编辑' } });
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
    expect(closed).not.toHaveBeenCalled(); expect(screen.getByText('还有未保存的编辑。')).toBeTruthy();
    expect((screen.getByLabelText('修订正文') as HTMLTextAreaElement).value).toBe('未保存的编辑');
    fireEvent.click(screen.getByRole('button', { name: '放弃未保存编辑并关闭' }));
    expect(closed).toHaveBeenCalledTimes(1); expect(calls.filter(call => call.method === 'POST')).toHaveLength(0);
  });
});
