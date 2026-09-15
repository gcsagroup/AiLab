/** CUA 界面验收的独立服务与合同夹具；不包含浏览器驱动，不执行模型。 */
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { randomUUID } from 'node:crypto';
import { createServer as createSocket } from 'node:net';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createViteServer } from 'vite';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const mode = process.argv[2] || 'serve';
const OUT = path.resolve(process.argv[3] || '.artifacts/ac23-responsive/cua-v1');
const fixtures = path.join(OUT, 'fixtures');
let connection;
async function request(method, route, body) {
  const response = await fetch(`http://127.0.0.1:${connection.port}/api/v1${route}`, { method, headers: { Authorization: `Bearer ${connection.token}`, 'Content-Type': 'application/json', 'Idempotency-Key': randomUUID() }, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json(); if (!response.ok) throw new Error(`${method} ${route}: ${JSON.stringify(result)}`); return result;
}
async function addFixtures() {
  const projectId = (await request('GET', '/projects')).items[0].id;
  const modelDir = path.join(fixtures, '界面验收专用模型夹具'); await fs.mkdir(modelDir);
  await fs.writeFile(path.join(modelDir, 'config.json'), JSON.stringify({ model_type: 'qwen2', hidden_size: 896, num_hidden_layers: 24 }));
  await fs.writeFile(path.join(modelDir, 'tokenizer_config.json'), '{}');
  let header = Buffer.from(JSON.stringify({ fixture_tensor: { dtype: 'F32', shape: [1], data_offsets: [0, 4] } })); header = Buffer.concat([header, Buffer.alloc((8 - header.length % 8) % 8, 32)]);
  const prefix = Buffer.alloc(8); prefix.writeBigUInt64LE(BigInt(header.length)); const weight = Buffer.alloc(4); weight.writeFloatLE(1);
  await fs.writeFile(path.join(modelDir, 'model.safetensors'), Buffer.concat([prefix, header, weight]));
  const modelName = '界面合同夹具·不是可运行模型·' + '中文模型名称超长显示与窄屏换行验证'.repeat(4);
  const plan = await request('POST', '/models/import-plans', { project_id: projectId, path: modelDir, name: modelName });
  const model = await request('POST', '/models/imports', { plan_id: plan.id || plan.plan_id, manifest_digest: plan.manifest_digest });
  const datasetPath = path.join(fixtures, '界面验收专用数据.jsonl');
  await fs.writeFile(datasetPath, JSON.stringify({ messages: [{ role: 'user', content: '界面合同夹具输入' }, { role: 'assistant', content: '界面合同夹具回答，不用于训练质量结论。' }] }) + '\n');
  const dataPlan = await request('POST', '/datasets/import-plans', { project_id: projectId, path: datasetPath, name: '界面合同夹具·' + '长中文数据集名称与记录显示验证'.repeat(4), schema: 'sft' });
  const dataset = await request('POST', '/datasets/imports', { plan_id: dataPlan.id || dataPlan.plan_id, manifest_digest: dataPlan.manifest_digest });
  const task = await request('POST', '/tasks', { project_id: projectId, kind: 'text', operation: 'generate', name: '界面验收夹具·' + '这是长中文普通任务名称用于验证窄屏标题按钮布局'.repeat(3) });
  const saved = await request('PATCH', `/tasks/${task.id}/draft`, { expected_revision: task.draft_revision, draft: { ...task.draft, model_id: model.id, input: { prompt: '界面夹具正文：' + '长中文段落与普通任务输入会保留。'.repeat(6) }, runtime: { ...task.draft.runtime, stop: [' 完成 ', 'END'], context_limit: 2048, stream: false } } });
  await fs.writeFile(path.join(OUT, 'fixture-resources.json'), JSON.stringify({ model, dataset, long_task: saved, model_path: modelDir, model_import_name: modelName }, null, 2));
}

if (mode === 'serve') {
  await fs.mkdir(OUT); await fs.mkdir(fixtures); await fs.mkdir(path.join(OUT, 'screenshots'));
  const socket = createSocket(); socket.listen(0, '127.0.0.1'); await once(socket, 'listening'); const port = socket.address().port; await new Promise(resolve => socket.close(resolve));
  const control = spawn(path.join(ROOT, 'services/control/.venv/bin/python'), ['-B', '-m', 'ailab_control', '--data-dir', path.join(OUT, 'control-data'), '--import-root', fixtures], { cwd: ROOT, env: { ...process.env, PYTHONPATH: path.join(ROOT, 'services/control') }, stdio: ['ignore', 'pipe', 'pipe'] });
  let errors = ''; control.stderr.on('data', block => { errors += block.toString(); });
  connection = await new Promise((resolve, reject) => { let data = ''; const timer = setTimeout(() => reject(new Error('隔离控制服务未按时握手')), 20000); control.once('error', reject); control.stdout.on('data', block => { data += block.toString(); if (data.includes('\n')) { clearTimeout(timer); resolve(JSON.parse(data.split('\n')[0])); } }); });
  const connectionFile = path.join(OUT, 'connection.private.json'); await fs.writeFile(connectionFile, JSON.stringify(connection), { mode: 0o600 });
  let config = await fs.readFile(path.join(ROOT, 'apps/desktop/vite.config.ts'), 'utf8');
  config = config.replace('const desktopRoot = dirname(fileURLToPath(import.meta.url));', `const desktopRoot = ${JSON.stringify(path.join(ROOT, 'apps/desktop'))};`).replace("const connectionFile = resolve(desktopRoot, '../../.artifacts/dev/control-connection.json');", `const connectionFile = ${JSON.stringify(connectionFile)};`).replaceAll('1420', String(port));
  const configFile = path.join(OUT, 'app.vite.config.ts'); await fs.writeFile(configFile, config);
  const vite = await createViteServer({ configFile }); await vite.listen();
  const state = { url: `http://127.0.0.1:${port}`, control_pid: control.pid, fixture_server_pid: process.pid, scope: '正式 App 源码，独立空 SQLite；仅界面合同夹具，无 GPU 执行' };
  await fs.writeFile(path.join(OUT, 'server.json'), JSON.stringify(state, null, 2)); console.log(JSON.stringify(state));
  let closing = false;
  async function close() { if (closing) return; closing = true; await vite.close(); control.kill('SIGTERM'); await once(control, 'exit'); await fs.writeFile(path.join(OUT, 'control.stderr.log'), errors); process.exit(0); }
  process.on('SIGTERM', close); process.on('SIGINT', close);
} else {
  connection = JSON.parse(await fs.readFile(path.join(OUT, 'connection.private.json'), 'utf8'));
  if (mode === 'seed') { await addFixtures(); console.log('已导入长中文名称界面合同夹具；没有执行模型。'); }
  else if (mode === 'verify') {
    const projects = await request('GET', '/projects');
    const project = projects.items[0];
    const tasks = await request('GET', `/tasks?project_id=${project.id}`);
    const records = await Promise.all(tasks.items.map(task => request('GET', `/tasks/${task.id}`)));
    const attempts = await request('GET', `/attempts?project_id=${project.id}`);
    const result = { projects: projects.items, tasks: records, attempt_count: attempts.items.length };
    await fs.writeFile(path.join(OUT, 'storage-readback.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } else throw new Error('模式必须是 serve、seed 或 verify');
}
