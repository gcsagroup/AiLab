import React from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { defaultMediaRuntime, MediaFields } from '../../apps/desktop/src/Media';
import type { Draft } from '../../apps/desktop/src/types';

afterEach(cleanup);
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
