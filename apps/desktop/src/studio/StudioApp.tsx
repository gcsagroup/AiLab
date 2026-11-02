import { useCallback, useEffect, useState } from 'react';
import { Boxes, ChevronDown, ChevronRight, Cpu, Database, FlaskConical, MessagesSquare, ListTodo, PanelLeftClose } from 'lucide-react';
import { errorMessage } from '../api';
import { useExitPreparation } from '../ExitPreparation';
import { Error, Empty, request } from './common';
import type { Assets, Status } from './types';
import Training from './Training';
import Library from './Library';
import Ablation from './Ablation';
import Environments from './Environments';
import EnvironmentCollection from './EnvironmentCollection';
import Inference from './Inference';
import TaskPanel, { TaskHistory } from './TaskPanel';
import './studio.css';

type Page = 'environmentCollection' | 'materials' | 'models' | 'datasets' | 'inference' | 'training' | 'ablation' | 'evaluation' | 'quantization' | 'environment' | 'tasks';
const titles: Record<Page, string> = { environmentCollection:'环境集', materials: '素材库', models: '模型库', datasets: '数据集', inference: '模型测试', training: '训练', ablation: '拒绝消融', evaluation: '评测', quantization: '量化', environment: '设置', tasks: '任务记录' };
export default function StudioApp() {
  const [page, setPage] = useState<Page>('inference'); const [expanded, setExpanded] = useState(true); const [collapsed, setCollapsed] = useState(false);
  const [status, setStatus] = useState<Status>(); const [assets, setAssets] = useState<Assets>({ models: [], datasets: [] }); const [error, setError] = useState(''); const [selected, setSelected] = useState('');
  const refresh = useCallback(() => { void Promise.all([request<Status>('GET', '/status'), request<Assets>('GET', '/assets')]).then(([s, a]) => { setStatus(s); setAssets(a); setError(''); }).catch(e => setError(errorMessage(e))); }, []);
  useEffect(refresh, [refresh]);
  const exit = useExitPreparation(async () => { const { items } = await request<{ items: { state: string }[] }>('GET', '/jobs'); if (items.some(j => ['running', 'queued', 'cancelling', 'pausing', 'paused', 'resuming'].includes(j.state))) throw new globalThis.Error('请先结束或取消运行任务，再退出应用。'); });
  function navigate(next: Page) { setPage(next); setSelected(''); refresh(); if (document.scrollingElement) document.scrollingElement.scrollTop = 0; }
  return <div className={`studio ${collapsed ? 'st-nav-collapsed' : ''}`}><aside className="st-sidebar"><div className="st-brand"><span className="st-brand-mark">A</span><div><strong>AiLab</strong><small>本地模型工作台</small></div></div><nav aria-label="主导航">
    <button className={page === 'models' ? 'active' : ''} onClick={() => navigate('models')}><Boxes size={19} />模型库</button>
    <button className={page === 'datasets' ? 'active' : ''} onClick={() => navigate('datasets')}><Database size={19} />数据集</button>
    <button className={page === 'environmentCollection' ? 'active' : ''} onClick={() => navigate('environmentCollection')}><FlaskConical size={19} />环境集</button>
    <button className={page === 'materials' ? 'active' : ''} onClick={() => navigate('materials')}><Boxes size={19} />素材库</button>
    <button className={page === 'inference' ? 'active' : ''} onClick={() => navigate('inference')}><MessagesSquare size={19} />模型测试</button>
    <button aria-expanded={expanded} onClick={() => setExpanded(!expanded)}><FlaskConical size={19} />模型实验室{expanded ? <ChevronDown className="st-chevron" size={16} /> : <ChevronRight className="st-chevron" size={16} />}</button>
    {expanded && <div className="st-subnav">{(['evaluation', 'training', 'quantization', 'ablation'] as Page[]).map(p => <button className={page === p ? 'active' : ''} key={p} onClick={() => navigate(p)}>{titles[p]}</button>)}</div>}
    <button className={page === 'tasks' ? 'active' : ''} onClick={() => navigate('tasks')}><ListTodo size={19} />任务记录</button>
  </nav><div className="st-sidebar-bottom"><button className={page === 'environment' ? 'active' : ''} onClick={() => navigate('environment')}><Cpu size={19} />设置</button><span className={`st-connection ${error ? 'offline' : ''}`}><i />{status && !error ? `${status.hardware.os} · 已连接` : '服务未连接'}</span></div></aside>
    <main className="st-main"><div className="st-topbar"><button aria-label="展开或收起侧栏" onClick={() => setCollapsed(!collapsed)}><PanelLeftClose size={18} /></button><span>{['training', 'ablation', 'evaluation', 'quantization'].includes(page) ? '模型实验室 / ' : ''}{titles[page]}</span><span className="st-topbar-right">本地执行</span><div id="studio-page-actions" /></div><div className="st-content">
    <Error text={error || exit.error} />{error && <p className="st-note">源码运行：先启动 scripts/studio.py，再启动前端开发服务。</p>}
    {page === 'environmentCollection' && <EnvironmentCollection />}
    {page === 'materials' && <Library />}
    {page === 'inference' && <Inference assets={assets} refreshAssets={refresh} />}
    {page === 'training' && <Training assets={assets} />}
    {page === 'ablation' && <Ablation assets={assets} vllmReady={Boolean(status?.runtimes.find(r => r.id === 'vllm')?.installed)} />}
    {page === 'environment' && (status ? <Environments status={status} refresh={refresh} /> : <Empty>连接后可管理运行环境。</Empty>)}
    {(page === 'models' || page === 'datasets') && <section className="st-panel"><header><h2>{page === 'models' ? '本地模型' : '本地数据集'}</h2><button onClick={() => navigate('environment')}>设置资源目录</button></header><Error text={assets[`${page}_error`] || ''} />{!assets[page].length ? <Empty>目录内暂无可识别资源。请在设备与环境中设置下载目录。</Empty> : <div className="st-assets">{assets[page].map(a => <article key={a.path}><div><h3>{a.name}</h3><p>{a.path}</p></div><span className="st-tag">{a.format}</span>{a.size_gb !== undefined && <span>{a.size_gb} GB</span>}</article>)}</div>}</section>}
    {page === 'tasks' && <div className="st-stack">{selected ? <><button onClick={() => setSelected('')}>返回任务列表</button><TaskPanel key={selected} id={selected} /></> : <TaskHistory onSelect={setSelected} />}</div>}
    {(page === 'evaluation' || page === 'quantization') && <section className="st-reserved" aria-label={`${titles[page]}页面，暂未实现`} />}
    </div></main></div>;
}
