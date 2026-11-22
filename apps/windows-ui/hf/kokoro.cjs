'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');

// Keep an entire short utterance in the same Kokoro request. Longer passages
// split at the last punctuation in the budget, retaining it for the phonemizer.
function splitText(text, limit = 48) {
  const chars = Array.from(text.trim());
  const chunks = [];
  for (let start = 0; start < chars.length; ) {
    let end = Math.min(chars.length, start + limit);
    if (end < chars.length) {
      for (let i = end - 1; i > start; --i) {
        if (/[，。！？；、,.!?;\n]/u.test(chars[i])) {
          end = i + 1;
          break;
        }
      }
    }
    const chunk = chars.slice(start, end).join('').trim();
    if (chunk) chunks.push(chunk);
    start = end;
  }
  return chunks;
}

function pcmData(file) {
  if (file.toString('ascii', 0, 4) !== 'RIFF' || file.toString('ascii', 8, 12) !== 'WAVE')
    throw Error('音频执行器未生成 WAV。');
  let pcm, format;
  for (let offset = 12; offset + 8 <= file.length; ) {
    const tag = file.toString('ascii', offset, offset + 4),
      size = file.readUInt32LE(offset + 4),
      data = offset + 8;
    if (data + size > file.length) throw Error('音频分段不完整。');
    if (tag === 'fmt ' && size >= 16)
      format = [
        file.readUInt16LE(data),
        file.readUInt16LE(data + 2),
        file.readUInt32LE(data + 4),
        file.readUInt16LE(data + 14),
      ];
    if (tag === 'data') pcm = file.subarray(data, data + size);
    offset = data + size + (size % 2);
  }
  if (!pcm?.length || pcm.length % 2 || format?.join(',') !== '1,1,24000,16')
    throw Error('音频分段需要 24 kHz 单声道 PCM16。');
  return pcm;
}

async function synthesize(exe, invoke, model, text, r, out, signal, event) {
  const segments = splitText(text);
  const pcm = [];
  for (const [index, part] of segments.entries()) {
    const filename = 'speech-' + index + '.wav',
      file = path.join(out, filename);
    const args = [
      '--task',
      'tts',
      '--family',
      'kokoro_tts',
      '--model',
      model,
      '--backend',
      'cpu',
      '--threads',
      '4',
      '--voice-id',
      r.voice,
      '--language',
      'zh',
      '--seed',
      String((r.seed + index) >>> 0),
      '--request-option',
      'speed=' + r.speed,
      '--text',
      part,
      '--out',
      filename,
    ];
    try {
      await invoke(exe, args, { cwd: out, signal });
      pcm.push(pcmData(await fs.readFile(file)));
      event('step', { completed: index + 1, total: segments.length });
    } finally {
      await fs.rm(file, { force: true });
    }
  }
  signal?.throwIfAborted();
  const data = Buffer.concat(pcm),
    header = Buffer.alloc(44);
  header.write('RIFF');
  header.writeUInt32LE(data.length + 36, 4);
  header.write('WAVEfmt ', 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(24000, 24);
  header.writeUInt32LE(48000, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write('data', 36);
  header.writeUInt32LE(data.length, 40);
  await fs.writeFile(path.join(out, 'speech.wav'), Buffer.concat([header, data]));
  return {
    name: 'speech.wav',
    media_type: 'audio/wav',
    sample_rate: 24000,
    channels: 1,
    duration_seconds: data.length / 48000,
  };
}
module.exports = { splitText, pcmData, synthesize };
