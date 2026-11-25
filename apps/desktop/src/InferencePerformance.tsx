import type { Attempt } from './types';
import { activeStates } from './ui';

type Measurement = { label: string; value: string; hint?: string };
function numeric(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : undefined;
}
function duration(ms: number) {
  if (ms < 1 && ms > 0) return '<1 ms';
  if (ms < 1000) return Math.round(ms) + ' ms';
  if (ms < 60000) return (ms / 1000).toFixed(2) + ' 秒';
  const tenths = Math.round(ms / 100);
  return Math.floor(tenths / 600) + ' 分 ' + ((tenths % 600) / 10).toFixed(1) + ' 秒';
}
function interval(from?: string, to?: number) {
  return from && to !== undefined ? numeric(to - Date.parse(from)) : undefined;
}

export function InferencePerformance({ attempt, engineMetric }: { attempt: Attempt; engineMetric?: Record<string, unknown> }) {
  if (attempt.snapshot?.operation !== 'generate') return null;
  const p = attempt.performance || {};
  const kind = attempt.snapshot.kind;
  const active = activeStates.has(attempt.state);
  const end = active ? Date.now() : attempt.completed_at ? Date.parse(attempt.completed_at) : undefined;
  const main: Measurement[] = [], details: Measurement[] = [];
  function addTime(rows: Measurement[], label: string, value: unknown, hint?: string) {
    const ms = numeric(value);
    if (ms !== undefined) rows.push({ label, value: duration(ms), hint });
  }
  function addRate(label: string, count: unknown, elapsed: unknown, unit: string, hint: string) {
    const n = numeric(count), ms = numeric(elapsed);
    if (n && ms) {
      const rate = n * 1000 / ms;
      main.push({ label, value: (rate < 0.1 ? rate.toPrecision(2) : rate.toFixed(2)) + ' ' + unit, hint });
    }
  }
  addTime(main, active ? '已用时间' : '总耗时', p.total_ms ?? interval(attempt.created_at, end), '从提交到结束，包含排队。');
  if (kind === 'text') {
    addTime(main, '首 token 延迟', p.first_token_ms, '从开始执行到首个生成 token 或服务端首个内容片段，包含输入校验和加载。');
    addRate('解码速度', p.decode_tokens, p.decode_ms, 'token/s', '根据执行器实际完成的逐 token 解码次数和解码耗时计算。');
    addRate('预填充速度', p.prefill_tokens, p.prefill_ms, 'token/s', '本次实际预填充的 token 数除以预填充耗时。');
    const input = numeric(p.prompt_tokens ?? attempt.result?.prompt_tokens);
    const output = numeric(p.completion_tokens ?? attempt.result?.completion_tokens);
    if (!p.decode_tokens) addRate('平均输出速度', output, p.render_ms, 'token/s', '生成 token 总数除以执行器运行耗时，包含加载和预填充。');
    if (input !== undefined) details.push({ label: '输入 token', value: String(input) });
    if (output !== undefined) details.push({ label: '生成 token', value: String(output) });
  }
  if (kind === 'image' || kind === 'video') {
    addRate('采样速度', p.sampling_steps, p.sampling_ms, '步/秒', '实际完成的采样步数除以采样耗时。');
    if (p.sampling_steps > 0) {
      details.push({ label: '实际采样步数', value: String(p.sampling_steps) });
      addTime(details, '平均每步采样', p.sampling_ms / p.sampling_steps);
    }
    if (p.output_frames > 0) {
      details.push({ label: '输出帧数', value: p.output_frames + ' 帧' });
      addRate('视频生成速度', p.output_frames, p.render_ms, '帧/秒', '输出帧数除以执行器运行时间，包含视频编码。');
    }
  }
  if (kind === 'audio') {
    const output = numeric(p.audio_seconds), seconds = output ?? numeric(p.input_audio_seconds);
    if (seconds && p.render_ms > 0) {
      main.push({ label: output ? '输出音频时长' : '输入音频时长', value: duration(seconds * 1000) },
        { label: '实时因子 RTF', value: (p.render_ms / (seconds * 1000)).toFixed(3), hint: '执行器运行耗时 ÷ 音频时长。小于 1 表示处理快于实时播放。' });
    }
  }
  addTime(details, '排队', p.queue_ms ?? (attempt.state === 'queued' ? interval(attempt.created_at, end) : undefined));
  addTime(details, '执行耗时', p.run_ms ?? interval(attempt.started_at, end), '从出队到运行结束。');
  addTime(details, '输入与文件校验', p.verify_ms);
  addTime(details, '执行器运行', p.render_ms, '包含执行器内的加载、推理与媒体处理。');
  addTime(details, '权重准备', p.weight_prepare_ms);
  addTime(details, '模型加载', p.model_load_ms);
  addTime(details, '服务启动与模型就绪', p.service_start_ms);
  addTime(details, '提示词预填充', p.prefill_ms);
  addTime(details, '逐 token 解码', p.decode_ms);
  addTime(details, '生成进程耗时', p.model_process_ms, '包含进程内的加载、计算及写出。');
  addTime(details, '条件编码', p.conditioning_ms);
  addTime(details, '去噪采样', p.sampling_ms);
  addTime(details, 'VAE 编码', p.vae_encode_ms);
  addTime(details, 'VAE 解码', p.vae_decode_ms);
  addTime(details, '音轨解码', p.audio_decode_ms);
  addTime(details, '音频会话准备与推理', p.audio_session_ms, '来自 audio.cpp 的离线会话计时，多段合成时累加各段。');
  addTime(details, '媒体输入处理', p.media_input_ms);
  addTime(details, '媒体输出编码', p.media_encode_ms);
  addTime(details, '结果校验与登记', p.collect_ms);
  if (!attempt.performance && engineMetric) {
    const ms = (key: string) => {
      const seconds = numeric(engineMetric[key]);
      return seconds === undefined ? undefined : seconds * 1000;
    };
    addTime(main, '首 token 延迟', ms('first_token_seconds'), '执行器从开始生成到首个 token 的计时。');
    for (const [label, key] of [['引擎生成速度','generation_tps'], ['预填充速度','prompt_tps']]) {
      const rate = numeric(engineMetric[key]);
      if (rate !== undefined && rate > 0) main.push({ label, value: rate.toFixed(2) + ' token/s' });
    }
    addTime(details, '模型加载', ms('model_load_seconds'));
    addTime(details, '生成阶段', ms('generation_wall_seconds') ?? ms('generate_seconds'));
    addTime(details, '执行器运行', ms('worker_wall_seconds') ?? ms('elapsed_seconds'));
    const generated = numeric(engineMetric.generation_tokens);
    if (generated !== undefined && attempt.result?.completion_tokens === undefined)
      details.push({ label: '生成 token', value: String(generated) });
  }
  if (!main.length && !details.length) return null;
  const rows = (items: Measurement[]) => items.map(row =>
    <div key={row.label} title={row.hint}><dt>{row.label}</dt><dd>{row.value}</dd></div>);
  return <section className="inference-performance" aria-label="推理性能">
    <h4>推理性能</h4>
    {!!main.length && <dl className="performance-highlights">{rows(main)}</dl>}
    {!!details.length && <details><summary>查看计时明细</summary>
      {p.render_ms !== undefined && <p className="muted">执行器运行时间包含模型加载、推理和媒体处理，各子阶段已计入总耗时。</p>}
      <dl className="facts">{rows(details)}</dl></details>}
    {!attempt.performance && !engineMetric && !active && <small className="muted">此历史记录仅显示当时保存的数据。</small>}
  </section>;
}
