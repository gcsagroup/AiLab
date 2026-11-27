'use strict';
const registry = require('./llama-architectures.json');
const models = new Set(registry.models);
const encoders = new Set([
  'bert',
  'modern-bert',
  'nomic-bert',
  'nomic-bert-moe',
  'neo-bert',
  'jina-bert-v2',
  'jina-bert-v3',
  'eurobert',
  't5encoder',
  'gemma-embedding',
  'gemma-embedding2',
  'llama-embed',
]);
const diffusion = new Set(['dream', 'llada', 'llada-moe', 'rnd1']);
const speech = new Set(['qwen3tts', 'pockettts', 'moshi', 'zonos3', 'kokoro', 'tiny-voca']);
// b12648 server_model_output_modalities lists these heads as decision-only, even with a chat template.
const decisionOnly = new Set([
  'openjev', 'lev', 'kev', 'nimble', 'laya', 'clef', 'pplx-decider', 'vllm-decision2',
  'vllm-d3', 'lfm2-d1', 'lfm2-d1-omni', 'lfm3-d1', 'lfm3-d1-omni', 'h2o-lightning',
  'openbmb-minicpm-ocr-jev',
]);
const drafts = { eagle3: 'draft-eagle3', dflash: 'draft-dflash', 'gemma4-assistant': 'draft-mtp' };
function llamaModel(arch, meta, tokenizer, hasDecisionHead, rankHead) {
  if (!models.has(arch) || meta['general.type'] === 'adapter') return {};
  if (Object.hasOwn(drafts, arch)) return { component: 'draft', specType: drafts[arch] };
  if (arch === 'wavtokenizer-dec') return { kind: 'audio', pipeline: 'llama-vocoder' };
  if (speech.has(arch) || meta['tokenizer.chat_template.tts']) return { component: 'speech-base' };
  if (!tokenizer) return {missingVocabulary:true};
  if (arch === 'deepseek2-ocr') return {component:'ocr-base', pipeline:'llama-ocr', chat:true};
  const pooling = meta[arch + '.pooling_type'];
  const template = meta['tokenizer.chat_template'] || '';
  const museRecipients=['muse-glimmer','muse-spark'].includes(arch) && template.includes('reasoning_strength') &&
    template.includes("message.get('recipient')") && template.includes('<|message|>') && template.includes('<|eom|>');
  // These publisher templates have no enable_thinking switch. A closed
  // assistant reasoning span is the prefix used for a direct answer.
  let reasoningPrefix;
  if (template.includes('</think>') && !template.includes('enable_thinking')) {
    if ((arch==='maple' || (arch==='step35' && meta['step35.attention.sliding_window_pattern']!==false)) &&
        template.includes('<|im_start|>assistant\\n<think>\\n')) reasoningPrefix='open-chatml';
    if (arch==='limite' && template.includes('<|im_start|>assistant\\n')) reasoningPrefix='chatml';
    if (arch==='arwkv7' && template.includes('<｜Assistant｜>')) reasoningPrefix='deepseek';
    if (arch==='flint' && template.includes('<|assistant|>') && template.includes('m.reasoning_content'))
      reasoningPrefix='flint';
  }
  const pleWidth = meta['qwen4exp.embedding_length_per_layer_input'] * meta['qwen4exp.ple.heads_per_ngram'] *
    (meta['qwen4exp.ple.ngram_size'] - 1);
  const ratios=meta['qwen4exp.attention.compress_ratios'];
  const draftLayers=meta['qwen4exp.nextn_predict_layers'];
  const draftOnlyIndexer=ratios && draftLayers>0 && draftLayers<ratios.length &&
    ratios.slice(0,-draftLayers).every(r=>r===0) && ratios.slice(-draftLayers).some(r=>r>0);
  const legacyQwenChat=arch==='qwen' && !template && /(?:^|[\s_-])chat(?:$|[\s_-])/i.test(meta['general.name'] || '');
  const legacyCogChat=arch==='cogvlm' && !template && /^Cogvlm Chat v1\.1$/i.test(meta['general.name'] || '');
  const decisionType = meta[arch + '.decision.type'];
  const harmonyChannels=arch==='maion-coder' && template.includes('<|channel|>final<|message|>') &&
    template.includes('<|channel|>analysis<|message|>') && template.includes('<|start|>assistant');
  const mistralEffort=arch==='mistral4' && template.includes('[MODEL_SETTINGS]') &&
    template.includes('reasoning_effort') && template.includes("['none', 'high']");
  const decision = !!decisionType || hasDecisionHead;
  let pipeline;
  if (decisionOnly.has(decisionType) || (decision && !template && arch !== 'graniteswitch') || ['clef', 'vllm-decision2'].includes(arch))
    pipeline = 'llama-decision';
  else if (pooling === 4 || (rankHead && encoders.has(arch)) || meta['tokenizer.chat_template.rerank'])
    pipeline = 'llama-rerank';
  // llama_model_save_to_file can serialize LLAMA_POOLING_TYPE_UNSPECIFIED (-1) as uint32.
  else if (encoders.has(arch) || [1, 2, 3].includes(pooling)) pipeline = 'llama-embedding';
  else if (arch === 't5') pipeline = 'llama-seq2seq';
  else if (arch === 'plm') pipeline = 'llama-plm';
  else if (arch === 'qwen4exp' && (draftOnlyIndexer || (pleWidth > 0 && meta['qwen4exp.embedding_length'] > 0 &&
           pleWidth !== meta['qwen4exp.embedding_length']))) pipeline = 'llama-qwen4exp-ple';
  else if (arch === 'step35' && meta['step35.attention.sliding_window_pattern']===false) pipeline='llama-step35-full';
  else if (diffusion.has(arch)) pipeline = 'llama-diffusion';
  else if (legacyQwenChat || legacyCogChat) pipeline='llama-chat';
  else if (
    template &&
    !(
      (['qwen2', 'qwen3', 'qwen3moe', 'qwen35'].includes(arch) && template.includes('<|im_start|>')) ||
      (arch === 'gemma4' && template.includes('<|turn>model'))
    )
  )
    pipeline = 'llama-chat';
  return {
    kind: 'text',
    pipeline,
    decision,
    chat: !!template || legacyQwenChat || legacyCogChat,
    ...(template.includes('<|im_start|>') && (arch==='qwen35' || (arch==='qwen4exp' && template.includes('<think>')))
      ? { nativeThinkPrefill: true } : {}),
    ...(legacyCogChat ? {legacyCogChat:true} : {}),
    ...(arch==='minimax-01' && meta['tokenizer.ggml.normalizer.nfc'] ? {normalizeNfc:true} : {}),
    ...(legacyQwenChat ? {legacyQwenChat:true} : {}),
    // Older EXAONE MoE exports omit the fixed sigmoid router used in the
    // publisher's reference model. Honor explicitly declared router types.
    ...(arch==='exaone-moe' && meta['exaone-moe.expert_gating_func']===undefined ? {defaultExaoneRouter:true} : {}),
    ...(reasoningPrefix ? {reasoningPrefix} : {}),
    ...(museRecipients ? {museRecipients:true} : {}),
    ...(harmonyChannels ? {harmonyChannels:true} : {}),
    ...(mistralEffort ? {mistralEffort:true} : {}),
    thinking: !!reasoningPrefix || museRecipients || harmonyChannels || mistralEffort || (template.includes('enable_thinking') && arch !== 'qwen2') ||
      (arch === 'gpt-oss' && template.includes('<|channel|>') && template.includes('<|message|>')) ||
      (['inkling2','inkling2_loop'].includes(arch) && template.includes('<|content_thinking|>') && template.includes('<|content_text|>')),
  };
}
module.exports = { llamaModel };
