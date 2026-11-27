'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {recipe,keyOf} = require('./generation-packages.cjs');

const { audioDeviceArgs, gpuBackend, trialThreads } = require('./trial-devices.cjs');

function audioEngine(executable, spec, deviceId = 'cpu') {
  if (deviceId !== 'cpu') {
    const directory = spec?.audioVersion === '0.9.6' ? path.join(path.dirname(executable), 'v0.9.6') : path.dirname(executable);
    return path.join(directory, gpuBackend(deviceId), 'audiocpp_cli.exe');
  }
  if (['f5','auk'].includes(spec?.audioWorker)) return path.join(path.dirname(executable),'f5','audiocpp_cli.exe');
  return spec?.audioVersion==='0.9.6' ? path.join(path.dirname(executable),'v0.9.6','audiocpp_cli.exe') : executable;
}

function diffusionEngine(executable, spec, deviceId = 'cpu') {
  const directory=path.dirname(executable);
  const extended = spec?.diffusionVersion === '0d71f96';
  const backend = deviceId === 'cpu' ? '' : gpuBackend(deviceId);
  return path.join(directory, extended ? '0d71f96' : '', extended || backend === 'cuda' ? backend : '', 'sd-cli.exe');
}

function referenceText(input) {
  const match=/^@参考文本[ \t]+([^\r\n]+)\r?\n/.exec(input);
  return match ? {text:input.slice(match[0].length).trim(),transcript:match[1].trim()} : {text:input.trim()};
}
function languageFor(spec,text) {
  const allowed=spec.languages;
  if (!allowed?.length) return spec.language;
  for (const [language,script] of [['ja',/[\u3040-\u30ff]/],['ko',/[\uac00-\ud7af]/],['zh',/[\u3400-\u9fff]/],['ar',/[\u0600-\u06ff]/],['ru',/[\u0400-\u04ff]/]]) {
    if (allowed.includes(language) && script.test(text)) return language;
  }
  return allowed.includes('auto') ? 'auto' : spec.language;
}
// Only command-line roles used by the pinned SDK's official model recipes are accepted.
const diffusionFlags=new Set(['--model','--diffusion-model','--high-noise-diffusion-model','--uncond-diffusion-model','--control-net','--vae','--audio-vae','--t5xxl','--clip_l','--clip_g','--llm','--llm_vision','--embeddings-connectors','--tokenizer']);
async function runPackage({model,extra,material,out,input,r,bins,invoke,linkWeight,signal}) {
  const packageId=r.generation_package, spec=recipe(packageId,r.native_recipe);
  if (!spec) throw Error('未知的生成模型配方。');
  const id=spec.family||packageId;
  const dir=await fs.mkdtemp(path.join(out,'package-'));
  try {
    const relative=path.basename(dir), names=[];
    for (const [i,asset] of spec.files.entries()) {
      const member=i ? extra[keyOf(packageId,i)] : model;
      if (!member) throw Error('没有找到此模型所需的文件 '+asset.path);
      const target=path.resolve(dir,asset.local);
      if (!target.startsWith(dir+path.sep)) throw Error('模型组件路径无效。');
      await fs.mkdir(path.dirname(target),{recursive:true});
      await linkWeight(member,target);
      names.push(path.relative(out,target));
    }
    if (spec.kind==='audio') {
      let {text,transcript}=referenceText(input);
      const voiceLine=(spec.voiceDesign || spec.speaker) && /^@(音色描述|音色)[ \t]+([^\r\n]+)\r?\n/.exec(text);
      if (voiceLine) text=text.slice(voiceLine[0].length).trim();
      if (!text) throw Error('请在音色设置后填写朗读内容。');
      if (id==='midashenglm_gen' && !/<\|(?:caption|asr|speech|music|sfx|env)\|>/.test(text))
        text='<|caption|> '+text;
      if (id==='echo_tts' && !/^\[S\d+\]/.test(text)) text='[S1] '+text;
      if (id==='vibevoice' && !/^Speaker\s+\d+\s*:/i.test(text)) text='Speaker 1: '+text;
      const song = /^@歌词[ \t]+([\s\S]+?)\r?\n([^\r\n][\s\S]*)$/u.exec(text);
      const music = ['ace_step','heartmula','minimax_music3','mulacover','yue2'].includes(id);
      const lyrics = song ? song[1].trim() : text;
      const description = song ? song[2].trim() : text;
      const explicitBackbone=['zonos2','zonos3','minimax_h3'].includes(id);
      let source=spec.files.length>1 && !explicitBackbone && !['vieneu_v3_turbo','miotts'].includes(id) ? relative : names[0];
      if (spec.compactAudio && r.audio_weight_conversion==='q8_0_to_mixed_q4_k') {
        source=path.join(relative,'cpu-q4_k.gguf');
        await invoke(bins.text,[],{signal,input:{action:'compact-audio',cpu_only:true,model,output:path.join(out,source)}});
      }
      if (spec.conversion==='mira') {
        await require('./mira-convert.cjs').convertInWorker(dir,signal);
        const packer=path.join(path.dirname(bins.audio),'audiocpp_gguf.exe');
        const parts={language_model:'model.safetensors',speaker_encoder:'speaker_encoder.safetensors',processor:'processor.safetensors',
          decoder:'decoders/detokenizer.safetensors',upsampler:'upsampler.safetensors'};
        await invoke(packer,[...Object.entries(parts).flatMap(([key,file])=>['--input',key+'='+file]),
          '--family','mira_tts','--model-spec',path.join(path.dirname(bins.audio),'model_specs/mira_tts.json'),
          '--root','.','--output','mira-tts.gguf','--type','bf16'],{cwd:dir,signal});
        source=path.join(relative,'mira-tts.gguf');
      }
      const raw=path.join(relative,'speech.wav');
      const task=material && ['zipvoice','higgs_audio_tts','chatterbox','firered_audio','fireredtts3','mira_tts','zonos2','zonos3','audio8_tts','omnivoice','voxmel_tts','m5_tts'].includes(id) ? 'clon' : spec.task;
      const deviceArgs = audioDeviceArgs(r);
      const mode = 'offline', threads = trialThreads(r);
      const args=['--task',task,'--family',id,...deviceArgs,'--mode',mode,'--model',source,'--text',music ? (id==='mulacover' ? lyrics : description) : text,
        '--seed',String(r.seed),'--threads',String(threads),'--out',raw];
      const qwen = id === 'qwen3_tts' ? require('./qwen3-tts.cjs').generationOptions(model, r.max_tokens) : undefined;
      const limit = qwen?.max_tokens ?? r.max_tokens;
      if (limit!==undefined && ['max_audio_tokens','max_tokens','max_frames'].includes(spec.audioLimitOption))
        args.push('--request-option',spec.audioLimitOption+'='+limit);
      if (qwen) {
        for (const [name, value] of Object.entries(qwen.sampling)) args.push('--request-option', name + '=' + value);
        args.push('--text-chunk-size', String(qwen.text_chunk_size));
      }
      const language=languageFor(spec,text);
      if (id==='moss_tts_local') args.push('--session-option','moss_tts_local.weight_type=native');
      if (['heartmula','dramabox','confucius4_tts'].includes(id)) args.push('--session-option',id+'.mem_saver=true');
      if (explicitBackbone) args.push('--model-spec-override',path.join(path.dirname(bins.audio),'model_specs',id+'.json'));
      if (language && spec.acceptsLanguage) args.push('--language',id==='moss_ttsd' ? (language==='zh'?'Chinese':'English') : language);
      if (id==='miotts') args.push('--session-option','miotts.codec_model_path='+names[1]);
      if (id==='auk') {
        const main=spec.files[0].local;
        const conditioning=spec.files.find(f=>f.local.startsWith('qwen') && f.local.endsWith('.gguf'));
        const vae=spec.files.find(f=>f.local.startsWith('auk-vae-') && f.local.endsWith('.gguf'));
        args.push('--session-option','auk.variant='+(main.startsWith('auk-flash-')?'flash':'base'),
          '--session-option','auk.model_gguf='+main,'--session-option','auk.qwen_gguf='+conditioning.local,
          '--session-option','auk.vae_gguf='+vae.local);
      }
      if (id==='firered_audio') args.push('--request-option','template_name=tts_clone');
      if (id==='minimax_h3') {
        args.push('--num-inference-steps',String(r.steps ?? 1),'--guidance-scale','1','--request-option','return_video=false',
          '--request-option','width=32','--request-option','height=32','--request-option','num_frames='+Math.round(24*r.duration_seconds+1),
          '--session-option','minimax_h3.mem_saver=true','--request-option','text_layerwise=true',
          '--request-option','text_layerwise_batch=1','--request-option','dit_layerwise=true','--request-option','dit_layerwise_batch=1');
      }
      if (music && (id!=='ace_step' || song)) args.push('--lyrics',lyrics);
      if (id==='ace_step') args.push('--task-route','text2music');
      const kittenVoices=id==='kitten_tts2' ? {ar:'Arabic',zh:'Chinese',fr:'French',de:'German',hi:'Hindi',it:'Italian',pt:'Portuguese',ru:'Russian',es:'Spanish'} : {};
      const voiceId = spec.speaker && (voiceLine?.[1]==='音色' ? voiceLine[2].trim() : kittenVoices[language] || spec.speaker);
      const instruction = (spec.voiceDesign || voiceLine?.[1]==='音色描述') ? voiceLine?.[2]?.trim() || 'A clear, natural speaking voice.' : undefined;
      if (voiceId) args.push('--request-option','voice_id='+voiceId);
      if (instruction) args.push('--instruct',instruction);
      if (id==='auk' && !material) {
        // AuK needs a positive acoustic window for unconditioned speech.
        const cjk=/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/gu;
        const characters=(text.match(cjk)||[]).length;
        const words=(text.replace(cjk,' ').match(/[\p{L}\p{N}]+/gu)||[]).length;
        args.push('--request-option','duration_sec='+Math.max(2,Math.ceil(words/2.5+characters/4)));
      }
      if (['heartmula','mulacover'].includes(id)) args.push('--request-option','tags='+description);
      if (id==='minimax_music3') args.push('--request-option','lyrics='+lyrics);
      if (id==='yue2') args.push('--session-option','yue2.model_gguf='+spec.files[0].local,
        '--request-option','style='+description,'--request-option','cot=off',
        '--request-option','semantic_min_tokens='+Math.round(25*r.duration_seconds),
        '--request-option','semantic_max_tokens='+Math.round(25*r.duration_seconds));
      if (id==='soulx_singer') {
        let score;
        try {score=JSON.parse(text);} catch {}
        if (!['reference','target'].every(key=>Array.isArray(score?.[key]) && score[key].length))
          throw Error('SoulX-Singer 需要在参考音频下方填写歌谱 JSON，其中 reference 和 target 分别为参考歌声与目标歌声的音素、时值和音高分段数组。');
        const control=score.control ?? 'score';
        if (!['score','melody'].includes(control)) throw Error('SoulX-Singer 的 control 可以填写 score 或 melody。');
        for (const key of ['reference','target']) {
          const filename=key+'.json';
          await fs.writeFile(path.join(dir,filename),JSON.stringify(score[key]));
          args.push('--request-option',key+'_metadata_file='+path.join(relative,filename));
        }
        args.push('--request-option','control='+control);
        args.splice(args.indexOf('--text'),2);
      }
      if (id === 'vieneu_v3_turbo') {
        const sdk=path.dirname(bins.audio);
        args.push('--session-option',id+'.g2p_library='+path.join(sdk,'sea_g2p_rs.dll'),
          '--session-option',id+'.g2p_dict_file='+path.join(sdk,'sea_g2p.bin'));
        if (!material) args.push('--request-option','reference_codes_file='+path.join(relative,'voices/minh_quan_pro/ref_codes.txt'),
          '--request-option','speaker_embedding_file='+path.join(relative,'voices/minh_quan_pro/speaker.emb.txt'));
      }
      if (material) {
        const ref=path.join(relative,'reference.wav');
        await linkWeight(material,path.join(out,ref));
        args.push(id==='mulacover'?'--audio':'--voice-ref',ref);
        if (transcript) args.push(id==='vevo2'?'--style-ref-text':'--reference-text',transcript);
        else if (id==='qwen3_tts') args.push('--request-option','x_vector_only_mode=true');
      }
      if (id==='zipvoice') {
        const es=path.join(path.dirname(bins.audio),'espeak');
        args.push('--session-option',id+'.espeak_library_path='+path.join(es,'espeak-ng.dll'),
          '--session-option',id+'.espeak_data_path='+path.join(es,'espeak-ng-data'));
      }
      if (spec.task==='gen' && spec.durationOption) args.push('--duration-seconds',String(r.duration_seconds),'--request-option','duration_sec='+r.duration_seconds);
      if (spec.minSteps && r.steps!==undefined && id!=='minimax_h3') {
        if (spec.stepOption==='num_steps') args.push('--request-option','num_steps='+r.steps);
        else args.push('--num-inference-steps',String(r.steps));
      }
      const synthesis = qwen && { ...qwen, task, backend: deviceArgs[1], mode, threads, model_file: model, text, seed: r.seed, language,
        voice_id: voiceId, instruct: instruction, reference_audio: material, reference_text: material ? transcript : undefined,
        x_vector_only_mode: material ? !transcript : undefined };
      await invoke(audioEngine(bins.audio,spec,r.device_id),args,{cwd:out,signal,recordConfig: synthesis && {stage:'synthesis', values:synthesis}});
      const encoding = {speed:r.speed, sample_rate:24000, channels:1, codec:'pcm_s16le'};
      const format=spec.task==='tts'?['-af','atempo='+encoding.speed,'-ar',String(encoding.sample_rate),'-ac',String(encoding.channels)]:[];
      await invoke(bins.ffmpeg,['-v','error','-i',raw,'-map','0:a:0',...format,'-c:a',encoding.codec,'speech.wav'],{
        cwd:out,signal,recordConfig: qwen && {stage:'audio_encoding', values:encoding}});
      if ((await fs.stat(path.join(out,'speech.wav'))).size<128) throw Error('音频模型未返回有效波形。');
      return {name:'speech.wav',media_type:'audio/wav'};
    }
    const video=spec.kind==='video';
    const engine=diffusionEngine(bins.image,spec,r.device_id);
    const args=['-M',video?'vid_gen':'img_gen','--backend',(r.device_id || 'cpu').toLowerCase(),'--params-backend','cpu','--mmap','-t',String(trialThreads(r))];
    if (spec.disablePrefetch) args.push('--disable-prefetch');
    let components=spec.files.map((f,i)=>({flag:f.flag,name:names[i],convertType:f.convertType}));
    if (id==='sefi_image') {
      const {rewrite}=require('./sefi-layout.cjs');
      for (const flag of ['--diffusion-model','--llm']) {
        const selected=components.filter(c=>c.flag===flag);
        const sources=selected.map(c=>path.join(out,c.name));
        if (sources.length===1 && path.extname(sources[0]).toLowerCase()==='.gguf') continue;
        const name=path.join(relative,flag.slice(2)+'.safetensors');
        await rewrite(sources,path.join(out,name),flag==='--llm',signal);
        components=components.filter(c=>c.flag!==flag);
        components.push({flag,name,convertType:selected[0].convertType});
      }
    }
    const convertedPaths = new Map();
    for (const [i,component] of components.entries()) {
      if (!diffusionFlags.has(component.flag)) throw Error('未知扩散模型参数。');
      let name=component.name;
      if (/\.safetensors$/i.test(name)) {
        const converted=path.join(relative,'converted-'+i+'.gguf');
        const typeRules=['(^|[.])num_batches_tracked$=f32'];
        // MiniT2I adds its masked T5 features to F32 activations on CPU.
        // A half-precision mask token would make the second operand F16.
        if (id==='minit2i' && component.flag==='--diffusion-model') typeRules.push('(^|[.])mask_token$=f32');
        // sd.cpp reads PyTorch's I64 BatchNorm counter as I32. Its integer
        // conversion supports F32, while direct conversion to F16 aborts.
        await invoke(engine,['-M','convert','--backend','cpu','--params-backend','cpu','-t',String(trialThreads(r)),'-m',name,
          '--type',component.convertType || 'f16','--tensor-type-rules',typeRules.join(','),'-o',converted],{cwd:out,signal});
        if (!(await fs.stat(path.join(out,converted))).size) throw Error('扩散组件转换失败：'+component.flag);
        name=converted;
      }
      args.push(component.flag,name);
      convertedPaths.set(component.flag,name);
    }
    if (spec.hostWeightLimitGiB && !video) {
      return await require('./bounded-diffusion.cjs').runBoundedImage({
        family:id, components:convertedPaths, input, runtime:r, out, dir, engine, invoke, signal, limit:spec.hostWeightLimitGiB,
      });
    }
    const raw=video?path.join(relative,'video.avi'):'image.png';
    if (spec.imageReference) {
      const edit=spec.imageReference==='ref-image';
      const size=Math.max(1,Math.round(r.size/(spec.referenceScale || 1)));
      const imageName=path.join(relative,'reference.png');
      await invoke(bins.ffmpeg,['-v','error','-i',material,'-frames:v','1','-vf','scale='+size+':'+size,imageName],{cwd:out,signal});
      if (edit) {
        args.push('--ref-image',imageName);
        if (spec.vaeFormat) args.push('--vae-format',spec.vaeFormat);
      }
      else args.push('--control-image',imageName,'--control-strength','0.8');
    }
    const positive = id === 'lingbot_video' ? JSON.stringify({caption:{comprehensive_description:input}}) : input;
    const negative = id === 'lingbot_video' && r.negative_prompt ? JSON.stringify({universal_negative:{visual_quality:[r.negative_prompt]}}) : r.negative_prompt || '';
    let steps=r.steps;
    if (spec.flowShift) args.push('--flow-shift',String(spec.flowShift));
    if (steps>=2 && components.some(c=>c.flag==='--high-noise-diffusion-model')) {
      // The CLI adds its high-noise steps to the regular stage. Keep the
      // total selected in the UI and apply Wan's published 8:10 ratio.
      const high=Math.max(1,Math.floor(steps*8/18));
      args.push('--high-noise-steps',String(high));
      steps-=high;
    }
    args.push('-p',positive,'-n',negative, '-W',String(video?r.inference_width:r.size),'-H',String(video?r.inference_height:r.size),
      '--steps',String(steps),'--cfg-scale',String(r.cfg),'--sampling-method','euler','-s',String(r.seed),'-o',raw);
    let nativeFrames;
    if (video) {
      const temporalStride=spec.temporalStride || (id==='ltx2' ? 8 : 4);
      nativeFrames=1+temporalStride*Math.ceil((r.frames-1)/temporalStride);
      args.push('--video-frames',String(nativeFrames),'--fps',String(r.fps));
    }
    if (id==='ltx25' && spec.hostWeightLimitGiB) {
      await require('./bounded-diffusion.cjs').runLtxVideo({components:convertedPaths,input,runtime:r,out,dir,
        engine,invoke,signal,limit:spec.hostWeightLimitGiB,frames:nativeFrames,output:raw});
    } else await invoke(engine,args,{cwd:out,signal});
    if (!video) return {name:'image.png',media_type:'image/png'};
    await invoke(bins.ffmpeg,['-v','error','-i',raw,'-map','0:v:0','-frames:v',String(r.frames),'-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart','video.mp4'],{cwd:out,signal});
    return {name:'video.mp4',media_type:'video/mp4'};
  } finally {await fs.rm(dir,{recursive:true,force:true});}
}
module.exports={runPackage,referenceText,languageFor,audioEngine,diffusionEngine};
