const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { randomUUID, createHash } = require('node:crypto');
const { OfficialModels } = require('../../apps/windows-ui/hf/official.cjs');

test('首帧、视频描述、重做、明确复用和重开绑定同一项目的输入版本', async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ailab-workflow-test-'));
  t.after(() => fs.rmSync(dir, {recursive:true, force:true}));
  let service;
  function reopen() {
    service = new OfficialModels({dataDir:dir});
    service.trials.resolve = kind => ({info: {kind, pipeline: kind === 'video' ? 'h3-video' : undefined}});
  }
  reopen();
  const api = async (method, path, body, key = randomUUID()) => (await service.request({method, path, body, idempotencyKey:key})).data;
  const project = 'project-test';
  const configs = Object.fromEntries(['image','video','audio'].map(kind => [kind,
    {model_id:kind, input:{prompt:'商品演示'}, runtime:{seed:0}}]));
  const start = {project_id:project, name:'台灯', definition_version:'product-story-v1', steps:configs};
  const run = await api('POST','/workflow-runs',start,'create');
  const route = '/workflow-runs/'+run.id;
  assert.equal((await api('POST','/workflow-runs',start,'create')).id,run.id);
  assert.deepEqual((await api('GET','/workflow-runs?project_id=project-other')).items, []);

  // Seed previous results to exercise the existing “复用旧作品” path without requiring model weights.
  function previous(kind, projectId) {
    const bytes = kind === 'image' ? Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB','base64') : Buffer.from(kind);
    const location = path.join(dir,randomUUID());
    fs.writeFileSync(location, bytes);
    const uid = () => randomUUID().replaceAll('-','');
    const file = {id:'artifact-'+uid(), name:kind, path:location, sha256:createHash('sha256').update(bytes).digest('hex'),
      size:bytes.length, media_type: {image:'image/png',video:'video/mp4',audio:'audio/wav'}[kind]};
    return service.trials.save({id:'attempt-'+uid(),project_id:projectId,state:'succeeded',artifacts:[file],
      snapshot:{kind,operation:'generate',input:{prompt:'原文案'}}});
  }
  let current = run;
  async function reuseAndAdvance(kind) {
    const origin = previous(kind, project);
    const step = current.steps[kind];
    const reuse = {step_id:kind, input_revision:step.input_revision, expected_revision:current.revision,
      source_attempt_id:origin.id, artifact_id:origin.artifacts[0].id};
    const foreign = previous(kind,'project-other');
    await assert.rejects(api('POST',route+'/reuse-output',{...reuse,source_attempt_id:foreign.id,artifact_id:foreign.artifacts[0].id}));
    current = await api('POST',route+'/reuse-output',reuse);
    const advance = {expected_revision:current.revision,input_revision:step.input_revision,
      step_attempt_id:current.steps[kind].step_attempt_id,artifact_ids:[reuse.artifact_id]};
    const replies = await Promise.all([1,2].map(() => api('POST',route+'/advance',advance,'advance-'+kind)));
    assert.equal(replies[0].revision,replies[1].revision);
    current = replies[0];
  }
  await reuseAndAdvance('image');
  const firstVideo = current.steps.video.task_id;
  const edit = {expected_revision:current.revision,configuration:{...configs.video,input:{prompt:'镜头向台灯缓慢推进。'}}};
  current = await api('PATCH',route+'/steps/video/input', edit);
  await assert.rejects(api('PATCH',route+'/steps/video/input', edit), /版本/);
  await assert.rejects(api('POST','/tasks/'+firstVideo+'/preflight',{}), /当前版本/);
  reopen();
  current = await api('GET',route);
  const task = await api('GET','/tasks/'+current.steps.video.task_id);
  assert.deepEqual(task.draft.input, {prompt:edit.configuration.input.prompt, material_id:current.steps.image.accepted.material_id});
  assert.equal((await api('GET','/materials/'+task.draft.input.material_id)).width,1);
  await reuseAndAdvance('video');
  assert.equal((await api('GET','/tasks/'+current.steps.audio.task_id)).workflow_ref.upstream_refs[1].artifact_id,current.steps.video.accepted.artifact_id);
  await reuseAndAdvance('audio');
  await api('POST',route+'/save',{expected_revision:current.revision});
  reopen();
  assert.equal((await api('GET',route)).status,'saved');
  assert.equal((await api('GET','/works?project_id='+project)).items.length,3);
  current = await api('GET',route);
  current = await api('PATCH',route+'/steps/image/input',{expected_revision:current.revision,configuration:configs.image});
  assert.equal(current.steps.video.stale,true);
  assert.equal(current.steps.audio.stale,true);
  assert.equal(current.steps.video.accepted,null);
});
