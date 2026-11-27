const { app, BrowserWindow, Menu, protocol, net, session, ipcMain, dialog } = require('electron');
const { dirname, join, resolve, sep } = require('node:path');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');

protocol.registerSchemesAsPrivileged([{ scheme: 'ailab', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);
const smokePath = process.argv.find(arg => arg.startsWith('--smoke-result='))?.slice('--smoke-result='.length);
// Preview data is separate from any existing full AiLab installation.
app.setPath('userData', smokePath ? join(dirname(smokePath), 'smoke-profile') : join(app.getPath('appData'), 'GCSA-AiLab-UI-Preview'));
process.env.AILAB_RUNTIME_DIR = join(app.getPath('userData'), 'runtime');
app.setAppUserModelId('org.gcsa.ailab.ui-preview');
let window;
let models;
let runtimeInstaller;
let closing = false;
if (!app.requestSingleInstanceLock()) app.exit(0);
app.on('second-instance', () => {
  if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
});
const failures = [];
app.whenReady().then(async () => {
  const { OfficialModels } = require('./hf/official.cjs');
  const { RuntimeInstaller } = require('./hf/runtime-installer.cjs');
  runtimeInstaller = new RuntimeInstaller(process.env.AILAB_RUNTIME_DIR);
  models = new OfficialModels({
    dataDir: join(app.getPath('userData'), 'official-models'),
    catalogPath: join(__dirname, 'hf-language-repos.txt.gz'),
    ensureRuntime: id => runtimeInstaller.ensure(id),
  });
  ipcMain.handle('ailab:runtime', async (event, action, component) => {
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame || event.senderFrame.url !== 'ailab://ui/') throw new Error('无效的运行库请求。');
    if (action === 'status') return runtimeInstaller.status();
    if (action === 'cancel') { runtimeInstaller.cancel(); return runtimeInstaller.status(); }
    if (action !== 'start') throw new Error('未知的运行库操作。');
    runtimeInstaller.start(component);
    return runtimeInstaller.status();
  });
  ipcMain.handle('ailab:official-models', async (event, action, request) => {
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame || event.senderFrame.url !== 'ailab://ui/' || action !== 'workbench') throw new Error('无效的工作台请求。');
    try {
      if (!request || !['GET', 'POST', 'PATCH', 'DELETE'].includes(request.method) || typeof request.path !== 'string' || !request.path.startsWith('/') || JSON.stringify(request).length > 256000) throw new Error('工作台请求格式无效。');
      if (request.method === 'POST' && request.path === '/environment/export') {
        const data = await models.trials.environment.export(request.body?.id, async name => {
          // The isolated UI smoke run supplies a destination in its own temporary profile.
          if (smokePath) return join(app.getPath('userData'), 'environment-smoke.json');
          const result = await dialog.showSaveDialog(window, {
            title: '保存环境诊断摘要', defaultPath: join(app.getPath('documents'), name),
            filters: [{ name: 'JSON 诊断摘要', extensions: ['json'] }],
          });
          return result.canceled ? null : result.filePath;
        });
        return { ok: true, data: { handled: true, data } };
      }
      return {ok: true, data: await models.request(request)};
    } catch (error) { return {ok: false, error: {code: error.code || 'MODEL_SERVICE', message: error.message || String(error)}}; }
  });
  const content = resolve(__dirname, 'dist');
  protocol.handle('ailab', request => {
    const url = new URL(request.url);
    if (url.hostname !== 'ui' || request.method !== 'GET') return new Response('Not found', { status: 404 });
    let file;
    try { file = resolve(content, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname)); }
    catch { return new Response('Invalid path', { status: 400 }); }
    if (!file.startsWith(content + sep)) return new Response('Forbidden', { status: 403 });
    return net.fetch(pathToFileURL(file).toString()).then(response => {
      const headers = new Headers(response.headers);
      headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'");
      return new Response(response.body, { status: response.status, headers });
    });
  });
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    const bundledAsset = details.url.startsWith(pathToFileURL(content + sep).toString());
    callback({ cancel: !bundledAsset && !details.url.startsWith('ailab://ui/') && !/^(data|blob|devtools):/.test(details.url) });
  });
  Menu.setApplicationMenu(null);
  window = new BrowserWindow({
    width: 1440, height: 960, minWidth: 480, minHeight: 640,
    title: 'GCSA AI Lab · Windows UI 预览版', icon: join(__dirname, 'icon.png'),
    backgroundColor: '#f7f8fa', show: false,
    webPreferences: { preload: join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true, spellcheck: false },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event, url) => { if (!url.startsWith('ailab://ui/')) event.preventDefault(); });
  window.webContents.on('page-title-updated', event => event.preventDefault());
  window.webContents.on('console-message', (_event, details) => { if (details.level === 'error') failures.push(details.message); });
  window.webContents.on('render-process-gone', (_event, detail) => failures.push(`Renderer: ${detail.reason}`));
  window.once('ready-to-show', () => { if (!smokePath) window.show(); });
  await window.loadURL('ailab://ui/');
  if (!smokePath) { window.show(); window.focus(); }
  if (smokePath) {
    try {
      const modelSmoke = process.argv.includes('--smoke-model-download');
      const assistantSmoke = process.argv.includes('--smoke-ai-assistance');
      const trialKind = process.argv.find(arg=>/^--smoke-gguf-trial=(text|image|video|audio)$/.test(arg))?.split('=')[1];
      const family=process.argv.find(a=>/^--smoke-family=(Qwen3\.5|Gemma 4|MiniMax-H3-Image|MiniMax-H3)$/i.test(a))?.slice('--smoke-family='.length);
      const deviceId = process.argv.find(arg => /^--smoke-device=(cpu|(?:Vulkan|CUDA)\d+)$/.test(arg))?.split('=')[1];
      const stepCount = Number(process.argv.find(arg => /^--smoke-steps=(?:[1-9]\d?|100)$/.test(arg))?.split('=')[1]) || null;
      const script = fs.readFileSync(join(__dirname, trialKind ? 'smoke-gguf-trial.cjs' : modelSmoke ? 'smoke-model-download.cjs' : assistantSmoke ? 'smoke-ai-assistance.cjs' : 'smoke.cjs'), 'utf8').trim();
      const result = await window.webContents.executeJavaScript(trialKind ? '(' + script.replace(/;$/, '') + ')(' + JSON.stringify(trialKind) + ','+JSON.stringify(family||null)+','+JSON.stringify(stepCount)+','+JSON.stringify(deviceId || null)+')' : modelSmoke ? script + '(' + process.argv.includes('--smoke-small-gguf') + ')' : script);
      if (trialKind && (result?.passed !== true || result.kind !== trialKind)) throw Error('试用验收未返回该类别的完整结果。');
      fs.writeFileSync(smokePath, JSON.stringify({ ...result, failures }, null, 2));
      app.exit(failures.length ? 1 : 0);
    } catch (error) {
      fs.writeFileSync(smokePath, JSON.stringify({ error: String(error), failures }, null, 2)); app.exit(1);
    }
  }
}).catch(error => {
  console.error(error);
  if (smokePath) fs.writeFileSync(smokePath, JSON.stringify({ error: String(error), failures }, null, 2));
  app.exit(1);
});
app.on('before-quit', event => {
  if (!models || closing) return;
  event.preventDefault();
  closing = true;
  Promise.allSettled([runtimeInstaller?.close(), models.close()]).finally(() => app.quit());
});
app.on('window-all-closed', () => app.quit());
