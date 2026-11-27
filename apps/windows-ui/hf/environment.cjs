'use strict';
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID } = require('node:crypto');
const { bins, invoke, deviceInventory } = require('./trial-worker.cjs');
const { audioEngine, diffusionEngine } = require('./generation-runtime.cjs');
const { version } = require('../package.json');

function failureDetail(error) {
  if (error.code === 'ENOENT') return '未找到运行库。请在本页选择对应组件并点击“下载并配置”。';
  if (['EPERM', 'EACCES', 'EROFS'].includes(error.code)) return '访问被拒绝，请检查目录权限或安全软件记录。';
  if (error.code === 'ENOSPC') return '磁盘空间不足。';
  if (error.message?.includes('响应超时')) return '执行器响应超时，请检查设备驱动后重新检测。';
  const code = /退出码 (-?\d+)/.exec(error.message || '');
  if (code) {
    const hex = (Number(code[1]) >>> 0).toString(16).toUpperCase();
    if (hex === 'C0000135') return 'Windows 缺少所需的 DLL（0xC0000135），请检查运行包。';
    return '执行器启动或自检失败，退出码 ' + code[1] + '。';
  }
  return '未取得有效检测结果，请重新检测。';
}

async function check(id, label, run) {
  try {
    return { id, label, status: 'ready', ...await run() };
  } catch (error) {
    return { id, label, status: 'failed', detail: failureDetail(error) };
  }
}

async function versionCheck(exe, pattern) {
  const output = await invoke(exe, ['--version'], { timeout: 10000 });
  const match = pattern.exec(output);
  if (!match) throw Error('版本响应无效');
  return { detail: match[0].trim() };
}

async function modelStorage(directory) {
  const volume = await fs.statfs(directory);
  const file = path.join(directory, '.ailab-environment-' + randomUUID());
  const handle = await fs.open(file, 'wx+');
  try {
    await handle.writeFile('AiLab');
    const data = Buffer.alloc(5);
    await handle.read(data, 0, data.length, 0);
    if (data.toString() !== 'AiLab') throw Error('读回不匹配');
  } finally {
    try { await handle.close(); } finally { await fs.unlink(file); }
  }
  return { detail: '模型目录已通过临时文件读写检查。', free_bytes: volume.bavail * volume.bsize };
}

// Each alternative is an actual inference route. Every local task also needs the GGML device inventory.
const routes = {
  text: [['devices'], ['devices', 'server'], ['devices', 'custom']],
  image: [['devices', 'diffusion'], ['devices', 'sd'], ['devices', 'sdControl']],
  video: [['devices', 'diffusion', 'videoEncode'], ['devices', 'sd', 'videoEncode'], ['devices', 'sdControl', 'videoEncode']],
  audio: [['devices'], ['devices', 'server'], ['devices', 'audio'], ['devices', 'audio', 'audioConvert'],
    ['devices', 'audioF5', 'audioConvert'], ['devices', 'audio96', 'audioConvert'], ['devices', 'server', 'audioConvert']],
};
function capabilities(checks) {
  const results = new Map(checks.map(item => [item.id, item]));
  return Object.entries(routes).flatMap(([kind, alternatives]) => {
    const available = alternatives.filter(route => route.every(id => results.get(id).status !== 'failed'));
    const degraded = alternatives.some(route => route.some(id => results.get(id).status !== 'ready'));
    const status = available.length ? (degraded ? 'partial' : 'ready') : 'not_prepared';
    const affected = [...new Set(alternatives.flat())].map(id => results.get(id)).filter(item => item.status !== 'ready');
    return [
      { kind, operation: 'generate', supported: !!available.length, status,
        reason: affected.length ? affected.map(item => item.label + ' · ' + item.detail).join('；') : '基础运行环境已响应。' },
      { kind, operation: 'train', supported: false, status: 'not_prepared', reason: 'Windows 本机训练执行器尚未接入。' },
    ];
  });
}

function deviceRank({ id }) {
  if (id.startsWith('CUDA')) return 0;
  return id === 'cpu' ? 2 : 1;
}

async function probeEnvironment(directory, refresh) {
  let devices = [];
  const sdVersion = /stable-diffusion\.cpp version [^\r\n]+/i;
  const audioVersion = /audio\.cpp [^\r\n]+/i;
  const inventory = deviceInventory(refresh);
  const checks = await Promise.all([
    ...Object.entries({ text: 'llama.cpp', diffusion: 'stable-diffusion.cpp', audio: 'audio.cpp' }).map(([engine, label]) =>
      check(engine + 'Cuda', label + ' · CUDA 环境', async () => {
        const result = (await inventory).cuda.find(probe => probe.engine === engine);
        if (result.error) throw Error(result.error);
        const adapters = result.devices.map(row => row.name.trim() + ' · ' + row.id);
        return { detail: adapters.length ? adapters.join('，') : '执行器已响应，未检测到可用 CUDA 显卡。' };
      })),
    check('devices', 'GGML 设备枚举', async () => {
      const result = await inventory;
      devices = [...result.devices].sort((a, b) => deviceRank(a) - deviceRank(b));
      return result.cpuFallback
        ? { status: 'partial', detail: '完整设备枚举失败，CPU 回退检查通过。' }
        : { detail: '执行器返回 ' + devices.length + ' 个可选设备。' };
    }),
    check('server', 'llama.cpp 多模态服务', () => versionCheck(bins.llamaService, /version: [^\r\n]+/i)),
    check('diffusion', 'AiLab 图像与视频执行器', async () => {
      let ready = false;
      await invoke(bins.image, [], { input: { action: 'probe' }, timeout: 10000,
        onLine(line) { if (line.startsWith('{') && JSON.parse(line).type === 'diffusion_ready') ready = true; } });
      if (!ready) throw Error('扩散执行器响应无效');
      return { detail: '已加载扩散库并初始化图像、视频生成选项。' };
    }),
    check('sd', 'stable-diffusion.cpp', () => versionCheck(diffusionEngine(bins.image), sdVersion)),
    check('sdControl', 'stable-diffusion.cpp 扩展配方', () => versionCheck(diffusionEngine(bins.image, { diffusionVersion: '0d71f96' }), sdVersion)),
    check('audio', 'audio.cpp', () => versionCheck(bins.audio, audioVersion)),
    check('audioF5', 'audio.cpp F5 配方', () => versionCheck(audioEngine(bins.audio, { audioWorker: 'f5' }), audioVersion)),
    check('audio96', 'audio.cpp 0.9.6 配方', () => versionCheck(audioEngine(bins.audio, { audioVersion: '0.9.6' }), audioVersion)),
    check('videoEncode', 'FFmpeg 视频编码', async () => {
      const output = await invoke(bins.ffmpeg, ['-v','error','-nostats','-progress','pipe:1','-f','lavfi','-i','color=s=16x16:r=1','-frames:v','1','-c:v','libx264','-f','null','-'], { timeout: 10000 });
      if (!/^frame=1$/m.test(output) || !output.includes('progress=end')) throw Error('没有编码帧');
      return { detail: '已实际编码一帧 H.264 测试画面。' };
    }),
    check('audioConvert', 'FFmpeg 音频转换', async () => {
      const output = await invoke(bins.ffmpeg, ['-v','error','-nostats','-progress','pipe:1','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','0.05','-ac','1','-ar','16000','-c:a','pcm_s16le','-f','null','-'], { timeout: 10000 });
      if (!/^out_time_us=[1-9]\d*$/m.test(output) || !output.includes('progress=end')) throw Error('没有音频输出');
      return { detail: '已将测试音频转为 16 kHz 单声道 PCM。' };
    }),
    check('storage', '模型存储', () => modelStorage(directory)),
    check('custom', '扩展语言架构执行器', async () => {
      let ready = false;
      await invoke(path.join(path.dirname(bins.text), 'plm-worker.exe'), [], { input: { action: 'devices', cpu_only: true },
        timeout: 10000, onLine(line) { const e = JSON.parse(line); if (e.type === 'devices') ready = e.items.some(d => d.id === 'cpu'); } });
      if (!ready) throw Error('设备响应无效');
      return { detail: '扩展执行器已返回 CPU 设备。' };
    }),
  ]);
  const cpu = os.cpus();
  return { id: randomUUID(), checked_at: new Date().toISOString(), app_version: version,
    system: { os: os.type() === 'Windows_NT' ? 'Windows' : os.type(), release: os.release(), arch: os.arch(),
      cpu: cpu[0]?.model.trim() || '未知', logical_processors: cpu.length, ram_bytes: os.totalmem(), free_ram_bytes: os.freemem() },
    devices, checks, capabilities: capabilities(checks) };
}

class LocalEnvironment {
  constructor(directory, probe = probeEnvironment) {
    this.directory = directory;
    this.probe = probe;
  }
  get(refresh = false) {
    if (this.pending) return this.pending;
    if (!refresh && this.report) return Promise.resolve(this.report);
    this.pending = this.probe(this.directory, refresh).then(report => (this.report = report))
      .finally(() => { this.pending = undefined; });
    return this.pending;
  }
  async export(reportId, chooseFile) {
    const report = this.report;
    if (!report || report.id !== reportId) throw Error('检测结果已更新，请刷新后导出。');
    const name = 'AiLab-环境诊断-' + report.checked_at.replace(/[:.]/g, '-') + '.json';
    const file = await chooseFile(name);
    if (!file) return { saved: false };
    await fs.writeFile(file, JSON.stringify(report, null, 2) + '\n', 'utf8');
    return { saved: true, filename: path.basename(file) };
  }
}

module.exports = { LocalEnvironment, capabilities };
