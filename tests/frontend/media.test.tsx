import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Workbench, { RunResult } from '../../apps/desktop/src/Workbench';
import { defaultMediaRuntime, MediaPreview } from '../../apps/desktop/src/Media';
import { mediaBlob } from '../../apps/desktop/src/api';
import type { Attempt, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const artifactId = 'artifact-' + 'a'.repeat(32);
const secondId = 'artifact-' + 'b'.repeat(32);
const models = [{ id: 'image-model', name: '固定图片基座', modality: 'image' as const, format: 'diffusers-safetensors' }, { id: 'video-model', name: '固定视频基座', modality: 'video' as const, format: 'diffusers-safetensors' }, { id: 'audio-model', name: '固定配音模型', modality: 'audio' as const, format: 'torch-restricted-official' }];
let task: Task;
let calls: { path: string; method: string; body: any; key?: string }[];

beforeEach(() => {
  task = { id: 'task-media', project_id: 'project-a', name: '媒体真实合同夹具', kind: 'video', operation: 'generate', draft_revision: 1, draft: { kind: 'video', operation: 'generate', model_id: 'video-model', dataset_id: null, input: { material_id: null }, runtime: defaultMediaRuntime('video', false) } };
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = String(input).replace('/api/v1', '');
    const method = options?.method || 'GET';
    const body = options?.body ? JSON.parse(String(options.body)) : {};
    calls.push({ path, method, body, key: (options?.headers as Record<string, string>)?.['Idempotency-Key'] });
    let data: unknown = { items: [] };
    if (path.endsWith('/draft')) { task = { ...task, draft: body.draft, draft_revision: task.draft_revision + 1 }; data = task; }
    if (path.endsWith('/preflight')) data = { preflight_id: 'checked-media', can_submit: true, blocking: [], warnings: [], effective_config: task.draft.runtime };
    return { ok: true, json: async () => data };
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function bench() {
  render(<Workbench task={task} models={models} datasets={[{ id: 'text-data', name: '不兼容语言数据', schema: 'sft' }, { id: 'image-data', name: '图片与描述', schema: 'image_caption_v1', sample_count: 2 }]} materials={[{ id: 'material-a', name: '本项目图片', kind: 'image', media_type: 'image/png', width: 512, height: 512, total_bytes: 123 }]} devices={[]} onBack={() => {}} registerLeave={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
}

it('视频草稿只提交图片身份和视频参数，不带文字生成或训练字段', async () => {
  bench();
  expect(screen.queryByLabelText('输入内容')).toBeNull();
  expect(screen.queryByLabelText('画面描述')).toBeNull();
  expect(screen.queryByLabelText('最大输出 token')).toBeNull();
  expect(screen.queryByRole('option', { name: '固定图片基座' })).toBeNull();
  fireEvent.change(screen.getByLabelText('输入图片'), { target: { value: 'material-a' } });
  fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  await screen.findByRole('button', { name: '开始运行' });
  expect(calls[0].body.draft.input).toEqual({ material_id: 'material-a' });
  expect(calls[0].body.draft.runtime).toEqual(defaultMediaRuntime('video', false));
  expect(calls.some(call => call.path.endsWith('/attempts'))).toBe(false);
  fireEvent.change(screen.getByLabelText('随机种子'), { target: { value: '20' } });
  expect(screen.queryByRole('button', { name: '开始运行' })).toBeNull();
});

it('图片训练筛掉语言数据，保留图片来源要求和独立 LoRA 配置', async () => {
  task = { ...task, kind: 'image', operation: 'train', draft: { ...task.draft, kind: 'image', operation: 'train', model_id: 'image-model', runtime: defaultMediaRuntime('image', true), input: { prompt: '', negative_prompt: '' } } };
  bench();
  expect(screen.queryByRole('option', { name: '不兼容语言数据' })).toBeNull();
  expect(screen.getByRole('option', { name: '图片与描述 · 2 张' })).toBeTruthy();
  expect(screen.queryByLabelText('画面描述')).toBeNull();
  expect(screen.queryByLabelText('温度')).toBeNull();
  fireEvent.change(screen.getByLabelText('图片与描述数据'), { target: { value: 'image-data' } });
  fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  await screen.findByRole('button', { name: '开始训练' });
  expect(calls[0].body.draft.runtime).toEqual(defaultMediaRuntime('image', true));
  expect(calls[0].body.draft.dataset_id).toBe('image-data');
});

it('配音表单显示中文和实际音频参数，不带 GPU 或图像输入', async () => {
  task = { ...task, kind: 'audio', draft: { ...task.draft, kind: 'audio', model_id: 'audio-model', runtime: defaultMediaRuntime('audio', false), input: { prompt: '' } } };
  bench();
  expect(screen.queryByLabelText('输入图片')).toBeNull();
  expect(screen.queryByLabelText('温度')).toBeNull();
  fireEvent.change(screen.getByLabelText('配音文本'), { target: { value: '蓝色陶瓷杯，适合每天使用。' } });
  fireEvent.change(screen.getByLabelText('语速'), { target: { value: '1.2' } });
  fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
  await screen.findByRole('button', { name: '开始运行' });
  expect(calls[0].body.draft.input).toEqual({ prompt: '蓝色陶瓷杯，适合每天使用。' });
  expect(calls[0].body.draft.runtime).toMatchObject({ engine: 'kokoro', device_id: 'cpu', speed: 1.2, voice: 'zf_xiaobei', sample_rate: 24000 });
  expect(screen.getByLabelText('运行前检查').textContent).toContain('固定配音模型 · 本机 CPU');
  expect(screen.getByLabelText('运行前检查').textContent).not.toContain('所选本机设备');
});

it('旧媒体草稿先明确应用默认配置，不能把文本参数悄悄替换', async () => {
  task.draft.runtime = { engine: 'mlx', device_id: 'apple-gpu', seed: 0, max_tokens: 128, temperature: 0, top_p: 1 };
  task.draft.input = { prompt: '旧媒体伪文本草稿' };
  bench();
  expect(task.draft.runtime.engine).toBe('mlx');
  fireEvent.click(screen.getByRole('button', { name: '应用本类别默认配置' }));
  fireEvent.click(screen.getByRole('button', { name: '保存草稿' }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body.draft.input).toEqual({ material_id: null });
  expect(calls[0].body.draft.runtime).toEqual(defaultMediaRuntime('video', false));
});

it('受保护媒体按原二进制读取，不能接受错误 MIME 或过大流', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'image/png' } }));
  const blob = await mediaBlob(artifactId);
  expect([...new Uint8Array(await blob.arrayBuffer())]).toEqual([1, 2, 3]);
  expect(blob.type).toBe('image/png');
  expect(vi.mocked(fetch).mock.calls[0]).toEqual([`/api/v1/artifacts/${artifactId}/content`, { headers: { 'X-AiLab-Request': '1' } }]);
  vi.mocked(fetch).mockResolvedValueOnce(new Response('不允许 HTML 预览', { headers: { 'Content-Type': 'text/html' } }));
  await expect(mediaBlob(artifactId)).rejects.toThrow('格式或大小');
  vi.mocked(fetch).mockResolvedValueOnce(new Response(new Uint8Array(0), { headers: { 'Content-Type': 'video/mp4', 'Content-Length': String(64 * 1024 * 1024 + 1) } }));
  await expect(mediaBlob(artifactId)).rejects.toThrow('格式或大小');
  await expect(mediaBlob('../private')).rejects.toThrow('编号');
});

it('媒体预览切换时撤销旧 URL，迟到响应不会替换新作品', async () => {
  const create = vi.fn().mockReturnValue('blob:checked-file');
  const revoke = vi.fn();
  const OriginalURL = URL;
  vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = create; static revokeObjectURL = revoke; });
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const view = render(<MediaPreview artifact={{ id: artifactId, media_type: 'image/png' }} autoLoad name="作品 A" />);
  vi.mocked(fetch).mockResolvedValueOnce(new Response(new Uint8Array([1]), { headers: { 'Content-Type': 'image/png' } }));
  view.rerender(<MediaPreview artifact={{ id: secondId, media_type: 'image/png' }} autoLoad name="作品 B" />);
  await screen.findByAltText('作品 B');
  await act(async () => finish(new Response(new Uint8Array([2]), { headers: { 'Content-Type': 'image/png' } })));
  expect(create).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(revoke).toHaveBeenCalledWith('blob:checked-file');
});

it('视频结果保存主视频，不能误保存前置条件图或评测 JSON', async () => {
  const attempt: Attempt = { id: 'attempt-media', task_id: task.id, project_id: task.project_id, state: 'succeeded', state_version: 5, snapshot: { kind: 'video', operation: 'generate' }, artifacts: [{ id: secondId, name: 'condition.png', media_type: 'image/png' }, { id: artifactId, name: 'video.mp4', media_type: 'video/mp4' }] };
  const normalFetch = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation(async (input, options) => {
    if (String(input).endsWith('/content')) return new Response(new Uint8Array([1, 2]), { headers: { 'Content-Type': 'video/mp4' } });
    if (String(input).endsWith('/attempts/attempt-media')) return { ok: true, json: async () => attempt } as Response;
    return normalFetch(input, options);
  });
  const OriginalURL = URL;
  vi.stubGlobal('URL', class extends OriginalURL { static createObjectURL = vi.fn().mockReturnValue('blob:video'); static revokeObjectURL = vi.fn(); });
  render(<RunResult initial={attempt} onChanged={() => {}} />);
  fireEvent.click(await screen.findByRole('button', { name: '保存作品' }));
  await screen.findByRole('button', { name: '已保存作品' });
  expect(calls.find(call => call.path === '/works')?.body).toEqual({ attempt_id: attempt.id, artifact_id: artifactId });
  expect(screen.queryByText('本次没有文本输出')).toBeNull();
});
