'use strict';
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { fail, safeFile, repoId, resolveUrl } = require('./hub.cjs');
const { parallelDownload, clearChunks } = require('./parallel-download.cjs');
function atomicJson(filename, value) { fs.mkdirSync(path.dirname(filename), { recursive: true }); fs.writeFileSync(filename + '.tmp', JSON.stringify(value, null, 2)); fs.renameSync(filename + '.tmp', filename); }
function contained(root, relative) { const target = path.resolve(root, safeFile(relative)); if (!target.startsWith(path.resolve(root) + path.sep)) throw fail('文件路径越界。'); return target; }
async function safeParents(root, relative) {
  let current = root;
  for (const part of safeFile(relative).split('/').slice(0, -1)) {
    current = path.join(current, part);
    try { const stat = await fsp.lstat(current); if (stat.isSymbolicLink() || !stat.isDirectory()) throw fail('模型父目录不能是链接或普通文件。'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; await fsp.mkdir(current); }
  }
}
async function verify(filename, file, signal) {
  signal?.throwIfAborted();
  const stat = await fsp.stat(filename); if (stat.size !== file.size) throw fail(`文件大小校验失败：${file.path}`, 'INTEGRITY');
  const algorithm = file.sha256 ? 'sha256' : /^[0-9a-f]{40}$/.test(file.gitOid || '') ? 'sha1' : null;
  if (!algorithm) throw fail('模型文件缺少可信摘要。', 'INTEGRITY');
  const hash = createHash(algorithm); if (algorithm === 'sha1') hash.update(`blob ${stat.size}\0`);
  for await (const chunk of fs.createReadStream(filename, { signal })) { signal?.throwIfAborted(); hash.update(chunk); }
  if (hash.digest('hex') !== (file.sha256 || file.gitOid)) throw fail(`文件哈希校验失败：${file.path}`, 'INTEGRITY');
  return algorithm;
}
class Downloads {
  constructor({ dataDir, hub }) {
    this.dataDir = path.resolve(dataDir); this.hub = hub; this.active = new Map(); this.jobs = new Map();
    this.jobDir = path.join(dataDir, 'downloads'); this.modelDir = path.join(dataDir, 'models');
    fs.mkdirSync(this.jobDir, { recursive: true }); fs.mkdirSync(this.modelDir, { recursive: true });
    for (const file of fs.readdirSync(this.jobDir).filter(f => /^download-[0-9a-f]{24}\.json$/.test(f))) {
      try { const job = JSON.parse(fs.readFileSync(path.join(this.jobDir, file), 'utf8'));
        if (file !== `${job.id}.json` || !/^hf-[0-9a-f]{24}$/.test(job.modelId || '') || job.modelId !== job.id.replace('download-', 'hf-') || !/^[0-9a-f]{40,64}$/.test(job.revision || '') || !Array.isArray(job.files)) continue;
        repoId(job.repoId);
        for (const item of job.files) { safeFile(item.path); if (!Number.isSafeInteger(item.size) || item.size < 0 || (item.sha256 && !/^[0-9a-f]{64}$/.test(item.sha256))) throw fail('下载记录文件元数据无效。'); const source=require('./h3-weights.cjs').sources(job.repoId,job.filename).find(f=>f.path===item.path && f.sha256===item.sha256); item.url = source ? source.url : resolveUrl(job.repoId, job.revision, item.path); }
        const identity = createHash('sha256').update(JSON.stringify([job.projectId, job.repoId, job.revision, job.format, job.files.map(f=>f.path)])).digest('hex').slice(0,24);
        if (job.id !== `download-${identity}`) continue;
        if (['queued', 'downloading'].includes(job.status)) job.status = 'paused';
        this.jobs.set(job.id, job);
      } catch { /* One damaged manifest must not discard other downloads. */ }
    }
  }
  save(job) { atomicJson(path.join(this.jobDir, `${job.id}.json`), job); }
  records(projectId) {
    return [...this.jobs.values()].filter(job => !projectId || job.projectId === projectId).sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  }
  model(job) {
    return {id: job.modelId, project_id: job.projectId, name: job.filename ? job.repoId + ' · ' + job.filename : job.repoId, format: job.format, status: 'downloaded', modality: 'text',
      path: path.join(this.modelDir, job.modelId), version_id: job.revision, manifest_digest: job.manifestDigest, total_bytes: job.totalBytes,
      provenance: {source: 'huggingface', repo: job.repoId, revision: job.revision, license: job.license, source_url: 'https://huggingface.co/' + job.repoId + '/tree/' + job.revision}};
  }
  async register(id) {
    const job = this.get(id);
    if (job.status !== 'completed') throw fail('请先完成下载和校验。', 'DOWNLOAD_INCOMPLETE');
    const h3 = require('./h3-weights.cjs');
    const types = h3.conversionTypes(job.repoId, job.filename);
    if (job.registeredAt && Object.entries(types).every(([role, type]) => job.derivedTypes?.[role] === type)) return this.model(job);
    try {
      for (const file of job.files) {
        const root = path.join(this.modelDir, job.modelId);
        const target = contained(root, file.path);
        if ((await fsp.realpath(target)).toLowerCase() !== target.toLowerCase()) throw fail('模型文件路径已变化。', 'INTEGRITY');
        await verify(target, file);
      }
    } catch (error) {
      job.status = 'failed'; job.error = '登记前文件核对失败：' + error.message; this.save(job);
      throw fail(job.error, 'INTEGRITY');
    }
    const derived = await h3.prepare(job, this.modelDir, this.dataDir);
    if (derived) {
      job.derivedComponents = derived;
      job.derivedTypes = types;
    }
    const registeredAt = new Date().toISOString();
    this.save({...job, registeredAt});
    job.registeredAt = registeredAt;
    return this.model(job);
  }
  get(id) { const job = this.jobs.get(id); if (!job) throw fail('下载任务不存在。'); return job; }
  async create(plan, projectId, manifestDigest) {
    const key = createHash('sha256').update(JSON.stringify([projectId, plan.repoId, plan.revision, plan.format, plan.files.map(f=>f.path)])).digest('hex').slice(0,24);
    const id = `download-${key}`; if (this.jobs.has(id)) return this.get(id);
    const disk = await fsp.statfs(this.modelDir); if (disk.bavail * disk.bsize < plan.totalBytes + 64 * 1024 * 1024) throw fail('磁盘空间不足，无法保存所选模型。', 'DISK_SPACE');
    if (this.jobs.has(id)) return this.get(id); // statfs yielded: another request may have claimed this snapshot.
    const job = { id, projectId, manifestDigest, modelId: `hf-${key}`, repoId: plan.repoId, revision: plan.revision, format: plan.format, filename: plan.filename || null, task: plan.task, modelType: plan.modelType, license: plan.license, files: plan.files.map(f=>({...f,verified:false})), totalBytes: plan.totalBytes, downloadedBytes: 0, status: 'queued', createdAt: new Date().toISOString(), error: null };
    this.save(job); this.jobs.set(id, job); this.launch(job); return { ...job };
  }
  launch(job) {
    if (this.active.has(job.id) || job.status === 'completed') return;
    const controller = new AbortController(); const entry = { controller };
    this.active.set(job.id, entry);
    entry.pending = this.execute(job, controller.signal).catch(error => {
      job.status = controller.signal.aborted ? 'paused' : 'failed'; job.error = controller.signal.aborted ? null : error.message; this.save(job);
    }).finally(() => this.active.delete(job.id));
  }
  async pause(id) { const job = this.get(id); const entry = this.active.get(id); if (entry) { entry.controller.abort(); await entry.pending; } return { ...job }; }
  async resume(id) { const job = this.get(id); if (this.active.has(id)) return { ...job }; if (job.status !== 'completed') { job.status = 'queued'; job.error = null; this.save(job); this.launch(job); } return { ...job }; }
  async execute(job, signal) {
    if ((await fsp.lstat(this.modelDir)).isSymbolicLink()) throw fail('模型根目录不能是符号链接。');
    const directory = path.join(this.modelDir, job.modelId); await fsp.mkdir(directory, { recursive: true });
    // Model paths are controlled by a content identity; reject links before writing.
    if ((await fsp.lstat(directory)).isSymbolicLink()) throw fail('模型目录不能是符号链接。');
    job.status = 'downloading'; this.save(job);
    let completed = 0;
    for (const [index, file] of job.files.entries()) {
      const part = path.join(this.jobDir, job.id + '.' + index + '.part');
      signal.throwIfAborted(); job.currentFile = file.path;
      const target = contained(directory, file.path); await safeParents(directory, file.path);
      const realParent = await fsp.realpath(path.dirname(target)); const realDirectory = await fsp.realpath(directory);
      if (realParent !== realDirectory && !realParent.startsWith(realDirectory + path.sep)) throw fail('模型路径包含越界链接。');
      for (const filename of [target, part]) { try { if ((await fsp.lstat(filename)).isSymbolicLink()) throw fail('模型文件不能是符号链接。'); } catch (error) { if (error.code !== 'ENOENT') throw error; } }
      file.verified = false;
      let exists = false; try { await fsp.access(target); exists = true; } catch { /* Not downloaded yet. */ }
      // A new component manifest can refer to a large DiT already verified in this project.
      if (!exists && file.sha256 && file.size>=16*1024*1024) {
        for(const previous of this.records(job.projectId)) {
          if(previous.id===job.id || previous.status!=='completed')continue;
          const match=previous.files.find(f=>f.sha256===file.sha256 && f.size===file.size && f.verified);
          if(!match)continue;
          const source=contained(path.join(this.modelDir,previous.modelId),match.path);
          try {
            if((await fsp.realpath(source)).toLowerCase()!==source.toLowerCase())continue;
            await fsp.link(source,target); exists=true;break;
          } catch(e){if(e.code==='EEXIST'){exists=true;break;} /* Missing or on another volume; use the Hub. */}
        }
      }
      if (exists) { try { file.verification = await verify(target, file, signal); file.verified = true; } catch (error) { signal.throwIfAborted(); await fsp.rename(target, part + `.corrupt-${Date.now()}`); file.verified = false; } }
      if (!file.verified) {
        for (let retry = 0; ; retry++) {
          try { await this.transfer(job, file, target, part, completed, signal); break; }
          catch (error) {
            if (signal.aborted || error.noRetry || retry >= 2 || ['HF_401','HF_403','HF_404','INVALID_ORIGIN','UNSAFE_CHUNK_PATH','SEGMENT_STATE'].includes(error.code)) throw error;
            if (error.code === 'INTEGRITY') { await fsp.truncate(part, 0).catch(() => {}); }
            await new Promise((resolve, reject) => { const listener=()=>{clearTimeout(timer); reject(signal.reason)}; const timer=setTimeout(()=>{signal.removeEventListener('abort',listener);resolve()},Math.min(10000,1000*2**retry));signal.addEventListener('abort',listener,{once:true}); });
          }
        }
      }
      completed += file.size; job.downloadedBytes = completed; this.save(job);
    }
    signal.throwIfAborted();
    job.status = 'completed'; job.downloadedBytes = job.totalBytes; job.currentFile = null; job.completedAt = new Date().toISOString(); job.error = null;
    this.save(job);
  }
  async transfer(job, file, target, part, completed, signal) {
    let offset = 0;
    try { offset = (await fsp.stat(part)).size; } catch { /* Start new file. */ }
    if (offset > file.size) { await fsp.truncate(part, 0); offset = 0; }
    if (offset < file.size && file.size >= 16 * 1024 * 1024) {
      let lastSave = 0;
      const fallback = await parallelDownload(this.hub, file, part, signal, bytes => {
        job.downloadedBytes = completed + bytes;
        if (Date.now() - lastSave >= 750) { this.save(job); lastSave = Date.now(); }
      });
      if (fallback) await clearChunks(part);
      try { offset = (await fsp.stat(part)).size; }
      catch (error) { if (error.code !== 'ENOENT') throw error; offset = 0; }
    }
    if (offset < file.size) {
      const idle = new AbortController(); let idleTimer;
      const resetIdle = () => { clearTimeout(idleTimer); idleTimer = setTimeout(() => idle.abort(new Error('下载连接长时间没有数据，请续传重试。')), 60000); };
      resetIdle();
      try {
      const response = await this.hub.request(file.url, { raw: true, signal: AbortSignal.any([signal, idle.signal]), headers: offset ? { Range: `bytes=${offset}-` } : {} });
      if (response.status === 206) {
        const range = response.headers.get('content-range')?.match(/^bytes (\d+)-(\d+)\/(\d+)$/);
        if (!range || Number(range[1]) !== offset || Number(range[3]) !== file.size || Number(range[2]) !== file.size - 1) { await response.body?.cancel(); throw fail('HF 分段下载响应不匹配。', 'INTEGRITY'); }
      } else if (response.status === 200) { offset = 0; }
      else { await response.body?.cancel(); throw fail('HF 文件响应状态无效。'); }
      const handle = await fsp.open(part, offset ? 'a' : 'w'); let lastSave = 0;
      try {
        for await (const chunk of response.body) {
          signal.throwIfAborted(); resetIdle();
          if (offset + chunk.length > file.size) throw fail('文件超过 HF 声明的大小。', 'INTEGRITY');
          let written = 0; while (written < chunk.length) { const result = await handle.write(chunk, written, chunk.length - written); if (!result.bytesWritten) throw fail('写入模型文件失败。'); written += result.bytesWritten; }
          offset += chunk.length; job.downloadedBytes = completed + offset;
          if (Date.now() - lastSave > 750) { this.save(job); lastSave = Date.now(); }
        }
        await handle.sync();
        if (offset < file.size) throw fail('连接提前结束，已保留部分文件。', 'NETWORK_INCOMPLETE');
      } finally { await handle.close(); }
      } finally { clearTimeout(idleTimer); }
    } else if (file.size === 0) { await fsp.writeFile(part, ''); }
    try {
      file.verification = await verify(part, file, signal);
    } catch (error) {
      if (error.code === 'INTEGRITY') { await clearChunks(part); await fsp.truncate(part, 0); }
      throw error;
    }
    signal.throwIfAborted();
    await clearChunks(part);
    await fsp.rename(part, target); file.verified = true;
  }
  async shutdown() { await Promise.all([...this.active.keys()].map(id=>this.pause(id))); }
}
module.exports = { Downloads, atomicJson, verify, contained };
