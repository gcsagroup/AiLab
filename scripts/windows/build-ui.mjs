import { access, cp, mkdir, readFile, readdir, rename, writeFile } from 'node:fs/promises';
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
let runtimeReady = false;
try {
  await access(join(root, 'node_modules/electron/dist/electron.exe'));
  runtimeReady = (await readFile(join(root, 'node_modules/electron/dist/version'), 'utf8')).trim().replace(/^v/, '') === electron.version;
} catch { /* A clean npm install may not include the Electron binary yet. */ }
if (!runtimeReady) run('node_modules/electron/install.js', []);
run('node_modules/typescript/bin/tsc', ['--noEmit', '-p', 'apps/desktop/tsconfig.json']);
run('node_modules/vite/bin/vite.js', ['build', '--config', 'apps/desktop/vite.config.ts', '--base', './', '--outDir', '../windows-ui/dist'], { VITE_UI_PREVIEW: 'true' });
await mkdir(output, { recursive: true });
await cp(join(root, 'node_modules/electron/dist'), output, { recursive: true });
await rename(join(output, 'electron.exe'), join(output, 'AiLab-UI.exe'));
const appDir = join(output, 'resources/app');
await mkdir(appDir, { recursive: true });
await cp(join(root, 'apps/windows-ui'), appDir, { recursive: true });
await cp(join(root, 'apps/desktop/src-tauri/icons/icon.png'), join(appDir, 'icon.png'));
await cp(join(root, 'scripts/windows/smoke.cjs'), join(appDir, 'smoke.cjs'));
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
  builtAt: new Date().toISOString(), entry: 'AiLab-UI.exe', mode: 'offline-ui-preview',
  sha256: createHash('sha256').update(await readFile(join(output, 'AiLab-UI.exe'))).digest('hex') };
await writeFile(join(output, 'build-info.json'), JSON.stringify(manifest, null, 2));
console.log(`\nWindows UI ready: ${join(output, 'AiLab-UI.exe')}`);
