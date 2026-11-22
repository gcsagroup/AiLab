'use strict';
const path = require('node:path');
const { metadata } = require('./gguf-metadata.cjs');

// Bind each role to exactly one GGUF. A standalone DiT, VAE or projector cannot run inference.
function bundle(files) {
  const entries = files.map((file) => ({ file, info: metadata(file) }));
  const primary = entries.filter(
    ({ info }) => info.kind || ['h3-image', 'h3-video'].includes(info.component),
  );
  if (primary.length !== 1) return null;
  const { file, info } = primary[0];
  const extra = {},
    extraInfo = {};
  for (const item of entries.filter((e) => e.file !== file)) {
    const role = item.info.motion ? 'motion' : item.info.component;
    if (!role || Object.hasOwn(extra, role)) return null;
    extra[role] = item.file;
    extraInfo[role] = item.info;
  }
  const roles = Object.keys(extra).sort().join(',');
  if (info.component === 'h3-image' && roles === 'encoder,image_vae')
    return { file, extra, info: { ...info, kind: 'image', pipeline: 'h3-image' } };
  if (info.component === 'h3-video' && ['audio_vae,encoder,video_vae', 'encoder,video_vae'].includes(roles))
    return { file, extra, info: { ...info, kind: 'video', pipeline: 'h3-video' } };
  if (roles === 'motion' && info.sd15)
    return { file, extra, info: { ...info, kind: 'video', pipeline: 'animatediff-sd15' } };
  if (roles === 'projector' && ['qwen35', 'gemma4'].includes(info.arch)) {
    const proj = extraInfo.projector;
    const identity = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (
      !info.name ||
      identity(proj.name) !== identity(info.name) ||
      proj.projectorType !== (info.arch === 'gemma4' ? 'gemma4v' : 'qwen3vl_merger')
    )
      return null;
    return { file, extra, info: { ...info, multimodal: true } };
  }
  return !roles && info.kind ? { file, extra, info } : null;
}
const roles = new Set(['motion', 'projector', 'encoder', 'image_vae', 'video_vae', 'audio_vae']);
function localExtras(row) {
  const extra = {};
  for (const role of Object.keys(row.component_digests || {})) {
    if (!roles.has(role)) throw Error('模型组件记录无效。');
    extra[role] = path.join(path.dirname(row.path), role + '.gguf');
  }
  if (row.motion_digest) extra.motion = path.join(path.dirname(row.path), 'motion.gguf');
  return extra;
}
function materialPrompt(input) {
  const text = input.prompt || '';
  const match = /^@素材[ \t]+([^\r\n]+)\r?\n/.exec(text);
  return {
    reference: match ? match[1].trim() : input.material_id,
    prompt: match ? text.slice(match[0].length) : text,
  };
}
module.exports = { bundle, localExtras, materialPrompt };
