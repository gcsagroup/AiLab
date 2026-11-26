(async () => {
  const button = label => [...document.querySelectorAll('button')].find(b => b.textContent.trim() === label && !b.disabled);
  async function waitFor(read, stage, timeout = 45000) {
    const until = Date.now() + timeout;
    while (Date.now() < until) {
      const value = read();
      if (value) return value;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw Error(stage + '：' + document.body.innerText.slice(-1300));
  }
  (await waitFor(() => document.querySelector('main .category-grid') && button('AI 辅助'), '打开 AI 辅助')).click();
  (await waitFor(() => button('打开语言试用草稿'), '打开试用草稿')).click();
  const select = await waitFor(() => document.querySelector('select[aria-label="本地建议模型"]'), '模型库已加载');
  const trialModel = document.querySelector('#base-model')?.value;
  const choice = [...select.options].find(option => /Qwen2.5-0.5B-Instruct/i.test(option.textContent));
  if (!choice) throw Error('验收项目需要已登记的 Qwen2.5-0.5B-Instruct。');
  select.value = choice.value;
  select.dispatchEvent(new Event('change', {bubbles: true}));
  const input = document.querySelector('textarea[aria-label="建议问题"]');
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, '请将最大输出改为 64 token，简要说明这样设置的作用。');
  input.dispatchEvent(new Event('input', {bubbles: true}));
  (await waitFor(() => button('检查建议请求'), '提交建议检查')).click();
  (await waitFor(() => button('生成建议（本机）'), '本机模型预检')).click();
  const preview = () => document.querySelector('section[aria-label="建议变更预览"] p')?.textContent;
  const answer = await waitFor(preview, '本机建议结果', 180000);
  const data = await window.ailabHF.request('workbench', {method:'GET', path:'/attempts?project_id=project-ui-preview'});
  const run = data.data?.data?.items?.find(a => a.task_id.startsWith('task-ai-') && a.state === 'succeeded');
  if (run?.snapshot.model_id !== choice.value || run.effective_config.device_id !== 'cpu' || !run.output_text.trim())
    throw Error('执行记录与建议模型选择不一致。');
  const target = document.querySelector('#base-model')?.value;
  if (target !== trialModel) throw Error('选择建议模型时意外改变了试用模型。');
  button('AI 辅助').click();
  await waitFor(() => !document.querySelector('.ai-panel'), '关闭面板');
  button('AI 辅助').click();
  await waitFor(() => preview() === answer, '重新打开后恢复同一次回答');
  let appliedAndUndone = false;
  if (button('应用这些字段')) {
    const maxTokens = [...document.querySelectorAll('.composer label')]
      .find(label => label.textContent.startsWith('最大输出 token')).querySelector('input');
    const original = maxTokens.value;
    button('应用这些字段').click();
    await waitFor(() => button('撤销本次应用') && maxTokens.value === '64', '将建议应用到试用草稿');
    button('撤销本次应用').click();
    await waitFor(() => button('应用这些字段') && maxTokens.value === original, '撤销并还原原值');
    appliedAndUndone = true;
  }
  return {passed: true, model: choice.textContent, modelId: choice.value, device: run.effective_config.device_id,
    answer, performance: run.performance, restored: true, appliedAndUndone};
})()
