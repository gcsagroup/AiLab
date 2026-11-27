'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { trialThreads } = require('./trial-devices.cjs');
const { randomInt } = require('node:crypto');

// These two SDK recipes share a sampling graph. LLaDA additionally loads its
// prompt adapter and uses its own noise schedule. The DGL context releases each
// component after its last use and enforces the host weight-buffer budget.
async function runBoundedImage({ family, components, input, runtime, out, dir, engine, invoke, signal, limit }) {
  if (!['lens', 'llada_image'].includes(family)) throw Error('未知的分段图像配方。');
  const string = JSON.stringify;
  const file = role => {
    const name = components.get(role);
    if (!name) throw Error('图像模型缺少组件 ' + role);
    return string(name.split(path.sep).join('/'));
  };
  const llada = family === 'llada_image';
  const loader = 'family = ' + string(family) + ', backend = ' + string((runtime.device_id || 'cpu').toLowerCase()) + ', params_backend = "disk"';
  const adapter = llada ? ', connectors_path = ' + file('--embeddings-connectors') : '';
  const size = Number(runtime.size);
  const steps = Number(runtime.steps);
  const cfg = Number(runtime.cfg);
  let seed = Number(runtime.seed);
  if (![size, steps, seed].every(Number.isSafeInteger) || size < 1 || steps < 1 || !Number.isFinite(cfg))
    throw Error('图像采样参数无效。');
  if (seed < 0) seed = randomInt(0x7fffffff);
  const decode = prompt => 'encode_prompt(text, ' + string(prompt) + ', width = ' + size + ', height = ' + size + ')';
  const lines = [
    'fn main() {',
    '  model = load_dit(' + file('--diffusion-model') + ', ' + loader + ')',
    '  text = load_text_encoder(' + file('--llm') + ', tokenizer = ' + file('--tokenizer') + adapter + ', ' + loader + ')',
    '  vae = load_vae(' + file('--vae') + ', ' + loader + ')',
    '  base = tensor::zeros(latent_shape(vae, width = ' + size + ', height = ' + size + '))',
    '  positive = ' + decode(input),
    '  pos = predictor(model, positive)',
  ];
  if (cfg !== 1) lines.push(
    '  negative = ' + decode(runtime.negative_prompt || ''),
    '  neg = predictor(model, negative)',
    '  guided = cfg(pos, neg, scale = ' + cfg + ')',
  );
  const predictor = cfg === 1 ? 'pos' : 'guided';
  lines.push(
    '  sigmas = make_sigmas(' + predictor + ', latent = base, steps = ' + steps + ', scheduler = ' + string(llada ? 'llada_image' : 'discrete') + ')',
    '  rng = make_rng("cpu", seed = ' + seed + ')',
    '  start = add_noise(' + predictor + ', base, tensor::randn_like(base, rng = rng), sigma = sigmas[0])',
    '  latent = sample(start, sigmas, predict = ' + predictor + ', method = "euler", rng = rng)',
    '  image = vae_decode(vae, dit_to_vae_latents(vae, latent))',
    '  image::save("image.png", image)',
    '  return {image = image}',
    '}',
  );
  const script = path.join(dir, 'sample.dgl');
  await fs.writeFile(script, lines.join('\n'));
  await invoke(engine, ['-M', 'dgl', '--script', path.relative(out, script), '--max-ram', String(limit),
    '--disable-prefetch', '--run-once', 'on', '-t', String(trialThreads(runtime))], { cwd: out, signal });
  return { name: 'image.png', media_type: 'image/png' };
}

async function runLtxVideo({components,input,runtime,out,dir,engine,invoke,signal,limit,frames,output}) {
  const asset=role=>{
    const file=components.get(role);
    if (!file) throw Error('LTX-2.5 缺少组件 '+role);
    return JSON.stringify(file.split(path.sep).join('/'));
  };
  const {inference_width:width,inference_height:height,steps,cfg,fps}=runtime;
  if (![width,height,frames,fps,steps].every(n=>Number.isSafeInteger(n) && n>0) || !Number.isFinite(cfg))
    throw Error('LTX-2.5 视频采样参数无效。');
  const seed=runtime.seed<0 ? randomInt(0x7fffffff) : runtime.seed;
  const loader='family = "ltxav", backend = ' + JSON.stringify((runtime.device_id || 'cpu').toLowerCase()) + ', params_backend = "disk"';
  const condition=(name,prompt)=>[
    `  ${name}_text = encode_prompt(text, ${JSON.stringify(prompt)}, width = ${width}, height = ${height})`,
    `  ${name} = predictor(model, ${name}_text, audio_length = audio_dims[1], fps = ${fps})`,
  ];
  const lines=[
    'fn main() {',
    `  model = load_dit(${asset('--diffusion-model')}, ${loader})`,
    `  text = load_text_encoder(${asset('--llm')}, ${loader}, projection_path = ${asset('--diffusion-model')})`,
    `  vae = load_vae(${asset('--vae')}, ${loader})`,
    `  sound_vae = load_audio_vae(${asset('--audio-vae')}, ${loader})`,
    `  v = latent_shape(vae, width = ${width}, height = ${height}, frames = ${frames})`,
    `  audio_dims = audio_latent_shape(sound_vae, frames = ${frames}, fps = ${fps})`,
    // LTX samples video and sound together. Its packed zero latent only needs
    // the sound dimensions when the trial exports video without a soundtrack.
    '  tail = math::ceil_div(math::product(audio_dims), v[0] * v[1] * v[2])',
    '  base = tensor::zeros([v[0], v[1], v[2], v[3] + tail, 1])',
    ...condition('positive',input),
  ];
  if (cfg!==1) lines.push(...condition('negative',runtime.negative_prompt || ''),
    `  guided = cfg(positive, negative, scale = ${cfg})`);
  const predictor=cfg===1 ? 'positive' : 'guided';
  lines.push(
    `  sigmas = make_sigmas(${predictor}, latent = base, steps = ${steps}, scheduler = "ltx2")`,
    `  rng = make_rng("cpu", seed = ${seed})`,
    `  start = add_noise(${predictor}, base, tensor::randn_like(base, rng = rng), sigma = sigmas[0])`,
    `  sampled = sample(start, sigmas, predict = ${predictor}, method = "euler", rng = rng)`,
    '  video_latent = sampled[:, :, :v[2], :v[3]]',
    '  pixels = vae_decode(vae, dit_to_vae_latents(vae, video_latent))',
    `  clip = {frames = pixels, fps_num = ${fps}, fps_den = 1}`,
    `  video::save(${JSON.stringify(output.split(path.sep).join('/'))}, clip)`,
    '  return {video = clip}',
    '}');
  const script=path.join(dir,'ltx-video.dgl');
  await fs.writeFile(script,lines.join('\n'));
  await invoke(engine,['-M','dgl','--script',path.relative(out,script),'--max-ram',String(limit),
    '--disable-prefetch','--run-once','on','-t',String(trialThreads(runtime))],{cwd:out,signal});
}
module.exports = { runBoundedImage, runLtxVideo };
