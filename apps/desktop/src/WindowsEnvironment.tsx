import { useState, type ReactNode } from 'react';
import { Download, RefreshCw } from 'lucide-react';
import { api, errorMessage } from './api';
import { Button, Dialog, ErrorNotice } from './ui';
import type { Capability, Device, Kind } from './types';

type Check = { id: string; label: string; status: 'ready' | 'partial' | 'failed'; detail: string; free_bytes?: number };
export type WindowsEnvironmentReport = {
  id: string; checked_at: string; app_version: string;
  system: { os: string; release: string; arch: string; cpu: string; logical_processors: number; ram_bytes: number; free_ram_bytes: number };
  devices: Device[]; checks: Check[]; capabilities: Capability[];
};
const taskNames: Record<Kind, string> = { text: '语言与多模态理解', image: '图片生成', video: '视频生成', audio: '音频试用' };
const labels = { ready: '通过', partial: '部分可用', failed: '失败' };
function gibibytes(bytes?: number) {
  return bytes === undefined ? '未知容量' : (bytes / 1024 ** 3).toFixed(1) + ' GiB';
}

export function WindowsEnvironment({ report, busy, error, onRefresh, onClose, children }: {
  report: WindowsEnvironmentReport | null; busy: boolean; error: string; onRefresh: () => void; onClose: () => void; children: ReactNode;
}) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(''), [saveError, setSaveError] = useState('');
  async function save() {
    if (!report) return;
    setSaving(true); setSaveError(''); setSaved('');
    try {
      const result = await api<{ saved: boolean; filename?: string }>('POST', '/environment/export', { id: report.id });
      if (result.saved) setSaved('已保存 ' + result.filename);
    } catch (e) { setSaveError(errorMessage(e)); }
    finally { setSaving(false); }
  }
  const storage = report?.checks.find(item => item.id === 'storage');
  const issues = report?.checks.filter(item => item.status !== 'ready') || [];
  return <Dialog title="设备与环境" wide onClose={onClose}>
    <div className="dialog-actions">
      <Button primary busy={busy} disabled={saving} onClick={() => { setSaved(''); setSaveError(''); onRefresh(); }}>
        <RefreshCw size={15} />刷新环境
      </Button>
      <Button busy={saving} disabled={!report || busy || !!error} onClick={save}><Download size={15} />导出诊断摘要</Button>
    </div>
    <p role="status" className="muted">{busy ? '正在检测本机设备、执行器和模型目录…' : report
      ? <>{error ? '上次检测' : '检测完成'} · <time dateTime={report.checked_at}>{new Date(report.checked_at).toLocaleString('zh-CN', { hour12: false })}</time>
        {' · '}{report.checks.length - issues.length}/{report.checks.length} 项通过</> : '尚未取得本机检测结果。'}</p>
    <ErrorNotice message={error || saveError} />{saved && <p role="status">{saved}</p>}
    {report && <>
      {issues.length > 0 && <section aria-label="需要处理的项目" className="data-management"><h3>需要处理的项目</h3>
        {issues.map(item => <p key={item.id}><strong>{item.label}</strong> · {item.detail}</p>)}</section>}
      <section className="data-management" aria-label="本机硬件"><h3>本机硬件</h3>
        <dl className="facts">
          <div><dt>系统</dt><dd>{report.system.os} {report.system.arch} · 内核 {report.system.release}</dd></div>
          <div><dt>处理器</dt><dd>{report.system.cpu} · {report.system.logical_processors} 个逻辑处理器</dd></div>
          <div><dt>系统内存</dt><dd>{gibibytes(report.system.free_ram_bytes)} 可用 / {gibibytes(report.system.ram_bytes)}</dd></div>
          <div><dt>模型目录所在磁盘</dt><dd>{storage?.free_bytes !== undefined ? gibibytes(storage.free_bytes) + ' 可用 · 读写通过' : storage?.detail}</dd></div>
        </dl>
        <h4>GGML 可选设备</h4>
        {report.devices.map(device => <div key={device.id}><strong>{device.name}</strong>
          {device.id !== 'cpu' && device.memory_bytes !== undefined && <p className="muted">驱动报告显存 · {gibibytes(device.free_bytes)} 可用 / {gibibytes(device.memory_bytes)}</p>}</div>)}
        {!report.devices.length && <p>设备枚举失败，请查看检测明细。</p>}
      </section>
      <section className="data-management" aria-label="各类任务环境"><h3>可用任务组合</h3>
        <p className="muted">按基础执行器汇总。选好模型后，任务预检会核对架构、权重组件和所选设备。</p>
        <dl className="facts">{report.capabilities.filter(item => item.operation === 'generate').map(item =>
          <div key={item.kind}><dt>{taskNames[item.kind]}</dt><dd>{item.status === 'partial' ? '部分可用' : item.supported ? '环境就绪' : '尚未就绪'}
            {item.status !== 'ready' && <p className="muted">{item.reason}</p>}</dd></div>)}</dl>
      </section>
      <details className="data-management"><summary>检测明细（{report.checks.length} 项）</summary>
        <dl className="facts">{report.checks.map(item => <div key={item.id}><dt>{item.label}</dt><dd><strong>{labels[item.status]}</strong> · {item.detail}</dd></div>)}</dl>
        <small className="muted">AiLab {report.app_version} · JSON 摘要包含本页的硬件信息、组件状态和检测时间。</small>
      </details>
    </>}
    <div className="data-management">{children}</div>
    <p className="muted">Windows 版暂未接入远程执行目标、市场数据源管理、整库备份恢复和存储清理。</p>
  </Dialog>;
}
