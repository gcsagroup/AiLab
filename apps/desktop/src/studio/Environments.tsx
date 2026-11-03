import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { errorMessage } from '../api';
import { Error, Field, NumberField, PathField, request } from './common';
import TaskPanel from './TaskPanel';
import type { Job, Status } from './types';

export default function Environments({ status, refresh }: { status: Status; refresh: () => void }) {
  const [section, setSection] = useState('device');
  const [environmentPath, setEnvironmentPath] = useState(status.environment_dir || '');
  const [environmentSaved, setEnvironmentSaved] = useState(false);
  useEffect(() => { setEnvironmentPath(status.environment_dir || ''); setPaths(status.paths); }, [status.environment_dir, status.paths]);
  const [accelerator, setAccelerator] = useState(status.hardware.device === 'mps' ? 'metal' : status.hardware.device);
  const [paths, setPaths] = useState(status.paths); const [job, setJob] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false);
  const [limit, setLimit] = useState(1); const [settingsSaved, setSettingsSaved] = useState(false);
  useEffect(() => { void request<{ max_concurrent_tasks: number }>('GET', '/settings').then(v => setLimit(v.max_concurrent_tasks)).catch(e => setError(errorMessage(e))); }, []);
  async function install(id: string) { setBusy(true); setError(''); try { const j = await request<Job>('POST', `/runtimes/${id}/install`, { accelerator }); setJob(j.id); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  const h = status.hardware;
  const info = [
    ['设备名称', h.hostname || '未识别'], ['操作系统', `${h.os} ${h.os_release || ''} · ${h.arch}`],
    ['系统版本', h.os_version || '未识别'], ['处理器', h.cpu_name || '未识别'],
    ['CPU 核心', `${h.cpu_physical_cores ?? '—'} 核 / ${h.cpu_logical_cores ?? '—'} 线程`],
    ['内存容量', `${h.memory_gb} GB`], ['可用内存', h.memory_available_gb !== undefined ? `${h.memory_available_gb} GB` : '未识别'],
    ['可用加速设备', h.device === 'cuda' ? 'NVIDIA CUDA' : h.device === 'mps' ? 'Apple Metal / MPS' : 'CPU'],
    ...h.gpus.flatMap((g, i) => [[`GPU ${i + 1}`, g.name], ['显存容量', `${g.memory_gb} GB`], ['GPU 驱动', g.driver_version || '未识别']]),
    ['环境所在磁盘', h.disk_total_gb !== undefined ? `${h.disk_free_gb} GB 可用 / ${h.disk_total_gb} GB` : '未识别'],
    ['控制服务 Python', h.python_version || '未识别'],
  ];
  return <div className="st-stack"><div className="st-tabs st-settings-tabs" role="tablist" aria-label="设置分类">{[['device','本机信息'],['environments','环境管理'],['resources','资源目录'],['tasks','任务设置']].map(([key,label]) => <button key={key} role="tab" aria-selected={section === key} className={section === key ? 'active' : ''} onClick={() => setSection(key)}>{label}</button>)}</div>
    <Error text={error} />
    {section === 'device' && <section aria-label="本机信息" className="st-panel st-device-info"><dl className="st-device-grid">{info.map(([label,value],i) => <div key={`${label}-${i}`}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section>}
    {section === 'tasks' && <section className="st-panel"><header><h2>任务设置</h2></header><form onSubmit={async e => { e.preventDefault(); setError(''); try { await request('POST', '/settings', { max_concurrent_tasks: limit }); setSettingsSaved(true); } catch (e) { setError(errorMessage(e)); } }}><NumberField title="同时运行的任务数" value={limit} min={1} max={16} onChange={v => { setLimit(v); setSettingsSaved(false); }} /><p className="st-note">训练、消融和推理共用队列，默认同时运行 1 个任务。暂停中的运行任务保留内存并占用名额；排队任务暂停后不会启动。降低上限将在现有任务结束后生效。</p><footer>{settingsSaved && <small role="status">设置已保存</small>}<button className="st-primary">保存任务设置</button></footer></form></section>}
    {section === 'environments' && <section className="st-panel"><header><h2>运行环境</h2><span className="st-tag">按需安装</span></header><form onSubmit={async e => { e.preventDefault(); setBusy(true); setError(''); setEnvironmentSaved(false); try { const value = await request<{environment_dir:string}>('POST', '/environment', {path:environmentPath}); setEnvironmentPath(value.environment_dir); setEnvironmentSaved(true); refresh(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}><PathField title="环境安装目录" value={environmentPath} onChange={value => { setEnvironmentPath(value); setEnvironmentSaved(false); }} directory /><p className="st-note">更改目录不会搬迁已有环境，模型和数据集目录保持原设置。</p><footer>{environmentSaved && <small role="status">环境目录已保存</small>}<button type="button" disabled={busy} onClick={() => { setEnvironmentPath(status.default_environment_dir || ''); setEnvironmentSaved(false); }}>恢复默认目录</button><button className="st-primary" disabled={busy}>保存环境目录</button></footer></form><Field title="安装加速后端"><select value={accelerator} onChange={e => setAccelerator(e.target.value)}><option value="cpu">CPU</option>{status.hardware.device === 'cuda' && <option value="cuda">NVIDIA CUDA</option>}{status.hardware.os === 'Darwin' && <option value="metal">Apple Metal / MPS</option>}</select></Field>
      <div className="st-runtimes">{status.runtimes.map(r => <article key={r.id}><div><h3>{r.name}</h3><p>{r.description}</p>{r.installed ? <details><summary>已安装 · {r.installed.accelerator} · {r.installed.version.slice(0, 8)}</summary><pre className="st-code">{r.installed.resolved}</pre><small>{r.installed.path}</small></details> : <small>未安装</small>}{!r.supported && <p className="st-note">{r.reason}</p>}</div><button disabled={busy || !r.supported} onClick={() => void install(r.id)}><Download size={15} />{r.installed ? '更新环境' : '安装'}</button></article>)}</div><p className="st-note">更新创建新版本，检查成功后切换。训练、HF 消融分别隔离；安装 vLLM 后可供推理和消融复用。llama.cpp GPU 构建需要本机 C/C++ 工具链。</p></section>}
    {section === 'resources' && <section className="st-panel"><header><h2>资源文件夹</h2></header><form onSubmit={async e => { e.preventDefault(); setSaved(false); setError(''); try { setPaths(await request<Status['paths']>('POST', '/paths', { models: paths.models, datasets: paths.datasets })); setSaved(true); refresh(); } catch (e) { setError(errorMessage(e)); } }}><PathField title="模型下载目录" value={paths.models} onChange={models => setPaths({ ...paths, models })} /><PathField title="数据集下载目录" value={paths.datasets} onChange={datasets => setPaths({ ...paths, datasets })} /><footer>{saved && <small role="status">目录已保存</small>}<button className="st-primary">保存目录</button></footer></form></section>}
    {job && section === 'environments' && <TaskPanel key={job} id={job} onDone={refresh} />}
  </div>;
}
