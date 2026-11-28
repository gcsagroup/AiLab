'use strict';
const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const { createHash } = require('node:crypto');
const { Readable, Transform } = require('node:stream');
const { pipeline } = require('node:stream/promises');
const { spawn } = require('node:child_process');

const release = 'https://github.com/gcsagroup/AiLab/releases/download/windows-ui-preview-20261127/';
const llama = 'https://github.com/ggml-org/llama.cpp/releases/download/b12648/';
const sd = 'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-1106-532d2c1/';
const sd2 = 'https://github.com/leejet/stable-diffusion.cpp/releases/download/master-1117-0d71f96/';
const audio95 = 'https://github.com/0xShug0/audio.cpp/releases/download/v0.9.5/';
const audio96 = 'https://github.com/0xShug0/audio.cpp/releases/download/v0.9.6/';
const native = 'https://github.com/unslothai/llama.cpp/releases/download/b12649-mix-c7059d6/';
const source = (url, hash, target = '', filter = 'all') => ({ url, hash, target, filter });
const wheelhost = 'https://files.pythonhosted.org/packages/';
const ffmpeg = wheelhost+'2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl';
const espeak = wheelhost+'9d/ed/a3d872fbad4f3a3f3db0e8c31768ab14e77cd77306de16b8b20b1e1df7ea/espeakng_loader-0.2.4-py3-none-win_amd64.whl';
const sea = 'https://github.com/pnnbao97/sea-g2p/releases/download/v0.10.0/';
const workers = (group, hash) => source(release+'ailab-workers-'+group+'-20261127-x64.zip',hash);
const cudaLibraries = engine => ['cudart64_12.dll','cublas64_12.dll','cublasLt64_12.dll'].map(file => engine + '/cuda-runtime/' + file);
// The Nov 26 portable workers and Nov 27 rebuilds differ only in PE timestamps and checksums.
const definitions = {
  base: { label: '基础运行库', needs: [], minFree: 512,
    fingerprint: ['text/ailab-gguf.exe','15d3705e8ffa79bad159056c29a8d6bd6b910956085a895d03525c5660465e70','c7e86c2f0656ca5da84f6f106b8db4d371be175289b526f59e00111a5dc1fd15'],
    required: ['text/ailab-gguf.exe','text/plm-worker.exe','text/llama.dll','text/llama-server.exe','text/llama-server-impl.dll','text/mtmd.dll','text/ggml.dll','text/ggml-base.dll','text/ggml-cpu-x64.dll','text/ggml-vulkan.dll','diffusion/ffmpeg.exe'], files: [
    source(llama+'llama-b12648-bin-win-vulkan-x64.zip','35670c463d67d33b26058d2ac867346007a44ef19eaf0c0bfd6de08faa535b47','text','text'),
    source(ffmpeg,'02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a','diffusion','ffmpeg'),
    workers('base','833708ba301f798731376409301d983f786923957edbd0277627a6fd197e6dbc')] },
  'image-video': { label: '图片与视频运行库', needs: ['base'], minFree: 800,
    fingerprint: ['diffusion/ailab-image.exe','d64bcbcad89929bf2517b2c00435a6d554c1b44af11a7e016f389d365ee7ad3c','56eef54b444156158e0f28956dd740cef6e0f68e8e2152a3830ca3203df32210'],
    required: ['diffusion/ailab-image.exe','diffusion/sd-cli.exe','diffusion/stable-diffusion.dll','diffusion/0d71f96/sd-cli.exe','diffusion/0d71f96/stable-diffusion.dll','diffusion/0d71f96/vulkan/sd-cli.exe','diffusion/0d71f96/vulkan/ggml-vulkan.dll'], files: [
    source(sd+'sd-master-532d2c1-bin-win-vulkan-x64.zip','3e66222c87ca27074e1fd8ce79706eef17a8aaf39949906aa1bee7e060f22ecc','diffusion','sd'),
    source(sd2+'sd-master-0d71f96-bin-win-cpu-x64.zip','ba3e524523297902c9db1ec0e43e0bcbaf4067b4e053bd899b30c138ff1edda2','diffusion/0d71f96','sd'),
    source(sd2+'sd-master-0d71f96-bin-win-vulkan-x64.zip','0c11ec33b9c1a636f9f72e2bc537384b6c88cf88cd72c97d53f3d834980f27e8','diffusion/0d71f96/vulkan','sd'),
    workers('image-video','7f6d675c62c8443cf5f65fde686393a99111e6b135054e260623ce920a0e31dc')] },
  audio: { label: '音频运行库', needs: ['base'], minFree: 1000,
    fingerprint: ['audio/f5/audiocpp_cli.exe','1c75643190834d4c0241df28feced86f445a5eec14019856af58444e0e05e8b8','b26586125dc2541ce02d9cf3b103d851843cdc48b43944c917dfeed54cd14fbd'],
    required: ['audio/audiocpp_cli.exe','audio/f5/audiocpp_cli.exe','audio/v0.9.6/audiocpp_cli.exe','audio/vulkan/audiocpp_cli.exe','audio/v0.9.6/vulkan/audiocpp_cli.exe','audio/audiocpp_gguf.exe','audio/soxr.dll','audio/sea_g2p.bin','audio/sea_g2p_rs.dll','audio/espeak/espeak-ng.dll','audio/espeak/espeak-ng-data/phontab','audio/model_specs/mira_tts.json'], files: [
    source(audio95+'audio-v0.9.5-bin-windows-x64-cpu-portable.zip','9f470c3b254205d044e91e84d609424f528734cd06b74968ab0e4868a30b839a','audio','audio-base'),
    source(audio95+'audio-v0.9.5-bin-windows-x64-vulkan-portable.zip','6c304c9a1e0cfc18b2d3b208b03d40365fec71d094ee4da4f695b2d9e7de29e8','audio/vulkan','audio'),
    source(audio96+'audio-v0.9.6-bin-windows-x64-cpu-portable.zip','5d2e7fe24dbec0f8267db00ab2c6ccdd24799d916cb7beef3168eb66a53a4077','audio/v0.9.6','audio'),
    source(audio96+'audio-v0.9.6-bin-windows-x64-vulkan-portable.zip','8cfbd5a3a3c655dbb752972e548424d761cbd598ad7ea0903b77dbba0f202c3e','audio/v0.9.6/vulkan','audio'),
    source(espeak,'41f1e08ac9deda2efd1ea9de0b81dab9f5ae3c4b24284f76533d0a7b1dd7abd7','audio/espeak','espeak'),
    source(sea+'sea_g2p.bin','4346e690d0711ebc5231e7a42c5c88aaf6e40377e894b4617c018fd81c6f4096','audio/sea_g2p.bin','file'),
    source(sea+'sea_g2p_rs-windows-x86_64.dll','1daff10cf65304daa56d90814f4f6a54cf6269bf22a684b940a3d7c0bbea25c3','audio/sea_g2p_rs.dll','file'),
    workers('audio','81bf31f4fafe644edc2c675d9a9a7d1e7fccc2c147bb3ee99f8cf1e1f454d334')],
    copies: [['audio/soxr.dll','audio/vulkan/soxr.dll'],['audio/soxr.dll','audio/v0.9.6/vulkan/soxr.dll']] },
  'text-cuda': { label: '语言 CUDA 加速', needs: ['base'], minFree: 4000,
    fingerprint: ['text/native-kernels/cuda/ailab-gguf.exe','63f1715cc1900665c08f10758d79011d4a95a5ad128255282e5c826b840b8114','745419427e4823dd144326d0122272e6228800fe8086fa1f543f2a93c8eac46b'],
    required: ['text/cuda/ailab-gguf.exe','text/cuda/plm-worker.exe','text/cuda/llama-server.exe','text/cuda/ggml-cuda.dll','text/native-kernels/cuda/ailab-gguf.exe','text/native-kernels/cuda/llama-server.exe','text/native-kernels/cuda/ggml-cuda.dll',...cudaLibraries('text')], files: [
    source(llama+'cudart-llama-bin-win-cuda-12.4-x64.zip','8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6','text/cuda-runtime','dll'),
    source(llama+'llama-b12648-bin-win-cuda-12.4-x64.zip','26b82a04c99449d19641e3db392ef2c5a2977ad087bb64c8d74e538b490b9649','text/cuda','text'),
    source(native+'app-b12649-mix-c7059d6-windows-x64-cuda12-older.zip','1bde79ab7182c27f9f7976847011ce7ef7dc9f0ea4ddede7c0ddf5360b070b7e','text/native-kernels/cuda','text'),
    source(release+'GCSA-AiLab-text-native-cuda-20261127-x64.exe','63f1715cc1900665c08f10758d79011d4a95a5ad128255282e5c826b840b8114','text/native-kernels/cuda/ailab-gguf.exe','file')],
    copies: [['text/ailab-gguf.exe','text/cuda/ailab-gguf.exe'],['text/plm-worker.exe','text/cuda/plm-worker.exe']] },
  'image-video-cuda': { label: '图片视频 CUDA 加速', needs: ['base','image-video'], minFree: 3500,
    fingerprint: ['diffusion/cuda/sd-cli.exe','add0215fec1e081d81c212617aa32735cc5f19d9a593223109784cd309ad6d46'],
    required: ['diffusion/cuda/ailab-image.exe','diffusion/cuda/sd-cli.exe','diffusion/cuda/ggml-cuda.dll','diffusion/0d71f96/cuda/sd-cli.exe','diffusion/0d71f96/cuda/ggml-cuda.dll',...cudaLibraries('diffusion')], files: [
    source(sd+'cudart-sd-bin-win-cu12-x64.zip','fe20366827d357c00797eebb58244dddab7fd9a348d70090c3871004c320f38d','diffusion/cuda-runtime','dll'),
    source(sd+'sd-master-532d2c1-bin-win-cuda12-x64.zip','b087219145a382cc1b1e826318289e1f672b9bb6965977734ef0deb85fe2d03a','diffusion/cuda','sd'),
    source(sd2+'sd-master-0d71f96-bin-win-cuda12-x64.zip','b2db431b50e5c5b87c25b6b52006627eae866193634112f68c57daf7c1c8cb0d','diffusion/0d71f96/cuda','sd')],
    copies: [['diffusion/ailab-image.exe','diffusion/cuda/ailab-image.exe']] },
  'audio-cuda': { label: '音频 CUDA 加速', needs: ['base','audio'], minFree: 4500,
    fingerprint: ['audio/cuda/audiocpp_cli.exe','d4382b3646b812b10ef8c0523277cc1136efca2843d979ebc5c9f608a3c14752'],
    required: ['audio/cuda/audiocpp_cli.exe','audio/cuda/ggml-cuda.dll','audio/v0.9.6/cuda/audiocpp_cli.exe','audio/v0.9.6/cuda/ggml-cuda.dll','audio/v0.9.6/cuda/soxr.dll','audio/cuda-runtime/cufft64_11.dll',...cudaLibraries('audio')], files: [
    source(audio96+'audio-v0.9.6-cudart-windows-x64-cuda12.4.zip','283fbf6927021b8e73cd22e6c3c300c2d12adb66361bc1d392401e1ca2759297','audio/cuda-runtime','dll'),
    source(audio95+'audio-v0.9.5-bin-windows-x64-cuda12.4.zip','81f38a0a62935bdf4b2605541a21d50223b2e12b661887031705dd8a369f844b','audio/cuda','audio'),
    source(audio96+'audio-v0.9.6-bin-windows-x64-cuda12.4.zip','ff7783e29b02e9006fa4304b9cdeffa030cd5a184998090f769f0a1d221b2698','audio/v0.9.6/cuda','audio')],
    copies: [['audio/soxr.dll','audio/cuda/soxr.dll'],['audio/soxr.dll','audio/v0.9.6/cuda/soxr.dll']] },
};

function allowed(url) {
  const u = new URL(url);
  return u.protocol === 'https:' && !u.username && !u.password &&
    (u.hostname === 'github.com' || u.hostname === 'files.pythonhosted.org' || u.hostname.endsWith('.githubusercontent.com'));
}
async function download(file, item, signal, progress) {
  let url = item.url, response;
  for (let i=0; i<8; i++) {
    if (!allowed(url)) throw Error('运行库下载地址不在允许的来源中。');
    response = await fetch(url,{redirect:'manual',signal,headers:{'User-Agent':'GCSA-AiLab'}});
    if ([301,302,303,307,308].includes(response.status)) {
      const location=response.headers.get('location'); await response.body?.cancel();
      if (!location) throw Error('运行库下载重定向无效。');
      url=new URL(location,url).href; continue;
    }
    if (!response.ok || !response.body) throw Error('运行库下载失败（HTTP '+response.status+'）。');
    break;
  }
  if (!response?.ok || !response.body) throw Error('运行库重定向次数过多。');
  const total=Number(response.headers.get('content-length')) || 0;
  if (total > 2_000_000_000) throw Error('运行库文件超过允许大小。');
  let received=0; const hash=createHash('sha256');
  const meter=new Transform({transform(chunk, _enc, done) {
    received+=chunk.length;
    if (received > 2_000_000_000) return done(Error('运行库文件超过允许大小。'));
    hash.update(chunk); progress(received,total); done(null,chunk);
  }});
  await pipeline(Readable.fromWeb(response.body),meter,fs.createWriteStream(file,{flags:'wx'}),{signal});
  if (hash.digest('hex') !== item.hash) throw Error('运行库摘要校验失败，请重试。');
}

function tar(args, signal, collect=false) {
  return new Promise((resolve,reject) => {
    const exe=path.join(process.env.SystemRoot || 'C:\\Windows','System32','tar.exe');
    const child=spawn(exe,args,{windowsHide:true,stdio:['ignore',collect?'pipe':'ignore','pipe']});
    let output='', error='';
    const stop=()=>child.kill(); signal.addEventListener('abort',stop,{once:true});
    child.stdout?.on('data',b=>{ output+=b.toString(); if (output.length>4_000_000) child.kill(); });
    child.stderr.on('data',b=>{ error=(error+b.toString()).slice(-1000); });
    child.on('error',reject);
    child.on('close',code=>{ signal.removeEventListener('abort',stop); if (signal.aborted) reject(Error('下载已取消。'));
      else if (code!==0) reject(Error('解压运行库失败：'+error)); else resolve(output); });
  });
}
function installedName(name, filter) {
  const base = path.posix.basename(name);
  if (filter === 'all') return name;
  if (filter === 'ffmpeg') {
    if (name.startsWith('imageio_ffmpeg/binaries/') && base.endsWith('.exe')) return 'ffmpeg.exe';
    if (/license/i.test(base)) return 'ffmpeg-' + base;
    return null;
  }
  if (filter === 'espeak') {
    const member = name.replace(/^espeakng_loader\//, '');
    return member === 'espeak-ng.dll' || member.startsWith('espeak-ng-data/') ? member : null;
  }
  if (filter === 'audio-base') {
    return /\.(dll)$/i.test(base) || /^(audiocpp_(cli|gguf)\.exe|LICENSE|(kokoro_tts|mira_tts|zonos[23]|minimax_h3)\.json)$/.test(base) ? name : null;
  }
  if (base !== name) return null;
  if (/^LICENSE/i.test(base)) return name;
  if (filter === 'text') {
    return /^(ggml(-cpu-[\w-]+|-vulkan|-cuda|-base)?\.dll|llama(-server-impl|-common)?\.dll|libomp\.dll|mtmd\.dll|llama-server\.exe|BUILD_INFO\.txt|THIRD_PARTY_LICENSES\.txt|UNSLOTH_PREBUILT_INFO\.json)$/i.test(name) ? name : null;
  }
  if (/\.(dll|txt)$/i.test(name)) return name;
  return (filter === 'sd' && name === 'sd-cli.exe') || (filter === 'audio' && name === 'audiocpp_cli.exe') ? name : null;
}

async function extract(archive, target, filter, signal) {
  const listing = await tar(['-tf', archive], signal, true);
  const selected = new Map();
  for (const member of listing.split(/\r?\n/).filter(Boolean)) {
    const name = member.replace(/\\/g, '/');
    if (name.endsWith('/')) continue;
    if (name.split('/').some(part => !part || part === '.' || part === '..' || /[:*?"<>|\x00-\x1f]|[. ]$/.test(part)))
      throw Error('运行库压缩包路径无效。');
    const dest = installedName(name, filter);
    if (dest) selected.set(member, dest);
  }
  if (!selected.size) throw Error('压缩包缺少所选组件。');
  const work = await fsp.mkdtemp(path.join(path.dirname(archive), 'extract-'));
  try {
    const members = path.join(work, 'members.txt'), raw = path.join(work,'raw');
    await fsp.mkdir(raw);
    await fsp.writeFile(members, [...selected.keys()].join('\n') + '\n');
    await tar(['-xf', archive, '-C', raw, '-T', members], signal);
    for (const [member, name] of selected) {
      signal.throwIfAborted();
      const src = path.join(raw, member), dst = path.join(target, name);
      if (!(await fsp.lstat(src)).isFile() || !(await fsp.realpath(src)).startsWith((await fsp.realpath(raw)) + path.sep))
        throw Error('运行库压缩包成员无效。');
      await fsp.mkdir(path.dirname(dst), {recursive:true});
      await fsp.rename(src, dst);
    }
  } finally { await fsp.rm(work, {recursive:true,force:true}); }
}

// Only expose verified, complete files. If activation fails, restore any previous files.
async function activate(stage, root, work, id) {
  const installed = [], saved = [], entries = [];
  async function list(directory) {
    for (const entry of await fsp.readdir(directory,{withFileTypes:true})) {
      const file = path.join(directory,entry.name);
      if (entry.isDirectory()) await list(file);
      else entries.push(path.relative(stage,file));
    }
  }
  await list(stage);
  try {
    for (const relative of entries) {
      const dest = path.join(root,relative);
      await fsp.mkdir(path.dirname(dest),{recursive:true});
      if (fs.existsSync(dest)) {
        const backup = path.join(work,'backup',relative);
        await fsp.mkdir(path.dirname(backup),{recursive:true});
        await fsp.rename(dest,backup);
        saved.push([backup,dest]);
      }
      await fsp.rename(path.join(stage,relative),dest);
      installed.push(dest);
    }
    const receipt = path.join(work,'receipt');
    await fsp.writeFile(receipt,JSON.stringify(entries));
    await fsp.rename(receipt,path.join(root,'.installed-'+id+'-20261127'));
  } catch (error) {
    for (const dest of installed.reverse()) await fsp.unlink(dest);
    for (const [backup,dest] of saved) await fsp.rename(backup,dest);
    throw error;
  }
}

class RuntimeInstaller {
  constructor(root, options={}) {
    this.root = root;
    this.fetchFile = options.fetchFile || download;
    this.extract = options.extract || extract;
    this.state = { busy: false };
    this.fingerprints = new Map();
  }
  async inspect(id) {
    const def = definitions[id];
    const stats = await Promise.all(def.required.map(file => fsp.stat(path.join(this.root, file)).catch(error => {
      if (error.code === 'ENOENT' || error.code === 'ENOTDIR') return null;
      throw error;
    })));
    const missing = def.required.filter((_, i) => !stats[i]?.isFile() || !stats[i].size);
    if (missing.length) return { installed: false, detail: missing.length === stats.length ? '当前目录未发现此组件' : '缺少文件 · ' + missing.join('、') };
    const receipt = await fsp.stat(path.join(this.root, '.installed-' + id + '-20261127')).catch(() => null);
    if (receipt?.isFile()) return { installed: true, detail: '已配置' };
    // Portable packages predate receipts. Match the build's worker as well as its required files.
    const [file, ...expected] = def.fingerprint;
    const stat = stats[def.required.indexOf(file)];
    const stamp = [stat.size, stat.mtimeMs, stat.ctimeMs].join('/');
    let entry = this.fingerprints.get(id);
    if (entry?.stamp !== stamp) {
      const hash = createHash('sha256');
      for await (const chunk of fs.createReadStream(path.join(this.root, file))) hash.update(chunk);
      entry = { stamp, matches: expected.includes(hash.digest('hex')) };
      this.fingerprints.set(id, entry);
    }
    return entry.matches ? { installed: true, detail: '已识别本机运行库' }
      : { installed: false, detail: '执行器版本与当前 AiLab 不匹配 · ' + file };
  }
  async installed(id) { return (await this.inspect(id)).installed; }
  async status() {
    const entries = await Promise.all(Object.entries(definitions).map(async ([id, def]) => {
      try { return { id, label: def.label, ...await this.inspect(id) }; }
      catch (error) { return { id, label: def.label, installed: false, detail: '读取组件失败 · ' + (error.code || error.message) }; }
    }));
    const components = entries.map(entry => {
      const needed = definitions[entry.id].needs.filter(id => !entries.find(item => item.id === id).installed);
      if (!entry.installed || !needed.length) return entry;
      return { ...entry, installed: false, detail: entry.detail + '，还需' + needed.map(id => definitions[id].label).join('、') };
    });
    return { ...this.state, components };
  }
  start(id) {
    if (this.closed) throw Error('程序正在退出。');
    if (typeof id !== 'string' || !Object.hasOwn(definitions,id)) throw Error('未知的运行库组件。');
    if (this.state.busy) throw Error('已有运行库正在准备。');
    this.controller=new AbortController(); this.state={busy:true,id,phase:'准备下载'};
    this.pending=this.run(id,this.controller.signal).then(
      () => ({...this.state,busy:false,id,phase:'准备完成'}),
      error => ({...this.state,busy:false,id,error:this.controller.signal.aborted ? '已取消，可以重新下载。' : error.message || String(error)})
    ).then(result => { this.state=result; return result; });
  }
  async ensure(id) {
    if (typeof id !== 'string' || !Object.hasOwn(definitions,id)) throw Error('未知的运行库组件。');
    const keys = [...definitions[id].needs, id];
    for (;;) {
      if ((await Promise.all(keys.map(key => this.installed(key)))).every(Boolean)) return;
      if (!this.state.busy) this.start(id);
      const same = this.state.id === id;
      const result = await this.pending;
      if (same && result.error) throw Error(result.error);
    }
  }
  cancel() { this.controller?.abort(); }
  close() {
    this.closed = true;
    this.cancel();
    return this.pending;
  }
  async run(id, signal) {
    await fsp.mkdir(this.root,{recursive:true});
    const files = [];
    for (const key of [...definitions[id].needs, id]) {
      if (!(await this.installed(key))) {
        files.push(...definitions[key].files.map(item => ({
          component: definitions[key].label,
          name: decodeURIComponent(new URL(item.url).pathname.split('/').pop()),
          status: '等待下载',
          received: 0,
          total: 0,
        })));
      }
    }
    this.state.files = files;
    let fileIndex = 0;
    for (const key of [...definitions[id].needs,id]) {
      if (await this.installed(key)) continue;
      const def=definitions[key];
      const volume=await fsp.statfs(this.root);
      if (volume.bavail*volume.bsize < def.minFree*1024**2) throw Error(`${def.label}需要至少 ${def.minFree} MiB 可用磁盘空间。`);
      const temp=await fsp.mkdtemp(path.join(this.root,'.install-'));
      const stage=path.join(temp,'staged');
      await fsp.mkdir(stage);
      try {
        for (let i=0;i<def.files.length;i++) {
          signal.throwIfAborted(); const item=def.files[i], archive=path.join(temp,'download');
          const detail = files[fileIndex++];
          detail.status = '下载中';
          Object.assign(this.state,{component:key,phase:`下载 ${def.label}（${i+1}/${def.files.length}）`,received:0,total:0});
          await this.fetchFile(archive,item,signal,(received,total)=>{this.state.received=received;this.state.total=total;detail.received=received;detail.total=total;});
          detail.status = '正在配置';
          this.state.phase='正在解压并配置 '+def.label;
          const target=path.join(stage,item.target);
          if (item.filter==='file') { await fsp.mkdir(path.dirname(target),{recursive:true}); await fsp.copyFile(archive,target); }
          else { await fsp.mkdir(target,{recursive:true}); await this.extract(archive,target,item.filter,signal); }
          await fsp.unlink(archive);
          detail.status = '已下载';
        }
        for (const [from,to] of def.copies || []) { await fsp.mkdir(path.dirname(path.join(stage,to)),{recursive:true}); await fsp.copyFile(fs.existsSync(path.join(stage,from)) ? path.join(stage,from) : path.join(this.root,from),path.join(stage,to)); }
        await Promise.all(def.required.map(f=>fsp.access(path.join(stage,f))));
        signal.throwIfAborted();
        await activate(stage,this.root,temp,key);
      } finally { await fsp.rm(temp,{recursive:true,force:true}); }
    }
  }
}
module.exports={RuntimeInstaller,definitions,allowed,download,extract};
