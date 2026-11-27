import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { TrialTextOutput } from '../../apps/desktop/src/TrialTextOutput';

afterEach(cleanup);

it('streams reasoning across split tags, collapses at the closing tag and keeps the answer visible when toggled', () => {
  const view = render(<TrialTextOutput text="<thi" active />);
  expect(screen.getByLabelText('模型输出').textContent).toBe('');
  view.rerender(<TrialTextOutput text={'<think>思考中</thi'} active />);
  expect(screen.getByRole('button', { name: '正在思考' }).getAttribute('aria-expanded')).toBe('true');
  expect(screen.getByText('思考中').hidden).toBe(false);
  view.rerender(<TrialTextOutput text={'<think>思考中</think>'} active />);
  expect(screen.getByText('思考中').hidden).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: '查看思考过程' }));
  view.rerender(<TrialTextOutput text={'<think>思考中</think>\n\n正式回答'} active={false} />);
  expect(screen.getByText('思考中').hidden).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: '收起思考过程' }));
  expect(screen.getByText('思考中').hidden).toBe(true);
  expect(screen.getByText('正式回答')).toBeTruthy();
});

it('starts a prefilled thought immediately and handles an interrupted generation without exposing it as the answer', () => {
  const view = render(<TrialTextOutput text="部分思考" prefilled active />);
  expect(screen.getByRole('button', { name: '正在思考' })).toBeTruthy();
  view.rerender(<TrialTextOutput text="部分思考" prefilled active={false} />);
  expect(screen.getByText('部分思考').hidden).toBe(true);
  expect(screen.getByText('本次生成在输出最终回答前结束。')).toBeTruthy();
  view.rerender(<TrialTextOutput text="部分思考</think>完成" prefilled active={false} />);
  expect(screen.getByText('完成')).toBeTruthy();
});

it('renders server reasoning separately and preserves literal markers in its final answer', () => {
  const view = render(<TrialTextOutput reasoning="服务端思考" text="" active />);
  expect(screen.getByText('服务端思考').hidden).toBe(false);
  view.rerender(<TrialTextOutput reasoning="服务端思考" text="<think> 是示例" active />);
  expect(screen.getByText('服务端思考').hidden).toBe(true);
  expect(screen.getByText('<think> 是示例')).toBeTruthy();
});

it('reads completed runs with Gemma thought channels, empty thoughts and plain answers', () => {
  const view = render(<TrialTextOutput text={'<|channel>thought\n想法<channel|>\n结果'} active={false} />);
  expect(screen.getByText('想法').hidden).toBe(true);
  expect(screen.getByText('结果')).toBeTruthy();
  view.rerender(<TrialTextOutput text={'<think>\n\n</think>\n\n直接回答'} active={false} />);
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText('直接回答')).toBeTruthy();
  view.rerender(<TrialTextOutput text="正文中的 <think> 是示例" active={false} />);
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.getByText('正文中的 <think> 是示例')).toBeTruthy();
});
