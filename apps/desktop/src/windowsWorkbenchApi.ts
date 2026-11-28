import { preferredTextGpu } from './types';
import { previewApi } from './previewApi';
import type { Attempt, Task } from './types';

declare global {
  interface Window {
    ailabHF?: { filePath?: (file:File)=>string; runtime?: (action: RuntimeAction, component?: string) => Promise<RuntimeStatus>; request: (action: string, payload: unknown) => Promise<{ok: true; data: unknown} | {ok: false; error: {code: string; message: string}}> };
  }
}
export type RuntimeAction = 'status' | 'prepare' | 'cancel' | 'choose-directory' | 'reset-directory';
export type RuntimeStatus = {
  root: string; selected: boolean; nextRoot: string; directoryWarning?: string;
  busy: boolean; id?: string; component?: string; phase?: string; error?: string; received?: number; total?: number;
  files?: { component: string; name: string; status: string; received: number; total: number }[];
  components: { id: string; label: string; installed: boolean; detail: string }[];
};
async function native<T>(method: string, path: string, body?: unknown, idempotencyKey?: string, task?: Partial<Task>): Promise<T> {
  const response=await window.ailabHF!.request('workbench',{method,path,body,idempotencyKey,task});
  if (!response.ok) throw {error:response.error};
  const reply=response.data as {handled:boolean;data:T};
  if(!reply.handled)throw Error('本机执行服务未响应。');
  return reply.data;
}
function windowsTask(task:Task) {
  const r=task.draft.runtime;
  if(task.operation==='generate' && !task.draft.execution_target_id && (r.engine==='mlx'||r.device_id==='apple-gpu'||r.engine==='kokoro'||r.engine==='diffusers')){
    r.engine='ailab-gguf';
    if (!r.device_id || r.device_id==='apple-gpu') r.device_id='cpu';
    if(task.kind==='image')Object.assign(r,{size:r.size??512,steps:r.steps??20,cfg:r.cfg??7.5});
    if(task.kind==='video')Object.assign(r,{steps:r.steps??25,frames:r.frames??14,fps:r.fps??7});
    if(task.kind==='audio')Object.assign(r,{voice:r.voice??'zf_xiaobei',speed:r.speed??1,sample_rate:24000});
  }
  return task;
}
export async function windowsWorkbenchApi<T>(method:string,path:string,body?:unknown,idempotencyKey?:string):Promise<T>{
  if(!window.ailabHF)return previewApi<T>(method,path,body);
  const route=path.split('?')[0];
  if (method === 'DELETE' && /^\/tasks\/task-[\w-]+$/.test(route)) {
    const project = new URL(path, 'https://preview.invalid').searchParams.get('project_id');
    if (!project) throw Error('请选择当前项目。');
    await native('DELETE', route + '/record?project_id=' + encodeURIComponent(project));
    if (route.startsWith('/tasks/task-wf-')) {
      const key = 'ailab-hidden-workflow-tasks:' + project;
      const hidden: string[] = JSON.parse(localStorage.getItem(key) || '[]');
      localStorage.setItem(key, JSON.stringify([...new Set([...hidden, route.split('/')[2]])]));
      return {deleted:true} as T;
    }
    return previewApi<T>(method,path,body);
  }
  if (route.startsWith('/workflow-runs') || route.startsWith('/tasks/task-wf-'))
    return native<T>(method,path,body,idempotencyKey);
  if(method==='POST'&&route==='/tasks'){
    let task=windowsTask(await previewApi<Task>(method,path,body));
    if(task.operation==='generate'&&['text','image','video'].includes(task.kind)){
      const inventory=await native<{items:{id:string;free_bytes:number;cuda_engines?:string[]}[]}>('GET','/devices').catch(()=>({items:[]}));
      const minFreeGiB = task.kind === 'video' ? 3 : 2;
      const gpu = task.kind==='text' ? preferredTextGpu(inventory.items) :
        inventory.items.find(d => /^(?:Vulkan|CUDA)\d+$/.test(d.id) && d.free_bytes >= minFreeGiB * 1024**3);
      if(gpu)task=await previewApi<Task>('PATCH','/tasks/'+task.id+'/draft',{expected_revision:task.draft_revision,draft:{...task.draft,runtime:{...task.draft.runtime,device_id:gpu.id}}});
    }
    return task as T;
  }
  const action=/^\/tasks\/(task-[\w-]+)\/(preflight|attempts)$/.exec(route);
  if(action){
    const task=windowsTask(await previewApi<Task>('GET','/tasks/'+action[1]));
    const snapshot={id:task.id,project_id:task.project_id,kind:task.kind,operation:task.operation,draft_revision:task.draft_revision,draft:task.draft};
    return native<T>(method,path,body,idempotencyKey,snapshot);
  }
  if(method==='GET' && (/^\/tasks\/task-[\w-]+$/.test(route)||route==='/tasks')){
    const reply=await previewApi<Task|{items:Task[]}>(method,path,body);
    const filter='items' in reply?path.split('?')[1]||'':'task_id='+encodeURIComponent(reply.id);
    const {items}=await native<{items:Attempt[]}>('GET','/attempts?'+filter);
    const attach=(task:Task)=>{windowsTask(task);task.attempts=items.filter(a=>a.task_id===task.id);task.latest_attempt=task.attempts[0];return task;};
    if('items' in reply) {
      const workflowTasks = await native<{items:Task[]}>('GET', '/workflow-tasks?' + filter);
      const project = new URL(path, 'https://preview.invalid').searchParams.get('project_id');
      const hidden: string[] = project ? JSON.parse(localStorage.getItem('ailab-hidden-workflow-tasks:' + project) || '[]') : [];
      reply.items = [...reply.items, ...workflowTasks.items.filter(task => !hidden.includes(task.id))].map(attach).sort((a,b) => (b.created_at || '').localeCompare(a.created_at || ''));
    } else attach(reply);
    return reply as T;
  }
  if(/^\/(?:models|model-catalog|model-downloads|capabilities|devices|environment|attempts|materials|artifacts|works)(?:[/?]|$)/.test(route))return native<T>(method,path,body,idempotencyKey);
  return previewApi<T>(method,path,body);
}
