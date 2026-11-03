"""Resident model process. Only the controller writes the private request mailbox."""
import asyncio
import inspect
import json
import os
from pathlib import Path
import sys
import time
from common import device, image
from inference import messages_for
from reasoning import ReasoningStream

os.environ['HF_HUB_OFFLINE'] = '1'
folder = Path(sys.argv[1])
job_id = ''


def emit(kind, **values):
    print('@@AILAB ' + json.dumps({'type': kind, 'job_id': job_id, **values}, ensure_ascii=False), flush=True)


class Session:
    def __init__(self, config):
        self.config = config; self.engine = config['engine']; self.loop = None
        if self.engine == 'llama':
            import llama_cpp
            from llama_cpp import Llama
            if config['device'] in ('cuda', 'mps') and not llama_cpp.llama_supports_gpu_offload():
                raise ValueError('当前 llama.cpp 环境没有 GPU 加速支持')
            handler = None
            if config['vision_handler'] != 'none':
                from llama_cpp import llama_chat_format
                name = {'llava15': 'Llava15ChatHandler', 'llava16': 'Llava16ChatHandler', 'moondream': 'MoondreamChatHandler'}[config['vision_handler']]
                handler = getattr(llama_chat_format, name)(clip_model_path=config['mmproj'])
            self.model = Llama(model_path=config['model'], n_ctx=config['context_length'],
                               n_gpu_layers=0 if config['device'] == 'cpu' else config['gpu_layers'], chat_handler=handler, verbose=False)
        else:
            if config['device'] not in ('auto', 'cuda'): raise ValueError('此 vLLM 运行配置要求 CUDA')
            device('cuda')
            from vllm.engine.arg_utils import AsyncEngineArgs
            from vllm.engine.async_llm_engine import AsyncLLMEngine
            self.loop = asyncio.new_event_loop(); asyncio.set_event_loop(self.loop)
            args = AsyncEngineArgs(model=config['model'], trust_remote_code=False, max_model_len=config['context_length'],
                gpu_memory_utilization=config['gpu_memory_utilization'], tensor_parallel_size=config['tensor_parallel_size'],
                cpu_offload_gb=config.get('cpu_offload_gb', 4) if config.get('cpu_offload', True) else 0)
            self.model = AsyncLLMEngine.from_engine_args(args)

    def thinking_prefix(self, messages):
        # Many templates already put <think> at the end of the prompt, outside generated tokens.
        try:
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter
            template = self.model.metadata.get('tokenizer.chat_template', '')
            if not template: return False
            formatter = Jinja2ChatFormatter(template=template,
                eos_token=self.model._model.token_get_text(self.model.token_eos()),
                bos_token=self.model._model.token_get_text(self.model.token_bos()))
            return formatter(messages=messages).prompt.rstrip().endswith(('<think>', '<analysis>'))
        except Exception:
            # Optional template introspection must not prevent normal inference.
            return False

    def generate(self, config):
        messages = messages_for(config)
        stream = ReasoningStream(lambda text, channel: emit('token', text=text, channel=channel),
                                 thinking=self.thinking_prefix(messages) if self.engine == 'llama' else False)
        if self.engine == 'llama':
            finish_reason = None
            for chunk in self.model.create_chat_completion(messages=messages, stream=True, max_tokens=config['max_tokens'],
                    temperature=config['temperature'], top_p=config['top_p'], top_k=config['top_k'], seed=config['seed']):
                choice = chunk['choices'][0]; delta = choice.get('delta', {})
                stream.write(delta.get('reasoning_content') or delta.get('reasoning') or '', reasoning=True)
                stream.write(delta.get('content') or '')
                finish_reason = choice.get('finish_reason') or finish_reason
        else:
            finish_reason = self.loop.run_until_complete(self.generate_vllm(config, stream))
        stream.finish()
        return {'text': stream.text, 'reasoning': stream.reasoning, 'finish_reason': finish_reason,
                'engine': self.engine, 'model': config['model']}

    async def generate_vllm(self, config, stream):
        from vllm import SamplingParams
        tokenizer = self.model.get_tokenizer()
        if inspect.isawaitable(tokenizer): tokenizer = await tokenizer
        messages = []; images = []
        for item in config['messages']:
            content = item['content']
            if item.get('image'):
                images.append(image(item['image']))
                content = [{'type': 'image'}, {'type': 'text', 'text': content}]
            messages.append({'role': item['role'], 'content': content})
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        stream.thinking = prompt.rstrip().endswith(('<think>', '<analysis>'))
        inputs = {'prompt': prompt}
        if images: inputs['multi_modal_data'] = {'image': images}
        sampling = SamplingParams(max_tokens=config['max_tokens'], temperature=config['temperature'], top_k=config['top_k'] or -1,
                                  top_p=config['top_p'], seed=config['seed'], skip_special_tokens=False)
        previous = ''; reason = None
        async for result in self.model.generate(inputs, sampling, request_id=job_id):
            if not result.outputs: continue
            current = result.outputs[0]
            if not current.text.startswith(previous): raise ValueError('推理流返回了非追加文本')
            stream.write(current.text[len(previous):]); previous = current.text; reason = current.finish_reason or reason
        return reason


def main():
    global job_id
    session = None; previous = ''
    while True:
        request = folder / 'request.json'
        if not request.exists(): time.sleep(.05); continue
        payload = json.loads(request.read_text(encoding='utf-8'))
        if payload['id'] == previous: time.sleep(.05); continue
        previous = job_id = payload['id']; config = payload['config']
        try:
            if session is None:
                emit('model_state', phase='loading', text='正在加载模型')
                session = Session(config)
            emit('model_state', phase='loaded', text='模型已加载')
            if config.get('action') == 'load': result = {'model': config['model'], 'engine': config['engine'], 'loaded': True}
            else:
                emit('model_state', phase='generating', text='正在生成')
                result = session.generate(config)
            emit('result', **result)
            emit('model_state', phase='loaded', text='模型保留在内存中')
            emit('completed')
        except Exception as exc:
            emit('error', text=str(exc)); emit('command_failed'); return


if __name__ == '__main__': main()
