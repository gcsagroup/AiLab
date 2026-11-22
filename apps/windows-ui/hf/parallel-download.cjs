'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { fail } = require('./hub.cjs');
const chunkBytes = 4 * 1024 * 1024;
const concurrency = 8;
const retries = 2;
async function regular(filename, missing = false) {
  try { const stat = await fs.lstat(filename); if (stat.isSymbolicLink() || !stat.isFile()) throw fail('分段缓存文件不能是链接或目录。', 'UNSAFE_CHUNK_PATH'); return stat; }
  catch (error) { if (missing && error.code === 'ENOENT') return null; throw error; }
}
async function directory(filename, create = false) {
  if (create) await fs.mkdir(filename, { recursive: false }).catch(error => { if (error.code !== 'EEXIST') throw error; });
  const stat = await fs.lstat(filename);
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw fail('分段缓存目录不能是链接或普通文件。', 'UNSAFE_CHUNK_PATH');
}
const CHUNK_NAME = /^(\d+)-(\d+)\.(chunk|download)$/;
async function clearChunks(part) {
  const root = `${part}.chunks`;
  try { await directory(root); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  const names = await fs.readdir(root);
  for (const name of names) {
    if (!CHUNK_NAME.test(name) && !['meta.json', 'meta.json.tmp'].includes(name)) throw fail('分段缓存含未知文件，已停止清理。', 'UNSAFE_CHUNK_PATH');
    await regular(path.join(root, name));
  }
  // Delete only checked ordinary files; never recursively follow a cache directory.
  for (const name of names) await fs.unlink(path.join(root, name));
  await fs.rmdir(root);
}
function sleep(milliseconds, signal) {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const done = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); resolve(); };
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(signal.reason); };
    const timer = setTimeout(done, milliseconds); signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}
function retryDelay(error, attempt, base) {
  if (error.status === 429 || error.code === 'HF_429') {
    const value = error.retryAfter;
    const seconds = value !== null && value !== undefined && /^\d+(?:\.\d+)?$/.test(String(value)) ? Number(value) * 1000 : Date.parse(value || '') - Date.now();
    if (Number.isFinite(seconds)) return Math.min(60000, Math.max(base, seconds));
  }
  return Math.min(30000, base * 2 ** attempt);
}

async function parallelDownload(hub, file, part, signal, onProgress) {
  signal.throwIfAborted();
  if (!path.isAbsolute(part) || !Number.isSafeInteger(file.size) || file.size <= 0) throw fail('分段下载文件参数无效。', 'SEGMENT_STATE');
  const root = `${part}.chunks`;
  await directory(path.dirname(part));
  let prefix = (await regular(part, true))?.size || 0;
  if (prefix > file.size) throw fail('连续下载文件超过声明大小。', 'SEGMENT_STATE');
  await directory(root, true);
  const identity = { version: 1, url: file.url, size: file.size, path: file.path, sha256: file.sha256 || null, gitOid: file.gitOid || null };
  const metaPath = path.join(root, 'meta.json');
  let chunkSize = chunkBytes;
  if (await regular(metaPath, true)) {
    const stored = JSON.parse(await fs.readFile(metaPath, 'utf8'));
    if (Object.keys(identity).some(key => stored[key] !== identity[key]) || !Number.isSafeInteger(stored.chunkSize) || stored.chunkSize < 1 || stored.chunkSize > 64 * 1024 * 1024) throw fail('分段缓存不属于当前固定模型文件。', 'SEGMENT_STATE');
    chunkSize = stored.chunkSize;
  } else {
    const names = await fs.readdir(root);
    if (names.some(name => name !== 'meta.json.tmp')) throw fail('分段缓存缺少身份记录，未修改现有连续文件。', 'SEGMENT_STATE');
    if (names.includes('meta.json.tmp')) { await regular(`${metaPath}.tmp`); await fs.unlink(`${metaPath}.tmp`); }
    await fs.writeFile(`${metaPath}.tmp`, JSON.stringify({ ...identity, chunkSize }), { flag: 'wx' });
    await fs.rename(`${metaPath}.tmp`, metaPath);
  }
  const records = new Map();
  for (const name of await fs.readdir(root)) {
    if (name === 'meta.json') continue;
    const match = CHUNK_NAME.exec(name);
    if (!match) throw fail('分段缓存包含未知文件。', 'SEGMENT_STATE');
    const start = Number(match[1]), end = Number(match[2]), index = Math.floor(start / chunkSize);
    const filename = path.join(root, name); const stat = await regular(filename);
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 0 || start > end || end !== Math.min(file.size - 1, (index + 1) * chunkSize - 1)) throw fail('分段缓存范围无效。', 'SEGMENT_STATE');
    if (end < prefix || stat.size > end - start + 1 || (match[3] === 'chunk' && stat.size !== end - start + 1)) { await fs.unlink(filename); continue; }
    const record = { start, end, index, filename, bytes: stat.size, complete: match[3] === 'chunk' };
    const previous = records.get(index);
    if (previous) {
      if (record.complete && !previous.complete) { await fs.unlink(previous.filename); records.set(index, record); }
      else { await fs.unlink(filename); }
    } else records.set(index, record);
  }
  const stop = new AbortController();
  const combined = AbortSignal.any([signal, stop.signal]);
  let failure = null, pauseUntil = 0;
  const progress = () => {
    let cached = 0;
    for (const record of records.values()) cached += Math.max(0, record.start + record.bytes - Math.max(prefix, record.start));
    onProgress(Math.min(file.size, prefix + cached));
  };
  const stopAll = error => { if (!failure) failure = error; stop.abort(error); };
  const timer = setInterval(() => { try { progress(); } catch (error) { stopAll(error); } }, 1000);
  let mergeChain = Promise.resolve();
  async function mergeReady() {
    while (prefix < file.size) {
      signal.throwIfAborted();
      const index = Math.floor(prefix / chunkSize), record = records.get(index);
      if (!record?.complete || record.start > prefix) return;
      const stat = await regular(record.filename);
      if (stat.size !== record.end - record.start + 1) throw fail('已下载分段大小发生改变。', 'SEGMENT_INTEGRITY');
      await regular(part, true);
      const input = await fs.open(record.filename, 'r'); const output = await fs.open(part, 'a');
      try {
        const current = await output.stat();
        if (current.size !== prefix) throw fail('连续文件被其他操作修改。', 'SEGMENT_STATE');
        const buffer = Buffer.allocUnsafe(Math.min(1024 * 1024, record.end - prefix + 1));
        while (prefix <= record.end) {
          signal.throwIfAborted();
          const { bytesRead } = await input.read(buffer, 0, Math.min(buffer.length, record.end - prefix + 1), prefix - record.start);
          if (!bytesRead) throw fail('分段缓存未包含完整数据。', 'SEGMENT_INTEGRITY');
          let written = 0;
          while (written < bytesRead) { const value = await output.write(buffer, written, bytesRead - written); if (!value.bytesWritten) throw fail('无法追加模型分段。', 'SEGMENT_WRITE'); written += value.bytesWritten; prefix += value.bytesWritten; }
        }
        await output.sync();
      } finally { await input.close(); await output.close(); }
      await fs.unlink(record.filename); records.delete(index); progress();
    }
  }
  function queueMerge() {
    mergeChain = mergeChain.then(mergeReady);
    mergeChain.catch(stopAll);
    return mergeChain;
  }
  async function getRecord(index) {
    const wantedStart = Math.max(prefix, index * chunkSize), end = Math.min(file.size - 1, (index + 1) * chunkSize - 1);
    let record = records.get(index);
    if (record && record.start > wantedStart) { await regular(record.filename); await fs.unlink(record.filename); records.delete(index); record = null; }
    if (!record) { record = { start: wantedStart, end, index, filename: path.join(root, `${wantedStart}-${end}.download`), bytes: 0, complete: false }; records.set(index, record); }
    return record;
  }
  async function fetchChunk(record) {
    if (record.complete) { await queueMerge(); return; }
    for (let attempt = 0; attempt <= retries; attempt++) {
      combined.throwIfAborted();
      if (pauseUntil > Date.now()) await sleep(pauseUntil - Date.now(), combined);
      let response, reader, handle, idleTimer, abortReader;
      const idle = new AbortController();
      const requestSignal = AbortSignal.any([combined, idle.signal]);
      const resetIdle = () => { clearTimeout(idleTimer); idleTimer = setTimeout(() => idle.abort(fail('分段连接长时间未收到数据。', 'SEGMENT_TIMEOUT')), 60000); };
      const before = record.bytes;
      try {
        const stat = await regular(record.filename, true); record.bytes = stat?.size || 0;
        const requestStart = record.start + record.bytes;
        if (requestStart <= record.end) {
          resetIdle();
          response = await hub.request(file.url, { raw: true, signal: requestSignal, headers: { Range: `bytes=${requestStart}-${record.end}` } });
          if (response.status === 200) { await response.body?.cancel(); throw fail('服务器未支持分段请求，已改用单连接下载。', 'RANGE_UNSUPPORTED'); }
          const range = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get('content-range') || '');
          const expected = record.end - requestStart + 1;
          const length = response.headers.get('content-length');
          const encoding = response.headers.get('content-encoding');
          if (response.status !== 206 || !range || Number(range[1]) !== requestStart || Number(range[2]) !== record.end || Number(range[3]) !== file.size || (length !== null && Number(length) !== expected) || (encoding && encoding !== 'identity')) throw fail('服务器分段范围或长度与请求不匹配。', 'SEGMENT_INTEGRITY');
          if (!response.body) throw fail('分段响应为空。', 'SEGMENT_INCOMPLETE');
          handle = await fs.open(record.filename, stat ? 'a' : 'wx');
          reader = response.body.getReader();
          abortReader = () => { void reader.cancel(requestSignal.reason).catch(() => {}); };
          requestSignal.addEventListener('abort', abortReader, { once: true });
          if (requestSignal.aborted) abortReader();
          let received = 0;
          while (true) {
            requestSignal.throwIfAborted();
            const value = await reader.read(); requestSignal.throwIfAborted(); if (value.done) break;
            const chunk = value.value;
            if (received + chunk.length > expected) throw fail('分段响应超过请求长度。', 'SEGMENT_INTEGRITY');
            resetIdle(); let written = 0;
            while (written < chunk.length) { const result = await handle.write(chunk, written, chunk.length - written); if (!result.bytesWritten) throw fail('分段写入失败。', 'SEGMENT_WRITE'); written += result.bytesWritten; record.bytes += result.bytesWritten; }
            received += chunk.length;
          }
          if (received !== expected) throw fail('分段连接提前结束，将续传缺少内容。', 'SEGMENT_INCOMPLETE');
          await handle.sync(); await handle.close(); handle = null;
        }
        combined.throwIfAborted();
        const completePath = path.join(root, `${record.start}-${record.end}.chunk`);
        await fs.rename(record.filename, completePath); record.filename = completePath; record.complete = true;
        await queueMerge(); return;
      } catch (error) {
        if (handle) { await handle.sync().catch(() => {}); await handle.close(); handle = null; }
        if (error.code === 'SEGMENT_INTEGRITY') { const stat = await regular(record.filename, true); if (stat) await fs.truncate(record.filename, before); record.bytes = before; }
        if (combined.aborted) throw combined.reason;
        if (error.code === 'RANGE_UNSUPPORTED' || ['HF_401', 'HF_403', 'HF_404', 'HF_416', 'INVALID_ORIGIN', 'INVALID_SOURCE', 'INVALID_HEADERS', 'UNSAFE_CHUNK_PATH', 'SEGMENT_STATE', 'SEGMENT_WRITE'].includes(error.code) || attempt >= retries) { error.noRetry = true; throw error; }
        const wait = retryDelay(error, attempt, 1000);
        if (error.code === 'HF_429' || error.status === 429) pauseUntil = Math.max(pauseUntil, Date.now() + wait);
        await sleep(wait, combined);
      } finally {
        clearTimeout(idleTimer);
        if (abortReader) requestSignal.removeEventListener('abort', abortReader);
        if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
        else if (response?.body && !response.body.locked) await response.body.cancel().catch(() => {});
        progress();
      }
    }
  }
  const active = new Map();
  let nextIndex = Math.floor(prefix / chunkSize);
  try {
    progress();
    while (prefix < file.size && !failure) {
      signal.throwIfAborted();
      // Refill each free slot immediately, while bounding active and cached
      // ranges to two connection windows ahead of the continuous prefix.
      while (active.size < concurrency && !failure) {
        signal.throwIfAborted();
        nextIndex = Math.max(nextIndex, Math.floor(prefix / chunkSize));
        const limit = Math.min(Math.ceil(file.size / chunkSize), Math.floor(prefix / chunkSize) + concurrency * 2);
        if (nextIndex >= limit) break;
        const index = nextIndex++, record = await getRecord(index);
        if (failure) break;
        const pending = fetchChunk(record).catch(stopAll).finally(() => active.delete(index));
        active.set(index, pending);
      }
      if (failure) break;
      if (active.size) await Promise.race(active.values());
      else {
        await queueMerge();
        if (prefix < file.size) throw fail('分段窗口未能推进连续文件。', 'SEGMENT_STATE');
      }
    }
    await Promise.allSettled(active.values());
    await mergeChain.catch(() => {});
    signal.throwIfAborted();
    if (failure) {
      if (failure.code === 'RANGE_UNSUPPORTED') return true;
      throw failure;
    }
    return false;
  } finally {
    clearInterval(timer); stop.abort();
    await Promise.allSettled(active.values());
    await mergeChain.catch(() => {}); progress();
  }
}
module.exports = { parallelDownload, clearChunks };
