import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SourceChecks from '../../apps/desktop/src/SourceChecks';
import { CapabilityDialog, CapabilityReviews } from '../../apps/desktop/src/CapabilityComparison';
import type { EvaluationReport } from '../../apps/desktop/src/Evaluation';
import type { Model } from '../../apps/desktop/src/types';

vi.mock('@tauri-apps/api/core', () => ({ isTauri: () => false, invoke: vi.fn() }));
const models = [{ id: 'base', name: '原模型', modality: 'text', format: 'safetensors', model_config: { model_type: 'qwen2', hidden_size: 896, num_hidden_layers: 24 } }, { id: 'student', name: '蒸馏模型', modality: 'text', format: 'safetensors', model_config: { model_type: 'qwen2', hidden_size: 896, num_hidden_layers: 24 } }] as Model[];
const saved = { id: 'source-1', name: '原模型 · 来源核验', created_at: '2026-10-20T00:00:00Z', source_report_sha256: 'raw-sha', result: { tool: 'Heretic', tool_version: '2.0.0.dev0', scope: '只作来源核验', files_match: false, library_manifest_matches: true, environment_ready: true, report_integrity: 'not_provided', source: { commit: 'abc' }, files: [{ path: 'model.safetensors', expected: 'a', actual: 'b', status: 'mismatch' }], environment: [{ package: 'torch', reported: '2.8', current: null, status: 'unavailable' }], findings: [{ code: 'FILES_DIFFER', message: '模型文件存在差异' }], uncovered_weights: [] } };
let calls: { path: string; body: Record<string, unknown>; key?: string }[];
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.open = true; } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.open = false; } });
  calls = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string, init: RequestInit) => {
    const path = String(input).replace('/api/v1', ''); const body = init.body ? JSON.parse(String(init.body)) : {};
    calls.push({ path, body, key: (init.headers as Record<string, string>)['Idempotency-Key'] });
    const response = path.startsWith('/source-checks?') ? { items: [] } : path === '/source-checks' ? saved : path.endsWith('/reviews') ? { revision: 1, items: [{ ...body, id: 'review-1', revision: 1 }] } : { id: 'task-1', draft: { evaluation_kind: 'capability_comparison' } };
    return { ok: true, json: async () => response };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('真实来源核验与普通能力对照入口', () => {
  it('显式选择模型及来源报告后核验，显示差异并导出已保存记录', async () => {
    const onExport = vi.fn(); render(<SourceChecks projectId="project" models={models} onExport={onExport} />);
    await screen.findByText('尚无来源核验记录');
    await waitFor(() => expect(screen.getByRole('button', { name: '新建来源核验' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: '新建来源核验' }));
    expect(screen.getByRole('button', { name: '核验并保存结果' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('外部来源 JSON'), { target: { value: '/source/reproduce.json' } });
    fireEvent.click(screen.getByRole('button', { name: '核验并保存结果' }));
    await screen.findByText('模型文件存在差异');
    expect(screen.getByText('不一致')).toBeInTheDocument(); expect(screen.getByText('当前未探测到')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '导出核验报告' }));
    expect(onExport).toHaveBeenCalledWith({ type: 'source-check', id: 'source-1', name: saved.name });
    expect(calls.find(call => call.path === '/source-checks')?.body).toEqual({ project_id: 'project', model_id: 'base', report_path: '/source/reproduce.json' });
  });

  it('不允许同模型对照，冻结后才创建任务，不自动执行', async () => {
    const created = vi.fn(); render(<CapabilityDialog projectId="project" models={models} onClose={() => {}} onCreated={created} />);
    fireEvent.change(screen.getByLabelText('候选模型'), { target: { value: 'base' } });
    expect(screen.getByRole('button', { name: '冻结题集并创建对照' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('候选模型'), { target: { value: 'student' } });
    fireEvent.click(screen.getByRole('button', { name: '冻结题集并创建对照' }));
    await waitFor(() => expect(created).toHaveBeenCalledOnce());
    expect(calls).toHaveLength(1); expect(calls[0].path).toBe('/evaluations/capability');
    expect(calls[0].body).toEqual({ project_id: 'project', model_id: 'base', candidate_model_id: 'student' });
  });

  it('复核保留实际输出，理由必填且请求绑定记录版本', async () => {
    const onSaved = vi.fn(); const report = { samples: [{ id: 'normal-email', prompt: '写邮件', baseline: { output: '你好' }, candidate: { output: '您好，同事。' } }] } as unknown as EvaluationReport;
    render(<CapabilityReviews attemptId="attempt-1" report={report} reviews={{ revision: 0, items: [] }} onSaved={onSaved} />);
    expect(screen.getByText('您好，同事。')).toBeInTheDocument(); expect(screen.getByRole('button', { name: '保存人工复核' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('人工结论'), { target: { value: 'normal' } });
    fireEvent.change(screen.getByLabelText('复核理由'), { target: { value: '确实提供了邮件开头。' } });
    fireEvent.click(screen.getByRole('button', { name: '保存人工复核' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(calls[0].body).toEqual({ expected_revision: 0, sample_id: 'normal-email', variant: 'candidate', verdict: 'normal', note: '确实提供了邮件开头。' });
    expect(screen.getByText('您好，同事。')).toBeInTheDocument();
  });

  it('创建结果丢失时重试沿用幂等键', async () => {
    const normal = vi.mocked(fetch).getMockImplementation()!; let dropped = false;
    vi.mocked(fetch).mockImplementation(async (input, init) => { const result = await normal(input, init); if (!dropped) { dropped = true; throw new Error('结果待确认'); } return result; });
    const created = vi.fn(); render(<CapabilityDialog projectId="project" models={models} onClose={() => {}} onCreated={created} />);
    fireEvent.click(screen.getByRole('button', { name: '冻结题集并创建对照' })); await screen.findByText('结果待确认');
    fireEvent.click(screen.getByRole('button', { name: '冻结题集并创建对照' })); await waitFor(() => expect(created).toHaveBeenCalledOnce());
    expect(calls[1].key).toBe(calls[0].key);
  });
  it('离开对照创建界面后，不应用迟到成功响应', async () => {
    let finish!: (value: unknown) => void;
    vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve as typeof finish; }));
    const created = vi.fn(); const view = render(<CapabilityDialog projectId="project" models={models} onClose={() => {}} onCreated={created} />);
    fireEvent.click(screen.getByRole('button', { name: '冻结题集并创建对照' }));
    view.unmount();
    await act(async () => { finish({ ok: true, json: async () => ({ id: 'late-task' }) }); });
    expect(created).not.toHaveBeenCalled();
  });

});
