import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DatasetSplitDialog from '../../apps/desktop/src/DatasetSplitDialog';
import { applied, model, source, splitPlan } from './fixtures/dataset-split';

// 控制旧预览 effect 的启动时刻，覆盖提交动作已先发生的调度顺序。
const schedule = vi.hoisted(() => ({ hold: false, delayed: null as (() => void | (() => void)) | null }));
vi.mock('react', async importOriginal => {
  const original = await importOriginal<typeof import('react')>();
  return { ...original, useEffect: (effect: React.EffectCallback, dependencies?: React.DependencyList) => {
    original.useEffect(() => {
      if (schedule.hold && dependencies?.length === 4 && dependencies[1] === 'split-plan' && dependencies[2] === 'ready') {
        schedule.hold = false;
        let dispose: void | (() => void);
        schedule.delayed = () => { dispose = effect(); };
        return () => { dispose?.(); schedule.delayed = null; };
      }
      return effect();
    }, dependencies);
  } };
});
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
let calls: { method: string; path: string; key: string | undefined }[];
let delayedRead: Promise<Response> | null;
beforeEach(() => {
  schedule.hold = false; schedule.delayed = null; calls = []; delayedRead = null;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const path = String(url).replace('/api/v1', '');
    calls.push({ method: init.method || 'GET', path, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    if (path.startsWith('/datasets/split-plans?')) return response({ items: [], next_cursor: null });
    if (path === '/datasets/split-plans') return response(splitPlan());
    if (path === '/datasets/split-plans/split-plan') return delayedRead || response(splitPlan());
    if (path === '/datasets/splits') return response({ ...applied, split: { ...applied.split, source_version_id: 'unexpected-version' } });
    throw new Error('未授权夹具请求：' + path);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function previewAndReject() {
  const onChanged = vi.fn(), onUseTraining = vi.fn();
  render(<DatasetSplitDialog dataset={source} models={[model]} projectId={source.project_id} onClose={() => {}} onChanged={onChanged} onUseTraining={onUseTraining} />);
  fireEvent.change(screen.getByLabelText('划分检查模型'), { target: { value: model.id } });
  fireEvent.click(screen.getByRole('button', { name: '检查并预览划分' }));
  const apply = await screen.findByRole('button', { name: '应用划分，生成新版本' });
  await waitFor(() => expect((apply as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(apply);
  await screen.findByText('划分结果与本次预览参数不一致，请重新读取。');
  return { onChanged, onUseTraining };
}

async function preserved(callbacks: Awaited<ReturnType<typeof previewAndReject>>) {
  expect(screen.getByRole('alert').textContent).toBe('划分结果与本次预览参数不一致，请重新读取。');
  expect(screen.queryByRole('button', { name: '使用训练子集' })).toBeNull();
  expect(callbacks.onChanged).not.toHaveBeenCalled(); expect(callbacks.onUseTraining).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '重试上次操作' }));
  await waitFor(() => expect(calls.filter(call => call.path === '/datasets/splits')).toHaveLength(2));
  const writes = calls.filter(call => call.path === '/datasets/splits');
  expect(writes[0].key).toBeTruthy(); expect(writes[1].key).toBe(writes[0].key);
}

it('提交拒绝后才启动的旧预览读取不能领取新代次或清除错误', async () => {
  schedule.hold = true;
  const callbacks = await previewAndReject();
  expect(schedule.delayed).toBeTypeOf('function');
  await act(async () => { schedule.delayed!(); });
  expect(screen.getByRole('alert').textContent).toBe('划分结果与本次预览参数不一致，请重新读取。');
  expect(calls.filter(call => call.path === '/datasets/split-plans/split-plan')).toHaveLength(0);
  await preserved(callbacks);
});

it('已启动的旧预览读取晚于提交拒绝返回时仍不能清除错误', async () => {
  let release!: (value: Response) => void;
  delayedRead = new Promise(resolve => { release = resolve; });
  const callbacks = await previewAndReject();
  expect(calls.filter(call => call.path === '/datasets/split-plans/split-plan')).toHaveLength(1);
  await act(async () => { release(response(splitPlan())); });
  await preserved(callbacks);
});
