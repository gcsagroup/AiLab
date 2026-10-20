import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, FileCheck2, Play } from 'lucide-react';
import { api, errorMessage } from './api';
import type { Attempt, Model, Preflight, Task } from './types';
import type { ExportObject } from './ExportDialog';
import { RunResult } from './Workbench';
import { Badge, Button, Dialog, Empty, ErrorNotice } from './ui';

export function ConversionStartDialog({ projectId, models, onClose, onCreated }: { projectId: string; models: Model[]; onClose: () => void; onCreated: (task: Task) => void }) {
  const available = models.filter(model => model.modality === 'text' && !model.model_config?.quantization && !model.model_config?.quantization_config && !model.conversion);
  const [modelId, setModelId] = useState(available[0]?.id || ''); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const requestKey = useRef<string | null>(null);
  async function create() {
    setBusy(true); setError(''); requestKey.current ||= crypto.randomUUID();
    try { onCreated(await api<Task>('POST', '/conversions', { project_id: projectId, model_id: modelId, name: 'MLX 4-bit 量化' }, requestKey.current)); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title="新建量化实验" wide onClose={onClose} preventClose={busy}><div className="form-stack"><p className="muted">把已验证的未量化 Qwen2.5-0.5B 模型转换为独立 MLX 4-bit 文件。下一步检查并明确开始。</p>{available.length ? <label>源模型<select disabled={busy} value={modelId} onChange={e => { setModelId(e.target.value); requestKey.current = null; }}>{available.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : <Empty title="需要未量化的源模型">先在模型库导入 Qwen2.5-0.5B-Instruct，量化后的模型不能在此重复量化。</Empty>}<ConversionSettings /><ErrorNotice message={error} /><Button primary busy={busy} disabled={!modelId} onClick={create}>创建量化任务</Button></div></Dialog>;
}

function ConversionSettings() {
  return <section className="review-box"><div className="section-title"><h3>固定量化组合</h3><Badge>本机 Apple GPU</Badge></div><dl className="facts"><div><dt>目标引擎</dt><dd>MLX</dd></div><div><dt>权重位宽</dt><dd>4-bit</dd></div><div><dt>分组大小</dt><dd>64</dd></div><div><dt>量化方式</dt><dd>affine</dd></div><div><dt>文件格式</dt><dd>MLX safetensors 分片</dd></div></dl><p className="muted">原模型保留。输出先作为实验模型保存，实际体积由文件计算；速度与质量需要另行对照。</p></section>;
}

export function ConversionTask({ task, models, onBack, registerLeave, onUpdated, onExport }: { task: Task; models: Model[]; onBack: () => void; registerLeave: (handler: (() => Promise<boolean>) | null) => void; onUpdated: () => void; onExport: (object: ExportObject) => void }) {
  const operationLabel = task.operation === 'merge' ? '合并' : task.operation === 'distill' ? '蒸馏' : task.operation === 'convert' ? '格式转换' : task.operation === 'generate' ? '格式试用' : '量化';
  const [attempts, setAttempts] = useState(task.attempts || (task.latest_attempt ? [task.latest_attempt] : [])); const [attempt, setAttempt] = useState<Attempt | null>(task.latest_attempt || task.attempts?.[0] || null);
  const [preflight, setPreflight] = useState<Preflight | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const submitKey = useRef<string | null>(null);
  useEffect(() => { registerLeave(async () => { if (busy) setError('当前操作尚未完成，请稍后再离开。'); return !busy; }); return () => registerLeave(null); }, [busy]);
  async function check() { setBusy(true); setError(''); try { setPreflight(await api<Preflight>('POST', `/tasks/${task.id}/preflight`, { draft_revision: task.draft_revision })); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function submit() {
    if (!preflight?.can_submit) return; setBusy(true); setError(''); submitKey.current ||= crypto.randomUUID();
    try { const value = await api<Attempt>('POST', `/tasks/${task.id}/attempts`, { preflight_id: preflight.preflight_id, expected_revision: task.draft_revision }, submitKey.current); setAttempt(value); setAttempts(items => [value, ...items.filter(item => item.id !== value.id)]); setPreflight(null); submitKey.current = null; onUpdated(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <><div className="breadcrumb"><button disabled={busy} onClick={onBack}><ArrowLeft size={15} />模型实验室</button></div><div className="page-heading"><div><h1>{task.name}</h1><p>{task.operation === 'generate' ? '使用模型对应的格式引擎在本机运行。' : '生成独立模型后可保存、试用和导出。'}</p></div></div><div className="workbench-layout"><section className="composer" aria-label={`${operationLabel}配置`}><h2>{models.find(item => item.id === task.draft.model_id)?.name || task.draft.model_id}</h2><>{task.operation === 'quantize' ? <ConversionSettings /> : <section className="review-box"><h3>已冻结的{operationLabel}配方</h3>{task.draft.input.prompt && <p>提示词：{task.draft.input.prompt}</p>}{task.operation === 'distill' && <p>教师：{models.find(item => item.id === task.draft.teacher_model_id)?.name || task.draft.teacher_model_id}</p>}<dl className="facts">{Object.entries(task.draft.runtime).map(([name, value]) => <div key={name}><dt>{({ merge_weight: '融合比例', steps: '训练步数', teacher_max_tokens: '教师输出上限', max_seq_length: '学生样本上限', engine: '执行引擎', device_id: '执行设备', seed: '随机种子', training_type: '训练目标', update_method: '更新方式', recipe_id: '配方版本', learning_rate: '学习率', lora_rank: 'LoRA 秩', lora_alpha: 'LoRA 缩放系数', num_layers: '更新层数', batch_size: '批次大小', gradient_accumulation: '梯度累积', optimizer: '优化器', weight_decay: '权重衰减', lora_dropout: 'LoRA 随机丢弃率', max_tokens: '最大输出词元' } as Record<string, string>)[name] || name}</dt><dd>{String(value)}</dd></div>)}</dl><p className="muted">来源和配方已冻结。需要修改时新建任务；原文件保留。</p></section>}</><ErrorNotice message={error} />{preflight && <section className="preflight"><strong>{preflight.can_submit ? `检查通过，可以开始${operationLabel}` : '请先完成以下准备'}</strong>{preflight.blocking.map((item, i) => <p className="error" key={i}>{item.message}</p>)}{preflight.warnings.map((item, i) => <p className="warning" key={i}>{item.message}</p>)}<details><summary>查看已应用的{operationLabel}参数</summary><pre>{JSON.stringify(preflight.effective_config, null, 2)}</pre></details></section>}{preflight?.can_submit ? <Button primary busy={busy} onClick={submit}><Play size={16} />开始{operationLabel}</Button> : <Button primary busy={busy} onClick={check}><FileCheck2 size={16} />检查{operationLabel}配置</Button>}</section><div className="result-column">{attempts.length > 1 && <label>查看{operationLabel}记录<select value={attempt?.id || ''} onChange={e => setAttempt(attempts.find(item => item.id === e.target.value) || null)}>{attempts.map(item => <option value={item.id} key={item.id}>{item.id.slice(-8)}</option>)}</select></label>}{attempt ? <RunResult key={attempt.id} initial={attempt} onChanged={onUpdated} onExport={onExport} /> : <Empty title={`${operationLabel}尚未开始`}>原模型与本次{operationLabel}配方会保留；执行前先检查文件与运行环境。</Empty>}</div></div></>;
}
