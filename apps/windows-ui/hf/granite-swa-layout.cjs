'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { pipeline } = require('node:stream/promises');
const { metadata } = require('./gguf-metadata.cjs');
const { cachedLayout } = require('./cached-layout.cjs');

const gateName = /^blk\.\d+\.ffn_gate_shexp\.weight$/;
// [values per block, bytes per block], from GGML_QUANT_SIZES at b12648.
const blocks = {
  0:[1,4], 1:[1,2], 2:[32,18], 3:[32,20], 6:[32,22], 7:[32,24],
  8:[32,34], 9:[32,36], 10:[256,84], 11:[256,110], 12:[256,144], 13:[256,176],
  14:[256,210], 15:[256,292], 16:[256,66], 17:[256,74], 18:[256,98], 19:[256,50],
  20:[32,18], 21:[256,110], 22:[256,82], 23:[256,136], 29:[256,56], 30:[1,2],
  34:[256,54], 35:[256,66], 39:[32,17], 40:[64,36], 41:[128,18], 42:[64,18], 43:[1,1],
};
function invalid() {
  throw Error('该 Granite SWA 共享专家权重布局无法无损合并，请使用主线格式的 GGUF。');
}
const align = (size, alignment) => Math.ceil(size / alignment) * alignment;

// The early SWASH GGUF exporter split IBM's gate/up matrix into two adjacent
// matrices. Restore the single mainline descriptor without changing the payload.
async function preparedGraniteSwa(file, signal, manifest = '') {
  const { fields, tensors, headerEnd } = metadata(file,true);
  if (!fields.length || headerEnd > 128 * 1024**2) invalid();
  const header = Buffer.alloc(headerEnd);
  const source = await fs.promises.open(file,'r');
  let size;
  try {
    size = (await source.stat()).size;
    for (let read = 0; read < headerEnd;) {
      const part = await source.read(header,read,headerEnd-read,read);
      if (!part.bytesRead) invalid();
      read += part.bytesRead;
    }
  } finally { await source.close(); }
  const alignmentField = fields.find(f => f.key === 'general.alignment');
  if (alignmentField && alignmentField.type !== 4) invalid();
  const alignment = alignmentField ? header.readUInt32LE(alignmentField.end-4) : 32;
  if (!alignment || alignment > 4096 || (alignment & (alignment-1))) invalid();
  const oldStart = align(headerEnd,alignment);
  const byName = new Map(tensors.map(t => [t.name,t]));
  if (byName.size !== tensors.length) invalid();
  const directoryStart = fields.at(-1).end;
  const descriptors = new Map(tensors.map((t,i) => [t.name,header.subarray(
    i ? tensors[i-1].typePosition+12 : directoryStart,t.typePosition+12)]));
  const merged = new Map(), removed = new Set();
  for (const gate of tensors.filter(t => gateName.test(t.name))) {
    const up = byName.get(gate.name.replace('ffn_gate_', 'ffn_up_'));
    const block = blocks[gate.type];
    if (!up || !block || up.type !== gate.type || gate.shape.length !== 2 ||
        up.shape.length !== 2 || !gate.shape.every((v,i) => v > 0 && v === up.shape[i])) invalid();
    const [valuesPerBlock,bytesPerBlock] = block;
    const bytes = gate.shape[0]/valuesPerBlock * bytesPerBlock * gate.shape[1];
    if (gate.shape[0] % valuesPerBlock || !Number.isSafeInteger(bytes) || gate.offset % alignment || gate.offset+bytes !== up.offset ||
        oldStart+up.offset+bytes > size) invalid();
    const descriptor = Buffer.from(descriptors.get(up.name));
    descriptor.writeBigUInt64LE(2n*BigInt(up.shape[1]),descriptor.length-20);
    descriptor.writeBigUInt64LE(BigInt(gate.offset),descriptor.length-8);
    merged.set(gate.name,descriptor);
    removed.add(up.name);
  }
  if (!merged.size) invalid();
  const prefix = Buffer.from(header.subarray(0,directoryStart));
  prefix.writeBigUInt64LE(BigInt(tensors.length-merged.size),8);
  const updated = Buffer.concat([prefix,...tensors.filter(t => !removed.has(t.name))
    .map(t => merged.get(t.name) || descriptors.get(t.name))]);
  const newStart = align(updated.length,alignment);
  const expected = size-oldStart+newStart;
  const identity = createHash('sha256').update(header).update(manifest).digest('hex');
  return cachedLayout(file,'granite-swa',identity,expected,signal,async partial => {
    const disk = await fs.promises.statfs(path.dirname(file));
    if (disk.bavail*disk.bsize < expected+64*1024**2) throw Error('磁盘空间不足，无法准备 Granite SWA 权重。');
    await fs.promises.writeFile(partial,Buffer.concat([updated,Buffer.alloc(newStart-updated.length)]),{flag:'wx'});
    await pipeline(fs.createReadStream(file,{start:oldStart}),fs.createWriteStream(partial,{flags:'a'}),{signal});
  });
}
module.exports = {preparedGraniteSwa,blocks};
