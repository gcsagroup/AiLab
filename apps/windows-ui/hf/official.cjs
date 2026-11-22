'use strict';
const { createHash } = require('node:crypto');
const { HubClient, fail } = require('./hub.cjs');
const { Downloads } = require('./downloads.cjs');
const starters = ['Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'unsloth/Qwen3.5-4B-GGUF', 'ggml-org/gemma-4-E2B-it-GGUF', 'unsloth/MiniMax-H3-Image-GGUF', 'leejet/MiniMax-H3-GGUF', 'Qwen/Qwen2.5-0.5B-Instruct', 'HuggingFaceTB/SmolLM2-135M-Instruct', 'EleutherAI/pythia-70m', 'google/flan-t5-small', 'allenai/OLMo-1B-hf', 'microsoft/phi-1_5', 'mistralai/Mistral-7B-Instruct-v0.3', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B'];
const quantizations = {
  'qwen/qwen3.5-4b':'unsloth/Qwen3.5-4B-GGUF',
  'google/gemma-4-e2b-it':'ggml-org/gemma-4-E2B-it-GGUF',
  'minimaxai/minimax-h3-image':'unsloth/MiniMax-H3-Image-GGUF',
  'minimaxai/minimax-h3':'leejet/MiniMax-H3-GGUF',
};
const handled = data => ({ handled: true, data });
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function catalog(job) {
  const files = job.files.map(({path, size, sha256, gitOid, url}) => ({path, size, sha256, gitOid, url}));
  const id = digest([job.repoId, job.revision, job.format, files]);
  return { id, manifest_digest: id, repo: job.repoId, name: job.repoId, revision: job.revision, format: job.format,
    source_url: 'https://huggingface.co/' + job.repoId + '/tree/' + job.revision, license: job.license,
    total_bytes: job.totalBytes, files, network_scope: '从 Hugging Face 官方站点及其文件分发服务下载。',
    capability: job.files.some(f=>f.role) ? '下载并核验组件，加入模型库时离线转换为 GGUF。' : '只下载并保存清单中的文件。' };
}

class OfficialModels {
  constructor({dataDir, hub = new HubClient(), catalogPath}) {
    this.hub = hub;
    if (process.env.HF_TOKEN) this.hub.setToken(process.env.HF_TOKEN);
    this.downloads = new Downloads({dataDir, hub});
    const {Trials}=require('./trials.cjs');
    this.trials=new Trials(require('node:path').join(dataDir,'trials'),this.downloads);
    this.plans = new Map();
    this.catalogPath = catalogPath;
    this.repoNames = null;
    this.details = new Map();
  }

  async searchLocal(q, offset) {
    if (!this.repoNames) {
      const {readFile} = require('node:fs/promises');
      const {gunzip} = require('node:zlib');
      const {promisify} = require('node:util');
      this.repoNames = readFile(this.catalogPath).then(bytes => promisify(gunzip)(bytes))
        .then(text => text.toString('utf8').trimEnd().split('\n')).catch(error => { this.repoNames = null; throw error; });
    }
    const names = await this.repoNames;
    const items = [];
    let index = offset;
    const query = q.toLowerCase();
    for (; index < names.length && items.length < 50; index++) {
      if (names[index].toLowerCase().includes(query)) items.push(names[index]);
    }
    return {items, next_cursor: index < names.length ? 'local-' + index : null};
  }

  async inspect(repo, format, filename) {
    const id = repo || starters[0];
    let detail = this.details.get(id);
    if (!detail || Date.now() - detail.readAt > 60000) {
      detail = {...await this.hub.detail({repoId: id}), readAt: Date.now()};
      this.details.set(id, detail);
      if (this.details.size > 8) this.details.delete(this.details.keys().next().value);
    }
    const quantized=quantizations[id.toLowerCase()];
    if(quantized && !detail.formats.includes('gguf')){
      if(!format || format==='gguf'){
        const entry=await this.inspect(quantized,'gguf',filename);
        return {...entry,formats:['gguf',...detail.formats]};
      }
      detail={...detail,formats:['gguf',...detail.formats]};
    }
    format ||= detail.formats[0];
    let variants = [];
    if (format === 'gguf') variants = detail.files.filter(f => /\.gguf$/i.test(f.path) && !/-(?!00001)\d{5}-of-\d{5}\.gguf$/i.test(f.path)).map(f => f.path);
    if (format === 'file') variants = detail.files.map(f => f.path);
    const preferred=detail.repoId.toLowerCase()==='leejet/minimax-h3-gguf'?'minimax_h3_fl2va_pruned-Q4_K_M.gguf':
      detail.repoId.toLowerCase()==='unsloth/minimax-h3-image-gguf'?'minimax_h3_image_pruned-Q2_K.gguf':null;
    const selected = filename || (format === 'gguf' && ((variants.includes(preferred) && preferred) ||
      variants.find(f => !/^(mmproj|mtp)-/i.test(f) && /q4_k_m/i.test(f)) || variants.find(f=>!/^mmproj/i.test(f) && /q4_0/i.test(f)))) || variants[0] || null;
    let plan;
    try { plan = this.hub.plan(detail, format, selected); }
    catch (error) {
      return { id: '', manifest_digest: '', repo: detail.repoId, name: detail.repoId, revision: detail.revision,
        source_url: 'https://huggingface.co/' + detail.repoId + '/tree/' + detail.revision, license: detail.license,
        files: [], total_bytes: 0, format, formats: detail.formats, variants, filename: selected,
        gated: detail.gated, selection_error: error.message };
    }
    if(format==='gguf') {
      const members=require('./h3-weights.cjs').sources(detail.repoId,selected);
      if(members.length) {
        plan.files.push(...members);
        plan.totalBytes+=members.reduce((sum,f)=>sum+f.size,0);
        plan.license+=' · MiniMax H3 Community License（含 Pruna 文本编码器）';
      }
    }
    const entry = catalog(plan);
    this.plans.set(entry.id, plan);
    if (this.plans.size > 32) this.plans.delete(this.plans.keys().next().value);
    return {...entry, formats: detail.formats, variants, filename: selected, gated: detail.gated};
  }

  record(job) {
    return {id: job.id, project_id: job.projectId, name: job.filename ? job.repoId + ' · ' + job.filename : job.repoId, state: job.status === 'paused' ? 'cancelled' : job.status,
      received_bytes: job.downloadedBytes, total_bytes: job.totalBytes, current_file: job.currentFile || null,
      cancel_requested: this.downloads.active.get(job.id)?.controller.signal.aborted || false,
      model_id: job.registeredAt ? job.modelId : null, created_at: job.createdAt,
      error: job.error ? {code: 'MODEL_DOWNLOAD', message: job.error} : null};
  }

  async request(request) {
    const url = new URL(request.path, 'https://ailab.invalid');
    const {method, body, idempotencyKey} = request;
    const project = url.searchParams.get('project_id');
    if (/^\/(?:models|materials|devices|capabilities|attempts|artifacts|works)(?:\/|$)/.test(url.pathname) || /^\/tasks\/task-[\w-]+\/(?:attempts|preflight)$/.test(url.pathname))
      return handled(await this.trials.request(request));
    if (method === 'GET' && url.pathname === '/model-catalog/search') {
      const q = (url.searchParams.get('q') || '').trim();
      if (!q) return handled({items: starters, next_cursor: null});
      const cursor = url.searchParams.get('cursor') || '';
      if (cursor.startsWith('local-')) {
        const offset = Number(cursor.slice(6));
        if (!Number.isSafeInteger(offset) || offset < 0) throw fail('无效的查询页码。', 'INVALID_CURSOR');
        return handled(await this.searchLocal(q, offset));
      }
      try {
        const page = await this.hub.search({query: q, cursor, limit: 35});
        const live = page.items.map(model => model.repoId);
        return handled({items: live, next_cursor: page.nextCursor || null});
      } catch (error) {
        if (!this.catalogPath || cursor) throw error;
        return handled(await this.searchLocal(q, 0));
      }
    }
    if (method === 'GET' && url.pathname === '/model-catalog') {
      const id = url.searchParams.get('download');
      if (id) return handled({items: [catalog(this.downloads.get(id))]});
      return handled({items: [await this.inspect(url.searchParams.get('repo'), url.searchParams.get('format'), url.searchParams.get('filename'))]});
    }
    if (method === 'POST' && url.pathname === '/model-downloads') {
      if (!body || !/^project-[a-zA-Z0-9-]+$/.test(body.project_id) || typeof idempotencyKey !== 'string' || !idempotencyKey) throw fail('无效的项目或下载请求。','INVALID_REQUEST');
      const previous = this.downloads.records(body.project_id).find(job => job.manifestDigest === body.manifest_digest && body.manifest_digest === body.catalog_id);
      if (previous) return handled(this.record(previous));
      const plan = this.plans.get(body.catalog_id);
      if (!plan || body.manifest_digest !== body.catalog_id) throw fail('请重新选择模型并核对文件清单。','MODEL_CATALOG_CHANGED');
      const job = await this.downloads.create(plan, body.project_id, body.manifest_digest);
      return handled(this.record(job));
    }
    if (method === 'GET' && url.pathname === '/model-downloads') return handled({items: this.downloads.records(project).map(job => this.record(job)), next_cursor: null});
    const match = /^\/model-downloads\/(download-[0-9a-f]{24})(?:\/(cancel|resume|models))?$/.exec(url.pathname);
    if (!match) throw fail('未知的模型下载请求。', 'INVALID_REQUEST');
    const job = this.downloads.get(match[1]);
    if (project && job.projectId !== project) throw fail('此下载属于其他项目。','RESOURCE_NOT_FOUND');
    if (method === 'GET' && !match[2]) return handled(this.record(job));
    if (method === 'POST' && match[2] === 'models') { await this.downloads.register(job.id); return handled(this.trials.describe(job)); }
    if (method === 'POST' && match[2] === 'resume') return handled(this.record(await this.downloads.resume(job.id)));
    if (method === 'POST' && match[2] === 'cancel') return handled(this.record(await this.downloads.pause(job.id)));
    throw fail('未知的模型下载操作。','INVALID_REQUEST');
  }

  async close() { await Promise.all([this.downloads.shutdown(),this.trials.close()]); }
}
module.exports = { OfficialModels };
