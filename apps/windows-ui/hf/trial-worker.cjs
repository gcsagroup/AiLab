'use strict';
const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const { spawn } = require('node:child_process');
const { materialPrompt } = require('./gguf-bundle.cjs');
const { synthesize } = require('./kokoro.cjs');
const { StringDecoder } = require('node:string_decoder');
const { createInterface } = require('node:readline');
const root = path.resolve(__dirname, '../runtime');
const bins = {
  text: path.join(root, 'text', 'ailab-gguf.exe'),
  image: path.join(root, 'diffusion', 'ailab-image.exe'),
  video: path.join(root, 'diffusion', 'ailab-image.exe'),
  audio: path.join(root, 'audio', 'audiocpp_cli.exe'),
  ffmpeg: path.join(root, 'diffusion', 'ffmpeg.exe'),
};
function environment() {
  const env = {};
  for (const k of [
    'SystemRoot',
    'WINDIR',
    'TEMP',
    'TMP',
    'LOCALAPPDATA',
    'USERPROFILE',
    'ProgramData',
    'SystemDrive',
  ])
    if (process.env[k]) env[k] = process.env[k];
  env.PATH = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32');
  // On hybrid Windows laptops an obsolete second ICD can hang enumeration. Use
  // the active NVIDIA ICD when present, otherwise let the Vulkan loader probe.
  try {
    const store = path.join(env.SystemRoot, 'System32', 'DriverStore', 'FileRepository');
    const drivers = fs
      .readdirSync(store)
      .filter((n) => /^nv.*\.inf_amd64_/i.test(n))
      .map((n) => path.join(store, n, 'nv-vk64.json'))
      .filter((f) => fs.existsSync(f));
    if (drivers.length)
      env.VK_DRIVER_FILES = drivers.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  } catch {}
  return env;
}
function invoke(exe, args, { cwd = path.dirname(exe), input, signal, onLine = () => {}, timeout = 0 } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(Error('运行已停止。'));
      return;
    }
    const child = spawn(exe, args, {
      cwd,
      env: environment(),
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let tail = '',
      fatal = null;
    const kill = () => child.kill();
    const timer = timeout
      ? setTimeout(() => {
          fatal = Error('执行器响应超时。');
          kill();
        }, timeout)
      : null;
    signal?.addEventListener('abort', kill, { once: true });
    const lineReader = createInterface({ input: child.stdout, crlfDelay: Infinity });
    lineReader.on('line', (line) => {
      tail = (tail + '\n' + line).slice(-5000);
      try {
        onLine(line);
      } catch (e) {
        fatal = e;
        kill();
      }
    });
    child.stderr.on('data', (data) => {
      tail = (tail + data.toString()).slice(-5000);
    });
    child.on('error', (e) => {
      fatal = e;
    });
    child.stdin.on('error', () => {});
    child.stdin.end(input === undefined ? '' : JSON.stringify(input) + '\n');
    child.on('close', (code) => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', kill);
      if (signal?.aborted) return reject(Error('运行已停止。'));
      if (fatal || code !== 0)
        return reject(fatal || Error(tail.trim().slice(-1800) || '本机执行器未能启动：' + code));
      resolve();
    });
  });
}
async function textWorker(input, signal, event = () => {}) {
  await invoke(bins.text, [], {
    input,
    signal,
    timeout: input.action === 'devices' ? 120000 : input.action === 'inspect' ? 90000 : 0,
    onLine(line) {
      const e = JSON.parse(line);
      if (e.type === 'error') throw Error(e.message);
      event(e);
    },
  });
}
let inventoryPromise;
function devices(refresh = false) {
  if (refresh) inventoryPromise = null;
  if (!inventoryPromise)
    inventoryPromise = (async () => {
      let items = [];
      try {
        await textWorker({ action: 'devices' }, undefined, (e) => {
          items = e.items;
        });
      } catch {
        await textWorker({ action: 'devices', cpu_only: true }, undefined, (e) => {
          items = e.items;
        });
      }
      return items.map((d) => ({
        ...d,
        name: d.name.trim() + ' · ' + d.backend,
        status: 'ready',
        engine: 'AiLab GGUF',
      }));
    })().catch((e) => {
      inventoryPromise = null;
      throw e;
    });
  return inventoryPromise;
}
function limits(n, min, max, integer = false) {
  return Number.isFinite(n) && (!integer || Number.isInteger(n)) && n >= min && n <= max;
}
function parameters(draft, info) {
  const r = { ...draft.runtime };
  if (draft.execution_target_id || draft.adapter_id || draft.checkpoint_id)
    throw Error('本次 GGUF 试用需要本机基座模型。');
  if (!limits(r.seed, 0, 4294967295, true)) throw Error('随机种子超出范围。');
  if (draft.kind === 'text') {
    Object.assign(r, {
      context_limit: r.context_limit ?? 4096,
      prefill_step_size: r.prefill_step_size ?? 2048,
      kv_precision: r.kv_precision ?? 'auto',
      stop: r.stop ?? [],
      stream: r.stream ?? true,
      thinking: r.thinking ?? 'default',
    });
    if (
      !limits(r.max_tokens, 1, 2048, true) ||
      !limits(r.temperature, 0, 2) ||
      !limits(r.top_p, 0.01, 1) ||
      !limits(r.context_limit, 128, 4096, true)
    )
      throw Error('采样参数或上下文预算超出范围。');
    if (
      ![512, 2048, 4096].includes(r.prefill_step_size) ||
      !['auto', 'f16', 'q8', 'q4'].includes(r.kv_precision)
    )
      throw Error('分块或 KV 精度不受支持。');
    if (
      !['default', 'enabled', 'disabled'].includes(r.thinking) ||
      (!info.thinking && r.thinking !== 'default')
    )
      throw Error('所选模型模板不支持此思考模式。');
    if (
      typeof r.stream !== 'boolean' ||
      !Array.isArray(r.stop) ||
      r.stop.length > 8 ||
      new Set(r.stop).size !== r.stop.length ||
      r.stop.some(
        (s) =>
          typeof s !== 'string' || !s.length || [...s].length > 128 || /[\x00-\x08\x0b-\x1f\x7f]/.test(s),
      )
    )
      throw Error('停止序列或流式设置无效。');
    if (r.overflow && r.overflow !== 'reject') throw Error('仅支持完整输入预算检查。');
  } else if (draft.kind === 'audio') {
    if (
      r.device_id !== 'cpu' ||
      r.voice !== 'zf_xiaobei' ||
      r.sample_rate !== 24000 ||
      !limits(r.speed, 0.5, 2)
    )
      throw Error('中文配音需要本机 CPU、小北音色及 24 kHz 输出。');
    if (
      !/^[\p{Script=Han}\d\s，。！？、：；“”‘’（）…—,.!?;:]+$/u.test(draft.input.prompt) ||
      draft.input.prompt.length > 120
    )
      throw Error('配音文本须为 1—120 个中文字符、数字或常用标点。');
  } else {
    if (!limits(r.steps, 1, 100, true)) throw Error('扩散步数应在 1—100 之间。');
    if (draft.kind === 'image' && (r.size !== 512 || !limits(r.cfg, 0, 30)))
      throw Error('图片尺寸或引导强度无效。');
    if (info.pipeline === 'h3-image' || info.pipeline === 'h3-video') {
      delete r.vram_budget_gib;
      delete r.diffusion_placement;
      Object.assign(r, { pipeline: info.pipeline, diffusion_backend: 'stable-diffusion.cpp@532d2c1' });
      if (draft.kind === 'video') {
        // Older model-library drafts inherited the read-only AnimateDiff timing.
        if ((r.frames === 14 && r.fps === 7) || (r.frames == null && r.fps == null)) {
          Object.assign(r, { frames: 22, fps: 24 });
        }
        if (r.frames !== 22 || r.fps !== 24) throw Error('MiniMax-H3 配方使用 22 帧和 24 FPS。');
        Object.assign(r, { inference_width: 512, inference_height: 320 });
        if (!materialPrompt(draft.input).prompt.trim()) throw Error('请填写视频画面描述。');
      }
    } else if (draft.kind === 'video') {
      if (r.frames !== 14 || r.fps !== 7) throw Error('当前 AnimateDiff 配方使用 14 帧和 7 FPS。');
      Object.assign(r, {
        pipeline: 'animatediff-sd15',
        diffusion_backend: 'stable-diffusion.cpp@532d2c1',
        inference_width: 512,
        inference_height: 320,
        strength: 0.55,
      });
    }
    if (draft.input.negative_prompt && typeof draft.input.negative_prompt !== 'string')
      throw Error('负面提示词无效。');
  }
  if (
    draft.kind !== 'video' &&
    (typeof draft.input.prompt !== 'string' ||
      !draft.input.prompt.trim() ||
      draft.input.prompt.length > (draft.kind === 'text' ? 12000 : 2000))
  )
    throw Error('请输入有效的试用内容。');
  r.engine = 'ailab-gguf';
  return r;
}
async function linkWeight(source, dest) {
  try {
    await fsp.link(source, dest);
  } catch (e) {
    if (e.code !== 'EXDEV') throw e;
    await fsp.copyFile(source, dest);
  }
}
async function render(job, model, material, out, signal, event, extra = {}) {
  const { runtime: r, input, kind } = job;
  if (kind === 'text') {
    const decoder = new StringDecoder('utf8');
    let text = '',
      done = false;
    await textWorker(
      {
        action: 'generate',
        model,
        prompt: material ? materialPrompt(input).prompt : input.prompt,
        media: material,
        projector: extra.projector,
        runtime: r,
      },
      signal,
      (e) => {
        if (e.type === 'bytes') {
          const fragment = decoder.write(Buffer.from(e.hex, 'hex'));
          text += fragment;
          if (r.stream && fragment) event('token', { text: fragment });
        } else if (e.type === 'done') {
          done = true;
          event('metrics', e);
        } else event(e.type, e);
      },
    );
    if (!done) throw Error('推理进程没有返回完成状态。');
    const rest = decoder.end();
    text += rest;
    if (rest && r.stream) event('token', { text: rest });
    await fsp.writeFile(path.join(out, 'result.txt'), text);
    return { name: 'result.txt', media_type: 'text/plain', text };
  }
  const local = 'weights.gguf';
  const alias = path.join(out, local);
  await linkWeight(model, alias);
  const temporary = [alias];
  try {
    if (kind === 'audio')
      return await synthesize(bins.audio, invoke, local, input.prompt, r, out, signal, event);
    for (const [role, file] of Object.entries(extra)) {
      const dest = path.join(out, role + '.gguf');
      await linkWeight(file, dest);
      temporary.push(dest);
    }
    if (kind === 'video')
      temporary.push(
        ...['condition.rgb', 'frames.rgb', 'audio.f32', 'audio.json'].map((name) => path.join(out, name)),
      );
    if (kind === 'video' && material) {
      // SD 1.5 requires multiples of 64. Reserve 16 extra rows above and below the 16:9 content.
      await invoke(
        bins.ffmpeg,
        [
          '-v',
          'error',
          '-i',
          material,
          '-vf',
          'scale=512:288:force_original_aspect_ratio=decrease,pad=512:288:(ow-iw)/2:(oh-ih)/2,pad=512:320:0:16,setsar=1',
          '-frames:v',
          '1',
          '-pix_fmt',
          'rgb24',
          '-f',
          'rawvideo',
          'condition.rgb',
        ],
        { cwd: out, signal },
      );
    }
    await invoke(bins[kind], [], {
      cwd: out,
      signal,
      input: {
        kind,
        input: r.pipeline === 'h3-video' ? { ...input, prompt: materialPrompt(input).prompt } : input,
        runtime: r,
        has_image: !!material,
        has_audio: !!extra.audio_vae,
      },
      onLine(line) {
        if (line.startsWith('{')) {
          const e = JSON.parse(line);
          event(e.type, e);
        }
      },
    });
    if (kind === 'image') return { name: 'image.png', media_type: 'image/png' };
    const bytes = r.inference_width * r.inference_height * r.frames * 3;
    if ((await fsp.stat(path.join(out, 'frames.rgb'))).size !== bytes)
      throw Error('视频模型输出帧数与配方不符。');
    let audioArgs = [];
    if (extra.audio_vae) {
      const audio = JSON.parse(await fsp.readFile(path.join(out, 'audio.json'), 'utf8'));
      if (
        !Number.isInteger(audio.rate) ||
        audio.rate < 8000 ||
        audio.rate > 192000 ||
        ![1, 2].includes(audio.channels)
      )
        throw Error('无效的 H3 音轨。');
      audioArgs = [
        '-f',
        'f32le',
        '-ar',
        String(audio.rate),
        '-ac',
        String(audio.channels),
        '-i',
        'audio.f32',
        '-c:a',
        'aac',
        '-t',
        String(r.frames / r.fps),
      ];
    }
    await invoke(
      bins.ffmpeg,
      [
        '-v',
        'error',
        '-f',
        'rawvideo',
        '-pixel_format',
        'rgb24',
        '-video_size',
        r.inference_width + 'x' + r.inference_height,
        '-framerate',
        String(r.fps),
        '-i',
        'frames.rgb',
        ...audioArgs,
        '-frames:v',
        String(r.frames),
        '-vf',
        'crop=512:288:0:16,scale=1024:576:flags=lanczos,setsar=1',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-movflags',
        '+faststart',
        'video.mp4',
      ],
      { cwd: out, signal },
    );
    return { name: 'video.mp4', media_type: 'video/mp4' };
  } finally {
    await Promise.all(temporary.map((file) => fsp.rm(file, { force: true })));
  }
}
module.exports = { bins, devices, parameters, render, textWorker, invoke };
