import { useEffect, useState } from 'react';
import { errorMessage, mediaBlob, type ImportKind } from './api';
import type { Adapter, Artifact, Dataset, Draft, Material, Model, Runtime } from './types';
import { Button, ErrorNotice } from './ui';

export function defaultMediaRuntime(kind: string, train: boolean): Runtime {
  if (kind === 'audio') return { engine: 'kokoro', device_id: 'cpu', voice: 'zf_xiaobei', speed: 1, sample_rate: 24000, seed: 0 };
  if (kind === 'video') return { engine: 'diffusers', device_id: 'apple-gpu', steps: 25, frames: 14, fps: 7, seed: 0 };
  return train ? { engine: 'diffusers', device_id: 'apple-gpu', size: 512, steps: 12, learning_rate: 0.0001, lora_rank: 4, seed: 0 } : { engine: 'diffusers', device_id: 'apple-gpu', size: 512, steps: 20, cfg: 7.5, seed: 0 };
}

export function selectMediaRuntime(draft: Draft, pipeline?: string, previousPipeline?: string, deviceFreeBytes?: number): Runtime {
  const runtime = draft.runtime;
  if (!window.ailabHF || draft.operation !== 'generate') return runtime;
  if (pipeline === 'audiocpp-tts' || pipeline === 'audiocpp-gen')
    return runtime.device_id === 'cpu' ? runtime : { ...runtime, device_id: 'cpu' };
  const h3 = pipeline === 'h3-video' || pipeline === 'h3-image';
  if (pipeline === 'wan21-t2v' || pipeline === 'diffusion-video') return { ...runtime, steps: 1, frames: 5, fps: 8, device_id: 'cpu' };
  if (pipeline === 'iris' || pipeline === 'anima' || pipeline === 'diffusion-image') return { ...runtime, steps: 1, cfg: 3, device_id: 'cpu' };
  if (!h3 && !previousPipeline?.startsWith('h3-') && previousPipeline !== 'wan21-t2v' && previousPipeline !== 'iris' && previousPipeline !== 'anima' && !previousPipeline?.startsWith('diffusion-')) return runtime;
  const defaults = draft.kind === 'video'
    ? (h3 ? { steps: 4, frames: 22, fps: 24 } : { steps: 25, frames: 14, fps: 7 })
    : (h3 ? { steps: 6, cfg: 1 } : { steps: 20, cfg: 7.5 });
  const useCPU = h3 && deviceFreeBytes !== undefined && deviceFreeBytes < 6 * 1024 ** 3;
  return { ...runtime, ...defaults, ...(useCPU ? { device_id: 'cpu' } : {}) };
}

export function mainMedia(artifacts: Artifact[] = []): Artifact | undefined {
  return artifacts.find(item => (item.name === 'image.png' && item.media_type === 'image/png') || (item.name === 'video.mp4' && item.media_type === 'video/mp4') || (item.name === 'speech.wav' && item.media_type === 'audio/wav'));
}

export function MediaPreview({ artifact, name = '生成结果', autoLoad = false, downloadName }: { artifact: Artifact; name?: string; autoLoad?: boolean; downloadName?: string }) {
  const [requested, setRequested] = useState(autoLoad);
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!requested || !artifact.id) return;
    let live = true;
    let created = '';
    setUrl(''); setError('');
    void mediaBlob(artifact.id).then(blob => {
      if (!live) return;
      if (blob.type !== artifact.media_type) throw new Error('预览文件类型与登记记录不符。');
      created = URL.createObjectURL(blob); setUrl(created);
    }).catch(e => { if (live) setError(errorMessage(e)); });
    return () => { live = false; if (created) URL.revokeObjectURL(created); };
  }, [artifact.id, artifact.media_type, requested, retry]);
  return <section className="media-preview" aria-label={`${name}预览`}>
    {url ? artifact.media_type === 'image/png' ? <img src={url} alt={name} /> : artifact.media_type === 'video/mp4' ? <video src={url} controls playsInline preload="metadata" aria-label={name} /> : <audio src={url} controls preload="metadata" aria-label={name} /> : <Button disabled={requested && !error} onClick={() => { setRequested(true); setRetry(value => value + 1); }}>{requested && !error ? '正在读取已校验文件…' : error ? '重新读取预览' : artifact.media_type === 'image/png' ? '预览图片' : artifact.media_type === 'video/mp4' ? '播放视频' : '播放音频'}</Button>}
    {url && downloadName && <a href={url} download={downloadName}>另存{name}</a>}
    <ErrorNotice message={error} />
  </section>;
}

export function MediaFields({ draft, models, datasets, adapters, materials, onChange, onImport, deviceName, deviceFreeBytes }: { deviceName?: string; deviceFreeBytes?: number; draft: Draft; models: Model[]; datasets: Dataset[]; adapters: Adapter[]; materials: Material[]; onChange: (draft: Draft) => void; onImport: (kind: ImportKind) => void }) {
  const kind = draft.kind;
  const train = draft.operation === 'train';
  const runtime = draft.runtime;
  const image = kind === 'image';
  const video = kind === 'video';
  const audio = kind === 'audio';
  const selectableModels = models.filter(model => model.modality === kind && (!window.ailabHF || model.execution_available !== false));
  const pipeline=selectableModels.find(m=>m.id===draft.model_id)?.pipeline;
  const llamaSpeech = pipeline === 'llama-tts';
  const vocoder = pipeline === 'llama-vocoder';
  const wan = pipeline === 'wan21-t2v' || pipeline === 'diffusion-video';
  const audioGen = pipeline === 'audiocpp-gen';
  const audioTts = pipeline === 'audiocpp-tts';
  const audioLabel = vocoder ? '音频码' : audioGen ? '声音描述' : '配音文本';
  const asr = pipeline === 'audiocpp-asr';
  const hibiki = pipeline === 'llama-hibiki';
  const audioInput = window.ailabHF && (asr || hibiki || pipeline === 'audiocpp-vad' || pipeline === 'firered-vad');
  const upscale = window.ailabHF && (pipeline === 'esrgan-x4' || pipeline === 'mosr-x4');
  const fromMaterial = audioInput || upscale;
  const materialKind = audioInput ? 'audio' : 'image';
  const h3=window.ailabHF && (pipeline==='h3-image' || pipeline==='h3-video');
  const selectModel=(id:string)=>{
    const next=selectableModels.find(m=>m.id===id)?.pipeline;
    const nextRuntime = selectMediaRuntime(draft, next, pipeline, deviceFreeBytes);
    onChange({...draft,model_id:id||null,adapter_id:null,runtime:nextRuntime,...(video && (next === 'wan21-t2v' || next === 'diffusion-video') ? {input:{prompt:draft.input.prompt || '',negative_prompt:draft.input.negative_prompt || ''}} : !window.ailabHF && nextRuntime !== runtime && video && next !== 'h3-video' ? {input:{material_id:draft.input.material_id ?? null}} : {})});
  };
  const engine = window.ailabHF ? 'ailab-gguf' : audio ? 'kokoro' : 'diffusers';
  function resetRuntime() {
    const runtime = { ...defaultMediaRuntime(kind, train), ...(window.ailabHF ? { engine, device_id: 'cpu' } : {}) };
    const input = (video && Boolean(window.ailabHF)) || fromMaterial ? draft.input : image ? { prompt: train ? '' : draft.input.prompt || '', negative_prompt: '' } : video ? { material_id: null } : { prompt: draft.input.prompt };
    onChange({ ...draft, runtime: selectMediaRuntime({ ...draft, runtime }, pipeline), input });
  }
  const update = (field: keyof Runtime, value: number | string) => onChange({ ...draft, runtime: { ...runtime, [field]: value } });
  if (train && !image) return <p className="warning">此组合尚未开放训练。请返回工作台的“运行 / 试用”，视频可使用图片生成短片，音频可输入中文生成配音。</p>;
  return <>
    <div className="field"><div className="label-action"><label htmlFor="media-model">{audio ? (audioInput || audioGen ? '音频模型' : '配音模型') : video ? '视频模型' : '图片基座模型'}</label><button tabIndex={0} type="button" onClick={() => onImport('model')}>导入模型</button></div><select id="media-model" aria-label="选择媒体模型" value={draft.model_id || ''} onChange={e => selectModel(e.target.value)}><option value="">请选择本类别的模型</option>{draft.model_id && !selectableModels.some(model => model.id === draft.model_id) && <option value={draft.model_id} disabled>原模型待核实 · {draft.model_id}</option>}{selectableModels.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></div>
    <p className="muted">{window.ailabHF ? (pipeline?.startsWith('diffusion-') ? 'stable-diffusion.cpp · 本机 CPU' : wan ? 'Wan 2.1 T2V 1.3B · 本机 CPU' : audioGen ? '音乐 / 音效生成 · 本机 CPU' : audioTts ? '语音合成 · 本机 CPU' : h3 ? (image ? 'MiniMax-H3-Image · 本机 GGUF' : 'MiniMax-H3 · 本机 GGUF') : upscale ? (pipeline === 'mosr-x4' ? 'MoSR 四倍放大 · 本机 CPU' : 'Real-ESRGAN 四倍放大 · 本机 CPU') : pipeline === 'anima' ? 'Anima · 本机 CPU' : pipeline === 'iris' ? 'Iris-3B · 本机 CPU' : pipeline === 'z-image' ? 'Z-Image · 本机 GGUF' : image ? 'Tiny-SD · 本机 GGUF' : video ? 'AnimateDiff 图生视频 · stable-diffusion.cpp · 本机 GGUF' : hibiki ? 'Hibiki 法语语音翻译' : asr ? '语音转写 · 本机 CPU' : pipeline === 'audiocpp-vad' ? '语音活动检测 · 本机 CPU' : audioInput ? 'FireRed VAD 语音活动检测 · 本机 CPU' : 'Kokoro 中文配音 · 本机 CPU') : image ? 'Tiny-SD · 本机 Apple GPU' : video ? 'SVD 图生视频 · 本机 Apple GPU' : 'Kokoro 中文配音 · 本机 CPU'}。每次运行独立加载；质量需要检查实际产物。</p>
    {runtime.engine !== engine && <div className="review-box"><p className="warning">这份旧草稿使用了其它类别的参数，需要先重新选择媒体配置。</p><Button onClick={resetRuntime}>应用本类别默认配置</Button></div>}
    {train ? <><div className="field"><div className="label-action"><label htmlFor="image-data">图片与描述数据</label><button tabIndex={0} type="button" onClick={() => onImport('image-dataset')}>导入图片数据</button></div><select id="image-data" value={draft.dataset_id || ''} onChange={e => onChange({ ...draft, dataset_id: e.target.value || null })}><option value="">请选择已检查的图片数据</option>{datasets.filter(dataset => dataset.schema === 'image_caption_v1').map(dataset => <option key={dataset.id} value={dataset.id}>{dataset.name} · {dataset.sample_count} 张</option>)}</select></div><p className="muted">1—8 张 512×512 RGB 图片；每张保留描述与来源。仅更新注意力层 LoRA，保留基座。当前没有图片检查点恢复及质量自动准入。</p></> : <>
    {((video && !wan) || fromMaterial) && <div className="field"><div className="label-action"><label htmlFor="video-source">{audioInput ? '输入音频' : '输入图片'}</label><button tabIndex={0} type="button" onClick={() => onImport('material')}>{audioInput ? '导入音频素材' : '导入图片素材'}</button></div><select id="video-source" value={draft.input.material_id || ''} onChange={e => onChange({ ...draft, input: { ...draft.input, material_id: e.target.value || null } })}><option value="">{audioInput ? '请选择当前项目的 WAV 素材' : h3 ? '可选首帧 · 从当前项目选择 PNG' : '请选择当前项目的 PNG 素材'}</option>{draft.input.material_id && !materials.some(item => item.id === draft.input.material_id && item.kind === materialKind) && <option value={draft.input.material_id} disabled>原素材待核实 · {draft.input.material_id}</option>}{materials.filter(item => item.kind === materialKind).map(item => <option key={item.id} value={item.id}>{item.name}{!audioInput && ` · ${item.width}×${item.height}`}</option>)}</select></div>}
    {fromMaterial ? <p className="muted">{hibiki ? '选择法语录音，生成英语语音。' : asr ? '将所选 WAV 中的语音转写为文字。' : audioInput ? '检测 WAV 中的语音段，结果以起止秒数显示。' : '将所选 PNG 的宽和高各放大四倍。'}</p> : video && !window.ailabHF ? <p className="muted">此模型使用图片作为条件，没有文字控制。{window.ailabHF ? '输入等比适配至 512×288，模型在上下补边后生成，再去除对齐补边并放大到 1024×576。' : '输入会转为 RGB、等比缩放后居中补边到 1024×576；不会裁掉主体。'}生成 14 帧、7 FPS，约 2 秒，可能只有轻微运动。</p> : <><label>{audio ? audioLabel : '画面描述'}<textarea aria-label={audio ? audioLabel : '画面描述'} rows={5} maxLength={vocoder ? 24000 : llamaSpeech || audioTts || audioGen ? 2000 : audio ? 120 : 2000} value={draft.input.prompt || ''} onChange={e => onChange({ ...draft, input: { ...draft.input, prompt: e.target.value } })} placeholder={h3 && video ? '描述场景、动作和声音…' : vocoder ? '输入音频码的 JSON 整数数组，例如 [10, 20, 30]。' : audioGen ? '描述音乐或音效…' : llamaSpeech || audioTts ? '输入要朗读的文字…' : audio ? '输入中文配音内容…' : '描述主体、环境和画面风格…'} /></label>{audio ? <small className="muted">{vocoder ? '使用此权重对应码本中的整数。' : audioGen ? '短片段默认请求 2 秒。歌曲模型可在首行用 @歌词 填歌词，下一行写风格。需要参考音频的模型可在最前面用 @素材 引用当前项目的 WAV。' : audioTts ? '请使用模型支持的语言。需要参考音频时，首行填写 @素材 和素材编号；需要原文时，下一行填写 @参考文本 和原文，再换行填写要朗读的文字。' : llamaSpeech ? '可在首行用 @素材 引用当前项目中的参考语音。' : '当前接受 1—120 字中文、数字与常用标点；不支持混入英文或表情。实际音素过长时会提示缩短。'}</small> : <label>不希望出现的内容<textarea aria-label="不希望出现的内容" rows={2} maxLength={2000} value={draft.input.negative_prompt || ''} onChange={e => onChange({ ...draft, input: { ...draft.input, negative_prompt: e.target.value } })} /></label>}</>}</>}
    {image && !train && (draft.adapter_id || adapters.some(adapter => adapter.base_model_id === draft.model_id)) && <label>图片训练适配器<select aria-label="图片训练适配器" value={draft.adapter_id || ''} onChange={e => onChange({ ...draft, adapter_id: e.target.value || null })}><option value="">仅使用基座模型</option>{draft.adapter_id && !adapters.some(adapter => adapter.id === draft.adapter_id && adapter.base_model_id === draft.model_id) && <option value={draft.adapter_id} disabled>原适配器待核实 · {draft.adapter_id}</option>}{adapters.filter(adapter => adapter.base_model_id === draft.model_id).map(adapter => <option key={adapter.id} value={adapter.id}>{adapter.name} · 实验产物</option>)}</select><small>试用同一适配器不代表图片质量已经通过验收。</small></label>}
    <details className="runtime-settings" open><summary>运行设置</summary><div className="form-stack"><div className="two-fields">
      {image && <label>图片尺寸<input value={upscale ? '原图宽高各 ×4' : '512 × 512'} readOnly /></label>}
      {!audio && !upscale && <label>{train ? '训练步数' : '生成步数'}<input type="number" value={runtime.steps ?? ''} readOnly={!window.ailabHF || train} min={1} max={100} onChange={e=>update('steps',Number(e.target.value))} /></label>}
      {image && !train && !upscale && <label>描述引导强度<input type="number" value={runtime.cfg ?? ''} readOnly={!window.ailabHF} min={0} max={30} step={0.1} onChange={e=>update('cfg',Number(e.target.value))} /></label>}
      {train && <><label>学习率<input value={runtime.learning_rate ?? ''} readOnly /></label><label>LoRA 秩<input value={runtime.lora_rank ?? ''} readOnly /></label></>}
      {video && <><label>视频尺寸<input value={wan ? "160 × 96" : "1024 × 576"} readOnly /></label><label>帧数 / 帧率<input value={wan ? "5 帧 / 8 FPS" : h3 ? "22 帧 / 24 FPS" : "14 帧 / 7 FPS"} readOnly /></label></>}
      {audio && !audioInput && <><label>音色<input value={vocoder ? '输入音频码' : audioGen ? '模型生成' : llamaSpeech || audioTts ? '模型默认音色' : '小北 · 中文女声'} readOnly /></label><label>语速<input disabled={vocoder || audioGen} type="number" min={0.5} max={2} step={0.1} value={runtime.speed ?? ''} onChange={e => update('speed', Number(e.target.value))} /></label><label>采样格式<input value={llamaSpeech || audioGen ? '模型原生采样率 · WAV' : '24 kHz · 单声道 WAV'} readOnly /></label></>}
      {!fromMaterial && <label>随机种子<input type="number" min={0} max={4294967295} value={runtime.seed} onChange={e => update('seed', Number(e.target.value))} /></label>}
    </div><small>{!audio && !window.ailabHF && '当前采用固定已验证配方；尺寸、步数、引导强度和训练参数尚未开放其它组合。'}执行位置：{window.ailabHF ? ((fromMaterial && !hibiki) || wan || audioGen || audioTts || pipeline === 'iris' || pipeline === 'anima' || pipeline === 'diffusion-image' ? '本机 CPU' : deviceName || (runtime.device_id === 'cpu' ? '本机 CPU' : runtime.device_id)) : audio ? '本机 CPU' : '本机 Apple GPU'}。本次输入在本机处理，模型、输入版本与实际参数一并保存。</small></div></details>
  </>;
}
