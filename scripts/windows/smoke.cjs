(async () => {
  const checks = [];
  const waitFor = async (test, name) => {
    const end = Date.now() + 15000;
    while (!test()) { if (Date.now() > end) throw new Error(`Timed out: ${name}`); await new Promise(resolve => setTimeout(resolve, 80)); }
    checks.push(name);
  };
  const text = () => document.body.innerText;
  const button = label => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === label);
  await waitFor(() => text().includes('Windows UI 预览版') && document.querySelectorAll('nav[aria-label="主导航"] button').length === 5, 'Application mounts');
  await waitFor(() => document.querySelector('main .category-grid, main .workbench-layout'), 'Saved project finishes loading');
  const nav = [...document.querySelectorAll('nav[aria-label="主导航"] button')];
  nav[0].click();
  await waitFor(() => text().includes('模型训练 / 微调'), 'Home renders');
  for (const [index, label] of ['模型训练与运行', '模型库', '数据集市场', '模型实验室', '作品与素材'].entries()) {
    nav[index].click(); await waitFor(() => document.querySelector('main h1')?.textContent === label, `Navigate: ${label}`);
  }
  button('设备与环境').click();
  await waitFor(() => document.querySelector('dialog[open]') && text().includes('本机 Windows · UI 预览'), 'Environment dialog renders');
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  await waitFor(() => !document.querySelector('dialog[open]'), 'Environment dialog closes');
  nav[0].click(); await waitFor(() => text().includes('模型训练 / 微调'), 'Home returns');
  document.querySelector('.category').click();
  await waitFor(() => document.querySelector('.module-heading h2')?.textContent === '语言与多模态', 'Text category selected');
  document.querySelector('[aria-label="工作台操作"] [role="tab"]').click();
  await waitFor(() => button('新建训练') && !button('新建训练').disabled, 'Draft creation is ready');
  button('新建训练').click();
  await waitFor(() => Boolean(document.querySelector('select#training-data')), 'Training draft opens');
  await waitFor(() => text().includes('训练步数') && !text().includes('无法确认训练参数'), 'Training parameters load');
  nav[0].click(); await waitFor(() => Boolean(button('直接试用')), 'Return from training draft');
  button('直接试用').click();
  await waitFor(() => Boolean(document.querySelector('textarea[aria-label="输入内容"]')), 'Text generation draft opens');
  const input = document.querySelector('textarea[aria-label="输入内容"]');
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, 'Windows UI 草稿保存测试');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await waitFor(() => JSON.parse(localStorage.getItem('gcsa-ailab-windows-ui-v1')).tasks.some(task => task.draft.input.prompt === 'Windows UI 草稿保存测试'), 'Draft persists locally');
  return { passed: true, checks, title: document.title, localPreview: true };
})()
