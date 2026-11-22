'use strict';
const fs = require('node:fs'),
  fsp = fs.promises,
  path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { bundle, localExtras, materialPrompt } = require('./gguf-bundle.cjs');
const { metadata } = require('./gguf-metadata.cjs');
const { devices, parameters, textWorker, render, bins } = require('./trial-worker.cjs');
const { atomicJson, contained, verify } = require('./downloads.cjs');
const { fail } = require('./hub.cjs');
const id = (prefix) => prefix + '-' + randomUUID().replaceAll('-', '');
const digest = (o) => createHash('sha256').update(JSON.stringify(o)).digest('hex');
const page = (items) => ({ items, next_cursor: null });
const now = () => new Date().toISOString();
const active = new Set(['queued', 'running', 'cancelling']);
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
  if (!row.component_digests && row.kind !== 'video') return row;
  try {
    const ref = bundle([row.path, ...Object.values(localExtras(row))]);
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
    this.rows = new Map();
    this.plans = new Map();
    this.queue = [];
    this.current = null;
    this.closing = false;
    fs.mkdirSync(dir, { recursive: true });
    for (const name of fs
      .readdirSync(dir)
      .filter((n) => /^(attempt|work|local|material)-[a-f0-9]{32}\.json$/.test(n))) {
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
    const paths = job.files
      .filter((f) => /\.gguf$/i.test(f.path))
      .map((f) => contained(path.join(this.downloads.modelDir, job.modelId), f.path));
    if (job.derivedComponents) {
      const h3 = require('./h3-weights.cjs');
      for (const { role } of h3.sources(job.repoId, job.filename)) {
        if (!job.derivedComponents[role]) break;
        const type = job.derivedTypes?.[role] ?? (role === 'encoder' ? 'q4_0' : undefined);
        paths.push(h3.derivedFile(this.downloads.dataDir, role, type));
      }
    }
    const complete = bundle(paths);
    if (complete) return complete;
    const file = this.weight(job);
    return { file, info: file && metadata(file) };
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
        throw Error('请选择完整的 AnimateDiff 或 MiniMax-H3 模型组合。');
      const extra = localExtras(local),
        ref = bundle([local.path, ...Object.values(extra)]);
      if (!ref || ref.info.kind !== local.kind)
        throw Error('模型组件不匹配。视频需完整 AnimateDiff 或 MiniMax-H3 模型。');
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
        for (const item of job.files.filter((f) => f.path.toLowerCase().endsWith('.gguf'))) {
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
    if ((await fsp.stat(file)).isDirectory() && type === 'models') {
      const candidates = (await fsp.readdir(file)).filter((n) => /\.gguf$/i.test(n));
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
      if (!/\.gguf$/i.test(file)) throw Error('本机试用只接收 GGUF 模型。');
      info = group?.info || metadata(file);
      kind = info.kind;
      if (info.motion && !extra.motion)
        throw Error('运动模块需要配套 SD 1.5 基座，请导入包含两份 GGUF 的目录。');
      if (!kind) throw Error('尚未接入该 GGUF 架构。');
      if (/-\d{5}-of-\d{5}\.gguf$/i.test(file)) throw Error('分片模型请通过官方模型入口选择完整分片组。');
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
    const sha = manifest(baseSha, hashes),
      key = id('plan');
    this.remember(key, {
      file,
      sha,
      baseSha,
      extra,
      hashes,
      kind,
      info,
      project: b.project_id,
      name:
        b.name ||
        (extra.motion ? 'SD 1.5 + AnimateDiff GGUF' : info.pipeline || info.name || path.basename(file)),
      type,
    });
    return {
      id: key,
      plan_id: key,
      can_import: true,
      manifest_digest: sha,
      name:
        b.name ||
        (extra.motion ? 'SD 1.5 + AnimateDiff GGUF' : info.pipeline || info.name || path.basename(file)),
      format: type === 'models' ? 'GGUF' : kind === 'audio' ? 'WAV' : 'PNG',
      file_count: 1 + Object.keys(extra).length,
      total_bytes: total,
      blocking: [],
      warnings: [],
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
        type === 'models' ? 'model.gguf' : p.kind === 'audio' ? 'source.wav' : 'source.png',
      );
      try {
        const members = [[p.file, file, p.baseSha]];
        for (const [role, member] of Object.entries(p.extra))
          members.push([member, path.join(dir, role + '.gguf'), p.hashes[role]]);
        let bytes = 0;
        for (const [source, dest, expected] of members) {
          await fsp.copyFile(source, dest);
          if ((await hash(dest)) !== expected) throw Error('复制期间文件已变化。');
          bytes += (await fsp.stat(dest)).size;
        }
        return this.save({
          id: key,
          project_id: p.project,
          name: p.name,
          kind: p.kind,
          modality: p.kind,
          format: type === 'models' ? 'gguf' : p.kind === 'audio' ? 'wav' : 'png',
          status: 'ready',
          execution_available: type === 'models',
          supports_thinking: p.info.thinking || false,
          default_engine: 'ailab-gguf',
          path: file,
          version_id: p.sha,
          manifest_digest: p.sha,
          total_bytes: bytes,
          component_digests: Object.keys(p.hashes).length ? p.hashes : undefined,
          motion_digest: p.hashes.motion,
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
      const engine = bins[task.kind];
      await fsp.access(engine);
      const input = materialPrompt(draft.input);
      if (task.kind === 'video') await fsp.access(bins.ffmpeg);
      const attached = (task.kind === 'text' || ref.info.pipeline === 'h3-video') && input.reference;
      if (attached || (task.kind === 'video' && ref.info.pipeline !== 'h3-video')) {
        const target = attached || draft.input.material_id;
        const matches = this.list('material', task.project_id).filter(
          (m) => m.id === target || m.name === target,
        );
        if (matches.length !== 1) throw Error('请选择当前项目中的唯一素材，或在首行填写 @素材 加素材编号。');
        material = matches[0];
        if (task.kind === 'text' && !ref.extra?.projector)
          throw Error('读取素材需要与此语言模型匹配的视觉投影 GGUF。');
        if (
          material.kind !== 'image' &&
          !(task.kind === 'text' && ref.info.arch === 'gemma4' && material.kind === 'audio')
        )
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
      if (task.kind === 'text')
        await textWorker(
          {
            action: 'inspect',
            model: ref.file,
            prompt: input.prompt,
            media: material?.path,
            projector: ref.extra?.projector,
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
    const a = {
      id: id('attempt'),
      task_id: task.id,
      project_id: task.project_id,
      state: 'queued',
      state_version: 1,
      allowed_actions: ['cancel'],
      created_at: now(),
      snapshot: structuredClone(task.draft),
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
      const artifact = await render(
        { ...a.snapshot, runtime: a.effective_config },
        ref.file,
        material?.path,
        dir,
        signal,
        (type, e) => {
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
      );
      signal.throwIfAborted();
      const file = path.join(dir, artifact.name),
        size = (await fsp.stat(file)).size;
      if (artifact.media_type !== 'text/plain' && (!size || size > 64 * 1024 * 1024))
        throw Error('媒体产物大小超出预览范围。');
      if (artifact.text !== undefined) a.output_text = artifact.text;
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
    if (s === '/devices') return page(await devices(url.searchParams.get('refresh') === 'true'));
    if (s === '/capabilities')
      return page(
        ['text', 'image', 'video', 'audio'].flatMap((kind) =>
          ['generate', 'train'].map((operation) => {
            const ok =
              operation === 'generate' &&
              fs.existsSync(bins[kind]) &&
              (kind !== 'video' || fs.existsSync(bins.ffmpeg));
            return {
              kind,
              operation,
              supported: ok,
              status: ok ? 'ready' : 'not_prepared',
              reason: ok
                ? '本机 GGUF，选择匹配架构后检查。'
                : operation === 'train'
                  ? 'GGUF 训练执行器尚未接入。'
                  : '本机缺少此试用执行器。',
            };
          }),
        ),
      );
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
        ...this.list('local', p).map(localView),
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
