import React from 'react';
import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { InferencePerformance } from '../../apps/desktop/src/InferencePerformance';
import type { Attempt } from '../../apps/desktop/src/types';

afterEach(cleanup);
function show(kind: string, props: Partial<Attempt>) {
  render(<InferencePerformance attempt={{ id:'a', task_id:'t', project_id:'p', state:'succeeded',
    state_version:2, snapshot:{operation:'generate',kind}, ...props }} />);
}
it('uses measured decode and prefill intervals and preserves the stop-token count separately', () => {
  show('text', {performance:{total_ms:6500, first_token_ms:1000, completion_tokens:5, decode_tokens:4, decode_ms:2000,
    prompt_tokens:16, prefill_tokens:8, prefill_ms:100}});
  for (const value of ['6.50 秒','1.00 秒','2.00 token/s','80.00 token/s','5','16']) expect(screen.getByText(value)).toBeTruthy();
});
it('uses encoded frames and render time for video throughput', () => {
  show('video', { performance:{sampling_ms:500, sampling_steps:2, output_frames:14, render_ms:7000, total_ms:10000} });
  expect(screen.getByText('2.00 帧/秒')).toBeTruthy();
  expect(screen.getByText('4.00 步/秒')).toBeTruthy();
  expect(screen.queryByText('解码速度')).toBeNull();
});
it('reports RTF using the duration of the actual WAV', () => {
  show('audio', {performance:{audio_seconds:2,render_ms:500, total_ms:1000}});
  expect(screen.getByText('0.250')).toBeTruthy();
});
it('reads historical timestamps without inventing stage durations or token throughput', () => {
  show('text', {created_at:'2026-01-01T00:00:00Z',completed_at:'2026-01-01T00:00:04Z',result:{completion_tokens:18}});
  expect(screen.getByText('4.00 秒')).toBeTruthy();
  expect(screen.queryByText('解码速度')).toBeNull();
  expect(screen.queryByText('提示词预填充')).toBeNull();
});
