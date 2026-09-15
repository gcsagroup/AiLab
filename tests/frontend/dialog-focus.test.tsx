import React, { useState } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Dialog } from '../../apps/desktop/src/ui';

beforeEach(() => {
  // jsdom 没有布局和原生 modal 行为；实际键盘与样式由 CUA 验收覆盖。
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function () {
    const hidden = this.closest('[hidden], [style*="display: none"]');
    return (hidden ? [] : [{ width: 20, height: 20 }]) as unknown as DOMRectList;
  });
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
    this.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function Example({ busy = false }: { busy?: boolean }) {
  const [open, setOpen] = useState(false);
  return <>
    <button onClick={() => setOpen(true)}>打开设备设置</button>
    <button>页面后续操作</button>
    {open && <Dialog title="设备设置" preventClose={busy} onClose={() => setOpen(false)}>
      <input aria-label="设备路径" disabled={busy} />
      <button disabled={busy}>刷新设备</button>
      <button disabled>不可用操作</button>
      <button hidden>隐藏操作</button>
      <button style={{ display: 'none' }}>不展示操作</button>
      <button style={{ visibility: 'hidden' }}>不可见操作</button>
      <div inert><button>暂停区域操作</button></div>
    </Dialog>}
  </>;
}

it('Tab 与 Shift+Tab 在可见可用控件首尾循环，跳过禁用和隐藏控件', async () => {
  const user = userEvent.setup(); render(<Example />);
  await user.click(screen.getByRole('button', { name: '打开设备设置' }));
  const first = screen.getByRole('button', { name: '关闭对话框' });
  const last = screen.getByRole('button', { name: '刷新设备' });
  expect(document.activeElement).toBe(first);
  await user.tab({ shift: true }); expect(document.activeElement).toBe(last);
  await user.tab(); expect(document.activeElement).toBe(first);
  await user.tab(); expect(document.activeElement).toBe(screen.getByLabelText('设备路径'));
  await user.tab(); expect(document.activeElement).toBe(last);
  await user.tab(); expect(document.activeElement).toBe(first);
});

it('原生取消事件关闭弹窗后，焦点返回原触发按钮', async () => {
  const user = userEvent.setup(); render(<Example />);
  const opener = screen.getByRole('button', { name: '打开设备设置' });
  await user.click(opener);
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(opener);
});

it('关闭按钮与取消事件使用同样的焦点恢复路径', async () => {
  const user = userEvent.setup(); render(<Example />);
  const opener = screen.getByRole('button', { name: '打开设备设置' });
  await user.click(opener);
  await user.click(screen.getByRole('button', { name: '关闭对话框' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(opener);
});

it('没有可操作控件时 Tab 双向留在弹窗，忙碌期间不允许取消', async () => {
  const user = userEvent.setup(); render(<Example busy />);
  await user.click(screen.getByRole('button', { name: '打开设备设置' }));
  const dialog = screen.getByRole('dialog'); dialog.focus();
  await user.tab(); expect(document.activeElement).toBe(dialog);
  await user.tab({ shift: true }); expect(document.activeElement).toBe(dialog);
  fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true })); expect(screen.getByRole('dialog')).toBe(dialog);
});

it('焦点位于弹窗本身时，可通过 Tab 和 Shift+Tab 进入首末控件', async () => {
  const user = userEvent.setup(); render(<Example />);
  await user.click(screen.getByRole('button', { name: '打开设备设置' }));
  const dialog = screen.getByRole('dialog'); dialog.focus();
  await user.tab(); expect(document.activeElement).toBe(screen.getByRole('button', { name: '关闭对话框' }));
  dialog.focus(); await user.tab({ shift: true });
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '刷新设备' }));
});
