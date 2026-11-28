'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const root = process.env.AILAB_RUNTIME_DIR || path.resolve(__dirname, '../runtime');
const engines = new Set(['text', 'diffusion', 'audio']);

function localDirectory(...parts) {
  const directory = path.join(process.env.LOCALAPPDATA || os.tmpdir(), 'GCSA-AiLab-UI-Preview', ...parts);
  fs.mkdirSync(directory, { recursive: true });
  return directory;
}

function engineTempDirectory(engine) {
  return localDirectory('engines', engine, 'temp');
}

function workerEnvironment(exe) {
  const env = {};
  for (const name of ['SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'LOCALAPPDATA', 'USERPROFILE', 'ProgramData', 'SystemDrive']) {
    if (process.env[name]) env[name] = process.env[name];
  }
  const system = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32');
  env.PATH = system;
  if (!exe) return env;

  const directory = path.dirname(exe);
  const cuda = path.basename(directory).toLowerCase() === 'cuda';
  const family = path.relative(root, exe).split(path.sep)[0].toLowerCase();
  if (!engines.has(family)) {
    if (cuda) throw Error('无法识别 CUDA 推理环境。');
    return env;
  }
  // FFmpeg is a standalone utility shared by media tasks, shipped alongside diffusion.
  const engine = family === 'diffusion' && path.basename(exe).toLowerCase() === 'ffmpeg.exe' ? 'ffmpeg' : family;
  env.TEMP = env.TMP = engineTempDirectory(engine);
  env.LOCALAPPDATA = localDirectory('engines', engine, 'local');
  env.APPDATA = localDirectory('engines', engine, 'roaming');
  env.XDG_CACHE_HOME = localDirectory('engines', engine, 'cache');
  if (engine === 'text') env.LLAMA_CACHE = env.XDG_CACHE_HOME;

  const search = engine === 'ffmpeg' ? [] : [directory];
  if (cuda) {
    search.push(path.join(root, family, 'cuda-runtime'));
    // Preserve the engine's existing compiled kernels across application updates.
    try { env.CUDA_CACHE_PATH = localDirectory('cuda-cache', family); }
    catch { env.CUDA_CACHE_DISABLE = '1'; }
  }
  env.PATH = [...search, system].join(path.delimiter);
  return env;
}

module.exports = { root, workerEnvironment, engineTempDirectory };
