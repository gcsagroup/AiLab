import { useContext, useEffect, useRef, useState } from 'react';
import { BookOpen, Plus, Star } from 'lucide-react';
import { api, errorMessage } from './api';
import { LibraryReadContext } from './LibraryReadContext';
import type { Task, Work, WorkRecipeView } from './types';
import { Badge, Button, Dialog, ErrorNotice } from './ui';

const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const display = (value: unknown) => value === undefined ? '未记录' : value === null ? '无' : typeof value === 'object' ? JSON.stringify(value) : String(value);
const parameterLabels: Record<string, string> = {
  engine: '执行引擎', device_id: '设备', precision: '计算精度', seed: '随机种子', max_tokens: '最大输出 token', temperature: '温度', top_p: 'Top-p',
  context_limit: '上下文上限', prompt_tokens: '输入 token', cpu_threads: 'CPU 逻辑核心数', kv_precision: 'KV 缓存精度', prefill_step_size: '预填充分块', overflow: '溢出处理',
  stop: '停止词', stream: '流式输出', thinking: '思考模式', size: '图片边长', cfg: '提示词引导强度', steps: '生成步数',
  frames: '视频帧数', fps: '每秒帧数', voice: '音色', speed: '语速', sample_rate: '采样率',
};

export function RecipeDetails({ view }: { view: WorkRecipeView }) {
  const recipe = view.recipe, input = record(recipe.input), runtime = record(recipe.runtime);
  const requested = record(recipe.requested_config ?? recipe.runtime), effective = record(recipe.effective_config);
  const target = record(recipe.execution_target), environment = record(recipe.environment);
  const names = Object.keys(parameterLabels).filter(key => key in requested || key in effective);
  const identity = [
    ['原任务', recipe.task_id], ['原运行', view.source_attempt_id], ['原作品', view.source_work_id], ['原产物', view.work.artifact_id],
    ['配方摘要', view.source_recipe_digest], ['基座模型', recipe.model_id], ['模型版本', recipe.model_version_id], ['模型摘要', recipe.model_manifest_digest],
    ['适配器', recipe.adapter_id ?? null], ...(recipe.adapter_id ? [['适配器版本', recipe.adapter_version_id], ['适配器摘要', recipe.adapter_manifest_digest], ['适配器训练配方摘要', recipe.adapter_training_recipe_digest]] : []),
    ...(input.material_id ? [['素材版本', recipe.material_version_id], ['素材摘要', recipe.input_image_manifest_digest]] : []),
    ['原执行位置', recipe.execution_target_id ? target.name ?? recipe.execution_target_id : '本机'],
    ...(recipe.execution_target_id ? [['执行目标编号', recipe.execution_target_id], ['原服务地址', target.origin], ['原执行器', target.executor_id]] : []),
    ['环境摘要', environment.digest],
  ];
  return <div className="form-stack recipe-details">
    <p className="muted">配方来自保存作品时的生成记录。载入后可修改新草稿；原输出和人工修订各自保留。</p>
    <section aria-label="原生成输入"><h3>原生成输入</h3>
      {input.prompt !== undefined && <><strong>{recipe.kind === 'audio' ? '原配音文案' : '输入内容'}</strong><p className="work-text">{display(input.prompt)}</p></>}
      {input.negative_prompt !== undefined && <><strong>负面提示词</strong><p className="work-text">{display(input.negative_prompt) || '未填写'}</p></>}
      {input.material_id !== undefined && <dl className="facts"><div><dt>原图片素材</dt><dd>{display(input.material_id)}</dd></div></dl>}
    </section>
    <section aria-label="原运行参数"><h3>原运行参数</h3><div className="recipe-table-scroll"><table className="recipe-table"><thead><tr><th>参数</th><th>当时请求</th><th>当时实际配置</th></tr></thead><tbody>
      {names.map(key => <tr key={key}><th scope="row">{parameterLabels[key]}</th><td>{display(requested[key])}</td><td>{display(effective[key])}</td></tr>)}
    </tbody></table></div><p className="muted">未记录的实际值不会用请求值填充。新草稿保存后仍需检查配置。</p></section>
    <details><summary>来源与版本</summary><dl className="facts">{identity.map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd>{display(value)}</dd></div>)}</dl></details>
    <details><summary>封存配置详情</summary><pre className="recipe-config">{JSON.stringify({ runtime, requested_config: requested, effective_config: effective, environment }, null, 2)}</pre></details>
  </div>;
}

export function WorkRecipeActions({ work, projectId, reuseKeys, onCreated, onUpdated }: {
  work: Work; projectId: string; reuseKeys: Map<string, string>; onCreated: (task: Task) => void; onUpdated: () => void;
}) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const epoch = useRef(0), inFlight = useRef(false);
  const [opened, setOpened] = useState(false), [view, setView] = useState<WorkRecipeView | null>(null);
  const [busy, setBusy] = useState<'read' | 'reuse' | 'favorite' | null>(null), [error, setError] = useState('');
  const [favorite, setFavorite] = useState(work.favorite === true);
  const keyScope = `${projectId}:${work.id}`;
  useEffect(() => {
    epoch.current++; inFlight.current = false; setOpened(false); setView(null); setError(''); setBusy(null); setFavorite(work.favorite === true);
    return () => { epoch.current++; };
  }, [work.id, projectId]);
  useEffect(() => { setFavorite(work.favorite === true); }, [work.favorite]);
  function begin(action: 'read' | 'reuse' | 'favorite') {
    if (inFlight.current) return null;
    const libraryCurrent = captureLibraryRead();
    if (!libraryCurrent()) return null;
    if (work.project_id && work.project_id !== projectId) { setError('作品不属于当前项目。'); return null; }
    inFlight.current = true; setBusy(action); setError('');
    const generation = epoch.current;
    return { valid: () => generation === epoch.current && libraryCurrent(), sameRequest: () => generation === epoch.current };
  }
  function finish(current: NonNullable<ReturnType<typeof begin>>) { if (current.sameRequest()) { inFlight.current = false; setBusy(null); } }
  async function read() {
    const current = begin('read'); if (!current) return;
    setOpened(true); setView(null);
    try {
      const value = await api<WorkRecipeView>('GET', `/works/${encodeURIComponent(work.id)}/recipe?project_id=${encodeURIComponent(projectId)}`);
      if (!current.valid()) return;
      if (value.work.id !== work.id || value.work.project_id !== projectId || value.source_work_id !== work.id || value.source_attempt_id !== work.attempt_id || value.recipe.project_id !== projectId) throw new Error('读取的配方来源与当前作品不符。');
      setView(value);
    } catch (value) { if (current.valid()) setError(errorMessage(value)); }
    finally { finish(current); }
  }
  async function reuse() {
    const current = begin('reuse'); if (!current) return;
    const key = reuseKeys.get(keyScope) || crypto.randomUUID(); reuseKeys.set(keyScope, key);
    try {
      const task = await api<Task>('POST', `/works/${encodeURIComponent(work.id)}/reuse-task`, { project_id: projectId }, key);
      if (!current.valid()) return;
      if (!task.id || task.project_id !== projectId || task.source_work_id !== work.id || task.source_attempt_id !== work.attempt_id || !task.source_recipe_digest || task.operation !== 'generate' || task.draft.operation !== 'generate') throw new Error('新草稿回执与当前作品不符，请重试读取同一份回执。');
      reuseKeys.delete(keyScope); setOpened(false); onCreated(task);
    } catch (value) { if (current.valid()) setError(`${errorMessage(value)} 再次载入会重试同一次新建。`); }
    finally { finish(current); }
  }
  async function toggleFavorite() {
    const current = begin('favorite'); if (!current) return;
    const requested = !favorite;
    try {
      const saved = await api<Work>('PATCH', `/works/${encodeURIComponent(work.id)}/favorite`, { project_id: projectId, favorite: requested });
      if (!current.valid()) return;
      if (saved.id !== work.id || saved.project_id !== projectId || saved.favorite !== requested) throw new Error('收藏回执与当前作品不符，请重新读取作品。');
      setFavorite(requested); onUpdated();
    } catch (value) { if (current.valid()) setError(errorMessage(value)); }
    finally { finish(current); }
  }
  return <>
    <div className="card-actions" aria-label="作品配方与收藏">
      <Button disabled={!!busy} onClick={() => void read()}><BookOpen size={14} />查看配方</Button>
      <Button disabled={!!busy} busy={busy === 'reuse'} onClick={() => void reuse()}><Plus size={14} />用此配方新建任务</Button>
      <Button disabled={!!busy} busy={busy === 'favorite'} aria-pressed={favorite} onClick={() => void toggleFavorite()}><Star size={14} fill={favorite ? 'currentColor' : 'none'} />{favorite ? '取消收藏' : '收藏'}</Button>
      {favorite && <Badge>已收藏</Badge>}
    </div>
    {!opened && <ErrorNotice message={error} />}
    {opened && <Dialog title={`${work.name || '作品'} · 生成配方`} wide preventClose={busy === 'reuse'} onClose={() => { if (busy === 'reuse') return; epoch.current++; inFlight.current = false; setOpened(false); setBusy(null); setError(''); }}>
      <ErrorNotice message={error} />{busy === 'read' && <p className="muted">正在读取原生成配方…</p>}
      {view && <RecipeDetails view={view} />}
      <div className="dialog-footer"><small>只新建草稿，开始运行前仍需检查配置。</small>{view ? <Button primary busy={busy === 'reuse'} disabled={!!busy} onClick={() => void reuse()}>用此配方新建任务</Button> : <Button busy={busy === 'read'} onClick={() => void read()}>重新读取配方</Button>}</div>
    </Dialog>}
  </>;
}
