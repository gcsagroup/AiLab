'use strict';
const path = require('node:path');
const fs = require('node:fs');
const { metadata } = require('./gguf-metadata.cjs');

const audioAssets = {
  sanotts: { voice_config: 'config.json' },
  pocket_tts_small: { pocket_voice: 'embeddings/alba.safetensors' },
  gradium_phonon: { phonon_voice: 'default-voice.safetensors' },
};
const assetPaths = Object.assign({}, ...Object.values(audioAssets));
function componentPath(dir, role) {
  return path.join(dir, require('./generation-packages.cjs').componentName(role) || assetPaths[role] || role + '.gguf');
}
function audioExtras(file, family) {
  const extra = {};
  const dir = path.dirname(file);
  for (const [role, relative] of Object.entries(audioAssets[family] || {})) {
    const asset = componentPath(dir, role);
    if (!fs.existsSync(asset) || !fs.statSync(asset).isFile() ||
        fs.realpathSync(asset).toLowerCase() !== path.join(fs.realpathSync(dir), relative).toLowerCase())
      throw Error(family + ' 需要与 GGUF 配套的 ' + relative + '，请导入完整模型目录。');
    extra[role] = asset;
  }
  return extra;
}

// Bind each role to exactly one GGUF. A standalone DiT, VAE or projector cannot run inference.
function bundle(files) {
  const shards = {};
  const split = files
    .map((file) => ({ file, match: /^(.*)-(\d{5})-of-(\d{5})\.gguf(?:_file)?$/i.exec(file) }))
    .filter((s) => s.match);
  if (split.length) {
    const [prefix, total] = [split[0].match[1], split[0].match[3]];
    if (Number(total) !== split.length || split.some((s) => s.match[1] !== prefix || s.match[3] !== total))
      return null;
    const byIndex = new Map(split.map((s) => [Number(s.match[2]), s.file]));
    for (let i = 1; i <= split.length; i++) {
      if (!byIndex.has(i)) return null;
      if (i > 1) shards['shard_' + String(i).padStart(5, '0')] = byIndex.get(i);
    }
    const tails = new Set(Object.values(shards));
    files = files.filter((file) => !tails.has(file));
  }
  const members = files.map((file) => ({ file, info: metadata(file) }));
  const reap=require('./qwen-reap.cjs').match(members);
  if (reap) return reap;
  const entries=members.filter(e=>!e.info.pleOnly);
  const tables=members.filter(e=>e.info.pleOnly);
  if (tables.length>1) return null;
  const table=tables[0];
  if (table && !entries.some(e=>e.info.kind==='text' && e.info.arch===table.info.arch &&
      ['qwen4exp','gemma4'].includes(e.info.arch))) return null;
  const anima = entries.find(e => e.info.component === 'anima');
  if (anima) {
    const encoder = entries.find(e => e.info.animaTextEncoder);
    const vae = entries.find(e => e.info.component === 'wan_vae');
    if (entries.length !== 3 || !encoder || !vae || split.length) return null;
    return {file:anima.file, extra:{anima_encoder:encoder.file, anima_vae:vae.file},
      info:{...anima.info, kind:'image', pipeline:'anima'}};
  }
  const iris = entries.find(e => e.info.component === 'iris');
  if (iris) {
    const encoder = entries.find(e => e.info.irisTextEncoder);
    if (entries.length !== 2 || !encoder || split.length) return null;
    return {file:iris.file, extra:{iris_encoder:encoder.file}, info:{...iris.info, kind:'image', pipeline:'iris'}};
  }
  const wan = entries.find(e => e.info.component === 'wan21-t2v');
  if (wan) {
    const encoder = entries.find(e => e.info.wanTextEncoder);
    const vae = entries.find(e => e.info.component === 'wan_vae');
    if (entries.length !== 3 || !encoder || !vae || split.length) return null;
    return {file:wan.file, extra:{umt5:encoder.file, wan_vae:vae.file},
      info:{...wan.info, kind:'video', pipeline:'wan21-t2v'}};
  }
  const primary = entries.filter(
    ({ info }) => info.kind || ['h3-image', 'h3-video', 'z-image', 'speech-base', 'ocr-base'].includes(info.component),
  );
  if (primary.length !== 1) return null;
  const { file, info } = primary[0];
  if (info.requiresPleTable && !info.hasPleTable && !table &&
      !Object.values(shards).some(shard=>metadata(shard).hasPleTable))
    throw Error('这份主模型需要配套的 PLE 词嵌入查找表。请选择包含主权重和查找表的发布目录。');
  const extra = {},
    extraInfo = {};
  for (const item of entries.filter((e) => e.file !== file)) {
    const role = item.info.motion ? 'motion' : item.info.component;
    if (!role || Object.hasOwn(extra, role)) return null;
    extra[role] = item.file;
    extraInfo[role] = item.info;
  }
  const roles = Object.keys(extra).sort().join(',');
  const projector = extraInfo.projector;
  if (info.modelWidth && projector?.projectionWidth && info.modelWidth !== projector.projectionWidth) return null;
  if (info.component === 'ocr-base' || ['deepseekocr','deepseekocr2'].includes(projector?.projectorType)) {
    if (info.component !== 'ocr-base' || roles !== 'projector' || !projector.acceptsImage ||
        !['deepseekocr','deepseekocr2'].includes(projector.projectorType)) return null;
    if (/deepseek[-_ ]?ocr[-_ ]?2/i.test(info.name) && projector.projectorType !== 'deepseekocr2') return null;
    if (/deepseek[-_ ]?ocr(?:$|[-_ ](?:base|q\d))/i.test(info.name) && projector.projectorType !== 'deepseekocr') return null;
    return {file, extra:{...extra,...shards}, info:{...info,kind:'text',pipeline:'llama-ocr',multimodal:true,acceptsImage:true}};
  }
  if (info.arch === 'moshi' || projector?.projectorType === 'moshi') {
    if (info.arch !== 'moshi' || roles !== 'projector' || projector?.projectorType !== 'moshi' ||
        !projector.acceptsAudio || !projector.generatesAudio) return null;
    return {file, extra:{...extra,...shards}, info:{...info,kind:'audio',pipeline:'llama-hibiki',multimodal:true,acceptsAudio:true}};
  }
  if (info.component === 'z-image' && roles === 'flux_vae,qwen3_encoder')
    return { file, extra, info: { ...info, kind: 'image', pipeline: 'z-image' } };
  if (info.component === 'h3-image' && roles === 'encoder,image_vae')
    return { file, extra, info: { ...info, kind: 'image', pipeline: 'h3-image' } };
  if (info.component === 'h3-video' && ['audio_vae,encoder,video_vae', 'encoder,video_vae'].includes(roles))
    return { file, extra, info: { ...info, kind: 'video', pipeline: 'h3-video' } };
  if (roles === 'motion' && info.sd15)
    return { file, extra, info: { ...info, kind: 'video', pipeline: 'animatediff-sd15' } };
  if (
    (info.component === 'speech-base' || info.kind === 'text') &&
    roles === 'projector' &&
    extraInfo.projector.generatesAudio
  )
    return { file, extra: { ...extra, ...shards }, info: { ...info, kind: 'audio', pipeline: 'llama-tts' } };
  if (
    info.kind === 'text' &&
    roles &&
    Object.keys(extra).every((role) => ['projector', 'draft'].includes(role))
  ) {
    if (extra.draft && info.pipeline && !['llama-chat'].includes(info.pipeline)) return null;
    if (extra.projector) {
      const type = extraInfo.projector.projectorType;
      if ((type==='cogvlm') !== (info.arch==='cogvlm')) return null;
      if (
        (info.arch === 'qwen35' && type === 'gemma4v') ||
        (info.arch === 'gemma4' && type === 'qwen3vl_merger')
      )
        return null;
    }
    // The runtime opens both files together and validates projector dimensions and draft compatibility.
    return {
      file,
      extra: { ...extra, ...shards, ...(table ? {ple_table:table.file} : {}) },
      info: {
        ...info,
        multimodal: !!extra.projector,
        acceptsAudio: !!extraInfo.projector?.acceptsAudio,
        acceptsImage: !!extraInfo.projector?.acceptsImage,
        specType: extraInfo.draft?.specType,
      },
    };
  }
  return !roles && info.kind ? { file, extra: { ...audioExtras(file, info.audioFamily), ...shards, ...(table ? {ple_table:table.file} : {}) }, info } : null;
}
const roles = new Set(['motion', 'projector', 'draft', 'ple_table','recovery_lora','encoder', 'image_vae', 'video_vae', 'audio_vae', 'qwen3_encoder', 'flux_vae', 'umt5', 'wan_vae', 'iris_encoder', 'anima_encoder', 'anima_vae']);
function localExtras(row) {
  const extra = {};
  for (const role of Object.keys(row.component_digests || {})) {
    if (/^shard_\d{5}$/.test(role)) {
      const match = /^(.*)-00001-of-(\d{5})\.gguf$/i.exec(row.path);
      if (!match || Number(role.slice(6)) < 2 || Number(role.slice(6)) > Number(match[2]))
        throw Error('模型分片记录无效。');
      extra[role] = match[1] + '-' + role.slice(6) + '-of-' + match[2] + '.gguf';
      continue;
    }
    if (!roles.has(role) && !Object.hasOwn(assetPaths, role) && !require('./generation-packages.cjs').componentName(role)) throw Error('模型组件记录无效。');
    extra[role] = componentPath(path.dirname(row.path), role);
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
module.exports = { bundle, localExtras, materialPrompt, componentPath, audioExtras };
