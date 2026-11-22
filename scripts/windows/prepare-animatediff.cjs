// Convert the publisher's AnimateDiff v3 motion weights once, using the same pinned native SDK as inference.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { bins, invoke } = require('../../apps/windows-ui/hf/trial-worker.cjs');
const { metadata } = require('../../apps/windows-ui/hf/gguf-metadata.cjs');

async function main() {
  const [source, output] = process.argv.slice(2);
  if (!source || !output || !/\.gguf$/i.test(output))
    throw Error('用法：node scripts/windows/prepare-animatediff.cjs v3_sd15_mm.safetensors motion.gguf');
  const checksum = createHash('sha256');
  for await (const chunk of fs.createReadStream(source)) checksum.update(chunk);
  if (checksum.digest('hex') !== '73c4b969c778b2ea96a172c3b432572b654e91865f9f224a709dbda13e730043')
    throw Error('输入与 guoyww/animatediff 发布的 v3_sd15_mm.safetensors 摘要不符。');
  const target = path.resolve(output);
  const parent = path.dirname(target);
  await fs.promises.mkdir(parent, { recursive: true });
  const stage = await fs.promises.mkdtemp(path.join(parent, '.animatediff-'));
  const converted = path.join(stage, 'motion.gguf');
  try {
    const input = path.join(stage, 'motion.safetensors');
    try {
      await fs.promises.link(path.resolve(source), input);
    } catch (error) {
      if (error.code !== 'EXDEV') throw error;
      await fs.promises.copyFile(source, input);
    }
    await invoke(
      path.join(path.dirname(bins.video), 'sd-cli.exe'),
      ['-M', 'convert', '-m', 'motion.safetensors', '--type', 'f16', '-o', 'motion.gguf'],
      { cwd: stage },
    );
    if (!metadata(converted).motion) throw Error('转换结果缺少 AnimateDiff 的运动张量。');
    // Atomically publish without overwriting an existing model file.
    await fs.promises.link(converted, target);
    console.log(target);
  } finally {
    await fs.promises.rm(stage, { recursive: true, force: true });
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
