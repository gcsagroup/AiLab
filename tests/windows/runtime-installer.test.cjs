'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { RuntimeInstaller, definitions, download } = require('../../apps/windows-ui/hf/runtime-installer.cjs');

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
