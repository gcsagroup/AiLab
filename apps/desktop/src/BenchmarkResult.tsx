import { useContext, useEffect, useState } from 'react';
import { LibraryReadContext } from './LibraryReadContext';
import { api, errorMessage } from './api';
import type { EvaluationReport } from './Evaluation';
import { Button, ErrorNotice } from './ui';

/** 千题报告只展示当前页，筛选不改变原始成绩。 */
export function BenchmarkResult({ report: initial, attemptId }: { report: EvaluationReport; attemptId?: string }) {
  const capture = useContext(LibraryReadContext);
  const [remote, setRemote] = useState(initial); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const report = attemptId ? remote : initial;
  const [filter, setFilter] = useState('all'); const [page, setPage] = useState(0);
  useEffect(() => {
    if (!attemptId) return;
    let live = true; const isCurrent = capture(); setBusy(true); setError('');
    void api<{ report: EvaluationReport; report_error?: { message: string } }>('GET', `/evaluations/${attemptId}?sample_offset=${page * 10}&sample_limit=10&sample_filter=${filter}`).then(value => {
      if (!live || !isCurrent()) return;
      if (!value.report) throw new Error(value.report_error?.message || '报告尚未就绪');
      setRemote(value.report);
    }).catch(e => { if (live && isCurrent()) setError(errorMessage(e)); }).finally(() => { if (live && isCurrent()) setBusy(false); });
    return () => { live = false; };
  }, [attemptId, page, filter, capture]);
  const metrics = report.benchmark_metrics!;
  const selected = attemptId ? report.samples : report.samples.filter(sample => (filter === 'truncated' && report.observations?.candidate?.[sample.id]?.finish_reason === 'length') || filter === 'all' || (filter === 'wrong' && sample.candidate.status !== 'passed') || (filter === 'different' && sample.baseline.status !== sample.candidate.status) || (filter === 'missing' && (sample.candidate as unknown as { strict_answer: string | null }).strict_answer === null));
  const matched = attemptId ? report.sample_page?.matched || 0 : selected.length;
  const pages = Math.max(1, Math.ceil(matched / 10)); const current = attemptId ? Math.floor((report.sample_page?.offset || 0) / 10) : Math.min(page, pages - 1);
  return <section className="result-card capability-reviews" aria-label="GSM8K 对照报告">
    <h3>GSM8K 对照报告</h3><p>{report.quality_scope}</p>
    <div className="table-scroll"><table><thead><tr><th>对象</th><th>严格正确</th><th>宽松正确</th><th>无法严格提取</th><th>输出截断</th></tr></thead><tbody>{(['baseline', 'candidate'] as const).map(variant => {
      const m = metrics[variant]; return <tr key={variant}><th>{variant === 'baseline' ? '基线' : '候选'}</th><td>{m.strict_correct} / {m.total}（{(100 * m.strict_correct / m.total).toFixed(2)}%）</td><td>{m.flexible_correct} / {m.total}（{(100 * m.flexible_correct / m.total).toFixed(2)}%）</td><td>{m.extraction_failed}</td><td>{m.truncated}</td></tr>;
    })}</tbody></table></div>
    <p>严格正确率变化：{(100 * (metrics.candidate.strict_correct / metrics.candidate.total - metrics.baseline.strict_correct / metrics.baseline.total)).toFixed(2)} 个百分点。</p>
    <p className="muted">宽松提取可能误取推理过程中的数字，单独展示，不替代严格成绩。截断及无法提取的回答仍计入总题数。</p>
    <label>筛选题目<select disabled={busy} value={filter} onChange={e => { setFilter(e.target.value); setPage(0); }}><option value="all">全部题目</option><option value="wrong">候选严格未通过</option><option value="different">两侧判定不同</option><option value="missing">候选无法严格提取</option><option value="truncated">候选输出截断</option></select></label>
    <ErrorNotice message={error} /><p>符合筛选 {matched} 题 · 第 {current + 1} / {pages} 页</p>
    {(attemptId ? selected : selected.slice(current * 10, current * 10 + 10)).map(sample => <article key={sample.id}><h4>{sample.id}</h4><p>{sample.prompt}</p><p>标准答案：{(sample.rule as { expected: string }).expected}</p><div className="two-fields">{(['baseline', 'candidate'] as const).map(variant => {
      const result = sample[variant] as typeof sample.baseline & { strict_answer?: string | null; flexible_answer?: string | null };
      return <section key={variant}><strong>{variant === 'baseline' ? '基线' : '候选'} · {result.status === 'passed' ? '严格通过' : '严格未通过'}</strong><p>严格提取：{result.strict_answer ?? '无'} · 宽松提取：{result.flexible_answer ?? '无'}</p><p>结束原因：{report.observations?.[variant]?.[sample.id]?.finish_reason || '未记录'}</p><pre>{result.output}</pre></section>;
    })}</div></article>)}
    <div className="pagination-actions"><Button disabled={busy || current === 0} onClick={() => setPage(current - 1)}>上一页</Button><Button disabled={busy || current + 1 >= pages} onClick={() => setPage(current + 1)}>下一页</Button></div>
  </section>;
}
