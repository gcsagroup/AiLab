import { useCallback, useEffect, useRef, useState } from 'react';
import { AudioLines, Boxes, ChevronRight, Database, FlaskConical, Folder, FolderHeart, History, Image, LayoutDashboard, MessagesSquare, Play, Plus, RefreshCw, Server, Settings2, Sparkles, Video } from 'lucide-react';
import { listen } from '@tauri-apps/api/event';
import { api, collection, mergeRecords, canPickFile, errorMessage, pickWorkerPython, pickMediaPython, restartControl, useBundledWorker, useBundledMedia, invalidateNativeConnection, observeNativeConnection, pendingNativeConnectionChange, beginBackupRecovery, readHostStatus, type NativeStatus } from './api';
import type { Adapter, Attempt, Candidate, Capability, Dataset, Device, Draft, Kind, Material, Model, Operation, Project, Task, Work } from './types';
import Workbench, { kindLabels, RunResult } from './Workbench';
import { MediaPreview, selectMediaRuntime } from './Media';
import { libraryModelKind, TrialModelSelect } from './TrialModelSelect';
import ImportDialog from './ImportDialog';
import ModelDownloadDialog, { modelDownloadStates, type ModelDownload } from './ModelDownloadDialog';
import DiagnosticsDialog from './DiagnosticsDialog';
import { InteractionTimingControls, useInteractionTiming } from './InteractionTiming';
import { WindowsEnvironment, type WindowsEnvironmentReport } from './WindowsEnvironment';
import BackupDialog from './BackupDialog';
import CleanupDialog from './CleanupDialog';
import { WorkRevisions } from './WorkRevisions';
import { WorkRecipeActions } from './WorkRecipes';
import { DatasetMarket } from './DatasetMarket';
import DatasetSplitDialog from './DatasetSplitDialog';
import { MarketSourceSettings } from './MarketSourceSettings';
import { ExecutionTargets } from './ExecutionTargets';
import { RemoteTransferTask } from './RemoteTransfer';
import { WorkflowRunView, WorkflowStartDialog, type WorkflowRun } from './Workflow';
import { ConversionStartDialog, ConversionTask } from './Conversion';
import { ModelLabDialog } from './ModelLab';
import { FormatDialog, formatNames } from './FormatConversion';
import { APP_VERSION_LABEL } from './version';
import { useStartupReceipt } from './Startup';
import { LibraryReadContext } from './LibraryReadContext';
import { ProjectContexts, rememberTaskSelection, taskSelectionKey, type LibraryViews, type Page, type ProjectView, type TaskSelectionKey } from './ProjectContext';
import { useExitPreparation } from './ExitPreparation';
import ExportDialog, { type ExportObject, type ExportRecord } from './ExportDialog';
import { EvaluationPlanDialog, EvaluationStartDialog, EvaluationTask, PlanSummary, type EvaluationPlan } from './Evaluation';
import { activeStates, Badge, Button, PaginationButton, Dialog, Empty, ErrorNotice, formatDate, readableSize, stateNames } from './ui';

const navigation = [
  { id: 'home' as Page, label: '工作台', Icon: LayoutDashboard },
  { id: 'models' as Page, label: '模型库', Icon: Boxes },
  { id: 'data' as Page, label: '数据集市场', Icon: Database },
  { id: 'lab' as Page, label: '模型实验室', Icon: FlaskConical },
  { id: 'assets' as Page, label: '作品与素材', Icon: FolderHeart },
];
const categories = [
  { kind: 'text' as Kind, title: '模型训练 / 微调', description: '语言与多模态模型', Icon: MessagesSquare, color: 'purple' },
  { kind: 'image' as Kind, title: '图片训练 / 微调', description: '图像生成、风格与主体', Icon: Image, color: 'blue' },
  { kind: 'video' as Kind, title: '视频训练 / 微调', description: '镜头、动作与视频内容', Icon: Video, color: 'peach' },
  { kind: 'audio' as Kind, title: '音频训练 / 微调', description: '配音、转写与声音', Icon: AudioLines, color: 'green' },
];

function canEvaluateModel(model: Model) { return Boolean(model.conversion && model.source_model_id && model.source_attempt_id && model.format === 'mlx-safetensors' && model.default_engine === 'mlx'); }
function modelQualityPassed(model: Model) { return canEvaluateModel(model) && model.status === 'quality_approved' && model.quality_status === 'passed' && Boolean(model.quality_candidate_id); }

function isMissingRecord(error: unknown) { return typeof error === 'object' && error !== null && 'error' in error && (error as { error: { code?: string } }).error?.code === 'RESOURCE_NOT_FOUND'; }
async function readSelected<T extends { id: string; project_id: string }>(path: string, projectId: string): Promise<T | null> {
  try {
    const value = await api<T>('GET', path);
    if (value.id !== path.split('/').at(-1) || value.project_id !== projectId) throw new Error('上次选择的对象不属于当前项目，请重新选择。');
    return value;
  } catch (e) { if (isMissingRecord(e)) return null; throw e; }
}

function ProjectDialog({ onClose, onCreate }: { onClose: () => void; onCreate: (name: string) => Promise<void> }) {
  const [name, setName] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) { event.preventDefault(); setBusy(true); setError(''); try { await onCreate(name.trim()); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <Dialog title="新建项目" onClose={onClose} preventClose={busy}><form onSubmit={submit} className="form-stack"><p className="muted">按项目保存模型、数据、运行与作品，方便持续对比和复用。</p><label>项目名称<input autoFocus required disabled={busy} maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder="例如：商品内容、文本助手" /></label><ErrorNotice message={error} /><Button type="submit" primary busy={busy} disabled={!name.trim()}>创建项目</Button></form></Dialog>;
}

export default function App() {
  const [libraryEpoch, setLibraryEpoch] = useState(0);
  return <LibraryView key={libraryEpoch} onLibraryChanged={() => { invalidateNativeConnection(); setLibraryEpoch(value => value + 1); }} />;
}

function LibraryView({ onLibraryChanged }: { onLibraryChanged: () => void }) {
  const timing = useInteractionTiming();
  const [page, setPage] = useState<Page>('home');
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [recoveryMode, setRecoveryMode] = useState(false);
  const recovery = useRef(false);
  const recoveryOperationBusy = useRef(false);
  const librarySwitching = useRef(false); const libraryReadEpoch = useRef(0);
  const mounted = useRef(true);
  const contextStore = useRef<ProjectContexts | null>(null);
  if (!contextStore.current) contextStore.current = new ProjectContexts(() => mounted.current && !librarySwitching.current && !recovery.current);
  const contexts = contextStore.current;
  const [contextReadyProject, setContextReadyProject] = useState<string | null>(null);
  const [contextError, setContextError] = useState('');
  const [contextReadError, setContextReadError] = useState('');
  const [contextAvailable, setContextAvailable] = useState(false);
  const captureLibraryRead = useCallback(() => { const epoch = libraryReadEpoch.current; return () => !librarySwitching.current && epoch === libraryReadEpoch.current; }, []);
  const [projectId, setProjectId] = useState('');
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [evaluationPlans, setEvaluationPlans] = useState<EvaluationPlan[]>([]);
  const [evaluationStart, setEvaluationStart] = useState<{ adapterId?: string; modelId?: string } | null>(null);
  const [revisingWork, setRevisingWork] = useState<Work | null>(null);
  const [exporting, setExporting] = useState<{ object: ExportObject; initial?: ExportRecord } | null>(null);
  const [modelDownloads, setModelDownloads] = useState<ModelDownload[]>([]); const [downloadInitial, setDownloadInitial] = useState<ModelDownload | undefined>();
  const [trialSelection, setTrialSelection] = useState<{ project: string; modelId: string } | null>(null);
  const [models, setModels] = useState<Model[]>([]); const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [splittingDataset, setSplittingDataset] = useState<Dataset | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]); const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const materialKeys = useRef(new Map<string, string>());
  const workReuseKeys = useRef(new Map<string, string>());
  const [tasks, setTasks] = useState<Task[]>([]); const [works, setWorks] = useState<Work[]>([]); const [devices, setDevices] = useState<Device[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const selectedTaskRef = useRef(selectedTask); selectedTaskRef.current = selectedTask;
  const editingDraft = useRef<{ taskId: string; draft: Draft } | null>(null);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]); const [selectedWorkflow, setSelectedWorkflow] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>('text'); const [moduleTab, setModuleTab] = useState<'train' | 'generate' | 'history'>('train');
  const [dataTab, setDataTab] = useState<'local' | 'market'>('local');
  const [formatTrialModel, setFormatTrialModel] = useState<Model | null>(null);
  const [modal, setModal] = useState<'project' | 'model' | 'dataset' | 'image-dataset' | 'material' | 'settings' | 'queue' | 'evaluation-plan' | 'backup' | 'cleanup' | 'conversion' | 'format-conversion' | 'merge' | 'distill' | 'workflow' | 'model-download' | 'market' | 'diagnostics' | null>(null);
  const [aiOpen, setAiOpen] = useState(false); const [aiPanelTarget, setAIPanelTarget] = useState<HTMLDivElement | null>(null); const [error, setError] = useState('');
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [connected, setConnected] = useState(false);
  const [hostHealthy, setHostHealthy] = useState(false);
  const environmentConnected = !recoveryMode && (hostHealthy || connected);
  const [projectResourcesReady, setProjectResourcesReady] = useState<string | null>(null);
  const [projectResourcesLoaded, setProjectResourcesLoaded] = useState(false); const [projectResourcesError, setProjectResourcesError] = useState('');
  const [environmentReady, setEnvironmentReady] = useState(false);
  const [windowsReport, setWindowsReport] = useState<WindowsEnvironmentReport | null>(null);
  const [environmentBusy, setEnvironmentBusy] = useState(false); const [environmentError, setEnvironmentError] = useState('');
  const environmentEpoch = useRef(0); const environmentInFlight = useRef(false);
  const markStartup = useStartupReceipt(connected && !loading && environmentReady && projectResourcesReady === projectId, projectId ? 'project_home' : 'empty_library');
  const [refresh, setRefresh] = useState(0);
  const [cursors, setCursors] = useState<Record<string, string | null | undefined>>({});
  const [pageBusy, setPageBusy] = useState<Record<string, boolean>>({});
  const pageEpoch = useRef(0);
  const projectRef = useRef(projectId); projectRef.current = projectId;

  const reload = useCallback(() => { if (!librarySwitching.current && !recovery.current) setRefresh(value => value + 1); }, []);
  const leaveTask = useRef<(() => Promise<boolean>) | null>(null);
  const navigationVersion = useRef(0);
  const taskOpenVersion = useRef(0);
  const taskCreationVersion = useRef(0);
  const taskEntryInFlight = useRef(false);
  const currentView = useRef({ projectId, ready: false, view: contexts.view(projectId) });
  currentView.current = { projectId, ready: contextReadyProject === projectId && (!selectedTask || selectedTask.project_id === projectId), view: rememberTaskSelection({
    ...contexts.view(projectId), page, kind, module_tab: moduleTab, data_tab: dataTab, task_id: selectedTask?.id || null, workflow_id: selectedWorkflow,
  }, selectedTask?.project_id === projectId ? selectedTask : null) };
  const exitPreparation = useExitPreparation(async () => {
    if (recovery.current && recoveryOperationBusy.current) throw new Error('备份恢复操作尚未完成，请等待文件检查或复制结束后再退出。');
    // 冷启动从未载入工作库时没有可保存的选择；已载入项目或草稿仍走完整保存。
    if (!connected && !projectsLoaded && !contexts.loaded && !currentView.current.projectId
      && !selectedTaskRef.current && !selectedWorkflow && !leaveTask.current && !librarySwitching.current) return;
    await prepareLibraryLeave();
  });
  function rememberView(id: string, view: ProjectView) {
    return contexts.remember(id, view).then(() => {
      if (mounted.current && !librarySwitching.current) setContextError('');
    }).catch(e => {
      if (mounted.current && !librarySwitching.current) setContextError(`当前选择尚未保存：${errorMessage(e)}`);
      throw e;
    });
  }
  async function saveCurrentView() {
    if (recovery.current) return;
    const isCurrent = captureLibraryRead();
    if (!contexts.loaded) {
      const stored = await api<LibraryViews>('GET', '/ui-context');
      if (!isCurrent()) throw new Error('工作库连接已变化，请重试保存当前选择。');
      if (!contexts.loaded) contexts.load(stored);
      setContextAvailable(true); setContextReadError('');
    }
    // 重试以眼前页面为准，不能因迟到的偏好读取覆盖正在编辑的草稿。
    const current = currentView.current;
    if (current.projectId) await rememberView(current.projectId, current.ready ? current.view : contexts.view(current.projectId));
    await contexts.flush();
  }
  async function prepareLibraryLeave() {
    if (librarySwitching.current) throw new Error('工作库正在切换，请等待完成后再试。');
    if (recovery.current) return;
    if (leaveTask.current && !(await leaveTask.current())) throw new Error('草稿尚未保存或操作尚未完成，请返回任务处理后再试。');
    try { await saveCurrentView(); setContextError(''); }
    catch (e) { setContextError(`当前选择尚未保存：${errorMessage(e)}`); throw e; }
  }
  async function beginLibrarySwitch() {
    await prepareLibraryLeave();
    // 宿主会先切换连接再返回成功；等待期间旧读取不能继续访问新库。
    invalidateTaskEntry();
    librarySwitching.current = true; libraryReadEpoch.current += 1;
    environmentEpoch.current += 1; environmentInFlight.current = false; pageEpoch.current += 1; navigationVersion.current += 1;
  }
  function failedLibrarySwitch() {
    invalidateNativeConnection();
    librarySwitching.current = false; setLoading(false); setPageBusy({});
    if (projectId && projectResourcesReady !== projectId) setProjectResourcesError('项目内容读取已中断，请重试加载。');
    if (!recovery.current) void loadEnvironment();
  }
  function applyRecoveryStatus(status: NativeStatus) {
    recovery.current = status.recovery_mode === true; setRecoveryMode(recovery.current);
    if (recovery.current) {
      invalidateTaskEntry(); libraryReadEpoch.current += 1; environmentEpoch.current += 1; pageEpoch.current += 1;
      environmentInFlight.current = false; setConnected(false); setHostHealthy(false); setLoading(false);
      setEnvironmentReady(false); setEnvironmentBusy(false);
    }
  }
  async function openBackupRecovery() {
    setBusy(true); setError('');
    librarySwitching.current = true; libraryReadEpoch.current += 1; environmentEpoch.current += 1; pageEpoch.current += 1;
    try {
      const current = recovery.current ? await readHostStatus() : null;
      if (!current || current.state !== 'running') await beginBackupRecovery();
      const status = await readHostStatus();
      if (!status || !status.recovery_mode || status.state !== 'running') throw new Error(status?.message || '恢复服务尚未连接，请重试。');
      applyRecoveryStatus(status); setModal('backup');
    } catch (e) {
      // 启动响应失败时，恢复区仍可能已建立；重新核对宿主，避免显示普通工作台。
      const status = await readHostStatus().catch(() => null);
      if (status?.recovery_mode) applyRecoveryStatus(status);
      setError(errorMessage(e));
    }
    finally { librarySwitching.current = false; setBusy(false); setLoading(false); }
  }
  function invalidateTaskEntry() {
    if (!taskEntryInFlight.current) return;
    taskCreationVersion.current += 1; taskEntryInFlight.current = false; setBusy(false);
  }
  async function navigate(action: () => void) {
    if (!leaveTask.current || await leaveTask.current()) {
      navigationVersion.current += 1;
      invalidateTaskEntry();
      leaveTask.current = null; action();
    }
  }
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; libraryReadEpoch.current += 1; navigationVersion.current += 1; };
  }, []);
  useEffect(() => {
    if (recovery.current || !projectId || contextReadyProject !== projectId || (selectedTask && selectedTask.project_id !== projectId)) return;
    void rememberView(projectId, currentView.current.view).catch(() => {});
  }, [contexts, contextAvailable, contextReadyProject, projectId, page, kind, moduleTab, dataTab, selectedTask?.id, selectedWorkflow]);
  useEffect(() => {
    if (!canPickFile()) return;
    let disposed = false;
    let eventVersion = 0;
    let unlisten: (() => void) | undefined;
    void listen<NativeStatus>('host-status', event => {
      if (librarySwitching.current) return;
      const version = ++eventVersion;
      const changed = observeNativeConnection(event.payload);
      applyRecoveryStatus(event.payload);
      if (recovery.current) { setError(event.payload.state === 'running' ? '' : event.payload.message || '恢复服务未连接。'); return; }
      if (event.payload.state === 'running') {
        if (changed) {
          invalidateTaskEntry();
          libraryReadEpoch.current += 1; environmentEpoch.current += 1; environmentInFlight.current = false; pageEpoch.current += 1;
          setEnvironmentReady(false); setEnvironmentBusy(false);
        }
        const resume = () => {
          if (disposed || version !== eventVersion || librarySwitching.current) return;
          markStartup('host_running_observed'); setHostHealthy(true); reload();
        };
        // 宿主可能先发健康事件，再结束切换命令；命令结束前不能启动新读取。
        const pending = pendingNativeConnectionChange();
        if (pending) void pending.then(resume); else resume();
      }
      else {
        markStartup('host_disconnected_observed');
        // 同批断连再连接也要同步作废旧响应，防止旧项目结果重新启用环境读取。
        invalidateTaskEntry();
        libraryReadEpoch.current += 1; environmentEpoch.current += 1; environmentInFlight.current = false; pageEpoch.current += 1;
        setHostHealthy(false); setConnected(false); setLoading(false); setPageBusy({});
        // 断连会卸载工作台；重连先按已记住的选择重读详情，不能用旧草稿冒充尚未执行。
        setContextReadyProject(null); setProjectResourcesLoaded(false); setProjectResourcesReady(null);
        setEnvironmentReady(false); setEnvironmentBusy(false); setError(event.payload.message || '本机服务未连接。');
      }
    }).then(stop => { if (disposed) stop(); else unlisten = stop; });
    return () => { disposed = true; unlisten?.(); };
  }, [reload]);
  const project = projects.find(item => item.id === projectId);
  useEffect(() => {
    let live = true; const epoch = libraryReadEpoch.current;
    async function connect() {
      markStartup('projects_started');
      setLoading(true);
      setCursors(previous => ({ ...previous, projects: null }));
      try {
        if (recovery.current || librarySwitching.current) return;
        const host = await readHostStatus();
        if (!live || epoch !== libraryReadEpoch.current || librarySwitching.current) return;
        if (host) {
          applyRecoveryStatus(host);
          if (recovery.current) return;
          if (host.state !== 'running') throw new Error(host.message || '本机服务未连接。');
        }
        const [result, stored] = await Promise.all([collection<Project>('/projects'), contexts.loaded ? null : api<LibraryViews>('GET', '/ui-context').then(value => ({ value, error: null })).catch(error => ({ value: null, error }))]);
        if (!live || epoch !== libraryReadEpoch.current) return;
        if (stored && !contexts.loaded) {
          if (stored.value) { contexts.load(stored.value); setContextAvailable(true); setContextReadError(''); }
          else setContextReadError(`上次选择暂未读回，当前页面可继续使用：${errorMessage(stored.error)}`);
        }
        const currentId = projectRef.current || contexts.value.project_id || '';
        let selected: Project | null = null; let selectionError = '';
        if (currentId && !result.items.some(item => item.id === currentId)) {
          try { selected = await api<Project>('GET', `/projects/${currentId}`); }
          catch (e) { if (projectRef.current) selectionError = errorMessage(e); else if (!isMissingRecord(e)) throw e; }
        }
        if (!live || epoch !== libraryReadEpoch.current) return;
        const chosenId = projectRef.current || (result.items.some(item => item.id === currentId) || selected?.id === currentId ? currentId : result.items[0]?.id || '');
        markStartup('projects_ready');
        setProjects(previous => mergeRecords(result.items, selected?.id === chosenId ? [selected] : previous.filter(item => item.id === chosenId))); setCursors(previous => ({ ...previous, projects: result.next_cursor })); setConnected(true); setProjectsLoaded(true); setError(selectionError);
        if (!projectRef.current && chosenId) { applyProjectView(chosenId); setProjectId(chosenId); }
      } catch (e) { if (live && epoch === libraryReadEpoch.current) { setConnected(false); setError(errorMessage(e)); } }
      finally { if (live && epoch === libraryReadEpoch.current) setLoading(false); }
    }
    void connect(); return () => { live = false; };
  }, [refresh]);
  useEffect(() => {
    if (recovery.current || librarySwitching.current) return;
    let live = true; const epoch = libraryReadEpoch.current; pageEpoch.current += 1; setPageBusy({}); setCursors(previous => ({ projects: previous.projects })); setProjectResourcesReady(projectId ? null : ''); setProjectResourcesError('');
    if (!projectId) { setModels([]); setModelDownloads([]); setAdapters([]); setCandidates([]); setEvaluationPlans([]); setDatasets([]); setTasks([]); setWorks([]); setMaterials([]); setWorkflowRuns([]); markStartup('resources_ready'); return; }
    async function loadProject() {
      markStartup('resources_started');
      try {
        const restoreView = contextReadyProject === projectId ? null : contexts.view(projectId);
        const navigation = navigationVersion.current;
        const query = `?project_id=${encodeURIComponent(projectId)}`;
        const [m, d, t, w, a, plans, accepted, inputMaterials, workflows, downloads, restoredTask, restoredWorkflow] = await Promise.all([
          collection<Model>(`/models${query}`), collection<Dataset>(`/datasets${query}`),
          collection<Task>(`/tasks${query}`), collection<Work>(`/works${query}`), collection<Adapter>(`/adapters${query}`),
          collection<EvaluationPlan>(`/evaluation-plans${query}`), collection<Candidate>(`/candidates${query}`), collection<Material>(`/materials${query}`), collection<WorkflowRun>(`/workflow-runs${query}`), collection<ModelDownload>(`/model-downloads${query}`),
          restoreView?.task_id ? readSelected<Task>(`/tasks/${restoreView.task_id}`, projectId) : null,
          restoreView?.workflow_id ? readSelected<WorkflowRun>(`/workflow-runs/${restoreView.workflow_id}`, projectId) : null,
        ]);
        if (!live || epoch !== libraryReadEpoch.current) return;
        if (restoreView && navigation === navigationVersion.current) {
          if (restoredTask && !['generate', 'train', 'evaluate', 'quantize', 'merge', 'distill', 'convert', 'transfer'].includes(restoredTask.operation)) throw new Error('上次选择的任务类型不能在此工作台打开。');
          setSelectedTask(restoredTask); setSelectedWorkflow(restoredWorkflow?.id || null);
        }
        setContextReadyProject(projectId);
        const currentDraft = editingDraft.current?.taskId === selectedTaskRef.current?.id ? editingDraft.current?.draft : selectedTaskRef.current?.draft;
        const pinned = new Set([currentDraft?.model_id, currentDraft?.candidate_model_id, currentDraft?.dataset_id, currentDraft?.adapter_id, currentDraft?.evaluation_plan_id, currentDraft?.input.material_id].filter(Boolean));
        setModelDownloads(downloads.items); setWorkflowRuns(workflows.items);
        setMaterials(previous => mergeRecords(inputMaterials.items, previous.filter(item => pinned.has(item.id) && !inputMaterials.items.some(fresh => fresh.id === item.id))));
        setModels(previous => window.ailabHF && !m.next_cursor ? m.items
          : mergeRecords(m.items, previous.filter(item => pinned.has(item.id) && !m.items.some(fresh => fresh.id === item.id))));
        setAdapters(previous => mergeRecords(a.items, previous.filter(item => pinned.has(item.id) && !a.items.some(fresh => fresh.id === item.id))));
        setEvaluationPlans(previous => mergeRecords(plans.items, previous.filter(item => pinned.has(item.id) && !plans.items.some(fresh => fresh.id === item.id))));
        setCandidates(accepted.items); setDatasets(previous => mergeRecords(d.items, previous.filter(item => pinned.has(item.id) && !d.items.some(fresh => fresh.id === item.id)))); setTasks(t.items); setWorks(w.items);
        markStartup('resources_ready'); setProjectResourcesReady(projectId); setProjectResourcesLoaded(true);
        setCursors(previous => ({ projects: previous.projects, models: m.next_cursor, datasets: d.next_cursor, tasks: t.next_cursor, works: w.next_cursor, adapters: a.next_cursor, 'evaluation-plans': plans.next_cursor, candidates: accepted.next_cursor, materials: inputMaterials.next_cursor, 'workflow-runs': workflows.next_cursor, 'model-downloads': downloads.next_cursor })); setError('');
      } catch (e) { if (live && epoch === libraryReadEpoch.current) setProjectResourcesError(errorMessage(e)); }
    }
    void loadProject(); return () => { live = false; };
  }, [projectId, refresh]);
  const loadEnvironment = useCallback(async (force = false) => {
    if (recovery.current || librarySwitching.current || environmentInFlight.current) return;
    const epoch = environmentEpoch.current;
    environmentInFlight.current = true; setEnvironmentBusy(true); setEnvironmentReady(false); setEnvironmentError('');
    markStartup('environment_started');
    try {
      if (window.ailabHF) {
        const report = await api<WindowsEnvironmentReport>('GET', force ? '/environment?refresh=true' : '/environment');
        if (epoch !== environmentEpoch.current) return;
        setWindowsReport(report); setDevices(report.devices); setCapabilities(report.capabilities);
        markStartup('capabilities_ready'); markStartup('devices_ready'); setEnvironmentReady(true);
        return;
      }
      // 显式刷新先完成各引擎探测，再读取使用同份探测结果的设备列表。
      const caps = await collection<Capability>(force ? '/capabilities?refresh=true' : '/capabilities');
      if (epoch !== environmentEpoch.current) return;
      markStartup('capabilities_ready');
      const result = await collection<Device>('/devices');
      if (epoch !== environmentEpoch.current) return;
      markStartup('devices_ready');
      setDevices(result.items); setCapabilities(caps.items); setEnvironmentReady(true);
    } catch (e) { if (epoch === environmentEpoch.current) setEnvironmentError(errorMessage(e)); }
    finally { if (epoch === environmentEpoch.current) { environmentInFlight.current = false; setEnvironmentBusy(false); } }
  }, []);
  useEffect(() => {
    setEnvironmentReady(false); setEnvironmentBusy(false);
    return () => { environmentEpoch.current += 1; environmentInFlight.current = false; };
  }, [environmentConnected]);

  function openEnvironment() {
    setModal('settings');
    if (window.ailabHF) void loadEnvironment(true);
  }
  // 宿主健康后即可与项目并行；项目返回不会清理已经在途的环境请求。
  useEffect(() => { if (environmentConnected) void loadEnvironment(); }, [environmentConnected, refresh, loadEnvironment]);
  async function loadMore<T extends { id: string }>(name: string, setter: React.Dispatch<React.SetStateAction<T[]>>) {
    const cursor = cursors[name]; if (!cursor || pageBusy[name]) return;
    const epoch = pageEpoch.current; const version = navigationVersion.current;
    setPageBusy(previous => ({ ...previous, [name]: true })); setError('');
    try {
      const path = name === 'projects' ? '/projects' : `/${name}?project_id=${encodeURIComponent(projectId)}`;
      const result = await collection<T>(path, cursor);
      if (epoch !== pageEpoch.current || version !== navigationVersion.current) return;
      setter(previous => mergeRecords(previous, result.items)); setCursors(previous => ({ ...previous, [name]: result.next_cursor }));
    } catch (e) { if (epoch === pageEpoch.current && version === navigationVersion.current) setError(errorMessage(e)); }
    finally { if (epoch === pageEpoch.current) setPageBusy(previous => ({ ...previous, [name]: false })); }
  }
  function moreButton<T extends { id: string }>(name: string, label: string, setter: React.Dispatch<React.SetStateAction<T[]>>) {
    return <PaginationButton key={`${name}:${name === 'projects' ? 'all' : projectId}`} label={label} hasMore={Boolean(cursors[name])} busy={Boolean(pageBusy[name])} onLoad={() => void loadMore(name, setter)} />;
  }
  useEffect(() => {
    if (recovery.current || !selectedTask || selectedTask.project_id !== projectId) return;
    let live = true; const epoch = libraryReadEpoch.current;
    const currentDraft = editingDraft.current?.taskId === selectedTask.id ? editingDraft.current.draft : selectedTask.draft;
    const refs = [
      { path: 'models', id: currentDraft.model_id, items: models, apply: (value: Model) => setModels(items => mergeRecords(items, [value])) },
      { path: 'models', id: currentDraft.candidate_model_id, items: models, apply: (value: Model) => setModels(items => mergeRecords(items, [value])) },
      { path: 'datasets', id: currentDraft.dataset_id, items: datasets, apply: (value: Dataset) => setDatasets(items => mergeRecords(items, [value])) },
      { path: 'adapters', id: currentDraft.adapter_id, items: adapters, apply: (value: Adapter) => setAdapters(items => mergeRecords(items, [value])) },
      { path: 'materials', id: currentDraft.input.material_id, items: materials, apply: (value: Material) => setMaterials(items => mergeRecords(items, [value])) },
      { path: 'evaluation-plans', id: currentDraft.evaluation_plan_id, items: evaluationPlans, apply: (value: EvaluationPlan) => setEvaluationPlans(items => mergeRecords(items, [value])) },
    ];
    for (const ref of refs) if (ref.id && !ref.items.some(item => item.id === ref.id)) {
      void api<{ id: string; project_id?: string }>('GET', `/${ref.path}/${ref.id}`).then(value => {
        if (!live || epoch !== libraryReadEpoch.current) return;
        if (value.id !== ref.id || (value.project_id && value.project_id !== projectId)) throw new Error('原任务引用的资源不属于当前项目。');
        (ref.apply as (value: unknown) => void)(value);
      }).catch(e => { if (live && epoch === libraryReadEpoch.current) setError(errorMessage(e)); });
    }
    return () => { live = false; };
  }, [selectedTask, projectId, models, datasets, adapters, materials, evaluationPlans]);
  async function createProject(name: string) {
    if (leaveTask.current && !(await leaveTask.current())) throw new Error('当前任务尚未保存或操作未完成，请先处理后再创建项目。');
    leaveTask.current = null;
    const created = await api<Project>('POST', '/projects', { name });
    navigationVersion.current += 1;
    invalidateTaskEntry();
    setProjects(previous => [...previous, created]); changeProject(created.id); setPage('home'); setModal(null); reload();
  }
  function applyProjectView(id: string) {
    const view = contexts.view(id);
    setContextReadyProject(null);
    setPage(view.page); setKind(view.kind); setModuleTab(view.module_tab); setDataTab(view.data_tab);
  }
  function changeProject(id: string) {
    // 项目选择立即入队；资源仍在读取时退出，也保留该项目原先选中的对象。
    void rememberView(id, contexts.view(id)).catch(() => {});
    applyProjectView(id);
    setSplittingDataset(null);
    setProjectResourcesLoaded(false); setProjectResourcesError(''); pageEpoch.current += 1; editingDraft.current = null; setCursors(previous => ({ projects: previous.projects })); setPageBusy({}); setProjectId(id); setSelectedTask(null); setSelectedWorkflow(null); setWorkflowRuns([]); setModels([]); setModelDownloads([]); setAdapters([]); setCandidates([]); setEvaluationPlans([]); setDatasets([]); setTasks([]); setWorks([]); setMaterials([]); setError('');
  }
  async function createTask(operation: Operation, initial?: { model?: Model; dataset?: Dataset; adapter?: Adapter; material?: Material; kind?: Kind; sample?: boolean }) {
    if (!projectId) { setModal('project'); return; }
    if (operation === 'generate' && initial?.model && !initial.model.execution_available && formatNames[initial.model.format]) { setFormatTrialModel(initial.model); return; }
    if (taskEntryInFlight.current) return;
    const libraryCurrent = captureLibraryRead(); const creation = ++taskCreationVersion.current;
    const startedAtNavigation = navigationVersion.current;
    const isCurrent = () => libraryCurrent() && creation === taskCreationVersion.current && startedAtNavigation === navigationVersion.current && projectRef.current === projectId;
    if (!isCurrent()) return;
    taskEntryInFlight.current = true; setBusy(true); setError('');
    try {
      const chosenModel = initial?.model;
      const selectedKind = initial?.kind || (chosenModel && window.ailabHF ? libraryModelKind(chosenModel) : chosenModel?.modality) || kind;
      let task = await api<Task>('POST', '/tasks', { project_id: projectId, kind: selectedKind, operation, name: `${kindLabels[selectedKind]}${operation === 'train' ? '微调' : '试用'} · ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}` });
      if (!isCurrent()) return;
      if (chosenModel || initial?.dataset || initial?.adapter || initial?.material) {
        const device = devices.find(item => item.id === task.draft.runtime.device_id);
        const runtime = selectMediaRuntime(task.draft, chosenModel?.pipeline, undefined, device?.free_bytes);
        task = await api<Task>('PATCH', `/tasks/${task.id}/draft`, { expected_revision: task.draft_revision, draft: { ...task.draft, model_id: chosenModel?.id || null, dataset_id: initial?.dataset?.id || null, adapter_id: initial?.adapter?.id || null, runtime, ...(initial?.sample && selectedKind==='text' ? { input: { prompt: '请用三条简短建议说明如何安排一天的学习。' } } : initial?.material ? { input: { material_id: initial.material.id } } : {}) } });
      }
      if (!isCurrent()) return;
      setSelectedTask(task); setSelectedWorkflow(null); setPage('home'); setKind(selectedKind); setModuleTab(operation); reload();
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (libraryCurrent() && creation === taskCreationVersion.current) { taskEntryInFlight.current = false; setBusy(false); } }
  }
  async function continueTask(operation: Operation, selectedKind = kind) {
    if (!projectId) { setModal('project'); return; }
    if (!contexts.loaded || busy || taskEntryInFlight.current) return;
    const libraryCurrent = captureLibraryRead(); const creation = ++taskCreationVersion.current;
    const navigation = ++navigationVersion.current;
    const isCurrent = () => libraryCurrent() && creation === taskCreationVersion.current && navigation === navigationVersion.current && projectRef.current === projectId;
    const slot: TaskSelectionKey = `${selectedKind}:${operation}`;
    taskEntryInFlight.current = true; setBusy(true); setError('');
    try {
      const savedId = contexts.view(projectId).recent_tasks?.[slot];
      let task = savedId ? await readSelected<Task>(`/tasks/${savedId}`, projectId) : null;
      if (!isCurrent()) return;
      if (savedId && !task) {
        const recent = { ...contexts.view(projectId).recent_tasks }; delete recent[slot];
        await rememberView(projectId, { ...contexts.view(projectId), recent_tasks: recent });
        if (!isCurrent()) return;
      }
      // 摘要可能不在已加载页；确认所有页后，才把没有任务作为新建依据。
      let cursor: string | null | undefined; const seen = new Set<string>();
      while (!task) {
        if (cursor) {
          if (seen.has(cursor)) throw new Error('任务列表游标重复，请刷新后重试。');
          seen.add(cursor);
        }
        const result = await collection<Task>(`/tasks?project_id=${encodeURIComponent(projectId)}`, cursor);
        if (!isCurrent()) return;
        for (const summary of result.items) {
          if (taskSelectionKey(summary) !== slot) continue;
          task = await readSelected<Task>(`/tasks/${summary.id}`, projectId);
          if (!isCurrent()) return;
          if (task) break;
        }
        if (task || !result.next_cursor) break;
        cursor = result.next_cursor;
      }
      if (!task) { taskEntryInFlight.current = false; await createTask(operation, { kind: selectedKind }); return; }
      if (taskSelectionKey(task) !== slot) throw new Error('上次任务的类别或操作已变化，请从任务记录重新选择。');
      setSelectedTask(task); setSelectedWorkflow(null); setPage('home'); setKind(selectedKind); setModuleTab(operation);
    } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
    finally { if (libraryCurrent() && creation === taskCreationVersion.current) { taskEntryInFlight.current = false; setBusy(false); } }
  }
  async function openTask(task: Task) {
    const opening = ++taskOpenVersion.current;
    if (task.workflow_ref?.workflow_run_id && !(task.latest_attempt && (task.latest_attempt.recovery_required || activeStates.has(task.latest_attempt.state) || task.latest_attempt.state === 'failed'))) { await navigate(() => { setSelectedTask(null); setSelectedWorkflow(task.workflow_ref!.workflow_run_id); setPage('home'); setModal(null); }); return; }
    if (task.operation === 'export') {
      if (!task.export_id) { setError('导出记录缺少来源编号，请刷新后重试。'); return; }
      const startedAtNavigation = navigationVersion.current;
      const libraryCurrent = captureLibraryRead();
      const isCurrent = () => mounted.current && libraryCurrent() && startedAtNavigation === navigationVersion.current && opening === taskOpenVersion.current;
      try {
        const record = await api<ExportRecord>('GET', `/exports/${task.export_id}`);
        if (!isCurrent()) return;
        setExporting({ object: { type: record.object_type, id: record.object_id, name: record.object_name || task.name, ...('work_revision_id' in record ? { work_revision_id: record.work_revision_id } : {}) }, initial: record }); setModal(null);
      } catch (e) { if (isCurrent()) setError(errorMessage(e)); }
      return;
    }
    if (task.operation !== 'generate' && task.operation !== 'train' && task.operation !== 'evaluate' && task.operation !== 'quantize' && task.operation !== 'merge' && task.operation !== 'distill' && task.operation !== 'convert') { setError('此任务需从对应的实验入口查看，不能使用普通运行表单重新提交。'); return; }
    await navigate(() => {
      const version = navigationVersion.current; setError('');
      void api<Task>('GET', `/tasks/${task.id}`).then(current => {
        if (version !== navigationVersion.current) return;
        if (current.id !== task.id || current.project_id !== projectId) throw new Error('任务已不属于当前项目，请刷新。');
        setSelectedTask(current); setSelectedWorkflow(null); setPage('home'); setModal(null);
        if (current.kind !== 'export') setKind(current.kind);
      }).catch(e => { if (version === navigationVersion.current) setError(errorMessage(e)); });
    });
  }
  async function useImageWork(work: Work) {
    const version = navigationVersion.current;
    if (!materialKeys.current.has(work.id)) materialKeys.current.set(work.id, crypto.randomUUID());
    setBusy(true); setError('');
    try {
      const material = await api<Material>('POST', `/works/${work.id}/materials`, {}, materialKeys.current.get(work.id));
      if (navigationVersion.current !== version) return;
      setMaterials(previous => [...previous.filter(item => item.id !== material.id), material]);
      await createTask('generate', { kind: 'video', material });
    } catch (e) { if (navigationVersion.current === version) setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  const recentTasks = tasks.filter(task => task.kind === kind);
  function taskNextStep(task: Task) {
    if (task.latest_attempt?.recovery_required) return '核实停止状态';
    if (task.latest_attempt && activeStates.has(task.latest_attempt.state)) return '查看运行';
    if (task.latest_attempt?.state === 'failed') return '查看失败原因';
    if (task.workflow_ref != null) return '查看工作流';
    if (task.operation === 'evaluate') return '查看评测';
    if (task.operation === 'quantize') return '查看量化';
    if (task.operation === 'convert') return '查看转换';
    if (task.operation === 'merge') return '查看合并';
    if (task.operation === 'distill') return '查看蒸馏';
    if (task.operation === 'export') return '查看导出';
    if (task.latest_attempt?.state === 'succeeded') return '查看结果';
    return '继续配置';
  }
  const [deletePending, setDeletePending] = useState<{kind: 'task' | 'model' | 'download' | 'work'; id: string; name: string; registered?: boolean} | null>(null);
  const deleteDescriptions = {
      task: '删除任务列表中的记录。已保存的作品和运行产物会保留。',
      model: '删除模型及其本应用保存的模型文件。使用此模型的草稿将需要重新选择模型。',
      download: deletePending?.registered ? '删除下载记录，模型库中已登记的模型和文件会保留。' : '删除下载记录及已下载的文件和续传缓存。',
      work: '删除作品列表中的记录，来源运行的产物会保留。',
    };
  function deleteItem(kind: 'task' | 'model' | 'download' | 'work', id: string, name: string, registered = false) {
    setDeletePending({kind, id, name, registered});
  }
  async function confirmDelete() {
    if (!deletePending) return;
    const {kind, id} = deletePending;
    if (kind === 'task' && selectedTask?.id === id) {
      setError('请先退出当前任务，再删除其记录。');
      setDeletePending(null);
      return;
    }
    setBusy(true); setError('');
    try {
      const paths = {task:'tasks', model:'models', download:'model-downloads', work:'works'};
      await api('DELETE', '/' + paths[kind] + '/' + encodeURIComponent(id) + '?project_id=' + encodeURIComponent(projectId));
      if (kind === 'model') setModels(previous => previous.filter(item => item.id !== id));
      setDeletePending(null);
      reload();
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }
  function taskRows(list: Task[]) {
    if (!list.length && cursors.tasks) return <Empty title="已加载记录中暂无此类任务">还有较早的任务未加载，请使用页面下方的“加载更多任务”继续查找。</Empty>;
    return list.length ? <div className="task-list">{list.map(task => <div className="deletable-row" key={task.id}><button tabIndex={0} className="task-row" data-timing-action="open_task" onClick={() => void openTask(task)}><div className="task-symbol">{task.operation === 'train' ? <FlaskConical size={17} /> : <Play size={17} />}</div><span className="task-name"><strong>{task.name}</strong><small>{task.kind === 'export' ? '作品' : kindLabels[task.kind]} · {task.operation === 'train' ? '训练 / 微调' : task.operation === 'export' ? '导出' : task.operation === 'evaluate' ? '评测' : task.operation === 'quantize' ? '量化' : task.operation === 'merge' ? '合并' : task.operation === 'distill' ? '蒸馏' : task.operation === 'convert' ? '格式转换' : '运行 / 试用'} · {formatDate(task.created_at)}</small><small>编号：{task.id}</small></span><span className="task-state"><Badge tone={task.latest_attempt?.state === 'succeeded' ? 'good' : ''}>{task.latest_attempt?.recovery_required ? '停止状态待核实' : stateNames[task.latest_attempt?.state || 'draft'] || '草稿'}</Badge><small>{taskNextStep(task)}</small></span><ChevronRight size={16} /></button>{window.ailabHF && <Button disabled={busy} onClick={() => void deleteItem('task', task.id, task.name)}>删除</Button>}</div>)}</div> : <Empty title="还没有任务记录">创建一次训练或试用，输入、配方和结果会保存在这里。</Empty>;
  }
  const taskEntryReady = connected && contextAvailable && (!projectId || (projectResourcesLoaded && projectResourcesReady === projectId));
  function taskEntryLabel(operation: Operation) {
    const slot: TaskSelectionKey = `${kind}:${operation}`;
    const hasPrevious = contexts.view(projectId).recent_tasks?.[slot] || tasks.some(task => taskSelectionKey(task) === slot);
    return hasPrevious ? (operation === 'train' ? '继续上次训练' : '继续上次运行') : (operation === 'train' ? '开始训练 / 微调' : '运行 / 试用');
  }
  function prepareModel(initial?: ModelDownload) { setDownloadInitial(initial); setModal('model-download'); }
  function firstExample() { const model = models.find(item => (!item.modality || item.modality === 'text') && item.status !== 'experimental' && (!window.ailabHF || item.execution_available)); if (model) void createTask('generate', { model, sample: true }); else prepareModel(); }
  function homeContent() {
    const libraryPicker = Boolean(window.ailabHF) && moduleTab === 'generate';
    const trialModel = libraryPicker && trialSelection?.project === projectId
      ? models.find(model => model.id === trialSelection.modelId && libraryModelKind(model) === kind && model.execution_available !== false)
      : undefined;
    const openTrial = () => trialModel ? createTask('generate', { model: trialModel }) : continueTask('generate');
    return <><div className="page-heading"><div><h1>模型训练与运行</h1><p>从一次试用开始，或用自己的数据微调模型。</p></div><Button primary busy={busy} disabled={!taskEntryReady} onClick={() => void openTrial()}><Play size={16} />直接试用</Button></div>
      <section className="first-use" aria-label="首次使用引导"><h2>从第一个真实结果开始</h2><p>先准备模型，再检查设备，最后建立一个可修改的示例任务。</p><div className="dialog-actions"><Button onClick={() => prepareModel()}>1 · 准备官方语言模型</Button><Button data-timing-action="open_settings" onClick={openEnvironment}>2 · 检查本机环境</Button><Button primary busy={busy} onClick={firstExample}>3 · 建立示例草稿</Button></div><small className="muted">示例是普通文字输入，结果由本机模型实际生成。你也可以跳过引导，自行导入模型。</small></section><div className="category-grid" aria-label="训练工作台分类">{categories.map(({ kind: value, title, description, Icon, color }) => <button tabIndex={0} key={value} className={`category ${kind === value ? 'selected' : ''}`} onClick={() => void navigate(() => setKind(value))} aria-pressed={kind === value}><span className={`category-icon ${color}`}><Icon size={21} /></span><strong>{title}</strong><small>{description}</small></button>)}</div>
      <div className="workspace-panel"><div className="module-heading"><div><h2>{kind === 'text' ? '语言与多模态' : `${kindLabels[kind]}工作台`}</h2><small>模型、材料和结果，在同一处继续工作</small></div><Badge>{capabilities.some(item => item.kind === kind && item.supported) ? (kind === 'text' ? (window.ailabHF ? '本机 GGUF' : '本机 MLX') : kind === 'audio' ? '本机 CPU 配音' : '本机图片 / 视频引擎') : '请检查运行环境'}</Badge></div>
      <div className="tabs" role="tablist" aria-label="工作台操作"><button tabIndex={0} role="tab" aria-selected={moduleTab === 'train'} onClick={() => void navigate(() => setModuleTab('train'))}><FlaskConical size={15} />训练 / 微调</button><button tabIndex={0} role="tab" aria-selected={moduleTab === 'generate'} onClick={() => void navigate(() => setModuleTab('generate'))}><Play size={15} />运行 / 试用</button><button tabIndex={0} role="tab" aria-selected={moduleTab === 'history'} onClick={() => void navigate(() => setModuleTab('history'))}><History size={15} />任务与结果</button></div>
      {moduleTab === 'history' ? taskRows(recentTasks) : <div className="module-start"><div><h3>{moduleTab === 'train' ? `让${kindLabels[kind]}适应你的任务` : '先看模型的实际表现'}</h3><p>{moduleTab === 'train' ? '选择基座模型和自己的数据，检查训练配置后运行。每次训练保留独立产物，方便与基线比较。' : '导入本机模型，输入内容后直接试用。运行参数和输出一并保存，可从历史继续调整。'}</p>{libraryPicker ? <TrialModelSelect id="trial-library-model" models={models} kind={kind} value={trialModel?.id || ''}
        onChange={modelId => setTrialSelection({ project: projectId, modelId })} /> : <div className="steps"><span><b>1</b>选择模型</span><ChevronRight size={14} /><span><b>2</b>{moduleTab === 'train' ? '准备数据' : '填写输入'}</span><ChevronRight size={14} /><span><b>3</b>检查并运行</span></div>}{kind !== 'text' && <p className="warning">{moduleTab === 'train' && kind !== 'image' ? '本组合尚未开放训练，请从“运行 / 试用”体验图片生成短视频或中文配音。' : kind === 'video' ? '首个组合使用 PNG 图片生成约两秒短片，可能只有轻微运动。' : kind === 'audio' ? '首个组合开放小北音色中文配音。模型与运行环境将在开始前实际检查。' : '首个组合支持 Tiny-SD 图片生成和 LoRA 微调，输出质量需检查实际结果。'}</p>}<div className="card-actions"><Button primary busy={busy} disabled={!taskEntryReady || !projectId || (moduleTab === 'train' && !['text', 'image'].includes(kind))} onClick={() => void (moduleTab === 'generate' ? openTrial() : continueTask(moduleTab))}><Play size={16} />{trialModel ? '用所选模型试用' : taskEntryLabel(moduleTab)}</Button>{!trialModel && <Button busy={busy} disabled={!taskEntryReady || !projectId || (moduleTab === 'train' && !['text', 'image'].includes(kind))} onClick={() => void createTask(moduleTab)}><Plus size={16} />{moduleTab === 'train' ? '新建训练' : '新建试用'}</Button>}</div></div><div className="ready-check"><strong>当前项目的准备情况</strong><button tabIndex={0} onClick={() => setPage('models')}><Boxes size={17} /><span>模型<small>{models.length ? `已加载 ${models.length} 个模型` : '导入你的第一个模型'}</small></span><ChevronRight size={15} /></button><button tabIndex={0} onClick={() => { setPage('data'); setDataTab('local'); }}><Database size={17} /><span>数据<small>{datasets.length ? `已加载 ${datasets.length} 个已检查数据` : '训练前准备本机数据'}</small></span><ChevronRight size={15} /></button><button tabIndex={0} data-timing-action="open_settings" onClick={openEnvironment}><Server size={17} /><span>设备与环境<small>{devices[0]?.name || '查看本机运行环境'}</small></span><ChevronRight size={15} /></button></div></div>}</div>
      {moduleTab !== 'history' && <section className="recent-section"><div className="section-title"><h2>最近任务</h2><button tabIndex={0} className="text-button" onClick={() => void navigate(() => setModuleTab('history'))}>查看全部<ChevronRight size={15} /></button></div>{taskRows(tasks.slice(0, 4))}</section>}
      <section className="workflow-section"><div><h2>工作流</h2><p>把不同类别的结果接起来，完成一次完整创作。</p></div><div className="workflow-card"><span className="workflow-icons"><Image size={19} /><ChevronRight size={13} /><Video size={19} /><ChevronRight size={13} /><AudioLines size={19} /></span><strong>商品图 → 视频 → 配音</strong><small>每步先查看结果，再带入下一步</small><Button primary disabled={busy || !projectId} onClick={() => setModal('workflow')}>新建工作流</Button></div></section>{workflowRuns.length > 0 && <section className="recent-section"><h2>工作流记录</h2><div className="task-list">{workflowRuns.map(run => <button tabIndex={0} className="task-row" key={run.id} onClick={() => void navigate(() => { setSelectedTask(null); setSelectedWorkflow(run.id); })}><span className="task-name"><strong>{run.name}</strong><small>{formatDate(run.created_at)} · 每轮独立保存输入与来源</small></span><Badge>{run.status === 'saved' ? '本轮已保存' : run.status === 'ready_to_save' ? '待保存本轮作品' : '进行中'}</Badge><ChevronRight size={15} /></button>)}</div></section>}
    </>;
  }
  function modelsContent() {
    return <>
      <div className="page-heading"><div><h1>模型库</h1><p>基座与训练适配器分别保存，保留清楚的来源。</p></div><div className="dialog-actions"><Button disabled={!projectId} onClick={() => prepareModel()}>准备官方模型</Button><Button primary disabled={!projectId} onClick={() => setModal('model')}><Plus size={16} />导入模型</Button></div></div>
      {models.length ? <div className="resource-grid">{models.map(model => <article className="resource-card" key={model.id}>
        <span className="resource-icon"><Boxes size={22} /></span><div><h2>{model.name}</h2><p>{model.format} · {model.modality === 'text' ? '语言' : model.modality ? kindLabels[model.modality] : '语言'}模型</p></div><Badge tone={modelQualityPassed(model) ? 'good' : ''}>{modelQualityPassed(model) ? '量化候选 · 质量通过' : model.status === 'experimental' || model.conversion ? '实验模型 · 待验收' : '已导入'}</Badge>
        <div className="resource-bottom"><small>{modelQualityPassed(model) ? model.quality_scope || '仅覆盖首次固定评测集，不代表普遍质量或速度收益' : model.conversion ? 'MLX 4-bit · 质量未验收' : '执行兼容性由运行前检查确认'}</small><div className="card-actions">{canEvaluateModel(model) && <Button disabled={!evaluationPlans.length} onClick={() => setEvaluationStart({ modelId: model.id })}>量化质量评测</Button>}{window.ailabHF && <Button disabled={busy} onClick={() => void deleteItem('model', model.id, model.name)}>删除模型</Button>}<Button onClick={() => setExporting({ object: { type: 'model', id: model.id, name: model.name } })}>导出</Button><Button onClick={() => void createTask('generate', { model })} disabled={Boolean(window.ailabHF && !model.execution_available)} busy={busy}><Play size={14} />试用</Button></div></div>
      </article>)}</div> : <Empty title="导入第一个模型" action={<Button primary onClick={() => setModal('model')} disabled={!projectId}><Folder size={16} />选择本机模型</Button>}>选择包含权重、配置和分词器的文件夹。检查通过后加入当前项目。</Empty>}
      {modelDownloads.length > 0 && <section className="recent-section"><h2>模型准备记录</h2><p className="muted">下载、停止、续传与登记都保留在当前项目；完整文件不会自动运行。</p><div className="task-list">{modelDownloads.map(item => <div className="deletable-row" key={item.id}><button tabIndex={0} className="task-row" onClick={() => prepareModel(item)}><span className="task-name"><strong>{item.name}</strong><small>{readableSize(item.received_bytes)} / {readableSize(item.total_bytes)} · {formatDate(item.created_at)}</small></span><Badge>{item.model_id ? '已加入模型库' : modelDownloadStates[item.state] || item.state}</Badge><ChevronRight size={15} /></button>{window.ailabHF && <Button disabled={busy} onClick={() => void deleteItem('download', item.id, item.name, Boolean(item.model_id))}>删除记录</Button>}</div>)}</div></section>}
      {adapters.length > 0 && <section className="recent-section"><div className="section-title"><h2>训练适配器</h2><Badge>实验产物</Badge></div><p className="muted">用于比较训练前后的输出。适配器依赖固定基座，质量通过后才能登记为已验收候选。</p><div className="resource-grid">{adapters.map(adapter => <article className="resource-card" key={adapter.id}>
        <span className="resource-icon"><FlaskConical size={22} /></span><div><h2>{adapter.name}</h2><p>基座：{models.find(model => model.id === adapter.base_model_id)?.name || adapter.base_model_id}</p></div><Badge tone={candidates.some(item => item.adapter_id === adapter.id) ? 'good' : ''}>{candidates.some(item => item.adapter_id === adapter.id) ? '已登记候选' : '待验收'}</Badge>
        <div className="resource-bottom"><small>来源运行 {adapter.source_attempt_id.slice(-8)}</small><div className="card-actions"><Button onClick={() => setExporting({ object: { type: 'adapter', id: adapter.id, name: adapter.name } })}>导出适配器</Button><Button disabled={!evaluationPlans.length || models.find(model => model.id === adapter.base_model_id)?.modality !== 'text'} onClick={() => setEvaluationStart({ adapterId: adapter.id })}>独立评测</Button><Button busy={busy} disabled={!models.some(model => model.id === adapter.base_model_id)} onClick={() => void createTask('generate', { model: models.find(model => model.id === adapter.base_model_id), adapter })}>试用实验产物</Button></div></div>
      </article>)}</div></section>}
    </>;
  }
  function dataContent() {
    return <><div className="page-heading"><div><h1>数据集市场</h1><p>准备本机数据，或从已连接的来源获取材料。</p></div><div className="dialog-actions"><Button disabled={!projectId} onClick={() => setModal('image-dataset')}>导入图片数据</Button><Button primary disabled={!projectId} onClick={() => setModal('dataset')}><Plus size={16} />导入语言数据</Button></div></div><div className="tabs" role="tablist" aria-label="数据来源"><button tabIndex={0} role="tab" aria-selected={dataTab === 'local'} onClick={() => setDataTab('local')}>我的数据</button><button tabIndex={0} role="tab" aria-selected={dataTab === 'market'} onClick={() => setDataTab('market')}>数据集市场</button></div>{dataTab === 'market' ? <Empty title="浏览数据来源" action={<Button primary onClick={() => setModal('market')}>打开数据市场</Button>}>查看版本与来源说明，申请访问、下载并检查后导入当前项目。可在设备与环境中连接受控测试来源。</Empty> : datasets.length ? <div className="resource-grid">{datasets.map(dataset => <article className="resource-card" key={dataset.id}><span className="resource-icon"><Database size={22} /></span><div><h2>{dataset.name}</h2><p>{dataset.schema || 'JSONL'} · {dataset.sample_count || 0} 条样本</p></div><Badge tone={dataset.dataset_split_role === 'validation' ? '' : 'good'}>{dataset.dataset_split_role === 'train' ? '训练子集' : dataset.dataset_split_role === 'validation' ? '验证子集' : '已检查'}</Badge><div className="resource-bottom" style={{ flexWrap: 'wrap' }}><small>独立版本 · 原文件保留</small><div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>{dataset.schema !== 'image_caption_v1' && <Button disabled={busy} onClick={() => setSplittingDataset(dataset)}>{dataset.dataset_split_id ? '查看划分' : '划分训练与验证'}</Button>}{dataset.dataset_split_id && <Button disabled={busy} onClick={() => setExporting({ object: { type: 'dataset-split', id: dataset.dataset_split_id!, name: `${dataset.name}的数据划分` } })}>导出划分</Button>}<Button disabled={busy || dataset.dataset_split_role === 'validation'} onClick={() => { const selectedKind = dataset.schema === 'image_caption_v1' ? 'image' : 'text'; setKind(selectedKind); void createTask('train', { kind: selectedKind, dataset }); }}>{dataset.dataset_split_role === 'validation' ? '验证子集不用于训练' : '用于训练'}<ChevronRight size={14} /></Button></div></div></article>)}</div> : <Empty title="准备训练数据" action={<Button primary disabled={!projectId} onClick={() => setModal('dataset')}>选择本机 JSONL</Button>}>导入时检查消息结构、样本内容和文件完整性，训练前进一步检查监督范围。</Empty>}</>;
  }
  function labContent() { return <><div className="page-heading"><div><h1>模型实验室</h1><p>先确定评测标准，再比较基线与训练或量化产物。</p></div><Button primary onClick={() => setModal('evaluation-plan')}>冻结评测方案</Button></div><section className="workspace-panel lab-evaluation"><div className="section-title"><h2>文本质量评测</h2><Button disabled={(!adapters.length && !models.some(canEvaluateModel)) || !evaluationPlans.length} onClick={() => setEvaluationStart({})}>新建独立评测</Button></div><p className="muted">训练前冻结问题和规则，并在训练配置中绑定。已有适配器可以做事后对照，事后对照不能用于候选准入。量化模型固定比较原权重与转换产物，首次评测时绑定准入方案，其他方案只作对照。</p>{evaluationPlans.length ? <div className="resource-grid">{evaluationPlans.map(plan => <PlanSummary key={plan.id} plan={plan} />)}</div> : <Empty title="先准备一份固定评测方案">包含业务、格式、回归和行为四类独立问题；每类都需达到预定通过率。</Empty>}</section><section className="recent-section"><h2>评测任务</h2>{taskRows(tasks.filter(item => item.operation === 'evaluate'))}</section><section className="workspace-panel lab-evaluation"><div className="section-title"><h2>量化与格式转换</h2><div className="card-actions"><Button onClick={() => setModal('conversion')}>新建量化实验</Button><Button onClick={() => setModal('format-conversion')}>新建格式转换</Button></div></div><p className="muted">Qwen2.5-0.5B 支持 MLX 4-bit 量化，以及 Core ML、ONNX、TorchScript 的固定形状 CPU 转换。输出作为实验模型保存。</p>{taskRows(tasks.filter(item => ['quantize', 'convert'].includes(item.operation)))}</section><div className="lab-grid">{([{ operation: 'merge', title: '模型合并', text: '将 LoRA 按比例融合到原始基座，生成独立权重并重新加载核对。' }, { operation: 'distill', title: '离线蒸馏', text: '本地教师生成回答，学生实际训练并融合为独立模型。' }] as const).map(item => <section className="lab-card" key={item.title}><FlaskConical size={22} /><h2>{item.title}</h2><p>{item.text}</p><Button onClick={() => setModal(item.operation)}>新建{item.operation === 'merge' ? '合并' : '蒸馏'}实验</Button></section>)}</div><section className="recent-section"><h2>合并与蒸馏任务</h2>{taskRows(tasks.filter(item => ['merge', 'distill'].includes(item.operation)))}</section></>; }
  function assetsContent() {
    return <div className="assets-page">
      <div className="page-heading"><div><h1>作品与素材</h1><p>保存有价值的结果，查看生成配方，或作为下一项任务的素材。</p></div><Button disabled={!projectId} onClick={() => setModal('material')}><Plus size={16} />导入图片素材</Button></div>
      {works.length ? <div className="works-grid">{works.map(work => <article className="work-card" key={work.id}>
        <div className="section-title"><h2>{work.name || '模型输出'}</h2><Badge>已保存</Badge></div>
        {work.artifact_id && work.media_type && ['image/png', 'video/mp4', 'audio/wav'].includes(work.media_type) ? <MediaPreview artifact={{ id: work.artifact_id, media_type: work.media_type }} name={work.name || '已保存作品'} /> : <p className="work-text">{work.text || work.content || '文件产物已保存'}</p>}
        {work.text_truncated && <p className="muted">此处为内容预览，导出可取得完整文本。</p>}
        <small>{formatDate(work.created_at)} · 来源 {work.attempt_id}</small>
        <WorkRecipeActions key={`${projectId}:${work.id}`} work={work} projectId={projectId} reuseKeys={workReuseKeys.current} onUpdated={reload} onCreated={task => {
          if (task.project_id !== projectRef.current || librarySwitching.current) return;
          void navigate(() => { setTasks(items => mergeRecords(items, [task])); setKind(task.draft.kind); setModuleTab('generate'); setSelectedTask(task); setSelectedWorkflow(null); setPage('home'); reload(); });
        }} />
        <div className="card-actions">{window.ailabHF && <Button disabled={busy} onClick={() => void deleteItem('work', work.id, work.name || '模型输出')}>删除作品</Button>}{(!work.kind || ['text', 'video', 'audio'].includes(work.kind)) && <Button onClick={event => { event.currentTarget.focus({ preventScroll: true }); setRevisingWork(work); }}>{work.kind === 'video' ? '字幕修订' : work.kind === 'audio' ? '配音文案修订' : '文字修订'}{work.current_revision_id ? ' · 已有修订' : ''}</Button>}<Button onClick={() => setExporting({ object: { type: 'work', id: work.id, name: work.name || '作品' } })}>导出原作品</Button>{work.kind === 'image' && <Button busy={busy} onClick={() => void useImageWork(work)}>用作视频输入<ChevronRight size={14} /></Button>}</div>
      </article>)}</div> : <Empty title="还没有保存的作品">完成一次运行后，在结果页点击“保存作品”。每份作品保留原模型、输入和运行配置。</Empty>}
      <section className="recent-section"><div className="section-title"><h2>输入素材</h2><Badge>{materials.length} 项</Badge></div>
        {materials.length ? <div className="resource-grid">{materials.map(material => <article className="resource-card" key={material.id}><div><h3>{material.name}</h3><p>PNG · {material.width}×{material.height} · {readableSize(material.total_bytes)}</p></div><small>{material.source_work_id ? '来自已保存的图片作品，来源已保留' : '本机导入的独立素材版本'}</small><Button busy={busy} onClick={() => void createTask('generate', { kind: 'video', material })}>用于视频任务</Button></article>)}</div> : <p className="muted">导入 PNG，或把已保存的图片作品用作视频输入，素材版本会保存在这里。</p>}
      </section>
    </div>;
  }
  if (recoveryMode) return <main className="app-work" inert={exitPreparation.preparing} aria-busy={exitPreparation.preparing}><section className="review-box" aria-label="备份恢复工作区"><h1>从备份恢复工作库</h1><p>原工作库及失败证据会保留。这里仅用于检查和恢复备份；恢复到新目录后，需明确切换才会打开项目与历史。未切换就退出会保留原工作库选择；下次进入恢复会建立新会话，先前的恢复目录仍保留。</p><ErrorNotice message={error} /><ErrorNotice message={exitPreparation.error} /><Button primary busy={busy} onClick={() => void openBackupRecovery()}>选择备份继续恢复</Button></section>{modal === 'backup' && <BackupDialog restoreOnly onBusyChange={value => { recoveryOperationBusy.current = value; }} onClose={() => setModal(null)} onLibrarySwitchStart={beginLibrarySwitch} onLibrarySwitchFailed={failedLibrarySwitch} onLibraryChanged={onLibraryChanged} />}</main>;
  return <LibraryReadContext.Provider value={captureLibraryRead}><div className="app-shell" inert={exitPreparation.preparing} aria-busy={exitPreparation.preparing}><aside className="sidebar"><div className="brand"><span className="brand-mark">A</span><div><strong>AiLab</strong><small>模型训练与运行</small></div></div><nav aria-label="主导航">{navigation.map(({ id, label, Icon }) => <button data-timing-action={id === 'models' ? 'navigate_models' : undefined} tabIndex={0} key={id} aria-current={page === id ? 'page' : undefined} onClick={() => void navigate(() => { setPage(id); setSelectedTask(null); setSelectedWorkflow(null); })}><Icon size={18} /><span>{label}</span></button>)}</nav><div className="sidebar-bottom"><button tabIndex={0} data-timing-action="open_settings" onClick={openEnvironment}><Server size={17} />设备与环境</button><button tabIndex={0} onClick={() => setAiOpen(value => !value)}><Sparkles size={17} />AI 连接</button><span className={`connection ${connected ? 'online' : ''}`}><i />{connected ? '本机服务已连接' : '本机服务未连接'}</span><small>技术预览 · {APP_VERSION_LABEL}</small></div></aside><div className="app-work"><header className="topbar"><div className="project-selector"><Folder size={17} /><select aria-label="当前项目" disabled={!projectsLoaded} value={projectId} onChange={e => { const id = e.target.value; void navigate(() => changeProject(id)); }}>{projects.length ? projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>) : <option value="">{projectsLoaded ? '尚未创建项目' : loading ? '正在读取工作库' : '工作库读取失败'}</option>}</select>{moreButton('projects', '项目', setProjects)}<button tabIndex={0} className="icon-button" aria-label="新建项目" onClick={() => setModal('project')} disabled={!connected}><Plus size={16} /></button></div><div className="top-actions"><Badge>本地优先</Badge><button tabIndex={0} className="header-button" onClick={() => setModal('queue')}><History size={16} /><span>任务队列</span></button><button tabIndex={0} className={`header-button ${aiOpen ? 'active' : ''}`} aria-pressed={aiOpen} onClick={() => setAiOpen(value => !value)}><Sparkles size={16} /><span>AI 辅助</span></button></div></header><div className={`main-and-ai ${aiOpen ? 'with-ai' : ''}`}><main><ErrorNotice message={error} /><ErrorNotice message={exitPreparation.error} /><ErrorNotice message={contextError || contextReadError} />{(contextError || contextReadError) && <Button onClick={() => void saveCurrentView().then(() => setContextError('')).catch(e => setContextError(`当前选择尚未保存：${errorMessage(e)}`))}>重试保存当前选择</Button>}<ErrorNotice message={projectResourcesError} />{projectResourcesError && <Button onClick={reload}><RefreshCw size={15} />重试加载</Button>}<ErrorNotice message={modal === 'settings' ? '' : environmentError} />{!connected ? <Empty title={loading ? '正在连接本机服务' : '本机服务尚未连接'} action={<><Button disabled={busy} onClick={async () => { if (canPickFile()) { try { await restartControl(); } catch (e) { setError(errorMessage(e)); } } reload(); }}><RefreshCw size={15} />重新连接</Button>{canPickFile() && <Button busy={busy} onClick={() => void openBackupRecovery()}>从备份恢复</Button>}</>}>启动控制服务后，项目与任务会从本机记录恢复。</Empty> : !projectId ? <Empty title="建立你的第一个项目" action={<Button primary onClick={() => setModal('project')}><Plus size={16} />新建项目</Button>}>用一个项目组织模型、数据与结果。随后可直接试用模型，或开始微调。</Empty> : !projectResourcesLoaded ? <Empty title={projectResourcesError ? '项目内容读取失败' : '正在读取项目内容'}>模型、数据、任务与作品读取完成后会在这里显示。</Empty> : selectedWorkflow ? <WorkflowRunView key={selectedWorkflow} runId={selectedWorkflow} models={models} works={works} onBack={() => { leaveTask.current = null; setSelectedWorkflow(null); }} onUpdated={reload} registerLeave={handler => { leaveTask.current = handler; }} onExport={work => setExporting({ object: { type: 'work', id: work.id, name: work.name || '工作流作品' } })} />  : selectedTask?.workflow_ref ? <section className="form-stack"><h2>工作流运行记录</h2><p>{selectedTask.name}</p><p className="muted">这里显示所选任务的运行记录。工作流当前输入可能已经变化。</p>{selectedTask.latest_attempt ? <RunResult key={selectedTask.latest_attempt.id} initial={selectedTask.latest_attempt} onChanged={reload} /> : <Empty title="此任务尚无运行记录" />}<Button onClick={() => void navigate(() => { setSelectedWorkflow(selectedTask.workflow_ref!.workflow_run_id); setSelectedTask(null); })}>查看工作流当前步骤</Button></section> : selectedTask?.operation === 'transfer' ? <RemoteTransferTask key={selectedTask.id} task={selectedTask} onBack={() => setSelectedTask(null)} onChanged={reload} /> : selectedTask && (['quantize', 'merge', 'distill', 'convert'].includes(selectedTask.operation) || Boolean(formatNames[selectedTask.draft.runtime.engine])) ? <ConversionTask key={selectedTask.id} task={selectedTask} models={models} registerLeave={handler => { leaveTask.current = handler; }} onBack={() => { leaveTask.current = null; setSelectedTask(null); setPage('lab'); }} onUpdated={reload} onExport={object => setExporting({ object })} /> : selectedTask?.operation === 'evaluate' ? <EvaluationTask key={selectedTask.id} task={selectedTask} plans={evaluationPlans} adapters={adapters} models={models} candidates={candidates} registerLeave={handler => { leaveTask.current = handler; }} onBack={() => { leaveTask.current = null; setSelectedTask(null); setPage('lab'); }} onUpdated={reload} onExport={object => setExporting({ object })} /> : selectedTask ? <Workbench key={selectedTask.id} onDraftChanged={draft => { editingDraft.current = { taskId: selectedTask.id, draft }; }} aiPanelTarget={aiOpen ? aiPanelTarget : null} task={selectedTask} models={models} datasets={datasets} devices={devices} materials={materials} adapters={adapters} evaluationPlans={evaluationPlans} onCreateEvaluationPlan={() => setModal('evaluation-plan')} onRestoreTask={task => { leaveTask.current = null; setSelectedTask(task); setSelectedWorkflow(null); setPage('home'); reload(); }} onExport={object => setExporting({ object })} onBack={() => { leaveTask.current = null; setSelectedTask(null); }} registerLeave={handler => { leaveTask.current = handler; }} onTaskChanged={saved => setSelectedTask(current => current?.id === saved.id ? saved : current)} onImport={setModal} onUpdated={reload} /> : page === 'home' ? homeContent() : page === 'models' ? modelsContent() : page === 'data' ? dataContent() : page === 'lab' ? labContent() : assetsContent()}{connected && projectId && <div className="pagination-actions" aria-label="继续加载列表">
      {(selectedTask || page === 'models') && <>{moreButton('models', '模型', setModels)}{moreButton('adapters', '训练适配器', setAdapters)}{moreButton('candidates', '候选记录', setCandidates)}{moreButton('model-downloads', '模型准备记录', setModelDownloads)}</>}
      {(selectedTask || (page === 'data' && dataTab === 'local')) && moreButton('datasets', '数据', setDatasets)}
      {(selectedTask || page === 'lab') && moreButton('evaluation-plans', '评测方案', setEvaluationPlans)}
      {(selectedTask || page === 'assets') && moreButton('materials', '素材', setMaterials)}
      {page === 'assets' && moreButton('works', '作品', setWorks)}
      {!selectedTask && ['home', 'lab'].includes(page) && <>{moreButton('tasks', '任务', setTasks)}{moreButton('workflow-runs', '工作流记录', setWorkflowRuns)}</>}
    </div>}</main>{aiOpen && <aside className="ai-panel" aria-label="AI 辅助"><div className="section-title"><h2><Sparkles size={17} />AI 辅助</h2><Badge>建议模式</Badge></div><p>帮助理解参数、检查材料和比较结果。修改先预览，执行由你决定。</p><div ref={setAIPanelTarget} />{(!selectedTask || selectedTask.workflow_ref || !['generate', 'train'].includes(selectedTask.operation)) && <Empty title="在任务中使用建议" action={window.ailabHF && !selectedTask ? <Button disabled={!taskEntryReady || busy} onClick={() => void continueTask('generate', 'text')}>打开语言试用草稿</Button> : undefined}>{window.ailabHF ? '打开试用草稿，选择模型库中的本地语言模型，然后输入你想了解的参数或希望调整的内容。' : '打开一份语言试用或训练草稿，再选择本机建议模型。建议只接收问题与当前表单允许的字段，应用前会展示旧值和新值。'}</Empty>}<div className="ai-boundary"><strong>由你决定</strong><small>建议不会自动修改草稿、启动训练或决定数据授权。</small></div></aside>}</div></div>
    {(modal === 'format-conversion' || formatTrialModel) && <FormatDialog projectId={projectId} models={models} trialModel={formatTrialModel || undefined} onClose={() => { setModal(null); setFormatTrialModel(null); }} onCreated={task => { setModal(null); setFormatTrialModel(null); void navigate(() => { setSelectedTask(task); setPage('lab'); reload(); }); }} />}
    {(modal === 'merge' || modal === 'distill') && <ModelLabDialog operation={modal} projectId={projectId} models={models} adapters={adapters} datasets={datasets} onClose={() => setModal(null)} onCreated={task => { setModal(null); void navigate(() => { setSelectedTask(task); setPage('lab'); reload(); }); }} />}
    {modal === 'conversion' && <ConversionStartDialog projectId={projectId} models={models} onClose={() => setModal(null)} onCreated={task => { setModal(null); void navigate(() => { setSelectedTask(task); setPage('lab'); reload(); }); }} />}
    {modal === 'evaluation-plan' && <EvaluationPlanDialog key={projectId} projectId={projectId} onClose={() => setModal(null)} onCreated={reload} />}
    {evaluationStart && <EvaluationStartDialog projectId={projectId} adapters={adapters} models={models} plans={evaluationPlans} initialAdapter={evaluationStart.adapterId} initialModel={evaluationStart.modelId} onClose={() => setEvaluationStart(null)} onCreated={task => { setEvaluationStart(null); void navigate(() => { setSelectedTask(task); setPage('lab'); reload(); }); }} />}
    {modal === 'diagnostics' && <DiagnosticsDialog projectId={projectId} attempts={tasks.flatMap(task => task.attempts || (task.latest_attempt ? [task.latest_attempt] : []))} onClose={() => setModal(null)} />}
    {splittingDataset && <DatasetSplitDialog key={`${projectId}:${splittingDataset.id}`} dataset={splittingDataset} models={models} projectId={projectId} onClose={() => setSplittingDataset(null)} onChanged={result => { if (result) setDatasets(items => mergeRecords(items, [result.train_dataset, result.validation_dataset])); reload(); }} onUseTraining={dataset => { setSplittingDataset(null); setKind('text'); void createTask('train', { kind: 'text', dataset }); }} onExport={object => { setSplittingDataset(null); setExporting({ object }); }} />}
    {modal === 'market' && <DatasetMarket projectId={projectId} onClose={() => setModal(null)} onDatasetImported={reload} onApplied={() => reload()} />}
    {modal === 'model-download' && <ModelDownloadDialog key={downloadInitial?.id || projectId} projectId={projectId} initial={downloadInitial} onClose={() => setModal(null)} onChanged={reload} onUse={model => { setModal(null); void createTask('generate', { model, sample: true }); }} />}
    {revisingWork && <WorkRevisions key={revisingWork.id} work={revisingWork} onClose={() => setRevisingWork(null)} onUpdated={reload} onExport={selection => { setExporting({ object: { type: 'work', id: revisingWork.id, ...selection } }); setRevisingWork(null); }} />}
    {exporting && <ExportDialog key={`${projectId}:${exporting.initial?.id || `${exporting.object.type}:${exporting.object.id}:${exporting.object.work_revision_id || 'original'}`}`} object={exporting.object} projectId={projectId} initial={exporting.initial} onClose={() => setExporting(null)} onChanged={reload} />}
    {modal === 'backup' && <BackupDialog onBeforeBackup={prepareLibraryLeave} onClose={() => setModal(null)} onLibrarySwitchStart={beginLibrarySwitch} onLibrarySwitchFailed={failedLibrarySwitch} onLibraryChanged={onLibraryChanged} />}
    {modal === 'cleanup' && <CleanupDialog onClose={() => setModal(null)} />}
    {deletePending && <Dialog title="确认删除" onClose={() => setDeletePending(null)} preventClose={busy}>
      <p>确定删除“{deletePending.name}”？</p><p>{deleteDescriptions[deletePending.kind]}</p>
      <ErrorNotice message={error} />
      <div className="dialog-actions"><Button disabled={busy} onClick={() => setDeletePending(null)}>取消</Button><Button primary busy={busy} onClick={() => void confirmDelete()}>确认删除</Button></div>
    </Dialog>}
    {modal === 'workflow' && <WorkflowStartDialog projectId={projectId} models={models} onClose={() => setModal(null)} onCreated={run => { setModal(null); setSelectedTask(null); setSelectedWorkflow(run.id); setPage('home'); reload(); }} />}
    {modal === 'project' && <ProjectDialog onClose={() => setModal(null)} onCreate={createProject} />}
    {(modal === 'model' || modal === 'dataset' || modal === 'image-dataset' || modal === 'material') && <ImportDialog key={`${projectId}:${modal}`} kind={modal} projectId={projectId} onClose={() => setModal(null)} onImported={() => { setModal(null); reload(); }} />}
    {modal === 'queue' && <Dialog title="任务队列与历史" wide onClose={() => setModal(null)}><ErrorNotice message={error} /><p className="muted">当前项目：{project?.name || '尚未选择'}</p>{taskRows(tasks)}{moreButton('tasks', '任务', setTasks)}</Dialog>}
    {modal === 'settings' && window.ailabHF && <WindowsEnvironment report={windowsReport} busy={environmentBusy} error={environmentError}
      onRefresh={() => void loadEnvironment(true)} onClose={() => setModal(null)}><InteractionTimingControls timing={timing} /></WindowsEnvironment>}
    {modal === 'settings' && !window.ailabHF && <Dialog title="设备与环境" wide onClose={() => setModal(null)}><ErrorNotice message={environmentError} /><p className="muted">只有实际探测和执行器已经接入的组合才允许提交，未验证能力保持关闭。</p><div className="device-list">{devices.map(device => <section key={device.id}><div className="section-title"><h3><Server size={18} />{device.name}</h3><Badge>{device.status ? ({ ready: '环境已准备', not_prepared: '尚未准备', unsupported: '当前不支持', unavailable: '当前不可用', error: '探测失败' } as Record<string, string>)[device.status] || '待核实' : '已探测'}</Badge></div><dl className="facts"><div><dt>设备编号</dt><dd>{device.id}</dd></div>{device.engine && <div><dt>引擎</dt><dd>{device.engine}</dd></div>}{device.memory_bytes && <div><dt>内存</dt><dd>{readableSize(device.memory_bytes)}</dd></div>}</dl></section>)}</div>{!devices.length && <Empty title="尚未取得设备信息">连接服务后重新查看。</Empty>}<section className="data-management" aria-label="各类任务环境"><h3>可用任务组合</h3><div className="form-stack">{capabilities.filter(item => item.operation === 'generate').map(item => <div key={item.kind}><strong>{kindLabels[item.kind]}：{item.supported ? '环境已准备，可选择模型检查' : '尚未准备'}</strong>{item.reason && <p className="muted">{item.reason}</p>}</div>)}</div></section><div className="dialog-footer"><small>本次输入的执行位置以任务中已应用的设备为准。</small><div className="dialog-actions">{canPickFile() && <><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await useBundledWorker(); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>使用内置运行环境</Button><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await pickWorkerPython(); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>高级：选择 Python 环境</Button><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await useBundledMedia('diffusers'); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>使用内置图片与视频环境</Button><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await useBundledMedia('kokoro'); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>使用内置配音环境</Button><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await pickMediaPython('diffusers'); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>配置图片与视频环境</Button><Button busy={busy} disabled={environmentBusy} onClick={async () => { setBusy(true); try { await pickMediaPython('kokoro'); reload(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>配置中文配音环境</Button></>}<Button busy={environmentBusy} disabled={!connected || busy} onClick={() => void loadEnvironment(true)}><RefreshCw size={15} />刷新环境</Button></div></div><ExecutionTargets key={projectId} projectId={projectId} onChanged={reload} /><MarketSourceSettings onChanged={reload} /><section className="data-management" aria-label="诊断与支持"><h3>诊断与支持</h3><p className="muted">查看版本和运行状态摘要，再保存到本机文件。</p><Button onClick={() => setModal('diagnostics')}>导出诊断摘要</Button><InteractionTimingControls timing={timing} /></section><section className="data-management" aria-label="本机数据管理"><h3>本机数据管理</h3><p className="muted">保存完整备份，或检查无人引用的资产并进行可恢复整理。</p><div className="dialog-actions"><Button disabled={busy || !connected} onClick={() => setModal('backup')}>备份与恢复</Button><Button disabled={busy || !connected} onClick={() => setModal('cleanup')}>存储清理与恢复</Button></div></section></Dialog>}
  </div></LibraryReadContext.Provider>;
}
