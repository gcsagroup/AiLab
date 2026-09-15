import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { Attempt, Task } from './types';
import { activeStates, Badge, Button, ErrorNotice } from './ui';

type Checkpoint = { id: string; source_attempt_id: string; step: number; total_steps: number; manifest_digest: string; status: string };

export function Checkpoints({ attempt, onRestoreTask }: { attempt: Attempt; onRestoreTask?: (task: Task) => void }) {
  const [items, setItems] = useState<Checkpoint[]>([]); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const keys = useRef(new Map<string, string>()); const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let live = true;
    void api<{ items: Checkpoint[] }>('GET', `/checkpoints?attempt_id=${encodeURIComponent(attempt.id)}`).then(result => { if (live) { setItems(result.items || []); setError(''); } }).catch(e => { if (live) setError(errorMessage(e)); });
    return () => { live = false; };
  }, [attempt.id, attempt.state, attempt.checkpoint_id]);
  async function restore(item: Checkpoint) {
    setBusy(true); setError(''); if (!keys.current.has(item.id)) keys.current.set(item.id, crypto.randomUUID());
    try {
      const task = await api<Task>('POST', `/checkpoints/${item.id}/restore-task`, {}, keys.current.get(item.id));
      if (mounted.current) onRestoreTask?.(task);
    } catch (e) { if (mounted.current) setError(errorMessage(e)); }
    finally { if (mounted.current) setBusy(false); }
  }
  if (!items.length && !error) return null;
  return <section className="data-check" aria-label="完整训练检查点"><strong>完整训练检查点</strong><p className="muted">保留权重、优化器、随机状态和数据位置。原进程退出后，从检查点创建新的恢复任务，再检查并开始。</p>{items.map(item => <div className="result-actions" key={item.id}><span>第 {item.step} / {item.total_steps} 步 <Badge>已保存</Badge></span>{onRestoreTask && !activeStates.has(attempt.state) && !attempt.recovery_required && <Button busy={busy} onClick={() => restore(item)}>从第 {item.step} 步创建恢复任务</Button>}</div>)}<ErrorNotice message={error} /></section>;
}
