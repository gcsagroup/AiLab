import '@testing-library/jest-dom/vitest';
import { afterEach, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BenchmarkResult } from '../../apps/desktop/src/BenchmarkResult';
import type { EvaluationReport } from '../../apps/desktop/src/Evaluation';

afterEach(cleanup);

it('千题报告分页，筛选保留原始严格与宽松成绩及完整回答', () => {
  const metrics = { total: 1319, strict_correct: 700, flexible_correct: 800, extraction_failed: 50, truncated: 10, generation_seconds: 100, generated_tokens: 1000 };
  const samples = Array.from({ length: 1319 }, (_, i) => ({
    id: `gsm8k-test-${String(i).padStart(4, '0')}`, prompt: `题目${i}`, rule: { expected: '42' },
    baseline: { status: 'passed', output: `原始基线${i}`, strict_answer: '42', flexible_answer: '42' },
    candidate: { status: i === 1234 ? 'failed' : 'passed', output: `原始候选${i}`, strict_answer: i === 1234 ? null : '42', flexible_answer: '42' },
  }));
  const report = { quality_scope: '完整 GSM8K · 1,319 题', benchmark_metrics: { baseline: metrics, candidate: metrics }, samples, observations: { candidate: { 'gsm8k-test-1234': { finish_reason: 'length' } } } } as unknown as EvaluationReport;
  render(<BenchmarkResult report={report} />);
  expect(screen.getByText('题目0')).toBeInTheDocument();
  expect(screen.queryByText('题目10')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  expect(screen.getByText('题目10')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('筛选题目'), { target: { value: 'missing' } });
  expect(screen.getByText('原始候选1234')).toBeInTheDocument();
  expect(screen.getByText('符合筛选 1 题 · 第 1 / 1 页')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('筛选题目'), { target: { value: 'truncated' } });
  expect(screen.getByText('结束原因：length')).toBeInTheDocument();
  expect(screen.getAllByText('700 / 1319（53.07%）')).toHaveLength(2);
  expect(screen.getAllByText('800 / 1319（60.65%）')).toHaveLength(2);
});
