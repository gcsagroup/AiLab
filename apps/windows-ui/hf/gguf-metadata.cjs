'use strict';
const fs = require('node:fs');
const path = require('node:path');

// Read only the metadata and tensor directory; large arrays (tokenizer scores,
// token strings, etc.) are skipped without materializing the weight data.
const cached = new Map();
function metadata(file) {
  const stat = fs.statSync(file);
  const stamp = stat.size + ':' + stat.mtimeMs;
  if (cached.get(file)?.stamp === stamp) return cached.get(file).value;
  const fd = fs.openSync(file, 'r');
  let pos = 0,
    start = -1,
    end = -1;
  const page = Buffer.alloc(65536);
  function take(n) {
    if (n < 0 || n > page.length || pos + n > stat.size) throw Error('GGUF 元数据越界。');
    if (pos < start || pos + n > end) {
      start = pos;
      end = start + fs.readSync(fd, page, 0, page.length, pos);
    }
    if (pos + n > end) throw Error('GGUF 元数据不完整。');
    const bytes = page.subarray(pos - start, pos - start + n);
    pos += n;
    return bytes;
  }
  const u32 = () => take(4).readUInt32LE();
  function u64() {
    const n = Number(take(8).readBigUInt64LE());
    if (!Number.isSafeInteger(n)) throw Error('GGUF 长度无效。');
    return n;
  }
  function skip(n) {
    if (!Number.isSafeInteger(n) || n < 0 || pos + n > stat.size) throw Error('GGUF 长度越界。');
    pos += n;
  }
  function str(read) {
    let n = u64();
    if (!read) {
      skip(n);
      return '';
    }
    if (n > 1024 * 1024) throw Error('GGUF 字段过长。');
    const parts = [];
    while (n) {
      const size = Math.min(n, page.length);
      parts.push(Buffer.from(take(size)));
      n -= size;
    }
    return Buffer.concat(parts).toString('utf8');
  }
  const widths = [1, 1, 2, 2, 4, 4, 4, 1, 0, 0, 8, 8, 8];
  try {
    if (take(4).toString() !== 'GGUF' || ![2, 3].includes(u32())) throw Error('需要 GGUF v2/v3 文件。');
    const tensors = u64(),
      fields = u64(),
      meta = {};
    if (fields > 100000 || tensors > 1000000) throw Error('GGUF 目录过大。');
    for (let i = 0; i < fields; i++) {
      const key = str(true),
        type = u32();
      if (type === 8) {
        const keep = [
          'general.name',
          'general.architecture',
          'tokenizer.chat_template',
          'clip.vision.projector_type',
          'clip.projector_type',
        ].includes(key);
        const value = str(keep);
        if (keep) meta[key] = value;
      } else if (type === 9) {
        const elem = u32(),
          count = u64();
        if (elem === 8 && count > 2000000) throw Error('GGUF 字符串表过大。');
        if (elem === 8) {
          for (let j = 0; j < count; j++) str(false);
        } else if (widths[elem]) skip(widths[elem] * count);
        else throw Error('GGUF 元数据类型不受支持。');
      } else if (widths[type]) skip(widths[type]);
      else throw Error('GGUF 元数据类型无效。');
    }
    let visual = false,
      temporal = false,
      tts = false;
    const components = new Set();
    const motionBlocks = new Set();
    let motionOnly = tensors > 0;
    const h3 = new Set();
    for (let i = 0; i < tensors; i++) {
      const name = str(true),
        dims = u32();
      if (!dims || dims > 5) throw Error('GGUF 张量维数无效。');
      const shape = Array.from({ length: dims }, u64);
      skip(12);
      const key = name.replace(
        /^(?:model\.diffusion_model\.|diffusion_model\.|first_stage_model\.|vae\.|cond_stage_model\.)/,
        '',
      );
      if (
        [
          'condition_proj.weight',
          'audio_patch_proj.weight',
          'video_patch_proj.weight',
          'decoder.mask_token',
          'latents_mean',
          'dec_in_proj.weight',
          'text_connector.sink_embedding',
        ].includes(key)
      )
        h3.add(key);
      if (/^(?:model\.)?(?:language_model\.)?embed_tokens\.weight$/.test(key) && shape[0]===5120) h3.add('h3-32b');
      if (key === 'decoder.proj_out.weight') h3.add('vae-' + shape[1]);
      if (
        /^(?:model\.)?(?:language_model\.)?(?:layers\.0\.self_attn\.q_proj.weight|embed_tokens.weight)$/.test(
          key,
        )
      )
        h3.add('encoder');
      if (name === 'model.diffusion_model.input_blocks.0.0.weight' && shape[2] === 4 && shape[3] === 320)
        components.add('latent');
      if (
        name === 'model.diffusion_model.input_blocks.1.1.transformer_blocks.0.attn2.to_k.weight' &&
        shape[0] === 768
      )
        components.add('sd15');
      if (name === 'model.diffusion_model.output_blocks.11.0.out_layers.3.weight') components.add('full');
      if (name === 'cond_stage_model.transformer.text_model.embeddings.token_embedding.weight')
        components.add('clip');
      if (name === 'first_stage_model.encoder.conv_in.weight') components.add('encoder');
      if (name === 'first_stage_model.decoder.conv_out.weight') components.add('decoder');
      const motion = /^((?:down|up)_blocks\.[0-3]\.motion_modules\.\d+)\.temporal_transformer\./.exec(name);
      if (
        motion &&
        name.endsWith('.proj_in.weight') &&
        /^(?:down_blocks\.[0-3]\.motion_modules\.[01]|up_blocks\.[0-3]\.motion_modules\.[012])$/.test(
          motion[1],
        )
      )
        motionBlocks.add(motion[1]);
      motionOnly &&= Boolean(motion) || /^mid_block\.motion_modules\.0\.temporal_transformer\./.test(name);
      visual ||= /diffusion_model|^unet\.|^first_stage_model\.|^vae\./.test(name);
      temporal ||= /time_stack|time_mixer|time_mix_blocks|temporal_transformer|temporal_res_block/.test(name);
      tts ||= /^(kokoro\.|bert\.|predictor\.)/.test(name);
    }
    const arch = meta['general.architecture'] || '',
      template = meta['tokenizer.chat_template'] || '';
    let kind = null,
      component = null;
    if (h3.has('condition_proj.weight') && h3.has('video_patch_proj.weight'))
      component = h3.has('audio_patch_proj.weight') ? 'h3-video' : 'h3-image';
    else if (h3.has('vae-768') && h3.has('decoder.mask_token')) component = 'image_vae';
    else if (h3.has('vae-3072') && h3.has('decoder.mask_token')) component = 'video_vae';
    else if (h3.has('dec_in_proj.weight') && h3.has('latents_mean')) component = 'audio_vae';
    else if (
      h3.has('encoder') &&
      (h3.has('text_connector.sink_embedding') || h3.has('h3-32b'))
    )
      component = 'encoder';
    else if (arch === 'clip') component = 'projector';
    if (['qwen2', 'qwen3', 'qwen3moe', 'qwen35'].includes(arch) && template.includes('<|im_start|>'))
      kind = 'text';
    else if (arch === 'gemma4' && template.includes('<|turn>model')) kind = 'text';
    else if (
      !component &&
      (/kokoro/i.test(arch + ' ' + meta['general.name']) || (tts && /kokoro/i.test(path.basename(file))))
    )
      kind = 'audio';
    else if (!component && visual && !temporal && arch !== 'stable-video-diffusion') kind = 'image';
    const value = {
      kind,
      arch,
      name: meta['general.name'] || '',
      projectorType: meta['clip.vision.projector_type'] || meta['clip.projector_type'] || '',
      component,
      sd15: kind === 'image' && components.size === 6,
      motion: motionOnly && motionBlocks.size === 20,
      thinking: kind === 'text' && arch !== 'qwen2' && template.includes('enable_thinking'),
      size: stat.size,
    };
    if (cached.size >= 128) cached.delete(cached.keys().next().value);
    cached.set(file, { stamp, value });
    return value;
  } finally {
    fs.closeSync(fd);
  }
}
module.exports = { metadata };
