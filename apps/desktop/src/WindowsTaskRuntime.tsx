import { useEffect, useRef, useState } from 'react';
import runtimes from '../../windows-ui/hf/task-runtimes.json';
import { errorMessage } from './api';
import { Button, ErrorNotice } from './ui';
import type { Kind } from './types';
import type { RuntimeStatus } from './windowsWorkbenchApi';

export function taskLibraries(kind: Kind, pipeline?: string) {
  return runtimes[pipeline && runtimes.languageAudioPipelines.includes(pipeline) ? 'text' : kind];
}

type Preparation = { id: string; request: number; pending: boolean; status?: RuntimeStatus; error?: string };

export function useTaskRuntime(onInstalled: () => void) {
  const [state, setState] = useState<Preparation | null>(null);
  const sequence = useRef(0), pending = useRef(''), refresh = useRef(onInstalled);
  refresh.current = onInstalled;
  useEffect(() => () => { sequence.current++; pending.current = ''; }, []);

  async function prepare(id: string) {
    const runtime = window.ailabHF?.runtime;
    if (!runtime || pending.current === id) return;
    const request = ++sequence.current;
    pending.current = id;
    setState({ id, request, pending: true });
    try {
      let status = await runtime('status');
      if (request !== sequence.current) return;
      const component = status.components.find(item => item.id === id);
      if (!component) throw Error('无法识别此任务需要的运行库。');
      if (!component.installed) {
        if (status.nextRoot !== status.root) throw Error('运行库目录已更改，请重新打开 AiLab 后继续。');
        setState({ id, request, pending: true, status });
        status = await runtime('prepare', id);
        refresh.current();
      }
      if (request === sequence.current) setState({ id, request, pending: false, status });
    } catch (e) {
      if (request === sequence.current) setState(previous => ({ ...previous, id, request, pending: false, error: errorMessage(e) }));
    } finally {
      if (request === sequence.current) pending.current = '';
    }
  }
  const polling = state?.pending ? state.request : null;
  useEffect(() => {
    const runtime = window.ailabHF?.runtime;
    if (polling === null || !runtime) return;
    let live = true, timer: number;
    async function poll() {
      try {
        const status = await runtime!('status');
        if (live) setState(prev => prev?.request === polling && prev.pending ? { ...prev, status } : prev);
      } catch { /* The prepare request reports its own terminal error. */ }
      if (live) timer = window.setTimeout(poll, 500);
    }
    timer = window.setTimeout(poll, 150);
    return () => { live = false; window.clearTimeout(timer); };
  }, [polling]);
  async function cancel() {
    if (!state) return;
    const request = state.request;
    try { await window.ailabHF?.runtime?.('cancel', state.id); }
    catch (e) { setState(prev => prev?.request === request ? { ...prev, error: errorMessage(e) } : prev); }
  }
  return { state, prepare, cancel };
}

export type TaskRuntime = ReturnType<typeof useTaskRuntime>;

export function TaskRuntimeNotice({ runtime, kind, pipeline }: { runtime: TaskRuntime; kind: Kind; pipeline?: string }) {
  const { state } = runtime;
  const group = taskLibraries(kind, pipeline);
  if (!state || (state.id !== group.standard && state.id !== group.cuda)) return null;
  const status = state.status, component = status?.components.find(item => item.id === state.id);
  const ownDownload = status?.busy && status.id === state.id;
  const percent = status?.total ? Math.floor(100 * (status.received || 0) / status.total) : null;
  let detail = '正在检查本机运行库…';
  if (component?.installed) detail = '已就绪，可在本机使用。';
  else if (state.pending && ownDownload) detail = status.phase + (percent === null ? '' : ` · ${percent}%`);
  else if (state.pending && status?.busy) detail = '等待当前运行库准备完成后自动下载。';
  else if (state.pending && component) detail = '正在准备下载…';
  return <section className="task-runtime" aria-label="试用运行库">
    <strong>{component?.label || '试用运行库'}</strong>
    {!state.error && <span role="status">{detail}</span>}
    {!!status?.files?.length && <details open={state.pending}><summary>下载明细</summary>
      <ul>{status.files.map((file, index) => <li key={index}>
        {file.component} · {file.name} · {file.status}
        {file.total > 0 && ` · ${(file.received / 1024 ** 2).toFixed(1)} / ${(file.total / 1024 ** 2).toFixed(1)} MiB`}
      </li>)}</ul>
    </details>}
    <ErrorNotice message={state.error || ''} />
    {state.error && !state.pending && <Button onClick={() => void runtime.prepare(state.id)}>重试准备运行库</Button>}
    {state.pending && ownDownload && <Button onClick={() => void runtime.cancel()}>取消下载</Button>}
    {!state.pending && !state.error && state.id === group.standard &&
      status?.components.some(item => item.id === group.cuda && !item.installed) &&
      <Button onClick={() => void runtime.prepare(group.cuda)}>准备 NVIDIA CUDA 加速库</Button>}
  </section>;
}
