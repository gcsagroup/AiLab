import { useEffect, useRef, useState } from 'react';
import { api, collection, errorMessage, mergeRecords } from './api';
import type { ExecutionTarget } from './ExecutionTargets';
import type { Preflight } from './types';
import { Button, ErrorNotice, readableSize } from './ui';

export function ExecutionLocation({ projectId, value, disabled, onChange, refreshKey }: { projectId: string; value?: string | null; disabled: boolean; onChange: (id: string | null) => void; refreshKey?: string }) {
  const [targets, setTargets] = useState<ExecutionTarget[]>([]); const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState(''); const [loading, setLoading] = useState(false); const epoch = useRef(0);
  const path = `/execution-targets?project_id=${encodeURIComponent(projectId)}`;
  async function load(current: number, cursor?: string) {
    setLoading(true); setError('');
    try {
      const result = await collection<ExecutionTarget>(path, cursor);
      if (!Array.isArray(result.items)) throw new Error('执行位置列表格式无效，请重新读取。');
      if (epoch.current === current) { setTargets(items => cursor ? mergeRecords(items, result.items) : result.items); setNext(result.next_cursor || null); }
    } catch (e) { if (epoch.current === current) setError(errorMessage(e)); }
    finally { if (epoch.current === current) setLoading(false); }
  }
  useEffect(() => { const current = ++epoch.current; setTargets([]); setNext(null); void load(current); return () => { ++epoch.current; }; }, [projectId, refreshKey]);
  const selected = targets.find(target => target.id === value);
  return <div className="form-stack" aria-label="本次执行位置">
    <label>执行位置<select value={value || ''} disabled={disabled} onChange={e => onChange(e.target.value || null)}><option value="">{window.ailabHF ? '本机 Windows' : '本机 Apple GPU'}</option>{value && !selected && <option value={value}>已保存的执行目标 · 待核实</option>}{targets.map(target => <option key={target.id} value={target.id}>{target.name} · {target.nvidia_ready ? 'NVIDIA 待任务检查' : 'NVIDIA 尚未就绪'}</option>)}</select></label>
    {value ? <p className="muted">{selected ? `${selected.name} · ${selected.origin} · ${selected.executor_id}` : `目标编号：${value}`}<br />本次使用 NVIDIA 文本组合。检查只核对环境与发送范围，明确开始后才发送模型和输入。</p> : <small className="muted">本次使用本机设备。更改项目默认位置不会覆盖此草稿。</small>}
    {next && <Button disabled={disabled || loading} onClick={() => void load(epoch.current, next)}>加载更多执行位置</Button>}
    {error && <><ErrorNotice message={error} /><Button disabled={disabled || loading} onClick={() => void load(epoch.current)}>重新读取执行位置</Button></>}
  </div>;
}

export function ExecutionDefault({ projectId, onChanged, refreshKey }: { projectId: string; onChanged: () => void; refreshKey?: string }) {
  const [saved, setSaved] = useState<{ execution_target_id: string | null; revision: number } | null>(null);
  const [value, setValue] = useState<string | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const epoch = useRef(0); const commandKey = useRef(crypto.randomUUID());
  async function load(current: number) {
    setBusy(true);
    try { const result = await api<{ execution_target_id: string | null; revision: number }>('GET', `/projects/${projectId}/execution-default`); if (!Number.isInteger(result.revision) || (result.execution_target_id !== null && typeof result.execution_target_id !== 'string')) throw new Error('项目默认位置格式无效，请重新读取。'); if (epoch.current === current) { setSaved(result); setValue(result.execution_target_id); setError(''); } }
    catch (e) { if (epoch.current === current) setError(errorMessage(e)); }
    finally { if (epoch.current === current) setBusy(false); }
  }
  useEffect(() => { const current = ++epoch.current; setSaved(null); setValue(null); setNotice(''); void load(current); return () => { ++epoch.current; }; }, [projectId]);
  async function save() {
    if (!saved) return; const current = epoch.current; setBusy(true); setError(''); setNotice('');
    try {
      const result = await api<{ execution_target_id: string | null; revision: number }>('POST', `/projects/${projectId}/execution-default`, { execution_target_id: value, expected_revision: saved.revision }, commandKey.current);
      if (epoch.current === current) { setSaved(result); setValue(result.execution_target_id); setNotice('已保存。仅以后新建的文本任务使用此默认位置，现有草稿保持原位置。'); onChanged(); }
    } catch (e) { if (epoch.current === current) setError(errorMessage(e)); }
    finally { if (epoch.current === current) setBusy(false); }
  }
  return <section className="form-stack" aria-label="项目默认执行位置"><h4>新文本任务的默认位置</h4><ExecutionLocation key={projectId} refreshKey={refreshKey} projectId={projectId} value={value} disabled={busy || !saved} onChange={id => { setValue(id); setNotice(''); commandKey.current = crypto.randomUUID(); }} /><Button disabled={busy || !saved || saved.execution_target_id === value} onClick={() => void save()}>保存默认执行位置</Button><Button disabled={busy} onClick={() => void load(epoch.current)}>重新读取项目默认位置</Button><ErrorNotice message={error} />{notice && <p role="status">{notice}</p>}</section>;
}

export function UploadSummary({ preflight }: { preflight: Preflight }) {
  const target = preflight.execution_target; const summary = preflight.upload_summary;
  if (!target && !summary) return null;
  return <section className="form-stack" aria-label="本次发送范围"><h4>本次发送范围</h4>{target && <p>{target.name} · {target.origin}<br /><span className="mono">{target.executor_id}</span></p>}{summary && <><p>{summary.files.length} 个文件 · {readableSize(summary.total_bytes)}，另发送本次输入与运行配置。点击开始后传输。</p><details><summary>查看文件与完整性摘要</summary><ul>{summary.files.map(file => <li key={file.path}>{file.path} · {readableSize(file.size)}<br /><span className="mono">SHA-256：{file.sha256}</span></li>)}</ul></details></>}</section>;
}
