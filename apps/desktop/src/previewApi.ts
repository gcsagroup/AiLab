import type { Capability, Draft, Project, Task } from './types';
import type { LibraryViews } from './ProjectContext';
import trainingContracts from '../../../tests/frontend/fixtures/training-contracts.json';

// This adapter is included only in the explicit Windows UI preview build.
// No real control service, model download, remote host, or executor is contacted.
const storageKey = 'gcsa-ailab-windows-ui-v1';
type PreviewState = { projects: Project[]; tasks: Task[]; context: LibraryViews };
const initialState = (): PreviewState => ({
  projects: [{ id: 'project-ui-preview', name: 'Windows UI 预览', revision: 1 }],
  tasks: [], context: { project_id: 'project-ui-preview', projects: {} },
});
function load(): PreviewState {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (value && Array.isArray(value.projects) && Array.isArray(value.tasks)
      && value.context && typeof value.context.projects === 'object') return value;
  } catch { /* A new preview library is created if no valid saved state exists. */ }
  return initialState();
}
let state = load();
function save() { localStorage.setItem(storageKey, JSON.stringify(state)); }
const page = (items: unknown[] = []) => ({ items, next_cursor: null });
const unavailable = () => ({ error: { code: 'UI_PREVIEW_ONLY', message: '当前为 Windows UI 预览版，此功能尚未接入。可以浏览界面并保存任务草稿。' } });
const missing = () => ({ error: { code: 'RESOURCE_NOT_FOUND', message: '此预览记录不存在。' } });

function draft(kind: Draft['kind'], operation: Draft['operation']): Draft {
  const train = operation === 'train';
  const runtime = kind === 'text' ? {
    engine: 'mlx', device_id: 'apple-gpu', seed: 0,
    ...(train ? { training_type: 'sft', update_method: 'lora', recipe_id: 'qwen25-assistant-only-v1', steps: 4, learning_rate: 0.0001, max_seq_length: 512, lora_rank: 4, lora_alpha: 8, num_layers: 2, batch_size: 1, gradient_accumulation: 1, optimizer: 'adamw', weight_decay: 0, lora_dropout: 0 }
      : { max_tokens: 128, temperature: 0, top_p: 1 }),
  } : { engine: kind === 'audio' ? 'kokoro' : 'diffusers', device_id: 'cpu', seed: 0 };
  if (window.ailabHF) {
    runtime.device_id = 'cpu';
    runtime.engine = 'ailab-gguf';
    if (kind !== 'text') Object.assign(runtime,kind==='image' ? {size:512,steps:20,cfg:7.5} : kind==='video' ? {steps:25,frames:14,fps:7} : {voice:'zf_xiaobei',speed:1,sample_rate:24000});
  }
  return { kind, operation, model_id: null, dataset_id: null, adapter_id: null, execution_target_id: null, input: { prompt: '' }, runtime };
}

export async function previewApi<T>(method: string, path: string, body?: unknown): Promise<T> {
  const value = body as Record<string, any> | undefined;
  const url = new URL(path, 'https://preview.invalid');
  const route = url.pathname;
  const project = url.searchParams.get('project_id');
  let result: unknown;
  if (route === '/projects' && method === 'GET') result = page(state.projects);
  else if (route === '/projects' && method === 'POST') {
    const created = { id: `project-${crypto.randomUUID()}`, name: String(value?.name || '未命名项目').slice(0, 80), revision: 1 };
    state.projects.push(created); save(); result = created;
  } else if (/^\/projects\/[^/]+\/execution-default$/.test(route) && method === 'GET') result = { execution_target_id: null, revision: 1 };
  else if (/^\/projects\/[^/]+$/.test(route) && method === 'GET') {
    result = state.projects.find(item => item.id === route.split('/')[2]); if (!result) throw missing();
  } else if (route === '/ui-context' && method === 'GET') result = state.context;
  else if (route === '/ui-context' && method === 'PATCH') {
    if (!value || !state.projects.some(item => item.id === value.project_id)) throw missing();
    state.context = { project_id: value.project_id, projects: { ...state.context.projects, [value.project_id]: value.context } }; save(); result = state.context;
  } else if (route === '/tasks' && method === 'GET') result = page(state.tasks.filter(item => !project || item.project_id === project));
  else if (route === '/tasks' && method === 'POST') {
    if (!value || !state.projects.some(item => item.id === value.project_id)) throw missing();
    const task: Task = { id: `task-${crypto.randomUUID()}`, project_id: value.project_id, name: value.name,
      kind: value.kind, operation: value.operation, draft_revision: 1,
      draft: draft(value.kind, value.operation), attempts: [], created_at: new Date().toISOString() };
    state.tasks.unshift(task); save(); result = task;
  } else if (/^\/tasks\/[^/]+\/draft$/.test(route) && method === 'PATCH') {
    const task = state.tasks.find(item => item.id === route.split('/')[2]); if (!task) throw missing();
    if (value?.expected_revision !== task.draft_revision) throw { error: { code: 'REVISION_CONFLICT', message: '草稿版本已变化，请重新打开任务。' } };
    task.draft = structuredClone(value.draft); task.draft_revision += 1; save(); result = task;
  } else if (/^\/tasks\/[^/]+\/preflight$/.test(route) && method === 'POST') result = {
    preflight_id: 'ui-preview-blocked', can_submit: false, draft_revision: value?.draft_revision,
    blocking: [{ code: 'UI_PREVIEW_ONLY', message: '当前仅预览 UI，模型执行环境尚未接入。' }], warnings: [],
  };
  else if (/^\/tasks\/[^/]+$/.test(route) && method === 'GET') {
    result = state.tasks.find(item => item.id === route.split('/')[2]); if (!result) throw missing();
  } else if (route === '/capabilities' && method === 'GET') result = page(
    ['text', 'image', 'video', 'audio'].flatMap(kind => ['generate', 'train'].map(operation => ({
      kind, operation, supported: false, status: 'not_prepared', reason: 'Windows UI 预览版，执行环境尚未接入。',
    } as Capability))),
  );
  else if (route === '/devices' && method === 'GET') result = page([{ id: 'windows-ui', name: '本机 Windows · UI 预览', status: 'not_prepared' }]);
  else if (route === '/training-contracts' && method === 'GET') result = trainingContracts;
  else if (route === '/market/catalog' || route === '/market/local-versions') result = { versions: [] };
  else if (method === 'GET' && new Set(['/models', '/datasets', '/works', '/adapters', '/evaluation-plans', '/candidates', '/materials', '/workflow-runs', '/model-downloads', '/model-catalog', '/execution-targets', '/market/sources', '/attempts', '/checkpoints', '/environments', '/recipes']).has(route)) result = page();
  else throw unavailable();
  return structuredClone(result) as T;
}
