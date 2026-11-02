import { Cpu, LoaderCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { terminal, type Job, type LlmStatus } from './types';

export default function ModelStatus({ job, resident, controls, concise = false }: { concise?: boolean; job?: Job; resident?: LlmStatus; controls?: ReactNode }) {
  const phase = typeof job?.model_state === 'string' ? job.model_state : '';
  let label = '模型未加载'; let detail = '提交任务后加载'; let active = false;
  if (job) {
    if (job.state === 'queued') { label = '等待加载'; detail = '任务排队中'; }
    else if (['paused', 'pausing', 'resuming'].includes(job.state)) {
      label = job.state === 'resuming' ? '正在恢复' : job.state === 'pausing' ? '正在暂停' : '任务已暂停';
      detail = phase === 'generating' ? '模型仍在内存中' : phase ? '加载进度已保留' : '尚未加载模型';
    } else if (phase === 'unloaded') {
      label = '模型已卸载'; detail = job.state === 'failed' ? '任务失败 · 资源已释放' : job.state === 'cancelled' ? '任务取消 · 资源已释放' : '推理进程已退出';
    } else if (terminal(job)) { label = '模型未驻留'; detail = job.state === 'failed' ? '任务失败，查看下方日志' : '任务已结束'; }
    else if (job.state === 'cancelling' || phase === 'unloading') { label = '正在卸载模型'; detail = '等待推理进程退出'; active = true; }
    else if (phase === 'generating') { label = '模型已加载'; detail = '正在生成'; active = true; }
    else { label = phase === 'loading' ? '正在加载模型' : '准备加载模型'; detail = '读取本地权重'; active = true; }
  }
  if (resident && (!job || terminal(job) || job.state === 'running')) {
    active = ['loading', 'generating', 'unloading'].includes(resident.phase);
    label = ({ unloaded:'模型未加载', loading:'正在加载模型', loaded:'模型已加载', generating:'模型已加载 · 正在生成', unloading:'正在卸载模型' } as Record<string,string>)[resident.phase] || '读取模型状态';
    detail = resident.phase === 'loaded' ? `空闲约 ${Math.max(1, Math.ceil(((resident.expires_at || Date.now()/1000) - Date.now()/1000)/60))} 分钟后卸载` : resident.phase === 'unloaded' ? '可手动加载，或发送时自动加载' : resident.model.split(/[\\/]/).at(-1) || '';
  }
  return <div className={`st-model-status ${active ? 'active' : ''}`} role="status" aria-live="polite">{active ? <LoaderCircle className="st-status-spinner" size={18} /> : <Cpu size={18} />}<strong>{label}</strong>{!concise && <span>{detail}</span>}{controls && <div className="st-actions">{controls}</div>}</div>;
}
