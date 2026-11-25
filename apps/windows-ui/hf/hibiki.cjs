'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');

// Mimi uses 80 ms frames of mono PCM16. Keep a short lookahead in the server
// and feed silence after EOF so delayed speech at the end can be decoded.
const rate = 24000;
const frameBytes = rate * 2 * 80 / 1000;
function wave(pcm) {
  const h = Buffer.alloc(44);
  h.write('RIFF'); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVEfmt ', 8);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28);
  h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36);
  h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

async function translate({address, key, signal}, file, out) {
  const size = (await fs.stat(file)).size;
  const wanted = (Math.ceil(size / frameBytes) + 50) * frameBytes;
  if (!size || size % 2 || wanted + 44 > 64 * 1024 ** 2) throw Error('翻译音频为空或超出 WAV 预览大小。');
  const input = await fs.readFile(file, {signal});
  signal.throwIfAborted();
  const url = new URL('/v1/realtime', address);
  url.protocol = 'ws:';
  const socket = new WebSocket(url, {headers:{Authorization:'Bearer ' + key}});
  const chunks = [];
  let sent = 0, received = 0, cancelling = false, transcript = '';
  function feed() {
    const end = Math.min(wanted + 16 * frameBytes, received + 32 * frameBytes);
    while (sent < end) {
      const chunk = Buffer.alloc(Math.min(8 * frameBytes, end - sent));
      if (sent < input.length) input.copy(chunk, 0, sent, sent + chunk.length);
      socket.send(JSON.stringify({type:'input_audio_buffer.append',audio:chunk.toString('base64')}));
      sent += chunk.length;
    }
  }
  let timer, abort;
  try {
    await new Promise((resolve, reject) => {
      const refresh = () => {
        clearTimeout(timer);
        timer = setTimeout(() => reject(Error('实时翻译接口长时间没有返回音频。')), 120000);
      };
      abort = () => reject(signal.reason);
      signal.addEventListener('abort', abort, {once:true});
      refresh();
      socket.onerror = () => reject(Error('无法连接本机实时翻译服务。'));
      socket.onclose = () => reject(Error('实时翻译服务提前关闭。'));
      socket.onmessage = ({data}) => {
        try {
          const e = JSON.parse(data);
          if (e.type === 'error') throw Error(e.error?.message || '实时翻译失败。');
          if (e.type === 'session.created') {
            const audio = e.session?.audio;
            if (audio?.input?.format?.rate !== rate || audio?.output?.format?.rate !== rate)
              throw Error('Hibiki 的输入和输出必须为 24 kHz PCM。');
            feed();
          } else if (e.type === 'response.output_text.delta' && typeof e.delta === 'string') {
            transcript += e.delta;
          } else if (e.type === 'response.output_audio.delta' && !cancelling) {
            const bytes = Buffer.from(e.delta, 'base64');
            if (!bytes.length || bytes.length % 2) throw Error('翻译服务返回了无效的 PCM。');
            const keep = bytes.subarray(0, wanted - received);
            chunks.push(keep);
            received += keep.length;
            refresh();
            if (received === wanted) {
              cancelling = true;
              socket.send(JSON.stringify({type:'response.cancel'}));
            } else feed();
          } else if (e.type === 'response.done') {
            if (!cancelling) throw Error('实时翻译提前结束。');
            resolve();
          }
        } catch (err) { reject(err); }
      };
    });
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
    socket.close();
  }
  await fs.writeFile(path.join(out,'speech.wav'), wave(Buffer.concat(chunks)), {signal});
  return {name:'speech.wav',media_type:'audio/wav',text:transcript.trim()};
}
module.exports = {translate};
