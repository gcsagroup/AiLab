'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { RuntimeInstaller, definitions, download } = require('../../apps/windows-ui/hf/runtime-installer.cjs');
const { runtimeDirectory } = require('../../apps/windows-ui/hf/runtime-directory.cjs');
const { createHash } = require('node:crypto');

test('a compatible portable component works offline without a receipt, and missing DLLs or mismatched workers are reported', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-portable-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  const def = definitions.base;
  const fixture = Buffer.from('fixture worker');
  const fingerprint = def.fingerprint;
  def.fingerprint = [fingerprint[0], createHash('sha256').update(fixture).digest('hex')];
  t.after(() => { def.fingerprint = fingerprint; });
  for (const file of [...def.required, ...definitions['image-video'].required]) {
    await fs.mkdir(path.dirname(path.join(root, file)), { recursive:true });
    await fs.writeFile(path.join(root, file), fixture);
  }
  const manager = new RuntimeInstaller(root, { fetchFile: () => assert.fail('unexpected download') });
  await manager.ensure('base');
  assert.match((await manager.inspect('base')).detail, /已识别本机/);
  await fs.writeFile(path.join(root, fingerprint[0]), 'another worker build');
  assert.match((await manager.inspect('base')).detail, /版本.*不匹配/);
  await fs.writeFile(path.join(root, '.installed-image-video-20261127'), '[]');
  const image = (await manager.status()).components.find(item => item.id === 'image-video');
  assert.equal(image.installed, false);
  assert.match(image.detail, /还需基础运行库/);
  await fs.rm(path.join(root, 'text/mtmd.dll'));
  assert.match((await manager.inspect('base')).detail, /mtmd\.dll/);
});

test('directory selection accepts a portable app or its runtime, survives reopening and can be reset', async t => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-directories-'));
  t.after(() => fs.rm(temp, {recursive:true, force:true}));
  const profile = path.join(temp, 'profile'), app = path.join(temp, '旧版 AiLab');
  const legacy = path.join(app, 'resources/app/runtime'), bundled = path.join(temp, 'bundled');
  for (const root of [legacy, bundled]) {
    await fs.mkdir(path.join(root, 'text'), {recursive:true});
    await fs.writeFile(path.join(root, 'text/ailab-gguf.exe'), 'worker');
  }
  const auto = await runtimeDirectory(profile, bundled);
  assert.equal(auto.root, await fs.realpath(bundled));
  assert.equal((await runtimeDirectory(profile, bundled, legacy)).root, await fs.realpath(legacy));
  await assert.rejects(auto.select(temp), /请选择/);
  await auto.select(app);
  assert.equal(auto.info().nextRoot, await fs.realpath(legacy));
  assert.notEqual(auto.root, auto.info().nextRoot);
  const reopened = await runtimeDirectory(profile, bundled);
  assert.equal(reopened.root, await fs.realpath(legacy));
  await fs.unlink(path.join(legacy, 'text/ailab-gguf.exe'));
  const missing = await runtimeDirectory(profile, bundled);
  assert.equal(missing.root, await fs.realpath(bundled));
  assert.match(missing.info().directoryWarning, /已不可用/);
  await missing.select(null);
  const clean = await runtimeDirectory(profile);
  assert.equal(clean.root, path.join(profile, 'runtime'));
  assert.equal(clean.info().selected, false);
});

test('a failed preparation leaves no active files, and callers share one successful retry', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-runtime-test-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  let failOnce = true, downloads = 0;
  const manager = new RuntimeInstaller(root, {
    async fetchFile(file) {
      downloads++;
      await fs.writeFile(file, 'fixture');
    },
    async extract(_archive, target, filter) {
      if (filter === 'ffmpeg' && failOnce) {
        failOnce = false;
        throw Error('interrupted');
      }
      if (filter === 'all') {
        for (const name of definitions.base.required) {
          const dest = path.join(target, name);
          await fs.mkdir(path.dirname(dest), {recursive:true});
          await fs.writeFile(dest, 'worker');
        }
      }
    },
  });
  await assert.rejects(manager.ensure('base'), /interrupted/);
  assert.deepEqual(await fs.readdir(root), []);
  downloads = 0;
  await Promise.all([manager.ensure('base'), manager.ensure('base')]);
  assert.equal(downloads, definitions.base.files.length);
  assert.equal(await manager.installed('base'), true);
  await manager.ensure('base');
  assert.equal(downloads, definitions.base.files.length);
});

test('rejects content whose SHA-256 differs from the pinned download', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'ailab-runtime-hash-'));
  t.after(() => fs.rm(root, {recursive:true, force:true}));
  t.mock.method(globalThis, 'fetch', async () => new Response('wrong content'));
  await assert.rejects(download(path.join(root,'archive'), definitions.base.files[0], new AbortController().signal, () => {}), /摘要校验失败/);
});
