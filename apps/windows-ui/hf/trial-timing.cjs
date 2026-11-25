'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { performance } = require('node:perf_hooks');

// The CLI recipes and native workers use the same subprocess entry point.
// Measure only the command being run. Accumulate repeated synthesis segments and conversions.
function timedMediaInvoke(invoke, bins, event) {
  const totals = {};
  function add(key, ms) {
    totals[key] = (totals[key] || 0) + ms;
    event('timing', { [key]: totals[key] });
  }
  return async (exe, args, options = {}) => {
    const ffmpeg = exe === bins.ffmpeg;
    const videoOutput = ffmpeg && /\.mp4$/i.test(args.at(-1));
    const mode = args.indexOf('-M');
    const preparesWeights = (mode >= 0 && args[mode + 1] === 'convert') ||
      /^(prepare-|compact-)/.test(options.input?.action || '') || path.basename(exe) === 'audiocpp_gguf.exe';
    let key = preparesWeights ? 'weight_prepare_ms' : 'model_process_ms';
    if (ffmpeg) key = videoOutput || /speech\.wav$/i.test(args.at(-1)) ? 'media_encode_ms' : 'media_input_ms';
    let frames;
    if (path.basename(exe) === 'audiocpp_cli.exe') {
      args = [...args, '--metrics'];
      const onLine = options.onLine;
      options = { ...options, onLine(line) {
        onLine?.(line);
        const match = /^metrics\.wall_ms=(\d+(?:\.\d+)?(?:e[+-]?\d+)?)$/i.exec(line);
        if (match) add('audio_session_ms', Number(match[1]));
      } };
    }
    if (path.basename(exe) === 'sd-cli.exe' && key === 'model_process_ms') {
      const stages = { get_learned_condition: 'conditioning_ms', sampling: 'sampling_ms',
        encode_first_stage: 'vae_encode_ms', decode_first_stage: 'vae_decode_ms' };
      options = { ...options, onLog(line) {
        const match = /^\[I\]\s+(get_learned_condition|sampling|encode_first_stage|decode_first_stage) completed, taking (\d+(?:\.\d+)?)\s*(ms|s)(?:\s+---\s+[\w.-]+:\d+)?\s*$/.exec(line.replace(/\x1b\[[\d;]*m/g, ''));
        if (match) add(stages[match[1]], Number(match[2]) * (match[3] === 's' ? 1000 : 1));
      } };
    }
    if (videoOutput) {
      args = ['-nostats','-progress','pipe:1', ...args];
      const onLine = options.onLine;
      options = { ...options, onLine(line) {
        onLine?.(line);
        const count = /^frame=(\d+)$/.exec(line);
        if (count) frames = Number(count[1]);
      } };
    }
    const start = performance.now();
    try {
      const result = await invoke(exe, args, options);
      if (videoOutput && frames > 0) event('timing', { output_frames: frames });
      return result;
    } finally {
      add(key, performance.now() - start);
    }
  };
}

// Skip ancillary chunks without reading the samples into memory.
async function waveSeconds(file) {
  if (!file) return;
  const handle = await fs.open(file, 'r');
  try {
    const size = (await handle.stat()).size;
    const buffer = Buffer.alloc(16);
    if ((await handle.read(buffer, 0, 12, 0)).bytesRead !== 12 ||
        buffer.toString('ascii',0,4) !== 'RIFF' || buffer.toString('ascii',8,12) !== 'WAVE') return;
    let rate, bytes = 0;
    for (let pos = 12; pos + 8 <= size;) {
      if ((await handle.read(buffer, 0, 8, pos)).bytesRead !== 8) return;
      const tag = buffer.toString('ascii',0,4), length = buffer.readUInt32LE(4);
      pos += 8;
      if (pos + length > size) return;
      if (tag === 'fmt ' && length >= 16) {
        if ((await handle.read(buffer, 0, 16, pos)).bytesRead !== 16) return;
        if (![1,3,65534].includes(buffer.readUInt16LE(0))) return;
        rate = buffer.readUInt32LE(8);
      }
      if (tag === 'data') bytes += length;
      pos += length + length % 2;
    }
    if (bytes > 0 && rate > 0) return bytes / rate;
  } finally { await handle.close(); }
}
module.exports = { timedMediaInvoke, waveSeconds };
