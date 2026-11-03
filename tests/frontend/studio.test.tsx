import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import StudioApp from '../../apps/desktop/src/studio/StudioApp';
import TaskPanel, { LossChart } from '../../apps/desktop/src/studio/TaskPanel';
import Training from '../../apps/desktop/src/studio/Training';
import Ablation from '../../apps/desktop/src/studio/Ablation';
import Environments from '../../apps/desktop/src/studio/Environments';
import Inference from '../../apps/desktop/src/studio/Inference';
import Library from '../../apps/desktop/src/studio/Library';
import ModelStatus from '../../apps/desktop/src/studio/ModelStatus';
import GgufModelSelect from '../../apps/desktop/src/studio/GgufModelSelect';
import ChatAnswer from '../../apps/desktop/src/studio/ChatAnswer';
import type { Job } from '../../apps/desktop/src/studio/types';

const mockApi = vi.hoisted(() => vi.fn());
const mockPicker = vi.hoisted(() => vi.fn());
vi.mock('../../apps/desktop/src/api', () => ({ api: mockApi, canPickFile: () => false, errorMessage: (e: unknown) => String(e), pickStudioPath: mockPicker }));
vi.mock('../../apps/desktop/src/ExitPreparation', () => ({ useExitPreparation: () => ({ preparing: false, error: '' }) }));
const status = { hardware: { os: 'Windows', arch: 'AMD64', memory_gb: 32, device: 'cpu', gpus: [] }, paths: { models: '', datasets: '' }, runtimes: [] };
beforeEach(() => {
  localStorage.clear(); mockApi.mockReset(); mockPicker.mockReset();
  mockApi.mockImplementation(async (_method: string, path: string, body: unknown) => {
    if (path.endsWith('/paths')) return body;
    if (path.endsWith('/settings')) return { max_concurrent_tasks: 1 };
    if (path.endsWith('/status')) return status;
    if (path.endsWith('/assets')) return { models: [], datasets: [] };
    if (path.endsWith('/ablation/template')) return { fields: { seed: 42, 'model.backend': 'hf', 'model.dtype_fallback_order':['bfloat16'], 'kl.target':0.1, 'steering.vector_method':'mean', 'detection.llm_judge': false }, reference: '[model]\nmax_model_len=2048', advanced: '' };
    return { items: [] };
  });
});
afterEach(cleanup);

describe('Studio UI', () => {
  it('retains a separate last successful preview for each media tab during this session', async () => {
    let completedWorkflow = 't2i';
    mockApi.mockImplementation(async (_method: string, path: string) => {
      if (path.includes('/materials/')) return new Promise(() => {});
      if (path.includes('/events')) return { items:[] };
      if (path.includes('/jobs/')) return { id:completedWorkflow, kind:'inference', state:'succeeded', config:{workflow:completedWorkflow}, result:{material_id:completedWorkflow + '-preview'} };
      if (path.endsWith('/llm/status')) return { phase:'unloaded' };
      return { items:[] };
    });
    const assets = { models:[], datasets:[] };
    for (const workflow of ['t2i','t2v','r2v']) {
      completedWorkflow = workflow;
      localStorage.setItem('studio:inference', JSON.stringify({workflow, engine:'diffusers'}));
      localStorage.setItem('studio:inference-job', JSON.stringify({id:workflow}));
      const view = render(<Inference assets={assets} />);
      await screen.findByText('已保存到素材库');
      view.unmount();
    }
    localStorage.setItem('studio:inference-job', JSON.stringify({id:''}));
    render(<Inference assets={assets} />);
    for (const [tab, workflow] of [['文生图 T2I','t2i'],['文生视频 T2V','t2v'],['参考图生视频 R2V','r2v'],['文生图 T2I','t2i']]) {
      fireEvent.click(screen.getByRole('tab', {name:'LLM 对话'}));
      mockApi.mockClear();
      fireEvent.click(screen.getByRole('tab', {name:tab}));
      await waitFor(() => expect(mockApi).toHaveBeenCalledWith('GET', `/studio/materials/${workflow}-preview/content?offset=0&length=524288`, undefined));
      expect(screen.getByText('已保存到素材库')).toBeInTheDocument();
    }
  });
  it('loads and sends with a GGUF selected outside the model library', async () => {
    const external = 'D:/external/model.gguf';
    mockPicker.mockResolvedValue(external);
    const job = { id:'external', kind:'inference', state:'succeeded', config:{ workflow:'chat', action:'load' }, result:null };
    mockApi.mockImplementation(async (method: string, path: string, body: object) => {
      if (path.endsWith('/llm/status')) return { phase:'unloaded' };
      if (path.endsWith('/llm/capabilities')) return { vision:false };
      if (path.endsWith('/conversations')) return method === 'GET' ? { items:[] } : { ...body, id:'conversation' };
      if (path.endsWith('/recommend')) return { config:{}, notes:[] };
      if (path.includes('/events')) return { items:[] };
      return job;
    });
    render(<Inference assets={{ models:[], datasets:[] }} />);
    expect(screen.queryByRole('button', { name:'选择模型', exact:true })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'__other__' } });
    await waitFor(() => expect(screen.getByLabelText('本地模型')).toHaveValue(external));
    fireEvent.click(screen.getByRole('button', { name:'加载模型', exact:true }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/llm/load', expect.objectContaining({ model:external, action:'load', conversation_id:null })));
    await waitFor(() => expect(screen.getByRole('button', { name:'发送', exact:true })).toBeEnabled());
    fireEvent.change(screen.getByLabelText('消息'), { target:{ value:'Hello' } });
    fireEvent.click(screen.getByRole('button', { name:'发送', exact:true }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/inference', expect.objectContaining({ model:external, messages:[{role:'user',content:'Hello'}] })));
  });
  it('places the environment collection after datasets and opens the specified console separately', async () => {
    render(<StudioApp />);
    await screen.findByText('Windows · 已连接');
    const labels = Array.from(screen.getByRole('navigation',{name:'主导航'}).querySelectorAll('button')).map(b => b.textContent);
    expect(labels.indexOf('环境集')).toBe(labels.indexOf('数据集')+1);
    fireEvent.click(screen.getByRole('button',{name:'环境集',exact:true}));
    const link = screen.getByRole('link',{name:'打开控制界面'});
    expect(link).toHaveAttribute('href','http://192.168.9.101:8090/');
    expect(link).toHaveAttribute('target','_blank');
  });
  it('remembers edited inference parameters without replacing them on re-entry', async () => {
    localStorage.setItem('studio:inference', JSON.stringify({ model:'D:/one.gguf', engine:'llama', workflow:'chat', temperature:0.3, context_length:1024 }));
    mockApi.mockImplementation(async (_m: string, path: string) => {
      if (path.endsWith('/recommend')) return { config:{ temperature:0.7, context_length:4096 }, notes:['不需要展示的提示'] };
      if (path.endsWith('/llm/status')) return { phase:'loaded', model:'D:/one.gguf', expires_at:Date.now()/1000+180 };
      return { items:[] };
    });
    const assets = { models:[{ path:'D:/one.gguf', name:'One', format:'gguf' }], datasets:[] };
    const view = render(<Inference assets={assets} />);
    fireEvent.change(screen.getByLabelText('Temperature'), { target:{value:'0.4'} });
    view.unmount(); render(<Inference assets={assets} />);
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 650)); });
    expect(screen.getByLabelText('Temperature')).toHaveValue(0.4);
    expect(screen.getByLabelText('上下文长度')).toHaveValue(1024);
    expect(mockApi.mock.calls.some(c => c[1] === '/studio/recommend')).toBe(false);
    expect(screen.queryByText(/空闲约|发送消息时自动加载|采样参数是通用起点/)).not.toBeInTheDocument();
  });
  it('keeps streaming callbacks without displaying chat results or logs', async () => {
    const onStream = vi.fn(); const onDone = vi.fn();
    mockApi.mockImplementation(async (_m: string, path: string) => path.includes('/events') ? { items:[{seq:1,type:'token',text:'答案',channel:'final'}] } : {id:'chat',kind:'inference',state:'succeeded',config:{workflow:'chat'},result:{text:'答案'},output_dir:'local'});
    render(<TaskPanel id="chat" compact onStream={onStream} onDone={onDone} />);
    await waitFor(() => expect(onStream).toHaveBeenCalledWith('答案',''));
    expect(onDone).toHaveBeenCalled();
    expect(screen.queryByText('运行结果')).not.toBeInTheDocument();
    expect(screen.queryByText('运行日志')).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'导出记录'})).not.toBeInTheDocument();
  });
  it('expands live reasoning and collapses it when the final answer starts', async () => {
    const view = render(<ChatAnswer text="" reasoning="检查条件" streaming />);
    expect(screen.getByText('正在思考…').closest('details')).toHaveAttribute('open');
    view.rerender(<ChatAnswer text="正式回答" reasoning="检查条件" streaming />);
    await waitFor(() => expect(screen.getByText('思考过程').closest('details')).not.toHaveAttribute('open'));
    expect(screen.getByText('正式回答')).toBeVisible();
    view.rerender(<ChatAnswer text="" reasoning="达到长度上限" />);
    expect(screen.getByText('思考过程').closest('details')).not.toHaveAttribute('open');
  });
  it('uses Enter to send, preserves Shift/IME Enter, and disables unsupported images', async () => {
    const job = { id:'keyboard', kind:'inference', state:'succeeded', config:{ workflow:'chat' }, result:null };
    mockApi.mockImplementation(async (_m: string, path: string, body: object) => {
      if (path.endsWith('/llm/status')) return { phase:'loaded', model:'D:/one.gguf', idle_timeout_seconds:300 };
      if (path.endsWith('/llm/capabilities')) return { vision:false };
      if (path.endsWith('/conversations')) return _m === 'GET' ? { items:[] } : { ...body, id:'chat' };
      if (path.endsWith('/recommend')) return { config:{}, notes:[] };
      if (path.includes('/events')) return { items:[] };
      return job;
    });
    render(<Inference assets={{ models:[{ path:'D:/one.gguf', name:'One', format:'gguf' }], datasets:[] }} />);
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'D:/one.gguf' } });
    await waitFor(() => expect(screen.getByRole('button', { name:'卸载模型' })).toBeEnabled());
    expect(screen.getByRole('button', { name:'图片', exact:true })).toBeDisabled();
    const input = screen.getByLabelText('消息');
    fireEvent.change(input, { target:{ value:'你好' } });
    fireEvent.keyDown(input, { key:'Enter', shiftKey:true });
    fireEvent.keyDown(input, { key:'Enter', isComposing:true, keyCode:229 });
    expect(mockApi.mock.calls.some(c => c[1] === '/studio/inference')).toBe(false);
    fireEvent.keyDown(input, { key:'Enter' });
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/inference', expect.objectContaining({ messages:[{ role:'user', content:'你好' }] })));
  });
  it('explains empty messages instead of silently disabling Send', async () => {
    mockApi.mockImplementation(async (_m: string, path: string) => path.endsWith('/recommend') ? { config:{}, notes:[] } : { items:[] });
    render(<Inference assets={{ models:[{ path:'D:/one.gguf', name:'One', format:'gguf' }], datasets:[] }} />);
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'D:/one.gguf' } });
    const send = screen.getByRole('button', { name:'发送', exact:true });
    expect(send).toBeEnabled();
    fireEvent.click(send);
    expect(screen.getByRole('alert')).toHaveTextContent('请在消息框输入内容');
    expect(screen.getByLabelText('消息')).toHaveFocus();
    expect(mockApi.mock.calls.some(call => call[0] === 'POST' && call[1] === '/studio/inference')).toBe(false);
    fireEvent.change(screen.getByLabelText('消息'), { target:{ value:'你好' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(send).toBeEnabled();
  });
  it('lists downloaded GGUFs, opens the native picker and preserves selection on cancel', async () => {
    const change = vi.fn();
    render(<GgufModelSelect value="D:/one.gguf" items={[{ path:'D:/one.gguf', name:'One', format:'gguf' }, { path:'D:/hf', name:'HF', format:'safetensors' }]} onChange={change} />);
    expect(screen.getByRole('option', { name:'One' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name:'HF' })).not.toBeInTheDocument();
    mockPicker.mockResolvedValueOnce(null);
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'__other__' } });
    await waitFor(() => expect(mockPicker).toHaveBeenCalledWith(false, true));
    await waitFor(() => expect(screen.getByLabelText('本地模型')).toBeEnabled());
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByLabelText('本地模型')).toHaveValue('D:/one.gguf');
    mockPicker.mockResolvedValueOnce('D:/other.gguf');
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'__other__' } });
    await waitFor(() => expect(change).toHaveBeenCalledWith('D:/other.gguf'));
  });
  it('keeps the chosen GGUF across workflow switches and enables sending', async () => {
    mockApi.mockImplementation(async (_m: string, path: string) => path.endsWith('/recommend') ? { config:{}, notes:[] } : { items:[] });
    render(<Inference assets={{ models:[{ path:'D:/one.gguf', name:'One', format:'gguf' }], datasets:[] }} />);
    fireEvent.change(screen.getByLabelText('消息'), { target:{ value:'Hello' } });
    fireEvent.click(screen.getByRole('button', { name:'发送', exact:true }));
    expect(screen.getByRole('alert')).toHaveTextContent('请先在左侧选择本地模型');
    expect(mockApi.mock.calls.some(call => call[0] === 'POST' && call[1] === '/studio/inference')).toBe(false);
    fireEvent.change(screen.getByLabelText('本地模型'), { target:{ value:'D:/one.gguf' } });
    expect(screen.getByRole('button', { name:'发送', exact:true })).toBeEnabled();
    fireEvent.click(screen.getByRole('tab', { name:'文生图 T2I' }));
    fireEvent.click(screen.getByRole('tab', { name:'LLM 对话' }));
    expect(screen.getByLabelText('本地模型')).toHaveValue('D:/one.gguf');
    expect(screen.getByRole('button', { name:'发送', exact:true })).toBeEnabled();
  });
  it('defaults CPU offload on in media workflows and allows disabling it', async () => {
    render(<Inference assets={{ models: [], datasets: [] }} />);
    fireEvent.click(screen.getByRole('tab', { name: '文生图 T2I' }));
    const toggle = screen.getByRole('checkbox', { name: 'CPU offload · 节省显存' });
    expect(toggle).toBeChecked(); fireEvent.click(toggle); expect(toggle).not.toBeChecked();
    expect(screen.getByRole('status')).toHaveTextContent('模型未加载');
  });
  it('distinguishes loading, generating, unloading and confirmed release', () => {
    const job: Job = { id:'status', kind:'inference', runtime:'llama', state:'running', created_at:0, output_dir:'', result:null, error:null, config:{}, model_state:'loading' };
    const view = render(<ModelStatus job={job} />);
    expect(screen.getByRole('status')).toHaveTextContent('正在加载模型');
    view.rerender(<ModelStatus job={{ ...job, model_state:'generating' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('模型已加载');
    view.rerender(<ModelStatus job={{ ...job, model_state:'unloading' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('正在卸载模型');
    view.rerender(<ModelStatus job={{ ...job, state:'succeeded', model_state:'unloaded' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('模型已卸载');
  });
  it('long press selects a card without opening it and batch deletion retains failed items', async () => {
    vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} });
    vi.stubGlobal('PointerEvent', MouseEvent);
    const oldModal = HTMLDialogElement.prototype.showModal; HTMLDialogElement.prototype.showModal = function() { this.setAttribute('open',''); };
    mockApi.mockImplementation(async (method: string, path: string) => {
      if(method === 'DELETE') { if(path.endsWith('/movie')) throw new Error('素材正被任务使用'); return {id:'photo'}; }
      return {items:[{id:'photo',name:'photo.png',kind:'image',source:'imported',created_at:1,size:10,parameters:{}},{id:'movie',name:'movie.mp4',kind:'video',source:'generated',created_at:1,size:10,parameters:{}}]};
    });
    try {
      render(<Library />);
      const card = await screen.findByRole('button', {name:'预览 photo.png'});
      fireEvent.pointerDown(card,{button:0,clientX:10,clientY:10});
      await act(async () => { await new Promise(resolve => setTimeout(resolve,550)); });
      fireEvent.pointerUp(card); fireEvent.click(card);
      expect(screen.getByRole('button',{name:'选择 photo.png'})).toHaveAttribute('aria-pressed','true');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button',{name:'选择 movie.mp4'}));
      expect(screen.getByText('已选 2 项')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button',{name:'删除所选'}));
      fireEvent.click(screen.getByText('确认删除'));
      await waitFor(() => expect(screen.queryByRole('button',{name:'选择 photo.png'})).not.toBeInTheDocument());
      expect(screen.getByRole('button',{name:'选择 movie.mp4'})).toHaveAttribute('aria-pressed','true');
      expect(screen.getByRole('alert')).toHaveTextContent('素材正被任务使用');
    } finally { HTMLDialogElement.prototype.showModal = oldModal; vi.unstubAllGlobals(); }
  });
  it('filters preview cards without a duplicate library heading', async () => {
    vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} });
    mockApi.mockResolvedValue({ items: [{ id:'photo', name:'photo.png', kind:'image', source:'imported', created_at:1, size:10, parameters:{} }, { id:'movie', name:'movie.mp4', kind:'video', source:'generated', created_at:2, size:10, parameters:{} }] });
    try {
      render(<Library />);
      await screen.findByRole('button', { name:'预览 photo.png' });
      expect(screen.queryByRole('heading', { name:'素材库' })).not.toBeInTheDocument();
      fireEvent.change(screen.getByLabelText('素材类型'), { target:{ value:'video' } });
      expect(screen.queryByRole('button', { name:'预览 photo.png' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name:'预览 movie.mp4' })).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText('素材来源'), { target:{ value:'imported' } });
      expect(screen.getByText('没有符合筛选条件的素材')).toBeInTheDocument();
    } finally { vi.unstubAllGlobals(); }
  });
  it('expands laboratory and leaves reserved pages without fake execution buttons', async () => {
    render(<StudioApp />);
    await screen.findByText('Windows · 已连接');
    fireEvent.click(screen.getByRole('button', { name: '评测', exact: true }));
    expect(screen.getByLabelText('评测页面，暂未实现')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '开始评测' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '模型实验室' }));
    expect(screen.queryByRole('button', { name: '训练', exact: true })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '模型测试' })).toBeInTheDocument();
  });
  it('submits local SFT paths and editable parameters to the backend', async () => {
    mockApi.mockImplementation(async (_m: string, path: string) => path.endsWith('/sft') ? { id: 'train', state: 'queued' } : path.includes('/events') ? { items: [] } : { id: 'train', kind: 'sft', state: 'succeeded', result: null });
    render(<Training assets={{ models: [], datasets: [] }} />);
    fireEvent.change(screen.getByLabelText('Safetensors 模型目录'), { target: { value: 'D:\\Models\\base' } });
    fireEvent.change(screen.getByLabelText('数据集文件或目录'), { target: { value: 'D:\\Data\\train.jsonl' } });
    fireEvent.change(screen.getByLabelText('学习率'), { target: { value: '0.0001' } });
    fireEvent.click(screen.getByRole('button', { name: '开始训练' }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/sft', expect.objectContaining({ model: 'D:\\Models\\base', learning_rate: .0001, loss_scope: 'assistant', method: 'lora' })));
  });
  it('edits all supplied basic TOML fields and preserves advanced TOML', async () => {
    render(<Ablation assets={{ models: [], datasets: [] }} />);
    await screen.findByLabelText('随机种子');
    expect(screen.getByLabelText('随机种子').closest('fieldset')).toBe(screen.getByLabelText('推理后端').closest('fieldset'));
    expect(screen.getByLabelText('KL 目标').closest('fieldset')).toBe(screen.getByLabelText('方向向量方法').closest('fieldset'));
    expect(screen.queryByText('按勾选顺序尝试；Auto 不指定精度')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('高级 TOML 配置'));
    fireEvent.click(screen.getByRole('button', { name: '载入 abliterix_all.toml 参考' }));
    expect(screen.getByLabelText('附加 TOML')).toHaveValue('[model]\nmax_model_len=2048');
    expect(screen.getByLabelText('推理后端')).toHaveValue('hf');
    expect(screen.getByRole('option', { name: 'vLLM（未安装）' })).toBeDisabled();
  });
  it('renders measured training and validation loss rather than placeholder data', () => {
    render(<LossChart events={[{ seq: 1, type: 'metric', step: 1, loss: 2.3 }, { seq: 2, type: 'metric', step: 2, eval_loss: 1.8 }]} />);
    expect(screen.getByRole('img', { name: '训练与验证损失随步数变化曲线' })).toBeInTheDocument();
    expect(screen.getByText('步数 2')).toBeInTheDocument();
  });
  it('saves resource paths without leaking persistence metadata into the request', async () => {
    render(<Environments status={{ ...status, paths: { ...status.paths, id: 'paths' } } as typeof status} refresh={() => {}} />);
    expect(screen.getByRole('tab', { name:'本机信息' })).toHaveAttribute('aria-selected','true');
    expect(screen.queryByRole('button', { name:'刷新' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name:'资源目录' }));
    fireEvent.change(screen.getByLabelText('模型下载目录'), { target: { value: 'D:\\Models' } });
    fireEvent.change(screen.getByLabelText('数据集下载目录'), { target: { value: 'D:\\Data' } });
    fireEvent.click(screen.getByRole('button', { name: '保存目录' }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/paths', { models: 'D:\\Models', datasets: 'D:\\Data' }));
    expect(await screen.findByRole('status')).toHaveTextContent('目录已保存');
  });
  it('saves a custom environment directory from its own settings category', async () => {
    mockApi.mockImplementation(async (_m: string, path: string) => path.endsWith('/environment') ? {environment_dir:'D:/custom-env'} : {max_concurrent_tasks:1});
    const refresh = vi.fn();
    render(<Environments status={{...status, environment_dir:'D:/app/environment', default_environment_dir:'D:/app/environment'}} refresh={refresh} />);
    fireEvent.click(screen.getByRole('tab', {name:'环境管理'}));
    fireEvent.change(screen.getByLabelText('环境安装目录'), {target:{value:'D:/custom-env'}});
    fireEvent.click(screen.getByRole('button', {name:'保存环境目录'}));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST','/studio/environment',{path:'D:/custom-env'}));
    expect(await screen.findByRole('status')).toHaveTextContent('环境目录已保存');
    expect(refresh).toHaveBeenCalled();
  });
  it('loads a saved conversation and submits its history with the next message', async () => {
    const session = { id: 'chat', title: '已有会话', model: 'D:/models/local.gguf', engine: 'llama', messages: [{ role: 'user', content: '上一条问题' }, { role: 'assistant', content: '上一条回答' }] };
    const job = { id: 'inference', kind: 'inference', state: 'failed', config: { workflow: 'chat' }, result: null };
    mockApi.mockImplementation(async (method: string, path: string, body: unknown) => {
      if (path === '/studio/conversations') return { items: [{ id: session.id, title: session.title }] };
      if (path === '/studio/conversations/chat') return method === 'GET' ? session : { ...session, ...(body as object) };
      if (path === '/studio/recommend') return { config: {}, notes: [] };
      if (path.includes('/events')) return { items: [] };
      return job;
    });
    render(<Inference assets={{ models: [], datasets: [] }} />);
    expect(screen.queryByLabelText('会话')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('本地模型'), { target: { value: session.model } });
    await screen.findByText('上一条回答');
    fireEvent.change(screen.getByLabelText('消息'), { target: { value: '继续回答' } });
    fireEvent.click(screen.getByRole('button', { name: '发送' }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith('POST', '/studio/inference', expect.objectContaining({
      conversation_id: 'chat', messages: [...session.messages, { role: 'user', content: '继续回答' }],
    })));
  });
  it('reports actual sampling steps from compact polling without displaying logs', async () => {
    const progress = vi.fn();
    const job = {id:'media-progress',kind:'inference',state:'succeeded',config:{workflow:'t2i'}};
    mockApi.mockImplementation(async (_method:string,path:string) => path.includes('/events')
      ? {items:[{seq:1,type:'progress',step:3,total:8},{seq:2,type:'progress',step:8,total:8}]}
      : job);
    render(<TaskPanel id="media-progress" compact onProgress={progress} />);
    await waitFor(() => expect(progress).toHaveBeenLastCalledWith(8,8));
    expect(progress).toHaveBeenCalledWith(3,8);
    expect(screen.queryByLabelText('运行日志')).not.toBeInTheDocument();
  });

});
