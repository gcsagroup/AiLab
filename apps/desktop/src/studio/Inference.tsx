import { useEffect, useRef, useState } from 'react';
import { Play, Send, ImagePlus, Plus, SlidersHorizontal, X } from 'lucide-react';
import { errorMessage } from '../api';
import { Error, Field, NumberField, PathField, request, uploadImage, useDraft } from './common';
import TaskPanel from './TaskPanel';
import ModelStatus from './ModelStatus';
import GgufModelSelect from './GgufModelSelect';
import ChatAnswer from './ChatAnswer';
import Library, { MediaPreview, importMaterial } from './Library';
import { terminal, type Assets, type Conversation, type Job, type Message, type Material, type LlmStatus } from './types';


// Keep only material IDs for this application session; blobs remain owned by MediaPreview.
const sessionPreviews: Record<string, string> = {};

const initial = { model: '', engine: 'llama', workflow: 'chat', media_format: 'diffusers', comfy_architecture: 'anima', text_encoder: '', text_encoder_2: '', vae: '', clip_vision: '', device: 'auto', context_length: 4096, max_tokens: 512, temperature: 0.7, top_k: 40, top_p: 0.95, gpu_memory_utilization: 0.75, tensor_parallel_size: 1, gpu_layers: -1, idle_timeout_seconds: 300, cpu_offload: true, cpu_offload_gb: 4, mmproj: '', vision_handler: 'none', prompt: '', negative_prompt: '', width: 512, height: 512, steps: 25, sampler: 'euler', guidance_scale: 7, frames: 17, fps: 8, seed: 42 };

export default function Inference({ assets, refreshAssets }: { assets: Assets; refreshAssets?: () => void }) {
  const [form, set] = useDraft('inference', initial); const [message, setMessage] = useState(''); const [attachment, setAttachment] = useState(''); const [system, setSystem] = useDraft('system', { text: '' });
  const [conversation, setConversation] = useState<Conversation>();
  const [job, setJob] = useState<Job>(); const [pending, setPending] = useState(false); const [error, setError] = useState('');
  const [sampling, setSampling] = useState<{step:number;total:number}>();
  useEffect(() => { setSampling(undefined); }, [job?.id]);
  const [savedJob, setSavedJob] = useDraft('inference-job', { id: '' });
  const busy = pending || Boolean(job && !terminal(job));
  const [resident, setResident] = useState<LlmStatus>(); const [modelControlBusy, setModelControlBusy] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [vision, setVision] = useState(false); const [live, setLive] = useState({ text:'', reasoning:'' });
  const imageInput = useRef<HTMLInputElement>(null);
  const messagesView = useRef<HTMLDivElement>(null); const followOutput = useRef(true);
  useEffect(() => { followOutput.current = true; }, [job?.id]);
  useEffect(() => { const node = messagesView.current; if (node && followOutput.current) node.scrollTop = node.scrollHeight; }, [live, conversation, job?.id]);
  useEffect(() => { let alive = true; let timer: ReturnType<typeof setTimeout>;
    async function poll() { try { const value = await request<LlmStatus>('GET', '/llm/status'); if (alive && value.phase) { setResident(value); setConnectionError(''); } } catch (e) { if (alive) setConnectionError(errorMessage(e)); } finally { if (alive) timer = setTimeout(poll, 700); } }
    void poll(); return () => { alive = false; clearTimeout(timer); };
  }, []);
  useEffect(() => { let alive = true; setVision(false);
    if (form.model && form.workflow === 'chat') void request<{ vision:boolean }>('POST', '/llm/capabilities', { model:form.model, engine:form.engine, mmproj:form.mmproj, vision_handler:form.vision_handler }).then(value => { if (alive) { setVision(value.vision); if (!value.vision) setAttachment(''); } }).catch(() => { if (alive) { setVision(false); setAttachment(''); } });
    return () => { alive = false; };
  }, [form.model, form.engine, form.workflow, form.mmproj, form.vision_handler]);
  async function controlModel(action: 'load' | 'unload') {
    setModelControlBusy(true); setError('');
    try {
      if (action === 'load') { const current = await request<Job>('POST', '/llm/load', { ...form, action:'load', messages:[], conversation_id:null }); setJob(current); setSavedJob({ id:current.id }); setLive({ text:'', reasoning:'' }); }
      else setResident(await request<LlmStatus>('POST', '/llm/unload', {}));
    } catch (e) { setError(errorMessage(e)); } finally { setModelControlBusy(false); }
  }
  const recommendationSequence = useRef(0);
  const recommendedModels = useRef(new Set(form.model ? [`${form.engine}:${form.model}`] : []));
  const modelSelect = useRef<HTMLSelectElement>(null);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const [composerError, setComposerError] = useState('');
  const chatModels = useRef<Record<string, string>>({ [form.engine]: form.workflow === 'chat' ? form.model : '' });
  const chatEngine = useRef(form.workflow === 'chat' ? form.engine : 'llama');
  useEffect(() => { if (form.workflow === 'chat') { chatModels.current[form.engine] = form.model; chatEngine.current = form.engine; } }, [form.workflow, form.engine, form.model]);
  function field<K extends keyof typeof form>(key: K, value: typeof form[K]) { set({ ...form, [key]: value }); }
  const [reference, setReference] = useState<Material>(); const [libraryOpen, setLibraryOpen] = useState(false); const [previews, setPreviews] = useState<Record<string, string>>(() => ({ ...sessionPreviews }));
  const generated = previews[form.workflow] || '';
  useEffect(() => { let alive = true; void request<{ items: { id: string }[] }>('GET', '/conversations').then(async r => { if (r.items[0]) { const c = await request<Conversation>('GET', `/conversations/${r.items[0].id}`); if (alive) { setConversation(c); set(current => !current.model && current.workflow === 'chat' ? { ...current, model: c.model, engine: c.engine } : current); } } }).catch(e => { if (alive) setError(errorMessage(e)); }); return () => { alive = false; }; }, []);
  useEffect(() => {
    let disposed = false;
    if (savedJob.id) void request<Job>('GET', `/jobs/${savedJob.id}`).then(value => { if (!disposed) setJob(value); }).catch(e => { if (!disposed) setError(errorMessage(e)); });
    return () => { disposed = true; };
  }, [savedJob.id]);
  useEffect(() => {
    const sequence = ++recommendationSequence.current;
    const modelKey = `${form.engine}:${form.model}`;
    if (!form.model || (form.workflow !== 'chat' && form.media_format === 'comfyui') || recommendedModels.current.has(modelKey)) return;
    const before = { ...form };
    const timer = setTimeout(() => { void request<{ config: Partial<typeof initial>; notes: string[] }>('POST', '/recommend', { model: form.model, engine: form.engine }).then(r => {
      if (sequence === recommendationSequence.current) {
        recommendedModels.current.add(modelKey);
        set(current => {
          const unchanged = Object.fromEntries(Object.entries(r.config).filter(([key]) => current[key as keyof typeof initial] === before[key as keyof typeof initial]));
          return { ...current, ...unchanged };
        });
      }
    }).catch(e => { if (sequence === recommendationSequence.current) setError(errorMessage(e)); }); }, 500);
    return () => { clearTimeout(timer); ++recommendationSequence.current; };
  }, [form.model, form.engine, form.media_format, form.workflow]);
  function clearJob() { setJob(undefined); setSavedJob({ id: '' }); }
  function workflow(value: string) {
    if (value === form.workflow) return;
    const engine = value === 'chat' ? chatEngine.current : 'diffusers';
    const model = value === 'chat' ? chatModels.current[engine] || (conversation?.engine === engine ? conversation.model : '') : '';
    set(current => ({ ...current, workflow: value, engine, model, comfy_architecture: value === 't2i' ? (current.comfy_architecture === 'wan21' ? 'anima' : current.comfy_architecture) : value === 'chat' ? current.comfy_architecture : 'wan21' })); clearJob(); setAttachment(''); refreshAssets?.();
  }
  async function done(current: Job) {
    setJob(current);
    if (current.state === 'succeeded' && typeof current.result?.material_id === 'string' && ['t2i', 't2v', 'r2v'].includes(String(current.config.workflow))) {
      const workflow = String(current.config.workflow);
      sessionPreviews[workflow] = current.result.material_id;
      setPreviews(previous => ({ ...previous, [workflow]: current.result!.material_id as string }));
    }
    if (current.kind !== 'inference' || current.config.workflow !== 'chat') return;
    if (current.config.conversation_id) {
      try { setConversation(await request<Conversation>('GET', `/conversations/${current.config.conversation_id}`)); }
      catch (e) { setError(errorMessage(e)); }
    }
  }
  async function newConversation() {
    setPending(true); setError('');
    try { const c = await request<Conversation>('POST', '/conversations', { model: form.model, engine: form.engine, messages: [] }); setConversation(c); clearJob(); setMessage(''); setAttachment(''); }
    catch (e) { setError(errorMessage(e)); } finally { setPending(false); }
  }
  async function trimConversation(index: number) {
    if (!conversation) return;
    const payload = { title: conversation.title, model: conversation.model, engine: conversation.engine, messages: conversation.messages.slice(0, index) };
    try { setConversation(await request<Conversation>('POST', `/conversations/${conversation.id}`, payload)); }
    catch (e) { setError(errorMessage(e)); }
  }
  async function submit() {
    if (busy) return;
    setComposerError('');
    if (form.workflow === 'chat') {
      if (!form.model) { setComposerError('请先在左侧选择本地模型。'); modelSelect.current?.focus(); return; }
      if (!message.trim() && !attachment) { setComposerError('请在消息框输入内容，或添加一张图片。'); messageInput.current?.focus(); return; }
    }
    setPending(true); setError('');
    if (form.workflow !== 'chat') setSampling(undefined);
    try {
      let messages: Message[] = [];
      let conversationId: string | undefined;
      if (form.workflow === 'chat') {
        const history = (conversation?.messages || []).filter(m => m.role !== 'system');
        // A failed run may have saved its user message but no answer. Replace it on retry.
        if (history.at(-1)?.role === 'user') history.pop();
        messages = [...(system.text ? [{ role: 'system' as const, content: system.text }] : []), ...history, { role: 'user', content: message, ...(attachment ? { image: attachment } : {}) }];
        const payload = { title: conversation?.title || message.slice(0, 40) || '图片对话', model: form.model, engine: form.engine, messages };
        const saved = await request<Conversation>('POST', conversation ? `/conversations/${conversation.id}` : '/conversations', payload);
        conversationId = saved.id; setConversation(saved);
      }
      const current = await request<Job>('POST', '/inference', { ...form, messages, conversation_id: conversationId || null, image: null, material_id: form.workflow === 'r2v' ? reference?.id || null : null });
      setJob(current); setSavedJob({ id: current.id }); setLive({ text:'', reasoning:'' }); setMessage(''); if (form.workflow === 'chat') setAttachment('');
    } catch (e) { setError(errorMessage(e)); } finally { setPending(false); }
  }
  async function attach(file?: File) { if (!file || !vision) return; try { setAttachment(await uploadImage(file)); } catch (e) { setError(errorMessage(e)); } }
  const models = assets.models.filter(m => m.format === (form.engine === 'llama' ? 'gguf' : form.engine === 'vllm' ? 'safetensors' : 'diffusers'));
  return <div className="st-stack"><div className="st-tabs" role="tablist" aria-label="推理类型">{[['chat', 'LLM 对话'], ['t2i', '文生图 T2I'], ['t2v', '文生视频 T2V'], ['r2v', '参考图生视频 R2V']].map(([value, title]) => <button role="tab" aria-selected={form.workflow === value} key={value} disabled={busy} className={form.workflow === value ? 'active' : ''} onClick={() => workflow(value)}>{title}</button>)}</div>
    <ModelStatus concise={form.workflow === 'chat'} job={job} resident={form.workflow === 'chat' ? resident : undefined} controls={form.workflow === 'chat' ? <><button disabled={busy || modelControlBusy || !form.model} onClick={() => void controlModel('load')}>加载模型</button><button disabled={busy || modelControlBusy || !resident || resident.phase !== 'loaded'} onClick={() => void controlModel('unload')}>卸载模型</button></> : undefined} /><div className="st-inference"><section className="st-panel st-inference-config"><header><h2><SlidersHorizontal size={17} />运行配置</h2></header><fieldset disabled={busy}>
      {form.workflow === 'chat' && <Field title="推理引擎"><select value={form.engine} onChange={e => { set({ ...form, engine: e.target.value, model: chatModels.current[e.target.value] || '' }); }}><option value="llama">llama.cpp · GGUF</option><option value="vllm">vLLM · Safetensors</option></select></Field>}
      {form.workflow !== 'chat' && <Field title="权重格式"><select value={form.media_format} onChange={e => set(current => ({...current, media_format:e.target.value, model:''}))}><option value="diffusers">Diffusers 模型目录</option><option value="comfyui">ComfyUI 分离权重</option></select></Field>}
      {form.workflow !== 'chat' && form.media_format === 'comfyui' ? <><Field title="模型架构"><select value={form.comfy_architecture} onChange={e => field('comfy_architecture',e.target.value)}>{(form.workflow === 't2i' ? [['anima','Anima'],['sd15','Stable Diffusion 1.5'],['sdxl','SDXL'],['flux','FLUX.1']] : [['wan21','Wan 2.1']]).map(([v,label]) => <option key={v} value={v}>{label}</option>)}</select></Field><PathField title="主干权重" directory={false} value={form.model} onChange={v => field('model',v)} /><PathField title="文本编码器" directory={false} value={form.text_encoder} onChange={v => field('text_encoder',v)} />{['sdxl','flux'].includes(form.comfy_architecture) && <PathField title="第二文本编码器" directory={false} value={form.text_encoder_2} onChange={v => field('text_encoder_2',v)} />}<PathField title="VAE 权重" directory={false} value={form.vae} onChange={v => field('vae',v)} />{form.workflow === 'r2v' && <PathField title="CLIP Vision 权重" directory={false} value={form.clip_vision} onChange={v => field('clip_vision',v)} />}</> : form.engine === 'llama' ? <GgufModelSelect selectRef={modelSelect} value={form.model} items={models} onChange={model => set(current => ({ ...current, model }))} /> : <PathField title="本地模型" value={form.model} onChange={v => field('model', v)} items={models} directory />}
      <Field title="推理设备"><select value={form.device} onChange={e => field('device', e.target.value)}>{[['auto', '自动'], ['cuda', 'NVIDIA CUDA'], ['mps', 'Apple Metal / MPS'], ['cpu', 'CPU']].map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></Field>
      {form.engine !== 'llama' && <div className="st-offload-option"><label className="st-check"><input type="checkbox" checked={form.cpu_offload} onChange={e => field('cpu_offload', e.target.checked)} />CPU offload · 节省显存</label>{form.engine === 'vllm' && form.cpu_offload && <NumberField title="CPU 卸载容量（GiB / GPU）" value={form.cpu_offload_gb} min={0.25} max={256} step={0.25} onChange={v => field('cpu_offload_gb', v)} />}</div>}
      {form.workflow === 'chat' ? <><NumberField title="空闲自动卸载（分钟）" value={form.idle_timeout_seconds / 60} min={1} max={60} onChange={v => field('idle_timeout_seconds', v * 60)} /><div className="st-grid"><NumberField title="上下文长度" value={form.context_length} min={256} onChange={v => field('context_length', v)} /><NumberField title="最大输出" value={form.max_tokens} min={1} onChange={v => field('max_tokens', v)} /><NumberField title="Temperature" value={form.temperature} min={0} max={2} step={0.1} onChange={v => field('temperature', v)} /><NumberField title="Top K" value={form.top_k} min={0} onChange={v => field('top_k', v)} /><NumberField title="Top P" value={form.top_p} min={0.01} max={1} step={0.01} onChange={v => field('top_p', v)} /></div>
      <Field title="系统提示词"><textarea rows={3} value={system.text} onChange={e => setSystem({ text: e.target.value })} /></Field><details><summary>引擎参数与视觉模型</summary>{form.engine === 'llama' ? <><NumberField title="GPU 层数（-1 全部）" value={form.gpu_layers} min={-1} onChange={v => field('gpu_layers', v)} /><Field title="视觉处理器"><select value={form.vision_handler} onChange={e => field('vision_handler', e.target.value)}><option value="none">无</option><option value="llava15">LLaVA 1.5</option><option value="llava16">LLaVA 1.6</option><option value="moondream">Moondream</option></select></Field><PathField title="匹配的 mmproj 文件" directory={false} value={form.mmproj} onChange={v => field('mmproj', v)} /></> : <><NumberField title="GPU 内存占比" value={form.gpu_memory_utilization} min={0.1} max={0.95} step={0.05} onChange={v => field('gpu_memory_utilization', v)} /><NumberField title="张量并行 GPU 数" value={form.tensor_parallel_size} min={1} onChange={v => field('tensor_parallel_size', v)} /></>}</details></> : <><div className="st-grid"><NumberField title="宽度" value={form.width} min={128} max={2048} step={8} onChange={v => field('width', v)} /><NumberField title="高度" value={form.height} min={128} max={2048} step={8} onChange={v => field('height', v)} /><NumberField title="采样步数" value={form.steps} min={1} onChange={v => field('steps', v)} /><NumberField title="引导强度" value={form.guidance_scale} min={0} step={0.5} onChange={v => field('guidance_scale', v)} />{form.workflow !== 't2i' && <><NumberField title="帧数" value={form.frames} min={2} onChange={v => field('frames', v)} /><NumberField title="FPS" value={form.fps} min={1} onChange={v => field('fps', v)} /></>}</div><Field title="采样器"><select value={form.sampler} onChange={e => field('sampler', e.target.value)}><option value="euler">Euler</option><option value="default">模型默认</option></select></Field></>}
      {form.workflow !== 'chat' && <NumberField title="随机种子" value={form.seed} min={0} onChange={v => field('seed', v)} />}
    </fieldset></section>
    <div className="st-stack">{form.workflow === 'chat' ? <section className="st-panel st-chat"><header><h2>LLM 对话</h2><div className="st-actions"><button disabled={busy} onClick={() => void newConversation()}><Plus size={15} />新对话</button></div></header>
      <div className="st-messages" ref={messagesView} onScroll={e => { const node = e.currentTarget; followOutput.current = node.scrollHeight - node.scrollTop - node.clientHeight < 70; }}>{!conversation?.messages.length && <div className="st-empty">选择本地模型，开始对话。</div>}{conversation?.messages.filter(m => m.role !== 'system').map((m, i) => <article className={`st-message ${m.role}`} key={i}><div><strong>{m.role === 'user' ? '你' : '模型'}</strong><button disabled={busy} title="移除此条及后续上下文" onClick={() => { const actualIndex = conversation.messages.indexOf(m); void trimConversation(actualIndex); }}><X size={12} /></button></div>{m.image && <img src={m.image} alt="会话图片" />}{m.role === 'assistant' ? <ChatAnswer text={m.content} reasoning={m.reasoning || ''} /> : <p>{m.content}</p>}</article>)}{job && !terminal(job) && job.config.action !== 'load' && <article className="st-message assistant" aria-label="模型流式输出"><strong>模型</strong><ChatAnswer text={live.text} reasoning={live.reasoning} streaming /></article>}</div>
      <form onSubmit={e => { e.preventDefault(); void submit(); }}><Field title="消息"><textarea ref={messageInput} rows={3} disabled={busy} value={message} onChange={e => { setMessage(e.target.value); setComposerError(''); }} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) { e.preventDefault(); void submit(); } }} placeholder={form.model ? "输入消息，Enter 发送，Shift+Enter 换行" : "先选择本地模型，再发送消息"} /></Field>{attachment && <div className="st-attachment"><img src={attachment} alt="待发送图片" /><button type="button" onClick={() => setAttachment('')}><X size={15} /></button></div>}<footer><button type="button" disabled={busy || !vision} title={vision ? '添加图片' : '当前模型不支持图片输入'} onClick={() => imageInput.current?.click()}><ImagePlus size={17} />图片</button><input ref={imageInput} hidden disabled={busy || !vision} type="file" accept="image/png,image/jpeg,image/webp" onChange={e => { void attach(e.target.files?.[0]); e.target.value = ''; }} /><button className="st-primary" type="submit" disabled={busy}><Send size={16} />{busy ? '处理中…' : '发送'}</button></footer><Error text={composerError} /></form>
    </section> : <section className="st-panel"><header><h2>{form.workflow === 't2i' ? '生成图像' : '生成视频'}</h2></header><div className="st-media-preview"><MediaPreview id={generated || (typeof job?.result?.material_id === 'string' ? job.result.material_id : undefined)} />{generated && <span className="st-tag">已保存到素材库</span>}</div><form onSubmit={e => { e.preventDefault(); void submit(); }}><fieldset className="st-media-fields" disabled={busy}><Field title="提示词"><textarea rows={5} value={form.prompt} onChange={e => field('prompt', e.target.value)} /></Field><Field title="负向提示词"><textarea rows={2} value={form.negative_prompt} onChange={e => field('negative_prompt', e.target.value)} /></Field>{form.workflow === 'r2v' && <div className="st-reference-picker"><h3>参考图片</h3><MediaPreview id={reference?.id} empty="从素材库选择，或导入一张参考图片" /><div className="st-actions"><button type="button" onClick={() => setLibraryOpen(true)}>从素材库选择</button><label className="st-upload"><ImagePlus size={16} />导入图片<input type="file" accept="image/png,image/jpeg,image/webp" onChange={async e => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return; setPending(true); try { setReference(await importMaterial(file)); } catch (err) { setError(errorMessage(err)); } finally { setPending(false); } }} /></label>{reference && <button type="button" onClick={() => setReference(undefined)}>移除</button>}</div>{reference && <small>{reference.name}</small>}</div>}</fieldset><footer><button className="st-primary" disabled={busy || !form.model || (form.workflow === 'r2v' ? !reference : !form.prompt.trim())}><Play size={16} />开始生成</button></footer></form>{(busy || sampling) && <div className="st-progress" aria-label="采样进度"><progress aria-label="采样进度" value={sampling?.step} max={sampling?.total || form.steps} /><span>{sampling ? `${sampling.step}/${sampling.total}` : job?.state === 'queued' ? '排队中' : '准备生成'}</span></div>}</section>}
      {libraryOpen && <div className="st-modal" role="dialog" aria-modal="true" aria-label="选择素材"><div><button className="st-modal-close" onClick={() => setLibraryOpen(false)}>关闭</button><Library imagesOnly onSelect={m => { setReference(m); setLibraryOpen(false); }} /></div></div>}
      <Error text={error || connectionError} />{job && <TaskPanel compact={form.workflow === 'chat'} hideProgress onProgress={(step,total) => setSampling({step,total})} hidePreview hideAnswer={form.workflow === 'chat'} onStream={(text, reasoning) => setLive({ text, reasoning })} onUpdate={setJob} key={job.id} id={job.id} onDone={j => { void done(j); }} />}
    </div></div></div>;
}
