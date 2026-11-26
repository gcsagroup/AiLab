(async () => {
  const button = (name, root = document) => [...root.querySelectorAll('button')].find(b => b.textContent.trim() === name && !b.disabled);
  const wait = async (read, label) => { for (let i=0;i<600;i++) { const value=read(); if(value)return value; await new Promise(r=>setTimeout(r,100)); } throw Error(label + ' ' + document.body.innerText.slice(-1200)); };
  const nav = index => document.querySelectorAll('nav[aria-label="主导航"] button')[index];
  async function confirm() {
    const dialog = await wait(() => [...document.querySelectorAll('dialog[open]')].find(d => d.textContent.includes('确认删除')), '确认框');
    button('确认删除', dialog).click();
    await wait(() => ![...document.querySelectorAll('dialog[open]')].some(d => d.textContent.includes('确认删除')), '确认完成');
  }
  await wait(() => nav(1) && button('AI 辅助'), '启动');
  button('AI 辅助').click();
  (await wait(() => button('打开语言试用草稿'), '试用入口')).click();
  await wait(() => document.querySelector('.composer'), '试用界面');
  document.querySelector('.breadcrumb button').click();
  await wait(() => document.querySelector('main h1')?.textContent === '模型训练与运行', '工作台');
  button('任务队列').click();
  const queue = await wait(() => [...document.querySelectorAll('dialog[open]')].find(d => d.textContent.includes('任务队列与历史')), '任务队列');
  const row = await wait(() => queue.querySelector('.deletable-row'), '任务记录');
  button('删除', row).click(); await confirm();
  await wait(() => !queue.querySelector('.deletable-row'), '任务已删除');
  queue.querySelector('button[aria-label="关闭对话框"]').click();
  nav(1).click();
  await wait(() => document.querySelector('main h1')?.textContent === '模型库', '模型库');
  const download = await wait(() => [...document.querySelectorAll('.deletable-row')].find(c => c.textContent.includes('Qwen2.5-0.5B')), '下载记录');
  button('删除记录', download).click(); await confirm();
  await wait(() => ![...document.querySelectorAll('.deletable-row')].some(c => c.textContent.includes('Qwen2.5-0.5B')), '记录已删除');
  const model = await wait(() => [...document.querySelectorAll('.resource-card')].find(c => c.textContent.includes('Qwen2.5-0.5B')), '模型仍存在');
  button('删除模型', model).click(); await confirm();
  await wait(() => ![...document.querySelectorAll('.resource-card')].some(c => c.textContent.includes('Qwen2.5-0.5B')), '模型已删除');
  nav(4).click();
  await wait(() => document.querySelector('main h1')?.textContent === '作品与素材', '作品页面');
  const work = await wait(() => [...document.querySelectorAll('.work-card')].find(c => c.textContent.includes('验收作品')), '作品');
  button('删除作品', work).click(); await confirm();
  await wait(() => !document.body.innerText.includes('验收作品'), '作品已删除');
  return {passed:true, task:true, download:true, model:true, work:true};
})()
