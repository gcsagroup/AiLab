(async () => {
  const checks = [];
  const waitFor = async (test, name, timeout = 15000) => {
    const end = Date.now() + timeout;
    while (!test()) {
      if (Date.now() > end) throw new Error(`Timed out: ${name}. ${document.body.innerText.slice(0, 1200)}`);
      await new Promise(resolve => setTimeout(resolve, 80));
    }
    checks.push(name);
  };
  const text = () => document.body.innerText;
  const button = label => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === label);
  await waitFor(() => text().includes('Windows UI 预览版') && document.querySelectorAll('nav[aria-label="主导航"] button').length === 5, 'Application mounts');
  await waitFor(() => document.querySelector('main .category-grid, main .workbench-layout'), 'Saved project finishes loading', 45000);
  const nav = [...document.querySelectorAll('nav[aria-label="主导航"] button')];
  nav[0].click();
  await waitFor(() => text().includes('语言模型'), 'Home renders');
  button('新建工作流').click();
  await waitFor(() => document.querySelector('dialog[open] .workflow-setup-step:nth-of-type(2) textarea'), 'Video prompt in workflow dialog');
  const videoPrompt = document.querySelector('dialog[open] .workflow-setup-step:nth-of-type(2) textarea');
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(videoPrompt, '镜头缓慢推近');
  videoPrompt.dispatchEvent(new Event('input', {bubbles: true}));
  await waitFor(() => videoPrompt.value === '镜头缓慢推近' && !videoPrompt.matches(':disabled'), 'Workflow video prompt accepts text');
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  await waitFor(() => !document.querySelector('dialog[open]'), 'Workflow dialog closes');
  await waitFor(() => button('1 · 准备官方语言模型'), 'Official language model entry is present');
  button('2 · 检查本机环境').click();
  const reportTime = () => document.querySelector('dialog[open] time')?.dateTime;
  await waitFor(() => reportTime() && !button('刷新环境')?.disabled, 'Home check reads a native environment report', 45000);
  await waitFor(() => document.querySelectorAll('table.runtime-guide tbody tr').length === 3 &&
    ['基础运行库','图片与视频运行库','音频运行库','语言 CUDA 加速','图片视频 CUDA 加速','音频 CUDA 加速']
      .every(label => [...document.querySelectorAll('table.runtime-guide td strong')].some(el => el.textContent === label)) &&
    document.querySelector('.runtime-directory code')?.textContent && button('选择本机已有运行库') && !button('下载并配置'),
    'Task guide shows all six runtime choices and the active runtime directory');
  const checked = reportTime();
  button('刷新环境').click();
  await waitFor(() => reportTime() && reportTime() !== checked && !button('刷新环境').disabled, 'Refresh completes a new hardware and runtime probe', 45000);
  document.querySelector('dialog details summary').click();
  await waitFor(() => text().includes('FFmpeg 视频编码') && text().includes('FFmpeg 音频转换') && text().includes('GGML 设备枚举'), 'Individual probe results render');
  button('导出诊断摘要').click();
  await waitFor(() => text().includes('已保存 environment-smoke.json'), 'Current report is exported from the dialog');
  const exportedAt = reportTime();
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  await waitFor(() => !document.querySelector('dialog[open]'), 'Home environment check closes');
  button('1 · 准备官方语言模型').click();
  await waitFor(() => document.querySelector('dialog[open] input[type="search"]'), 'Official model search opens');
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  await waitFor(() => !document.querySelector('dialog[open]'), 'Official model search closes');
  for (const [index, label] of ['模型训练与运行', '模型库', '数据集市场', '模型实验室', '作品与素材'].entries()) {
    nav[index].click(); await waitFor(() => document.querySelector('main h1')?.textContent === label, `Navigate: ${label}`);
  }
  button('设备与环境').click();
  await waitFor(() => document.querySelector('dialog[open]') && text().includes('可用任务组合'), 'Environment dialog renders');
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  await waitFor(() => !document.querySelector('dialog[open]'), 'Environment dialog closes');
  nav[0].click(); await waitFor(() => text().includes('语言模型'), 'Home returns');
  for (const [category, modelLabel] of [['模型', '基座模型'], ['图片', '图片基座模型'], ['视频', '视频模型'], ['音频', '配音模型']]) {
    const categoryButton = [...document.querySelectorAll('.category')].find(item => item.querySelector('strong')?.textContent === ({模型:'语言模型', 图片:'图片生成', 视频:'视频生成', 音频:'音频试用'})[category]);
    categoryButton.click();
    await waitFor(() => categoryButton.getAttribute('aria-pressed') === 'true', category + '分类已选中');
    await waitFor(() => document.querySelector('[aria-label="试用运行库"] strong')?.textContent === ({模型:'基础运行库',图片:'图片与视频运行库',视频:'图片与视频运行库',音频:'音频运行库'})[category], category + '点击类别后显示对应的运行库');
    await waitFor(() => {
      const steps = [...document.querySelectorAll('.module-start .steps span')].map(item => item.textContent);
      const create = button('新建试用');
      return create && !create.disabled && steps.join('|') === '1选择模型|2填写输入|3检查并运行' && !document.querySelector('.module-start select');
    }, category + '试用入口显示原三步提示和新建按钮');
    button('新建试用').click();
    const selectId = category === '模型' ? 'base-model' : 'media-model';
    await waitFor(() => document.querySelector('select#' + selectId) && document.querySelector('label[for="' + selectId + '"]')?.textContent === modelLabel, category + '草稿使用原模型选择栏');
    nav[0].click();
    await waitFor(() => document.querySelector('.category-grid'), category + '草稿返回工作台');
  }
  document.querySelector('.category').click();
  await waitFor(() => document.querySelector('.module-heading h2')?.textContent === '语言与多模态', 'Text category selected');
  document.querySelector('[aria-label="工作台操作"] [role="tab"]').click();
  await waitFor(() => button('新建训练') && !button('新建训练').disabled, 'Draft creation is ready');
  button('新建训练').click();
  await waitFor(() => Boolean(document.querySelector('select#training-data')), 'Training draft opens');
  nav[0].click(); await waitFor(() => button('直接试用') && !button('直接试用').disabled, 'Return from training draft');
  button('直接试用').click();
  await waitFor(() => Boolean(document.querySelector('textarea[aria-label="输入内容"]')), 'Text generation draft opens');
  const input = document.querySelector('textarea[aria-label="输入内容"]');
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, 'Windows UI 草稿保存测试');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await waitFor(() => JSON.parse(localStorage.getItem('gcsa-ailab-windows-ui-v1')).tasks.some(task => task.draft.input.prompt === 'Windows UI 草稿保存测试'), 'Draft persists locally');
  return { passed: true, checks, title: document.title, localPreview: true, exportedAt };
})()
