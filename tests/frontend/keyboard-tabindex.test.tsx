import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import App from '../../apps/desktop/src/App';
import { Button, Dialog } from '../../apps/desktop/src/ui';
import { defaultProjectView } from '../../apps/desktop/src/ProjectContext';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async () => () => {}) }));

const project = { id: 'project-keyboard', name: '键盘项目', revision: 1 };
const task = { id: 'task-export', project_id: project.id, name: '已有导出任务', kind: 'export', operation: 'export', created_at: '2026-09-14T00:00:00Z', latest_attempt: { id: 'attempt-export', state: 'succeeded' } };
const work = { id: 'work-text', project_id: project.id, name: '已有正文', kind: 'text', text: '原保存内容' };
const response = (value: unknown) => ({ ok: true, json: async () => structuredClone(value) }) as Response;
const descriptors = {
  showModal: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'),
  close: Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close'),
};

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  // 仅补 jsdom 的模态和布局缺失，不模拟 Safari 的系统键盘策略。
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) {
    this.setAttribute('open', '');
    if (!this.contains(document.activeElement)) this.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
  } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.removeAttribute('open'); } });
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{ width: 20, height: 20 }] as unknown as DOMRectList);
  let context = { project_id: project.id, projects: { [project.id]: { ...defaultProjectView(), page: 'assets' } } };
  vi.stubGlobal('fetch', vi.fn(async (input: string, options: RequestInit = {}) => {
    const path = new URL(String(input), 'http://fixture').pathname.replace('/api/v1', '');
    const method = options.method || 'GET';
    if (path === '/ui-context') {
      if (method === 'PATCH') {
        const body = JSON.parse(String(options.body));
        context = { project_id: body.project_id, projects: { ...context.projects, [body.project_id]: body.context } };
      }
      return response(context);
    }
    if (method !== 'GET') throw new Error('键盘声明测试不允许业务写入：' + path);
    if (path === '/projects') return response({ items: [project] });
    if (path === `/projects/${project.id}`) return response(project);
    if (path === '/works') return response({ items: [work] });
    if (path === '/tasks') return response({ items: [task] });
    return response({ items: [], next_cursor: null });
  }));
});
afterEach(() => {
  cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks();
  for (const [name, descriptor] of Object.entries(descriptors)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name);
  }
});

function expectExplicitButtons(root: ParentNode) {
  const buttons = Array.from(root.querySelectorAll('button'));
  expect(buttons.length).toBeGreaterThan(0);
  for (const button of buttons) {
    // tabIndex 属性值默认也可能为 0；必须检查显式 HTML 声明才覆盖本次差异。
    expect(button.getAttribute('tabindex'), button.textContent || button.getAttribute('aria-label') || '').toBe('0');
  }
}

it('共用按钮显式加入原生 Tab 顺序，未在挂载时抢焦点', () => {
  render(<Button>核对导出</Button>);
  expect(screen.getByRole('button').getAttribute('tabindex')).toBe('0');
  expect(document.activeElement).toBe(document.body);
});

it('调用方的负值和正值 tabIndex 保留，不替调用方重排顺序', () => {
  render(<><Button tabIndex={-1}>仅程序聚焦</Button><Button tabIndex={3}>明确顺序</Button></>);
  expect(screen.getByRole('button', { name: '仅程序聚焦' }).getAttribute('tabindex')).toBe('-1');
  expect(screen.getByRole('button', { name: '明确顺序' }).getAttribute('tabindex')).toBe('3');
});

it('busy、disabled、fieldset 禁用及显式 autoFocus 的原有合同保持', () => {
  const clicked = vi.fn();
  render(<><Button busy onClick={clicked}>处理中</Button><Button disabled onClick={clicked}>不可用</Button><fieldset disabled><Button>字段集操作</Button></fieldset><Button autoFocus>指定焦点</Button></>);
  for (const name of ['处理中', '不可用', '字段集操作']) expect(screen.getByRole('button', { name }).matches(':disabled')).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '处理中' })); fireEvent.click(screen.getByRole('button', { name: '不可用' }));
  expect(clicked).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '指定焦点' }));
});

it('弹窗关闭按钮显式可达，中间的可取消 Tab 仍交由宿主推进', () => {
  render(<Dialog title="核对" onClose={() => {}}><Button>中间操作</Button><input aria-label="路径" /><Button>末尾操作</Button></Dialog>);
  expect(screen.getByRole('button', { name: '关闭对话框' }).getAttribute('tabindex')).toBe('0');
  const middle = screen.getByRole('button', { name: '中间操作' }); middle.focus();
  const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
  fireEvent(middle, event);
  expect(event.defaultPrevented).toBe(false);
  // jsdom 不执行原生 Tab；此断言防止引入手动全局推进，不代表原生已验收。
  expect(document.activeElement).toBe(middle);
});

it('真实 App 的五页导航、顶部入口和各页按钮均有显式 Tab 声明', async () => {
  const { container } = render(<App />); await screen.findByRole('button', { name: '文字修订' });
  expect(document.activeElement).toBe(document.body);
  expectExplicitButtons(container);
  for (const name of ['工作台', '模型库', '数据集市场', '模型实验室', '作品与素材']) {
    fireEvent.click(within(screen.getByRole('navigation', { name: '主导航' })).getByRole('button', { name }));
    expectExplicitButtons(container);
  }
});

it('真实任务队列的已有导出行和关闭按钮显式可达，新建项目仍自动聚焦名称', async () => {
  render(<App />); await screen.findByRole('button', { name: '文字修订' });
  fireEvent.click(screen.getByRole('button', { name: '任务队列' }));
  const dialog = screen.getByRole('dialog', { name: '任务队列与历史' });
  expect(within(dialog).getByRole('button', { name: /已有导出任务/ }).getAttribute('tabindex')).toBe('0');
  expectExplicitButtons(dialog);
  fireEvent.click(within(dialog).getByRole('button', { name: '关闭对话框' }));
  fireEvent.click(screen.getByRole('button', { name: '新建项目' }));
  expect(document.activeElement).toBe(screen.getByLabelText('项目名称'));
});
