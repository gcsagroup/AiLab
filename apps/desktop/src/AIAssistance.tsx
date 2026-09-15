import { useEffect, useRef, useState } from 'react';
import { FileCheck2, Play, Undo2 } from 'lucide-react';
import { api, errorMessage } from './api';
import type { Attempt, Model, Preflight, Task } from './types';
import { activeStates, Badge, Button, ErrorNotice, stateNames } from './ui';

type AIField = { field: string; from: string | number; to: string | number; reason: string; impact: string };
type AIRequest = { id: string; target_task_id: string; target_revision: number; generation_task_id: string; model_id: string; status: string; proposal_id: string | null; context: { instruction: string; sent_scope: string; long_prompt_scope: string; allowed_fields: Record<string, unknown> }; connection: { type: string; engine: string; model_name: string; network: boolean }; parse_failures: { code: string; message: string }[] };
type AIProposal = { id: string; target_id: string; expected_revision: number; title: string; changes: AIField[]; status: 'proposed' | 'applied' | 'undone' | 'no_changes'; source_attempt_id: string; source_artifact_id: string; raw_sha256: string; requires_preflight: boolean; execution_actions: unknown[]; application: { to_revision: number } | null };
type AIChange = { proposal: AIProposal; task: Task; requires_preflight: boolean; execution_actions: unknown[] };
const fieldLabels: Record<string, string> = { 'input.prompt': '输入内容', 'runtime.max_tokens': '最大输出 token', 'runtime.steps': '训练步数', 'runtime.max_seq_length': '最大序列长度' };

export function AIAssistance({ task, models, hasUnsavedChanges = false, taskBusy = false, onTaskChanged, onApplyingChange }: { task: Task; models: Model[]; hasUnsavedChanges?: boolean; taskBusy?: boolean; onTaskChanged: (task: Task) => void; onApplyingChange?: (applying: boolean) => void }) {
  const available = models.filter(model => (model.modality || 'text') === 'text' && !model.model_config?.quantization && !model.model_config?.quantization_config && !model.conversion);
  const [modelId, setModelId] = useState(available.find(model => model.id === task.draft?.model_id)?.id || available[0]?.id || '');
  const [instruction, setInstruction] = useState(''); const [request, setRequest] = useState<AIRequest | null>(null);
  const [check, setCheck] = useState<Preflight | null>(null); const [attempt, setAttempt] = useState<Attempt | null>(null); const [proposal, setProposal] = useState<AIProposal | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [parseFailed, setParseFailed] = useState(false); const [target, setTarget] = useState(task);
  const keys = useRef<Record<string, string>>({}); const currentTarget = useRef(task.id); currentTarget.current = task.id;
  const unsaved = useRef(hasUnsavedChanges); unsaved.current = hasUnsavedChanges;
  const parsed = useRef<string | null>(null);
  const keyFor = (action: string) => keys.current[action] ||= crypto.randomUUID();
  const active = !!attempt && activeStates.has(attempt.state);
  const supported = task.kind === 'text' && ['generate', 'train'].includes(task.operation) && !task.draft?.checkpoint_id && !(task as Task & { immutable_draft?: boolean }).immutable_draft;

  useEffect(() => { setTarget(task); }, [task.id, task.draft_revision]);
  useEffect(() => {
    let closed = false;
    setRequest(null); setCheck(null); setAttempt(null); setProposal(null); setError(''); setParseFailed(false); setInstruction(''); setBusy(false); setModelId(available.find(model => model.id === task.draft?.model_id)?.id || available[0]?.id || ''); parsed.current = null; keys.current = {};
    if (!supported) return;
    api<{ items: AIRequest[] }>('GET', `/ai/requests?target_task_id=${encodeURIComponent(task.id)}`).then(async result => {
      const latest = result.items.at(-1);
      if (closed || !latest) return;
      setRequest(latest); setModelId(latest.model_id); setInstruction(latest.context.instruction);
      if (latest.proposal_id) {
        const value = await api<AIProposal>('GET', `/ai/proposals/${latest.proposal_id}`);
        if (!closed) setProposal(value);
      }
      const runs = await api<{ items: Attempt[] }>('GET', `/attempts?task_id=${encodeURIComponent(latest.generation_task_id)}`);
      if (!closed) {
        setAttempt(runs.items.at(-1) || null);
        if (latest.status === 'invalid_response') { parsed.current = runs.items.at(-1)?.id || null; setParseFailed(true); setError(latest.parse_failures.at(-1)?.message || '原回答未通过结构化检查。'); }
      }
    }).catch(value => { if (!closed) setError(errorMessage(value)); });
    return () => { closed = true; };
  }, [task.id, supported]);

  useEffect(() => {
    if (!attempt || !request || proposal || parsed.current === attempt.id) return;
    let closed = false; let timer: ReturnType<typeof setTimeout> | undefined;
    const attemptId = attempt.id, requestId = request.id;
    async function poll() {
      try {
        const latest = await api<Attempt>('GET', `/attempts/${attemptId}`);
        if (closed) return;
        setAttempt(latest);
        if (activeStates.has(latest.state)) { timer = setTimeout(poll, 1000); return; }
        if (latest.compute_outcome === 'succeeded' && latest.collection_state === 'succeeded') {
          parsed.current = latest.id;
          try {
            const value = await api<AIProposal>('POST', `/ai/requests/${requestId}/proposals`, { attempt_id: latest.id }, keyFor(`parse:${latest.id}`));
            if (!closed) { setProposal(value); setParseFailed(false); setError(''); }
          } catch (value) { if (!closed) { setParseFailed(true); setError(errorMessage(value)); } }
        }
      } catch (value) { if (!closed) { setError(errorMessage(value)); timer = setTimeout(poll, 3000); } }
    }
    void poll();
    return () => { closed = true; if (timer) clearTimeout(timer); };
  }, [attempt?.id, request?.id, proposal?.id]);

  function reset() { setRequest(null); setCheck(null); setAttempt(null); setProposal(null); setParseFailed(false); setError(''); parsed.current = null; keys.current = {}; }
  async function reread() {
    if (!request || !attempt || proposal || busy || attempt.compute_outcome !== 'succeeded' || attempt.collection_state !== 'succeeded') return;
    const taskId = task.id; setBusy(true); setError('');
    try {
      const value = await api<AIProposal>('POST', `/ai/requests/${request.id}/proposals`, { attempt_id: attempt.id }, keyFor(`parse:${attempt.id}`));
      if (currentTarget.current === taskId) { setProposal(value); setParseFailed(false); }
    } catch (value) { if (currentTarget.current === taskId) { setParseFailed(true); setError(errorMessage(value)); } }
    finally { if (currentTarget.current === taskId) setBusy(false); }
  }
  async function prepare() {
    if (!modelId || !instruction.trim() || hasUnsavedChanges || taskBusy) return;
    const taskId = task.id; setBusy(true); setError('');
    try {
      const value = request || await api<AIRequest>('POST', '/ai/requests', { target_task_id: taskId, expected_revision: target.draft_revision, model_id: modelId, instruction }, keyFor('request'));
      if (currentTarget.current !== taskId) return;
      setRequest(value);
      const checked = await api<Preflight>('POST', `/tasks/${value.generation_task_id}/preflight`, { draft_revision: 1 });
      if (currentTarget.current === taskId) setCheck(checked);
    } catch (value) { if (currentTarget.current === taskId) setError(errorMessage(value)); }
    finally { if (currentTarget.current === taskId) setBusy(false); }
  }
  async function generate() {
    if (!request || !check?.can_submit || hasUnsavedChanges || taskBusy) return;
    const taskId = task.id; setBusy(true); setError('');
    try {
      const value = await api<Attempt>('POST', `/tasks/${request.generation_task_id}/attempts`, { preflight_id: check.preflight_id, expected_revision: 1 }, keyFor(`generate:${request.id}`));
      if (currentTarget.current === taskId) { setAttempt(value); setCheck(null); }
    } catch (value) { if (currentTarget.current === taskId) setError(errorMessage(value)); }
    finally { if (currentTarget.current === taskId) setBusy(false); }
  }
  async function change(undo: boolean) {
    if (!proposal || hasUnsavedChanges || taskBusy) return;
    const taskId = task.id; const action = undo ? 'undo' : 'apply'; setBusy(true); setError('');
    try {
      onApplyingChange?.(true);
      const value = await api<AIChange>('POST', `/ai/proposals/${proposal.id}/${action}`, { expected_revision: target.draft_revision }, keyFor(`${action}:${proposal.id}:${target.draft_revision}`));
      if (currentTarget.current === taskId) {
        setProposal(value.proposal); setTarget(value.task); setCheck(null);
        if (unsaved.current) setError('已保存草稿的建议操作已完成，但当前还有新的未保存修改；未覆盖本地输入，请刷新并检查差异。');
        else onTaskChanged(value.task);
      }
    } catch (value) { if (currentTarget.current === taskId) setError(errorMessage(value)); }
    finally { onApplyingChange?.(false); if (currentTarget.current === taskId) setBusy(false); }
  }
  async function cancel() {
    if (!attempt) return; const taskId = task.id; setBusy(true); setError('');
    try { const value = await api<Attempt>('POST', `/attempts/${attempt.id}/cancel`, { expected_state_version: attempt.state_version }, keyFor(`cancel:${attempt.id}:${attempt.state_version}`)); if (currentTarget.current === taskId) setAttempt(value); }
    catch (value) { if (currentTarget.current === taskId) setError(errorMessage(value)); } finally { if (currentTarget.current === taskId) setBusy(false); }
  }

  const stale = !!proposal && (proposal.status === 'proposed' ? target.draft_revision !== proposal.expected_revision : proposal.status === 'applied' ? target.draft_revision !== proposal.application?.to_revision : false);
  return <section className="review-box form-stack" aria-label="AI 建议助手">
    <div className="section-title"><h2>AI 建议</h2><Badge>建议模式 · 由你决定</Badge></div>
    <p className="muted">先查看模型回答和字段变更，点击应用才修改草稿。任务执行需要你另行检查并开始。</p>
    {!supported ? <p className="muted">当前仅支持普通文本生成与训练草稿；媒体、固定计划和检查点任务暂不提供建议。</p> : <>
      {taskBusy && <p className="warning">当前任务正在保存或检查，请稍后再操作建议。</p>}
      {hasUnsavedChanges && <p className="warning">当前有未保存的修改，请先保存草稿，再请求或应用建议。</p>}
      <label>本地建议模型<select aria-label="本地建议模型" disabled={busy || active || !!request} value={modelId} onChange={event => { setModelId(event.target.value); reset(); }}><option value="">选择未量化 Qwen2.5-0.5B-Instruct</option>{available.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
      <label>你希望调整什么<textarea aria-label="建议问题" rows={3} maxLength={2000} disabled={busy || active || !!request} value={instruction} onChange={event => { setInstruction(event.target.value); reset(); }} placeholder="例如：把首次生成的最大输出调整为 64 token，并说明影响。" /></label>
      <p className="muted">本机 MLX 独立进程，不使用网络。建议模型仅接收你的问题和当前步骤的白名单字段；不会读取数据集、媒体、日志或凭证。</p>
      {request && <details open><summary>实际发送范围 · {request.connection.model_name}</summary><p>{request.context.sent_scope}</p><p className="muted">{request.context.long_prompt_scope}</p><pre aria-label="发送上下文">{JSON.stringify(request.context, null, 2)}</pre></details>}
      {!attempt && !proposal && <>{check && <div className="preflight"><strong>{check.can_submit ? '检查通过，尚未调用建议模型' : '建议模型尚未准备好'}</strong>{check.blocking.map((item, index) => <p className="error" key={index}>{item.message}</p>)}{check.warnings.map((item, index) => <p className="warning" key={index}>{item.message}</p>)}</div>}{check?.can_submit ? <Button primary busy={busy} disabled={hasUnsavedChanges || taskBusy} onClick={generate}><Play size={16} />生成建议（本机）</Button> : <Button busy={busy} disabled={!modelId || !instruction.trim() || hasUnsavedChanges || taskBusy} onClick={prepare}><FileCheck2 size={16} />检查建议请求</Button>}</>}
      {attempt && <div role="status"><strong>建议模型：{stateNames[attempt.state] || attempt.state}</strong>{active && <p className="muted">只生成建议，当前任务草稿尚未修改。</p>}{active && attempt.allowed_actions?.includes('cancel') && <Button busy={busy} onClick={cancel}>取消建议生成</Button>}{['failed', 'cancelled'].includes(attempt.state) && <p className="warning">建议生成未完成，当前任务保持原样。可在任务中心查看运行记录。</p>}{attempt.output_text && <details><summary>查看模型原始回答</summary><pre aria-label="建议模型原始回答">{attempt.output_text}</pre></details>}</div>}
      {proposal && <section aria-label="建议变更预览"><h3>{proposal.title}</h3><p className="muted">对应草稿版本 {proposal.expected_revision}，需要重新检查；没有执行动作。</p>{proposal.changes.length ? <table><thead><tr><th>字段</th><th>旧值</th><th>新值</th><th>原因与影响</th></tr></thead><tbody>{proposal.changes.map(item => <tr key={item.field}><th>{fieldLabels[item.field] || item.field}</th><td><pre>{String(item.from) || '（空）'}</pre></td><td><pre>{String(item.to)}</pre></td><td>{item.reason}<br />{item.impact}</td></tr>)}</tbody></table> : <p>模型没有提出可应用的字段变更。</p>}
        {stale && <p className="warning">草稿已有后续修改，此建议不能覆盖当前内容。请重新请求建议。</p>}
        {proposal.status === 'proposed' && <Button primary busy={busy} disabled={stale || hasUnsavedChanges || taskBusy} onClick={() => change(false)}>应用这些字段</Button>}
        {proposal.status === 'applied' && <><p role="status">建议已应用，任务尚未执行。请重新检查任务配置。</p><Button busy={busy} disabled={stale || hasUnsavedChanges || taskBusy} onClick={() => change(true)}><Undo2 size={16} />撤销本次应用</Button></>}
        {proposal.status === 'undone' && <p role="status">已撤销本次建议，恢复原字段值。</p>}
        <details><summary>建议来源</summary><p>运行：{proposal.source_attempt_id}</p><p>原始回答 SHA256：{proposal.raw_sha256}</p></details>
      </section>}
      <ErrorNotice message={error} />
      {parseFailed && attempt && !proposal && <div><Button busy={busy} onClick={reread}>重新读取这次建议</Button><p className="muted">只重新读取和检查本次原回答，不再次调用模型；原回答无效时会继续显示错误。</p></div>}
      {request && !active && <Button disabled={busy} onClick={reset}>重新请求建议</Button>}
    </>}
  </section>;
}
