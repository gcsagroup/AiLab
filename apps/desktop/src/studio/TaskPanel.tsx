import { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import { errorMessage } from '../api';
import { Error, request, Empty } from './common';
import { JobControls } from './JobActions';
import { MediaPreview } from './Library';
import ChatAnswer from './ChatAnswer';
import { terminal, stateLabel, type Job, type Event } from './types';

export function LossChart({ events }: { events: Event[] }) {
  const points = events.filter(e => typeof e.step === 'number' && (Number.isFinite(e.loss) || Number.isFinite(e.eval_loss)));
  if (!points.length) return <Empty>等待首个训练指标</Empty>;
  const maximum = Math.max(0.01, ...points.flatMap(e => [e.loss || 0, e.eval_loss || 0]));
  const steps = Math.max(1, ...points.map(e => e.step || 0));
  const line = (key: 'loss' | 'eval_loss') => points.filter(e => Number.isFinite(e[key])).map(e => `${42 + (e.step || 0) / steps * 600},${185 - e[key]! / maximum * 150}`).join(' ');
  return <figure className="st-chart"><figcaption><span><i />训练 Loss</span><span><i className="eval" />验证 Loss</span></figcaption><svg viewBox="0 0 680 215" role="img" aria-label="训练与验证损失随步数变化曲线"><path d="M42 25 V185 H650" fill="none" stroke="#bdc9c6" />{[0, 0.5, 1].map(p => <g key={p}><text x="2" y={190 - p * 150}>{(p * maximum).toFixed(2)}</text><path d={`M42 ${185 - p * 150} H650`} stroke="#e4eae7" /></g>)}<polyline points={line('loss')} fill="none" stroke="#087f6b" strokeWidth="2.5" /><polyline points={line('eval_loss')} fill="none" stroke="#c9821c" strokeWidth="2.5" />{(['loss', 'eval_loss'] as const).map(key => points.filter(e => Number.isFinite(e[key])).map(e => <circle key={`${key}-${e.seq}`} cx={42 + (e.step || 0) / steps * 600} cy={185 - e[key]! / maximum * 150} r={3} fill={key === 'loss' ? '#087f6b' : '#c9821c'} />))}<text x="42" y="208">0</text><text x="590" y="208">步数 {steps}</text></svg></figure>;
}

export default function TaskPanel({ id, onDone, onUpdate, onStream, onProgress, hideAnswer = false, hidePreview = false, hideProgress = false, compact = false }: { compact?: boolean; onProgress?: (step: number, total: number) => void; id: string; onDone?: (job: Job) => void; onUpdate?: (job: Job) => void; onStream?: (text: string, reasoning: string) => void; hideAnswer?: boolean; hidePreview?: boolean; hideProgress?: boolean }) {
  const [job, setJob] = useState<Job>(); const [events, setEvents] = useState<Event[]>([]); const [error, setError] = useState('');
  const callback = useRef(onDone); callback.current = onDone;
  const update = useRef(onUpdate); update.current = onUpdate;
  const stream = useRef(onStream); stream.current = onStream;
  const progressCallback = useRef(onProgress); progressCallback.current = onProgress;
  const lastCompleted = useRef('');
  useEffect(() => {
    let disposed = false; let after = 0; let timer: ReturnType<typeof setTimeout>; let output = ''; let reasoning = '';
    setJob(undefined); setEvents([]); setError('');
    async function poll() {
      try {
        const current = await request<Job>('GET', `/jobs/${id}`);
        const page = await request<{ items: Event[] }>('GET', `/jobs/${id}/events?after=${after}`);
        if (disposed) return;
        setJob(current); setError(''); update.current?.(current);
        if (page.items.length) {
          after = page.items.at(-1)!.seq; setEvents(old => [...old, ...page.items].slice(-5000));
          for (const event of page.items) if (event.type === 'token') {
            if (event.channel === 'reasoning') reasoning += event.text || ''; else output += event.text || '';
          }
          for (const event of page.items) if (event.type === 'progress' && event.total) progressCallback.current?.(event.step || 0, event.total);
          stream.current?.(output, reasoning);
        }
        if (terminal(current) && page.items.length < 250) {
          if (lastCompleted.current !== id) { lastCompleted.current = id; callback.current?.(current); }
          return;
        }
        timer = setTimeout(poll, page.items.length === 250 ? 20 : current.kind === 'inference' ? 150 : 700);
      } catch (e) { if (!disposed) { setError(errorMessage(e)); timer = setTimeout(poll, 2500); } }
    }
    void poll(); return () => { disposed = true; clearTimeout(timer); };
  }, [id]);
  const metrics = events.filter(e => e.type === 'metric'); const progress = events.filter(e => e.total).at(-1);
  const text = events.filter(e => e.type === 'token' && e.channel !== 'reasoning').map(e => e.text || '').join('');
  const reasoning = events.filter(e => e.type === 'token' && e.channel === 'reasoning').map(e => e.text || '').join('');
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ job, events }, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `ailab-${id}.json`; link.click(); URL.revokeObjectURL(url);
  }
  if (compact) return <><Error text={error || job?.error || ''} />{job && !terminal(job) && <div className="st-actions st-chat-controls"><JobControls job={job} /></div>}</>;
  return <section className="st-panel st-task"><header><div><span className={`st-state ${job?.state || ''}`}>{job ? stateLabel[job.state] : '读取任务'}</span><small>{id.slice(0, 8)}</small></div><div className="st-actions">{job && <JobControls job={job} />}<button onClick={download} disabled={!job}><Download size={14} />导出记录</button></div></header>
    <Error text={error || job?.error || ''} />
    {!hideProgress && progress && <div className="st-progress"><progress value={progress.step || 0} max={progress.total} /><span>{progress.step}/{progress.total}</span></div>}
    {job?.kind === 'sft' && <LossChart events={metrics} />}
    {!hideAnswer && (text || reasoning) && <ChatAnswer text={text} reasoning={reasoning} streaming={Boolean(job && !terminal(job))} />}
    {!hidePreview && typeof job?.result?.material_id === 'string' && <MediaPreview id={job.result.material_id} />}
    {job?.result && <div className="st-result"><h3>运行结果</h3>{job.result.metrics && <div className="st-metrics">{Object.entries(job.result.metrics).map(([key, value]) => <div key={key}><small>{key}</small><strong>{Number.isInteger(value) ? value : value.toFixed(5)}</strong></div>)}</div>}<p className="st-mono">{job.result.model_dir || job.result.file || job.output_dir}</p>{job.kind === 'sft' && <p>训练样本 {job.result.train_samples} · 验证样本 {job.result.validation_samples} · {job.result.kind === 'lora_adapter' ? 'LoRA 适配器（使用时需要原始基座）' : '完整模型'}</p>}{job.result.weight_loading === 'dequantize' && <p>量化基座在加载时解量化后进行 LoRA 训练；原始量化权重未修改。</p>}{job.result.weight_loading === 'quantized_lora' && <p>使用冻结的量化基座进行 LoRA 训练。</p>}{job.result.finish_reason === 'length' && <p>输出达到 token 上限，回答可能未完成。</p>}</div>}
    <details open={job?.kind === 'ablation' || job?.kind === 'install'}><summary>运行日志 {events.length >= 5000 ? '（显示最近 5000 条）' : ''}</summary><pre className="st-log" aria-label="运行日志">{events.filter(e => ['log', 'error', 'status'].includes(e.type)).map(e => e.text).join('\n') || '等待进程输出…'}</pre></details>
  </section>;
}

export function TaskHistory({ onSelect }: { onSelect: (id: string) => void }) {
  const [jobs, setJobs] = useState<Job[]>([]); const [error, setError] = useState('');
  function refresh() { void request<{ items: Job[] }>('GET', '/jobs').then(r => { setJobs(r.items); setError(''); }).catch(e => setError(errorMessage(e))); }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 1000); return () => clearInterval(timer); }, []);
  return <section className="st-panel"><header><h2>运行与历史任务</h2><span className="st-tag">自动更新</span></header><Error text={error} />{!jobs.length && <Empty>尚无任务</Empty>}<div className="st-history">{jobs.map(j => <div className="st-history-row" key={j.id}><button onClick={() => onSelect(j.id)}><span>{({ sft: 'SFT 训练', inference: '模型推理', ablation: '拒绝消融', install: '环境安装' } as Record<string, string>)[j.kind]}</span><span className={`st-state ${j.state}`}>{stateLabel[j.state]}{j.queue_position ? ` · 第 ${j.queue_position} 位` : ''}</span><time>{new Date(j.created_at * 1000).toLocaleString()}</time></button><JobControls job={j} changed={refresh} /></div>)}</div></section>;
}
