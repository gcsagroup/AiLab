import { useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { Model, Task } from './types';
import { Button, Dialog, ErrorNotice } from './ui';

export const formatNames: Record<string, string> = { coreml: 'Core ML', onnx: 'ONNX', torchscript: 'TorchScript' };

export function FormatDialog({ projectId, models, trialModel, onCreated, onClose }: { projectId: string; models: Model[]; trialModel?: Model; onCreated: (task: Task) => void; onClose: () => void }) {
  const available = models.filter(item => item.modality === 'text' && ['safetensors', 'mlx-safetensors'].includes(item.format) && item.model_config?.model_type === 'qwen2' && item.model_config?.hidden_size === 896 && item.model_config?.num_hidden_layers === 24 && !item.model_config?.quantization && !item.model_config?.quantization_config);
  const [modelId, setModelId] = useState(trialModel?.id || available[0]?.id || '');
  const [format, setFormat] = useState(trialModel?.default_engine || 'torchscript');
  const [prompt, setPrompt] = useState('只回答一个数字：4加5等于几？');
  const [tokens, setTokens] = useState('32'); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const key = useRef<string | null>(null);
  async function create() {
    const maximum = Number(tokens);
    if (trialModel && (!prompt.trim() || !Number.isInteger(maximum) || maximum < 1 || maximum > 64)) { setError('请填写提示词，最大输出须为 1—64 的整数。'); return; }
    setBusy(true); setError(''); key.current ||= crypto.randomUUID();
    try { onCreated(await api<Task>('POST', trialModel ? '/formatted-model-trials' : '/format-conversions', { project_id: projectId, model_id: modelId, ...(trialModel ? { prompt, max_tokens: maximum } : { target_format: format }) }, key.current)); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title={trialModel ? `${formatNames[format]} 独立试用` : '新建格式转换'} wide onClose={onClose} preventClose={busy}><div className="form-stack" onChange={() => { key.current = null; }}>
    {trialModel ? <><h3>{trialModel.name}</h3><label>提示词<textarea disabled={busy} value={prompt} onChange={e => setPrompt(e.target.value)} /></label><label>最大输出词元（1—64）<input disabled={busy} inputMode="numeric" value={tokens} onChange={e => setTokens(e.target.value)} /></label></> : <>
      <label>源模型<select disabled={busy} value={modelId} onChange={e => setModelId(e.target.value)}><option value="">选择未量化的 Qwen2.5-0.5B</option>{available.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>目标格式<select disabled={busy} value={format} onChange={e => setFormat(e.target.value)}>{Object.entries(formatNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
    </>}
    <section className="review-box"><h3>当前已适配范围</h3><p>Qwen2.5-0.5B · CPU · FP32 · 固定 128 词元上下文。输入与最大输出合计不能超过 128，不会截断输入。</p><p className="muted">{trialModel ? '使用该格式自身的运行引擎，逐词元重新计算完整图，不使用 KV 缓存。' : '生成独立模型文件后，在目标引擎重新加载，并与原生模型做固定样例数值对照。'}Core ML 当前也只使用 CPU；不代表已验证 GPU、神经网络引擎或速度提升。</p></section>
    <ErrorNotice message={error} /><Button primary busy={busy} disabled={!modelId} onClick={create}>{trialModel ? '创建试用任务' : '创建转换任务'}</Button>
  </div></Dialog>;
}
