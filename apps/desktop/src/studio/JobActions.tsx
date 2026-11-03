import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pause, Play, Square } from 'lucide-react';
import { errorMessage } from '../api';
import { Error, request } from './common';
import { terminal, type Job } from './types';

export function JobControls({ job, changed }: { job: Job; changed?: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  async function act(action: string) { setBusy(true); setError(''); try { await request('POST', `/jobs/${job.id}/${action}`, {}); changed?.(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  if (terminal(job)) return null;
  const paused = ['paused', 'pausing'].includes(job.state);
  return <span className="st-actions"><Error text={error} />{job.kind !== 'install' && <button type="button" disabled={busy || ['cancelling', 'pausing', 'resuming'].includes(job.state)} onClick={() => void act(paused ? 'resume' : 'pause')}>{paused ? <Play size={14} /> : <Pause size={14} />}{paused ? '继续' : '暂停'}</button>}<button type="button" disabled={busy || job.state === 'cancelling'} onClick={() => void act('cancel')}><Square size={14} />取消</button></span>;
}

export function HeaderJobAction({ id, form, label, disabled }: { id: string; form: string; label: string; disabled: boolean }) {
  const [job, setJob] = useState<Job>(); const [error, setError] = useState(''); const [pending, setPending] = useState(false);
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => setHost(document.getElementById('studio-page-actions')), []);
  useEffect(() => { let alive = true; setJob(undefined); setError(''); if (!id) return;
    const poll = () => request<Job>('GET', `/jobs/${id}`).then(j => { if (alive) { setJob(j); setError(''); } }).catch(e => { if (alive) setError(errorMessage(e)); });
    void poll(); const timer = setInterval(() => void poll(), 800); return () => { alive = false; clearInterval(timer); };
  }, [id]);
  const active = job && !terminal(job); const paused = job?.state === 'paused';
  const button = <div><Error text={error} />{active ? <button className="st-primary" type="button" disabled={pending || ['pausing', 'resuming', 'cancelling'].includes(job.state)} onClick={async () => { setPending(true); try { setJob(await request<Job>('POST', `/jobs/${id}/${paused ? 'resume' : 'pause'}`, {})); } catch (e) { setError(errorMessage(e)); } finally { setPending(false); } }}>{paused ? <Play size={16} /> : <Pause size={16} />}{paused ? '继续' : job.state === 'pausing' ? '正在暂停' : '暂停'}</button> : <button type="submit" form={form} className="st-primary" disabled={disabled}><Play size={16} />{label}</button>}</div>;
  return host ? createPortal(button, host) : button;
}
