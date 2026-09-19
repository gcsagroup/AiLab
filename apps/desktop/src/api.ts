import { invoke, isTauri } from '@tauri-apps/api/core';

export type ApiFailure = { error: { code: string; message: string; details?: Record<string, unknown> } };
export type NativeStatus = { state: string; connection_id?: string; message?: string; recovery_mode?: boolean };
export const readHostStatus = () => isTauri() ? invoke<NativeStatus>('host_status') : Promise.resolve(null);
type NativeScope = { status: Promise<NativeStatus>; id?: string };
let nativeScope: NativeScope | undefined;
let nativeChanging = false;
let lastNativeId: string | undefined;
let nativeChangeDone: Promise<void> | undefined;
export const pendingNativeConnectionChange = () => nativeChangeDone;
const connectionChanged = (): ApiFailure => ({ error: { code: 'CONTROL_CONNECTION_CHANGED', message: '工作库连接已变化，请重新读取后再操作。' } });

export function invalidateNativeConnection() { nativeScope = undefined; }
export function observeNativeConnection(status: NativeStatus): boolean {
  if (status.state !== 'running') { invalidateNativeConnection(); return true; }
  if (!status.connection_id) return false;
  const changed = lastNativeId !== undefined && lastNativeId !== status.connection_id;
  lastNativeId = status.connection_id;
  if (nativeScope) {
    // 启动事件可能先于身份读取返回；记录观察值，返回后仍需双向核对。
    if (nativeScope.id && nativeScope.id !== status.connection_id) invalidateNativeConnection();
    else nativeScope.id = status.connection_id;
  }
  return changed;
}

async function invokeBound<T>(command: string, argumentsFor: (id: string) => Record<string, unknown>): Promise<T> {
  if (nativeChanging) throw { error: { code: 'LIBRARY_SWITCH_PENDING', message: '正在切换工作库，请等待连接完成。' } } satisfies ApiFailure;
  // 在第一次等待之前固定作用域；旧 IPC 与迟到的身份读取都不能换用新库身份。
  const scope = nativeScope ||= { status: invoke<NativeStatus>('host_status') };
  let status: NativeStatus;
  try { status = await scope.status; }
  catch (error) { if (nativeScope === scope) invalidateNativeConnection(); throw error; }
  if (nativeScope !== scope || nativeChanging) throw connectionChanged();
  if (status.state !== 'running' || typeof status.connection_id !== 'string' || !status.connection_id) {
    invalidateNativeConnection();
    throw { error: { code: 'CONTROL_UNAVAILABLE', message: '本地服务未连接，请重新连接后再操作。' } } satisfies ApiFailure;
  }
  if (scope.id && scope.id !== status.connection_id) { invalidateNativeConnection(); throw connectionChanged(); }
  scope.id = status.connection_id;
  lastNativeId = status.connection_id;
  let result: T;
  try { result = await invoke<T>(command, argumentsFor(scope.id)); }
  catch (error) { if (nativeScope !== scope || nativeChanging) throw connectionChanged(); throw error; }
  if (nativeScope !== scope || nativeChanging) throw connectionChanged();
  return result;
}

async function changeNativeConnection<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (nativeChanging) throw { error: { code: 'LIBRARY_SWITCH_PENDING', message: '正在切换工作库，请等待连接完成。' } } satisfies ApiFailure;
  nativeChanging = true; invalidateNativeConnection();
  let finish!: () => void;
  nativeChangeDone = new Promise<void>(resolve => { finish = resolve; });
  try { return await invoke<T>(command, args); }
  finally { nativeChanging = false; invalidateNativeConnection(); nativeChangeDone = undefined; finish(); }
}
const fieldNames: Record<string, string> = { prompt: '输入内容', model_id: '基座模型', dataset_id: '训练数据', adapter_id: '训练适配器', max_tokens: '最大输出 token', temperature: '温度', top_p: 'Top-p', seed: '随机种子', steps: '训练步数', learning_rate: '学习率', max_seq_length: '最大序列长度', lora_rank: 'LoRA 秩', lora_alpha: 'LoRA Alpha', num_layers: '训练末尾层数', name: '名称', target_dir: '保存目录' };
export function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error && 'error' in error) {
    const failure = (error as ApiFailure).error;
    const fields = failure.details?.fields;
    const labels = Array.isArray(fields) ? [...new Set(fields.map(item => fieldNames[String(item.field).split('.').at(-1) || '']).filter(Boolean))] : [];
    return `${failure.message}${labels.length ? ` 请检查：${labels.join('、')}。` : ''}`;
  }
  if (error instanceof Error) return error.message;
  if (typeof error === 'string') {
    try { const parsed = JSON.parse(error); return parsed.error ? errorMessage(parsed) : error; } catch { return error; }
  }
  return '操作未完成，请重试。';
}

export async function api<T>(method: string, path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const fullPath = `/api/v1${path}`;
  if (isTauri()) {
    return invokeBound<T>('api_request', connection_id => ({ request: { connection_id, method, path: fullPath, body, idempotency_key: idempotencyKey } }));
  }
  const headers: Record<string, string> = { 'Content-Type': 'application/json', 'X-AiLab-Request': '1' };
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  const response = await fetch(fullPath, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json();
  if (!response.ok) throw result;
  return result;
}

export type ImportSelection = { path: string; grant_id?: string };
export const canPickFile = () => isTauri();
export type ImportKind = 'model' | 'dataset' | 'image-dataset' | 'material';
export const pickImport = (kind: ImportKind | 'backup') => invokeBound<ImportSelection | null>('pick_import_path', connectionId => ({ kind, connectionId }));
export const pickExportDirectory = () => invokeBound<ImportSelection | null>('pick_export_directory', connectionId => ({ connectionId }));
export const beginBackupRecovery = () => changeNativeConnection('begin_backup_recovery');
export const restartControl = () => changeNativeConnection('restart_control');
export const recordFirstFrame = (view: 'empty_library' | 'project_home', frontend: import('./Startup').StartupPhases) => invoke('record_first_frame', { view, frontend });

export type CollectionPage<T> = { items: T[]; next_cursor?: string | null };
export async function collection<T>(path: string, cursor?: string | null): Promise<CollectionPage<T>> {
  const url = cursor ? `${path}${path.includes('?') ? '&' : '?'}cursor=${encodeURIComponent(cursor)}` : path;
  const page = await api<CollectionPage<T>>('GET', url);
  if (cursor && page.next_cursor === cursor) throw new Error('列表游标重复，请刷新后重试。');
  return page;
}

export function mergeRecords<T extends { id: string }>(current: T[], incoming: T[]): T[] {
  const records = new Map(current.map(item => [item.id, item]));
  incoming.forEach(item => records.set(item.id, item));
  return [...records.values()];
}

export type EnvironmentSettings = { revision: number; worker_python: string | null; [key: string]: unknown };
export const pickWorkerPython = () => invokeBound<EnvironmentSettings | null>('pick_worker_python', connectionId => ({ connectionId }));
export const pickMediaPython = (engine: 'diffusers' | 'kokoro') => invokeBound<EnvironmentSettings | null>('pick_media_python', connectionId => ({ engine, connectionId }));
export const useBundledMedia = (engine: 'diffusers' | 'kokoro') => invokeBound<EnvironmentSettings>('use_bundled_media', connectionId => ({ engine, connectionId }));
export const useBundledWorker = () => invokeBound<EnvironmentSettings>('use_bundled_worker', connectionId => ({ connectionId }));
export const useRestoredLibrary = (restoreId: string) => changeNativeConnection('use_restored_library', { restoreId });
export const configureMarketFixture = (origin: string | null) => changeNativeConnection<{ market_fixture_origin: string | null }>('configure_market_fixture', { origin });

export async function mediaBlob(artifactId: string): Promise<Blob> {
  if (!/^artifact-[a-f0-9]{32}$/.test(artifactId)) throw new Error('媒体文件编号无效。');
  const allowed = new Set(['image/png', 'video/mp4', 'audio/wav']);
  const limit = 64 * 1024 * 1024;
  if (isTauri()) {
    const result = await invokeBound<{ media_type: string; base64: string }>('api_media', connectionId => ({ artifactId, connectionId }));
    if (!allowed.has(result.media_type) || result.base64.length > Math.ceil(limit / 3) * 4) throw new Error('媒体格式或大小超出预览范围。');
    const bytes = Uint8Array.from(atob(result.base64), character => character.charCodeAt(0));
    if (bytes.length > limit) throw new Error('媒体大小超出预览范围。');
    return new Blob([bytes], { type: result.media_type });
  }
  const response = await fetch(`/api/v1/artifacts/${artifactId}/content`, { headers: { 'X-AiLab-Request': '1' } });
  if (!response.ok) throw await response.json();
  const type = response.headers.get('Content-Type')?.split(';')[0].trim() || '';
  if (!allowed.has(type) || Number(response.headers.get('Content-Length') || '0') > limit) throw new Error('媒体格式或大小超出预览范围。');
  const reader = response.body?.getReader();
  if (!reader) throw new Error('媒体数据流不可读取。');
  const chunks: BlobPart[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > limit) { await reader.cancel(); throw new Error('媒体大小超出预览范围。'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  return new Blob(chunks, { type });
}
