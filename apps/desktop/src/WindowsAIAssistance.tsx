import { useEffect, useRef, useState } from 'react';
import { api, errorMessage } from './api';
import { InferencePerformance } from './InferencePerformance';
import type { Attempt, Draft, Model, Preflight, Task } from './types';
import { activeStates, Button, ErrorNotice, stateNames } from './ui';

type AdviceSession = {
  targetId: string; projectId: string; targetRevision: number; modelId: string; instruction: string;
  generationTaskId: string; generationRevision: number; attemptId?: string;
  submitKey: string; appliedRevision?: number; originalDraft?: Draft;
};
type Change = { field: string; from: string | number; to: string | number; reason: string };
const storageKey = (project: string, task: string) => 'ailab-windows-advice:' + project + ':' + task;
const specializedPipelines = new Set(['llama-embedding', 'llama-rerank', 'llama-decision', 'llama-ocr']);
const fieldNames: Record<string, string> = {
  'input.prompt': '输入内容', 'runtime.max_tokens': '最大输出 token', 'runtime.steps': '步数',
};

function readSession(task: Task): AdviceSession | null {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey(task.project_id, task.id)) || 'null');
    return value?.targetId === task.id && value?.projectId === task.project_id && value?.generationTaskId && value?.submitKey ? value : null;
  } catch { return null; }
}
function allowedFields(draft: Draft): Record<string, string | number> {
  const fields: Record<string, string | number> = {};
  if (draft.operation === 'generate' && typeof draft.input?.prompt === 'string') fields['input.prompt'] = draft.input.prompt;
  if (typeof draft.runtime?.max_tokens === 'number') fields['runtime.max_tokens'] = draft.runtime.max_tokens;
  if (typeof draft.runtime?.steps === 'number') fields['runtime.steps'] = draft.runtime.steps;
  return fields;
}
function promptFor(instruction: string, draft: Draft) {
  const fields = allowedFields(draft);
  const visible = Object.fromEntries(Object.entries(fields).map(([key, value]) =>
    [key, typeof value === 'string' && value.length > 800 ? { length: value.length, omitted: true } : value]));
  const descriptions: Record<string, string> = {
    'input.prompt': '用户给试用模型的输入内容。',
    'runtime.max_tokens': '本次回答最多生成的 token 数，取值 1 至 2048。调低上限可能截短回答。输入窗口大小由上下文设置决定。',
    'runtime.steps': draft.operation === 'train' ? '训练步数。' : '生成时的采样步数，更多步通常需要更多时间。',
  };
  return [
    '你是 AiLab 本地配置助手。根据字段含义用简短中文回答用户。',
    '任务：' + JSON.stringify({kind: draft.kind, operation: draft.operation}),
    '当前字段：' + JSON.stringify(visible),
    ...Object.keys(fields).map(field => field + '：' + descriptions[field]),
    '用户只问问题时直接回答。用户要求改动时，输出包含 advice 和 changes 的 JSON 对象。',
    'advice 是给用户的说明。changes 是数组，每项包含 field（当前字段名）、to（新值，数字不加引号）、reason（修改原因）。',
    '用户要求：' + JSON.stringify(instruction),
  ].join('\n');
}
function parseAdvice(raw: string, draft: Draft): { advice: string; changes: Change[] } {
  let value: unknown;
  try {
    const text = raw.trim().replace(/^\x60\x60\x60(?:json)?\s*/i, '').replace(/\s*\x60\x60\x60$/, '');
    value = JSON.parse(text);
  } catch { return { advice: raw, changes: [] }; }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { advice: raw, changes: [] };
  const result = value as { advice?: unknown; title?: unknown; changes?: unknown };
  const advice = typeof result.advice === 'string' && result.advice.trim() ? result.advice : raw;
  if (!Array.isArray(result.changes) || result.changes.length > 3) return { advice, changes: [] };
  const fields = allowedFields(draft), seen = new Set<string>(), changes: Change[] = [];
  for (const item of result.changes) {
    if (!item || typeof item !== 'object' || typeof item.field !== 'string' || !Object.hasOwn(fields, item.field) || seen.has(item.field))
      return { advice, changes: [] };
    const field = item.field;
    // Small instruction models sometimes quote integral JSON values.
    const to = field !== 'input.prompt' && typeof item.to === 'string' && /^\d{1,4}$/.test(item.to)
      ? Number(item.to) : item.to;
    const valid = field === 'input.prompt'
      ? typeof to === 'string' && to.trim().length > 0 && to.length <= 2000
      : Number.isInteger(to) && to >= 1 && to <= (field === 'runtime.max_tokens' ? 2048 : 100);
    if (!valid || fields[field] === to || typeof item.reason !== 'string' || !item.reason.trim()) return { advice, changes: [] };
    seen.add(field);
    changes.push({ field, from: fields[field], to, reason: item.reason.slice(0, 500) });
  }
  return { advice, changes };
}

export function WindowsAIAssistance({ task, models, hasUnsavedChanges, taskBusy, onTaskChanged, onApplyingChange }: {
  task: Task; models: Model[]; hasUnsavedChanges: boolean; taskBusy: boolean;
  onTaskChanged: (task: Task) => void; onApplyingChange: (busy: boolean) => void;
}) {
  const available = models.filter(model => (model.modality || model.kind) === 'text' &&
    model.execution_available === true && !specializedPipelines.has(model.pipeline || ''));
  const [session, setSession] = useState<AdviceSession | null>(() => readSession(task));
  const [selectedModel, setSelectedModel] = useState(session?.modelId || '');
  const modelId = session?.modelId || available.find(m => m.id === selectedModel)?.id ||
    available.find(m => m.id === task.draft.model_id)?.id || available[0]?.id || '';
  const [instruction, setInstruction] = useState(session?.instruction || '');
  // A preflight refers to a native plan held in this process only.
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const lifetime = useRef(true);
  useEffect(() => {
    lifetime.current = true;
    return () => { lifetime.current = false; };
  }, []);
  function save(value: AdviceSession | null) {
    if (value) localStorage.setItem(storageKey(task.project_id, task.id), JSON.stringify(value));
    else localStorage.removeItem(storageKey(task.project_id, task.id));
    if (lifetime.current) setSession(value);
  }
  useEffect(() => {
    const attemptId = session?.attemptId;
    if (!attemptId) return;
    let cancelled = false, timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api<Attempt>('GET', '/attempts/' + attemptId + '?project_id=' + encodeURIComponent(task.project_id));
        if (cancelled) return;
        setAttempt(current);
        if (activeStates.has(current.state)) timer = setTimeout(poll, 800);
      } catch (e) { if (!cancelled) { setError(errorMessage(e)); timer = setTimeout(poll, 2000); } }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [session?.attemptId, task.project_id]);
  async function prepare() {
    if (!modelId || !instruction.trim() || busy || hasUnsavedChanges || taskBusy) return;
    setBusy(true); setError('');
    try {
      let current = session;
      if (current && current.targetRevision !== task.draft_revision) throw Error('任务草稿已改变，请重新请求建议。');
      if (!current) {
        const saved = await api<Task>('POST', '/ai/generation-tasks', {
          target_id: task.id, project_id: task.project_id, expected_revision: task.draft_revision,
          model_id: modelId, prompt: promptFor(instruction.trim(), task.draft),
          thinking: available.find(model => model.id === modelId)?.supports_thinking ? 'disabled' : 'default',
        });
        current = { targetId:task.id, projectId:task.project_id, targetRevision:task.draft_revision,
          modelId, instruction:instruction.trim(), generationTaskId:saved.id, generationRevision:saved.draft_revision, submitKey:crypto.randomUUID() };
        if (!lifetime.current) return;
        save(current);
      } else {
        // A submit receipt can be lost when the panel closes while the worker is starting.
        const runs = await api<{items: (Attempt & {idempotency_key?: string})[]}>('GET',
          '/attempts?project_id=' + encodeURIComponent(task.project_id) + '&task_id=' + encodeURIComponent(current.generationTaskId));
        const { submitKey } = current;
        const existing = runs.items.find(run => run.idempotency_key === submitKey);
        if (!lifetime.current) return;
        if (existing) {
          save({ ...current, attemptId: existing.id });
          setAttempt(existing);
          return;
        }
      }
      const preflight = await api<Preflight>('POST', '/tasks/' + current.generationTaskId + '/preflight', { draft_revision:current.generationRevision });
      if (lifetime.current) setPreflight(preflight);
    } catch (e) { if (lifetime.current) setError(errorMessage(e)); }
    finally { if (lifetime.current) setBusy(false); }
  }
  async function generate() {
    if (!session || !preflight?.can_submit || stale || busy || taskBusy || hasUnsavedChanges) return;
    setBusy(true); setError('');
    try {
      const result = await api<Attempt>('POST', '/tasks/' + session.generationTaskId + '/attempts',
        { preflight_id:preflight.preflight_id, expected_revision:session.generationRevision }, session.submitKey);
      if (readSession(task)?.submitKey === session.submitKey) save({ ...session, attemptId: result.id });
      if (lifetime.current) setAttempt(result);
    } catch (e) { if (lifetime.current) { setError(errorMessage(e)); setPreflight(null); } }
    finally { if (lifetime.current) setBusy(false); }
  }
  async function apply(changes: Change[], undo = false) {
    if (!session || busy || taskBusy || hasUnsavedChanges || task.immutable_draft || task.draft.checkpoint_id) return;
    const revision = undo ? session.appliedRevision : session.targetRevision;
    if (revision !== task.draft_revision) { setError('任务草稿已改变，请重新生成建议。'); return; }
    setBusy(true); setError(''); onApplyingChange(true);
    try {
      const fresh = await api<Task>('GET', '/tasks/' + task.id);
      if (fresh.draft_revision !== revision) throw Error('任务草稿已改变，请重新生成建议。');
      const draft = undo ? session.originalDraft : structuredClone(fresh.draft);
      if (!draft) throw Error('缺少可撤销的原草稿。');
      if (!undo) for (const change of changes) {
        if (change.field === 'input.prompt') draft.input.prompt = change.to as string;
        else if (change.field === 'runtime.max_tokens') draft.runtime.max_tokens = change.to as number;
        else if (change.field === 'runtime.steps') draft.runtime.steps = change.to as number;
      }
      const updated = await api<Task>('PATCH', '/tasks/' + task.id + '/draft', { expected_revision:revision, draft });
      // Closing the side panel leaves the workbench mounted. It still needs the new revision.
      onTaskChanged(updated);
      save(undo ? { ...session, appliedRevision:undefined, originalDraft:undefined, targetRevision:updated.draft_revision }
        : { ...session, appliedRevision:updated.draft_revision, originalDraft:fresh.draft });
    } catch (e) { if (lifetime.current) setError(errorMessage(e)); }
    finally { onApplyingChange(false); if (lifetime.current) setBusy(false); }
  }
  async function cancel() {
    if (!attempt || busy) return;
    setBusy(true);
    try {
      const updated = await api<Attempt>('POST', '/attempts/' + attempt.id + '/cancel', {});
      if (lifetime.current) setAttempt(updated);
    } catch (e) { if (lifetime.current) setError(errorMessage(e)); }
    finally { if (lifetime.current) setBusy(false); }
  }
  const active = !!attempt && activeStates.has(attempt.state);
  const raw = attempt?.state === 'succeeded' ? attempt.output_text || '' : '';
  const advice = raw ? parseAdvice(raw, session?.originalDraft || task.draft) : null;
  const stale = !!session && task.draft_revision !== (session.appliedRevision ?? session.targetRevision);
  if (task.immutable_draft || task.draft.checkpoint_id || !['generate', 'train'].includes(task.operation))
    return <p className="muted">打开可编辑的试用或训练草稿，即可使用本地模型生成建议。</p>;
  return <section className="review-box form-stack" aria-label="AI 建议助手">
    <h2>AI 建议</h2>
    <p className="muted">选择当前项目中已登记的本地语言模型，输入问题后生成建议。应用修改需要你确认。</p>
    <label>本地建议模型<select aria-label="本地建议模型" value={modelId} disabled={busy || !!session || !available.length}
      onChange={e => setSelectedModel(e.target.value)}>{!available.length && <option value="">选择本地语言模型</option>}
      {available.map(model => <option key={model.id} value={model.id}>{model.name}</option>)}</select></label>
    {!available.length && <p>当前项目没有可用的本地语言模型，请先在模型库下载或导入并登记。</p>}
    <label>你希望调整什么<textarea aria-label="建议问题" rows={3} maxLength={1000} value={instruction}
      disabled={busy || !!session} onChange={e => setInstruction(e.target.value)} placeholder="例如：帮我把输出长度调整为 64，并说明影响。" /></label>
    <p className="muted">建议在本机 CPU 上运行，发送给模型的内容包括你的问题及当前任务的类型和可修改字段。</p>
    {(hasUnsavedChanges || taskBusy) && <p className="warning">请先完成当前草稿保存或操作。</p>}
    <ErrorNotice message={error} />
    {stale && <p className="warning">草稿已改变，请重新请求建议。</p>}
    {!session?.attemptId && <>{preflight && <div className="preflight">
      <strong>{preflight.can_submit ? '检查通过，可以生成建议' : '模型检查未通过'}</strong>
      {preflight.blocking.map((item, index) => <p className="error" key={index}>{item.message}</p>)}
      {preflight.warnings.map((item, index) => <p className="warning" key={index}>{item.message}</p>)}
    </div>}{preflight?.can_submit
      ? <Button primary busy={busy} disabled={stale || taskBusy || hasUnsavedChanges} onClick={generate}>生成建议（本机）</Button>
      : <Button busy={busy} disabled={stale || !modelId || !instruction.trim() || taskBusy || hasUnsavedChanges} onClick={prepare}>检查建议请求</Button>}</>}
    {session?.attemptId && <div role="status"><strong>建议模型：{stateNames[attempt?.state || ''] || '读取中'}</strong>
      {active && attempt?.allowed_actions?.includes('cancel') && <Button busy={busy} onClick={cancel}>取消建议生成</Button>}
      {attempt?.error && <ErrorNotice message={attempt.error.message} />}
      {attempt?.performance && !active && <InferencePerformance attempt={attempt} />}
      {attempt?.output_text && (!advice || advice.advice !== raw) && <details open={active}><summary>模型原始回答</summary><pre aria-label="建议模型原始回答">{attempt.output_text}</pre></details>}
      {attempt?.state === 'succeeded' && !raw.trim() && <p>模型返回了空回答，可重新提问或更换建议模型。</p>}
    </div>}
    {advice && <section aria-label="建议变更预览"><h3>建议</h3><p>{advice.advice}</p>
      {advice.changes.length > 0 && <><dl className="facts">{advice.changes.map(change =>
        <div key={change.field}><dt>{fieldNames[change.field]}</dt><dd>{String(change.from)} → {String(change.to)}<br />{change.reason}</dd></div>)}</dl>
        {!session?.appliedRevision && <Button primary busy={busy} disabled={stale || taskBusy || hasUnsavedChanges} onClick={() => apply(advice.changes)}>应用这些字段</Button>}
        {session?.appliedRevision && <Button busy={busy} disabled={stale || taskBusy || hasUnsavedChanges} onClick={() => apply(advice.changes, true)}>撤销本次应用</Button>}
      </>}
    </section>}
    {session && !active && (!session.attemptId || attempt || error) && <Button disabled={busy} onClick={() => { save(null); setAttempt(null); setPreflight(null); setError(''); }}>重新请求建议</Button>}
  </section>;
}
