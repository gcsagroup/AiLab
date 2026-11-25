'use strict';
const fs = require('node:fs'),
  fsp = fs.promises,
  path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { bundle, localExtras, materialPrompt, componentPath, audioExtras } = require('./gguf-bundle.cjs');
const generation = require('./generation-packages.cjs');
const { inputModel, useService, structuredInput } = require('./llama-service.cjs');
const { metadata } = require('./gguf-metadata.cjs');
const { devices, parameters, textWorker, render, bins, prepareCompactText } = require('./trial-worker.cjs');
const { atomicJson, contained, verify } = require('./downloads.cjs');
const { fail } = require('./hub.cjs');
const { workflowEligible } = require('./workflows.cjs');
const { LocalEnvironment } = require('./environment.cjs');
const { performance } = require('node:perf_hooks');
const { waveSeconds } = require('./trial-timing.cjs');
const id = (prefix) => prefix + '-' + randomUUID().replaceAll('-', '');
const digest = (o) => createHash('sha256').update(JSON.stringify(o)).digest('hex');
const page = (items) => ({ items, next_cursor: null });
const now = () => new Date().toISOString();
const active = new Set(['queued', 'running', 'cancelling']);
function modelExtension(file) {
  const extension=path.extname(file).toLowerCase();
  return extension==='.gguf_file' ? '.gguf' : extension;
}
const boundary = {
  scope_semantics: 'loader_policy_not_os_permissions',
  process: 'separate_process',
  os_sandbox: false,
  filesystem: 'current_user_permissions',
  network: 'offline_loader_options_not_os_block',
  credentials: 'environment_allowlist_not_filesystem_denial',
  custom_code: 'not_supported',
};
async function hash(file) {
  const h = createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) h.update(chunk);
  return h.digest('hex');
}
function localView(row) {
  if (row.generation_package) {
    try {
      const ref=generation.stored(row);
      return {...row,pipeline:ref.info.pipeline,execution_available:[ref.file,...Object.values(ref.extra)].every(f=>fs.existsSync(f))};
    } catch { return {...row,execution_available:false}; }
  }
  if (!row.component_digests && row.kind !== 'video') return row;
  try {
    const ref = bundle([row.path, ...Object.values(localExtras(row)).filter(f => /\.gguf$/i.test(f))]);
    if (ref?.info.kind === row.kind)
      return { ...row, pipeline: ref.info.pipeline, supports_media: !!ref.info.multimodal };
  } catch {}
  return { ...row, execution_available: false };
}
function manifest(base, extras) {
  const entries = Object.entries(extras).sort(([a], [b]) => a.localeCompare(b));
  if (entries.length === 0) return base;
  if (entries.length === 1 && entries[0][0] === 'motion') return digest([base, entries[0][1]]);
  return digest([base, entries]);
}
function validateWav(bytes) {
  let fmt, dataSize=0;
  for (let offset=12;offset+8<=bytes.length;) {
    const length=bytes.readUInt32LE(offset+4), start=offset+8, end=start+length;
    if(end>bytes.length)throw Error('WAV 数据不完整。');
    const tag=bytes.toString('ascii',offset,offset+4);
    if(tag==='fmt ' && length>=16) fmt={type:bytes.readUInt16LE(start),channels:bytes.readUInt16LE(start+2),rate:bytes.readUInt32LE(start+4),align:bytes.readUInt16LE(start+12),bits:bytes.readUInt16LE(start+14)};
    if(tag==='data')dataSize+=length;
    offset=end+(length%2);
  }
  if(!fmt || !dataSize || ![1,2].includes(fmt.channels) || fmt.rate<8000 || fmt.rate>192000 ||
    !(fmt.type===1 && [8,16,24,32].includes(fmt.bits) || fmt.type===3 && fmt.bits===32) ||
    fmt.align!==fmt.channels*fmt.bits/8 || dataSize%fmt.align)throw Error('请选择有效的单声道或双声道 PCM WAV。');
}
function projectKey(p) {
  if (!/^project-[a-zA-Z0-9-]+$/.test(p || '')) throw Error('项目编号无效。');
  return p;
}
class Trials {
  constructor(dir, downloads) {
    this.dir = dir;
    this.downloads = downloads;
    this.environment = new LocalEnvironment(downloads.modelDir);
    this.rows = new Map();
    this.plans = new Map();
    this.queue = [];
    this.queuedSince = new Map();
    this.current = null;
    this.closing = false;
    fs.mkdirSync(dir, { recursive: true });
    for (const name of fs
      .readdirSync(dir)
      .filter((n) => /^(attempt|work|local|material|workflow)-[a-f0-9]{32}\.json$/.test(n))) {
      try {
        const row = JSON.parse(fs.readFileSync(path.join(dir, name)));
        if (row.id + '.json' !== name) continue;
        if (row.id.startsWith('attempt-') && active.has(row.state)) {
          row.state = 'failed';
          row.error = { message: '上次应用退出时运行中断。' };
          row.allowed_actions = [];
          this.save(row);
        }
        this.rows.set(row.id, row);
      } catch {}
    }
  }
  save(row) {
    atomicJson(path.join(this.dir, row.id + '.json'), row);
    this.rows.set(row.id, row);
    return row;
  }
  list(prefix, project) {
    return [...this.rows.values()]
      .filter((x) => x.id.startsWith(prefix + '-') && (!project || x.project_id === project))
      .reverse()
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  }
  weight(job) {
    const files = job.files.filter(
      (f) => f.path.toLowerCase().endsWith('.gguf') && !/^(?:mmproj|.*\/mmproj)/i.test(f.path),
    );
    const firsts = files.filter(
      (f) => !/-\d{5}-of-\d{5}\.gguf$/i.test(f.path) || /-00001-of-\d{5}\.gguf$/i.test(f.path),
    );
    const first = firsts.find((f) => f.path === job.filename) || (firsts.length === 1 ? firsts[0] : null);
    if (!first) return null;
    const shard = /^(.*)-(\d{5})-of-(\d{5})\.gguf$/i.exec(first.path);
    if (shard) {
      const members = new Set(files.map((f) => f.path.toLowerCase()));
      const count = Number(shard[3]);
      if (shard[2] !== '00001' || !count || count > 10000) return null;
      for (let i = 1; i <= count; i++)
        if (
          !members.has(
            (shard[1] + '-' + String(i).padStart(5, '0') + '-of-' + shard[3] + '.gguf').toLowerCase(),
          )
        )
          return null;
    }
    return contained(path.join(this.downloads.modelDir, job.modelId), first.path);
  }
  downloadedWeights(job) {
    const pack=generation.downloaded(job,path.join(this.downloads.modelDir,job.modelId));
    if (pack !== undefined) return pack || {};
    const paths = job.files
      .filter((f) => /\.gguf(?:_file)?$/i.test(f.path) || require('./cogvlm-layout.cjs').publishedProjector(job.repoId,f))
      .map((f) => contained(path.join(this.downloads.modelDir, job.modelId), f.path));
    if (job.derivedComponents) {
      const h3 = require('./h3-weights.cjs');
      for (const role of Object.keys(h3.conversionTypes(job.repoId, job.filename))) {
        if (!job.derivedComponents[role]) break;
        const type = job.derivedTypes?.[role] ?? (role === 'encoder' ? 'q4_0' : undefined);
        paths.push(h3.derivedFile(this.downloads.dataDir, role, type));
      }
    }
    const file = this.weight(job);
    const members = paths.filter(p => !/-\d{5}-of-\d{5}\.gguf$/i.test(p) || p === file);
    if (paths.some(p=>/-\d{5}-of-\d{5}\.gguf$/i.test(p)) && !file) return {};
    let complete = bundle(paths);
    if (!complete) {
      if (!file || members.some(p => ['draft','projector','ple_table','ocr-base','speech-base'].includes(metadata(p).component))) return {};
      const info = metadata(file);
      if (info.requiresPleTable && !info.hasPleTable) return {};
      complete = {file, info, extra: audioExtras(file, info.audioFamily)};
    }
    const assets = Object.values(complete.extra).filter(f => !/\.gguf$/i.test(f));
    if (assets.length) {
      const dir = path.join(this.downloads.modelDir, job.modelId);
      const registered = new Set(job.files.map(f => contained(dir, f.path)));
      if (assets.some(f => !registered.has(f))) return {};
    }
    return complete;
  }
  describe(job) {
    const m = this.downloads.model(job);
    try {
      const { info } = this.downloadedWeights(job);
      return {
        ...m,
        modality: info?.kind || m.modality,
        pipeline: info?.pipeline,
        supports_media: !!info?.multimodal,
        execution_available: !!info?.kind,
        workflow_eligible: !!info && workflowEligible(info),
        supports_thinking: !!info?.thinking,
        default_engine: info?.kind ? 'ailab-gguf' : undefined,
      };
    } catch {
      return { ...m, execution_available: false };
    }
  }
  resolve(modelId, project) {
    const local = this.rows.get(modelId);
    if (local?.id.startsWith('local-') && local.project_id === project) {
      if (!localView(local).execution_available)
        throw Error(local.kind === 'video' ? '请导入完整的视频模型组合（AnimateDiff、MiniMax-H3 或 Wan 2.1）。' : '请重新导入该模型及其配套组件。');
      const extra = localExtras(local),
        ref = local.generation_package ? generation.stored(local) : bundle([local.path, ...Object.values(extra).filter(f => /\.gguf$/i.test(f))]);
      if (!ref || ref.info.kind !== local.kind ||
          Object.keys(ref.extra).some(role => ref.extra[role] !== extra[role]))
        throw Error('已登记的 GGUF 主模型和配套组件不匹配。');
      return {
        ...ref,
        motion:extra.motion,
        model: local,
        verify: async () => {
          const hashes = {};
          for (const [role, file] of Object.entries(extra)) hashes[role] = await hash(file);
          if (manifest(await hash(local.path), hashes) !== local.manifest_digest)
            throw Error('导入的模型摘要已变化。');
        },
      };
    }
    const job = this.downloads
      .records(project)
      .find((j) => j.modelId === modelId && j.registeredAt && j.status === 'completed');
    if (!job) throw Error('请先将模型登记到当前项目。');
    const { file, extra = {}, info } = this.downloadedWeights(job);
    if (!file) throw Error('请在准备模型时选择一份 GGUF 权重或一组分片。');
    return {
      model: this.describe(job),
      file,
      extra,
      motion:extra.motion,
      info,
      verify: async () => {
        for (const [role, member] of Object.entries(extra)) {
          if (job.derivedComponents?.[role] && (await hash(member)) !== job.derivedComponents[role])
            throw Error('GGUF 组件摘要已变化。');
        }
        const dir = path.join(this.downloads.modelDir, job.modelId);
        const resources = new Set([file, ...Object.values(extra)]);
        for (const item of job.files.filter(f => /\.gguf$/i.test(f.path) || resources.has(contained(dir, f.path)))) {
          const target = contained(dir, item.path);
          if ((await fsp.realpath(target)).toLowerCase() !== target.toLowerCase())
            throw Error('权重路径已变化。');
          await verify(target, item);
        }
      },
    };
  }
  remember(key, item) {
    if (this.plans.size > 128) this.plans.delete(this.plans.keys().next().value);
    this.plans.set(key, item);
  }
  async inspectImport(type, b) {
    projectKey(b.project_id);
    if (typeof b.path !== 'string' || !path.isAbsolute(b.path)) throw Error('请输入本机绝对路径。');
    let file = await fsp.realpath(b.path);
    let group,
      extra = {};
    if (type === 'models') {
      const reapFiles=require('./qwen-reap.cjs').localFiles(file);
      group=reapFiles ? bundle(reapFiles) : generation.localPackage(file);
    }
    if (group) {
      file = group.file;
      extra = group.extra;
    } else if ((await fsp.stat(file)).isDirectory() && type === 'models') {
      const candidates = (await fsp.readdir(file)).filter((n) => /\.gguf(?:_file)?$/i.test(n) || n===require('./cogvlm-layout.cjs').projectorName);
      if (candidates.length === 1) file = path.join(file, candidates[0]);
      else {
        group = bundle(candidates.map((name) => path.join(file, name)));
        if (!group) throw Error('GGUF 模型组件缺失、重复或架构不匹配。');
        file = group.file;
        extra = group.extra;
      }
    }
    const stat = await fsp.stat(file);
    if (!stat.isFile()) throw Error('请选择普通文件。');
    let kind,
      info = {};
    if (type === 'models') {
      if (!group?.info.packageId && !/\.gguf(?:_file)?$/i.test(file)) throw Error('本机试用只接收 GGUF 模型。');
      info = group?.info || metadata(file);
      if (!group && require('./qwen-reap.cjs').requiresBundle(info)) throw require('./qwen-reap.cjs').incomplete();
      if (!group && info.requiresPleTable && !info.hasPleTable)
        throw Error('这份主模型需要配套的 PLE 词嵌入查找表。请选择包含主权重和查找表的发布目录。');
      if (!group && info.audioFamily) extra = audioExtras(file, info.audioFamily);
      kind = info.kind;
      if (info.motion && !extra.motion)
        throw Error('运动模块需要配套 SD 1.5 基座，请导入包含两份 GGUF 的目录。');
      if (!kind) {
        if (info.component === 'anima') throw Error('Anima 需要 Qwen3-0.6B-Base 文本编码器及 Qwen Image VAE，请导入三份 GGUF 所在的目录。');
        if (info.component === 'iris') throw Error('Iris-3B 需要 Qwen3-VL-4B 文本编码器，请导入两份 GGUF 所在的目录。');
        if (info.component === 'wan21-t2v' || info.component === 'wan_vae')
          throw Error('Wan 2.1 T2V 1.3B 需要主模型、UMT5-XXL 编码器和 Wan 2.1 VAE，请导入三份 GGUF 所在的目录。');
        if (info.component==='ocr-base') throw Error('DeepSeek OCR 需要匹配的视觉投影器，请导入完整发布目录。');
        if (['projector','speech-base','draft'].includes(info.component))
          throw Error('请导入含配套主模型与投影器、语音编解码器或推测头的目录。');
        if (info.arch==='gptj') throw Error('GPT-J 需要词表和分离的 Q、K、V 投影，请核对主模型文件。');
        if (info.missingVocabulary) throw Error('已识别 '+info.arch+' 架构，但这个 GGUF 缺少词表。请选择完整主模型；分片模型请导入全部分片所在的目录。');
        throw Error('尚未接入该 GGUF 架构。');
      }
      if (!group && /-\d{5}-of-\d{5}\.gguf(?:_file)?$/i.test(file)) throw Error('请导入含完整分片的目录。');
    } else {
      if (stat.size > 32 * 1024 * 1024) throw Error('素材超过 32 MiB。');
      const buf = await fsp.readFile(file);
      if (
        buf.length >= 44 &&
        buf.toString('ascii', 0, 4) === 'RIFF' &&
        buf.toString('ascii', 8, 12) === 'WAVE'
      ) {
        validateWav(buf);
        kind = 'audio';
      } else {
        if (
          buf.length < 33 ||
          buf.subarray(0, 8).toString('hex') !== '89504e470d0a1a0a' ||
          buf.toString('ascii', 12, 16) !== 'IHDR' ||
          buf[24] !== 8 ||
          ![2, 6].includes(buf[25]) ||
          buf[28] !== 0
        )
          throw Error('需要非隔行的 8-bit RGB/RGBA PNG。');
        info = { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
        if (!info.width || !info.height || info.width * info.height > 32000000)
          throw Error('素材尺寸超出范围。');
        kind = 'image';
      }
    }
    const baseSha = await hash(file);
    const hashes = {};
    let total = stat.size;
    for (const [role, member] of Object.entries(extra)) {
      hashes[role] = await hash(member);
      total += (await fsp.stat(member)).size;
    }
    if (info.packageId) await generation.checkHashes(group,baseSha,hashes);
    if (info.reap25) require('./qwen-reap.cjs').verifyLocal(baseSha,hashes);
    const sha = manifest(baseSha, hashes),
      key = id('plan');
    const familyName = ['tts','gen'].includes(info.audioTask) ? info.audioFamily : undefined;
    const name = b.name || (extra.motion ? 'SD 1.5 + AnimateDiff GGUF' :
      familyName || info.pipeline || info.name || path.basename(file));
    let compactImport=false;
    const warnings=[];
    if (process.platform==='win32' && type==='models' && kind==='text' &&
        !Object.keys(extra).length && info.compactTextBytes) {
      const volume=await fsp.statfs(this.dir);
      const free=volume.bavail*volume.bsize, margin=64*1024**2;
      if (free<total+margin) {
        if (free<info.compactTextBytes+margin) throw Error('模型存储目录的磁盘空间不足以保存低内存 GGUF。');
        compactImport=true;
        warnings.push({code:'COMPACT_CPU_IMPORT',message:'原精度副本超出可用磁盘空间。确认导入后将生成约 '+
          (info.compactTextBytes/1024**3).toFixed(2)+' GiB 的混合 '+info.compactTextType.toUpperCase()+' 副本。'});
      }
    }
    this.remember(key, {
      file,
      compactImport,
      sha,
      baseSha,
      extra,
      hashes,
      kind,
      info,
      project: b.project_id,
      name,
      type,
    });
    return {
      id: key,
      plan_id: key,
      can_import: true,
      manifest_digest: sha,
      name,
      format: type === 'models' ? modelExtension(file).slice(1).toUpperCase() : kind === 'audio' ? 'WAV' : 'PNG',
      file_count: 1 + Object.keys(extra).length,
      total_bytes: total,
      blocking: [],
      warnings,
      trust_class: 'restricted_weights',
      loader: 'ailab.gguf',
      execution_boundary: boundary,
    };
  }
  async confirmImport(type, b) {
    const p = this.plans.get(b.plan_id);
    if (!p || p.type !== type || p.sha !== b.manifest_digest) throw Error('请重新检查所选文件。');
    if (p.result) return p.result;
    if (p.copying) return p.copying;
    const save = async () => {
      const key = id(type === 'models' ? 'local' : 'material'),
        dir = path.join(this.dir, key);
      await fsp.mkdir(dir);
      const file = path.join(
        dir,
        type === 'models' ? 'model'+(/-00001-of-\d{5}(?=\.gguf(?:_file)?$)/i.exec(p.file)?.[0] || '')+modelExtension(p.file) : p.kind === 'audio' ? 'source.wav' : 'source.png',
      );
      try {
        const members = [[p.file, file, p.baseSha]];
        for (const [role, member] of Object.entries(p.extra))
          members.push([member, role.startsWith('shard_') ? file.replace('-00001-of-', '-'+role.slice(6)+'-of-') : componentPath(dir, role), p.hashes[role]]);
        let bytes = 0, storedDigest=p.sha;
        for (const [source, dest, expected] of members) {
          await fsp.mkdir(path.dirname(dest), { recursive: true });
          if (p.compactImport) {
            await prepareCompactText(source,dest,undefined,expected);
            storedDigest=await hash(dest);
          } else {
            await fsp.copyFile(source, dest);
            if ((await hash(dest)) !== expected) throw Error('复制期间文件已变化。');
          }
          bytes += (await fsp.stat(dest)).size;
        }
        return this.save({
          id: key,
          project_id: p.project,
          name: p.name,
          kind: p.kind,
          modality: p.kind,
          format: type === 'models' ? path.extname(file).slice(1).toLowerCase() : p.kind === 'audio' ? 'wav' : 'png',
          status: 'ready',
          execution_available: type === 'models',
          supports_thinking: p.info.thinking || false,
          default_engine: 'ailab-gguf',
          path: file,
          version_id: storedDigest,
          manifest_digest: storedDigest,
          ...(p.compactImport ? {source_manifest_digest:p.sha,weight_conversion:'mixed_'+p.info.compactTextType} : {}),
          total_bytes: bytes,
          component_digests: Object.keys(p.hashes).length ? p.hashes : undefined,
          motion_digest: p.hashes.motion,
          generation_package: p.info.packageId,
          pipeline: p.info.pipeline,
          supports_media: !!p.info.multimodal,
          media_type:
            type === 'models' ? 'application/octet-stream' : p.kind === 'audio' ? 'audio/wav' : 'image/png',
          width: p.info.width,
          height: p.info.height,
        });
      } catch (error) {
        await fsp.rm(dir, { recursive: true, force: true });
        throw error;
      }
    };
    p.copying = save();
    try {
      return (p.result = await p.copying);
    } finally {
      p.copying = null;
    }
  }
  async check(task) {
    const key = id('preflight'),
      draft = task.draft,
      blocking = [];
    let effective = {},
      ref,
      material;
    try {
      projectKey(task.project_id);
      if (task.operation !== 'generate' || draft.operation !== 'generate' || draft.kind !== task.kind)
        throw Error('此次接入的是四类模型的运行 / 试用。');
      ref = this.resolve(draft.model_id, task.project_id);
      if (ref.info.kind !== task.kind) throw Error('所选 GGUF 架构与当前试用类别不匹配。');
      effective = parameters(draft, ref.info);
      const hibiki = ref.info.pipeline === 'llama-hibiki';
      const engine = ref.info.pipeline==='llama-vocoder' ? bins.text : (hibiki || ref.info.pipeline==='llama-tts') ? bins.llamaService : bins[task.kind];
      await fsp.access(engine);
      const input = materialPrompt(draft.input);
      const audioInput = hibiki || ['asr', 'vad'].includes(ref.info.audioTask);
      if (ref.info.pipeline==='llama-ocr' && !input.reference)
        throw Error('DeepSeek OCR 需要包含文字的 PNG 图片，请拖入图片或在首行填写 @素材 加素材编号。');
      const upscale = ['esrgan-x4', 'mosr-x4'].includes(ref.info.pipeline);
      if (upscale || ['iris','anima','wan21-t2v','diffusion-image','diffusion-video'].includes(ref.info.pipeline)) await fsp.access(path.join(path.dirname(bins.image), 'sd-cli.exe'));
      if (task.kind === 'video' || ref.info.audioTask || hibiki) await fsp.access(bins.ffmpeg);
      const recipe = generation.recipe(ref.info.packageId || ref.info.nativeRecipe,!!ref.info.nativeRecipe);
      if (recipe?.compactAudio && (await fsp.stat(ref.file)).size===recipe.files[0].size) {
        await fsp.access(bins.text);
        effective.audio_weight_conversion='q8_0_to_mixed_q4_k';
      }
      if (recipe?.kind==='audio') await fsp.access(require('./generation-runtime.cjs').audioEngine(bins.audio,recipe));
      if (recipe?.diffusionVersion) await fsp.access(require('./generation-runtime.cjs').diffusionEngine(bins.image,recipe));
      if (recipe?.imageReference) await fsp.access(bins.ffmpeg);
      const audioRef = recipe?.voiceRef;
      const imageRef = recipe?.imageReference;
      if (recipe && input.reference && !audioRef && !imageRef)
        throw Error('此模型配方使用纯文字输入，请清除素材引用。');
      if (imageRef && (!input.reference || !input.prompt.trim()))
        throw Error('此模型需要参考图片和画面描述。请在输入首行填写 @素材 和当前项目中的图片素材编号，下一行填写画面描述。');
      if (recipe?.requiresReference && !input.reference)
        throw Error('此模型需要参考 WAV，请在输入首行填写 @素材 和当前项目中的素材编号。');
      const attached = (task.kind === 'text' || audioInput || audioRef || imageRef || ['llama-tts','h3-video'].includes(ref.info.pipeline)) && input.reference;
      if (upscale || audioInput || attached || (task.kind === 'video' && !['h3-video','wan21-t2v','diffusion-video'].includes(ref.info.pipeline))) {
        const target = attached || draft.input.material_id;
        const matches = this.list('material', task.project_id).filter(
          (m) => m.id === target || m.name === target,
        );
        if (matches.length !== 1) throw Error('请选择当前项目中的唯一素材，或在首行填写 @素材 加素材编号。');
        material = matches[0];
        if (task.kind === 'text' && !ref.extra?.projector)
          throw Error('读取素材需要与此语言模型匹配的视觉投影 GGUF。');
        const acceptsMaterial = (audioInput || audioRef || ref.info.pipeline==='llama-tts') ? material.kind==='audio' :
          task.kind==='text' ? (material.kind==='audio' ? ref.info.acceptsAudio : ref.info.acceptsImage) : material.kind==='image';
        if (!acceptsMaterial)
          throw Error('当前模型不支持这种素材。');
        if (task.kind === 'text' && !input.prompt.trim()) throw Error('请在素材引用之后输入问题。');
      }
      const inventory = await devices();
      const device = inventory.find((d) => d.id === effective.device_id);
      if (!device) throw Error('所选设备当前不可用。');
      if (ref.info.pipeline?.startsWith('h3-') && device.id !== 'cpu' && device.free_bytes > 0) {
        const freeGiB = device.free_bytes / 1024 ** 3;
        // WDDM's reported budget includes memory the desktop can reclaim during a run.
        // Keep the decoder and the prompt encoder on the CPU on smaller GPUs.
        const lowMemory = freeGiB < 8;
        if (freeGiB < 6) {
          effective.device_id = 'cpu';
        } else {
          effective.vram_budget_gib = Math.max(0.25, Math.floor(freeGiB * (lowMemory ? 0.5 : 0.85) * 100) / 100);
          if (lowMemory) effective.diffusion_placement = 'diffusion=' + device.id.toLowerCase() + ',te=cpu,vae=cpu';
        }
      }
      const mode=inputModel(ref.info,input.prompt);
      delete effective.language_weight_conversion;
      delete effective.cpu_no_repack;
      delete effective.cpu_working_set_mib;
      delete effective.cpu_working_set_floor_mib;
      if (effective.device_id==='cpu' && mode.cpuNoRepack) effective.cpu_no_repack=true;
      if (task.kind==='text' && effective.device_id==='cpu' && (mode.compactTextBytes || mode.mappedCpuWindowBytes)) {
        const GiB=1024**3;
        const available=require('node:os').freemem();
        const companions=(material && ref.extra.projector ? (await fsp.stat(ref.extra.projector)).size : 0) +
          (ref.extra.draft ? (await fsp.stat(ref.extra.draft)).size : 0);
        const ctx=effective.context_limit ?? 4096;
        // The pinned, single-sequence CPU graph accounts for KV, recurrent state,
        // logits and compute arenas. Leave 1.25 GiB for backend/host allocations.
        const shortGraph=process.platform==='win32' && process.arch==='x64' && mode.shortContextGraphMiB && !companions &&
          ['auto','f16'].includes(effective.kv_precision ?? 'auto');
        if (shortGraph && ctx<=128) effective.cpu_no_repack=true;
        const shortBudget=bytes=>bytes+mode.shortContextGraphMiB*1024**2+3.25*GiB;
        const budget=bytes=>shortGraph && ctx<=128 ? shortBudget(bytes) :
          bytes+Math.max(GiB,Math.ceil(bytes*0.13))+ctx*1024**2+2.5*GiB;
        if (budget(mode.size+companions)>available) {
          const executionBytes=mode.compactTextBytes || mode.size;
          const required=budget(executionBytes+companions);
          const processLimit=Math.floor((Math.min(available,required)-2*GiB)/1024**2);
          const floor=bytes=>shortGraph && ctx<=128 && bytes
            ? Math.ceil((bytes+1.25*GiB)/1024**2)+mode.shortContextGraphMiB : Infinity;
          const originalFloor=floor(mode.mappedCpuWindowBytes);
          const preparedFloor=floor(mode.preparedCpuWindowBytes);
          const mapOriginal=originalFloor<=processLimit;
          if (mapOriginal || (required>available && preparedFloor<=processLimit)) {
            effective.cpu_working_set_floor_mib=mapOriginal ? originalFloor : preparedFloor;
            effective.cpu_working_set_mib=processLimit;
            effective.cpu_no_repack=true;
            if (!mapOriginal) effective.language_weight_conversion='mixed_'+mode.compactTextType;
          } else if (required>available) {
            const hint=shortGraph && ctx>128 && shortBudget(executionBytes)<=available ?
              '使用 128 词元的上下文总预算可通过本机预检，输入与最大输出需能放入该预算。' : '';
            throw Error('量化后的 GGUF 与当前上下文预计需要 '+(required/GiB).toFixed(2)+
              ' GiB 可用内存，当前可用 '+(available/GiB).toFixed(2)+' GiB。'+hint);
          } else {
            effective.language_weight_conversion='mixed_'+mode.compactTextType;
          }
        }
      }
      if (useService(mode,ref.extra,material,effective)) {
        await fsp.access(bins.llamaService);
        const structured=structuredInput(input.prompt,mode.pipeline);
        if (structured?.files?.length) {
          if (!ref.extra?.projector) throw Error('决策素材需要配套投影器。');
          const available=this.list('material',task.project_id);
          effective.decision_material_ids=structured.files.map(id=>{
            const matches=available.filter(row=>row.id===id || row.name===id);
            if(matches.length!==1) throw Error('决策模型引用的素材在当前项目中不唯一或不存在。');
            const row=matches[0];
            if(!(row.kind==='image' ? ref.info.acceptsImage : ref.info.acceptsAudio)) throw Error('此投影器不支持引用的决策素材。');
            return row.id;
          });
        }
        effective.architecture=ref.info.arch;
        effective.context_limit=Math.min(effective.context_limit || 4096,ref.info.trainedContext || 4096);
      } else if (task.kind === 'text' || ref.info.pipeline==='llama-vocoder')
        await textWorker(
          {
            action: 'inspect',
            model: ref.file,
            prompt: input.prompt,
            media: material?.path,
            projector: ref.extra?.projector,
            ple_table: ref.extra?.ple_table,
            runtime: effective,
          },
          undefined,
          (e) => {
            if (e.type === 'config') Object.assign(effective, e);
          },
        );
      Object.assign(effective, {
        device_name: inventory.find((d) => d.id === effective.device_id)?.name || effective.device_id,
        model_version_id: ref.model.version_id,
        model_manifest_digest: ref.model.manifest_digest,
      });
    } catch (e) {
      blocking.push({ message: e.message, code: 'GGUF_PREFLIGHT' });
    }
    this.remember(key, {
      task: structuredClone(task),
      fingerprint: digest(task.draft),
      revision: task.draft_revision,
      can: !blocking.length,
      effective,
      material: material?.id,
    });
    return {
      id: key,
      preflight_id: key,
      can_submit: !blocking.length,
      draft_revision: task.draft_revision,
      blocking,
      warnings: [],
      effective_config: effective,
    };
  }
  submit(task, b, key) {
    const p = this.plans.get(b.preflight_id);
    if (
      !p?.can ||
      p.task.id !== task.id ||
      p.task.project_id !== task.project_id ||
      p.revision !== b.expected_revision ||
      p.revision !== task.draft_revision ||
      p.fingerprint !== digest(task.draft)
    )
      throw Error('草稿已变化，请重新检查配置。');
    if (p.attempt) return this.view(this.rows.get(p.attempt));
    const submitted = performance.now();
    const a = {
      id: id('attempt'),
      task_id: task.id,
      project_id: task.project_id,
      state: 'queued',
      state_version: 1,
      allowed_actions: ['cancel'],
      created_at: now(),
      snapshot: structuredClone(task.draft),
      performance: {},
      effective_config: p.effective,
      output_text: '',
      artifacts: [],
      events: [],
      idempotency_key: key,
      material_id: p.material,
      last_event_sequence: 0,
    };
    this.save(a);
    p.attempt = a.id;
    this.queue.push(a);
    this.queuedSince.set(a.id, submitted);
    this.pump();
    return this.view(a);
  }
  view(a) {
    const { events, ...data } = a;
    return data;
  }
  event(a, type, payload) {
    const seq = ++a.last_event_sequence;
    a.events.push({ type, payload, sequence: seq, created_at: now() });
  }
  pump() {
    if (this.current || this.closing || !this.queue.length) return;
    const a = this.queue.shift(),
      controller = new AbortController();
    this.current = { a, controller };
    this.current.done = this.execute(a, controller.signal).finally(() => {
      this.current = null;
      this.pump();
    });
  }
  async execute(a, signal) {
    const started = performance.now();
    a.started_at = now();
    const timing = a.performance;
    timing.queue_ms = started - this.queuedSince.get(a.id);
    this.queuedSince.delete(a.id);
    let phaseStarted = started, phase = 'verify_ms';
    const finishPhase = () => {
      const end = performance.now();
      timing[phase] = end - phaseStarted;
      phaseStarted = end;
    };
    try {
      a.state = 'running';
      a.phase = 'loading';
      a.state_version++;
      this.save(a);
      const ref = this.resolve(a.snapshot.model_id, a.project_id);
      await ref.verify();
      signal.throwIfAborted();
      const dir = path.join(this.dir, a.id);
      await fsp.mkdir(dir, { recursive: true });
      const material = this.rows.get(a.material_id);
      if (material && (await hash(material.path)) !== material.manifest_digest)
        throw Error('输入素材摘要已变化。');
      const decisionMedia=[];
      for(const id of a.effective_config.decision_material_ids || []) {
        const row=this.rows.get(id);
        if(!row || row.project_id!==a.project_id || await hash(row.path)!==row.manifest_digest) throw Error('决策输入素材已变化。');
        decisionMedia.push(row);
      }
      finishPhase();
      phase = 'render_ms';
      const artifact = await render(
        { ...a.snapshot, runtime: a.effective_config },
        ref.file,
        material?.path,
        dir,
        signal,
        (type, e) => {
          if (['timing','prefill','metrics','config','step'].includes(type)) {
            for (const key of ['model_load_ms','service_start_ms','prefill_ms','decode_ms','prompt_tokens','prefill_tokens',
              'completion_tokens','decode_tokens','conditioning_ms','sampling_ms','sampling_steps','vae_encode_ms','vae_decode_ms',
              'audio_decode_ms','audio_session_ms','media_encode_ms','media_input_ms','model_process_ms','weight_prepare_ms','output_frames']) {
              if (Number.isFinite(e[key]) && e[key] >= 0) timing[key] = e[key];
            }
          }
          if (type === 'first_token' && timing.first_token_ms === undefined) timing.first_token_ms = performance.now() - started;
          if (type === 'token') a.output_text += e.text;
          else if (type === 'stage' && e.name === 'unet') a.phase = 'generating';
          else if (type === 'step') {
            a.phase = 'generating';
            a.effective_config.completed_steps = e.completed;
          } else if (type === 'prefill') {
            a.phase = 'generating';
            Object.assign(a.effective_config, {
              prefill_chunks: e.chunks,
              actual_kv_precision: e.kv_precision,
              micro_batch: e.ubatch,
            });
          } else if (type === 'metrics') a.result = e;
          this.event(a, type, e);
        },
        ref.extra,
        decisionMedia,
      );
      finishPhase();
      phase = 'collect_ms';
      signal.throwIfAborted();
      const file = path.join(dir, artifact.name),
        size = (await fsp.stat(file)).size;
      if (artifact.media_type !== 'text/plain' && (!size || size > 64 * 1024 * 1024))
        throw Error('媒体产物大小超出预览范围。');
      if (artifact.text !== undefined) a.output_text = artifact.text;
      if (artifact.media_type === 'audio/wav' || (ref.info.kind === 'audio' && material?.kind === 'audio')) {
        const output = artifact.media_type === 'audio/wav';
        const seconds = await waveSeconds(output ? file : material.path).catch(() => undefined);
        if (seconds > 0) timing[output ? 'audio_seconds' : 'input_audio_seconds'] = seconds;
      }
      const sha256 = await hash(file);
      signal.throwIfAborted();
      a.artifacts = [{ ...artifact, id: id('artifact'), sha256, size, path: file }];
      a.state = 'succeeded';
      a.compute_outcome = 'succeeded';
      a.collection_state = 'succeeded';
    } catch (e) {
      a.state = signal.aborted ? 'cancelled' : 'failed';
      if (!signal.aborted) a.error = { message: e.message };
    } finally {
      finishPhase();
      timing.run_ms = performance.now() - started;
      timing.total_ms = timing.queue_ms + timing.run_ms;
      a.phase = undefined;
      a.state_version++;
      a.allowed_actions = [];
      a.completed_at = now();
      this.event(a, 'terminal', { state: a.state, message: a.error?.message || a.state });
      this.save(a);
    }
  }
  cancel(a) {
    if (active.has(a.state)) {
      if (this.current?.a === a) {
        a.state = 'cancelling';
        this.current.controller.abort();
      } else {
        this.queue = this.queue.filter((x) => x !== a);
        a.state = 'cancelled';
        a.completed_at = now();
        a.performance.queue_ms = performance.now() - this.queuedSince.get(a.id);
        a.performance.total_ms = a.performance.queue_ms;
        this.queuedSince.delete(a.id);
        a.allowed_actions = [];
      }
      a.state_version++;
      this.save(a);
    }
    return this.view(a);
  }
  async close() {
    this.closing = true;
    for (const a of [...this.queue]) this.cancel(a);
    if (this.current) {
      this.current.controller.abort();
      await this.current.done;
    }
  }
  async request({ method, path: route, body: b = {}, task, idempotencyKey }) {
    const url = new URL(route, 'https://local.invalid'),
      s = url.pathname,
      p = url.searchParams.get('project_id');
    const refresh = url.searchParams.get('refresh') === 'true';
    if (s === '/devices' && method === 'GET') return page(await devices(refresh));
    if (s === '/environment' && method === 'GET') return this.environment.get(refresh);
    if (s === '/capabilities' && method === 'GET') return page((await this.environment.get(refresh)).capabilities);
    const imported = /^\/(models|materials)\/(import-plans|imports)$/.exec(s);
    if (imported && method === 'POST')
      return imported[2] === 'imports'
        ? this.confirmImport(imported[1], b)
        : this.inspectImport(imported[1], b);
    if (s === '/models')
      return page([
        ...this.downloads
          .records(p)
          .filter((j) => j.registeredAt)
          .map((j) => this.describe(j)),
        ...this.list('local', p).map(localView).map(row => ({ ...row, workflow_eligible: workflowEligible(row) })),
      ]);
    if (s === '/materials') return page(this.list('material', p));
    if (s.startsWith('/models/') || s.startsWith('/materials/')) {
      const mid = s.split('/')[2];
      const row = this.rows.get(mid);
      if (
        row?.id.startsWith(s.startsWith('/models/') ? 'local-' : 'material-') &&
        (!p || p === row.project_id)
      )
        return row.id.startsWith('local-') ? localView(row) : row;
      const j = this.downloads.records(p).find((j) => j.registeredAt && j.modelId === mid);
      if (j && s.startsWith('/models/')) return this.describe(j);
      throw Error('当前项目缺少该资源。');
    }
    if (s === '/attempts')
      return page(
        this.list('attempt', p)
          .filter((a) => !url.searchParams.get('task_id') || url.searchParams.get('task_id') === a.task_id)
          .map((a) => this.view(a)),
      );
    const tr = /^\/tasks\/(task-[\w-]+)\/(attempts|preflight)$/.exec(s);
    if (tr) {
      if (method === 'GET' && tr[2] === 'attempts')
        return page(
          this.list('attempt', p)
            .filter((a) => a.task_id === tr[1])
            .map((a) => this.view(a)),
        );
      if (method !== 'POST' || task?.id !== tr[1]) throw Error('任务记录无效。');
      return tr[2] === 'preflight' ? this.check(task) : this.submit(task, b, idempotencyKey);
    }
    const ar = /^\/attempts\/(attempt-[a-f0-9]{32})(?:\/(events|cancel|force-stop))?$/.exec(s);
    if (ar) {
      const a = this.rows.get(ar[1]);
      if (!a || (p && a.project_id !== p)) throw Error('运行记录不存在。');
      if (ar[2] === 'events')
        return page(a.events.filter((e) => e.sequence > Number(url.searchParams.get('after') || 0)));
      if (method === 'POST' && ['cancel', 'force-stop'].includes(ar[2])) return this.cancel(a);
      if (method === 'GET' && !ar[2]) return this.view(a);
    }
    if (s.startsWith('/artifacts/') && method === 'GET') {
      const key = s.split('/')[2];
      const f = this.list('attempt', p)
        .flatMap((a) => a.artifacts || [])
        .find((a) => a.id === key);
      if (
        !f ||
        !['image/png', 'video/mp4', 'audio/wav'].includes(f.media_type) ||
        (await hash(f.path)) !== f.sha256
      )
        throw Error('媒体产物不存在或摘要已变化。');
      return { media_type: f.media_type, base64: (await fsp.readFile(f.path)).toString('base64') };
    }
    if (s === '/works' && method === 'POST') {
      const a = this.rows.get(b.attempt_id),
        f = a?.artifacts?.find((i) => i.id === b.artifact_id);
      if (
        !f ||
        a.state !== 'succeeded' ||
        (p && a.project_id !== p) ||
        (b.project_id && a.project_id !== b.project_id)
      )
        throw Error('所选产物不可保存。');
      const prev = this.list('work', a.project_id).find((w) => w.artifact_id === f.id);
      if (prev) return prev;
      const w = this.save({
        id: id('work'),
        project_id: a.project_id,
        kind: a.snapshot.kind,
        name: f.name,
        attempt_id: a.id,
        artifact_id: f.id,
        media_type: f.media_type,
        text: f.text,
        artifacts: [f],
        created_at: now(),
        revision: 1,
      });
      a.saved_work_artifact_ids = [f.id];
      this.save(a);
      return w;
    }
    if (s === '/works') return page(this.list('work', p));
    if (/^\/works\/work-[a-f0-9]{32}$/.test(s)) {
      const work = this.rows.get(s.slice(7));
      if (work && (!p || work.project_id === p)) return work;
      throw Error('当前项目缺少该作品。');
    }
    throw fail('当前 GGUF 执行器未提供该操作。', 'UNSUPPORTED_TRIAL');
  }
}
module.exports = { Trials };
