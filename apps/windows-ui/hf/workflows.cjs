'use strict';
const { createHash, randomUUID } = require('node:crypto');
const { createReadStream } = require('node:fs');
const { open } = require('node:fs/promises');
const kinds = ['image', 'video', 'audio'];
const labels = { image: '商品图片', video: '商品视频', audio: '中文配音' };
const media = { image: 'image/png', video: 'video/mp4', audio: 'audio/wav' };
const uid = () => randomUUID().replaceAll('-', '');
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const page = items => ({ items, next_cursor: null });
const timestamp = () => new Date().toISOString();
function workflowEligible(info) {
  const recipe = require('./generation-packages.cjs').recipe(info.packageId || info.generation_package || info.nativeRecipe, !!info.nativeRecipe);
  if (info.kind === 'video') return ['h3-video', 'animatediff-sd15'].includes(info.pipeline);
  if (info.kind === 'image') return !recipe?.imageReference && !['mosr-x4', 'esrgan-x4'].includes(info.pipeline);
  if (info.kind === 'audio') return !recipe?.requiresReference && (!info.pipeline || ['audiocpp-tts','llama-tts'].includes(info.pipeline));
  return false;
}

function note(run, action, details = {}) {
  run.history.push({ action, created_at: timestamp(), revision: run.revision, ...details });
}
function view({ commands, ...run }) { return run; }
function newTask(run, kind) {
  const step = run.steps[kind];
  const configuration = structuredClone(step.configuration);
  const upstream = kinds.slice(0, kinds.indexOf(kind)).map(parent => run.steps[parent].accepted);
  if (kind === 'video') configuration.input.material_id = upstream[0].material_id;
  const stepId = uid();
  const task = {
    id: 'task-wf-' + run.id.slice('workflow-'.length) + '-' + stepId, project_id: run.project_id,
    kind, operation: 'generate', name: run.name + ' · ' + labels[kind], created_at: timestamp(),
    draft_revision: 1, immutable_draft: true,
    workflow_ref: { workflow_run_id: run.id, step_id: kind, step_attempt_id: stepId, upstream_refs: upstream },
    draft: { ...configuration, kind, operation: 'generate', dataset_id: null },
  };
  Object.assign(step, { task_id: task.id, step_attempt_id: stepId, input_revision: step.input_revision + 1,
    input_digest: digest([task.draft, upstream]), accepted: null, stale: false });
  run.step_attempts.push({ id: stepId, mode: 'compute', task, attempt_id: null, source: null });
  run.current_step = kind;
  run.status = 'active';
  run.result_id = null;
  note(run, 'input_created', { step_id: kind, input_revision: step.input_revision, task_id: task.id });
}

class Workflows {
  constructor(trials) {
    this.trials = trials;
    this.pending = Promise.resolve();
    // A process can exit after the queue persisted the attempt but before the run recorded its ID.
    const byTask = new Map(trials.list('attempt').map(attempt => [attempt.task_id, attempt]));
    for (const run of trials.list('workflow')) {
      for (const record of run.step_attempts) {
        if (record.mode !== 'compute' || !record.task) continue;
        const attempt = byTask.get(record.task.id);
        if (!record.attempt_id && attempt) this.recordSubmission(run, record, attempt);
      }
    }
  }
  handles(path) {
    return /^\/(?:workflow-runs|workflow-tasks)(?:\/|$)/.test(path) || path.startsWith('/tasks/task-wf-');
  }
  request(request, url) {
    // Preflights and artifact verification can yield between the revision check and the write.
    const result = this.pending.then(() => this.dispatch(request, url));
    this.pending = result.catch(() => {});
    return result;
  }
  configuration(project, kind, config) {
    const info = this.trials.resolve(config?.model_id, project).info;
    if (info.kind !== kind) throw Error('所选模型与工作流步骤不匹配。');
    if (kind === 'video' && !['h3-video', 'animatediff-sd15'].includes(info.pipeline))
      throw Error('请选择可同时使用首帧图片和视频描述的模型。');
    if (!workflowEligible(info)) throw Error('此模型需要其他输入或产生其他类型的输出。');
    const input = {};
    for (const field of kind === 'image' ? ['prompt', 'negative_prompt'] : ['prompt']) {
      const value = config.input?.[field] ?? '';
      if (typeof value !== 'string' || value.length > (kind === 'audio' ? 120 : 2000))
        throw Error('请检查' + labels[kind] + '的输入长度。');
      input[field] = value;
    }
    if (kind === 'video' && /^@素材[ \t]/.test(input.prompt)) throw Error('工作流自动使用上一步的图片，请直接填写视频描述。');
    if (!input.prompt.trim() && info.pipeline !== 'animatediff-sd15') throw Error('请填写' + labels[kind] + '的文字内容。');
    const device = config.runtime?.device_id;
    return { model_id: config.model_id, input, runtime: { ...config.runtime, engine: 'ailab-gguf',
      device_id: !device || device === 'apple-gpu' ? 'cpu' : device } };
  }
  create(body, key) {
    if (!/^project-[\w-]+$/.test(body.project_id) || body.definition_version !== 'product-story-v1' ||
        typeof body.name !== 'string' || !body.name.trim() || body.name.length > 120) throw Error('请检查工作流名称和项目。');
    const id = 'workflow-' + digest([body.project_id, key]).slice(0, 32);
    const existing = this.trials.rows.get(id);
    if (existing) {
      if (existing.commands[key] !== digest(body)) throw Error('工作流创建请求与原记录不同。');
      return view(existing);
    }
    const steps = Object.fromEntries(kinds.map(kind => [kind, { configuration: this.configuration(body.project_id, kind, body.steps?.[kind]),
      input_revision: 0, input_digest: null, task_id: null, step_attempt_id: null, accepted: null, stale: false }]));
    const run = { id, name: body.name.trim(), project_id: body.project_id, definition_version: body.definition_version,
      steps, step_attempts: [], history: [], revision: 1, created_at: timestamp(), commands: { [key]: digest(body) } };
    newTask(run, 'image');
    return view(this.trials.save(run));
  }
  async artifact(project, kind, attemptId, artifactId) {
    const attempt = this.trials.rows.get(attemptId);
    const file = attempt?.artifacts?.find(item => item.id === artifactId && item.media_type === media[kind]);
    if (!file || attempt.state !== 'succeeded' || attempt.project_id !== project || attempt.snapshot.kind !== kind)
      throw Error('请选择本项目中已成功生成的对应作品。');
    const hash = createHash('sha256');
    for await (const chunk of createReadStream(file.path)) hash.update(chunk);
    if (hash.digest('hex') !== file.sha256) throw Error('作品文件已变化。');
    return { attempt, file };
  }
  async advance(run, body) {
    const kind = run.current_step;
    const step = run.steps[kind];
    const record = run.step_attempts.find(item => item.id === step?.step_attempt_id);
    if (!record || body.step_attempt_id !== record.id || body.input_revision !== step.input_revision || body.artifact_ids?.length !== 1)
      throw Error('步骤或输入版本已变化，请刷新工作流。');
    const [artifactId] = body.artifact_ids;
    if (record.source && record.source.artifact_id !== artifactId) throw Error('复用作品与所选产物不匹配。');
    const { attempt, file } = await this.artifact(run.project_id, kind, record.source?.attempt_id || record.attempt_id, artifactId);
    const work = await this.trials.request({ method: 'POST', path: '/works', body: { project_id: run.project_id, attempt_id: attempt.id, artifact_id: file.id } });
    const accepted = { step_id: kind, step_attempt_id: record.id, input_revision: step.input_revision, attempt_id: attempt.id,
      artifact_id: file.id, artifact_sha256: file.sha256, work_id: work.id, mode: record.mode, computed: record.mode === 'compute' };
    if (kind === 'image') {
      const materialId = file.id.replace(/^artifact-/, 'material-');
      if (!this.trials.rows.has(materialId)) {
        const handle = await open(file.path, 'r');
        const header = Buffer.alloc(24);
        try {
          const { bytesRead } = await handle.read(header, 0, header.length, 0);
          if (bytesRead !== header.length || header.toString('ascii', 12, 16) !== 'IHDR') throw Error('首帧 PNG 文件不完整。');
        } finally { await handle.close(); }
        this.trials.save({ id: materialId, project_id: run.project_id, kind: 'image',
        name: run.name + ' · 首帧', status: 'ready', format: 'png', media_type: file.media_type, path: file.path,
        width: header.readUInt32BE(16), height: header.readUInt32BE(20), version_id: file.sha256,
        manifest_digest: file.sha256, total_bytes: file.size, source_work_id: work.id, created_at: timestamp() });
      }
      accepted.material_id = materialId;
    }
    step.accepted = accepted;
    note(run, 'accepted', { step_id: kind, artifact_id: file.id });
    const next = kinds[kinds.indexOf(kind) + 1];
    if (next) newTask(run, next);
    else { run.status = 'ready_to_save'; run.current_step = null; }
  }
  async mutate(run, method, action, body) {
    const revision = /^steps\/(image|video|audio)\/input$/.exec(action);
    if (method === 'PATCH' && revision) {
      const kind = revision[1];
      const step = run.steps[kind];
      if (!step.input_revision || step.stale) throw Error('请先完成上游步骤。');
      for (const name of kinds.slice(kinds.indexOf(kind))) {
        const downstream = run.steps[name];
        const record = run.step_attempts.find(item => item.id === downstream.step_attempt_id);
        if (this.busy(record)) throw Error('请先完成或停止正在运行的步骤。');
        if (name !== kind && downstream.input_revision) {
          downstream.stale = true; downstream.accepted = null;
          note(run, 'invalidated', { step_id: name });
        }
      }
      step.configuration = this.configuration(run.project_id, kind, body.configuration);
      newTask(run, kind);
    } else if (method === 'POST' && action === 'advance') {
      await this.advance(run, body);
    } else if (method === 'POST' && action === 'reuse-output') {
      const kind = run.current_step;
      const step = run.steps[kind];
      const record = run.step_attempts.find(item => item.id === step?.step_attempt_id);
      if (!step || body.step_id !== kind || body.input_revision !== step.input_revision || this.busy(record)) throw Error('当前步骤无法复用此作品。');
      const { attempt, file } = await this.artifact(run.project_id, kind, body.source_attempt_id, body.artifact_id);
      const current = record.task?.draft || record.source.differences.current;
      const source = { attempt_id: attempt.id, artifact_id: file.id, selected_at: timestamp(), differences: { original: attempt.snapshot, current } };
      const reused = { id: uid(), mode: 'reused', attempt_id: null, source };
      run.step_attempts.push(reused);
      Object.assign(step, { step_attempt_id: reused.id, task_id: null });
      note(run, 'reused', { step_id: kind, artifact_id: file.id });
    } else if (method === 'POST' && action === 'save') {
      if (run.status !== 'ready_to_save') throw Error('请先接受三个步骤的结果。');
      for (const kind of kinds) {
        const accepted = run.steps[kind].accepted;
        await this.artifact(run.project_id, kind, accepted.attempt_id, accepted.artifact_id);
      }
      run.status = 'saved'; run.result_id = 'result-' + uid(); note(run, 'saved');
    } else throw Error('未知工作流操作。');
  }
  busy(record) {
    return ['running', 'queued', 'cancelling'].includes(this.trials.rows.get(record?.attempt_id)?.state);
  }
  recordSubmission(run, record, attempt) {
    record.attempt_id = attempt.id;
    run.revision++;
    note(run, 'submitted', { step_id: record.task.kind, attempt_id: attempt.id });
    this.trials.save(run);
  }
  async taskRequest(run, taskId, action, request) {
    const record = run.step_attempts.find(item => item.task?.id === taskId);
    if (!record) throw Error('工作流任务不存在。');
    const { task } = record;
    const attempts = this.trials.list('attempt', run.project_id).filter(attempt => attempt.task_id === taskId).map(attempt => this.trials.view(attempt));
    if (request.method === 'GET') {
      if (action === 'attempts') return page(attempts);
      if (!action) return { ...task, attempts, latest_attempt: attempts[0] };
    }
    if (request.method !== 'POST' || !['preflight', 'attempts'].includes(action) ||
        run.current_step !== task.kind || run.steps[task.kind].step_attempt_id !== record.id) throw Error('只能运行当前版本的工作流步骤。');
    if (action === 'preflight') return this.trials.check(task);
    const previous = attempts[0];
    if (previous && previous.idempotency_key !== request.idempotencyKey) throw Error('此步骤已提交。要重做请创建新输入版本。');
    const attempt = previous || this.trials.submit(task, request.body, request.idempotencyKey);
    if (!record.attempt_id) this.recordSubmission(run, record, attempt);
    return attempt;
  }
  async dispatch(request, url) {
    const { method, body = {}, idempotencyKey: key } = request;
    const route = url.pathname;
    const project = url.searchParams.get('project_id');
    if (route === '/workflow-runs' && method === 'GET') return page(this.trials.list('workflow', project).map(view));
    if (route === '/workflow-tasks' && method === 'GET') return page(this.trials.list('workflow', project).flatMap(run => run.step_attempts.flatMap(record => record.task || [])));
    const task = /^\/tasks\/(task-wf-([a-f0-9]{32})-[a-f0-9]{32})(?:\/(\w+))?$/.exec(route);
    if (method !== 'GET' && !task && (typeof key !== 'string' || !/^[\w-]{1,160}$/.test(key))) throw Error('工作流请求编号无效。');
    if (route === '/workflow-runs' && method === 'POST') return this.create(body, key);
    const match = /^\/workflow-runs\/(workflow-[a-f0-9]{32})(?:\/(.+))?$/.exec(route);
    const stored = this.trials.rows.get(task ? 'workflow-' + task[2] : match?.[1]);
    if (!stored || (project && stored.project_id !== project)) throw Error('工作流不存在。');
    const run = structuredClone(stored);
    if (task) return this.taskRequest(run, task[1], task[3], request);
    if (method === 'GET' && !match[2]) return view(run);
    const fingerprint = digest([method, route, body]);
    if (Object.hasOwn(run.commands, key)) {
      if (run.commands[key] !== fingerprint) throw Error('重试请求与原操作不匹配。');
      return view(run);
    }
    if (run.revision !== body.expected_revision) throw Error('工作流版本已更新，请刷新重试。');
    run.revision++;
    await this.mutate(run, method, match[2], body);
    run.commands[key] = fingerprint;
    return view(this.trials.save(run));
  }
}
module.exports = { Workflows, workflowEligible };
