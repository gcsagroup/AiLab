export type Asset = { path: string; name: string; format: string; architecture?: string; size_gb?: number };
export type Runtime = { id: string; name: string; description: string; supported: boolean; reason: string; state: string; installed?: { path: string; version: string; accelerator: string; resolved: string } };
export type Status = { environment_dir?: string; default_environment_dir?: string; hardware: { os: string; arch: string; memory_gb: number; device: string; hostname?: string; os_release?: string; os_version?: string; cpu_name?: string; cpu_physical_cores?: number; cpu_logical_cores?: number; python_version?: string; memory_available_gb?: number; disk_total_gb?: number; disk_free_gb?: number; gpus: { name: string; memory_gb: number; driver_version?: string }[] }; runtimes: Runtime[]; paths: { models: string; datasets: string } };
export type Assets = { models: Asset[]; datasets: Asset[]; models_error?: string; datasets_error?: string };
export type Result = { text?: string; file?: string; model_dir?: string; kind?: string; engine?: string; finish_reason?: string; metrics?: Record<string, number>; train_samples?: number; validation_samples?: number; [key: string]: unknown };
export type Job = { id: string; kind: string; runtime: string; state: string; created_at: number; output_dir: string; queue_position?: number; holds_slot?: boolean; model_state?: string; result: Result | null; error: string | null; config: Record<string, unknown> };
export type Event = { seq: number; type: string; channel?: 'reasoning' | 'final'; text?: string; step?: number; total?: number; loss?: number; eval_loss?: number; learning_rate?: number; epoch?: number };
export type Message = { role: 'system' | 'user' | 'assistant'; content: string; reasoning?: string | null; image?: string | null };
export type Conversation = { id: string; title: string; model: string; engine: 'llama' | 'vllm'; messages: Message[] };
export const terminal = (job: Job) => ['succeeded', 'failed', 'cancelled', 'interrupted'].includes(job.state);
export const stateLabel: Record<string, string> = { queued: '排队中', paused: '已暂停', pausing: '正在暂停', resuming: '正在恢复', running: '运行中', cancelling: '正在停止', succeeded: '已完成', failed: '失败', cancelled: '已取消', interrupted: '执行中断' };

export type Material = { id: string; name: string; kind: 'image' | 'video'; source: 'imported' | 'generated'; mime: string; size: number; created_at: number; parameters: Record<string, unknown>; job_id?: string };

export type LlmStatus = { phase: string; model: string; engine: string; pid?: number | null; idle_timeout_seconds: number; expires_at: number | null };
