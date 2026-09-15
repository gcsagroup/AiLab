import React from 'react';
import trainingContracts from './fixtures/training-contracts.json';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Workbench, { defaultTrainingRuntime, RunResult } from '../../apps/desktop/src/Workbench';
import { Checkpoints } from '../../apps/desktop/src/Checkpoints';
import type { Attempt, Task } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const checkpoint = { id: 'checkpoint-a', source_attempt_id: 'attempt-a', step: 3, total_steps: 12, manifest_digest: 'a'.repeat(64), status: 'verified' };
let current: Attempt;
let calls: { path: string; method: string; body: unknown; key?: string }[];
const task: Task = { id: 'restore-task', project_id: 'project-a', kind: 'text', operation: 'train', name: '从第 3 步恢复', draft_revision: 1, draft: { kind: 'text', operation: 'train', model_id: 'model-a', dataset_id: 'dataset-a', checkpoint_id: checkpoint.id, runtime: { ...defaultTrainingRuntime, steps: 12 }, input: { prompt: '' } } };
beforeEach(() => {
  calls = [];
  current = { id: 'attempt-a', task_id: 'original-task', project_id: 'project-a', state: 'running', state_version: 2, snapshot: { operation: 'train' }, allowed_actions: ['pause', 'cancel'], last_event_sequence: 0 };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const method = init.method || 'GET'; const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, method, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    let result: unknown = current;
    if (path === '/training-contracts') result = trainingContracts;
    if (path.startsWith('/execution-targets?')) result = { items: [] };
    if (path.includes('/events?')) result = { items: [] };
    if (path.startsWith('/checkpoints?')) result = { items: current.checkpoint_id || current.state === 'cancelled' ? [checkpoint] : [] };
    if (path.endsWith('/pause')) { current = { ...current, state: 'pausing', state_version: 3, allowed_actions: ['cancel'] }; result = current; }
    if (path.endsWith('/resume')) { current = { ...current, state: 'resuming', state_version: 5, allowed_actions: ['cancel'] }; result = current; }
    if (path.endsWith('/restore-task')) result = task;
    if (path.endsWith('/preflight')) result = { preflight_id: 'check-restore', can_submit: true, blocking: [], warnings: [] };
    return { ok: true, json: async () => result };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('训练安全检查点与恢复', () => {
  it('只有执行器确认已暂停后才显示继续；继续仍等待执行器确认', async () => {
    render(<RunResult initial={current} onChanged={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: '保存检查点并暂停' }));
    await screen.findByText('正在暂停');
    expect(screen.queryByRole('button', { name: '继续训练' })).toBeNull();
    expect(calls.find(call => call.path.endsWith('/pause'))?.body).toEqual({ expected_state_version: 2 });
    current = { ...current, state: 'paused', state_version: 4, checkpoint_id: checkpoint.id, allowed_actions: ['resume', 'cancel'] };
    fireEvent.click(await screen.findByRole('button', { name: '继续训练' }));
    await screen.findByText('正在继续');
    expect(calls.find(call => call.path.endsWith('/resume'))?.body).toEqual({ expected_state_version: 4 });
    expect(screen.queryByRole('button', { name: '从第 3 步创建恢复任务' })).toBeNull();
  });
  it('原运行退出后才创建新恢复草稿，响应丢失重试保留同一个命令编号', async () => {
    current = { ...current, state: 'cancelled', state_version: 6, allowed_actions: [] };
    const real = vi.mocked(fetch).getMockImplementation()!; let lost = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await real(input, init); if (String(input).endsWith('/restore-task') && !lost) { lost = true; throw new Error('恢复草稿响应丢失'); } return result; });
    const restored = vi.fn(); render(<Checkpoints attempt={current} onRestoreTask={restored} />);
    const button = await screen.findByRole('button', { name: '从第 3 步创建恢复任务' });
    expect(calls.some(call => call.method === 'POST')).toBe(false);
    fireEvent.click(button); await screen.findByText('恢复草稿响应丢失');
    fireEvent.click(button); await waitFor(() => expect(restored).toHaveBeenCalledWith(task));
    const posts = calls.filter(call => call.method === 'POST');
    expect(posts).toHaveLength(2); expect(posts[0].key).toBe(posts[1].key);
    expect(posts.every(call => call.path === '/checkpoints/checkpoint-a/restore-task')).toBe(true);
  });
  it('恢复草稿锁定原模型、数据和参数，需要新的检查，不会自动运行', async () => {
    render(<Workbench task={task} models={[{ id: 'model-a', name: '原基座', format: 'safetensors' }]} datasets={[{ id: 'dataset-a', name: '原数据' }]} devices={[]} onBack={() => {}} registerLeave={() => {}} onTaskChanged={() => {}} onImport={() => {}} onUpdated={() => {}} />);
    expect((screen.getByLabelText('选择基座模型') as HTMLSelectElement).closest('fieldset')?.disabled).toBe(true);
    expect(screen.queryByRole('button', { name: '开始训练' })).toBeNull();
    await waitFor(() => expect((screen.getByRole('button', { name: '检查配置' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '检查配置' }));
    await screen.findByRole('button', { name: '开始训练' });
    expect(calls.filter(call => call.method === 'POST').map(call => call.path)).toEqual(['/tasks/restore-task/preflight']);
  });
});
