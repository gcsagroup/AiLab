import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const desktopRoot = dirname(fileURLToPath(import.meta.url));
const connectionFile = resolve(desktopRoot, '../../.artifacts/dev/control-connection.json');
const executeFile = promisify(execFile);
let pickerOpen = false;

class MediaResponseError extends Error {}
export async function readMediaContent(response: Response, maximum = 64 * 1024 * 1024) {
  const contentType = response.headers.get('content-type');
  if (!contentType || !['image/png', 'video/mp4', 'audio/wav'].includes(contentType)) throw new MediaResponseError('媒体类型不支持在应用内预览。');
  if (Number(response.headers.get('content-length') || 0) > maximum || !response.body) throw new MediaResponseError('媒体超过预览大小限制或没有可读取内容，请导出后查看。');
  const reader = response.body.getReader(); const chunks: Buffer[] = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) { await reader.cancel(); throw new MediaResponseError('媒体超过预览大小限制，请导出后查看。'); }
      chunks.push(Buffer.from(value));
    }
  } finally { reader.releaseLock(); }
  if (!size) throw new MediaResponseError('媒体产物为空，无法预览。');
  return { contentType, body: Buffer.concat(chunks, size) };
}

export default defineConfig({
  root: desktopRoot,
  plugins: [react(), {
    name: 'ailab-local-control-bridge',
    configureServer(server) {
      // 开发桥接只接受同源脚本请求，令牌不进入浏览器或源码。
      server.middlewares.use('/api/v1', async (req, res) => {
        const error = (status: number, message: string) => {
          res.statusCode = status;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.end(JSON.stringify({ error: { code: 'LOCAL_BRIDGE', message, details: {} } }));
        };
        const host = req.headers.host;
        const origin = req.headers.origin;
        if (!['127.0.0.1:1420', 'localhost:1420'].includes(host || '') ||
            req.headers['x-ailab-request'] !== '1' ||
            (origin && origin !== `http://${host}`) ||
            (req.headers['sec-fetch-site'] && req.headers['sec-fetch-site'] !== 'same-origin')) {
          return error(403, '仅允许当前本机工作台访问控制服务。');
        }
        const path = req.url || '/';
        const route = path.split('?')[0];
        if (!/^\/[a-zA-Z0-9/_?=&.%-]*$/.test(path) || path.includes('..') || route.includes('%') || /^\/(import|export)-grants/.test(route) || /^\/restores\/[^/]+\/activation\/?$/.test(route) || (route === '/settings' && req.method !== 'GET')) {
          return error(403, '此路径不允许通过开发桥接访问。');
        }
        if (!['GET', 'POST', 'PATCH', 'DELETE'].includes(req.method || '')) return error(405, '请求方法不支持。');
        try {
          const connection = JSON.parse(await readFile(connectionFile, 'utf8'));
          if (!Number.isInteger(connection.port) || connection.port < 1 || connection.port > 65535 || typeof connection.token !== 'string') {
            return error(503, '本机控制服务的连接信息无效。');
          }
          const chunks: Buffer[] = [];
          let size = 0;
          for await (const chunk of req) {
            size += chunk.length;
            if (size > 2 * 1024 * 1024) return error(413, '请求过大，请使用本机文件导入。');
            chunks.push(Buffer.from(chunk));
          }
          if (route === '/studio/pick-path') {
            if (req.method !== 'POST') return error(405, '请选择文件后重试。');
            const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
            if (!body || typeof body.directory !== 'boolean' || (body.gguf !== undefined && typeof body.gguf !== 'boolean') || Object.keys(body).some(k => !['directory', 'gguf'].includes(k))) return error(400, '文件选择参数无效。');
            if (pickerOpen) return error(409, '文件选择窗口已打开，请完成或取消当前选择。');
            pickerOpen = true;
            try {
              const python = process.env.AILAB_CONTROL_PYTHON || resolve(desktopRoot, process.platform === 'win32' ? '../../.venv/Scripts/python.exe' : '../../.venv/bin/python');
              const selected = await executeFile(python, [resolve(desktopRoot, '../../scripts/desktop/pick_studio_path.py'), body.directory ? 'directory' : body.gguf ? 'gguf' : 'file'], { windowsHide: true, timeout: 300000, maxBuffer: 16384 });
              res.setHeader('Content-Type', 'application/json; charset=utf-8');
              res.setHeader('Cache-Control', 'no-store');
              res.end(JSON.stringify(JSON.parse(selected.stdout.trim())));
            } catch { error(503, '无法打开系统文件窗口。请确认本机 Python 已安装 Tk，或使用桌面应用。'); }
            finally { pickerOpen = false; }
            return;
          }
          const headers: Record<string, string> = {
            Authorization: `Bearer ${connection.token}`, 'Content-Type': 'application/json',
          };
          if (typeof req.headers['idempotency-key'] === 'string') headers['Idempotency-Key'] = req.headers['idempotency-key'];
          const response = await fetch(`http://127.0.0.1:${connection.port}/api/v1${path}`, {
            method: req.method, headers,
            body: req.method === 'GET' ? undefined : Buffer.concat(chunks),
            signal: AbortSignal.timeout(120000), redirect: 'error',
          });
          if (req.method === 'GET' && /^\/artifacts\/artifact-[0-9a-f]{32}\/content$/.test(route) && response.ok) {
            const media = await readMediaContent(response);
            res.statusCode = response.status;
            res.setHeader('Content-Type', media.contentType);
            res.setHeader('Content-Length', media.body.length);
            res.setHeader('Cache-Control', 'no-store');
            res.setHeader('X-Content-Type-Options', 'nosniff');
            res.end(media.body);
            return;
          }
          res.statusCode = response.status;
          res.setHeader('Content-Type', 'application/json; charset=utf-8');
          res.setHeader('Cache-Control', 'no-store');
          res.end(Buffer.from(await response.arrayBuffer()));
        } catch (failure) {
          error(failure instanceof MediaResponseError ? 502 : 503, failure instanceof MediaResponseError ? failure.message : '本机控制服务尚未连接，请启动服务或在桌面应用中重启连接。');
        }
      });
    },
  }],
  server: { watch: { ignored: ['**/src-tauri/**'] }, host: '127.0.0.1', port: 1420, strictPort: true, cors: false, fs: { strict: true, allow: [desktopRoot, resolve(desktopRoot, '../../node_modules')], deny: ['**/.artifacts/**', '**/.git/**', '**/.env*', '**/*.private.*', '**/*.{crt,pem,key}'] } },
  build: { outDir: 'dist', emptyOutDir: true },
  test: { environment: 'jsdom', include: ['../../tests/frontend/**/*.{test,spec}.{ts,tsx}'], globals: true },
});
