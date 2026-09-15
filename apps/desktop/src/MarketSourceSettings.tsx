import { useEffect, useRef, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { api, canPickFile, errorMessage } from './api';
import { Badge, Button, ErrorNotice } from './ui';

type Source = { provider_id: string; origin: string; source_label: string };
export function MarketSourceSettings({ onChanged }: { onChanged: () => void }) {
  const [origin, setOrigin] = useState<string | null>(null); const [port, setPort] = useState('');
  const [busy, setBusy] = useState(true); const [error, setError] = useState(''); const [unknown, setUnknown] = useState(false);
  const live = useRef(true);
  async function read() {
    setBusy(true); setError('');
    try {
      const value = canPickFile() ? (await invoke<{ market_fixture_origin?: string | null }>('host_status')).market_fixture_origin || null : (await api<{ items: Source[] }>('GET', '/market/sources')).items.find(item => item.provider_id === 'fixture-provider')?.origin || null;
      if (live.current) { setOrigin(value); setPort(value?.split(':').at(-1) || ''); setUnknown(false); }
    } catch (e) { if (live.current) { setError(errorMessage(e)); setUnknown(true); } }
    finally { if (live.current) setBusy(false); }
  }
  useEffect(() => { live.current = true; void read(); return () => { live.current = false; }; }, []);
  const valid = /^[1-9]\d{0,4}$/.test(port) && Number(port) <= 65535;
  async function configure(value: string | null) {
    setBusy(true); setError('');
    try {
      const result = await invoke<{ market_fixture_origin: string | null }>('configure_market_fixture', { origin: value });
      if (live.current) { setOrigin(result.market_fixture_origin); setPort(result.market_fixture_origin?.split(':').at(-1) || ''); setUnknown(false); onChanged(); }
    } catch (e) { if (live.current) { setError(errorMessage(e)); setUnknown(true); } }
    finally { if (live.current) setBusy(false); }
  }
  return <section className="data-management" aria-label="受控数据来源设置"><div className="section-title"><h3>数据集来源</h3><Badge>受控测试来源</Badge></div><p className="muted">连接已启动的本机测试提供方，验证目录、申请、下载和导入。审批回复由提供方保存；App 只读取状态。默认关闭。</p><p>当前来源：{unknown ? '状态待确认' : origin || '未连接'}</p>
    {canPickFile() ? <><label>本机提供方端口<input inputMode="numeric" maxLength={5} value={port} disabled={busy || unknown} onChange={e => setPort(e.target.value)} placeholder="输入提供方显示的端口" /></label><small className="muted">固定连接 127.0.0.1。更改会重新连接本机控制服务，请先完成当前任务和下载。</small><div className="dialog-actions"><Button busy={busy} disabled={!valid || unknown || origin === `http://127.0.0.1:${port}`} onClick={() => void configure(`http://127.0.0.1:${port}`)}>连接受控来源</Button><Button disabled={busy || !origin || unknown} onClick={() => void configure(null)}>断开来源</Button></div></> : <p className="muted">来源由当前运行环境登记。桌面 App 可在此明确连接或断开。</p>}
    <ErrorNotice message={error} />{unknown && <Button busy={busy} onClick={() => void read()}>重新读取连接状态</Button>}
  </section>;
}
