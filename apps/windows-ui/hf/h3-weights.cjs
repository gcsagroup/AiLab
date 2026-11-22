'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const catalog = require('./h3-components.json');
const { metadata } = require('./gguf-metadata.cjs');
const pending = new Map();

function roles(repo, filename = '') {
  if (
    repo.toLowerCase() === 'unsloth/minimax-h3-image-gguf' &&
    /^minimax_h3_image_pruned[-_].*\.gguf$/i.test(filename)
  )
    return ['encoder', 'image_vae'];
  if (
    repo.toLowerCase() === 'leejet/minimax-h3-gguf' &&
    /^minimax_h3_fl2va(?:_pruned)?-.*\.gguf$/i.test(filename)
  )
    return ['encoder', 'video_vae', 'audio_vae'];
  return [];
}
function sources(repo, filename) {
  return roles(repo, filename).map((role) => {
    const c = catalog[role];
    return {
      role,
      path: 'components/' + role + '.safetensors',
      sha256: c.sha256,
      size: c.size,
      url: 'https://huggingface.co/' + c.repo + '/resolve/' + c.revision + '/' + c.file + '?download=true',
    };
  });
}
async function sha(file) {
  const h = createHash('sha256');
  for await (const b of fs.createReadStream(file)) h.update(b);
  return h.digest('hex');
}
// Keep derived weights outside the immutable downloaded snapshot. Shared encoders are converted once.
function conversionTypes(repo, filename) {
  return Object.fromEntries(roles(repo, filename).map(role => [role, catalog[role].quant]));
}
function derivedFile(dataDir, role, type) {
  const c = catalog[role];
  if (!c) throw Error('未知组件。');
  const quant = type ?? c.quant;
  if (quant !== c.quant && !(role === 'encoder' && quant === 'q4_0')) throw Error('未知的 GGUF 组件精度。');
  return path.join(dataDir, 'derived-gguf', 'sd-532d2c1-' + quant + '-' + c.sha256, role + '.gguf');
}
async function convert(source, dest, role) {
  const { bins, invoke } = require('./trial-worker.cjs'),
    dir = path.dirname(dest);
  await fs.promises.mkdir(path.dirname(dir), { recursive: true });
  const existing = async () => {
    const record = JSON.parse(await fs.promises.readFile(path.join(dir, 'manifest.json'), 'utf8'));
    if (record.sha256 !== (await sha(dest)) || metadata(dest).component !== role)
      throw Error('已有 GGUF 组件校验失败。');
    return record.sha256;
  };
  if (fs.existsSync(dest)) return existing();
  const tmp = await fs.promises.mkdtemp(dir + '-');
  try {
    const input = path.join(tmp, 'source.safetensors');
    try {
      await fs.promises.link(source, input);
    } catch (e) {
      if (e.code !== 'EXDEV') throw e;
      await fs.promises.copyFile(source, input);
    }
    const out = path.join(tmp, role + '.gguf');
    await invoke(
      path.join(path.dirname(bins.image), 'sd-cli.exe'),
      ['-M', 'convert', '-m', 'source.safetensors', '--type', catalog[role].quant, '-o', role + '.gguf'],
      { cwd: tmp },
    );
    if (metadata(out).component !== role) throw Error('转换后的 GGUF 组件不匹配：' + role);
    const hash = await sha(out);
    await fs.promises.writeFile(path.join(tmp, 'manifest.json'), JSON.stringify({ sha256: hash }));
    await fs.promises.unlink(input);
    try {
      await fs.promises.rename(tmp, dir);
    } catch (e) {
      if (!fs.existsSync(dest)) throw e;
      return existing();
    }
    return hash;
  } finally {
    await fs.promises.rm(tmp, { recursive: true, force: true });
  }
}
async function prepareComponent(source, role, dataDir) {
  const dest = derivedFile(dataDir, role);
  if (!pending.has(dest)) {
    pending.set(dest, convert(source, dest, role).finally(() => pending.delete(dest)));
  }
  return pending.get(dest);
}
async function prepare(job, modelDir, dataDir) {
  const members = sources(job.repoId, job.filename);
  if (!members.length || members.some(member => !job.files.some(f => f.path === member.path && f.sha256 === member.sha256))) return undefined;
  const hashes = {};
  for (const member of members) {
    hashes[member.role] = await prepareComponent(path.join(modelDir, job.modelId, member.path), member.role, dataDir);
  }
  return hashes;
}
module.exports = { sources, derivedFile, prepare, prepareComponent, conversionTypes };
