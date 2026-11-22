// Runs only with --smoke-result and --smoke-model-download in an isolated profile.
(async (useSmallModel = false) => {
  const button = text => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === text);
  const wait = async (read, description, timeout = 60000) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      const result = read();
      if (result) return result;
      const error = document.querySelector('dialog [role="alert"]')?.textContent;
      if (error) throw new Error(description + '：' + error);
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    throw new Error(description + ' 超时：' + document.body.innerText.slice(-1200));
  };
  (await wait(() => button('1 · 准备官方语言模型'), '首次使用入口')).click();
  const repo = useSmallModel ? 'ggml-org/models-moved' : 'Qwen/Qwen2.5-0.5B-Instruct-GGUF';
  if (useSmallModel) {
    const search = await wait(() => document.querySelector('dialog input[type=search]'), '搜索框');
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(search, repo);
    search.dispatchEvent(new Event('input', {bubbles:true}));
    const selectOption = async (value, description) => {
      const select = await wait(() => [...document.querySelectorAll('dialog select')].find(element =>
        [...element.options].some(option => option.value === value)), description);
      select.value = value;
      select.dispatchEvent(new Event('change', {bubbles:true}));
    };
    await selectOption(repo, '查找发布仓库');
    const file = 'tinyllamas/stories15M-q4_0.gguf';
    await selectOption(file, '选择 GGUF 版本');
    await wait(() => document.querySelector('section[aria-label="固定模型来源"] li')?.textContent.startsWith(file), '核对所选 GGUF 文件');
  }
  const start = await wait(() => {
    const b = button('下载并核对所选文件');
    return b && !b.disabled && b;
  }, '读取官方清单');
  const review = document.querySelector('section[aria-label="固定模型来源"]').innerText;
  if (!review.includes(repo)) throw new Error('意外的默认仓库。');
  start.click();
  const progress = await wait(() => document.querySelector('dialog progress'), '建立下载记录');
  let restored = false;
  const resume = button('继续下载并核对');
  if (resume) { resume.click(); restored = true; }
  await wait(() => progress.value > 1024 * 1024 || button('加入当前项目模型库'), '开始接收权重', 180000);
  let resumed = restored;
  if (button('停止下载，保留进度')) {
    button('停止下载，保留进度').click();
    (await wait(() => button('继续下载并核对'), '停止并保留进度')).click();
    resumed = true;
  }
  const registration = await wait(() => button('加入当前项目模型库') || button('用此模型开始试用') || button('已加入当前项目模型库'), '下载并核对 GGUF', 10800000);
  if (registration.textContent.trim() === '加入当前项目模型库') registration.click();
  await wait(() => button('已加入当前项目模型库') || button('用此模型开始试用'), '登记模型', 120000);
  const result = {passed: true, source: review, resumed, bytes: progress.max, location: document.querySelector('dialog [role="status"]')?.textContent};
  document.querySelector('dialog button[aria-label="关闭对话框"]').click();
  const nav = document.querySelectorAll('nav[aria-label="主导航"] button');
  nav[1].click();
  await wait(() => document.querySelector('main h1')?.textContent === '模型库' && document.querySelector('main')?.innerText.includes('已加入模型库'), '模型库可回读');
  return result;
})
