import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { defaultMediaRuntime, MediaFields } from '../../apps/desktop/src/Media';
import type { Draft } from '../../apps/desktop/src/types';

afterEach(cleanup);
it('Anima 使用原有图片试用的描述、步数和引导强度', () => {
  vi.stubGlobal('ailabHF', {request:vi.fn()});
  try {
    const model = {id:'anima',name:'Anima',modality:'image' as const,format:'gguf',pipeline:'anima'};
    const draft: Draft = {kind:'image',operation:'generate',model_id:null,dataset_id:null,
      runtime:{...defaultMediaRuntime('image',false),engine:'ailab-gguf',device_id:'Vulkan1'},input:{prompt:'A sailboat'}};
    const props = {draft,models:[model],datasets:[],adapters:[],materials:[],onChange:vi.fn(),onImport:vi.fn()};
    const view = render(<MediaFields {...props} />);
    fireEvent.change(screen.getByLabelText('选择媒体模型'), {target:{value:model.id}});
    const next = props.onChange.mock.lastCall?.[0] as Draft;
    expect(next.runtime).toMatchObject({device_id:'Vulkan1',steps:1,cfg:3});
    view.rerender(<MediaFields {...props} draft={next} />);
    fireEvent.change(screen.getByLabelText('生成步数'), {target:{value:'3'}});
    expect(props.onChange.mock.lastCall?.[0].runtime.steps).toBe(3);
  } finally { vi.unstubAllGlobals(); }
});
it('Wan 使用原有画面描述和步数字段，切换时清除图生视频草稿的素材', () => {
  vi.stubGlobal('ailabHF', { request: vi.fn() });
  try {
    const model = {id:'wan', name:'Wan 2.1', modality:'video' as const, format:'gguf', pipeline:'wan21-t2v'};
    const draft: Draft = {kind:'video', operation:'generate', model_id:null, dataset_id:null,
      runtime:{...defaultMediaRuntime('video', false),device_id:'Vulkan1'}, input:{material_id:'old-image', prompt:'A sailboat'}};
    const props = {draft, models:[model], datasets:[], adapters:[], materials:[], onChange:vi.fn(), onImport:vi.fn()};
    const view = render(<MediaFields {...props} />);
    fireEvent.change(screen.getByLabelText('选择媒体模型'), {target:{value:model.id}});
    const next = props.onChange.mock.lastCall?.[0] as Draft;
    expect(next.runtime).toMatchObject({device_id:'Vulkan1', steps:1, frames:5, fps:8});
    expect(next.input.material_id).toBeUndefined();
    view.rerender(<MediaFields {...props} draft={next} />);
    expect((screen.getByLabelText('画面描述') as HTMLTextAreaElement).value).toBe('A sailboat');
    expect(screen.queryByLabelText('输入图片')).toBeNull();
  } finally { vi.unstubAllGlobals(); }
});
it.each(['audiocpp-asr', 'audiocpp-vad'])('%s 通过原有素材选择器读取 WAV', pipeline => {
  vi.stubGlobal('ailabHF', { request: vi.fn() });
  try {
    const model = { id: 'test-model', name: '测试模型', modality: 'audio' as const, format: 'gguf', pipeline };
    const draft: Draft = { kind: 'audio', operation: 'generate', model_id: model.id, dataset_id: null,
      input: {}, runtime: { ...defaultMediaRuntime('audio', false), engine: 'ailab-gguf' } };
    const onChange = vi.fn();
    const material = { id: 'test-wav', name: '朗读.wav', kind: 'audio' as const, media_type: 'audio/wav', total_bytes: 64044 };
    render(<MediaFields draft={draft} models={[model]} datasets={[]} adapters={[]} materials={[material]} onChange={onChange} onImport={vi.fn()} />);
    const picker = screen.getByLabelText('输入音频');
    fireEvent.change(picker, { target: { value: material.id } });
    expect(onChange.mock.lastCall?.[0].input.material_id).toBe(material.id);
    expect(screen.queryByLabelText('配音文本')).toBeNull();
  } finally {
    vi.unstubAllGlobals();
  }
});
it('MiniMax-H3 uses the same video timing on selection and when resetting an old draft', () => {
  vi.stubGlobal('ailabHF', { request: vi.fn() });
  try {
    const model = { id: 'model-h3', name: 'MiniMax-H3', modality: 'video' as const, format: 'gguf', pipeline: 'h3-video' };
    const draft: Draft = { kind: 'video', operation: 'generate', model_id: null, dataset_id: null,
      runtime: defaultMediaRuntime('video', false), input: { prompt: '小猫打哈欠', material_id: 'material-cat' } };
    const props = { draft, models: [model], datasets: [], adapters: [], materials: [], onChange: vi.fn(), onImport: vi.fn() };
    const view = render(<MediaFields {...props} />);
    fireEvent.change(screen.getByLabelText('选择媒体模型'), { target: { value: model.id } });
    const recipe = { steps: 4, frames: 22, fps: 24 };
    expect(props.onChange.mock.lastCall?.[0]).toMatchObject({ model_id: model.id, runtime: recipe, input: draft.input });
    view.rerender(<MediaFields {...props} draft={{ ...draft, model_id: model.id }} />);
    fireEvent.click(screen.getByRole('button', { name: '应用本类别默认配置' }));
    expect(props.onChange.mock.lastCall?.[0]).toMatchObject({ runtime: { ...recipe, engine: 'ailab-gguf' }, input: draft.input });
  } finally {
    vi.unstubAllGlobals();
  }
});
it.each(['image', 'video', 'audio'] as const)('%s 保存的引用未读回时保留原选择，不显示成另一个模型', kind => {
  const draft: Draft = { kind, operation: 'generate', model_id: 'model-original', adapter_id: kind === 'image' ? 'adapter-original' : null, dataset_id: null, input: kind === 'video' ? { material_id: 'material-original' } : { prompt: '原输入' }, runtime: defaultMediaRuntime(kind, false) };
  const changed = vi.fn();
  render(<MediaFields draft={draft} models={[{ id: 'model-other', name: '其它模型', modality: kind, format: 'safetensors' }]} datasets={[]} adapters={[]} materials={[]} onChange={changed} onImport={() => {}} />);
  expect((screen.getByLabelText('选择媒体模型') as HTMLSelectElement).value).toBe('model-original');
  expect((screen.getByRole('option', { name: '原模型待核实 · model-original' }) as HTMLOptionElement).selected).toBe(true);
  if (kind === 'image') expect((screen.getByLabelText('图片训练适配器') as HTMLSelectElement).value).toBe('adapter-original');
  if (kind === 'video') expect((screen.getByLabelText('输入图片') as HTMLSelectElement).value).toBe('material-original');
  expect(changed).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('选择媒体模型'), { target: { value: 'model-other' } });
  expect(changed).toHaveBeenCalledExactlyOnceWith({ ...draft, model_id: 'model-other', adapter_id: null });
});
