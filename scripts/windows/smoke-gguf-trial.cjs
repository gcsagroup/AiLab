(async function trial(kind, family, stepCount) {
  const wait = async (fn, desc, ms = 120000) => {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const result = fn();
      if (result) return result;
      await new Promise((r) => setTimeout(r, 200));
    }
    throw Error(desc + ' ' + document.querySelector('main')?.innerText?.slice(-2200));
  };
  const btn = (name) =>
    [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === name && !b.disabled);
  const selector = (element, value) => {
    const proto = Object.getPrototypeOf(element);
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
  };
  if (kind === 'video' && family === 'MiniMax-H3') {
    const modelTrial = await wait(() => {
      if (document.querySelector('main h1')?.textContent !== '模型库') {
        btn('模型库')?.click();
        return false;
      }
      const card = [...document.querySelectorAll('.resource-card')].find(el => {
        const name = el.querySelector('h2')?.textContent || '';
        return /MiniMax-H3/i.test(name) && !/MiniMax-H3-Image/i.test(name);
      });
      return card && [...card.querySelectorAll('button')].find(b => b.textContent.trim() === '试用' && !b.disabled);
    }, '从已登记的 MiniMax-H3 模型开始试用');
    modelTrial.click();
    await wait(() => document.querySelector('#media-model')?.value, '带入模型');
    const steps = [...document.querySelectorAll('.composer label')].find(l => l.textContent.startsWith('生成步数'))?.querySelector('input');
    if (steps?.value !== '4') throw Error('模型库试用没有采用 MiniMax-H3 的默认生成步数。');
  } else if (kind === 'text' && !family) {
    await wait(() => document.querySelector('main h1')?.textContent, '工作台载入');
    (
      await wait(() => {
        const match = [...document.querySelectorAll('.task-row')].find(
          (b) =>
            b.textContent.includes('Qwen/Qwen2.5-0.5B-Instruct-GGUF') &&
            b.textContent.includes('已加入模型库'),
        );
        if (!match && document.querySelector('main h1')?.textContent !== '模型库')
          document.querySelectorAll('nav[aria-label="主导航"] button')[1]?.click();
        return match;
      }, '已登记权重')
    ).click();
    (await wait(() => btn('用此模型开始试用'), '原试用按钮')).click();
  } else {
    const title = { text:'模型训练 / 微调', image: '图片训练 / 微调', audio: '音频训练 / 微调', video: '视频训练 / 微调' }[kind];
    (
      await wait(
        () =>
          [...document.querySelectorAll('.category-grid button')].find((b) => b.textContent.includes(title)),
        '选择类别',
      )
    ).click();
    (await wait(() => btn('直接试用'), '原试用入口')).click();
    const select = await wait(() => {
      const e = document.querySelector(kind==='text'?'#base-model':'#media-model');
      return e?.options.length > 1 && e;
    }, '已登记媒体模型');
    const option=family?[...select.options].find(o=>o.value && o.textContent.toLowerCase().includes(family.toLowerCase())):select.options[1];
    if (!option) throw Error('未找到模型 '+family);
    selector(select, option.value);
  }
  await wait(() => document.querySelector('.composer'), '试用工作台');
  if (kind === 'text' && family) {
    selector(document.querySelector('.composer textarea'),'@素材 sunflower\nName the flower in this image. Answer in English.');
    const thinking=[...document.querySelectorAll('.composer label')].find(l=>l.textContent.includes('思考') && l.querySelector('select option[value="disabled"]'))?.querySelector('select');
    if (thinking) selector(thinking,'disabled');
  } else if (kind === 'text') {
    selector(
      document.querySelector('.composer textarea'),
      'What is the capital of France? Answer in one word.',
    );
    const kv = [...document.querySelectorAll('label')]
      .find((l) => l.textContent.startsWith('KV 缓存精度'))
      .querySelector('select');
    selector(kv, 'q8');
    const preset = [...document.querySelectorAll('label')]
      .find((l) => l.textContent.startsWith('运行预设'))
      .querySelector('select');
    selector(preset, 'low_memory_v2');
    (await wait(() => btn('预览预设差异'), '预览低内存分块')).click();
    (await wait(() => btn('应用到草稿'), '应用预设')).click();
    const block = [...document.querySelectorAll('label')]
      .find((l) => l.textContent.startsWith('提示词分块上限'))
      .querySelector('select');
    await wait(() => block.value === '512' && kv.value === 'q8', '预设应采用 512 分块并保留 Q8 缓存', 5000);
    const max = [...document.querySelectorAll('label')]
      .find((l) => l.textContent.startsWith('最大输出 token'))
      .querySelector('input');
    selector(max, '12');
  } else if (kind === 'video' && family) {
    selector(document.querySelector('.composer textarea'),'A yellow sunflower sways in a sunny garden. The leaves rustle in the breeze and a bird chirps nearby.');
  } else if (kind === 'video') {
    const mat = await wait(() => {
      const e = document.querySelector('#video-source');
      return e?.options.length > 1 && e;
    }, 'PNG 素材');
    selector(mat, mat.options[1].value);
  } else
    selector(
      document.querySelector('.composer textarea'),
      kind === 'image' ? (family ? 'A close-up studio photograph of one large sunflower centered in the frame. Golden yellow petals surround a dark brown seed head. A green stem and two leaves stand against a clean sky-blue backdrop, with soft daylight and sharp botanical detail.' : 'a small yellow sunflower on a blue background') : '你好，欢迎使用本地语音模型。',
    );
  if ((!family || stepCount) && (kind === 'image' || kind === 'video')) {
    const steps = [...document.querySelectorAll('.composer label')]
      .find((l) => l.textContent.startsWith('生成步数'))
      .querySelector('input');
    selector(steps, String(stepCount || (kind === 'video' ? 4 : 3)));
    await wait(() => Number(steps.value) === (stepCount || (kind === 'video' ? 4 : 3)), '应用测试步数');
  }
  (await wait(() => btn('检查配置'), '检查配置')).click();
  await wait(() => document.querySelector('.preflight'), '实际配置');
  const run = await wait(() => btn('开始运行') || document.querySelector('.preflight .error'), '预检结果');
  if (run.tagName !== 'BUTTON') throw Error(run.textContent);
  run.click();
  const saved = await wait(
    () => {
      const card = document.querySelector('.result-card');
      if (card?.querySelector('.result-header')?.textContent.includes('失败')) throw Error(card.innerText.slice(-2200));
      return btn('保存作品') || card?.querySelector('.error');
    },
    '推理输出',
    7200000,
  );
  if (saved.tagName !== 'BUTTON') throw Error(saved.textContent);
  const performancePanel = await wait(() => {
    const panel = document.querySelector('.result-card [aria-label="推理性能"]');
    return panel?.textContent.includes('总耗时') && panel;
  }, '显示本次试用总耗时');
  performancePanel.querySelector('summary').click();
  if (!performancePanel.innerText.includes('执行器运行')) throw Error('缺少执行器耗时');
  const display =
    kind === 'text'
      ? document.querySelector('.model-output')?.textContent
      : (
          await wait(
            () => document.querySelector('.media-preview img,.media-preview video,.media-preview audio'),
            '媒体预览',
            60000,
          )
        ).tagName;
  if (kind === 'text' && !(family?/sunflower/i:/Paris/i).test(display)) throw Error('模型回答：' + display);
  if (kind !== 'text') {
    await wait(
      () => {
        const media = document.querySelector('.media-preview img,.media-preview video,.media-preview audio');
        if (!media) return false;
        if (media.error) throw Error('媒体解码失败：' + media.error.message);
        if (kind === 'image')
          return media.complete && media.naturalWidth === 512 && media.naturalHeight === 512;
        if (media.readyState < 1 || !Number.isFinite(media.duration) || media.duration <= 0) return false;
        if (kind === 'video')
          return (
            media.videoWidth === 1024 && media.videoHeight === 576 && Math.abs(media.duration - (family ? 22/24 : 2)) < 0.08
          );
        return true;
      },
      '解码生成媒体',
      60000,
    );
  }
  if (family && kind === 'image') {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 32;
    const context = canvas.getContext('2d');
    context.drawImage(document.querySelector('.media-preview img'), 0, 0, 32, 32);
    const pixels = context.getImageData(0, 0, 32, 32).data;
    const colors = new Set();
    for (let i = 0; i < pixels.length; i += 4) colors.add((pixels[i] << 16) | (pixels[i+1] << 8) | pixels[i+2]);
    if (colors.size < 8) throw Error('生成的向日葵画面缺少像素变化。');
  }
  if (kind === 'video') {
    const media = document.querySelector('.media-preview video');
    media.muted = true;
    await media.play();
    await wait(() => media.currentTime >= 0.2, '播放生成的视频', 10000);
    media.pause();
  }
  saved.click();
  await wait(
    () => [...document.querySelectorAll('button')].some((b) => b.textContent.includes('已保存作品')),
    '保存作品',
  );
  const measured = performancePanel.innerText;
  const total = performancePanel.querySelector('.performance-highlights dd').textContent;
  const taskName = document.querySelector('main h1').textContent;
  btn('工作台').click();
  const history = await wait(() => [...document.querySelectorAll('.task-row')].find(row =>
    row.querySelector('.task-name strong')?.textContent === taskName && row.textContent.includes('查看结果')), '历史运行入口');
  history.click();
  await wait(() => document.querySelector('.result-card .performance-highlights dd')?.textContent === total, '历史运行读回同一总耗时');
  return { passed: true, kind, display, measured, historyVerified: true };
});
