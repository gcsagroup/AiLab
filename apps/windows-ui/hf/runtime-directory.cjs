'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

async function findRuntime(directory) {
  if (!directory || !path.isAbsolute(directory)) return;
  for (const root of [directory, path.join(directory, 'resources', 'app', 'runtime')]) {
    for (const file of ['text/ailab-gguf.exe', 'diffusion/ailab-image.exe', 'audio/audiocpp_cli.exe']) {
      const stat = await fs.stat(path.join(root, file)).catch(() => null);
      if (stat?.isFile() && stat.size > 0) return fs.realpath(root);
    }
  }
}

async function runtimeDirectory(profile, bundled, override) {
  const file = path.join(profile, 'runtime-directory.json');
  const managed = path.join(profile, 'runtime');
  let selected, warning;
  try {
    selected = JSON.parse(await fs.readFile(file, 'utf8')).directory;
    if (typeof selected !== 'string' || !path.isAbsolute(selected)) throw Error();
  } catch (error) {
    if (error.code !== 'ENOENT') warning = '无法读取保存的运行库目录。请重新选择。';
    selected = undefined;
  }
  const automatic = await findRuntime(override) || await findRuntime(bundled) || managed;
  const existing = await findRuntime(selected);
  if (selected && !existing) warning = '上次选择的运行库目录已不可用：' + selected;
  const root = existing || automatic;
  let nextRoot = root;
  return {
    root,
    info: () => ({ root, selected: !!selected, nextRoot, directoryWarning: warning }),
    async select(directory) {
      const next = directory ? await findRuntime(directory) : automatic;
      if (!next) throw Error('请选择包含 AiLab 执行器的 runtime 目录，或包含该运行库的 AiLab 程序目录。');
      if (directory) {
        await fs.mkdir(profile, { recursive: true });
        const temp = file + '.' + randomUUID();
        try {
          await fs.writeFile(temp, JSON.stringify({ directory: next }), { flag: 'wx' });
          await fs.rename(temp, file);
        } finally { await fs.rm(temp, { force: true }); }
      } else {
        await fs.rm(file, { force: true });
      }
      selected = directory ? next : undefined;
      nextRoot = next;
      warning = undefined;
    },
  };
}

module.exports = { runtimeDirectory };
