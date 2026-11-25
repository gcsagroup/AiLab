'use strict';
const { createHash } = require('node:crypto');
const { HubClient, fail } = require('./hub.cjs');
const { Downloads } = require('./downloads.cjs');
const languageSources = {...require('./language-releases.json'), ...require('./language-sources.json')};
const starters = ['Qwen/Qwen2.5-0.5B-Instruct-GGUF', 'unsloth/Qwen3.5-4B-GGUF', 'ggml-org/gemma-4-E2B-it-GGUF', 'unsloth/MiniMax-H3-Image-GGUF', 'leejet/MiniMax-H3-GGUF', 'Qwen/Qwen2.5-0.5B-Instruct', 'HuggingFaceTB/SmolLM2-135M-Instruct', 'EleutherAI/pythia-70m', 'google/flan-t5-small', 'allenai/OLMo-1B-hf', 'microsoft/phi-1_5', 'mistralai/Mistral-7B-Instruct-v0.3', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B'];
const quantizations = {
  'gradium/phonon-31m-en':'gradium/phonon-31m-en-audiocpp',
  'ekwek/soprano-1.1-80m':'WalkingCat/Soprano-1.1-80M-GGUF',
  'supertone/supertonic-3':'audio-cpp/audio.cpp-gguf',
  'openbmb/voxcpm-0.5b':'audio-cpp/audio.cpp-gguf',
  'circlestone-labs/anima':'JusteLeo/Anima2-GGUF',
  'swiss-ai/apertus-8b-instruct-2509':'mradermacher/Apertus-8B-Instruct-2509-GGUF',
  'speridlabs/iris-3b':'realrebelai/iris-3b_GGUFs',
  'wan-ai/wan2.1-t2v-1.3b':'samuelchristlie/Wan2.1-T2V-1.3B-GGUF',
  'qwen/qwen3.5-4b':'unsloth/Qwen3.5-4B-GGUF',
  'google/gemma-4-e2b-it':'ggml-org/gemma-4-E2B-it-GGUF',
  'minimaxai/minimax-h3-image':'unsloth/MiniMax-H3-Image-GGUF',
  'minimaxai/minimax-h3':'leejet/MiniMax-H3-GGUF',
};
const defaultGguf = {
  'justeleo/anima2-gguf': 'anima-preview2_q3_K_M.gguf',
  'walkingcat/soprano-1.1-80m-gguf': 'Soprano-1.1-80M-GGUF/soprano-1.1-80m-q8_0.gguf',
  'gradium/phonon-31m-en-audiocpp': 'phonon-31m-en-q8_0.gguf',
  'realrebelai/iris-3b_ggufs': 'Iris-3B-Q3_K_S.gguf',
  'samuelchristlie/wan2.1-t2v-1.3b-gguf': 'Wan2.1-T2V-1.3B-Q4_0.gguf',
  'leejet/minimax-h3-gguf': 'minimax_h3_fl2va_pruned-Q4_K_M.gguf',
  'unsloth/minimax-h3-image-gguf': 'minimax_h3_image_pruned-Q2_K.gguf',
};
const handled = data => ({ handled: true, data });
function partialWeight(repo,name) {
  return /(?:^|\/)patch-(?:ud-)?i?q[1-8][^/]*\//i.test(name) ||
    /[-_.](?:patch|overlay)(?:-\d{5}-of-\d{5})?\.gguf$/i.test(name) ||
    /(?:^|[-_/])tokenizer\.gguf$/i.test(name) ||
    (repo.toLowerCase()==='anemll/glm-5.2-sidecar' && name==='dense/model-dense.gguf') ||
    (repo.toLowerCase()==='hyukudan/deepseek-v4.1-flash-1017-strix-dense-u6' && name==='c-u6.gguf');
}
const quantizationPattern = '(?:UD-)?(?:[IT]?Q[1-8](?:[_-][a-z0-9]+)*|BF16|F16|F32|MXFP4(?:_MOE)?)';
const quantizationFolder = new RegExp('^'+quantizationPattern+'$','i');
const quantizationSuffix = new RegExp('[-_.]'+quantizationPattern+'\\.gguf$','i');
function checkpointPath(file) {
  return file.toLowerCase().replace(/-\d{5}-of-\d{5}(?=\.gguf$)/,'')
    .split('/').filter(part=>!quantizationFolder.test(part)).join('/').replace(quantizationSuffix,'.gguf');
}
// These GGUFs share a repository with unrelated models. Keep official cards scoped to their own package.
const packagedAudio = {
  'supertone/supertonic-3': 'Supertonic-3-GGUF/supertonic-3-f16.gguf',
  'openbmb/voxcpm-0.5b': 'VoxCPM1-GGUF/voxcpm-0.5b-q8_0-audiovae-f16.gguf',
};
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

function catalog(job) {
  const files = job.files.map(({path, size, sha256, gitOid, url}) => ({path, size, sha256, gitOid, url}));
  const id = digest([job.repoId, job.revision, job.format, files]);
  return { id, manifest_digest: id, repo: job.repoId, name: job.repoId, revision: job.revision, format: job.format,
    source_url: 'https://huggingface.co/' + job.repoId + '/tree/' + job.revision, license: job.license,
    total_bytes: job.totalBytes, files, network_scope: '从 Hugging Face 官方站点及其文件分发服务下载。',
    capability: job.generationRecipe === 'convert' ? '下载原始组件，试用时在本机转换为 GGUF。' : job.generationRecipe ? '下载并核验此配方的主模型与配套组件。' : job.files.some(f=>f.role && /\.safetensors$/i.test(f.path)) ? '下载并核验组件，加入模型库时离线转换为 GGUF。' :
      job.files.some(f=>f.role) ? '下载并核验主模型和配套 GGUF 组件。' : '只下载并保存清单中的文件。' };
}

class OfficialModels {
  constructor({dataDir, hub = new HubClient(), catalogPath}) {
    this.hub = hub;
    if (process.env.HF_TOKEN) this.hub.setToken(process.env.HF_TOKEN);
    this.downloads = new Downloads({dataDir, hub});
    const {Trials}=require('./trials.cjs');
    this.trials=new Trials(require('node:path').join(dataDir,'trials'),this.downloads);
    this.workflows = new (require('./workflows.cjs').Workflows)(this.trials);
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

  async inspectLanguage(language,filename) {
    const matches=name=>checkpointPath(name)===checkpointPath(language.filename);
    if (filename && !matches(filename)) throw fail('请选择当前语言模型的量化文件。','INVALID_FILE');
    const entry=await this.inspect(language.repo,'gguf',filename || language.filename,language);
    if (!filename || filename===language.filename) {
      const main=entry.files.find(f=>f.path===language.filename);
      if (!main || main.sha256!==language.sha256) throw fail('发布版本与已验证的 GGUF 文件不匹配。','MODEL_CATALOG_CHANGED');
    }
    return {...entry,variants:entry.variants.filter(matches)};
  }

  async inspect(repo, format, filename, {revision = 'main', projector} = {}) {
    const id = repo || starters[0];
    const language = revision === 'main' ? languageSources[id.toLowerCase()] : undefined;
    if (language?.repo.toLowerCase()===id.toLowerCase() && (!format || format==='gguf') && !filename) {
      return this.inspectLanguage(language);
    }
    const cacheKey = JSON.stringify([id, revision]);
    let detail = this.details.get(cacheKey);
    if (!detail || Date.now() - detail.readAt > 60000) {
      try {
        detail = {...await this.hub.detail({repoId: id, revision}), readAt: Date.now()};
      } catch (error) {
        if (language && (!format || format==='gguf') && [401,403,404].includes(error.status))
          return {...await this.inspectLanguage(language,filename),formats:['gguf']};
        throw error;
      }
      this.details.set(cacheKey, detail);
      if (this.details.size > 8) this.details.delete(this.details.keys().next().value);
    }
    const quantized=quantizations[id.toLowerCase()];
    const generation = require('./generation-packages.cjs');
    const derived = generation.sourceChoices(id);
    // Phonon also publishes GGUFs for its own runtime. Keep those downloadable alongside the audio.cpp build.
    const phononFile = 'phonon-31m-en-q8_0.gguf';
    const nativePhonon = id.toLowerCase() === 'gradium/phonon-31m-en' && detail.formats.includes('gguf');
    if (nativePhonon && (!format || format === 'gguf') && (!filename || filename === phononFile)) {
      const entry = await this.inspect(quantized, 'gguf', phononFile);
      const original = detail.files.filter(f => /\.gguf$/i.test(f.path)).map(f => f.path);
      return {...entry, formats:detail.formats, variants:[...new Set([phononFile,...original])]};
    }
    if(quantized && !detail.formats.includes('gguf')){
      if(!format || format==='gguf'){
        const packaged = packagedAudio[id.toLowerCase()];
        if (packaged && filename && filename !== packaged) throw fail('请选择当前模型的 GGUF 文件。','INVALID_FILE');
        const additional=packaged ? [] : derived.filter(f=>f.repo.toLowerCase()!==quantized.toLowerCase() && f.repo.toLowerCase()!==id.toLowerCase());
        if (additional.length) {
          const variant=additional.find(f=>f.path===filename);
          const primary=await this.inspect(quantized,'gguf',variant ? undefined : filename);
          const entry=variant ? await this.inspect(variant.repo,'gguf',variant.path) : primary;
          return {...entry,formats:['gguf',...detail.formats],variants:[...new Set([...(primary.variants || []),...additional.map(f=>f.path)])]};
        }
        const entry=await this.inspect(quantized,'gguf',packaged || filename);
        return {...entry, ...(packaged ? {variants:[packaged]} : {}), formats:['gguf',...detail.formats]};
      }
      detail={...detail,formats:['gguf',...detail.formats]};
    }
    if (derived.length && !detail.formats.includes('gguf')) {
      if (!format || format==='gguf') {
        const selected=filename ? derived.find(f=>f.path===filename) : derived[0];
        if (!selected && !language) throw fail('请选择此发行模型的量化文件。','INVALID_FILE');
        const entry=selected ? await this.inspect(selected.repo,'gguf',selected.path) : await this.inspectLanguage(language,filename);
        const variants=derived.map(f=>f.path);
        if (language) variants.push(...(selected ? [language.filename] : entry.variants));
        return {...entry,formats:['gguf',...detail.formats],variants:[...new Set(variants)]};
      }
      detail={...detail,formats:['gguf',...detail.formats]};
    }
    if (language && !detail.formats.includes('gguf')) {
      if (!format || format==='gguf') {
        return {...await this.inspectLanguage(language,filename),formats:['gguf',...detail.formats]};
      }
      detail={...detail,formats:['gguf',...detail.formats]};
    }
    const convertible = generation.convertiblePrimaries(detail.repoId, detail.files).map(f => f.path);
    if (convertible.length && !detail.formats.includes('gguf')) detail={...detail,formats:['gguf',...detail.formats]};
    format ||= detail.formats[0];
    let variants = [];
    if (format === 'gguf') variants = detail.files.filter(f => /\.gguf$/i.test(f.path) && !/-(?!00001)\d{5}-of-\d{5}\.gguf$/i.test(f.path)).map(f => f.path);
    if (nativePhonon && format === 'gguf' && !variants.includes(phononFile)) variants.unshift(phononFile);
    if (format === 'gguf') variants.push(...convertible);
    if (format === 'file') variants = detail.files.map(f => f.path);
    const preferred = defaultGguf[detail.repoId.toLowerCase()];
    const standalone=variants.filter(f=>!partialWeight(detail.repoId,f) && !/(?:^|\/)(?:mmproj|mtp)[-_.]/i.test(f));
    const selected = filename || (format === 'gguf' && ((variants.includes(preferred) && preferred) ||
      standalone.find(f=>/q4_k_m/i.test(f)) || standalone.find(f=>/q4_0/i.test(f)) || standalone[0])) || variants[0] || null;
    let plan;
    const convert = format === 'gguf' && convertible.includes(selected);
    try {
      plan = this.hub.plan(detail, convert ? 'file' : format, selected, {projector});
      if (convert) Object.assign(plan,{format,filename:selected});
    }
    catch (error) {
      return { id: '', manifest_digest: '', repo: detail.repoId, name: detail.repoId, revision: detail.revision,
        source_url: 'https://huggingface.co/' + detail.repoId + '/tree/' + detail.revision, license: detail.license,
        files: [], total_bytes: 0, format, formats: detail.formats, variants, filename: selected,
        gated: detail.gated, selection_error: error.message };
    }
    if(format==='gguf') {
      const pinned=generation.planFiles(detail.repoId,plan.files.find(f=>f.path===selected),detail.revision);
      if (pinned) {
        plan.generationRecipe=convert ? 'convert' : 'weights';
        const docs=plan.files.filter(f=>/^(README(?:\.md)?|LICENSE(?:\.txt)?)$/i.test(f.path));
        plan.files=[...pinned,...docs];
        plan.totalBytes=plan.files.reduce((sum,f)=>sum+f.size,0);
      }
    }
    if(format==='gguf') {
      const members=require('./h3-weights.cjs').sources(detail.repoId,selected);
      if(members.length) {
        plan.files.push(...members);
        plan.totalBytes+=members.reduce((sum,f)=>sum+f.size,0);
        if (members.some(member => member.role === 'encoder')) plan.license+=' · MiniMax H3 Community License（含 Pruna 文本编码器）';
      }
    }
    const entry = catalog(plan);
    if (format==='gguf' && selected && partialWeight(detail.repoId,selected))
      entry.capability='可下载模型组件。独立试用需要发布者指定的完整基础模型与配套权重。';
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
    if (this.workflows.handles(url.pathname)) return handled(await this.workflows.request(request, url));
    if (/^\/(?:models|materials|devices|capabilities|environment|attempts|artifacts|works)(?:\/|$)/.test(url.pathname) || /^\/tasks\/task-[\w-]+\/(?:attempts|preflight)$/.test(url.pathname))
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
