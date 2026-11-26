'use strict';
const fs = require('node:fs');
const { metadata } = require('./gguf-metadata.cjs');

// audio.cpp 0.9.5 (61c7838b), Qwen3TTSGenerationOptions. The checkpoint
// supplies the length limit. Session::generation_options_from_request_impl
// takes the other sampling defaults from the backend, even for CUSTOMVOICE.
const sampling = Object.freeze({
  do_sample: true, temperature: 0.9, top_k: 50, top_p: 1, repetition_penalty: 1.05,
  subtalker_do_sample: true, subtalker_temperature: 0.9, subtalker_top_k: 50, subtalker_top_p: 1,
});

function checkpointLimit(file) {
  const { fields } = metadata(file, true);
  const field = suffix => fields.find(item => item.key === 'audiocpp.embedded_files.' + suffix);
  const names = field('names'), offsets = field('offsets'), data = field('data');
  if (!names) return;
  const fd = fs.openSync(file, 'r');
  try {
    // Each GGUF array starts with the field type, element type and a uint64 count.
    // Seek past unrelated assets (including the tokenizer) without loading them.
    function read(entry, position, size) {
      if (!entry || !Number.isSafeInteger(position) || position < entry.start ||
          !Number.isSafeInteger(size) || size < 0 || position + size > entry.end)
        throw Error('Qwen3-TTS 的 GGUF 内嵌配置目录无效。');
      const buffer = Buffer.alloc(size);
      if (fs.readSync(fd, buffer, 0, size, position) !== size) throw Error('Qwen3-TTS 的模型配置不完整。');
      return buffer;
    }
    const filename = 'generation_config.json';
    for (let pos = names.start + 16, index = 0; pos < names.end; index++) {
      const length = Number(read(names, pos, 8).readBigUInt64LE());
      pos += 8;
      if (length === filename.length && read(names, pos, length).toString() === filename) {
        const pair = read(offsets, offsets?.start + 16 + 8 * index, 16);
        const from = Number(pair.readBigUInt64LE()), to = Number(pair.readBigUInt64LE(8));
        if (to - from > 1024 * 1024) throw Error('Qwen3-TTS 的 generation_config.json 过大。');
        const config = JSON.parse(read(data, data?.start + 16 + from, to - from).toString('utf8'));
        return config.max_new_tokens;
      }
      pos += length;
    }
  } finally {
    fs.closeSync(fd);
  }
}

function generationOptions(model, requestedLimit) {
  const embedded = requestedLimit === undefined ? checkpointLimit(model) : undefined;
  return {
    sampling, text_chunk_size: 8192,
    max_tokens: requestedLimit ?? embedded ?? 2048,
    max_tokens_source: requestedLimit !== undefined ? 'request' :
      embedded !== undefined ? 'generation_config.json' : 'audio.cpp',
  };
}

module.exports = { generationOptions };
