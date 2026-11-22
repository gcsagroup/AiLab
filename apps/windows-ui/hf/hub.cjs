'use strict';
const HF = 'https://huggingface.co';
const formatPatterns = {
  gguf: /\.gguf$/i,
  safetensors: /\.safetensors$/i,
  pytorch: /\.(?:bin|pt|pth|ckpt)$/i,
  onnx: /\.onnx(?:_data)?$|\.onnx\.data$|(^|\/)onnx\/.*\.data$/i,
  tensorflow: /\.(?:h5|keras|tflite)$|(^|\/)saved_model\.pb$|\.data-\d+-of-\d+$|\.ckpt\.index$/i,
  flax: /\.msgpack$/i,
  openvino: /(^|\/)(?:openvino[^/]*\.(?:xml|bin)|openvino\/.*\.(?:xml|bin))$/i,
  coreml: /\.(?:mlmodel|mlpackage|mlmodelc)(?:\/|$)/i,
  ggml: /\.ggml$/i,
};
function formatOf(filename) {
  if (formatPatterns.openvino.test(filename)) return 'openvino';
  return Object.keys(formatPatterns).find(format => formatPatterns[format].test(filename));
}
function fail(message, code = 'HF_REQUEST') { return Object.assign(new Error(message), { code }); }
function repoId(value) {
  if (typeof value !== 'string' || !/^(?:[A-Za-z0-9_][A-Za-z0-9._-]{0,95}\/)?[A-Za-z0-9_][A-Za-z0-9._-]{0,95}$/.test(value) || value.includes('..') || value.includes('--') || /[.-]$/.test(value)) throw fail('模型 ID 必须为有效的 owner/model 或 HF 模型名称。', 'INVALID_REPO');
  return value;
}
function revision(value = 'main') {
  if (typeof value !== 'string' || !value || value.length > 200 || /[\x00-\x20\\?#]/.test(value) || value.split('/').some(p => p === '..' || p === '.')) throw fail('无效的模型版本。', 'INVALID_REVISION');
  return value;
}
function safeFile(value) {
  if (typeof value !== 'string' || !value || value.length > 500 || /[\\:\x00-\x1f<>"|?*]/.test(value) || value.split('/').some(p => !p || p === '.' || p === '..' || p.toLowerCase() === '.git' || /[. ]$/.test(p) || /^(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\.|$)/i.test(p))) throw fail('仓库包含不安全或不兼容 Windows 的文件路径。', 'INVALID_FILE');
  return value;
}
function resolveUrl(id, rev, filename) { return `${HF}/${repoId(id)}/resolve/${encodeURIComponent(revision(rev))}/${safeFile(filename).split('/').map(encodeURIComponent).join('/')}?download=true`; }
function allowedDownload(url) { const u = new URL(url); return u.protocol === 'https:' && !u.username && !u.password && (!u.port || u.port === '443') && /(^|\.)(huggingface\.co|hf\.co)$/.test(u.hostname); }
function licenseOf(item) { const raw = item.cardData?.license || item.tags?.find(t => t.startsWith('license:'))?.slice(8); return Array.isArray(raw) ? raw.join(', ') : raw || 'unknown'; }
function normalize(item) {
  const id = repoId(item.id || item.modelId); const license = licenseOf(item);
  return { id, repoId: id, url: `${HF}/${id}`, author: item.author || id.split('/')[0], downloads: item.downloads || 0, likes: item.likes || 0, task: item.pipeline_tag || (item.tags?.includes('text-generation') ? 'text-generation' : item.tags?.includes('conversational') ? 'conversational' : 'unknown'), library: item.library_name || 'unknown', license, gated: item.gated || false, tags: item.tags || [], updatedAt: item.lastModified || null };
}
async function readJson(response, maximum = 32 * 1024 * 1024) {
  const chunks = []; let size = 0;
  if (!response.body) throw fail('HF 返回了空响应。');
  for await (const chunk of response.body) { size += chunk.length; if (size > maximum) { throw fail('HF 元数据响应过大，请缩小查询范围。'); } chunks.push(chunk); }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}
class HubClient {
  constructor({ fetchImpl = fetch } = {}) { this.fetch = fetchImpl; this.token = ''; }
  setToken(token) { if (typeof token !== 'string' || token.length > 1000 || /[\r\n]/.test(token)) throw fail('无效的访问令牌。'); this.token = token.trim(); return { configured: !!this.token }; }
  async request(url, { signal, headers = {}, raw = false } = {}) {
    if (!allowedDownload(url)) throw fail('只允许 Hugging Face 官方 API 与下载域名。', 'INVALID_ORIGIN');
    let target = url;
    for (let redirect = 0; redirect < 8; redirect++) {
      const host = new URL(target).hostname;
      const auth = host === 'huggingface.co' && this.token ? { Authorization: `Bearer ${this.token}` } : {};
      const connection = new AbortController(); const timer = setTimeout(() => connection.abort(new Error('HF 连接超时。')), 45000);
      let response;
      try { response = await this.fetch(target, { redirect: 'manual', headers: { 'User-Agent': 'GCSA-AiLab-HF/3.1', 'Accept-Encoding': 'identity', ...auth, ...headers }, signal: signal ? AbortSignal.any([signal, connection.signal]) : connection.signal }); }
      catch (error) { clearTimeout(timer); if (signal?.aborted) throw error; throw fail('无法连接 Hugging Face 官方来源，请检查网络后重试。', 'NETWORK_HF'); }
      // Large weights may take hours. Downloads enforce a resettable idle timeout, not a total lifetime limit.
      if (raw) clearTimeout(timer);
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const location = response.headers.get('location'); clearTimeout(timer); await response.body?.cancel();
        if (!location) throw fail('HF 重定向缺少地址。'); target = new URL(location, target).href;
        if (!allowedDownload(target)) throw fail('HF 返回了未识别的下载域名；请更新下载器。', 'INVALID_ORIGIN'); continue;
      }
      if (!response.ok) {
        clearTimeout(timer); await response.body?.cancel();
        const messages = { 401: '请检查仓库名称。受限仓库需要先在 Hugging Face 获得授权，再设置 HF_TOKEN 并重开 AiLab。', 403: '没有访问权限，请先在 HF 模型页接受条款或申请访问。', 404: '模型、版本或文件不存在。', 429: 'HF 请求限流，请稍后继续。' };
        throw Object.assign(fail(messages[response.status] || `HF 请求失败 (${response.status})。`, `HF_${response.status}`), { status: response.status, retryAfter: response.headers.get('retry-after') });
      }
      if (raw) return response;
      try { return { data: await readJson(response), headers: response.headers }; } finally { clearTimeout(timer); }
    }
    throw fail('HF 重定向次数过多。');
  }
  async search({ query = '', task = '', license = '', cursor, limit = 30, signal } = {}) {
    let url;
    if (cursor) {
      if (typeof cursor !== 'string' || cursor.length > 12000) throw fail('无效的分页游标。');
      url = Buffer.from(cursor, 'base64url').toString(); const parsed = new URL(url);
      if (parsed.origin !== HF || parsed.pathname !== '/api/models' || parsed.username || parsed.password) throw fail('无效的分页地址。');
    } else {
      url = new URL('/api/models', HF); url.searchParams.set('limit', String(Math.max(1, Math.min(1000, Number(limit) || 30))));
      url.searchParams.append('expand', 'tags'); url.searchParams.set('sort', 'downloads'); url.searchParams.set('direction', '-1');
      if (query) url.searchParams.set('search', String(query).slice(0, 200));
      if (task) url.searchParams.set('pipeline_tag', String(task).slice(0, 100));
      if (license) url.searchParams.set('filter', `license:${String(license).slice(0, 100)}`);
      url = url.href;
    }
    const result = await this.request(url, { signal }); if (!Array.isArray(result.data)) throw fail('HF 返回的模型列表无效。');
    const next = result.headers.get('link')?.match(/<([^>]+)>;\s*rel="next"/)?.[1];
    return { items: result.data.filter(m => !m.private).map(normalize), nextCursor: next ? Buffer.from(new URL(next, HF).href).toString('base64url') : null };
  }
  async detail({ repoId: id, revision: rev = 'main' }) {
    const result = await this.request(`${HF}/api/models/${repoId(id)}/revision/${encodeURIComponent(revision(rev))}?blobs=true`);
    const data = result.data;
    if (!/^[0-9a-f]{40,64}$/.test(data.sha || '')) throw fail('HF 没有返回可固定的提交版本。');
    const files = (data.siblings || []).map(f => ({ path: f.rfilename, size: f.size ?? f.lfs?.size ?? null, sha256: f.lfs?.sha256 || null, gitOid: f.blobId || null }));
    const formats = Object.keys(formatPatterns).filter(format => files.some(f => formatOf(f.path) === format));
    return { ...normalize(data), revision: data.sha, formats: [...formats, 'snapshot', 'file'], files };
  }
  plan(detail, format, filename) {
    if (!detail.formats.includes(format)) throw fail('当前版本没有所选的下载格式。', 'INVALID_FORMAT');
    const siblings = detail.files;
    let files;
    if (format === 'snapshot') {
      files = siblings;
    } else if (format === 'file') {
      files = siblings.filter(file => file.path === filename);
    } else if (format === 'gguf') {
      const chosen = siblings.find(file => file.path === filename && formatOf(file.path) === format);
      if (!chosen) throw fail('请选择清单中的 GGUF 文件。', 'INVALID_FILE');
      const shard = /^(.*)-(\d{5})-of-(\d{5})\.gguf$/i.exec(chosen.path);
      files = [chosen];
      if (shard) {
        const members = new Map(siblings.map(file => [file.path.toLowerCase(), file]));
        const count = Number(shard[3]);
        if (!count || count > 10000) throw fail('GGUF 分片数量无效。', 'INVALID_SHARDS');
        files = Array.from({length: count}, (_, i) => {
          const name = shard[1] + '-' + String(i + 1).padStart(5, '0') + '-of-' + shard[3] + '.gguf';
          const member = members.get(name.toLowerCase());
          if (!member) throw fail('缺少 GGUF 分片 ' + name, 'INCOMPLETE_SHARDS');
          return member;
        });
      }
      if ((/qwen3\.5-4b-gguf$/i.test(detail.repoId) || /gemma-4-e2b-it-gguf$/i.test(detail.repoId)) && !/^(mmproj|mtp)-/i.test(chosen.path)) {
        const projections=siblings.filter(f=>/^mmproj.*\.gguf$/i.test(f.path));
        const proj=projections.find(f=>/Q8_0/i.test(f.path)) || projections.find(f=>/[-_]F16/i.test(f.path)) || projections[0];
        if(proj)files.push(proj);
      }
      files.push(...siblings.filter(f => /^(README(?:\.md)?|NOTICE(?:\..*)?|LICEN[SC]E(?:\..*)?)$/i.test(f.path)));
    } else {
      // Keep the tokenizer, indices, configs and license alongside the chosen weights.
      files = siblings.filter(file => {
        const family = formatOf(file.path);
        if (family) return family === format;
        if (format === 'onnx' && /(?:^|\/)onnx\//i.test(file.path)) return true;
        const index = /^(.*)\.index\.json$/i.exec(file.path);
        if (index && formatOf(index[1])) return formatOf(index[1]) === format;
        return /\.(?:json|txt|md|yaml|yml|jinja2?|model|tiktoken|spm|vocab|merges)$/i.test(file.path) || /(?:^|\/)(?:LICEN[SC]E|NOTICE|COPYING)(?:\..*)?$/i.test(file.path);
      });
    }
    if (!files.length) throw fail('下载清单为空，请重新选择。', 'EMPTY_MANIFEST');
    const paths = new Set();
    files = files.map(file => {
      const name = safeFile(file.path).toLowerCase();
      if (paths.has(name)) throw fail('文件名在 Windows 上冲突：' + file.path, 'INVALID_FILE');
      paths.add(name);
      if (!Number.isSafeInteger(file.size) || file.size < 0 || !(file.sha256 ? /^[a-f0-9]{64}$/.test(file.sha256) : /^[a-f0-9]{40}$/.test(file.gitOid || ''))) throw fail('Hub 未提供文件大小或可验证的摘要：' + file.path, 'INVALID_MANIFEST');
      return {...file, url: resolveUrl(detail.repoId, detail.revision, file.path)};
    });
    for (const item of paths) {
      const parts = item.split('/');
      while (parts.length > 1) {
        parts.pop();
        if (paths.has(parts.join('/'))) throw fail('文件与目录路径冲突。', 'INVALID_FILE');
      }
    }
    return {repoId: detail.repoId, revision: detail.revision, license: detail.license, task: detail.task, format, filename, files, totalBytes: files.reduce((n, f) => n + f.size, 0)};
  }
}
module.exports = { HubClient, repoId, revision, safeFile, resolveUrl, normalize, fail, allowedDownload };
