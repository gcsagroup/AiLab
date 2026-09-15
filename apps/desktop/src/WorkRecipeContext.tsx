import { useContext, useEffect, useState } from 'react';
import { api, errorMessage } from './api';
import { LibraryReadContext } from './LibraryReadContext';
import { RecipeDetails } from './WorkRecipes';
import type { Adapter, Draft, Material, Model, Task, WorkRecipeView } from './types';
import { Button, ErrorNotice } from './ui';

type ReferenceKind = 'models' | 'adapters' | 'materials' | 'execution-targets';
type Reference = { kind: ReferenceKind; id: string; value?: Record<string, unknown>; error?: string };
const referenceNames: Record<ReferenceKind, string> = { models: '模型', adapters: '适配器', materials: '输入素材', 'execution-targets': '执行目标' };
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const id = (value: unknown) => typeof value === 'string' && value ? value : null;
const display = (value: unknown) => value === undefined ? '未记录' : value === null ? '未选择' : typeof value === 'object' ? JSON.stringify(value) : String(value);
const interruptedRead = '读取期间工作库已变化，旧结果未采用。请重新读取来源与引用。';

export function useWorkRecipeContext(task: Task, draft: Draft) {
  const captureLibraryRead = useContext(LibraryReadContext);
  const [refresh, setRefresh] = useState(0);
  const identity = JSON.stringify([task.id, task.project_id, task.source_work_id, task.source_attempt_id, task.source_recipe_digest]);
  const [loaded, setLoaded] = useState<{ identity: string; view?: WorkRecipeView; error?: string } | null>(null);
  const [resolved, setResolved] = useState<{ identity: string; items: Reference[] } | null>(null);
  const source = loaded?.identity === identity ? loaded : null;
  const view = source?.view;
  const recipe = view?.recipe || {};
  const specs: { kind: ReferenceKind; id: string }[] = [];
  function reference(kind: ReferenceKind, value: unknown) {
    const key = id(value);
    if (key && !specs.some(item => item.kind === kind && item.id === key)) specs.push({ kind, id: key });
  }
  if (view) {
    reference('models', recipe.model_id); reference('models', draft.model_id);
    reference('adapters', recipe.adapter_id); reference('adapters', draft.adapter_id);
    reference('materials', record(recipe.input).material_id); reference('materials', draft.input.material_id);
    reference('execution-targets', recipe.execution_target_id); reference('execution-targets', draft.execution_target_id);
  }
  const referencesIdentity = JSON.stringify([identity, view?.source_recipe_digest, specs]);
  const references = resolved?.identity === referencesIdentity ? resolved.items : [];
  useEffect(() => {
    let live = true; const libraryCurrent = captureLibraryRead();
    const isCurrent = () => live && libraryCurrent();
    setLoaded(null); setResolved(null);
    if (!task.source_work_id) return () => { live = false; };
    if (!task.source_attempt_id || !task.source_recipe_digest) {
      setLoaded({ identity, error: '此任务的作品来源记录不完整，不能确定原配方基准。' });
      return () => { live = false; };
    }
    async function load() {
      if (!isCurrent()) { if (live) setLoaded({ identity, error: interruptedRead }); return; }
      try {
        const result = await api<WorkRecipeView>('GET', `/works/${encodeURIComponent(task.source_work_id!)}/recipe?project_id=${encodeURIComponent(task.project_id)}`);
        if (!isCurrent()) { if (live) setLoaded({ identity, error: interruptedRead }); return; }
        if (result.source_work_id !== task.source_work_id || result.source_attempt_id !== task.source_attempt_id || result.source_recipe_digest !== task.source_recipe_digest || result.work.id !== task.source_work_id || result.work.project_id !== task.project_id || result.recipe.project_id !== task.project_id || result.recipe.attempt_id !== task.source_attempt_id) throw new Error('来源作品、运行或配方基准已变化，请重新核对来源。');
        setLoaded({ identity, view: result });
      } catch (error) { if (live) setLoaded({ identity, error: libraryCurrent() ? errorMessage(error) : interruptedRead }); }
    }
    void load();
    return () => { live = false; };
  }, [identity, refresh, captureLibraryRead]);
  useEffect(() => {
    let live = true; const libraryCurrent = captureLibraryRead();
    const isCurrent = () => live && libraryCurrent();
    setResolved(null);
    if (!view) return () => { live = false; };
    async function load() {
      const items = await Promise.all(specs.map(async item => {
        if (!isCurrent()) return item;
        try {
          const value = await api<Record<string, unknown>>('GET', `/${item.kind}/${encodeURIComponent(item.id)}`);
          if (!isCurrent()) return item;
          if (value.id !== item.id || value.project_id !== task.project_id) throw new Error('记录身份或所属项目不符，未采用此引用。');
          return { ...item, value };
        } catch (error) { return { ...item, error: errorMessage(error) }; }
      }));
      if (live) setResolved({ identity: referencesIdentity, items: libraryCurrent() ? items : specs.map(item => ({ ...item, error: interruptedRead })) });
    }
    void load();
    return () => { live = false; };
  }, [referencesIdentity, view, captureLibraryRead]);
  const values = <T,>(kind: ReferenceKind) => references.filter(item => item.kind === kind && item.value).map(item => item.value as T);
  return { sourceWorkId: task.source_work_id, view, error: source?.error, references,
    loading: Boolean(task.source_work_id && !source), referencesLoading: Boolean(view && resolved?.identity !== referencesIdentity),
    retry: () => setRefresh(value => value + 1), models: values<Model>('models'), adapters: values<Adapter>('adapters'), materials: values<Material>('materials') };
}

const runtimeLabels: Record<string, string> = { max_tokens: '最大输出 token', temperature: '温度', top_p: 'Top-p', seed: '随机种子', steps: '步数', size: '图片尺寸', cfg: '提示词引导强度', frames: '帧数', fps: '帧率', voice: '音色', speed: '语速', sample_rate: '采样率', precision: '计算精度', kv_precision: 'KV 缓存精度', prefill_step_size: '提示词分块上限', context_limit: '上下文上限', overflow: '超长输入处理', stop: '停止序列', stream: '流式输出', thinking: '思考设置' };

export function WorkRecipeContext({ state, draft }: { state: ReturnType<typeof useWorkRecipeContext>; draft: Draft }) {
  if (!state.sourceWorkId) return null;
  const recipe = state.view?.recipe || {};
  const find = (kind: ReferenceKind, value: unknown) => state.references.find(item => item.kind === kind && item.id === id(value))?.value;
  const selectedModel = find('models', draft.model_id);
  const selectedAdapter = find('adapters', draft.adapter_id);
  const selectedMaterial = find('materials', draft.input.material_id);
  const selectedTarget = find('execution-targets', draft.execution_target_id);
  const targetTransport = selectedTarget && (selectedTarget.transport === undefined ? 'loopback_http' : selectedTarget.transport);
  const modelKind = selectedModel ? selectedModel.modality ?? selectedModel.kind ?? 'text' : undefined;
  const originalRuntime = record(recipe.runtime); const originalTarget = record(recipe.execution_target);
  const differences: { label: string; before: string; after: string }[] = [];
  function compare(label: string, before: unknown, after: unknown) {
    if (JSON.stringify(before) !== JSON.stringify(after)) differences.push({ label, before: display(before), after: display(after) });
  }
  if (state.view && !state.referencesLoading) {
    compare('模型编号', id(recipe.model_id), draft.model_id);
    compare('模型类别', recipe.kind, draft.model_id ? modelKind : null);
    compare('模型版本', recipe.model_version_id, draft.model_id ? selectedModel?.version_id : null);
    compare('模型文件摘要', recipe.model_manifest_digest, draft.model_id ? selectedModel?.manifest_digest : null);
    compare('适配器编号', id(recipe.adapter_id), draft.adapter_id || null);
    if (recipe.adapter_id || draft.adapter_id) {
      compare('适配器版本', recipe.adapter_version_id, draft.adapter_id ? selectedAdapter?.version_id : null);
      compare('适配器文件摘要', recipe.adapter_manifest_digest, draft.adapter_id ? selectedAdapter?.manifest_digest : null);
      compare('适配器训练配方摘要', recipe.adapter_training_recipe_digest, draft.adapter_id ? selectedAdapter?.training_recipe_digest : null);
      compare('适配器基座编号', recipe.adapter_id ? recipe.model_id : null, selectedAdapter?.base_model_id ?? null);
      compare('适配器基座版本', recipe.adapter_id ? recipe.model_version_id : null, selectedAdapter?.base_model_version_id ?? null);
      compare('适配器基座摘要', recipe.adapter_id ? recipe.model_manifest_digest : null, selectedAdapter?.base_manifest_digest ?? null);
    }
    compare('执行引擎', originalRuntime.engine, draft.runtime.engine);
    compare('执行设备', originalRuntime.device_id, draft.runtime.device_id);
    compare('执行位置', id(recipe.execution_target_id) || '本机', draft.execution_target_id || '本机');
    if (recipe.execution_target_id || draft.execution_target_id) {
      compare('执行地址', recipe.execution_target_id ? originalTarget.origin : '本机', draft.execution_target_id ? selectedTarget?.origin : '本机');
      compare('执行器身份', recipe.execution_target_id ? originalTarget.executor_id : '本机', draft.execution_target_id ? selectedTarget?.executor_id : '本机');
      compare('执行连接方式', recipe.execution_target_id ? originalTarget.transport : '本机', draft.execution_target_id ? targetTransport : '本机');
      compare('执行验证范围', recipe.execution_target_id ? originalTarget.validation_scope : '本机', draft.execution_target_id ? selectedTarget?.validation_scope : '本机');
    }
    const originalInput = record(recipe.input);
    compare('输入内容', originalInput.prompt, draft.input.prompt);
    compare('不希望出现的内容', originalInput.negative_prompt, draft.input.negative_prompt);
    compare('输入素材编号', id(originalInput.material_id), draft.input.material_id || null);
    if (originalInput.material_id || draft.input.material_id) {
      compare('输入素材版本', recipe.material_version_id, draft.input.material_id ? selectedMaterial?.version_id : null);
      compare('输入素材摘要', recipe.input_image_manifest_digest, draft.input.material_id ? selectedMaterial?.manifest_digest : null);
    }
    for (const key of new Set([...Object.keys(originalRuntime), ...Object.keys(draft.runtime)])) {
      if (key !== 'engine' && key !== 'device_id') compare(runtimeLabels[key] || `运行参数 ${key}`, originalRuntime[key], record(draft.runtime)[key]);
    }
  }
  const adapterMismatch = selectedAdapter && selectedModel && (selectedAdapter.base_model_id !== selectedModel.id || selectedAdapter.base_model_version_id !== selectedModel.version_id || selectedAdapter.base_manifest_digest !== selectedModel.manifest_digest);
  const modelKindMismatch = selectedModel && modelKind !== recipe.kind;
  return <section className="data-check" aria-label="来源作品与配方对照">
    <div className="section-title"><h2>来源作品与配方</h2><Button disabled={state.loading || state.referencesLoading} onClick={state.retry}>重新读取来源与引用</Button></div>
    <p>来源作品编号：{state.sourceWorkId}</p>
    {state.loading && <p role="status">正在读取原配方基准…</p>}
    <ErrorNotice message={state.error || ''} />
    {state.view && <><p>来源运行编号：{state.view.source_attempt_id}</p><details><summary>查看原配方基准</summary><RecipeDetails view={state.view} /></details>
      <h3>当前草稿与原配方的差异</h3>
      {state.referencesLoading ? <p role="status">正在按编号读取原引用和当前选择…</p> : <>
        {state.references.filter(item => item.error).map(item => <p className="error" key={`${item.kind}:${item.id}`}>{referenceNames[item.kind]} {item.id}：{item.error} 原配方和草稿编号保留，请明确重新选择后检查。</p>)}
        {modelKindMismatch && <p className="error">当前模型类别与原配方不符：原配方为 {display(recipe.kind)}，当前模型为 {display(modelKind)}。请明确选择同类别模型后检查。</p>}
        {adapterMismatch && <p className="error">当前适配器与所选基座不兼容：要求 {display(selectedAdapter?.base_model_id)} / {display(selectedAdapter?.base_model_version_id)} / {display(selectedAdapter?.base_manifest_digest)}；当前为 {display(selectedModel?.id)} / {display(selectedModel?.version_id)} / {display(selectedModel?.manifest_digest)}。</p>}
        {differences.length ? <><p className="warning">当前选择已有变化，保存后请重新检查配置。</p><dl className="facts" aria-label="配方差异">{differences.map(item => <div key={item.label}><dt>{item.label}</dt><dd><span>原：{item.before}</span><br /><span>当前：{item.after}</span></dd></div>)}</dl></> : !state.references.some(item => item.error) && <p>已读回的选择与原配方一致。执行前仍需检查配置。</p>}
      </>}
    </>}
  </section>;
}
