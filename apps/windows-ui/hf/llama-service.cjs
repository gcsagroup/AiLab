'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { trialThreads } = require('./trial-devices.cjs');
const { spawn } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');
const { createInterface } = require('node:readline');

function useService(info, extra = {}, media, runtime = {}) {
  if (runtime.cpu_working_set_mib && info.arch!=='rnd1') return true;
  if (info.pipeline === 'llama-qwen4exp-ple' && !extra.draft && !extra.recovery_lora) return false;
  if (extra.ple_table) return true;
  return (
    !!extra.draft ||
    !!info.legacyInklingLoop ||
    !!info.legacyGraniteShared ||
    (info.kind==='text' && !!info.legacyQ4) ||
    Number.isSafeInteger(info.chameleonSeparator) ||
    !!info.legacyZayaLayers ||
    !!info.defaultExaoneRouter ||
    !!info.minimaxInterval ||
    (!!media && info.kind === 'text') ||
    ['llama-chat', 'llama-embedding', 'llama-rerank', 'llama-decision', 'llama-tts', 'llama-ocr', 'llama-hibiki'].includes(info.pipeline) ||
    (info.kind==='text' && Object.entries(extra).some(([key,file])=>
      /^shard_\d{5}$/.test(key) && require('./gguf-metadata.cjs').metadata(file).legacyQ4))
  );
}
// A graph can expose both decision scores and a language head (e.g. Granite Switch).
function inputModel(info, prompt) {
  if (
    info.kind !== 'text' ||
    !(info.decision || info.arch === 'graniteswitch') ||
    info.pipeline === 'llama-decision' ||
    !prompt.trimStart().startsWith('{')
  )
    return info;
  try {
    const request = JSON.parse(prompt);
    if (
      request &&
      typeof request === 'object' &&
      Object.hasOwn(request, 'state') &&
      Object.hasOwn(request, 'questions')
    )
      return { ...info, pipeline: 'llama-decision' };
  } catch {}
  return info;
}
function structuredInput(prompt, pipeline) {
  if (pipeline === 'llama-rerank') {
    const [query, ...documents] = prompt
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!query || !documents.length) throw Error('重排需要首行查询，之后每行一份候选文本。');
    return { query, documents, return_documents: true };
  }
  if (pipeline === 'llama-decision') {
    let body;
    try {
      body = JSON.parse(prompt);
    } catch {}
    if (
      !body ||
      !Object.hasOwn(body, 'state') ||
      !body.questions ||
      typeof body.questions !== 'object' ||
      Array.isArray(body.questions)
    )
      throw Error('决策输入需要含 state 和 questions 的 JSON 对象。');
    if (
      body.files !== undefined &&
      (!Array.isArray(body.files) || body.files.some((id) => typeof id !== 'string' || !id.trim()))
    )
      throw Error('files 中需要填写项目素材编号或名称。');
    return { state: body.state, questions: body.questions, files: body.files || [] };
  }
}
// Muse may stream its raw recipient protocol through the generic chat parser.
// Buffer only an incomplete header or delimiter across server events.
function museAnswerStream(onThought = () => {}) {
  const start='<|start|>assistant', message='<|message|>', boundaries=['<|eom|>','<|eot|>',start];
  let pending='',state='header',sawPrivate=false;
  return {
    get sawPrivate() {return sawPrivate;},
    push(chunk,final=false) {
      pending+=chunk;
      let visible='';
      while (pending) {
        if (state==='header') {
          const head=pending.trimStart();
          if (head.startsWith(start)) {pending=head.slice(start.length);continue;}
          if (!final && (!head || start.startsWith(head) || 'to='.startsWith(head))) break;
          if (head.startsWith('to=')) {
            const end=head.indexOf(message);
            if (end<0) {
              if (head.length>256) throw Error('Muse 返回了无效的收件人标记。');
              if (final) pending='';
              break;
            }
            const recipient=head.slice(3,end);
            state=recipient==='user' ? 'public' : recipient==='self' ? 'thought' : 'private';
            sawPrivate ||= state!=='public';
            pending=head.slice(end+message.length);
            continue;
          }
          state='public'; // Upstream already parsed the recipient.
        }
        let end=pending.length, marker='';
        for (const token of boundaries) {
          const at=pending.indexOf(token);
          if (at>=0 && at<end) {end=at;marker=token;}
        }
        if (!marker && !final) {
          const tail=pending.lastIndexOf('<');
          if (tail>=0 && boundaries.some(token=>token.startsWith(pending.slice(tail)))) end=tail;
        }
        if (state==='public') visible+=pending.slice(0,end);
        else if (state==='thought' && end) onThought(pending.slice(0,end));
        pending=pending.slice(end+marker.length);
        if (!marker) break;
        state='header';
      }
      return visible;
    },
  };
}
function flags(file, info, r, extra, key) {
  const ctx = Math.min(r.context_limit || 4096, info.trainedContext || 4096);
  const whole = ['llama-embedding', 'llama-rerank', 'llama-decision'].includes(info.pipeline);
  const chunk = whole ? ctx : Math.min(ctx, r.prefill_step_size || 2048);
  const args = [
    '--model',
    file,
    '--host',
    '127.0.0.1',
    '--port',
    '0',
    '--api-key',
    key,
    '--no-ui',
    '--offline',
    '--no-warmup',
    '--perf',
    '--parallel',
    '1',
    '--ctx-size',
    String(ctx),
    '--batch-size',
    String(chunk),
    '--ubatch-size',
    String(chunk),
    '--device',
    r.device_id === 'cpu' ? 'none' : r.device_id,
    '--gpu-layers',
    r.device_id === 'cpu' ? '0' : 'all',
    '--fit',
    'off',
  ];
  if (r.device_id === 'cpu') {
    const threads = String(trialThreads(r));
    args.push('--no-mmproj-offload', '--threads', threads, '--threads-batch', threads);
    if (extra.draft) args.push('--spec-draft-threads', threads, '--spec-draft-threads-batch', threads);
  }
  if (info.pipeline === 'llama-hibiki') args.push('--seed', String(r.seed));
  const compactCpu=r.device_id==='cpu' && (r.language_weight_conversion || r.cpu_no_repack ||
    (extra.ple_table && extra.recovery_lora));
  if (compactCpu) args.push('--no-repack');
  if (compactCpu || extra.ple_table) args.push('--load-mode','mmap');
  if (r.cpu_working_set_mib) args.push('--lazy-mode','on');
  if (info.apertusChatTemplate && info.pipeline === 'llama-chat')
    args.push('--chat-template-file', path.join(__dirname, 'apertus-chat.jinja'), '--skip-chat-parsing');
  if (info.legacyQwenChat) args.push('--chat-template','chatml');
  if (info.legacyCogChat) args.push('--chat-template-file', path.join(__dirname,'cogvlm-chat.jinja'),'--skip-chat-parsing');
  if (info.defaultExaoneRouter) args.push('--override-kv','exaone-moe.expert_gating_func=int:2');
  if (info.minimaxInterval) args.push('--override-kv','minimax-01.full_attention_interval=int:'+info.minimaxInterval);
  const csvPath = value => value.includes(',') ? '"'+value.replaceAll('"','""')+'"' : value;
  if (extra.ple_table) args.push('--ple',csvPath(extra.ple_table),'--lazy-mode','on');
  if (extra.recovery_lora) args.push('--lora',csvPath(extra.recovery_lora),
    '--presence-penalty','1.5','--repeat-last-n',String(Math.min(ctx,20480)));
  if (extra.projector) {
    args.push('--mmproj', extra.projector);
    if (r.device_id?.startsWith('CUDA')) args.push('--mmproj-device', r.device_id);
  }
  if (extra.draft)
    args.push(
      '--slots',
      '--spec-draft-model',
      extra.draft,
      '--spec-type',
      info.specType,
      '--spec-draft-device',
      r.device_id === 'cpu' ? 'none' : r.device_id,
      '--spec-draft-ngl',
      r.device_id === 'cpu' ? '0' : 'all',
    );
  if (info.pipeline === 'llama-embedding') args.push('--embedding');
  if (info.pipeline === 'llama-rerank') args.push('--reranking');
  const cache = { q4: 'q4_0', q8: 'q8_0', f16: 'f16' }[r.kv_precision];
  if (cache) {
    args.push('--cache-type-k', cache, '--cache-type-v', cache);
    if (extra.draft) args.push('--spec-draft-type-k', cache, '--spec-draft-type-v', cache);
    if (cache !== 'f16') args.push('--flash-attn', 'on');
  }
  return args;
}
async function withServer(exe, args, key, env, signal, run) {
  signal?.throwIfAborted();
  const child = spawn(exe, args, {
    cwd: path.dirname(exe),
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const lifetime = new AbortController();
  let address, mappedLimit,
    tail = '',
    failure;
  const aborted = () => lifetime.abort(signal.reason);
  signal?.addEventListener('abort', aborted, { once: true });
  const closed = new Promise((resolve) => {
    child.on('error', (e) => {
      failure = e;
      lifetime.abort(e);
    });
    child.once('close', () => {
      failure ||= Error(tail.trim().slice(-1300) || 'llama.cpp 服务已退出。');
      lifetime.abort(failure);
      resolve();
    });
  });
  for (const stream of [child.stdout, child.stderr])
    createInterface({ input: stream }).on('line', (line) => {
      const m = /listening on (?:http:\/\/)?127\.0\.0\.1:(\d+)/i.exec(line);
      const limit = /^AiLab mapped CPU service resident limit (\d+) MiB$/.exec(line);
      if (limit) mappedLimit=Number(limit[1]);
      if (m) address = 'http://127.0.0.1:' + m[1];
      tail = (tail + '\n' + line.replaceAll(key, '***')).slice(-2400);
    });
  try {
    const startup = AbortSignal.any([lifetime.signal, AbortSignal.timeout(240000)]);
    while (true) {
      startup.throwIfAborted();
      if (address) {
        const ready = await fetch(address + '/health', {
          signal: startup,
          headers: { Authorization: 'Bearer ' + key },
        });
        await ready.body?.cancel();
        if (ready.ok) break;
        if (ready.status !== 503) throw Error('llama.cpp 健康检查失败 ' + ready.status);
      }
      await delay(80, null, { signal: startup });
    }
    if (args.includes('--spec-draft-model')) {
      const state = await fetch(address + '/slots', {
        headers: { Authorization: 'Bearer ' + key },
        signal: lifetime.signal,
      });
      if (!state.ok || !(await state.json()).some((slot) => slot.speculative === true))
        throw Error('主模型与推测解码头未能启用联合推理。');
    }
    const post = async (route, body) => {
      const response = await fetch(address + route, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: lifetime.signal,
      });
      if (!response.ok) {
        const message = await response.text();
        throw Error('llama.cpp ' + route + ' ' + response.status + ' ' + message.slice(-900));
      }
      return response;
    };
    return await run(post,mappedLimit, {address,key,signal:lifetime.signal});
  } catch (e) {
    throw failure || (signal?.aborted ? Error('运行已停止。') : e);
  } finally {
    signal?.removeEventListener('abort', aborted);
    child.kill();
    await closed;
  }
}
async function runService({ exe, env, file, info, r, extra, media, decisionMedia = [], prompt, out, signal, event = () => {}, resident, preload }) {
  if (info.normalizeNfc) prompt=prompt.normalize('NFC');
  if (info.legacyCogChat && !media && extra.projector) extra={...extra,projector:undefined};
  const key = randomBytes(24).toString('hex');
  const args = flags(file, info, r, extra, key);
  if (r.cpu_working_set_mib) {
    exe=path.join(path.dirname(exe),'ailab-gguf.exe');
    args.unshift('--bounded-service',String(r.cpu_working_set_floor_mib),String(r.cpu_working_set_mib));
  }
  const data = preload ? null : structuredInput(prompt, info.pipeline);
  const startup = performance.now();
  const run = async (post,mappedLimit, connection) => {
    event('timing', { service_start_ms: performance.now() - startup });
    if (info.pipeline==='llama-hibiki')
      return require('./hibiki.cjs').translate(connection,media,out);
    let part;
    if (media) {
      const buf = await fs.readFile(media);
      part =
        buf.toString('ascii', 0, 4) === 'RIFF'
          ? { type: 'input_audio', input_audio: { data: buf.toString('base64'), format: 'wav' } }
          : { type: 'image_url', image_url: { url: 'data:image/png;base64,' + buf.toString('base64') } };
    }
    const content = part ? [part, { type: 'text', text: prompt }] : prompt;
    let text;
    if (info.pipeline === 'llama-tts') {
      const res = await post('/tts', {
        input: prompt,
        seed: r.seed,
        speed: r.speed ?? 1,
        ...(part?.input_audio ? { speaker_ref_b64: part.input_audio.data } : {}),
      });
      const wav = Buffer.from(await res.arrayBuffer());
      if (
        wav.length <= 44 ||
        wav.toString('ascii', 0, 4) !== 'RIFF' ||
        wav.toString('ascii', 8, 12) !== 'WAVE'
      )
        throw Error('语音执行器返回了无效的 WAV。');
      await fs.writeFile(path.join(out, 'result.wav'), wav);
      return { name: 'result.wav', media_type: 'audio/wav' };
    } else if (info.pipeline === 'llama-embedding') {
      const result = await (await post('/embeddings', { input: part ? { content } : prompt })).json();
      if (!result[0]?.embedding?.length) throw Error('模型未返回向量。');
      text = JSON.stringify(result);
    } else if (info.pipeline === 'llama-rerank') {
      if (part) data.query = { content: [part, { type: 'text', text: data.query }] };
      const result = await (await post('/v1/rerank', data)).json();
      if (!result.results?.length) throw Error('模型未返回重排结果。');
      text = JSON.stringify(result.results, null, 2);
    } else if (info.pipeline === 'llama-decision') {
      data.files = [];
      if (part) data.files.push(part.image_url?.url || 'data:audio/wav;base64,' + part.input_audio.data);
      for (const material of decisionMedia) {
        const bytes = await fs.readFile(material.path);
        data.files.push(
          'data:' +
            (material.kind === 'audio' ? 'audio/wav' : 'image/png') +
            ';base64,' +
            bytes.toString('base64'),
        );
      }
      text = JSON.stringify(await (await post('/v1/systemone', data)).json(), null, 2);
    } else {
      let chat = info.chat || !!part;
      let body = chat ? { messages: [{ role: 'user', content }] } : { prompt };
      if (info.legacyQwenChat) body.messages.unshift({role:'system',content:'You are a helpful assistant.'});
      let directTokenCount;
      let stops=r.stop;
      const harmony=info.arch==='gpt-oss' || info.harmonyChannels;
      const channelChat=info.thinking && (info.museRecipients || harmony || ['inkling2','inkling2_loop'].includes(info.arch));
      if (!chat && Number.isSafeInteger(info.chameleonSeparator)) {
        // ChameleonProcessor uses a vocabulary separator to end the user turn.
        // Tokenize the user's text independently of that control token.
        const encoded=await (await post('/tokenize',{content:prompt,add_special:true,parse_special:false})).json();
        if (!Array.isArray(encoded.tokens)) throw Error('Chameleon 分词器未返回输入词元。');
        body={prompt:[...encoded.tokens,info.chameleonSeparator]};
        directTokenCount=body.prompt.length;
      } else if (chat && (channelChat || info.reasoningPrefix) && r.thinking==='disabled') {
        // These templates have separate prefixes for reasoning and public
        // answers. Preselect the answer prefix when thinking is disabled.
        const template=info.museRecipients ? {...body,chat_template_kwargs:{reasoning_strength:'low'}} :
          {...body,reasoning_effort:harmony?'low':'none'};
        const rendered=await (await post('/apply-template',template)).json();
        if (typeof rendered.prompt!=='string') throw Error('模型未返回可用的聊天模板。');
        let suffix;
        if (info.museRecipients && rendered.prompt.endsWith('<|start|>assistant')) suffix=' to=user<|message|>';
        if (harmony && rendered.prompt.endsWith('<|start|>assistant')) suffix='<|channel|>final<|message|>';
        if (channelChat && !harmony && rendered.prompt.endsWith('<|end_message|>')) suffix='<|message_model|><|content_text|>';
        if (channelChat && !harmony && rendered.prompt.endsWith('<|message_model|>')) suffix='<|content_text|>';
        if (info.reasoningPrefix==='open-chatml' && rendered.prompt.trimEnd().endsWith('<|im_start|>assistant\n<think>'))
          suffix='\n</think>\n\n';
        if ((info.reasoningPrefix==='chatml' && rendered.prompt.trimEnd().endsWith('<|im_start|>assistant')) ||
            (info.reasoningPrefix==='deepseek' && rendered.prompt.endsWith('<｜Assistant｜>')) ||
            (info.reasoningPrefix==='flint' && rendered.prompt.trimEnd().endsWith('<|assistant|>')))
          suffix='<think>\n\n</think>\n\n';
        if (!suffix) throw Error('聊天模板末尾缺少预期的助手或消息结束标记。');
        const direct=(harmony ? rendered.prompt.trimEnd() : rendered.prompt)+suffix;
        const encoded=await (await post('/tokenize',{content:part?suffix:direct,add_special:!part,parse_special:true})).json();
        if (!Array.isArray(encoded.tokens) || !encoded.tokens.length) throw Error('聊天模板分词失败。');
        directTokenCount=encoded.tokens.length;
        if (part) {
          const counted=await (await post('/v1/chat/completions/input_tokens',template)).json();
          directTokenCount+=counted.input_tokens;
          const base64=part.input_audio?.data || part.image_url.url.split(',')[1];
          body={prompt:{prompt_string:direct,multimodal_data:[base64]}};
        } else body={prompt:encoded.tokens};
        if (info.museRecipients) stops=[...new Set([...(r.stop || []),'<|eom|>','<|eot|>'])];
        else if (info.reasoningPrefix) stops=[...new Set([...(r.stop || []),'<think>','</think>'])];
        else if (!harmony) stops=[...new Set([...(r.stop || []),'<|end_message|>','<|content_model_end_sampling|>'])];
        chat=false;
      } else if (chat && info.museRecipients && r.thinking==='enabled')
        body.chat_template_kwargs={reasoning_strength:'high'};
      else if (chat && r.thinking && r.thinking !== 'default')
        body.chat_template_kwargs = { enable_thinking: r.thinking === 'enabled' };
      if (chat && r.thinking === 'disabled') body.reasoning_effort = 'none';
      else if (chat && info.mistralEffort && r.thinking==='enabled') body.reasoning_effort='high';
      else if (chat && channelChat) {
        if (r.thinking==='enabled') body.reasoning_effort='medium';
        else if (r.max_tokens<128) body.reasoning_effort='low';
        body.reasoning_budget_tokens=Math.max(0,r.max_tokens-Math.min(24,Math.ceil(r.max_tokens/3)));
      }
      if (chat && info.arch==='lfm3' && info.thinking && r.thinking==='disabled') {
        // LFM3's disabled template already closes <think>. Some checkpoints
        // emit a second closing marker and repeat the answer after it.
        body.reasoning_budget_tokens=0;
        stops=[...new Set([...(stops || []),'</think>'])];
      }
      if (chat && info.mistralEffort && r.thinking!=='default')
        body.chat_template_kwargs={reasoning_effort:r.thinking==='enabled'?'high':'none'};
      const n = chat
        ? (await (await post('/v1/chat/completions/input_tokens', body)).json()).input_tokens
        : directTokenCount ?? (
            await (
              await post('/tokenize', { content: prompt, add_special: true, parse_special: false })
            ).json()
          ).tokens.length;
      if (
        !Number.isInteger(n) ||
        n + r.max_tokens > Math.min(r.context_limit, info.trainedContext || r.context_limit)
      )
        throw Error('输入和生成长度超过上下文预算。');
      // With a projector, b12648's OpenAI completion handler requires a
      // string. Its native route accepts both token IDs and image data.
      const native = directTokenCount!==undefined && !!extra.projector;
      const route = chat ? '/v1/chat/completions' : native ? '/completion' : '/v1/completions';
      const res = await post(route, {
        ...body,
        stream: true,
        ...(!native ? { stream_options: { include_usage: true } } : {}),
        temperature: r.temperature,
        top_p: r.top_p,
        top_k: extra.recovery_lora ? 20 : 0,
        min_p: 0,
        seed: r.seed,
        ...(native ? {n_predict:r.max_tokens} : {max_tokens:r.max_tokens}),
        stop: stops,
        reasoning_format: chat && (info.thinking || r.thinking === 'disabled' || info.arch==='gpt-oss') ? 'deepseek' : 'none',
      });
      text = '';
      let finished = false, reasoning = false, firstToken = false;
      const metrics = { prompt_tokens: n, ...(mappedLimit ? {mapped_working_set_mib:mappedLimit} : {}) };
      let bufferedThought = '';
      function receiveThought(fragment) {
        if (!fragment || r.thinking === 'disabled') return;
        if (r.stream) event('reasoning', { text: fragment });
        else bufferedThought += fragment;
      }
      const recipientReader=info.museRecipients ? museAnswerStream(receiveThought) : null;
      const lines = createInterface({
        input: require('node:stream').Readable.fromWeb(res.body),
        crlfDelay: Infinity,
      });
      for await (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (raw === '[DONE]') break;
        const payload = JSON.parse(raw);
        if (payload.error) throw Error(payload.error.message);
        const timings = payload.timings;
        if (timings) {
          if (Number.isFinite(timings.prompt_ms)) metrics.prefill_ms = timings.prompt_ms;
          if (Number.isInteger(timings.prompt_n)) metrics.prefill_tokens = timings.prompt_n;
          if (Number.isFinite(timings.predicted_ms)) metrics.decode_ms = timings.predicted_ms;
          if (Number.isInteger(timings.predicted_n)) metrics.decode_tokens = metrics.completion_tokens = timings.predicted_n;
        }
        if (Number.isInteger(payload.usage?.completion_tokens)) metrics.completion_tokens = payload.usage.completion_tokens;
        if (native && Number.isInteger(payload.tokens_predicted)) metrics.completion_tokens = payload.tokens_predicted;
        const choice = native ? {text:payload.content,finish_reason:payload.stop ?
          (payload.stop_type==='limit' ? 'length' : 'stop') : null} : payload.choices?.[0];
        if (!choice) continue;
        reasoning ||= !!choice.delta?.reasoning_content;
        const rawToken = choice.delta?.content ?? choice.text ?? '';
        if (!firstToken && (rawToken || choice.delta?.reasoning_content)) {
          event('first_token', {});
          firstToken = true;
        }
        receiveThought(choice.delta?.reasoning_content);
        const token = recipientReader ? recipientReader.push(rawToken,!!choice.finish_reason) : rawToken;
        text += token;
        if (r.stream && token) event('token', { text: token });
        if (choice.finish_reason) {
          finished = true;
          metrics.finish_reason = choice.finish_reason;
        }
      }
      if (bufferedThought) event('reasoning', { text: bufferedThought });
      if (!finished) throw Error('llama.cpp 流式输出中断。');
      event('metrics', metrics);
      if (!text.trim() && (reasoning || recipientReader?.sawPrivate)) throw Error('模型已生成思考内容，尚未输出最终回答。请增加最大输出 token。');
    }
    await fs.writeFile(path.join(out, 'result.txt'), text);
    return { name: 'result.txt', media_type: 'text/plain', text };
  };
  if (!resident) return withServer(exe,args,key,env,signal,run);
  const identity=JSON.stringify([exe,...args.map(arg=>arg===key?'':arg)]);
  const handle=await resident.connect(identity,(lifetime,ready)=>withServer(exe,args,key,env,lifetime,async (...handle)=>{
    const lost=handle[2].signal;
    await Promise.race([ready(handle),new Promise(resolve=>lost.addEventListener('abort',resolve,{once:true}))]);
  }),signal);
  if (!preload) {
    signal?.throwIfAborted();
    const cancel=()=>{void resident.stop();};
    signal?.addEventListener('abort',cancel,{once:true});
    try { return await run(...handle); }
    finally { signal?.removeEventListener('abort',cancel); }
  }
}
module.exports = { inputModel, useService, runService, structuredInput, flags, museAnswerStream };
