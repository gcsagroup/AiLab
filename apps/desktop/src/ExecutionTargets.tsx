import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { api, canPickFile, collection, errorMessage, mergeRecords } from './api';
import { Badge, Button, ErrorNotice } from './ui';
import { RemoteTransfers } from './RemoteTransfer';
import { ExecutionDefault } from './ExecutionLocation';

export type ExecutionTarget = {
  id: string; project_id: string; name: string; origin: string; executor_id: string; revision: number;
  credential_ref: string; credential_status: string; validation_scope: string; connection_state: string;
  transport?: 'loopback_http' | 'https'; network_remote_ready?: boolean;
  protocol_ready?: boolean; nvidia_ready?: boolean; checked_at?: string;
  last_error?: { code: string; message: string } | null;
};

export function validExecutionOrigin(value: string) {
  const origin = value.trim();
  if (!origin || origin.length > 2048 || !/^[\x21-\x7e]+$/.test(origin)) return false;
  if (/^http:\/\/127\.0\.0\.1:([1-9]\d{0,4})\/?$/i.test(origin)) return Number(origin.match(/:(\d+)\/?$/)?.[1]) <= 65535;
  const parts = origin.match(/^https:\/\/(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::([1-9]\d{0,4}))?\/?$/i);
  if (!parts || (parts[2] && Number(parts[2]) > 65535)) return false;
  try {
    const parsed = new URL(origin); const host = parts[1].toLowerCase();
    if (host.startsWith('[')) return parsed.hostname.startsWith('[');
    // 拒绝 URL 解析器会自动改写的短式、八进制或十六进制 IPv4。
    if (/^[0-9.]+$/.test(parsed.hostname)) return host === parsed.hostname && host.split('.').length === 4;
    const dns = host.replace(/\.$/, '');
    return dns.length <= 253 && dns.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label));
  } catch { return false; }
}

function verifiedProtocol(target: ExecutionTarget) {
  if (target.transport === 'https' && target.validation_scope === 'https_protocol_only') return 'HTTPS 协议';
  return target.validation_scope === 'loopback_protocol_only' ? '回环协议' : '执行协议';
}

function connectionLabel(target: ExecutionTarget) {
  if (target.credential_status === 'required') return '需要凭据';
  if (target.connection_state !== 'connected') return '连接待确认';
  return target.protocol_ready ? `${verifiedProtocol(target)}连接已验证` : '身份已连接，能力待检查';
}

export function ExecutionTargets({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const [targets, setTargets] = useState<ExecutionTarget[]>([]); const [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [form, setForm] = useState<'new' | string | null>(null); const [name, setName] = useState('');
  const [transferTarget, setTransferTarget] = useState<string | null>(null);
  const [origin, setOrigin] = useState(''); const [executor, setExecutor] = useState(''); const [secret, setSecret] = useState('');
  const epoch = useRef(0); const commandKey = useRef(crypto.randomUUID());
  const path = `/execution-targets?project_id=${encodeURIComponent(projectId)}`;

  async function load(expected: number, cursor?: string) {
    const result = await collection<ExecutionTarget>(path, cursor);
    if (epoch.current === expected) { setTargets(current => cursor ? mergeRecords(current, result.items) : result.items); setNext(result.next_cursor || null); }
  }
  useEffect(() => {
    const current = ++epoch.current; setTargets([]); setNext(null); setForm(null); setTransferTarget(null); setSecret(''); setError(''); setNotice('');
    if (projectId) { setBusy(true); void load(current).catch(e => { if (epoch.current === current) setError(errorMessage(e)); }).finally(() => { if (epoch.current === current) setBusy(false); }); }
    return () => { ++epoch.current; };
  }, [projectId]);

  function changeForm(value: string | null) { setForm(value); setTransferTarget(null); setSecret(''); setName(''); setOrigin(''); setExecutor(''); setError(''); setNotice(''); commandKey.current = crypto.randomUUID(); }
  function formChanged() { commandKey.current = crypto.randomUUID(); }
  async function check(target: ExecutionTarget) {
    const result = canPickFile()
      ? await invoke<ExecutionTarget>('connect_remote_target', { targetId: target.id, expectedRevision: target.revision })
      : await api<ExecutionTarget>('POST', `/execution-targets/${target.id}/check`, {});
    return { ...target, ...result };
  }
  async function act(action: () => Promise<void>) {
    const current = epoch.current; const submittedSecret = secret; setBusy(true); setError(''); setNotice('');
    try { await action(); if (epoch.current === current) onChanged(); }
    catch (e) { if (epoch.current === current) setError(submittedSecret ? errorMessage(e).replaceAll(submittedSecret, '[凭据已隐藏]') : errorMessage(e)); }
    finally { if (epoch.current === current) { setSecret(''); try { await load(current); } catch (e) { if (epoch.current === current) setError(errorMessage(e)); } if (epoch.current === current) setBusy(false); } }
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); const current = epoch.current; const selected = targets.find(target => target.id === form);
    await act(async () => {
      const input = { name: name.trim(), project_id: projectId, origin: origin.trim(), transport: origin.trim().toLowerCase().startsWith('https://') ? 'https' : 'loopback_http', executor_id: executor.trim(), credential_token: secret };
      const target = form === 'new'
        ? canPickFile() ? await invoke<ExecutionTarget>('create_execution_target', { input, idempotencyKey: commandKey.current }) : await api<ExecutionTarget>('POST', '/execution-targets', input, commandKey.current)
        : selected ? canPickFile() ? await invoke<ExecutionTarget>('connect_remote_target', { targetId: selected.id, secret, expectedRevision: selected.revision }) : await api<ExecutionTarget>('POST', `/execution-targets/${selected.id}/credentials`, { credential_token: secret, expected_revision: selected.revision }, commandKey.current) : null;
      if (!target) throw new Error('目标已改变，请刷新后重新选择。');
      if (epoch.current === current) { setTargets(items => mergeRecords(items, [target])); setForm(null); }
      const checked = canPickFile() && form !== 'new' ? target : await check(target);
      if (epoch.current === current) setNotice(checked.protocol_ready ? `目标身份和${verifiedProtocol(checked)}已验证。模型运行能力仍以任务检查为准。` : '目标已保存，执行能力尚未通过检查。');
    });
  }
  const validOrigin = validExecutionOrigin(origin);
  const valid = /^[\x21-\x7e]{32,512}$/.test(secret) && (form !== 'new' || (name.trim().length > 0 && validOrigin && /^executor-[0-9a-f]{32}$/.test(executor.trim())));

  return <section className="data-management" aria-label="执行目标管理"><div className="section-title"><h3>执行目标</h3><Badge>HTTPS / 本机回环</Badge></div>
    <p className="muted">登记 HTTPS 或本机回环执行服务，检查身份、传输和重连。HTTPS 会验证服务器证书。验证连接不会发送项目文件或运行模型，NVIDIA 能力仍需任务检查。</p>
    {!projectId ? <p>创建或选择项目后再登记执行目标。</p> : <>
      <div className="form-stack">{targets.map(target => <article className="resource-card execution-target-card" key={target.id} aria-label={`执行目标：${target.name}`}>
        <div className="section-title"><h4>{target.name}</h4><Badge>{connectionLabel(target)}</Badge></div>
        <dl className="facts"><div><dt>连接地址</dt><dd>{target.origin}</dd></div><div><dt>传输方式</dt><dd>{target.transport === 'https' ? 'HTTPS（校验服务器证书）' : '本机回环 HTTP'}</dd></div><div><dt>执行器编号</dt><dd className="mono">{target.executor_id}</dd></div></dl>
        <p className="muted">{target.nvidia_ready ? 'NVIDIA 探测有返回，实际模型与参数仍需任务检查。' : 'NVIDIA 尚未通过实机验证。'}</p>
        <ErrorNotice message={target.last_error?.message || ''} />
        <div className="dialog-actions"><Button disabled={busy || (!canPickFile() && target.credential_status === 'required')} onClick={() => { const current = epoch.current; void act(async () => { const result = await check(target); if (epoch.current === current) setNotice(result.protocol_ready ? `${verifiedProtocol(result)}已验证，未执行模型任务。` : '执行能力尚未通过检查。'); }); }}>验证连接</Button><Button disabled={busy} onClick={() => changeForm(target.id)}>重新输入凭据</Button>{canPickFile() && <Button disabled={busy} onClick={() => { const current = epoch.current; void act(async () => { await invoke('forget_remote_target', { targetId: target.id, expectedRevision: target.revision }); if (epoch.current === current) setNotice('已清除本目标保存的凭据。连接记录保留，重新连接需要输入凭据。'); }); }}>清除保存的凭据</Button>}</div>
        <Button disabled={busy || !target.protocol_ready || target.credential_status === 'required'} onClick={() => { setForm(null); setSecret(''); setTransferTarget(target.id); }}>验证文件传输</Button>
      </article>)}</div>
      {targets.find(target => target.id === transferTarget) && <RemoteTransfers key={transferTarget} projectId={projectId} target={targets.find(target => target.id === transferTarget)!} onChanged={onChanged} />}
      {!busy && !targets.length && !form && <p className="muted">当前项目尚未登记执行目标。</p>}
      {next && <Button disabled={busy} onClick={() => { const current = epoch.current; setBusy(true); void load(current, next).catch(e => { if (epoch.current === current) setError(errorMessage(e)); }).finally(() => { if (epoch.current === current) setBusy(false); }); }}>加载更多执行目标</Button>}
      {form ? <form className="form-stack" aria-label={form === 'new' ? '登记执行目标' : '更新执行目标凭据'} onSubmit={submit}>
        {form === 'new' && <><label>目标名称<input required maxLength={80} disabled={busy} value={name} onChange={e => { setName(e.target.value); formChanged(); }} /></label><label>连接地址<input required autoComplete="off" spellCheck={false} disabled={busy} value={origin} onChange={e => { setOrigin(e.target.value); formChanged(); }} placeholder="https://执行服务地址:端口" /></label><small className="muted">HTTPS 需要有效的受信证书，也可使用 http://127.0.0.1:端口 进行本机回环验证。地址登记后固定。</small><label>执行器编号<input required autoComplete="off" spellCheck={false} disabled={busy} value={executor} onChange={e => { setExecutor(e.target.value); formChanged(); }} placeholder="粘贴该执行服务显示的编号" /></label></>}
        <label>访问凭据<input type="password" required minLength={32} maxLength={512} autoComplete="new-password" spellCheck={false} disabled={busy} value={secret} onChange={e => { setSecret(e.target.value); formChanged(); }} /></label>
        <small className="muted">{canPickFile() ? '凭据保存在系统钥匙串，仅用于此目标连接，不进入项目配方或导出。' : '开发浏览器仅临时连接；服务重启后需重新输入凭据。凭据不写入项目记录。'}</small>
        <div className="dialog-actions"><Button primary type="submit" busy={busy} disabled={!valid}>保存并验证连接</Button><Button disabled={busy} onClick={() => changeForm(null)}>取消输入</Button></div>
      </form> : <Button disabled={busy} onClick={() => changeForm('new')}>登记执行目标</Button>}
      <Button disabled={busy} onClick={() => void act(async () => {})}>刷新执行目标</Button>
      <ExecutionDefault refreshKey={targets.map(target => target.id).join(',')} projectId={projectId} onChanged={onChanged} />
    </>}
    <ErrorNotice message={error} />{notice && <p role="status">{notice}</p>}
  </section>;
}
