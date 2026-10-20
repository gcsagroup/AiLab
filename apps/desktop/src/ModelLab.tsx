import { useRef, useState } from 'react';
import { api, errorMessage } from './api';
import type { Adapter, Dataset, Model, Task } from './types';
import { Button, Dialog, Empty, ErrorNotice } from './ui';

export function ModelLabDialog({ operation, projectId, models, adapters, datasets, onClose, onCreated }: { operation: 'merge' | 'distill'; projectId: string; models: Model[]; adapters: Adapter[]; datasets: Dataset[]; onClose: () => void; onCreated: (task: Task) => void }) {
  const teachers = models.filter(item => item.modality === 'text' && ['safetensors', 'mlx-safetensors'].includes(item.format) && item.model_config?.model_type === 'qwen2' && !item.model_config?.quantization && !item.model_config?.quantization_config);
  const available = teachers.filter(item => item.model_config?.hidden_size === 896 && item.model_config?.num_hidden_layers === 24);
  const [modelId, setModelId] = useState(available[0]?.id || '');
  const [adapterId, setAdapterId] = useState(''); const [teacherId, setTeacherId] = useState(available[0]?.id || '');
  const [datasetId, setDatasetId] = useState(datasets.find(item => item.schema === 'sft' && item.dataset_split_role === 'train')?.id || '');
  const [weight, setWeight] = useState('1'); const [steps, setSteps] = useState('4'); const [tokens, setTokens] = useState('64'); const [length, setLength] = useState('512');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const key = useRef<string | null>(null);
  const compatible = adapters.filter(item => item.base_model_id === modelId);
  const label = operation === 'merge' ? '合并' : '蒸馏';
  async function create() {
    setBusy(true); setError('');
    const values = [weight, steps, tokens, length].map(Number);
    if (values.some(value => !Number.isFinite(value)) || !Number.isInteger(values[1]) || !Number.isInteger(values[2]) || !Number.isInteger(values[3]) || values[0] < 0.01 || values[0] > 1 || values[1] < 1 || values[1] > 200 || values[2] < 8 || values[2] > 256 || values[3] < 32 || values[3] > 2048) { setError('请在标明范围内填写完整数值；步数与词元数必须为整数。'); setBusy(false); return; }
    key.current ||= crypto.randomUUID();
    try {
      onCreated(await api<Task>('POST', '/model-lab/tasks', { project_id: projectId, operation, model_id: modelId, ...(operation === 'merge' ? { adapter_id: adapterId, merge_weight: values[0] } : { teacher_model_id: teacherId, dataset_id: datasetId, steps: values[1], teacher_max_tokens: values[2], max_seq_length: values[3] }) }, key.current));
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <Dialog title={`新建${label}实验`} wide onClose={onClose} preventClose={busy}><div className="form-stack" onChange={() => { key.current = null; }}>
    <p className="muted">{operation === 'merge' ? '将已保存的 LoRA 按比例融合到其原始基座，生成独立模型，并在本机重新加载核对数值。' : '本地教师生成固定监督回答，再用这些回答更新学生 LoRA 并融合为独立模型。仅支持单轮 SFT 数据，请先在数据页按来源组划分，每次 1—64 条；不发送远端请求。'}</p>
    {available.length ? <label>{operation === 'merge' ? '原始基座' : '学生基座'}<select disabled={busy} value={modelId} onChange={e => { setModelId(e.target.value); setAdapterId(''); }}>{available.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label> : <Empty title="需要未量化 Qwen2.5 基座">先在模型库导入 0.5B 原始权重；教师另可选择 7B。</Empty>}
    {operation === 'merge' ? <><label>适配器<select disabled={busy} value={adapterId} onChange={e => setAdapterId(e.target.value)}><option value="">请选择与基座匹配的 LoRA</option>{compatible.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>融合比例（0.01—1）<input disabled={busy} inputMode="decimal" value={weight} onChange={e => setWeight(e.target.value)} /></label></> : <>
      <label>本地教师<select disabled={busy} value={teacherId} onChange={e => setTeacherId(e.target.value)}>{teachers.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>提示词来源（已划分的单轮训练集）<select disabled={busy} value={datasetId} onChange={e => setDatasetId(e.target.value)}><option value="">请选择数据</option>{datasets.filter(item => item.schema === 'sft' && item.dataset_split_role === 'train').map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
      <label>学生训练步数（1—200）<input disabled={busy} inputMode="numeric" value={steps} onChange={e => setSteps(e.target.value)} /></label>
      <label>教师最大输出词元（8—256）<input disabled={busy} inputMode="numeric" value={tokens} onChange={e => setTokens(e.target.value)} /></label>
      <label>学生完整样本词元上限（32—2048）<input disabled={busy} inputMode="numeric" value={length} onChange={e => setLength(e.target.value)} /></label>
      <p className="muted">原数据的助手回答保留为来源；训练实际使用教师新生成的回答。超长或空回答会阻断任务。其他训练参数采用已验证的固定 LoRA 配方。</p>
    </>}
    <p className="muted">输入文件保留。产物先标记为实验模型；成功执行不代表质量或速度提升。</p><ErrorNotice message={error} />
    <Button primary busy={busy} disabled={!modelId || (operation === 'merge' ? !adapterId : !teacherId || !datasetId)} onClick={create}>创建{label}任务</Button>
  </div></Dialog>;
}
