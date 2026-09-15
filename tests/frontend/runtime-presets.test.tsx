import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { RuntimePresets } from '../../apps/desktop/src/RuntimePresets';
import type { Runtime } from '../../apps/desktop/src/types';

beforeEach(() => { HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); }; });
afterEach(cleanup);
const runtime: Runtime = { engine: 'mlx', device_id: 'apple-gpu', max_tokens: 512, temperature: 0.6, top_p: 0.9, seed: 2028, context_limit: 2048, overflow: 'reject', stop: [' 完成 '], stream: false, thinking: 'default' };
it('低内存 v2 先展示模型精度与 512 分块及首字取舍，取消保留草稿', () => {
  const apply = vi.fn(); render(<RuntimePresets runtime={runtime} onApply={apply} />);
  expect((screen.getByRole('option', { name: '低内存' }) as HTMLOptionElement).disabled).toBe(false);
  fireEvent.change(screen.getByLabelText('运行预设'), { target: { value: 'low_memory_v2' } }); fireEvent.click(screen.getByRole('button', { name: '预览预设差异' }));
  expect(screen.getByRole('dialog', { name: '应用低内存预设' })).toBeTruthy(); expect(screen.getByText('512 词元')).toBeTruthy(); expect(screen.getByText(/首字可能更慢/)).toBeTruthy(); expect(apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '取消' })); expect(apply).not.toHaveBeenCalled();
});
it.each([['default', 'auto', 2048], ['low_memory_v2', 'auto', 512], ['low_latency', 'auto', 4096]])('预设 %s 只改缓存精度与分块，保留生成字段和既有输入', (preset, precision, block) => {
  const apply = vi.fn(); render(<RuntimePresets runtime={runtime} onApply={apply} />); fireEvent.change(screen.getByLabelText('运行预设'), { target: { value: preset } }); fireEvent.click(screen.getByRole('button', { name: '预览预设差异' })); fireEvent.click(screen.getByRole('button', { name: '应用到草稿' }));
  expect(apply).toHaveBeenCalledOnce(); expect(apply).toHaveBeenCalledWith({ ...runtime, kv_precision: precision, prefill_step_size: block });
});
it('低延迟说明实测改善较小并提示内存取舍', () => {
  render(<RuntimePresets runtime={runtime} onApply={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('运行预设'), { target: { value: 'low_latency' } }); fireEvent.click(screen.getByRole('button', { name: '预览预设差异' }));
  expect(screen.getByText(/只有小幅延迟改善/)).toBeTruthy(); expect(screen.getByText(/内存可能更高/)).toBeTruthy();
});
it('运行或保存期间禁用预设应用，包括已打开的差异窗口', () => {
  const apply = vi.fn(); const view = render(<RuntimePresets runtime={runtime} onApply={apply} />);
  fireEvent.click(screen.getByRole('button', { name: '预览预设差异' }));
  view.rerender(<RuntimePresets runtime={runtime} disabled onApply={apply} />);
  expect((screen.getByRole('button', { name: '预览预设差异' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: '应用到草稿' }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '应用到草稿' })); expect(apply).not.toHaveBeenCalled();
});
