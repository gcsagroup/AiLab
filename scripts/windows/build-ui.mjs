import { access, cp, mkdir, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const output = process.env.AILAB_WINDOWS_OUTPUT_DIR ? resolve(process.env.AILAB_WINDOWS_OUTPUT_DIR) : resolve(root, '../release/GCSA-AiLab-Windows-UI');
const project = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const electron = JSON.parse(await readFile(join(root, 'node_modules/electron/package.json'), 'utf8'));
function run(file, args, env = {}) {
  const result = spawnSync(process.execPath, [join(root, file), ...args], { cwd: root, stdio: 'inherit', env: { ...process.env, ...env } });
  if (result.status !== 0) throw new Error(`${file} failed (${result.status})`);
}
if (process.platform !== 'win32' || process.arch !== 'x64') throw new Error('This build targets Windows x64.');
for (const file of ['text/ailab-gguf.exe', 'text/llama.dll', 'text/mtmd.dll', 'diffusion/ailab-image.exe', 'diffusion/stable-diffusion.dll', 'diffusion/ffmpeg.exe', 'audio/audiocpp_cli.exe']) {
  try { await access(join(root, 'apps/windows-ui/runtime', file)); }
  catch { throw new Error(`Missing Windows inference runtime ${file}. Run python scripts/windows/prepare-gguf.py first; see scripts/windows/README-Windows.txt.`); }
}
let runtimeReady = false;
try {
  await access(join(root, 'node_modules/electron/dist/electron.exe'));
  runtimeReady = (await readFile(join(root, 'node_modules/electron/dist/version'), 'utf8')).trim().replace(/^v/, '') === electron.version;
} catch { /* A clean npm install may not include the Electron binary yet. */ }
if (!runtimeReady) run('node_modules/electron/install.js', []);
run('node_modules/typescript/bin/tsc', ['--noEmit', '-p', 'apps/desktop/tsconfig.json']);
run('node_modules/vite/bin/vite.js', ['build', '--config', 'apps/desktop/vite.config.ts', '--base', './', '--outDir', '../windows-ui/dist'], { VITE_UI_PREVIEW: 'true' });
await mkdir(output, { recursive: true });
const runtimeDir = join(root, 'node_modules/electron/dist');
async function differs(source, destination) {
  try {
    const [original, installed] = await Promise.all([readFile(source), readFile(destination)]);
    return !original.equals(installed);
  } catch (error) {
    if (error.code === 'ENOENT' || error.code === 'EISDIR') return true;
    throw error;
  }
}
for (const entry of await readdir(runtimeDir, {withFileTypes:true})) {
  const source = join(runtimeDir, entry.name);
  const destination = join(output, entry.name === 'electron.exe' ? 'AiLab-UI.exe' : entry.name);
  if (entry.isDirectory()) await cp(source, destination, {recursive:true, filter: async (src,dst) =>
    (await stat(src)).isDirectory() || differs(src,dst)});
  else if (await differs(source,destination)) await cp(source,destination);
}
const appDir = join(output, 'resources/app');
await mkdir(appDir, { recursive: true });
// Retire the previous packaged Python video worker when updating a portable build in place.
for (const obsolete of ['runtime/video', 'hf/svd-worker.py', 'hf/svd-config.json'])
  await rm(join(appDir, obsolete), { recursive:true, force:true });
await cp(join(root, 'apps/windows-ui'), appDir, { recursive: true });
const assetsDir = join(appDir, 'dist/assets');
const currentAssets = new Set(await readdir(join(root, 'apps/windows-ui/dist/assets')));
for (const entry of await readdir(assetsDir, {withFileTypes:true})) {
  if (entry.isFile() && /^(?:index|previewApi|windowsWorkbenchApi)-[\w-]+\.(?:js|css)$/.test(entry.name) && !currentAssets.has(entry.name))
    await rm(join(assetsDir, entry.name));
}
await cp(join(root, 'downloads/hf-language-repos.txt.gz'), join(appDir, 'hf-language-repos.txt.gz'));
await cp(join(root, 'apps/desktop/src-tauri/icons/icon.png'), join(appDir, 'icon.png'));
for (const file of ['smoke.cjs', 'smoke-model-download.cjs', 'smoke-gguf-trial.cjs']) await cp(join(root, 'scripts/windows', file), join(appDir, file));
await cp(join(root, 'scripts/windows/README-Windows.txt'), join(output, '使用说明.txt'));
const require = createRequire(join(root, 'package.json'));
const licenses = [];
for (const name of ['react', 'react-dom', '@tauri-apps/api', 'lucide-react', 'scheduler']) {
  const from = name === 'scheduler' ? createRequire(require.resolve('react-dom/package.json')) : require;
  const packageDir = dirname(from.resolve(`${name}/package.json`));
  for (const file of await readdir(packageDir)) {
    if (/^licen[cs]e/i.test(file)) licenses.push(`${name} / ${file}\n\n${await readFile(join(packageDir, file), 'utf8')}`);
  }
}
await writeFile(join(output, 'third-party-licenses.txt'), licenses.join('\n\n----------------------------------------\n\n'));
const manifest = { app: 'GCSA AI Lab Windows UI Preview', version: project.version, platform: 'win32-x64', electron: electron.version,
  builtAt: new Date().toISOString(), entry: 'AiLab-UI.exe', mode: 'local-gguf-workbench',
  sha256: createHash('sha256').update(await readFile(join(output, 'AiLab-UI.exe'))).digest('hex') };
await writeFile(join(output, 'build-info.json'), JSON.stringify(manifest, null, 2));
console.log(`\nWindows UI ready: ${join(output, 'AiLab-UI.exe')}`);
