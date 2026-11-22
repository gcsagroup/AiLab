'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { join, resolve } = require('node:path');
const { metadata } = require('../../apps/windows-ui/hf/gguf-metadata.cjs');
const { Trials } = require('../../apps/windows-ui/hf/trials.cjs');
const { parameters, textWorker } = require('../../apps/windows-ui/hf/trial-worker.cjs');

const textDraft = {
  kind: 'text',
  input: { prompt: 'Where is Paris?' },
  runtime: { device_id: 'cpu', seed: 0, context_limit: 1024, max_tokens: 12, temperature: 0, top_p: 1 },
};

test('model-specific settings preserve the requested cache, chunk size and stopping behavior', () => {
  const draft = {
    ...textDraft,
    runtime: {
      ...textDraft.runtime,
      kv_precision: 'q8',
      prefill_step_size: 512,
      stream: false,
      stop: ['完'],
    },
  };
  const effective = parameters(draft, { thinking: false });
  assert.equal(effective.kv_precision, 'q8');
  assert.equal(effective.prefill_step_size, 512);
  assert.equal(effective.stream, false);
  assert.deepEqual(effective.stop, ['完']);
  const thinking = { ...draft, runtime: { ...draft.runtime, thinking: 'enabled' } };
  assert.throws(() => parameters(thinking, { thinking: false }), /思考/);
  assert.equal(parameters(thinking, { thinking: true }).thinking, 'enabled');
  assert.throws(
    () => parameters({ ...draft, runtime: { ...draft.runtime, stop: ['完', '完'] } }, {}),
    /停止序列/,
  );
});

test('a sharded model requires every shard; an ambiguous download needs an exact filename', () => {
  const state = { downloads: { modelDir: resolve('models') } };
  const pick = (paths, filename) =>
    Trials.prototype.weight.call(state, {
      modelId: 'hf-example',
      filename,
      files: paths.map((path) => ({ path })),
    });
  const shard = 'model-00001-of-00002.gguf',
    rest = 'model-00002-of-00002.gguf';
  assert.equal(pick([shard]), null);
  assert.equal(pick([rest]), null);
  assert.equal(pick([shard, rest]), join(state.downloads.modelDir, 'hf-example', shard));
  assert.equal(pick(['a.gguf', 'b.gguf']), null);
  assert.equal(pick(['a.gguf', 'b.gguf'], 'b.gguf'), join(state.downloads.modelDir, 'hf-example', 'b.gguf'));
  assert.equal(pick(['model.safetensors']), null);
});

test('Chinese TTS segments retain punctuation and stay within the phonemizer budget', () => {
  const { splitText, pcmData } = require('../../apps/windows-ui/hf/kokoro.cjs');
  const sentence = '这是一次本地语音试用，保留这句话里的停顿。';
  const text = sentence.repeat(4),
    parts = splitText(text);
  assert.deepEqual(splitText(sentence), [sentence]);
  assert.ok(parts.length > 1);
  assert.equal(parts.join(''), text);
  assert.ok(parts.every((part) => Array.from(part).length <= 48));
  assert.throws(() => pcmData(Buffer.from('invalid')), /WAV/);
});

const file = process.env.AILAB_TEST_QWEN_GGUF;
test(
  'Qwen2.5 native decode honors cache precision, chunked prefill and byte-spanning stops',
  { skip: !file },
  async () => {
    const info = metadata(file);
    assert.equal(info.kind, 'text');
    async function run(prompt, options) {
      const r = parameters(
        { ...textDraft, input: { prompt }, runtime: { ...textDraft.runtime, ...options } },
        info,
      );
      const parts = [];
      let prefill, finish;
      await textWorker({ action: 'generate', model: resolve(file), prompt, runtime: r }, undefined, (e) => {
        if (e.type === 'bytes') parts.push(Buffer.from(e.hex, 'hex'));
        if (e.type === 'prefill') prefill = e;
        if (e.type === 'done') finish = e;
      });
      return { text: Buffer.concat(parts).toString('utf8'), prefill, finish };
    }
    const long = ' hello'.repeat(600);
    const small = await run(long, { prefill_step_size: 512, kv_precision: 'q4', max_tokens: 1 });
    const large = await run(long, { prefill_step_size: 4096, kv_precision: 'f16', max_tokens: 1 });
    assert.equal(small.prefill.chunks, 2);
    assert.equal(small.prefill.kv_precision, 'q4');
    assert.equal(large.prefill.chunks, 1);
    assert.equal(large.prefill.kv_precision, 'f16');
    const prompt = 'Write a creative name for a bookstore. Give a short answer.';
    const greedy = await run(prompt, { kv_precision: 'q8' });
    assert.ok(greedy.text.length >= 6);
    const phrase = greedy.text.slice(1, 5);
    const stopped = await run(prompt, { kv_precision: 'q8', stop: [phrase] });
    assert.equal(stopped.text, greedy.text.slice(0, greedy.text.indexOf(phrase)));
    assert.equal(stopped.finish.finish_reason, 'stop');
  },
);

test('video dispatch uses the packaged image backend and freezes the output recipe', () => {
  const { bins } = require('../../apps/windows-ui/hf/trial-worker.cjs');
  assert.equal(bins.video, bins.image);
  const draft = {
    kind: 'video',
    input: { material_id: 'material-example' },
    runtime: { steps: 4, frames: 14, fps: 7, seed: 42, device_id: 'Vulkan0' },
  };
  const effective = parameters(draft, {});
  assert.equal(effective.pipeline, 'animatediff-sd15');
  assert.deepEqual(
    [
      effective.device_id,
      effective.steps,
      effective.seed,
      effective.inference_width,
      effective.inference_height,
    ],
    ['Vulkan0', 4, 42, 512, 320],
  );
  assert.throws(() => parameters({ ...draft, runtime: { ...draft.runtime, frames: 1 } }, {}), /14 帧/);
});

test('old single-file video models cannot be selected or run after upgrade', async () => {
  const id = 'local-' + '1'.repeat(32),
    project = 'project-example';
  const row = { id, project_id: project, kind: 'video', execution_available: true, path: 'obsolete.gguf' };
  const trials = Object.assign(Object.create(Trials.prototype), {
    rows: new Map([[id, row]]),
    downloads: { records: () => [] },
  });
  const detail = await trials.request({ method: 'GET', path: '/models/' + id + '?project_id=' + project });
  assert.equal(detail.execution_available, false);
  assert.equal(
    (await trials.request({ method: 'GET', path: '/models?project_id=' + project })).items[0]
      .execution_available,
    false,
  );
  assert.throws(() => trials.resolve(id, project), /AnimateDiff/);
});

test(
  'imported motion weights are bound to the video model digest',
  { skip: !process.env.AILAB_TEST_ANIMATEDIFF },
  async (t) => {
    const fs = require('node:fs/promises'),
      os = require('node:os');
    const dir = await fs.mkdtemp(join(os.tmpdir(), 'ailab-animatediff-'));
    t.after(() => fs.rm(dir, { force: true, recursive: true }));
    const trial = new Trials(dir, { records: () => [] });
    const params = { project_id: 'project-example', path: resolve(process.env.AILAB_TEST_ANIMATEDIFF) };
    const plan = await trial.inspectImport('models', params);
    assert.equal(plan.file_count, 2);
    const row = await trial.confirmImport('models', {
      plan_id: plan.id,
      manifest_digest: plan.manifest_digest,
    });
    const ref = trial.resolve(row.id, params.project_id);
    assert.equal(ref.info.kind, 'video');
    await ref.verify();
    const f = await fs.open(ref.motion, 'r+');
    const last = (await f.stat()).size - 1;
    const byte = Buffer.alloc(1);
    try {
      await f.read(byte, 0, 1, last);
      byte[0] ^= 1;
      await f.write(byte, 0, 1, last);
    } finally {
      await f.close();
    }
    await assert.rejects(ref.verify(), /摘要/);
  },
);

test('media prompts bind one current-project reference without treating normal text as a path',()=>{
  const {materialPrompt}=require('../../apps/windows-ui/hf/gguf-bundle.cjs');
  assert.deepEqual(materialPrompt({prompt:'@素材 向日葵\r\n花是什么颜色？'}),{reference:'向日葵',prompt:'花是什么颜色？'});
  assert.equal(materialPrompt({prompt:'C:\\some-file.png'}).reference,undefined);
});
test('FL2VA and H3 Image plan different VAEs and reuse the pinned text encoder',()=>{
  const {sources, conversionTypes, derivedFile}=require('../../apps/windows-ui/hf/h3-weights.cjs');
  assert.equal(conversionTypes('unsloth/MiniMax-H3-Image-GGUF', 'minimax_h3_image_pruned-Q2_K.gguf').encoder, 'bf16');
  assert.notEqual(derivedFile('cache','encoder'), derivedFile('cache','encoder','q4_0'));
  const image=sources('unsloth/MiniMax-H3-Image-GGUF','minimax_h3_image_pruned-Q2_K.gguf');
  const video=sources('leejet/MiniMax-H3-GGUF','minimax_h3_fl2va_pruned-Q4_K_M.gguf');
  assert.deepEqual(image.map(f=>f.role),['encoder','image_vae']);
  assert.deepEqual(video.map(f=>f.role),['encoder','video_vae','audio_vae']);
  assert.equal(image[0].sha256,video[0].sha256);
  assert.ok(video.every(f=>f.size>0 && /^https:\/\/huggingface\.co\/.+\/resolve\/[a-f0-9]{40}\//.test(f.url)));
  assert.deepEqual(sources('leejet/MiniMax-H3-GGUF','qwen3vl_32b_minimax_h3-Q4_K_M.gguf'),[]);
});
test('MiniMax-H3 repairs inherited read-only timing while retaining requested generation settings', () => {
  const saved = {kind:'video', input:{prompt:'sunflowers'}, runtime:{seed:8,steps:1,frames:14,fps:7}};
  for (const timing of [{frames:14,fps:7}, {frames:22,fps:24}, {frames:undefined,fps:undefined}]) {
    const draft = {...saved, runtime:{...saved.runtime,...timing}};
    const r = parameters(draft, {pipeline:'h3-video'});
    assert.deepEqual([r.frames,r.fps,r.steps,r.seed], [22,24,1,8]);
    assert.equal(draft.runtime.frames, timing.frames);
  }
  assert.throws(() => parameters({...saved,runtime:{...saved.runtime,frames:5}}, {pipeline:'h3-video'}), /24 FPS/);
});
test('real Qwen3.5/Gemma projector pairs are checked independently of filenames',{skip:!process.env.AILAB_TEST_FOUR_MODELS},()=>{
  const {bundle}=require('../../apps/windows-ui/hf/gguf-bundle.cjs');
  const root=process.env.AILAB_TEST_FOUR_MODELS;
  const file=(k,n)=>join(root,k,n+'.gguf');
  for(const group of ['qwen','gemma']){
    const base=file(group,'model'),proj=file(group,'mmproj');
    assert.equal(bundle([base,proj]).info.multimodal,true);
    assert.equal(bundle([base]).info.kind,'text');
    assert.equal(bundle([proj]),null);
    assert.equal(bundle([base,file(group==='qwen'?'gemma':'qwen','mmproj')]),null);
  }
});
test('H3 runs only with the matching image or video decoder and encoder', {skip: !process.env.AILAB_TEST_H3_BUNDLES}, () => {
  const {bundle} = require('../../apps/windows-ui/hf/gguf-bundle.cjs');
  const root = process.env.AILAB_TEST_H3_BUNDLES;
  const member = (kind, name) => join(root, kind, name + '.gguf');
  const image = member('image', 'diffusion'), video = member('video', 'diffusion');
  const encoder = member('image', 'encoder'), imageVae = member('image', 'image_vae');
  const videoVae = member('video', 'video_vae'), audioVae = member('video', 'audio_vae');
  assert.equal(bundle([image, encoder, imageVae]).info.pipeline, 'h3-image');
  assert.equal(bundle([video, encoder, videoVae, audioVae]).info.pipeline, 'h3-video');
  assert.equal(bundle([image, encoder, videoVae]), null);
  assert.equal(bundle([video, encoder, imageVae, audioVae]), null);
  assert.equal(bundle([image]), null);
  assert.equal(bundle([video, videoVae, audioVae]), null);
});
