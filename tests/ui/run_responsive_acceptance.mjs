/** 正式 App 的隔离 Chrome 响应式与键盘验收；只使用本机合同夹具，不运行模型。 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { once } from 'node:events';
import { createHash, randomUUID } from 'node:crypto';
import { createServer as createSocket } from 'node:net';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer as createViteServer } from 'vite';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(import.meta.url);
const playwrightPath = process.env.AILAB_PLAYWRIGHT_MODULE || '/Users/lazy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const { chromium } = require(playwrightPath);
const outputIndex = process.argv.indexOf('--output');
const OUT = path.resolve(outputIndex >= 0 ? process.argv[outputIndex + 1] : path.join(ROOT, '.artifacts/ac23-responsive', new Date().toISOString().replaceAll(':', '-')));
const executable = process.env.AILAB_CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.mkdir(OUT); // 每次验收新建目录，保留失败与历史截图。
await fs.mkdir(path.join(OUT, 'screenshots'));
const fixtures = path.join(OUT, 'fixtures'); await fs.mkdir(fixtures);
const report = { schema_version: 'ailab-responsive-acceptance-v1', scope: '正式 React App、真实回环 HTTP 与 SQLite；模型和数据为界面合同夹具，未执行 GPU 或模型生成。', started_at: new Date().toISOString(), output: OUT, checks: [], captures: [], keyboard: [], network: [], blocked_requests: [], browser_errors: [], sources: {}, fixture_resources: {}, success: false };
const sourcePaths = ['apps/desktop/src/App.tsx', 'apps/desktop/src/Workbench.tsx', 'apps/desktop/src/GenerationFields.tsx', 'apps/desktop/src/RuntimePresets.tsx', 'apps/desktop/src/ui.tsx', 'apps/desktop/src/styles.css'];
for (const file of sourcePaths) report.sources[file] = createHash('sha256').update(await fs.readFile(path.join(ROOT, file))).digest('hex');
const check = (name, passed, details = {}) => { report.checks.push({ name, passed: Boolean(passed), ...details }); };
let control, vite, browser, connection;
let controlErrors = '';
async function freePort() { const socket = createSocket(); socket.listen(0, '127.0.0.1'); await once(socket, 'listening'); const port = socket.address().port; await new Promise(resolve => socket.close(resolve)); return port; }
async function request(method, route, body) {
  const response = await fetch(`http://127.0.0.1:${connection.port}/api/v1${route}`, { method, headers: { Authorization: `Bearer ${connection.token}`, 'Content-Type': 'application/json', 'Idempotency-Key': randomUUID() }, body: body === undefined ? undefined : JSON.stringify(body) });
  const result = await response.json(); if (!response.ok) throw new Error(`${method} ${route}: ${JSON.stringify(result)}`); return result;
}
async function active(page) { return page.evaluate(() => { const element = document.activeElement; const style = getComputedStyle(element); const bounds = element.getBoundingClientRect(); return { tag: element.tagName, label: element.getAttribute('aria-label') || (element.labels?.[0]?.textContent || element.textContent || '').trim().slice(0, 100), focus_visible: element.matches(':focus-visible'), outline_style: style.outlineStyle, outline_width: style.outlineWidth, bounds: { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height } }; }); }
async function tabTo(page, locator, name, maximum = 120) {
  await locator.waitFor({ state: 'visible' });
  for (let steps = 0; steps <= maximum; steps++) {
    if (await locator.evaluate(element => element === document.activeElement)) { const focus = await active(page); report.keyboard.push({ target: name, tab_count: steps, ...focus }); check(`键盘焦点可见：${name}`, focus.focus_visible && focus.outline_style !== 'none' && Number.parseFloat(focus.outline_width) >= 2); return; }
    await page.keyboard.press('Tab');
  }
  throw new Error(`Tab 无法到达：${name}`);
}
async function layout(page, scenario) {
  return page.evaluate(name => {
    const visible = element => { const box = element.getBoundingClientRect(); const style = getComputedStyle(element); return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'; };
    const width = window.innerWidth;
    const overflow = [...document.querySelectorAll('body *')].filter(visible).map(element => { const box = element.getBoundingClientRect(); return { element, box }; }).filter(({ box }) => box.left < -1 || box.right > width + 1).map(({ element, box }) => ({ tag: element.tagName, class: typeof element.className === 'string' ? element.className : '', text: (element.textContent || '').trim().slice(0, 80), left: box.left, right: box.right })).slice(0, 20);
    const dialogs = [...document.querySelectorAll('dialog[open]')].map(element => { const box = element.getBoundingClientRect(); return { title: element.getAttribute('aria-label'), width: element.clientWidth, scroll_width: element.scrollWidth, x: box.x, y: box.y, right: box.right, bottom: box.bottom }; });
    return { scenario: name, width, height: window.innerHeight, document_width: document.documentElement.scrollWidth, body_width: document.body.scrollWidth, dark: matchMedia('(prefers-color-scheme: dark)').matches, background: getComputedStyle(document.body).backgroundColor, root_background: getComputedStyle(document.documentElement).backgroundColor, overflow, dialogs };
  }, scenario);
}
async function capture(page, name, fullPage = true) {
  await page.evaluate(() => document.fonts.ready);
  const measured = await layout(page, name);
  const screenshot = path.join('screenshots', `${name}.png`); await page.screenshot({ path: path.join(OUT, screenshot), fullPage, animations: 'disabled' });
  check(`视口无横向溢出：${name}`, measured.document_width <= measured.width + 1 && measured.body_width <= measured.width + 1 && measured.overflow.length === 0, measured);
  for (const dialog of measured.dialogs) check(`弹窗在视口内且无横向溢出：${name}`, dialog.x >= 0 && dialog.y >= 0 && dialog.right <= measured.width + 1 && dialog.bottom <= measured.height + 1 && dialog.scroll_width <= dialog.width + 1, dialog);
  report.captures.push({ ...measured, screenshot }); return measured;
}
async function newPage(width, scheme) {
  const context = await browser.newContext({ viewport: { width, height: width <= 360 ? 800 : 900 }, deviceScaleFactor: 1, colorScheme: scheme, locale: 'zh-CN' });
  await context.route('**/*', route => { const url = new URL(route.request().url()); if (url.origin === report.url) return route.continue(); report.blocked_requests.push({ url: `${url.origin}${url.pathname}`, method: route.request().method() }); return route.abort(); });
  const page = await context.newPage();
  page.on('pageerror', error => report.browser_errors.push({ type: 'pageerror', message: error.message }));
  page.on('console', message => { if (message.type() === 'error') report.browser_errors.push({ type: 'console', message: message.text() }); });
  page.on('request', req => { if (new URL(req.url()).pathname.startsWith('/api/v1')) report.network.push({ method: req.method(), path: new URL(req.url()).pathname }); });
  return { context, page };
}
async function keyboardFlow() {
  const { context, page } = await newPage(360, 'light');
  try {
    await page.goto(report.url); await page.getByRole('heading', { name: '建立你的第一个项目' }).waitFor();
    await capture(page, 'keyboard-01-empty-project');
    const emptySettingsTrigger = page.getByRole('button', { name: '设备与环境', exact: true });
    const emptySettingsVisible = await emptySettingsTrigger.isVisible();
    check('空库全局设备与环境入口可见', emptySettingsVisible); assert.ok(emptySettingsVisible, '空库全局设备与环境入口不可见'); // 先保留失败画面，不让隐藏入口进入默认30秒等待。
    await tabTo(page, emptySettingsTrigger, '空库全局设备与环境'); await page.keyboard.press('Enter');
    const emptySettings = page.getByRole('dialog', { name: '设备与环境' }); await emptySettings.waitFor();
    await capture(page, 'keyboard-01a-empty-settings-dialog', false); await page.keyboard.press('Escape'); await emptySettings.waitFor({ state: 'hidden' });
    check('空库全局设备与环境 Esc 关闭并归还焦点', await emptySettingsTrigger.evaluate(element => element === document.activeElement));
    await tabTo(page, page.getByRole('main').getByRole('button', { name: '新建项目', exact: true }), '空库新建项目'); await page.keyboard.press('Enter');
    const dialog = page.getByRole('dialog', { name: '新建项目' }); await dialog.waitFor();
    const projectName = '界面验收夹具·' + '普通草稿与长中文名称显示验证'.repeat(4);
    await tabTo(page, page.getByLabel('项目名称'), '填写长中文项目名'); await page.keyboard.insertText(projectName);
    await capture(page, 'keyboard-02-project-dialog', false);
    await tabTo(page, dialog.getByRole('button', { name: '创建项目', exact: true }), '确认创建项目'); await page.keyboard.press('Enter'); await dialog.waitFor({ state: 'hidden' });
    await tabTo(page, page.getByRole('button', { name: '直接试用', exact: true }), '创建普通试用草稿'); await page.keyboard.press('Enter');
    const prompt = '界面与合同验收专用：使用键盘输入并保存普通草稿。这里不执行模型，也不把夹具当成真实生成能力。';
    await tabTo(page, page.getByLabel('输入内容'), '填写普通草稿'); await page.keyboard.insertText(prompt);
    await tabTo(page, page.getByLabel('上下文总预算（词元）'), '修改上下文预算'); await page.keyboard.press('ControlOrMeta+A'); await page.keyboard.insertText('2048');
    await tabTo(page, page.getByLabel('停止序列'), '逐行停止序列'); await page.keyboard.insertText(' 完成 '); await page.keyboard.press('Enter'); await page.keyboard.insertText('END'); await page.keyboard.press('Enter');
    check('真实键盘 Enter 保留停止词尾部空行', await page.getByLabel('停止序列').inputValue() === ' 完成 \nEND\n');
    await tabTo(page, page.getByLabel('流式显示输出'), '关闭流式显示'); await page.keyboard.press('Space');
    await tabTo(page, page.getByRole('button', { name: '保存草稿', exact: true }), '保存普通草稿'); await capture(page, 'keyboard-03-save-focus', false); await page.keyboard.press('Enter');
    await page.getByRole('button', { name: '草稿已保存', exact: true }).waitFor();
    const projects = await request('GET', '/projects'); assert.equal(projects.items.length, 1);
    const tasks = await request('GET', `/tasks?project_id=${projects.items[0].id}`); assert.equal(tasks.items.length, 1);
    const task = await request('GET', `/tasks/${tasks.items[0].id}`); const attempts = await request('GET', `/attempts?project_id=${projects.items[0].id}`);
    assert.equal(task.draft.input.prompt, prompt); assert.deepEqual(task.draft.runtime.stop, [' 完成 ', 'END']); assert.equal(task.draft.runtime.stream, false); assert.equal(task.draft.runtime.context_limit, 2048); assert.equal(attempts.items.length, 0);
    check('空项目经纯键盘创建普通草稿并真实保存', true, { project_id: projects.items[0].id, task_id: task.id, draft_revision: task.draft_revision, attempt_count: attempts.items.length, prompt, runtime: task.draft.runtime, keyboard_only: true });
    await capture(page, 'keyboard-04-persisted-draft'); report.fixture_resources.project = projects.items[0]; report.fixture_resources.keyboard_task = task;
  } finally { await context.close(); }
}
async function addFixtures() {
  const projectId = report.fixture_resources.project.id;
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
  report.fixture_resources = { ...report.fixture_resources, model, dataset, long_task: saved, model_path: modelDir, model_import_name: modelName };
}
async function dialogKeyboardCheck(page, trigger, name) {
  await trigger.click(); const dialog = page.getByRole('dialog', { name }); await dialog.waitFor();
  let contained = true; const observed = [];
  for (let index = 0; index < 24; index++) { await page.keyboard.press('Tab'); contained &&= await dialog.evaluate(element => element.contains(document.activeElement)); observed.push(await active(page)); }
  check(`弹窗 Tab 焦点留在弹窗：${name}:${page.viewportSize().width}`, contained, { observed });
  return dialog;
}
async function matrix() {
  for (const width of [1024, 736, 360, 320]) for (const scheme of ['light', 'dark']) {
    const { context, page } = await newPage(width, scheme); const prefix = `${width}-${scheme}`;
    try {
      await page.goto(report.url); await page.getByRole('heading', { name: '模型训练与运行', exact: true }).waitFor();
      await page.getByRole('button', { name: new RegExp(report.fixture_resources.long_task.name) }).waitFor();
      const home = await capture(page, `${prefix}-home`); check(`真实主题与视口：${prefix}`, home.width === width && home.dark === (scheme === 'dark'), { root_background: home.root_background });
      check(`任务队列按钮有可访问名称：${prefix}`, await page.getByRole('button', { name: '任务队列', exact: true }).count() === 1);
      const settingsTrigger = page.getByRole('button', { name: '2 · 检查本机环境', exact: true });
      const settings = await dialogKeyboardCheck(page, settingsTrigger, '设备与环境'); await capture(page, `${prefix}-settings-dialog`, false); await page.keyboard.press('Escape'); await settings.waitFor({ state: 'hidden' });
      check(`Esc 关闭并归还焦点：${prefix}`, await settingsTrigger.evaluate(element => element === document.activeElement));
      await page.getByRole('button', { name: new RegExp(report.fixture_resources.long_task.name) }).click(); await page.getByLabel('输入内容').waitFor();
      await capture(page, `${prefix}-workbench`);
      await page.getByLabel('运行预设').selectOption('low_memory_v2');
      const preset = await dialogKeyboardCheck(page, page.getByRole('button', { name: '预览预设差异', exact: true }), '应用低内存预设'); await capture(page, `${prefix}-preset-dialog`, false); await page.keyboard.press('Escape'); await preset.waitFor({ state: 'hidden' });
      await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '模型库', exact: true }).click(); await page.getByRole('heading', { name: report.fixture_resources.model.name, exact: true }).waitFor(); await capture(page, `${prefix}-models`);
      const modelSettingsTrigger = page.getByRole('button', { name: '设备与环境', exact: true });
      const modelSettingsVisible = await modelSettingsTrigger.isVisible();
      check(`模型库全局设备与环境入口可见：${prefix}`, modelSettingsVisible); assert.ok(modelSettingsVisible, `模型库全局设备与环境入口不可见：${prefix}`);
      const modelSettings = await dialogKeyboardCheck(page, modelSettingsTrigger, '设备与环境'); await capture(page, `${prefix}-models-settings-dialog`, false); await page.keyboard.press('Escape'); await modelSettings.waitFor({ state: 'hidden' });
      check(`模型库全局设备与环境 Esc 关闭并归还焦点：${prefix}`, await modelSettingsTrigger.evaluate(element => element === document.activeElement));
      await page.getByRole('button', { name: '导入模型', exact: true }).click(); const imported = page.getByRole('dialog', { name: '导入本机模型' }); await imported.waitFor();
      await page.getByLabel('名称（可选）').fill(report.fixture_resources.model_import_name); await page.getByLabel('模型文件路径').fill(report.fixture_resources.model_path); await imported.getByRole('button', { name: '检查模型', exact: true }).click(); await page.getByLabel('导入检查结果').waitFor(); await capture(page, `${prefix}-import-dialog`, false); await page.keyboard.press('Escape'); await imported.waitFor({ state: 'hidden' });
      await page.getByRole('navigation', { name: '主导航' }).getByRole('button', { name: '数据集市场', exact: true }).click(); await page.getByRole('heading', { name: report.fixture_resources.dataset.name, exact: true }).waitFor(); await capture(page, `${prefix}-datasets`);
      console.log(`${prefix} 真实渲染、弹窗与键盘焦点检查完成`);
    } finally { await context.close(); }
  }
}
try {
  const port = await freePort(); report.url = `http://127.0.0.1:${port}`;
  control = spawn(path.join(ROOT, 'services/control/.venv/bin/python'), ['-B', '-m', 'ailab_control', '--data-dir', path.join(OUT, 'control-data'), '--import-root', fixtures], { cwd: ROOT, env: { ...process.env, PYTHONPATH: path.join(ROOT, 'services/control') }, stdio: ['ignore', 'pipe', 'pipe'] });
  control.stderr.on('data', block => { controlErrors += block.toString(); });
  connection = await new Promise((resolve, reject) => { let text = ''; const timer = setTimeout(() => reject(new Error('隔离控制服务未按时握手')), 20000); control.once('error', error => { clearTimeout(timer); reject(error); }); control.stdout.on('data', block => { text += block.toString(); if (text.includes('\n')) { clearTimeout(timer); try { resolve(JSON.parse(text.split('\n')[0])); } catch (error) { reject(error); } } }); });
  const connectionFile = path.join(OUT, 'connection.private.json'); await fs.writeFile(connectionFile, JSON.stringify({ port: connection.port, token: connection.token, pid: connection.pid }), { mode: 0o600 });
  let config = await fs.readFile(path.join(ROOT, 'apps/desktop/vite.config.ts'), 'utf8');
  config = config.replace('const desktopRoot = dirname(fileURLToPath(import.meta.url));', `const desktopRoot = ${JSON.stringify(path.join(ROOT, 'apps/desktop'))};`).replace("const connectionFile = resolve(desktopRoot, '../../.artifacts/dev/control-connection.json');", `const connectionFile = ${JSON.stringify(connectionFile)};`).replaceAll('1420', String(port));
  const configFile = path.join(OUT, 'app.vite.config.ts'); await fs.writeFile(configFile, config);
  vite = await createViteServer({ configFile }); await vite.listen();
  browser = await chromium.launch({ headless: true, executablePath: executable, args: ['--disable-gpu'], chromiumSandbox: true });
  report.browser = { product: 'Google Chrome 独立临时实例', version: browser.version(), playwright_version: require(path.join(playwrightPath, 'package.json')).version, executable, chromium_sandbox: true, existing_user_tabs_touched: false, control_pid: control.pid };
  assert.deepEqual((await request('GET', '/projects')).items, []);
  await keyboardFlow(); await addFixtures(); await matrix();
  const attemptPage = await request('GET', `/attempts?project_id=${report.fixture_resources.project.id}`); check('整个验收没有创建模型运行', attemptPage.items.length === 0);
  check('页面没有外部网络请求', report.blocked_requests.length === 0, { blocked_requests: report.blocked_requests });
  check('浏览器无脚本或控制台错误', report.browser_errors.length === 0, { errors: report.browser_errors });
  const changed = [];
  for (const file of sourcePaths) if (createHash('sha256').update(await fs.readFile(path.join(ROOT, file))).digest('hex') !== report.sources[file]) changed.push(file);
  check('验收期间使用同一源码版本', changed.length === 0, { changed_sources: changed });
  report.success = report.checks.every(item => item.passed);
} catch (error) { report.failure = { message: error.message, stack: error.stack }; }
finally {
  await browser?.close().catch(() => {}); await vite?.close().catch(() => {});
  if (control?.pid && control.exitCode === null && control.signalCode === null) { control.kill('SIGTERM'); await Promise.race([once(control, 'exit'), new Promise(resolve => setTimeout(resolve, 10000))]); if (control.exitCode === null && control.signalCode === null) { control.kill('SIGKILL'); await once(control, 'exit'); } }
  report.control_final = { pid: control?.pid ?? null, exit_code: control?.exitCode ?? null, signal_code: control?.signalCode ?? null };
  await fs.writeFile(path.join(OUT, 'control.stderr.log'), controlErrors);
  report.completed_at = new Date().toISOString(); report.summary = { passed: report.checks.filter(item => item.passed).length, failed: report.checks.filter(item => !item.passed).length, captures: report.captures.length, browser_errors: report.browser_errors.length };
  await fs.writeFile(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ success: report.success, ...report.summary, failure: report.failure?.message, report: path.join(OUT, 'report.json') }));
  if (!report.success) process.exitCode = 1;
}
