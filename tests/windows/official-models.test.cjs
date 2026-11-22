const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtemp, readFile, writeFile } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { createHash, randomUUID } = require('node:crypto');
const { HubClient } = require('../../apps/windows-ui/hf/hub.cjs');
const { OfficialModels } = require('../../apps/windows-ui/hf/official.cjs');

function fixture() {
  const repo = 'publisher/test';
  const revision = 'c'.repeat(40);
  const bytes = Buffer.from('test weight');
  const hash = createHash('sha256').update(bytes).digest('hex');
  const paths = ['model-00001-of-00002.gguf', 'model-00002-of-00002.gguf', 'other.gguf', 'config.json', 'README.md',
    'model.safetensors', 'pytorch_model.bin', 'onnx/model.onnx', 'model.custom', 'notes.part', 'notes', 'ailab-model.json'];
  const responses = [];
  const hub = new HubClient({fetchImpl: async (url, options) => {
    responses.push({url, options});
    if (url.includes('/api/models/')) return Response.json({id: repo, sha: revision, pipeline_tag: 'text-generation', tags: ['license:mit'],
      siblings: paths.map(rfilename => ({rfilename, size: bytes.length, lfs: {sha256: hash}}))});
    return new Response(bytes);
  }});
  return {repo, bytes, hub, responses};
}

test('GGUF shards stay together; whole snapshots and single-file selections preserve unknown formats', async () => {
  const {repo, hub} = fixture();
  const detail = await hub.detail({repoId: repo});
  const names = (format, file) => hub.plan(detail, format, file).files.map(item => item.path);
  assert.deepEqual(names('gguf', 'model-00001-of-00002.gguf'), ['model-00001-of-00002.gguf', 'model-00002-of-00002.gguf', 'README.md']);
  assert.ok(names('snapshot').includes('model.custom'));
  assert.deepEqual(names('file','model.custom'), ['model.custom']);
  assert.ok(names('safetensors').includes('config.json'));
  assert.ok(!names('safetensors').includes('pytorch_model.bin'));
  assert.ok(names('onnx').includes('onnx/model.onnx'));
  detail.files = detail.files.filter(file => !file.path.startsWith('model-00002'));
  assert.throws(() => names('gguf','model-00001-of-00002.gguf'), {code: 'INCOMPLETE_SHARDS'});
});

test('download, register and reopen preserve versions and isolate projects; damaged bytes can be repaired', async () => {
  const {hub, repo, bytes} = fixture();
  const dataDir = await mkdtemp(path.join(tmpdir(), 'ailab-hf-test-'));
  let service = new OfficialModels({dataDir, hub});
  const get = async path => (await service.request({method: 'GET', path})).data;
  const post = async (path, body = {}) => (await service.request({method: 'POST', path, body, idempotencyKey: randomUUID()})).data;
  const project = 'project-test';
  const {items: [entry]} = await get('/model-catalog?repo=' + repo + '&format=snapshot');
  const start = {project_id: project, catalog_id: entry.id, manifest_digest: entry.manifest_digest};
  const [job, duplicate] = await Promise.all([post('/model-downloads', start), post('/model-downloads', start)]);
  assert.equal(job.id, duplicate.id);
  const finish = async () => { await service.downloads.active.get(job.id)?.pending; assert.equal((await get('/model-downloads/' + job.id)).state, 'completed'); };
  await finish();
  assert.deepEqual((await get('/models?project_id=' + project)).items, []);
  const file = path.join(service.downloads.modelDir, service.downloads.get(job.id).modelId, 'model.custom');
  await writeFile(file, Buffer.alloc(bytes.length));
  await assert.rejects(post('/model-downloads/' + job.id + '/models'), {code: 'INTEGRITY'});
  await post('/model-downloads/' + job.id + '/resume');
  await finish();
  const registered = await post('/model-downloads/' + job.id + '/models');
  for (const name of ['model.custom', 'notes', 'notes.part', 'ailab-model.json']) assert.deepEqual(await readFile(path.join(registered.path, name)), bytes);
  await service.close();
  service = new OfficialModels({dataDir, hub});
  assert.equal((await get('/models?project_id=' + project)).items[0].id, registered.id);
  assert.deepEqual((await get('/model-downloads?project_id=project-other')).items, []);
  assert.equal((await get('/model-catalog?download=' + job.id)).items[0].manifest_digest, entry.manifest_digest);
  await service.close();
});

test('a paused transfer keeps incomplete ranges across an application restart', async () => {
  const data = Buffer.alloc(16 * 1024 * 1024, 42);
  const hash = createHash('sha256').update(data).digest('hex');
  const received = 65536;
  let pausedOnce = false;
  const resumedStarts = [];
  const hub = new HubClient({fetchImpl: async (url, {headers}) => {
    if (url.includes('/api/models/')) return Response.json({id:'publisher/large', sha:'a'.repeat(40),
      siblings:[{rfilename:'test.gguf', size:data.length, lfs:{sha256:hash}}]});
    const [, left, right] = /^bytes=(\d+)-(\d+)$/.exec(headers.Range);
    const start = Number(left), end = Number(right);
    const payload = pausedOnce ? data.subarray(start, end + 1) : new ReadableStream({
      start(controller) { controller.enqueue(data.subarray(start, start + received)); }
    });
    if (pausedOnce) resumedStarts.push(start);
    return new Response(payload, {status:206, headers:{'Content-Range': 'bytes ' + start + '-' + end + '/' + data.length}});
  }});
  const dataDir = await mkdtemp(path.join(tmpdir(), 'ailab-hf-pause-'));
  let service = new OfficialModels({dataDir, hub});
  const entry = await service.inspect('publisher/large', 'gguf');
  const {data: record} = await service.request({method:'POST', path:'/model-downloads', idempotencyKey:randomUUID(),
    body:{project_id:'project-test', catalog_id:entry.id, manifest_digest:entry.id}});
  const deadline = Date.now() + 10000;
  while (service.downloads.get(record.id).downloadedBytes < received * 4 && Date.now() < deadline) {
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  await service.close();
  service = new OfficialModels({dataDir, hub});
  const initial = service.downloads.get(record.id);
  assert.equal(initial.status, 'paused');
  assert.equal(initial.downloadedBytes, received * 4);
  pausedOnce = true;
  await service.downloads.resume(record.id);
  await service.downloads.active.get(record.id)?.pending;
  assert.equal(initial.status, 'completed', initial.error);
  assert.equal(resumedStarts.length, 4);
  assert.ok(resumedStarts.every(start => start % (4 * 1024 * 1024) === received));
  assert.deepEqual(await readFile(path.join(service.downloads.modelDir, initial.modelId, 'test.gguf')), data);
  await service.close();
});

test('an unavailable default GGUF still lets the user choose another file', async () => {
  const {hub, bytes} = fixture();
  const digest = createHash('sha256').update(bytes).digest('hex');
  const repo = 'publisher/_collection';
  hub.fetch = async () => Response.json({id:repo, sha:'a'.repeat(40),
    siblings:['bad-00001-of-00002.gguf','good.gguf'].map(rfilename => ({rfilename,size:bytes.length,lfs:{sha256:digest}}))});
  const dataDir = await mkdtemp(path.join(tmpdir(), 'ailab-hf-selection-'));
  const service = new OfficialModels({dataDir, hub});
  const invalid = await service.inspect(repo);
  assert.match(invalid.selection_error, /分片/);
  assert.ok(invalid.variants.includes('good.gguf'));
  assert.equal(invalid.manifest_digest, '');
  const recovered = await service.inspect(repo, 'gguf', 'good.gguf');
  assert.ok(recovered.manifest_digest);
  assert.equal(recovered.files[0].path, 'good.gguf');
  await service.close();
});

test('large files fall back to one stream if the official server ignores ranges', async () => {
  const data = Buffer.alloc(16 * 1024 * 1024, 59);
  const sha256 = createHash('sha256').update(data).digest('hex');
  let ranges = 0;
  let streams = 0;
  const hub = new HubClient({fetchImpl: async (url, {headers}) => {
    if (url.includes('/api/models/')) return Response.json({id:'publisher/_large', sha:'a'.repeat(40),
      siblings:[{rfilename:'sample.gguf', size:data.length, lfs:{sha256}}]});
    if (headers.Range) ranges++; else streams++;
    return new Response(data);
  }});
  const dataDir = await mkdtemp(path.join(tmpdir(), 'ailab-hf-fallback-'));
  const service = new OfficialModels({dataDir, hub});
  const entry = await service.inspect('publisher/_large', 'gguf');
  const {data: record} = await service.request({method:'POST', path:'/model-downloads', idempotencyKey:randomUUID(),
    body:{project_id:'project-test', catalog_id:entry.id, manifest_digest:entry.id}});
  await service.downloads.active.get(record.id)?.pending;
  const job = service.downloads.get(record.id);
  assert.equal(job.status, 'completed', job.error);
  assert.ok(ranges >= 1);
  assert.equal(streams, 1);
  assert.deepEqual(await readFile(path.join(service.downloads.modelDir,job.modelId,'sample.gguf')), data);
  await service.close();
});

test('large files use bounded HTTP ranges and verify the assembled snapshot', async () => {
  const data = Buffer.alloc(16 * 1024 * 1024 + 1200);
  for (let i = 0; i < data.length; i += 4093) data[i] = i % 251;
  const hash = createHash('sha256').update(data).digest('hex');
  const ranges = [];
  const hub = new HubClient({fetchImpl: async (url, options) => {
    if (url.includes('/api/models/')) return Response.json({id:'publisher/large', sha:'a'.repeat(40), siblings:[
      {rfilename:'model.custom', size:data.length, lfs:{sha256:hash}}]});
    const match = /^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);
    assert.ok(match);
    const first = Number(match[1]), last = Number(match[2]);
    ranges.push([first, last]);
    return new Response(data.subarray(first, last + 1), {status:206, headers:{'Content-Range':'bytes ' + first + '-' + last + '/' + data.length}});
  }});
  const dataDir = await mkdtemp(path.join(tmpdir(), 'ailab-hf-range-'));
  const service = new OfficialModels({dataDir, hub});
  const entry = await service.inspect('publisher/large', 'snapshot');
  const {data: record} = await service.request({method:'POST', path:'/model-downloads', idempotencyKey:randomUUID(),
    body:{project_id:'project-test', catalog_id:entry.id, manifest_digest:entry.id}});
  await service.downloads.active.get(record.id)?.pending;
  const job = service.downloads.get(record.id);
  assert.equal(job.status, 'completed', job.error);
  assert.equal(job.downloadedBytes, data.length);
  assert.ok(ranges.length > 1);
  assert.equal(ranges.reduce((sum, [first,last]) => sum + last - first + 1, 0), data.length);
  assert.deepEqual(await readFile(path.join(service.downloads.modelDir,job.modelId,'model.custom')),data);
  await service.close();
});
test('published model IDs resolve to the matching GGUF inference bundles and preserve original formats', async () => {
  const cards = [
    ['Qwen/Qwen3.5-4B', 'unsloth/Qwen3.5-4B-GGUF', 'Qwen3.5-4B-Q4_K_M.gguf', ['mmproj-F16.gguf']],
    ['google/gemma-4-E2B-it', 'ggml-org/gemma-4-E2B-it-GGUF', 'gemma-4-E2B-it-Q4_0.gguf', ['mmproj-gemma-4-E2B-it-Q8_0.gguf']],
    ['MiniMaxAI/MiniMax-H3-Image', 'unsloth/MiniMax-H3-Image-GGUF', 'minimax_h3_image_pruned-Q2_K.gguf', ['components/encoder.safetensors', 'components/image_vae.safetensors']],
    ['MiniMaxAI/MiniMax-H3', 'leejet/MiniMax-H3-GGUF', 'minimax_h3_fl2va_pruned-Q4_K_M.gguf', ['components/encoder.safetensors', 'components/video_vae.safetensors', 'components/audio_vae.safetensors']],
  ];
  const hub = new HubClient({ fetchImpl: async (url) => {
    const repo = new URL(url).pathname.split('/').slice(3,5).join('/');
    const [official, , main, companions] = cards.find(([source, quantized]) => source === repo || quantized === repo);
    const files = repo === official ? ['model.safetensors'] : [main, ...companions.filter(name => !name.includes('/'))];
    return Response.json({id: repo, sha: 'c'.repeat(40), siblings: files.map(rfilename => ({rfilename, size: 10, lfs: {sha256: 'a'.repeat(64)}}))});
  }});
  const service = new OfficialModels({dataDir: await mkdtemp(path.join(tmpdir(), 'ailab-hf-bundles-')), hub});
  try {
    for (const [official, quantized, main, companions] of cards) {
      const entry = await service.inspect(official, 'gguf');
      assert.equal(entry.repo, quantized);
      assert.equal(entry.filename, main);
      assert.deepEqual(entry.files.map(f => f.path), [main, ...companions]);
      assert.equal(entry.total_bytes, entry.files.reduce((n, file) => n + file.size, 0));
      for (const file of entry.files) assert.match(file.url, /\/resolve\/[0-9a-f]{40}\//);
      assert.equal((await service.inspect(official, 'safetensors')).repo, official);
    }
  } finally { await service.close(); }
});
