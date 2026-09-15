import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { RecipeDetails, WorkRecipeActions } from '../../apps/desktop/src/WorkRecipes';
import { LibraryReadContext } from '../../apps/desktop/src/LibraryReadContext';
import type { Kind, Task, Work, WorkRecipeView } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done; }); return { promise, resolve }; };
let calls: { method: string; path: string; body: any; key?: string }[];
let work: Work, view: WorkRecipeView, draft: Task, keys: Map<string, string>;
let handler: (call: typeof calls[number]) => Promise<Response>;
function fixtures(kind: Kind = 'text') {
  work = { id: 'work-a', project_id: 'project-a', name: '原作品', attempt_id: 'attempt-a', kind, artifact_id: 'artifact-original', current_revision_id: 'manual-revision', favorite: false };
  const input = kind === 'video' ? { material_id: 'material-original' } : { prompt: kind === 'audio' ? '原配音文案内容' : '原始提示词', ...(kind === 'image' ? { negative_prompt: '原负面提示词' } : {}) };
  const runtime = { engine: 'mlx', device_id: 'apple-gpu', seed: 19, max_tokens: 64 };
  view = { work, source_work_id: work.id, source_attempt_id: work.attempt_id, source_recipe_digest: 'a'.repeat(64), recipe: {
    project_id: work.project_id, task_id: 'task-original', kind, operation: 'generate', input, runtime, requested_config: runtime,
    effective_config: { engine: 'mlx', device_id: 'apple-gpu', seed: 19, max_tokens: 64, context_limit: 4096 }, model_id: 'model-original', model_version_id: 'version-original', model_manifest_digest: 'b'.repeat(64),
  } };
  draft = { id: 'task-reused', project_id: 'project-a', name: '原作品 · 新草稿', kind, operation: 'generate', draft_revision: 1,
    source_work_id: work.id, source_attempt_id: work.attempt_id, source_recipe_digest: view.source_recipe_digest,
    draft: { kind, operation: 'generate', model_id: 'model-original', dataset_id: null, execution_target_id: null, input, runtime },
  };
}
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  calls = []; keys = new Map(); fixtures();
  handler = async call => {
    if (call.method === 'GET') return response(view);
    if (call.path.endsWith('/reuse-task')) return response(draft);
    if (call.path.endsWith('/favorite')) return response({ ...work, favorite: call.body.favorite });
    throw new Error('未声明接口');
  };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit) => {
    const call = { method: options.method || 'GET', path: String(input).replace('/api/v1', ''), body: options.body ? JSON.parse(String(options.body)) : undefined, key: (options.headers as Record<string, string>)['Idempotency-Key'] };
    calls.push(call); return handler(call);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function controls(onCreated = vi.fn(), onUpdated = vi.fn()) { return <WorkRecipeActions work={work} projectId="project-a" reuseKeys={keys} onCreated={onCreated} onUpdated={onUpdated} />; }

describe('作品配方、复用与收藏', () => {
  it.each(['text', 'image', 'video', 'audio'] as Kind[])('%s 查看完整原输入与来源，关闭不创建草稿', async kind => {
    fixtures(kind); render(controls());
    fireEvent.click(screen.getByRole('button', { name: '查看配方' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByRole('heading', { name: '原生成输入' });
    const input = within(dialog).getByRole('region', { name: '原生成输入' });
    expect(input.textContent).toContain(kind === 'video' ? 'material-original' : kind === 'audio' ? '原配音文案内容' : '原始提示词');
    if (kind === 'image') expect(input.textContent).toContain('原负面提示词');
    expect(within(dialog).getByText('version-original')).toBeTruthy();
    expect(within(dialog).getByText('artifact-original')).toBeTruthy();
    expect(dialog.textContent).not.toContain('manual-revision');
    const actualOnly = within(dialog).getByRole('row', { name: '上下文上限 未记录 4096' }); expect(actualOnly).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '关闭对话框' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(calls).toEqual([{ method: 'GET', path: '/works/work-a/recipe?project_id=project-a', body: undefined, key: undefined }]);
  });

  it('直接载入一次草稿，不带人工修订或启动模型；在途双击只提交一次', async () => {
    const pending = deferred<Response>(), created = vi.fn(); handler = () => pending.promise;
    render(controls(created)); const button = screen.getByRole('button', { name: '用此配方新建任务' });
    fireEvent.click(button); fireEvent.click(button);
    expect(calls).toHaveLength(1); expect(calls[0].body).toEqual({ project_id: 'project-a' }); expect(calls[0].key).toBeTruthy();
    await act(async () => { pending.resolve(response(draft)); });
    expect(created).toHaveBeenCalledExactlyOnceWith(draft); expect(keys.size).toBe(0);
    expect(calls[0].path).toBe('/works/work-a/reuse-task');
  });

  it('回执丢失后重试和作品卡重挂均使用原key，成功后下一次明确载入用新key', async () => {
    let first = true; const created = vi.fn();
    handler = async () => { if (first) { first = false; throw new Error('连接中断'); } return response(draft); };
    const mounted = render(controls(created)); fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    await screen.findByText(/连接中断.*同一次新建/); mounted.unmount();
    render(controls(created)); fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
    expect(calls[1].key).toBe(calls[0].key); expect(calls[1].body).toEqual(calls[0].body);
    fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    await waitFor(() => expect(created).toHaveBeenCalledTimes(2)); expect(calls[2].key).not.toBe(calls[1].key);
  });

  it('收藏与取消只更新布尔属性，回读后显示正确状态，原修订指针不参与请求', async () => {
    const updated = vi.fn(); const original = structuredClone(work); render(controls(undefined, updated));
    fireEvent.click(screen.getByRole('button', { name: '收藏' }));
    await screen.findByText('已收藏'); expect(screen.getByRole('button', { name: '取消收藏' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: '取消收藏' }));
    await waitFor(() => expect(screen.queryByText('已收藏')).toBeNull());
    expect(calls.map(({ method, path, body }) => ({ method, path, body }))).toEqual([true, false].map(favorite => ({ method: 'PATCH', path: '/works/work-a/favorite', body: { project_id: 'project-a', favorite } })));
    expect(updated).toHaveBeenCalledTimes(2); expect(work).toEqual(original);
  });

  it('旧作品无favorite按未收藏显示，保存失败保持状态且不自动重试', async () => {
    delete work.favorite; handler = async () => { throw new Error('收藏保存失败'); }; render(controls());
    fireEvent.click(screen.getByRole('button', { name: '收藏' })); await screen.findByText('收藏保存失败');
    expect(screen.getByRole('button', { name: '收藏' }).getAttribute('aria-pressed')).toBe('false'); expect(calls).toHaveLength(1);
  });

  it('错项目配方不显示，错误回执不打开任务，也不丢掉重试key', async () => {
    const created = vi.fn(); view.work = { ...work, project_id: 'project-b' }; render(controls(created));
    fireEvent.click(screen.getByRole('button', { name: '查看配方' })); await screen.findByText('读取的配方来源与当前作品不符。');
    expect(screen.queryByRole('heading', { name: '原生成输入' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
    draft.project_id = 'project-b'; fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    await screen.findByText(/新草稿回执与当前作品不符/); expect(created).not.toHaveBeenCalled(); expect(keys.size).toBe(1);
  });

  it('关闭读取中的配方后丢弃晚响应，不能重开弹窗', async () => {
    const pending = deferred<Response>(); handler = () => pending.promise; render(controls());
    fireEvent.click(screen.getByRole('button', { name: '查看配方' })); fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
    await act(async () => { pending.resolve(response(view)); }); expect(screen.queryByRole('dialog')).toBeNull(); expect(calls).toHaveLength(1);
  });

  it.each(['project', 'library'])('%s 切换后迟到的新建回执不导航或更新当前项目', async mode => {
    const pending = deferred<Response>(), created = vi.fn(), updated = vi.fn(); let live = true;
    handler = () => pending.promise;
    const mounted = render(<LibraryReadContext.Provider value={() => () => live}>{controls(created, updated)}</LibraryReadContext.Provider>);
    fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    if (mode === 'project') mounted.rerender(<WorkRecipeActions work={{ ...work, id: 'work-b', project_id: 'project-b' }} projectId="project-b" reuseKeys={keys} onCreated={created} onUpdated={updated} />);
    else live = false;
    await act(async () => { pending.resolve(response(draft)); }); expect(created).not.toHaveBeenCalled(); expect(updated).not.toHaveBeenCalled(); expect(keys.size).toBe(1);
  });

  it('切库失败仍留原库，丢弃旧连接回执后解除忙碌，重试同一草稿', async () => {
    const pending = deferred<Response>(), created = vi.fn(); let libraryEpoch = 0;
    handler = () => pending.promise;
    render(<LibraryReadContext.Provider value={() => { const captured = libraryEpoch; return () => captured === libraryEpoch; }}>{controls(created)}</LibraryReadContext.Provider>);
    fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    libraryEpoch++;
    await act(async () => { pending.resolve(response(draft)); });
    expect(created).not.toHaveBeenCalled();
    expect((screen.getByRole('button', { name: '用此配方新建任务' }) as HTMLButtonElement).disabled).toBe(false);
    handler = async () => response(draft);
    fireEvent.click(screen.getByRole('button', { name: '用此配方新建任务' }));
    await waitFor(() => expect(created).toHaveBeenCalledExactlyOnceWith(draft));
    expect(calls[1].key).toBe(calls[0].key);
  });

  it('适配器、素材版本及远端身份可追溯，原值缺失不会显示成本机', () => {
    view.recipe = { ...view.recipe, execution_target_id: 'target-old', execution_target: { origin: 'https://executor.example', executor_id: 'executor-original' }, adapter_id: 'adapter-old', adapter_version_id: 'adapter-version', adapter_manifest_digest: 'adapter-digest', adapter_training_recipe_digest: 'training-recipe', input: { material_id: 'material-original' }, material_version_id: 'material-version', input_image_manifest_digest: 'material-digest' };
    render(<RecipeDetails view={view} />);
    for (const value of ['adapter-version', 'adapter-digest', 'training-recipe', 'material-version', 'material-digest', 'https://executor.example', 'executor-original']) expect(screen.getByText(value)).toBeTruthy();
    expect(screen.queryByText('本机')).toBeNull();
  });
});
