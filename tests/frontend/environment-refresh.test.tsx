import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { invoke } from '@tauri-apps/api/core';
import App from '../../apps/desktop/src/App';

const host = vi.hoisted(() => ({ listener: undefined as undefined | ((event: { payload: { state: string; message: string } }) => void) }));
vi.mock('@tauri-apps/api/event', () => ({ listen: vi.fn(async (name, listener) => { if (name !== 'host-status') return () => {}; host.listener = listener; return () => { host.listener = undefined; }; }) }));
vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn(async () => ({})) }));
vi.mock('../../apps/desktop/src/api', async importOriginal => ({ ...await importOriginal<object>(), canPickFile: () => true }));

const response = (value: unknown, ok = true) => ({ ok, json: async () => value }) as Response;
const caps = (supported: boolean) => ({ items: [{ kind: 'text', operation: 'generate', supported, reason: supported ? '' : '执行器尚未准备' }] });
const device = (name: string) => ({ items: [{ id: 'apple-gpu', name, status: 'ready' }] });
let requests: string[];
let refreshed: boolean;
let forced: () => Promise<Response>;
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  requests = []; refreshed = false;
  forced = async () => { refreshed = true; return response(caps(true)); };
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = String(url).replace('/api/v1', ''); requests.push(path);
    if (path === '/capabilities?refresh=true') return forced();
    if (path === '/capabilities') return response(caps(refreshed));
    if (path === '/devices') return response(device(refreshed ? '恢复后的设备' : '原设备'));
    return response({ items: [] });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
async function settings() {
  render(<App />);
  await screen.findByText('建立你的第一个项目');
  fireEvent.click(screen.getByRole('button', { name: '设备与环境' }));
  await screen.findByText('模型：尚未准备');
  const button = screen.getByRole('button', { name: '刷新环境' });
  await waitFor(() => expect(button.matches(':disabled')).toBe(false));
  return button;
}

it('显式刷新探测后再读设备，更新能力且不重新加载项目列表', async () => {
  const button = await settings();
  expect(requests.filter(path => path.includes('refresh=true'))).toEqual([]);
  const offset = requests.length;
  fireEvent.click(button);
  await screen.findByText('模型：环境已准备，可选择模型检查');
  expect(screen.getByText('恢复后的设备')).toBeTruthy();
  expect(requests.slice(offset)).toEqual(['/capabilities?refresh=true', '/devices']);
  expect((screen.getByLabelText('当前项目') as HTMLSelectElement).value).toBe('');
});

it('等待探测时连点和普通宿主刷新不会重复探测或提前覆盖结果', async () => {
  const button = await settings(); let finish!: (value: Response) => void;
  forced = () => new Promise(resolve => { finish = resolve; });
  fireEvent.click(button); fireEvent.click(button);
  expect(button.matches(':disabled')).toBe(true);
  const cachedReads = requests.filter(path => path === '/capabilities').length;
  await act(async () => { host.listener!({ payload: { state: 'running', message: '' } }); });
  expect(requests.filter(path => path === '/capabilities?refresh=true')).toHaveLength(1);
  expect(requests.filter(path => path === '/capabilities')).toHaveLength(cachedReads);
  await act(async () => { refreshed = true; finish(response(caps(true))); });
  await screen.findByText('恢复后的设备');
  expect(button.matches(':disabled')).toBe(false);
});

it('刷新失败在设置页显示原因，可重新探测，成功后清除错误', async () => {
  const button = await settings();
  forced = async () => response({ error: { code: 'CONTROL_UNAVAILABLE', message: '环境探测暂时无法完成' } }, false);
  const before = requests.filter(path => path === '/devices').length;
  fireEvent.click(button);
  await screen.findByText('环境探测暂时无法完成');
  expect(requests.filter(path => path === '/devices')).toHaveLength(before);
  expect(button.matches(':disabled')).toBe(false);
  forced = async () => { refreshed = true; return response(caps(true)); };
  fireEvent.click(button);
  await screen.findByText('恢复后的设备');
  expect(screen.queryByText('环境探测暂时无法完成')).toBeNull();
});

it('探测与运行环境切换互斥，不把两个环境的能力和设备混合显示', async () => {
  const button = await settings(); let finish!: (value: Response) => void;
  forced = () => new Promise(resolve => { finish = resolve; });
  const environmentButtons = ['使用内置运行环境', '高级：选择 Python 环境', '使用内置图片与视频环境', '使用内置配音环境', '配置图片与视频环境', '配置中文配音环境'].map(name => screen.getByRole('button', { name }));
  fireEvent.click(button);
  const before = vi.mocked(invoke).mock.calls.length;
  for (const item of environmentButtons) { expect(item.matches(':disabled')).toBe(true); fireEvent.click(item); }
  expect(vi.mocked(invoke).mock.calls).toHaveLength(before);
  await act(async () => { finish(response(caps(true))); });
  for (const item of environmentButtons) expect(item.matches(':disabled')).toBe(false);
  let finishSwitch!: (value: unknown) => void;
  vi.mocked(invoke).mockImplementationOnce(() => new Promise(resolve => { finishSwitch = resolve; }));
  fireEvent.click(environmentButtons[0]);
  expect(button.matches(':disabled')).toBe(true);
  const probes = requests.filter(path => path === '/capabilities?refresh=true').length;
  fireEvent.click(button);
  expect(requests.filter(path => path === '/capabilities?refresh=true')).toHaveLength(probes);
  await act(async () => { finishSwitch({}); });
  await waitFor(() => expect(button.matches(':disabled')).toBe(false));
});

it.each(['success', 'failure'])('断连后重新连接不接收旧探测的迟到%s', async outcome => {
  const button = await settings(); let finish!: (value: Response) => void;
  forced = () => new Promise(resolve => { finish = resolve; });
  fireEvent.click(button);
  await act(async () => { host.listener!({ payload: { state: 'stopped', message: '服务已停止' } }); });
  expect(button.matches(':disabled')).toBe(true);
  await act(async () => { host.listener!({ payload: { state: 'running', message: '' } }); });
  await waitFor(() => expect(button.matches(':disabled')).toBe(false));
  const deviceReads = requests.filter(path => path === '/devices').length;
  await act(async () => { finish(outcome === 'success' ? response(caps(true)) : response({ error: { code: 'CONTROL_UNAVAILABLE', message: '旧连接迟到错误' } }, false)); });
  expect(screen.getByText('模型：尚未准备')).toBeTruthy();
  expect(screen.queryByText('旧连接迟到错误')).toBeNull();
  expect(requests.filter(path => path === '/devices')).toHaveLength(deviceReads);
  expect(button.matches(':disabled')).toBe(false);
});
