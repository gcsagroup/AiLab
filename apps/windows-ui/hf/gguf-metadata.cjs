'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');

// Read only the metadata and tensor directory; large arrays (tokenizer scores,
// token strings, etc.) are skipped without materializing the weight data.
const { llamaModel } = require('./llama-model.cjs');
const audioTasks = new Map([
  ['firered_vad', 'vad'], ['pulsevad', 'vad'],
  ['citrinet_asr', 'asr'], ['kroko_asr', 'asr'], ['moonshine_asr', 'asr'], ['canary_asr', 'asr'],
  ['piper_tts', 'tts'], ['sanotts', 'tts'], ['inflect_v2', 'tts'], ['kitten_tts', 'tts'],
  ['moss_tts_nano', 'tts'], ['pocket_tts_small', 'tts'],
  ['soprano_tts', 'tts'], ['gradium_phonon', 'tts'], ['supertonic', 'tts'], ['voxcpm1', 'tts'],
  ['magenta_realtime_2', 'gen'], ['stable_audio', 'gen'],
]);
const cached = new Map();
// Bytes per GGML block. Low-memory MoE conversion applies only to routed
// expert matrices; attention, routers, shared experts and the LM head keep their precision.
const compactProfiles = {
  cogvlm:'q4_0', rnd1:'q4_0', 'kimi-k3':'q2_0',
  mistral4:'q1_0', step35:'q1_0', dbrx:'q1_0', 'maion-coder':'q1_0', deepseek4:'q1_q4',
};
const sourceBlocks = {1:[1,2],2:[32,18],8:[32,34],10:[256,84],16:[256,66],17:[256,74],19:[256,50],22:[256,82],29:[256,56]};
const shortGraphs = require('./cpu-short-context.json');
function measuredCpuProfile(arch, size, fd, length) {
  const family=Object.hasOwn(shortGraphs,arch) && shortGraphs[arch];
  const known=family && (family.sourceBytes===size ? family : family.prepared);
  if (!known || known.sourceBytes!==size || length>16*1024**2) return undefined;
  const hash=createHash('sha256'), chunk=Buffer.alloc(65536);
  for (let offset=0; offset<length;) {
    const count=fs.readSync(fd,chunk,0,Math.min(length-offset,chunk.length),offset);
    if (!count) throw Error('GGUF 目录不完整。');
    hash.update(chunk.subarray(0,count));
    offset+=count;
  }
  return hash.digest('hex')===known.directorySha256 ? known : undefined;
}
const compactBlocks = {q4_0:[32,18],q2_0:[64,18],q1_0:[128,18]};
function tensorPrecision(profile,name) {
  if (profile!=='q1_q4') return profile;
  if (/_exps\.weight$/.test(name)) return 'q1_0';
  return name==='token_embd.weight' || /^blk\.\d+\.(?:attn_(?:output_[ab]|q_[ab]|kv)|ffn_(?:up|gate|down)_shexp)\.weight$/.test(name) ? 'q4_0' : undefined;
}
function compactSaving(profile, name, shape, type, alignment) {
  const precision=tensorPrecision(profile,name);
  if (!precision || !sourceBlocks[type] || shape.length<2 || shape.length>3 || shape[1]<=1 ||
      !(name==='token_embd.weight' && profile==='q1_q4') && !/^blk\..+\.weight$/.test(name)) return 0;
  const expert=precision==='q1_0';
  if (expert ? (shape.length!==3 || !/_exps\.weight$/.test(name) || type===1 || type===8)
             : (type!==8 && (precision!=='q4_0' || type!==1))) return 0;
  const [width,bytes]=compactBlocks[precision];
  if (shape[0]<=0 || shape[0]>1048576 || shape[0]%width!==0) return 0;
  if (!Number.isSafeInteger(alignment) || alignment<1 || alignment>65536 || (alignment & (alignment-1))!==0)
    throw Error('GGUF 张量对齐值无效。');
  const elems=shape.reduce((total,axis)=>total*axis,1);
  if (!Number.isSafeInteger(elems*2)) throw Error('GGUF 张量大小无效。');
  const [fromWidth,fromBytes]=sourceBlocks[type];
  const padded=n=>Math.ceil(n/alignment)*alignment;
  return padded(elems/fromWidth*fromBytes)-padded(elems/width*bytes);
}
// Published Apertus Instruct templates with matching text turns but incompatible tool parsers.
const apertusTemplates = new Set([
  '00067a2e29980bd17baa6a745a54556295f9fdda712d41f9c9a886376988e363',
  '56f72c27fa2e565312a830b7315a455c79fb452fdbe7a5b7595d8a094f282b07',
]);
const irisMatrix = /^(?:y_embedder\.refiner\.)?blocks\.\d+\.mlp(?:_[xy])?\.w2\.weight$/;
const qwenPleDimensions = new Set(['qwen4exp.embedding_length', 'qwen4exp.embedding_length_per_layer_input',
  'qwen4exp.ple.ngram_size', 'qwen4exp.ple.heads_per_ngram', 'qwen4exp.nextn_predict_layers']);
function metadata(file, directory = false) {
  const stat = fs.statSync(file);
  const stamp = stat.size + ':' + stat.mtimeMs;
  if (!directory && cached.get(file)?.stamp === stamp) return cached.get(file).value;
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
    let tokenizer = false, decisionHead = false, rankHead = false, legacyInklingQueries = 0;
    let vocabulary, chameleonSeparator;
    const fieldsOnDisk = [], tensorsOnDisk = [];
    let senseNovaPatch=false, senseNovaGenerator=false;
    const originalMatrices = new Map(), packedMatrices = {};
    if (fields > 100000 || tensors > 1000000) throw Error('GGUF 目录过大。');
    for (let i = 0; i < fields; i++) {
      const key = str(true), valueStart = pos, type = u32();
      if (key.endsWith('.decision.labels') || key.endsWith('.decision.block_count')) decisionHead = true;
      if (key === 'tokenizer.ggml.tokens' && type === 9) tokenizer = true;
      if (type === 8) {
        const keep = [
          'general.name',
          'general.type',
          'general.architecture',
          'adapter.type',
          'audiocpp.model_spec.family',
          'tokenizer.chat_template',
          'tokenizer.chat_template.rerank',
          'tokenizer.chat_template.tts',
          'clip.audio.projector_type',
          'clip.vision.projector_type',
          'clip.projector_type',
        ].includes(key) || key.endsWith('.decision.type');
        const value = str(keep);
        if (keep) meta[key] = value;
      } else if (type === 9) {
        const elem = u32(),
          count = u64();
        if (key==='minimax-01.attention.recurrent_layers') meta[key]=true;
        if (key==='qwen4exp.ple.layers') meta[key]=count;
        if (elem === 8 && count > 2000000) throw Error('GGUF 字符串表过大。');
        if (elem === 8) {
          if (key==='tokenizer.ggml.tokens') vocabulary={start:pos,count};
          for (let j = 0; j < count; j++) str(false);
        } else if (key==='qwen4exp.attention.compress_ratios' && [4,5].includes(elem) && count>0 && count<=1024) {
          meta[key]=Array.from({length:count},()=>u32());
        } else if (key==='step35.attention.sliding_window_pattern' && elem===7 && count>0 && count<=1024) {
          meta[key]=take(count).includes(1);
        } else if (key.startsWith('comfy.gguf.orig_shape.') && irisMatrix.test(key.slice(22)) &&
                   [4,5].includes(elem) && count === 2) {
          const rows = u32(), columns = u32();
          originalMatrices.set(key.slice(22), [columns, rows]);
        } else if (widths[elem]) skip(widths[elem] * count);
        else throw Error('GGUF 元数据类型不受支持。');
      } else if (type === 7 && ['clip.has_gen_audio_encoder','clip.has_audio_encoder','clip.has_vision_encoder','tokenizer.ggml.normalizer.nfc','ailab.cpu_no_repack'].includes(key)) meta[key]=!!take(1)[0];
      else if ((/\.(block_count|embedding_length|attention\.(head_count|head_count_kv|key_length|value_length))$/.test(key) || key.endsWith('.pooling_type') || key.endsWith('.context_length') || ['clip.audio.projection_dim','clip.vision.projection_dim'].includes(key) || key==='exaone-moe.expert_gating_func' || qwenPleDimensions.has(key) ||
                key==='general.alignment' || key==='split.count' || key==='gemma4.embedding_length_per_layer_input' || key==='minimax-01.block_count' || key==='minimax-01.full_attention_interval') && [0,1,2,3,4,5].includes(type)) {
        const size = widths[type], buf = take(size);
        meta[key] = type % 2 ? buf.readIntLE(0,size) : buf.readUIntLE(0,size);
      }
      else if (widths[type]) skip(widths[type]);
      else throw Error('GGUF 元数据类型无效。');
      if (directory) fieldsOnDisk.push({key, type, start: valueStart, end: pos});
    }
    if (!directory && vocabulary && meta['general.architecture']==='chameleon' && !meta['tokenizer.chat_template']) {
      const end=pos;
      pos=vocabulary.start;
      for (let i=0;i<vocabulary.count;i++) {
        const length=u64();
        if (length===15 && take(length).toString()==='<reserved08706>') {chameleonSeparator=i;break;}
        if (length!==15) skip(length);
      }
      pos=end;
    }
    let visual = false,
      temporal = false,
      tts = false;
    const components = new Set();
    const motionBlocks = new Set();
    let motionOnly = tensors > 0;
    const h3 = new Set();
    const upscaler = new Set();
    const mosr = new Set();
    const zDenoiser = new Set(), qwenEncoder = new Set(), fluxVae = new Set();
    const wanVae = new Set();
    const gptjProjections = new Set();
    const zayaLayers = new Set();
    const iris = new Set();
    const anima = new Set();
    const minimaxLayers = new Map();
    let hasPleTable=false, legacyQ4=false, legacyGraniteShared=false, legacyCogQkv=false, splitVisionQ=false;
    let compactSavings=0;
    const compactText=!(meta['split.count']>1) && Object.hasOwn(compactProfiles,meta['general.architecture']) && compactProfiles[meta['general.architecture']];
    const alignment=meta['general.alignment'] ?? 32;
    let animaTextEmbedding = false, animaLastLayer = false;
    let irisTextEmbedding = false;
    let wanPatch = false, wanHead = false, umt5Embedding = false, umt5AttentionBias = false;
    for (let i = 0; i < tensors; i++) {
      const name = str(true),
        dims = u32();
      if (!dims || dims > 5) throw Error('GGUF 张量维数无效。');
      if (dims===2 && name==='per_layer_token_embd.weight') hasPleTable=true;
      if (meta['general.architecture']==='minimax-01') {
        const attention=/^blk\.(\d+)\.attn_(qkv|q|k|v|gate|norm_2)\.weight$/.exec(name);
        if (attention) {
          const layer=Number(attention[1]);
          if (!minimaxLayers.has(layer)) minimaxLayers.set(layer,new Set());
          minimaxLayers.get(layer).add(attention[2]);
        }
      }
      rankHead ||= name === 'cls.weight' || name === 'cls.output.weight';
      decisionHead ||= name.startsWith('decision.');
      const shape = Array.from({ length: dims }, u64);
      if (compactText==='q4_0' && meta['general.architecture']==='cogvlm' && /^blk\.\d+\.(?:vis_)?attn_q\.weight$/.test(name)) legacyCogQkv=true;
      if (name==='v.blk.0.attn_q.weight') splitVisionQ=true;
      const typePosition=pos, tensorType=u32();
      if (compactText) compactSavings+=compactSaving(compactText,name,shape,tensorType,alignment);
      if (tensorType>=31 && tensorType<=33) legacyQ4=true;
      if (meta['general.architecture']==='granite_swa' && /^blk\.\d+\.ffn_gate_shexp\.weight$/.test(name))
        legacyGraniteShared=true;
      if (directory) tensorsOnDisk.push({name, shape, type: tensorType, typePosition, offset: u64()});
      else skip(8);
      if (meta['general.architecture'] === 'inkling2' &&
          (name === 'loop_kv_res_query.weight' || name === 'loop_res_query.weight')) legacyInklingQueries++;
      const original = originalMatrices.get(name);
      if (meta['general.architecture'] === 'gptj' && /^blk\.0\.attn[._][qkv](?:_proj)?\.weight$/.test(name))
        gptjProjections.add(name);
      if (meta['general.architecture'] === 'zaya' &&
          ['blk.0.cca_conv_grp.weight','blk.0.cca_val_proj1.weight','blk.0.cca_val_proj2.weight','blk.1.zaya_router_mlp4.weight'].includes(name))
        zayaLayers.add(name);
      if (meta['general.architecture'] === 'iris' && original && original.join(',') !== shape.join(',')) {
        if (dims !== 2 || original[0] !== 6826 || original[1] !== 2560 ||
            shape[0] * shape[1] !== original[0] * original[1]) throw Error('Iris GGUF 原始矩阵形状不匹配。');
        packedMatrices[name] = original;
      }
      if (!meta['general.architecture']) {
        if ((name === 'cap_embedder.1.weight' && shape[0] === 2560 && shape[1] === 3840) ||
            (name === 'noise_refiner.0.attention.qkv.weight' && shape[0] === 3840 && shape[1] === 11520) ||
            (name === 'x_embedder.weight' && shape[0] === 64 && shape[1] === 3840) ||
            (name === 'final_layer.linear.weight' && shape[0] === 3840 && shape[1] === 64)) zDenoiser.add(name);
        if ((name === 'model.embed_tokens.weight' && shape[0] === 2560 && shape[1] === 151936) ||
            (name === 'model.layers.35.self_attn.q_norm.weight' && shape[0] === 128) ||
            (name === 'model.norm.weight' && shape[0] === 2560)) qwenEncoder.add(name);
        if ((name === 'decoder.conv_in.weight' && shape[2] === 16 && shape[3] === 512) ||
            (name === 'encoder.conv_out.weight' && shape[2] === 512 && shape[3] === 32) ||
            (name === 'decoder.conv_out.weight' && shape[2] === 128 && shape[3] === 3)) fluxVae.add(name);
      }
      const key = name.replace(
        /^(?:model\.diffusion_model\.|diffusion_model\.|first_stage_model\.|vae\.|cond_stage_model\.)/,
        '',
      );
      if ((key === 'net.x_embedder.proj.1.weight' && shape.join(',') === '68,2048') ||
          (key === 'net.llm_adapter.embed.weight' && shape.join(',') === '1024,32128') ||
          (key === 'net.final_layer.linear.weight' && shape.join(',') === '2048,64')) anima.add(key);
      if (name === 'token_embd.weight' && shape.join(',') === '1024,151936') animaTextEmbedding = true;
      if (name === 'blk.27.attn_q_norm.weight' && shape.join(',') === '128') animaLastLayer = true;
      if (key === 'patch_embedding.weight' && shape.join(',') === '2,2,1,16,1536') wanPatch = true;
      if (key === 'head.modulation' && shape[0] === 1536) wanHead = true;
      if (name === 'token_embd.weight' && shape[0] === 4096 && shape[1] === 256384) umt5Embedding = true;
      if (meta['general.architecture'] === 'qwen3vl' && name === 'token_embd.weight' && shape[0] === 2560)
        irisTextEmbedding = true;
      if (key === 'y_embedder.layer_pool.weight' || key === 'modulation_cores.adaln_img.weight') iris.add(key);
      if (name === 'enc.blk.0.attn_rel_b.weight' && shape[0] === 64) umt5AttentionBias = true;
      // sd-cli stores 3D convolutions in four GGUF dimensions by folding the two channel axes.
      if ((key === 'conv2.weight' && ['1,1,1,256','1,1,1,16,16'].includes(shape.join(','))) ||
          (key === 'decoder.conv1.weight' && ['3,3,3,6144','3,3,3,16,384'].includes(shape.join(','))) ||
          (key === 'encoder.conv1.weight' && ['3,3,3,288','3,3,3,3,96'].includes(shape.join(',')))) wanVae.add(key);
      if (['conv_first.weight','body.0.rdb1.conv1.weight','conv_up1.weight','conv_up2.weight','conv_last.weight'].includes(name))
        upscaler.add(name);
      if (dims === 4 && ((name === 'gblocks.0.weight' && shape[2] === 3) ||
          (name === 'upsampler.0.weight' && shape[3] === 48) ||
          name === 'gblocks.1.fc1.weight' || name === 'gblocks.1.conv.weight'))
        mosr.add(name);
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
      if (key.endsWith('fm_modules.vision_model_mot_gen.embeddings.patch_embedding.weight')) senseNovaPatch=true;
      if (key.endsWith('language_model.model.layers.0.self_attn.q_proj_mot_gen.weight')) senseNovaGenerator=true;
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
    if (directory) return {fields: fieldsOnDisk, tensors: tensorsOnDisk, headerEnd: pos, alignment};
    const sourceArch = meta['general.architecture'] || '';
    const depth=meta['minimax-01.block_count'];
    let minimaxInterval;
    if (sourceArch==='minimax-01' && depth===minimaxLayers.size && depth>0 && depth<=1024 &&
        !meta['minimax-01.attention.recurrent_layers'] && meta['minimax-01.full_attention_interval']===undefined) {
      const layers=Array.from({length:depth},(_,i)=>minimaxLayers.get(i));
      // Match all discriminating tensors before overriding b12648's default
      // interval of eight. A partial GGUF shard cannot establish this pattern.
      const dense=layers.map(names=>names?.has('q') && names.has('k') && names.has('v') && !names.has('gate'));
      const linear=layers.map(names=>names?.has('qkv') && names.has('gate') && names.has('norm_2') && !names.has('q'));
      const period=dense.indexOf(true)+1 || depth+1;
      if (period!==8 && dense.every((v,i)=>v || linear[i]) && dense.every((v,i)=>Boolean(v)===((i+1)%period===0)))
        minimaxInterval=period;
    }
    const arch = zayaLayers.size === 4 ? 'zaya1' : sourceArch,
      fileType = meta['general.type'];
    let kind = null,
      component = null;
    const pleOnly=hasPleTable && tensors===1;
    if (pleOnly) component='ple_table';
    else if (h3.has('condition_proj.weight') && h3.has('video_patch_proj.weight'))
      component = h3.has('audio_patch_proj.weight') ? 'h3-video' : 'h3-image';
    else if (h3.has('vae-768') && h3.has('decoder.mask_token')) component = 'image_vae';
    else if (h3.has('vae-3072') && h3.has('decoder.mask_token')) component = 'video_vae';
    else if (h3.has('dec_in_proj.weight') && h3.has('latents_mean')) component = 'audio_vae';
    else if (
      h3.has('encoder') &&
      (h3.has('text_connector.sink_embedding') || h3.has('h3-32b'))
    )
      component = 'encoder';
    else if (iris.size === 2 && arch === 'iris') component = 'iris';
    else if (anima.size === 3) component = 'anima';
    else if (wanPatch && wanHead) component = 'wan21-t2v';
    else if (wanVae.size === 3) component = 'wan_vae';
    else if (arch === 'clip' || fileType === 'mmproj') component = 'projector';
    else if (!visual && zDenoiser.size === 4) component = 'z-image';
    else if (!visual && qwenEncoder.size === 3) component = 'qwen3_encoder';
    else if (!visual && fluxVae.size === 3) component = 'flux_vae';
    const llama = arch === 'gptj' && tokenizer && !component && !visual && gptjProjections.size === 3
      ? {kind:'text',pipeline:'llama-gptj'} : !component && !visual ? llamaModel(arch, meta, tokenizer, decisionHead, rankHead) : {};
    const declaredFamily = meta['audiocpp.model_spec.family'];
    const audioFamily = arch === 'audiocpp' || arch === declaredFamily ? declaredFamily : undefined;
    const nativeAudio = audioFamily && !audioTasks.has(audioFamily) && require('./generation-packages.cjs').nativeAudio(audioFamily);
    const audioTask = audioTasks.get(audioFamily) || nativeAudio?.task;
    const upscalePipeline = upscaler.size === 5 ? 'esrgan-x4' : mosr.size === 4 ? 'mosr-x4' : undefined;
    if (llama.component) component = llama.component;
    if (llama.kind) kind = llama.kind;
    else if (audioTask) kind = 'audio';
    else if (
      !component &&
      (/kokoro/i.test(arch + ' ' + meta['general.name']) || (tts && /kokoro/i.test(path.basename(file))))
    )
      kind = 'audio';
    else if (!component && arch !== 'audiocpp' && ((visual && !temporal && arch !== 'stable-video-diffusion') || upscalePipeline)) kind = 'image';
    const cpuProfile=(compactSavings>0 || meta['ailab.cpu_no_repack']) && measuredCpuProfile(arch,stat.size,fd,pos);
    const value = {
      ...llama,
      ...(pleOnly ? {pleOnly:true} : {}),
      ...(hasPleTable ? {hasPleTable:true} : {}),
      ...((arch==='qwen4exp' && meta['qwen4exp.ple.layers']>0) ||
          (arch==='gemma4' && meta['gemma4.embedding_length_per_layer_input']>0) ? {requiresPleTable:true} : {}),
      ...(fileType==='adapter' && meta['adapter.type']==='lora' ? {lora:true} : {}),
      ...(minimaxInterval ? {minimaxInterval} : {}),
      kind,
      arch,
      ...(cpuProfile ? {shortContextGraphMiB:cpuProfile.graphMiB} : {}),
      ...(cpuProfile?.moeWindowBytes ? {mappedCpuWindowBytes:cpuProfile.moeWindowBytes} : {}),
      ...(cpuProfile?.prepared ? {preparedCpuWindowBytes:cpuProfile.prepared.moeWindowBytes} : {}),
      ...(meta['ailab.cpu_no_repack'] ? {cpuNoRepack:true} : {}),
      ...(compactSavings>0 && compactSavings<stat.size ? {compactTextType:compactText,compactTextBytes:stat.size-compactSavings+alignment+128} : {}),
      ...(arch !== sourceArch ? {sourceArchitecture:sourceArch,legacyZayaLayers:true} : {}),
      ...(legacyInklingQueries === 2 ? {legacyInklingLoop: true} : {}),
      ...(legacyQ4 ? {legacyQ4:true} : {}),
      ...(legacyGraniteShared ? {legacyGraniteShared:true} : {}),
      ...(legacyCogQkv ? {legacyCogQkv:true} : {}),
      ...(splitVisionQ && (meta['clip.projector_type'] ?? meta['clip.vision.projector_type'])==='cogvlm' ? {legacyCogProjector:true} : {}),
      ...(chameleonSeparator!==undefined ? {chameleonSeparator} : {}),
      apertusChatTemplate: arch === 'apertus' && apertusTemplates.has(
        createHash('sha256').update(meta['tokenizer.chat_template'] || '').digest('hex')),
      trainedContext: meta[sourceArch + '.context_length'],
      kvElementsPerToken: (meta[sourceArch+'.block_count'] || 0) * (meta[sourceArch+'.attention.head_count_kv'] ?? meta[sourceArch+'.attention.head_count'] ?? 0) *
        ((meta[sourceArch+'.attention.key_length'] ?? meta[sourceArch+'.embedding_length']/meta[sourceArch+'.attention.head_count']) +
         (meta[sourceArch+'.attention.value_length'] ?? meta[sourceArch+'.embedding_length']/meta[sourceArch+'.attention.head_count'])) || 0,
      ...(arch==='moshi' || arch==='deepseek2-ocr' ? {modelWidth:meta[arch+'.embedding_length']} : {}),
      ...(component==='projector' ? {projectionWidth:meta['clip.vision.projection_dim'] || meta['clip.audio.projection_dim']} : {}),
      audioFamily, audioTask,
      nativeRecipe:nativeAudio ? audioFamily : undefined,
      pipeline: audioTask ? (audioFamily === 'firered_vad' ? 'firered-vad' : 'audiocpp-' + audioTask) :
        upscalePipeline || llama.pipeline,
      name: meta['general.name'] || '',
      generatesAudio: !!meta['clip.has_gen_audio_encoder'],
      acceptsAudio: !!meta['clip.has_audio_encoder'],
      acceptsImage: !!meta['clip.has_vision_encoder'],
      projectorType: meta['clip.vision.projector_type'] || meta['clip.projector_type'] || meta['clip.audio.projector_type'] || '',
      component,
      wanTextEncoder: arch === 't5encoder' && umt5Embedding && umt5AttentionBias,
      irisTextEncoder: irisTextEmbedding && tokenizer,
      animaTextEncoder: arch === 'qwen3' && tokenizer && animaTextEmbedding && animaLastLayer,
      irisPackedMatrices: Object.keys(packedMatrices).length ? packedMatrices : undefined,
      ...(senseNovaPatch && senseNovaGenerator ? {senseNovaImage:true} : {}),
      sd15: kind === 'image' && components.size === 6,
      motion: motionOnly && motionBlocks.size === 20,
      thinking: !!llama.thinking,
      size: stat.size,
    };
    if (cached.size >= 128) cached.delete(cached.keys().next().value);
    cached.set(file, { stamp, value });
    return value;
  } finally {
    fs.closeSync(fd);
  }
}
module.exports = { metadata, compactSaving, compactProfiles };
