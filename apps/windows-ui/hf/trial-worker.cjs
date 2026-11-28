'use strict';
const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const { spawn } = require('node:child_process');
const { metadata } = require('./gguf-metadata.cjs');
const { inputModel, useService, runService } = require('./llama-service.cjs');
const { materialPrompt, componentPath } = require('./gguf-bundle.cjs');
const { audioDeviceArgs, audioDevices, diffusionDevices, gpuBackend, deviceExecutable, textExecutable, logicalProcessors, trialThreads } = require('./trial-devices.cjs');
const { audioEngine, diffusionEngine } = require('./generation-runtime.cjs');
const { synthesize } = require('./kokoro.cjs');
const { StringDecoder } = require('node:string_decoder');
const { createInterface } = require('node:readline');
const { root, workerEnvironment, engineTempDirectory } = require('./engine-environment.cjs');
const customGraphs = new Set(['llama-plm', 'llama-step35-full', 'llama-qwen4exp-ple']);
const bins = {
  text: path.join(root, 'text', 'ailab-gguf.exe'),
  llamaService: path.join(root, 'text', 'llama-server.exe'),
  image: path.join(root, 'diffusion', 'ailab-image.exe'),
  video: path.join(root, 'diffusion', 'ailab-image.exe'),
  audio: path.join(root, 'audio', 'audiocpp_cli.exe'),
  ffmpeg: path.join(root, 'diffusion', 'ffmpeg.exe'),
};
let cachedDriver;
function driverFile() {
  if (cachedDriver !== undefined) return cachedDriver;
  try {
    const store = path.join(process.env.SystemRoot, 'System32', 'DriverStore', 'FileRepository');
    const drivers = fs.readdirSync(store).filter(name => /^nv.*\.inf_amd64_/i.test(name))
      .map(name => path.join(store, name, 'nv-vk64.json')).filter(file => fs.existsSync(file))
      .map(file => ({ file, modified: fs.statSync(file).mtimeMs }));
    cachedDriver = drivers.sort((a, b) => b.modified - a.modified)[0]?.file || null;
  } catch { cachedDriver = null; }
  return cachedDriver;
}
function environment(exe) {
  const env = workerEnvironment(exe);
  // On hybrid Windows laptops an obsolete second ICD can hang enumeration. Use
  // the active NVIDIA ICD when present, otherwise let the Vulkan loader probe.
  const driver = driverFile();
  if (driver) env.VK_DRIVER_FILES = driver;
  return env;
}
function invoke(exe, args, { cwd = path.dirname(exe), input, signal, onLine = () => {}, onLog, timeout = 0 } = {}) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(Error('运行已停止。'));
      return;
    }
    const child = spawn(exe, args, {
      cwd,
      env: environment(exe),
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
        onLog?.(line);
      } catch (e) {
        fatal = e;
        kill();
      }
    });
    child.stderr.on('data', (data) => {
      tail = (tail + data.toString()).slice(-5000);
    });
    if (onLog) createInterface({ input: child.stderr, crlfDelay: Infinity }).on('line', onLog);
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
        return reject(fatal || Error(path.basename(exe)+' 退出码 '+code+'。'+tail.trim().slice(-1800)));
      resolve(tail.trim());
    });
  });
}
async function textWorker(input, signal, event = () => {}, resident) {
  if (input.model && typeof input.prompt==='string' && metadata(input.model).normalizeNfc)
    input={...input,prompt:input.prompt.normalize('NFC')};
  if (resident && input.runtime?.pipeline==='llama-gptj') {
    const dir=await resident.directory();
    if (!resident.gptj) {
      await linkWeight(input.model,path.join(dir,'weights.gguf'));
      await invoke(bins.text,[],{cwd:dir,signal,input:{action:'prepare-gptj-layout',vocabulary_only:false}});
      resident.gptj=path.join(dir,'layout.gguf');
    }
    input={...input,model:resident.gptj};
  } else if (['inspect','generate'].includes(input.action) && input.runtime?.pipeline === 'llama-gptj') {
    const dir=await fsp.mkdtemp(path.join(engineTempDirectory('text'),'ailab-gptj-'));
    try {
      const inspect=input.action==='inspect';
      const space=await fsp.statfs(dir);
      if (!inspect && space.bavail*space.bsize < (await fsp.stat(input.model)).size+64*1024**2)
        throw Error('GPT-J 量化行转换所需的临时磁盘空间不足。');
      await linkWeight(input.model,path.join(dir,'weights.gguf'));
      await invoke(bins.text,[],{cwd:dir,signal,input:{action:'prepare-gptj-layout',vocabulary_only:inspect}});
      return await nativeTextWorker({...input,model:path.join(dir,'layout.gguf')},signal,event);
    } finally { await fsp.rm(dir,{recursive:true,force:true}); }
  }
  return nativeTextWorker(input,signal,event,undefined,undefined,resident);
}
async function nativeTextWorker(input, signal, event, executable, onLog, resident) {
  const worker = customGraphs.has(input.runtime?.pipeline) ? path.join(path.dirname(bins.text),'plm-worker.exe') : bins.text;
  const exe = executable ?? textExecutable(worker, input.runtime);
  if (resident) {
    const r=input.runtime;
    const key=JSON.stringify([exe,input.model,input.ple_table,r.device_id,r.language_weight_conversion,r.cpu_no_repack,r.cpu_working_set_mib]);
    const send=await resident.connect(key,(lifetime,ready)=>
      require('./resident-text.cjs').nativeSession(exe,environment(exe),input,lifetime,ready),signal);
    if (input.action!=='preload') return send(input,event,signal);
    return;
  }
  await invoke(exe, [], {
    input,
    signal,
    onLog,
    timeout: input.action === 'devices' ? 15000 : input.action === 'inspect' ? 90000 : 0,
    onLine(line) {
      const e = JSON.parse(line);
      if (e.type === 'error') throw Error(e.message);
      event(e);
    },
  });
}
async function enumerateDevices(cpuOnly, executable = bins.text) {
  let items;
  const capabilities = new Map();
  await nativeTextWorker({ action: 'devices', cpu_only: cpuOnly }, undefined, (event) => {
    if (event.type === 'devices') items = event.items;
  }, executable, line => {
    const match = /^\s*Device (\d+): .*?, compute capability (\d+\.\d+),/i.exec(line);
    if (match) capabilities.set('CUDA' + match[1], match[2]);
  });
  if (!Array.isArray(items) || !items.some(device => device.id === 'cpu'))
    throw Error('GGML 执行器未返回 CPU 设备。');
  return items.map(item => capabilities.has(item.id) ? { ...item, cuda_compute_capability: capabilities.get(item.id) } : item);
}

async function cudaInventories() {
  const probes = {
    text: enumerateDevices(false, path.join(root, 'text', 'cuda', 'ailab-gguf.exe')),
    audio: audioDevices(invoke, path.join(root, 'audio', 'cuda', 'audiocpp_cli.exe')).then(rows =>
      rows.map(row => ({ id: row.name, name: row.description, memory_bytes: row.memory?.total_bytes, free_bytes: row.memory?.free_bytes }))),
    diffusion: diffusionDevices(invoke, path.join(root, 'diffusion', 'cuda', 'sd-cli.exe')),
  };
  return Promise.all(Object.entries(probes).map(async ([engine, probe]) => {
    try {
      return { engine, devices: (await probe).filter(row => /^CUDA\d+$/.test(row.id)) };
    } catch (error) {
      return { engine, devices: [], error: error.message };
    }
  }));
}
let cachedInventory, inventoryPending;
function deviceInventory(refresh = false) {
  if (inventoryPending) return inventoryPending;
  if (!refresh && cachedInventory) return Promise.resolve(cachedInventory);
  if (refresh) cachedDriver = undefined;
  cachedInventory = undefined;
  inventoryPending = (async () => {
    const [standard, cuda] = await Promise.all([enumerateDevices(false).catch(() => null), cudaInventories()]);
    const items = standard ?? await enumerateDevices(true).catch(() => []);
    for (const { engine, devices } of cuda) {
      for (const row of devices) {
        const existing = items.find(item => item.id === row.id);
        if (existing) (existing.cuda_engines ??= []).push(engine);
        else items.push({ ...row, backend: row.id, cuda_engines: [engine] });
      }
    }
    if (!items.length) throw Error('本机推理环境未返回可用设备。');
    const devices = items.map(device => ({
      ...device, ...(device.id === 'cpu' ? { logical_processors: logicalProcessors() } : {}),
      name: device.name.trim() + ' · ' + device.backend, status: 'ready', engine: 'AiLab GGUF',
    }));
    return { devices, cuda, cpuFallback: !standard && devices.every(device => device.id === 'cpu') };
  })().then(result => (cachedInventory = result)).finally(() => { inventoryPending = undefined; });
  return inventoryPending;
}
async function devices(refresh = false) {
  return (await deviceInventory(refresh)).devices;
}
function limits(n, min, max, integer = false) {
  return Number.isFinite(n) && (!integer || Number.isInteger(n)) && n >= min && n <= max;
}
function parameters(draft, info, loading=false) {
  const config = modelParameters(draft, info, loading);
  if (config.device_id === 'cpu') {
    const maximum = logicalProcessors();
    const threads = draft.runtime.cpu_threads ?? maximum;
    if (!limits(threads, 1, maximum, true)) throw Error('CPU 逻辑核心数必须是 1 到 ' + maximum + ' 之间的整数。');
    config.cpu_threads = threads;
  } else {
    delete config.cpu_threads;
  }
  return config;
}

function modelParameters(draft, info, loading) {
  const r = { ...draft.runtime };
  r.device_id ??= 'cpu';
  if (r.device_id !== 'cpu') gpuBackend(r.device_id);
  delete r.audio_device_index;
  delete r.cuda_compute_capability;
  if (draft.execution_target_id || draft.adapter_id || draft.checkpoint_id)
    throw Error('本次 GGUF 试用需要本机基座模型。');
  if (!limits(r.seed, 0, 4294967295, true)) throw Error('随机种子超出范围。');
  if (info.packageId && draft.kind !== 'audio') {
    if (typeof draft.input.prompt !== 'string' || !draft.input.prompt.trim() || draft.input.prompt.length>2000)
      throw Error('请填写 1—2000 字的画面描述。');
    if (!limits(r.steps,1,100,true) || !limits(r.cfg ?? 2,0,30)) throw Error('生成步数或引导强度超出范围。');
    if (draft.kind === 'image' && r.size !== 512) throw Error('当前图片试用尺寸为 512 × 512。');
    if (draft.input.negative_prompt != null && (typeof draft.input.negative_prompt !== 'string' || draft.input.negative_prompt.length>2000))
      throw Error('负面提示词最多可填写 2000 字。');
    if (draft.kind === 'video' && (!limits(r.frames ?? 5, 1, 129, true) || !limits(r.fps ?? 8, 1, 60, true)))
      throw Error('视频帧数或帧率超出范围。');
    const spec=require('./generation-packages.cjs').recipe(info.packageId);
    return {engine:'ailab-gguf',device_id:r.device_id,pipeline:info.pipeline,generation_package:info.packageId,seed:r.seed,steps:r.steps,
      diffusion_backend:'stable-diffusion.cpp@'+(spec?.diffusionVersion || '532d2c1'),
      cfg:r.cfg ?? 2,negative_prompt:draft.input.negative_prompt || '',
      ...(draft.kind==='video'?{frames:r.frames ?? 5,fps:r.fps ?? 8,inference_width:160,inference_height:96}:{size:r.size})};
  }
  if (draft.kind === 'text') {
    if (info.pipeline==='llama-gptj' || customGraphs.has(info.pipeline)) r.pipeline=info.pipeline;
    else if (r.pipeline==='llama-gptj' || customGraphs.has(r.pipeline)) delete r.pipeline;
    Object.assign(r, {
      context_limit: r.context_limit ?? 4096,
      prefill_step_size: r.prefill_step_size ?? 2048,
      kv_precision: r.kv_precision ?? 'f16',
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
  } else if (draft.kind === 'image' && ['esrgan-x4', 'mosr-x4'].includes(info.pipeline)) {
    if (!draft.input.material_id) throw Error('请选择需要放大的 PNG 图片。');
    return {engine:'ailab-gguf', pipeline:info.pipeline, device_id:r.device_id, scale:4};
  } else if (draft.kind === 'audio' && ['gen', 'tts'].includes(info.audioTask)) {
    const prompt = draft.input.prompt;
    if (typeof prompt !== 'string' || !prompt.trim() || prompt.length > 2000)
      throw Error('请输入 1—2000 字的试用内容。');
    const config = {engine: 'ailab-gguf', pipeline: info.pipeline, family: info.audioFamily, device_id: r.device_id, seed: r.seed};
    if (info.packageId || info.nativeRecipe) {
      config.generation_package=info.packageId || info.nativeRecipe;
      if (info.nativeRecipe) config.native_recipe=true;
      const spec=require('./generation-packages.cjs').recipe(config.generation_package,config.native_recipe);
      if (r.device_id !== 'cpu' && spec.audioWorker === 'f5') throw Error('F5-TTS 的 Windows 配方仅支持 CPU。');
      config.audio_backend='audio.cpp@'+(spec.audioVersion || '0.9.5')+(spec.audioWorker?'/'+spec.audioWorker+'-windows':'');
      const material=materialPrompt(draft.input);
      if (info.audioTask==='tts' && spec.audioLimitOption && r.max_tokens!==undefined) {
        if (!limits(r.max_tokens,1,16384,true)) throw Error('语音生成长度上限应在 1—16384 之间。');
        config.max_tokens=r.max_tokens;
      }
      if (info.audioTask==='tts' && spec.minSteps && r.steps!==undefined) {
        if (!limits(r.steps,1,100,true)) throw Error('此语音模型的生成步数超出范围。');
        config.steps=spec.fixedSteps ?? Math.max(r.steps,spec.minSteps);
      }
      const {text,transcript}=require('./generation-runtime.cjs').referenceText(material.prompt);
      if (!text) throw Error('请填写要生成的文本。');
      if (spec.transcript && (spec.family||info.audioFamily)!=='qwen3_tts' && material.reference && !transcript) throw Error('参考音频需要对应原文，请在素材引用后另起一行填写 @参考文本 和原文。');
    }
    if (info.audioTask === 'gen') {
      const spec=require('./generation-packages.cjs').recipe(config.generation_package,config.native_recipe);
      const steps=spec?.minSteps ? Math.max(spec.minSteps,r.steps ?? 2) : info.audioFamily==='stable_audio' ? 2 : undefined;
      if (steps!==undefined && !limits(steps,1,100,true)) throw Error('音频生成步数超出范围。');
      return {...config,duration_seconds:2,...(steps===undefined ? {} : {steps})};
    }
    if (!limits(r.speed ?? 1, 0.5, 2)) throw Error('语速超出范围。');
    return { ...config, speed: r.speed ?? 1, sample_rate: 24000 };
  } else if (draft.kind === 'audio' && (info.audioTask || info.pipeline === 'firered-vad')) {
    if (!materialPrompt(draft.input).reference) throw Error('请选择当前项目中的 WAV 音频素材。');
    return {engine:'ailab-gguf', pipeline:info.pipeline, device_id:r.device_id, sample_rate:16000};
  } else if (draft.kind === 'audio' && info.pipeline==='llama-hibiki') {
    if (!materialPrompt(draft.input).reference) throw Error('Hibiki 需要当前项目中的法语 WAV 素材。');
    return {engine:'ailab-gguf',pipeline:info.pipeline,device_id:r.device_id,seed:r.seed,
      context_limit:Math.min(info.trainedContext || 1500,1500),prefill_step_size:512,kv_precision:'auto'};
  } else if (draft.kind === 'audio' && ['llama-tts','llama-vocoder'].includes(info.pipeline)) {
    if (typeof draft.input.prompt !== 'string' || !draft.input.prompt.trim()) throw Error('请输入语音文本或音频码。');
    if (r.speed !== undefined && !limits(r.speed,0.5,2)) throw Error('语速超出范围。');
    return {engine:'ailab-gguf',pipeline:info.pipeline,device_id:r.device_id,seed:r.seed,speed:r.speed ?? 1,
      context_limit:Math.min(info.trainedContext || 4096,4096),max_tokens:1,prefill_step_size:512,kv_precision:'auto'};
  } else if (draft.kind === 'audio') {
    if (
      r.voice !== 'zf_xiaobei' ||
      r.sample_rate !== 24000 ||
      !limits(r.speed, 0.5, 2)
    )
      throw Error('中文配音需要小北音色及 24 kHz 输出。');
    if (
      !/^[\p{Script=Han}\d\s，。！？、：；“”‘’（）…—,.!?;:]+$/u.test(draft.input.prompt) ||
      draft.input.prompt.length > 120
    )
      throw Error('配音文本须为 1—120 个中文字符、数字或常用标点。');
  } else {
    if (!limits(r.steps, 1, 100, true)) throw Error('扩散步数应在 1—100 之间。');
    if (draft.kind === 'image' && (r.size !== 512 || !limits(r.cfg, 0, 30)))
      throw Error('图片尺寸或引导强度无效。');
    if (draft.kind === 'video' && info.pipeline === 'wan21-t2v') {
      if (typeof draft.input.prompt !== 'string' || !draft.input.prompt.trim() || draft.input.prompt.length > 2000)
        throw Error('请填写 1—2000 字的视频画面描述。');
      if (draft.input.material_id) throw Error('Wan 2.1 T2V 使用文字生成视频，请清除首帧素材。');
      Object.assign(r, {pipeline:info.pipeline, frames:5, fps:8, inference_width:160,
        inference_height:96, diffusion_backend:'stable-diffusion.cpp@532d2c1'});
    } else if (draft.kind === 'image' && ['iris','anima'].includes(info.pipeline)) {
      Object.assign(r, {pipeline:info.pipeline, diffusion_backend:'stable-diffusion.cpp@532d2c1'});
    } else if (info.pipeline === 'z-image') {
      Object.assign(r, { pipeline: info.pipeline, diffusion_backend: 'stable-diffusion.cpp@532d2c1' });
    } else if (info.pipeline === 'h3-image' || info.pipeline === 'h3-video') {
      delete r.vram_budget_gib;
      delete r.diffusion_placement;
      Object.assign(r, { pipeline: info.pipeline, diffusion_backend: 'stable-diffusion.cpp@532d2c1' });
      if (draft.kind === 'video') {
        // Saved drafts can inherit either fixed timing from another video recipe.
        if ((r.frames === 14 && r.fps === 7) || (r.frames === 5 && r.fps === 8) || (r.frames == null && r.fps == null)) {
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
    !loading && draft.kind !== 'video' &&
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
async function renderGeneratedAudio(model, prompt, r, extra, out, signal, invoke) {
  const { audioTask, audioFamily } = metadata(model);
  if (r.family !== audioFamily || r.pipeline !== 'audiocpp-' + audioTask)
    throw Error('音频模型与已检查的家族不匹配。');
  // Keep only the verified weights and voice assets visible to the package loader.
  const dir = await fsp.mkdtemp(path.join(out, 'audio-'));
  try {
    await linkWeight(model, path.join(dir, 'model.gguf'));
    for (const [role, file] of Object.entries(extra)) {
      const dest = componentPath(dir, role);
      await fsp.mkdir(path.dirname(dest), { recursive: true });
      await linkWeight(file, dest);
    }
    const source = Object.keys(extra).length ? path.basename(dir) : path.join(path.basename(dir), 'model.gguf');
    const raw = path.join(path.basename(dir), 'generated.wav');
    const args = ['--task', audioTask, '--family', audioFamily, '--mode', 'offline', ...audioDeviceArgs(r),
      '--threads', String(trialThreads(r)), '--model', source, '--text', prompt.trim(), '--seed', String(r.seed), '--out', raw];
    if (['piper_tts', 'inflect_v2', 'sanotts', 'kitten_tts'].includes(audioFamily)) {
      const phonemizer = path.join(path.dirname(bins.audio), 'espeak');
      args.push('--session-option', audioFamily + '.espeak_library_path=' + path.join(phonemizer, 'espeak-ng.dll'),
        '--session-option', audioFamily + '.espeak_data_path=' + path.join(phonemizer, 'espeak-ng-data'));
    }
    if (audioTask === 'gen') {
      args.push('--duration-seconds', String(r.duration_seconds), '--request-option', 'duration_sec=' + r.duration_seconds);
      if (audioFamily === 'stable_audio')
        args.push('--num-inference-steps', String(r.steps), '--request-option', 'duration_padding_sec=0');
    }
    await invoke(audioEngine(bins.audio, undefined, r.device_id), args, { cwd: out, signal });
    const format = audioTask === 'tts' ? ['-af', 'atempo=' + r.speed, '-ar', String(r.sample_rate), '-ac', '1'] : [];
    await invoke(bins.ffmpeg, ['-v', 'error', '-i', raw, '-map', '0:a:0', ...format,
      '-c:a', 'pcm_s16le', 'speech.wav'], { cwd: out, signal });
    if ((await fsp.stat(path.join(out, 'speech.wav'))).size < 128) throw Error('音频模型返回空波形。');
    return {name: 'speech.wav', media_type: 'audio/wav'};
  } finally {
    await fsp.rm(dir, { recursive: true, force: true });
  }
}
async function prepareCompactText(source, output, signal, sourceSha256) {
  const info=metadata(source);
  const space=await fsp.statfs(path.dirname(output));
  if (space.bavail*space.bsize<info.compactTextBytes+64*1024**2) throw Error('准备低内存语言权重所需的临时磁盘空间不足。');
  const {compactSaving}=require('./gguf-metadata.cjs');
  const {tensors,alignment}=metadata(source,true);
  const matrices=tensors.filter(t=>compactSaving(info.compactTextType,t.name,t.shape,t.type,alignment)>0).map(t=>t.name);
  await invoke(bins.text,[],{signal,input:{action:'compact-language',cpu_only:true,model:source,output,matrices,source_sha256:sourceSha256}});
  if (info.legacyCogQkv) await require('./cogvlm-layout.cjs').joinInPrivateFile(output);
}
async function render(job, model, material, out, signal, event, extra = {}, decisionMedia = [], resident, preload=false) {
  const runMedia = require('./trial-timing.cjs').timedMediaInvoke(invoke, bins, event);
  const { runtime: r, input, kind } = job;
  if (r.generation_package)
    return require('./generation-runtime.cjs').runPackage({model,extra,material,out,input:material ? materialPrompt(input).prompt : input.prompt,
      r:{...r,negative_prompt:input.negative_prompt},bins,invoke:runMedia,linkWeight,signal});
  const service = textExecutable(bins.llamaService, r);
  if (r.pipeline === 'llama-hibiki' && kind === 'audio') {
    const pcm = path.join(out,'hibiki-input.pcm');
    try {
      await runMedia(bins.ffmpeg,['-v','error','-i',material,'-map','0:a:0','-ac','1','-ar','24000','-f','s16le',pcm],{cwd:out,signal});
      return await runService({exe:service,env:environment(service),file:model,info:{...metadata(model),pipeline:r.pipeline},
        r,extra,media:pcm,prompt:'',out,signal,event});
    } finally { await require('node:fs/promises').rm(pcm,{force:true}); }
  }
  if (kind === 'text' || r.pipeline==='llama-tts') {
    const shards=Object.keys(extra).filter(key=>/^shard_\d{5}$/.test(key)).sort().map(key=>extra[key]);
    if (resident) {
      resident.shards ??= await require('./legacy-q4.cjs').prepareShards([model,...shards],await resident.directory(),r.model_manifest_digest,signal,linkWeight);
      model=resident.shards;
    } else model=await require('./legacy-q4.cjs').prepareShards([model,...shards],out,r.model_manifest_digest,signal,linkWeight);
    const sourceInfo=metadata(model);
    if (sourceInfo.compactTextBytes && r.device_id==='cpu' && r.language_weight_conversion==='mixed_'+sourceInfo.compactTextType) {
      const source=model;
      model=await require('./cached-layout.cjs').cachedLayout(source,'text-'+sourceInfo.compactTextType,r.model_manifest_digest,undefined,signal,async output=>{
        await prepareCompactText(source,output,signal);
      });
    } else if (sourceInfo.legacyCogQkv) model=await require('./cogvlm-layout.cjs').preparedCog(model,r.model_manifest_digest,signal);
    if (sourceInfo.legacyGraniteShared)
      model = await require('./granite-swa-layout.cjs').preparedGraniteSwa(model,signal,r.model_manifest_digest);
    if (sourceInfo.legacyInklingLoop)
      model = await require('./inkling-layout.cjs').preparedInkling(model,signal,r.model_manifest_digest);
    if (sourceInfo.legacyZayaLayers) {
      const source=model;
      model = await require('./cached-layout.cjs').cachedLayout(source,'zaya',r.model_manifest_digest,undefined,signal,
        output=>invoke(bins.text,[],{signal,input:{action:'prepare-zaya-layout',cpu_only:true,model:source,output}}));
    }
    const info={...inputModel(metadata(model),material ? materialPrompt(input).prompt : input.prompt)};
    if (r.pipeline==='llama-tts') info.pipeline=r.pipeline;
    if (material && info.arch==='cogvlm' && extra.projector && metadata(extra.projector).legacyCogProjector) {
      const projector=await require('./cogvlm-layout.cjs').preparedCog(extra.projector,r.model_manifest_digest,signal,'projector');
      extra={...extra,projector};
    }
    if (extra.draft) info.specType=metadata(extra.draft).specType;
    if (useService(info,extra,material,r) && !(info.legacyCogChat && material && r.device_id==='cpu'))
      return runService({exe:service,env:environment(service),file:model,info,r,extra,media:material,decisionMedia,
        prompt:material ? materialPrompt(input).prompt : input.prompt,out,signal,event,resident,preload});
    if (info.nativeThinkPrefill && r.thinking !== 'disabled')
      event('execution_parameters', { reasoning_prefilled: true });
  }
  if (kind === 'text' || r.pipeline==='llama-vocoder') {
    const decoder = new StringDecoder('utf8');
    let text = '',
      done = false;
    await textWorker(
      {
        action: preload ? 'preload' : 'generate',
        model,
        prompt: material ? materialPrompt(input).prompt : input.prompt,
        media: material,
        projector: extra.projector,
        ...(material && r.device_id==='cpu' && metadata(model).legacyCogChat ? {cogvlm_chat_v1:true} : {}),
        ple_table: extra.ple_table,
        runtime: r, ...(r.pipeline==='llama-vocoder' ? {wav:path.join(out,'result.wav')} : {}),
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
      resident,
    );
    if (preload) return;
    if (!done) throw Error('推理进程没有返回完成状态。');
    if (r.pipeline==='llama-vocoder') return {name:'result.wav',media_type:'audio/wav'};
    const rest = decoder.end();
    text += rest;
    if (rest && r.stream) event('token', { text: rest });
    await fsp.writeFile(path.join(out, 'result.txt'), text);
    return { name: 'result.txt', media_type: 'text/plain', text };
  }
  if (kind === 'audio' && ['audiocpp-tts', 'audiocpp-gen'].includes(r.pipeline))
    return renderGeneratedAudio(model, input.prompt, r, extra, out, signal, runMedia);
  const local = 'weights.gguf';
  const alias = path.join(out, local);
  await linkWeight(model, alias);
  const temporary = [alias];
  try {
    if (kind === 'image' && ['esrgan-x4', 'mosr-x4'].includes(r.pipeline)) {
      const source = path.join(out, 'input.png');
      temporary.push(source);
      await linkWeight(material, source);
      await runMedia(diffusionEngine(bins.image, undefined, r.device_id),
        ['-M','upscale','--backend',r.device_id.toLowerCase(),'--params-backend','cpu','--upscale-model',local,
          ...(r.device_id === 'cpu' ? ['-t', String(trialThreads(r))] : []),'-i','input.png','-o','image.png'], {cwd:out,signal});
      const result = await fsp.open(path.join(out,'image.png'),'r');
      try {
        const input = await fsp.open(source,'r');
        try {
          const src = Buffer.alloc(24), dst = Buffer.alloc(24);
          await input.read(src); await result.read(dst);
          if (dst.readUInt32BE(16)!==4*src.readUInt32BE(16) || dst.readUInt32BE(20)!==4*src.readUInt32BE(20))
            throw Error('放大模型未返回四倍尺寸的图像。');
        } finally { await input.close(); }
      } finally { await result.close(); }
      return {name:'image.png',media_type:'image/png'};
    }
    if (kind === 'audio' && ['firered-vad', 'audiocpp-vad', 'audiocpp-asr'].includes(r.pipeline)) {
      const {audioTask, audioFamily} = metadata(model);
      if (!audioTask) throw Error('音频权重与执行配置不匹配。');
      temporary.push(path.join(out, 'input.wav'));
      await runMedia(bins.ffmpeg, ['-v','error','-i',material,'-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le','input.wav'], {cwd:out,signal});
      const args = ['--task',audioTask,'--family',audioFamily,...audioDeviceArgs(r),
        ...(r.device_id === 'cpu' ? ['--threads', String(trialThreads(r))] : []),'--model',local,'--audio','input.wav'];
      if (audioTask === 'asr') {
        await runMedia(audioEngine(bins.audio, undefined, r.device_id),[...args,'--text-out','result.txt'],{cwd:out,signal});
        const text=(await fsp.readFile(path.join(out,'result.txt'),'utf8')).trim();
        if (!text) throw Error('未识别出有效语音。');
        return {name:'result.txt',media_type:'text/plain',text};
      }
      let segments;
      await runMedia(audioEngine(bins.audio, undefined, r.device_id), args, {
        cwd:out, signal, onLine(line) {
          if (line.startsWith('speech_segments=')) segments = JSON.parse(line.slice('speech_segments='.length));
        },
      });
      if (!Array.isArray(segments) || segments.some(s=>!Number.isSafeInteger(s.start_sample)||!Number.isSafeInteger(s.end_sample)||s.start_sample<0||s.end_sample<s.start_sample))
        throw Error('语音检测未返回有效的时间区间。');
      const text = segments.length ? segments.map(s=>(s.start_sample/16000).toFixed(3)+'–'+(s.end_sample/16000).toFixed(3)+' 秒').join('\n') : '未检测到语音。';
      await fsp.writeFile(path.join(out,'result.txt'),text);
      return {name:'result.txt',media_type:'text/plain',text};
    }
    if (kind === 'audio')
      return await synthesize(audioEngine(bins.audio, undefined, r.device_id), runMedia, local, input.prompt, r, out, signal, event);
    for (const [role, file] of Object.entries(extra)) {
      const dest = path.join(out, role + '.gguf');
      await linkWeight(file, dest);
      temporary.push(dest);
    }
    if (kind === 'image' && ['iris','anima'].includes(r.pipeline)) {
      const cli = diffusionEngine(bins.image, undefined, r.device_id), info = metadata(model);
      let denoiser = local;
      if (r.pipeline === 'iris' && info.irisPackedMatrices) {
        const disk = await fsp.statfs(out);
        const scratchBytes = Object.values(info.irisPackedMatrices).reduce((sum, [x,y]) => sum + 2*x*y, info.size);
        if (disk.bavail*disk.bsize < scratchBytes) throw Error('磁盘空间不足，无法临时展开 Iris 量化矩阵。');
        denoiser = 'iris-layout.gguf';
        const prepared = path.join(out, denoiser);
        temporary.push(prepared);
        await runMedia(bins.text, [], {cwd:out, signal, input:{action:'prepare-iris-layout', matrices:info.irisPackedMatrices}});
      }
      await runMedia(cli, ['-M','img_gen','--backend',r.device_id.toLowerCase(),'--params-backend','cpu',
        '--diffusion-model',denoiser,'--llm',r.pipeline + '_encoder.gguf',
        ...(r.pipeline === 'anima' ? ['--vae','anima_vae.gguf','--sampling-method','euler'] : []),
        '-p',input.prompt,'-n',input.negative_prompt || '',
        '-W',String(r.size),'-H',String(r.size),'--steps',String(r.steps),'--cfg-scale',String(r.cfg),
        '-t',String(trialThreads(r)),'-s',String(r.seed),'-o','image.png'], {cwd:out,signal});
      return {name:'image.png', media_type:'image/png'};
    }
    if (kind === 'video')
      temporary.push(
        ...['condition.rgb', 'frames.rgb', 'audio.f32', 'audio.json'].map((name) => path.join(out, name)),
      );
    if (kind === 'video' && r.pipeline === 'wan21-t2v') {
      temporary.push(path.join(out, 'wan.avi'));
      await runMedia(diffusionEngine(bins.video, undefined, r.device_id), ['-M','vid_gen','--backend',r.device_id.toLowerCase(),'--params-backend','cpu',
        '--diffusion-model',local,'--t5xxl','umt5.gguf','--vae','wan_vae.gguf','-p',input.prompt,'-n',input.negative_prompt || '',
        '-W',String(r.inference_width),'-H',String(r.inference_height),'--video-frames',String(r.frames),'--fps',String(r.fps),
        '--steps',String(r.steps),'--cfg-scale','1','--sampling-method','euler','--flow-shift','3','-t',String(trialThreads(r)),'-s',String(r.seed),'-o','wan.avi'], {cwd:out,signal});
      await runMedia(bins.ffmpeg, ['-v','error','-i','wan.avi','-map','0:v:0','-c:v','libx264','-pix_fmt','yuv420p',
        '-movflags','+faststart','video.mp4'], {cwd:out,signal});
      return {name:'video.mp4', media_type:'video/mp4'};
    }
    if (kind === 'video' && material) {
      // SD 1.5 requires multiples of 64. Reserve 16 extra rows above and below the 16:9 content.
      await runMedia(
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
    await runMedia(deviceExecutable(bins[kind], r.device_id), [], {
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
    await runMedia(
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
module.exports = { bins, devices, deviceInventory, parameters, render, textWorker, invoke, prepareCompactText, environment };
