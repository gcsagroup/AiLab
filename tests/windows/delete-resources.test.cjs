const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { OfficialModels } = require('../../apps/windows-ui/hf/official.cjs');

test('Windows resource deletion preserves shared assets and prevents deleting active models', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'ailab-delete-'));
  const service = new OfficialModels({dataDir: root});
  const project = 'project-test', other = 'project-other';
  const suffix = '?project_id=' + project;
  const call = async (method, route) => (await service.request({method, path: route})).data;
  try {
    const modelId = 'hf-' + 'a'.repeat(24), jobId = modelId.replace('hf-', 'download-');
    const job = {id: jobId, modelId, projectId: project, status: 'completed', registeredAt: 'yes',
      files: [], createdAt: '2026-01-01', repoId: 'owner/model'};
    service.downloads.jobs.set(jobId, job);
    service.downloads.save(job);
    const directory = path.join(service.downloads.modelDir, modelId);
    fs.mkdirSync(directory);
    fs.writeFileSync(path.join(directory, 'weights.gguf'), 'weights');
    const shared = path.join(root, 'derived-gguf', 'shared');
    fs.mkdirSync(shared, {recursive: true});
    fs.writeFileSync(path.join(shared, 'encoder.gguf'), 'shared');
    await assert.rejects(call('DELETE', '/models/' + modelId + '?project_id=' + other));
    await call('DELETE', '/model-downloads/' + jobId + suffix);
    assert.equal((await call('GET', '/model-downloads' + suffix)).items.length, 0);
    assert.equal((await call('GET', '/models' + suffix)).items.length, 1);
    assert.ok(fs.existsSync(path.join(directory, 'weights.gguf')));
    const attemptId = 'attempt-' + 'b'.repeat(32);
    service.trials.save({id:attemptId, project_id:project, task_id:'task-test', state:'running', snapshot:{model_id:modelId}});
    await assert.rejects(call('DELETE', '/models/' + modelId + suffix), /正在运行/);
    await assert.rejects(call('DELETE', '/tasks/task-test/record' + suffix), /仍在运行/);
    service.trials.save({...service.trials.rows.get(attemptId), state:'succeeded'});
    await call('DELETE', '/tasks/task-test/record' + suffix);
    await call('DELETE', '/models/' + modelId + suffix);
    assert.equal(fs.existsSync(directory), false);
    assert.equal(fs.existsSync(path.join(service.downloads.jobDir, jobId + '.json')), false);
    assert.ok(fs.existsSync(path.join(shared, 'encoder.gguf')));
    assert.ok(service.trials.rows.has(attemptId));
    const workId = 'work-' + 'c'.repeat(32);
    service.trials.save({id:workId, project_id:project, attempt_id:attemptId, artifact_id:'artifact-1'});
    await call('DELETE', '/works/' + workId + suffix);
    assert.equal((await call('GET', '/works' + suffix)).items.length, 0);
    assert.ok(service.trials.rows.has(attemptId));
    const imported = 'local-' + 'd'.repeat(32);
    const importedDir = path.join(service.trials.dir, imported);
    fs.mkdirSync(importedDir);
    fs.writeFileSync(path.join(importedDir, 'model.gguf'), 'copy');
    service.trials.save({id:imported, project_id:project, kind:'text', path:path.join(importedDir, 'model.gguf')});
    await call('DELETE', '/models/' + imported + suffix);
    assert.equal(fs.existsSync(importedDir), false);
    const partialId = 'download-' + 'e'.repeat(24);
    const partial = {id:partialId, modelId:partialId.replace('download-', 'hf-'), projectId:project,
      status:'paused', files:[], createdAt:'2026-01-01', repoId:'owner/partial'};
    service.downloads.jobs.set(partialId, partial);
    service.downloads.save(partial);
    const partialDirectory = path.join(service.downloads.modelDir, partial.modelId);
    fs.mkdirSync(partialDirectory);
    fs.writeFileSync(path.join(partialDirectory, 'partial.gguf'), 'partial');
    fs.writeFileSync(path.join(service.downloads.jobDir, partialId + '.0.part'), 'part');
    await call('DELETE', '/model-downloads/' + partialId + suffix);
    assert.equal(fs.existsSync(partialDirectory), false);
    assert.equal(fs.existsSync(path.join(service.downloads.jobDir, partialId + '.0.part')), false);
  } finally {
    await service.close();
    fs.rmSync(root, {recursive: true, force: true});
  }
});
