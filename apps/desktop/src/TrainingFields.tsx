import { useContext, useEffect, useId, useState } from 'react';
import { collection, errorMessage } from './api';
import { LibraryReadContext } from './LibraryReadContext';
import type { Runtime, TrainingContract, TrainingParameter, TrainingParameterName } from './types';

const fields = [
  ['steps', '训练步数', '步'], ['learning_rate', '学习率', ''], ['max_seq_length', '最大序列长度', '词元'],
  ['lora_rank', 'LoRA 秩', ''], ['lora_alpha', 'LoRA Alpha', ''], ['num_layers', '训练末尾层数', '层'], ['seed', '随机种子', ''],
] as const;
const fixedFields = ['batch_size', 'gradient_accumulation', 'optimizer', 'weight_decay', 'lora_dropout'] as const;
const fixedLabels = { batch_size: '批大小', gradient_accumulation: '梯度累积', optimizer: '优化器', weight_decay: '权重衰减', lora_dropout: 'LoRA Dropout' };
type Scope = { taskId: string; projectId: string; targetId?: string | null; engine: string; deviceId: string; enabled: boolean };
type ContractRead = { key: string; contract: TrainingContract | null; pending: boolean; error: string; isCurrent: () => boolean };
export type TrainingContractState = ContractRead & { retry: () => void };

function accepts(parameter: TrainingParameter, value: unknown) {
  if (parameter.type === 'string') return typeof value === 'string' && (!parameter.enum || parameter.enum.includes(value));
  return typeof value === 'number' && Number.isFinite(value) && (parameter.type !== 'integer' || Number.isInteger(value))
    && (parameter.minimum === undefined || value >= parameter.minimum) && (parameter.maximum === undefined || value <= parameter.maximum)
    && (!parameter.enum || parameter.enum.includes(value));
}

function readContract(items: unknown, scope: Scope): TrainingContract {
  const fail = () => { throw new Error('约束缺失、格式无效或与当前执行位置不一致。'); };
  if (!Array.isArray(items)) return fail();
  const remote = Boolean(scope.targetId);
  const matches = items.filter(value => value && value.engine === scope.engine && value.device_id === scope.deviceId && value.execution_scope === (remote ? 'remote' : 'local'));
  if (matches.length !== 1) return fail();
  const contract = matches[0] as TrainingContract;
  const expectedId = remote ? 'qwen25-nvidia-sft-lora-v1' : 'qwen25-mlx-sft-lora-v1';
  if (contract.schema_version !== 'ailab-training-contract-v1' || contract.id !== expectedId
    || contract.engine !== (remote ? 'transformers' : 'mlx') || contract.device_id !== (remote ? 'cuda:0' : 'apple-gpu')
    || contract.kind !== 'text' || contract.operation !== 'train' || contract.training_type !== 'sft' || contract.update_method !== 'lora'
    || contract.recipe_id !== 'qwen25-assistant-only-v1' || typeof contract.model_constraint !== 'string' || !contract.model_constraint.trim()
    || contract.source?.id !== contract.id || typeof contract.source.label !== 'string' || !contract.source.label.trim()
    || contract.source.default_source !== 'versioned_control_schema' || contract.source.constraint_source !== 'control_and_worker_intersection'
    || contract.application_policy?.applies_to !== 'next_run' || contract.application_policy.restart_required !== false
    || contract.application_policy.saved_values !== 'preserve_and_validate' || !Array.isArray(contract.application_policy.conflicts) || contract.application_policy.conflicts.length
    || contract.stopping?.mode !== 'steps' || contract.stopping.sample_order !== 'file_cycle'
    || contract.stopping.data_parallel_devices !== 1 || contract.stopping.effective_batch_size !== 1
    || contract.verification?.device_execution !== 'requires_preflight' || contract.verification.quality !== 'not_implied') return fail();
  for (const name of [...fields.map(([name]) => name), ...fixedFields]) {
    const parameter = contract.parameters?.[name];
    const editable = fields.some(([field]) => field === name);
    if (!parameter || !['integer', 'number', 'string'].includes(parameter.type) || parameter.editable !== editable
      || typeof parameter.unit !== 'string' || !parameter.unit
      || (parameter.enum !== undefined && (!Array.isArray(parameter.enum) || !parameter.enum.length || parameter.enum.some(value => !['number', 'string'].includes(typeof value))))
      || (parameter.minimum !== undefined && !Number.isFinite(parameter.minimum)) || (parameter.maximum !== undefined && !Number.isFinite(parameter.maximum))
      || (parameter.minimum !== undefined && parameter.maximum !== undefined && parameter.minimum > parameter.maximum)
      || (editable && (parameter.type === 'string' || parameter.minimum === undefined || parameter.maximum === undefined))
      || !accepts(parameter, parameter.default)) return fail();
  }
  return contract;
}

export function useTrainingContract(scope: Scope): TrainingContractState {
  const captureLibraryRead = useContext(LibraryReadContext);
  const key = JSON.stringify([scope.taskId, scope.projectId, scope.targetId || null, scope.engine, scope.deviceId]);
  const [revision, setRevision] = useState(0);
  const [read, setRead] = useState<ContractRead>({ key: '', contract: null, pending: true, error: '', isCurrent: () => false });
  useEffect(() => {
    if (!scope.enabled) return;
    let live = true; const libraryCurrent = captureLibraryRead();
    const isCurrent = () => live && libraryCurrent();
    setRead({ key, contract: null, pending: true, error: '', isCurrent });
    void collection<unknown>('/training-contracts').then(result => {
      if (!isCurrent()) return;
      const contract = readContract(result.items, scope);
      setRead({ key, contract, pending: false, error: '', isCurrent });
    }).catch(error => {
      if (isCurrent()) setRead({ key, contract: null, pending: false, error: `无法确认训练参数。${errorMessage(error)} 当前输入保留，可保存草稿后重试。`, isCurrent });
    });
    return () => { live = false; };
  }, [scope.enabled, key, revision, captureLibraryRead]);
  const current = scope.enabled && read.key === key && read.isCurrent();
  const stale = scope.enabled && read.key === key && !read.isCurrent();
  return { ...(current ? read : { key, contract: null, pending: !stale, error: stale ? '工作库读取已失效，无法确认训练参数。当前输入保留，请重新读取后检查。' : '', isCurrent: () => false }), retry: () => setRevision(value => value + 1) };
}

export function trainingParameterErrors(contract: TrainingContract | null, runtime: Runtime): Partial<Record<TrainingParameterName | 'recipe', string>> {
  if (!contract) return {};
  const errors: Partial<Record<TrainingParameterName | 'recipe', string>> = {};
  if (runtime.training_type !== contract.training_type || runtime.update_method !== contract.update_method || runtime.recipe_id !== contract.recipe_id) {
    errors.recipe = '当前训练类型、更新方式或监督配方与声明约束不一致；原值保留，不能检查或提交。';
  }
  for (const [name, label] of fields) {
    const parameter = contract.parameters[name];
    if (!accepts(parameter, runtime[name])) errors[name] = `${label}须为 ${parameter.minimum}—${parameter.maximum} 之间的${parameter.type === 'integer' ? '整数' : '有限数值'}；当前值未被自动调整。`;
  }
  for (const name of fixedFields) {
    const parameter = contract.parameters[name];
    if (!accepts(parameter, runtime[name]) || runtime[name] !== parameter.default) errors[name] = `${fixedLabels[name]}当前仅支持 ${parameter.default}；已保存或未保存的值保持原样，请核对草稿。`;
  }
  return errors;
}

export function TrainingFields({ runtime, state, disabled, acceptedSamples, onChange }: {
  runtime: Runtime; state: TrainingContractState; disabled?: boolean; acceptedSamples?: number; onChange: (field: TrainingParameterName, value: number) => void;
}) {
  const id = useId(); const contract = state.contract; const errors = trainingParameterErrors(contract, runtime);
  const cycles = acceptedSamples && acceptedSamples > 0 && Number.isFinite(runtime.steps) ? Number((runtime.steps! / acceptedSamples).toFixed(2)) : null;
  return <section className="form-stack" aria-label="训练参数约束">
    {state.pending && <p className="muted" role="status">正在读取训练参数约束；确认前不能检查或开始训练，当前输入可以保存。</p>}
    {state.error && <p className="error" role="alert">{state.error}</p>}
    {contract && <><p className="muted">{contract.model_constraint}</p><small className="muted">默认值来源：{contract.source.label}（版本化模板）。约束来源：控制服务与执行器共同支持的范围。下方默认值仅供参考，当前输入不会被替换。</small></>}
    <div className="two-fields" style={{ alignItems: 'start' }}>{fields.map(([name, label, unit]) => {
      const parameter = contract?.parameters[name]; const error = errors[name];
      return <div className="field" key={name}><label htmlFor={`${id}-${name}`}>{label}</label><input id={`${id}-${name}`} type="number" value={runtime[name] ?? ''} disabled={disabled}
        min={parameter?.minimum} max={parameter?.maximum} step={parameter?.type === 'integer' ? 1 : 'any'} aria-invalid={Boolean(error)}
        aria-describedby={parameter ? `${id}-${name}-help${error ? ` ${id}-${name}-error` : ''}` : undefined}
        onChange={event => onChange(name, Number(event.target.value))} />
        {parameter && <small className="muted" id={`${id}-${name}-help`}>{parameter.minimum}—{parameter.maximum}{unit ? ` ${unit}` : ''} · {parameter.type === 'integer' ? '整数' : '数值'} · 默认 {parameter.default}</small>}
        {error && <p className="error" role="alert" id={`${id}-${name}-error`}>{error}</p>}</div>;
    })}</div>
    {contract && <><dl className="facts"><div><dt>批大小</dt><dd>{String(runtime.batch_size)}</dd></div><div><dt>梯度累积</dt><dd>{String(runtime.gradient_accumulation)}</dd></div><div><dt>有效批量</dt><dd>{contract.stopping.effective_batch_size}</dd></div></dl>
      <small className="muted">当前固定为每设备批大小 {contract.parameters.batch_size.default} × 梯度累积 {contract.parameters.gradient_accumulation.default} × 数据并行设备 {contract.stopping.data_parallel_devices} = 有效批量 {contract.stopping.effective_batch_size}。{contract.parameters.optimizer.default}，权重衰减 {contract.parameters.weight_decay.default}，LoRA Dropout {contract.parameters.lora_dropout.default}。</small>
      <small className="muted">{cycles === null ? '数据检查后按可训练样本数换算约几轮；训练仍按步数停止。' : `本次 ${acceptedSamples} 条可训练样本，按文件顺序循环约 ${cycles} 轮；停止条件仍为 ${runtime.steps} 步。`}</small>
      <small className="muted">约束用于下一次运行，无需重启。设备与数据仍需运行前检查，参数符合范围不表示质量达标。</small>
      {(['recipe', ...fixedFields] as const).map(name => errors[name] && <p className="error" role="alert" key={name}>{errors[name]}</p>)}</>}
  </section>;
}
