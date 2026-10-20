const { app, BrowserWindow, Menu, protocol, net, session } = require('electron');
const { dirname, join, resolve, sep } = require('node:path');
const { pathToFileURL } = require('node:url');
const fs = require('node:fs');

protocol.registerSchemesAsPrivileged([{ scheme: 'ailab', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);
const smokePath = process.argv.find(arg => arg.startsWith('--smoke-result='))?.slice('--smoke-result='.length);
// Preview data is separate from any existing full AiLab installation.
app.setPath('userData', smokePath ? join(dirname(smokePath), 'smoke-profile') : join(app.getPath('appData'), 'GCSA-AiLab-UI-Preview'));
app.setAppUserModelId('org.gcsa.ailab.ui-preview');
let window;
if (!app.requestSingleInstanceLock()) app.exit(0);
app.on('second-instance', () => {
  if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); }
});
const failures = [];
app.whenReady().then(async () => {
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
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, spellcheck: false },
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
      const result = await window.webContents.executeJavaScript(fs.readFileSync(join(__dirname, 'smoke.cjs'), 'utf8'));
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
app.on('window-all-closed', () => app.quit());
