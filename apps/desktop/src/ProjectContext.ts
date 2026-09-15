import { api } from './api';
import type { Kind, Operation, Task } from './types';

export type Page = 'home' | 'models' | 'data' | 'lab' | 'assets';
export type TaskSelectionKey = `${Kind}:${Operation}`;
export type ProjectView = {
  page: Page; kind: Kind; module_tab: 'train' | 'generate' | 'history'; data_tab: 'local' | 'market';
  task_id: string | null; workflow_id: string | null;
  recent_tasks?: Partial<Record<TaskSelectionKey, string>>;
};
export type LibraryViews = { project_id: string | null; projects: Record<string, ProjectView> };
export const defaultProjectView = (): ProjectView => ({ page: 'home', kind: 'text', module_tab: 'train', data_tab: 'local', task_id: null, workflow_id: null });

export function taskSelectionKey(task: Task): TaskSelectionKey | null {
  if (task.workflow_ref != null || task.immutable_draft || task.kind === 'export' || (task.operation !== 'train' && task.operation !== 'generate')) return null;
  return `${task.kind}:${task.operation}`;
}

export function rememberTaskSelection(view: ProjectView, task: Task | null): ProjectView {
  if (!task) return view;
  const key = taskSelectionKey(task);
  if (!key || view.recent_tasks?.[key] === task.id) return view;
  return { ...view, recent_tasks: { ...view.recent_tasks, [key]: task.id } };
}

/** 每个已挂载工作库独立持有；队列只保存选择编号，不保存任务正文或环境路径。 */
export class ProjectContexts {
  value: LibraryViews = { project_id: null, projects: {} };
  loaded = false;
  private pending = new Map<string, ProjectView>();
  private writing: Promise<void> | null = null;

  constructor(private canWrite: () => boolean) {}

  load(value: LibraryViews) {
    this.value = { project_id: value.project_id || null, projects: value.projects || {} };
    this.loaded = true;
  }

  view(projectId: string): ProjectView { return this.value.projects[projectId] || defaultProjectView(); }

  remember(projectId: string, view: ProjectView): Promise<void> {
    if (!this.loaded || !projectId || !this.canWrite()) return Promise.resolve();
    if (this.value.project_id === projectId && JSON.stringify(this.value.projects[projectId]) === JSON.stringify(view)) return this.pending.size ? this.flush() : this.writing || Promise.resolve();
    this.value = { project_id: projectId, projects: { ...this.value.projects, [projectId]: view } };
    // 同一项目的连续选择只保留最新值；重新排到末尾，最后写入仍是当前项目。
    this.pending.delete(projectId); this.pending.set(projectId, view);
    return this.flush();
  }

  async flush(): Promise<void> {
    while (this.writing || this.pending.size) {
      // 回执与 finally 之间仍可能收到新选择，等待者也必须重新检查队列。
      if (this.writing) { await this.writing; continue; }
      this.writing = (async () => {
        while (this.pending.size) {
          if (!this.canWrite()) throw new Error('工作库正在切换，当前选择尚未保存。');
          const [projectId, view] = this.pending.entries().next().value!;
          await api('PATCH', '/ui-context', { project_id: projectId, context: view });
          if (this.pending.get(projectId) === view) this.pending.delete(projectId);
        }
      })();
      try { await this.writing; }
      finally { this.writing = null; }
    }
  }
}
