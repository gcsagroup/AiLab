'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { LocalEnvironment } = require('../../apps/windows-ui/hf/environment.cjs');
const { bins } = require('../../apps/windows-ui/hf/trial-worker.cjs');

test('a refresh replaces the snapshot once and export writes exactly the displayed result', async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-environment-test-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const probes = [];
  const environment = new LocalEnvironment(dir, (_directory, refresh) => new Promise(resolve => probes.push({ refresh, resolve })));
  const first = environment.get();
  assert.equal(environment.get(true), first);
  probes[0].resolve({ id: '1', checked_at: '2026-11-25T00:00:00Z' });
  const original = await first;
  assert.equal(await environment.get(), original);
  const next = environment.get(true);
  assert.equal(probes[1].refresh, true);
  assert.equal(environment.get(), next);
  probes[1].resolve({ id: '2', checked_at: '2026-11-25T00:00:01Z' });
  const current = await next;
  await assert.rejects(environment.export(original.id, () => assert.fail()), /已更新/);
  assert.deepEqual(await environment.export(current.id, () => null), { saved: false });
  assert.deepEqual(await fs.readdir(dir), []);
  const file = path.join(dir, 'test.json');
  assert.equal((await environment.export(current.id, () => file)).saved, true);
  assert.deepEqual(JSON.parse(await fs.readFile(file)), current);
});

test('an existing executable that cannot encode fails video, preserves other results and recovers on refresh',
  { skip: process.platform !== 'win32' }, async t => {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-probe-test-'));
    t.after(() => fs.rm(dir, { recursive: true, force: true }));
    const environment = new LocalEnvironment(dir);
    const original = bins.ffmpeg;
    t.after(() => { bins.ffmpeg = original; });
    bins.ffmpeg = process.execPath;
    const broken = await environment.get();
    const capability = (report, kind) => report.capabilities.find(item => item.kind === kind && item.operation === 'generate');
    assert.equal(capability(broken, 'video').supported, false);
    assert.equal(capability(broken, 'audio').status, 'partial');
    assert.equal(capability(broken, 'image').supported, true);
    assert.equal(broken.checks.find(item => item.id === 'videoEncode').status, 'failed');
    bins.ffmpeg = original;
    const fixed = await environment.get(true);
    assert.notEqual(fixed.id, broken.id);
    assert.equal(capability(fixed, 'video').status, 'ready');
    assert.equal(fixed.checks.find(item => item.id === 'audioConvert').status, 'ready');
    assert.equal(fixed.checks.find(item => item.id === 'storage').status, 'ready');
    assert.deepEqual(await fs.readdir(dir), []);
  });
