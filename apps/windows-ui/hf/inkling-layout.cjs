'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { cachedLayout } = require('./cached-layout.cjs');
const { metadata } = require('./gguf-metadata.cjs');

function integer(value, width) {
  const buffer = Buffer.alloc(width);
  if (width === 8) buffer.writeBigUInt64LE(BigInt(value));
  else buffer.writeUIntLE(value, 0, width);
  return buffer;
}
function string(value) {
  const bytes = Buffer.from(value);
  return Buffer.concat([integer(bytes.length, 8), bytes]);
}
const align = (size, alignment) => Math.ceil(size / alignment) * alignment;
const scalar = (value) => Buffer.concat([integer(4, 4), integer(value, 4)]);
function invalid() { throw Error('Inkling 循环布局与该发行版本不一致，请选择发布者的 Mainline_Support GGUF。'); }

// Older Inkling-2 releases describe logical passes as separate blocks. Quantized
// matrices are identical in the mainline layout. Only the two F32 controller
// tables need their rows interleaved. Preserve tokenizer metadata byte for byte.
function layout(directory, header, size) {
  const { fields, tensors, headerEnd } = directory;
  const values = new Map(fields.map(({key,start,end}) => [key, header.subarray(start, end)]));
  const read = key => {
    const field = values.get(key);
    if (field?.length !== 8 || field.readUInt32LE() !== 4) invalid();
    return field.readUInt32LE(4);
  };
  const alignment = values.has('general.alignment') ? read('general.alignment') : 32;
  if (!alignment || alignment > 4096 || (alignment & (alignment - 1)) !== 0) invalid();
  const oldStart = align(headerEnd, alignment);
  const start = read('inkling2.loop.core_start'), end = read('inkling2.loop.core_end');
  const passes = read('inkling2.num_loops'), logical = read('inkling2.block_count');
  const layers = end - start, physical = logical - (passes - 1) * layers;
  const width = read('inkling2.embedding_length'), row = width * 4;
  if (passes < 2 || layers <= 0 || end > physical || logical > 4096 ||
      !width || width > 65536 || row % alignment) invalid();
  const dataSize = size - oldStart, tableSize = 2 * layers * row;
  if (tableSize > 32 * 1024**2) invalid();
  const names = ['loop_kv_res_query.weight', 'loop_res_query.weight'];
  if (tensors.length <= 2 || names.some((name,i) => {
    const t = tensors[i];
    return t.name !== name || t.type !== 0 || t.shape.join(',') !== [width, 2 * layers].join(',') ||
      t.offset !== i * tableSize;
  }) || tensors[2].offset !== 2 * tableSize || tensors.at(-1).offset >= dataSize) invalid();

  const count = tensors.length - 2 + layers;
  const parts = [header.subarray(0,8), integer(count,8), integer(fields.length + 1,8)];
  const rename = {'num_loops':'loop.count','loop.core_start':'loop.start','loop.core_end':'loop.end'};
  const perBlock = new Set(['attention.head_count','attention.head_count_kv','attention.sliding_window_pattern']);
  for (const [key, raw] of values) {
    if (key === 'general.architecture') {
      parts.push(string(key), integer(8,4), string('inkling2_loop'));
      continue;
    }
    if (!key.startsWith('inkling2.')) { parts.push(string(key),raw); continue; }
    const suffix = key.slice('inkling2.'.length);
    parts.push(string('inkling2_loop.' + (rename[suffix] || suffix)));
    if (suffix === 'block_count') { parts.push(scalar(physical)); continue; }
    if (!perBlock.has(suffix) || raw.readUInt32LE() !== 9) { parts.push(raw); continue; }
    const element = raw.readUInt32LE(4), bytes = element === 7 ? 1 : [4,5].includes(element) ? 4 : 0;
    if (!bytes || raw.readBigUInt64LE(8) !== BigInt(logical) || raw.length !== 16 + bytes * logical) invalid();
    const entries = raw.subarray(16);
    const firstPass = entries.subarray(bytes * start, bytes * end);
    for (let i = 1; i < passes; i++)
      if (!entries.subarray(bytes*(start+i*layers),bytes*(end+i*layers)).equals(firstPass)) invalid();
    parts.push(raw.subarray(0,8),integer(physical,8),entries.subarray(0,end*bytes),
      entries.subarray((end+(passes-1)*layers)*bytes));
  }
  parts.push(string('inkling2_loop.loop.varying'),integer(7,4),Buffer.from([0]));
  function tensor(name, shape, type, offset) {
    parts.push(string(name),integer(shape.length,4),...shape.map(n=>integer(n,8)),integer(type,4),integer(offset,8));
  }
  const prefixes = {attn:'q',k:'k',v:'v',mlp:'ffn'};
  let previous = -1;
  for (const t of tensors.slice(2)) {
    if (t.offset <= previous || t.offset % alignment || t.offset >= dataSize) invalid();
    previous = t.offset;
    const name = t.name.replace(/^((?:blk\.\d+)\.loop_)(attn|k|v|mlp)_(down|gain|forget)\.weight$/,
      (_,prefix,group,suffix)=>prefix+prefixes[group]+'_ctrl_'+suffix+'.weight');
    tensor(name,t.shape,t.type,t.offset-2*tableSize);
  }
  const unchanged = dataSize - 2 * tableSize;
  if (unchanged % alignment) invalid();
  for (let i = 0; i < layers; i++)
    tensor('blk.'+(start+i)+'.loop_msg_query.weight',[width,4],0,unchanged + 4*i*row);
  const bytes = Buffer.concat(parts);
  return {header:Buffer.concat([bytes,Buffer.alloc(align(bytes.length,alignment)-bytes.length)]),
    oldStart,unchanged,tableSize,layers,row};
}
async function readInto(handle, buffer, offset) {
  for (let done = 0; done < buffer.length;) {
    const {bytesRead} = await handle.read(buffer,done,buffer.length-done,offset+done);
    if (!bytesRead) throw Error('Inkling GGUF 权重不完整。');
    done += bytesRead;
  }
}
async function preparedInkling(file, signal, manifest = '') {
  const dir = path.dirname(file), source = await fs.open(file,'r');
  try {
    const stat = await source.stat(), directory = metadata(file,true);
    if (directory.headerEnd > 64 * 1024**2) invalid();
    const header = Buffer.alloc(directory.headerEnd);
    await readInto(source,header,0);
    const plan = layout(directory,header,stat.size);
    const {oldStart,unchanged,tableSize,layers,row} = plan;
    const identity = createHash('sha256').update(header).update(manifest).digest('hex');
    const expected = plan.header.length + stat.size - oldStart;
    return await cachedLayout(file,'inkling',identity,expected,signal,async partial => {
      const disk = await fs.statfs(dir);
      if (disk.bavail * disk.bsize < expected + 64 * 1024**2)
        throw Error('旧版 Inkling GGUF 首次试用需要 '+(expected/1024**3).toFixed(2)+' GiB 磁盘空间来准备主线布局。');
      const output = await fs.open(partial,'wx');
      try {
        await output.writeFile(plan.header);
        const buffer = Buffer.alloc(Math.min(4*1024**2,unchanged));
        for (let pos = 0; pos < unchanged;) {
          signal?.throwIfAborted();
          const block = buffer.subarray(0,Math.min(buffer.length,unchanged-pos));
          await readInto(source,block,oldStart+2*tableSize+pos);
          await output.writeFile(block); pos += block.length;
        }
        const controls = Buffer.alloc(2*tableSize);
        await readInto(source,controls,oldStart);
        for (let i = 0; i < layers; i++) {
          const at = 2*i*row;
          await output.writeFile(Buffer.concat([controls.subarray(tableSize+at,tableSize+at+row),
            controls.subarray(at,at+2*row),controls.subarray(tableSize+at+row,tableSize+at+2*row)]));
        }
        await output.sync();
      } finally { await output.close(); }
    });
  } finally {await source.close();}
}
module.exports = { layout, preparedInkling };
