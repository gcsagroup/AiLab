"""Native engine adapters. Inputs are local; history is never silently truncated."""
import inspect
from pathlib import Path
from common import device, emit, finish, image


def messages_for(config):
    messages = []
    for item in config['messages']:
        content = item['content']
        if item.get('image'):
            content = [{'type': 'text', 'text': content}, {'type': 'image_url', 'image_url': {'url': item['image']}}]
        messages.append({'role': item['role'], 'content': content})
    return messages


def llama(config):
    import llama_cpp
    from llama_cpp import Llama
    if config['device'] in ('cuda', 'mps') and not llama_cpp.llama_supports_gpu_offload():
        raise ValueError('当前 llama.cpp 环境没有 GPU 加速支持，请重新安装对应环境或选择 CPU')
    handler = None
    if config['vision_handler'] != 'none':
        from llama_cpp import llama_chat_format
        name = {'llava15': 'Llava15ChatHandler', 'llava16': 'Llava16ChatHandler', 'moondream': 'MoondreamChatHandler'}[config['vision_handler']]
        handler = getattr(llama_chat_format, name)(clip_model_path=config['mmproj'])
    model = Llama(model_path=config['model'], n_ctx=config['context_length'],
                  n_gpu_layers=0 if config['device'] == 'cpu' else config['gpu_layers'], seed=config['seed'], chat_handler=handler, verbose=False)
    emit('model_state', phase='generating', text='模型已加载，正在生成')
    text = ''; finish_reason = None
    for chunk in model.create_chat_completion(messages=messages_for(config), max_tokens=config['max_tokens'],
            temperature=config['temperature'], top_k=config['top_k'], top_p=config['top_p'], stream=True):
        choice = chunk['choices'][0]; token = choice.get('delta', {}).get('content') or ''
        if token: text += token; emit('token', text=token)
        finish_reason = choice.get('finish_reason') or finish_reason
    finish(config, {'text': text, 'finish_reason': finish_reason, 'engine': 'llama', 'model': config['model']})


def vllm(config):
    from vllm import LLM, SamplingParams
    if config['device'] not in ('auto', 'cuda'): raise ValueError('此 vLLM 运行配置要求 CUDA')
    device('cuda')
    model = LLM(model=config['model'], trust_remote_code=False, max_model_len=config['context_length'],
                gpu_memory_utilization=config['gpu_memory_utilization'], tensor_parallel_size=config['tensor_parallel_size'],
                cpu_offload_gb=config.get('cpu_offload_gb', 4) if config.get('cpu_offload', True) else 0)
    emit('model_state', phase='generating', text='模型已加载，正在生成')
    sampling = SamplingParams(max_tokens=config['max_tokens'], temperature=config['temperature'], top_k=config['top_k'] or -1, top_p=config['top_p'], seed=config['seed'])
    messages = messages_for(config)
    # Engine owns template/multimodal preprocessing and rejects context overflow.
    outputs = model.chat(messages, sampling_params=sampling, use_tqdm=False)
    completion = outputs[0].outputs[0]
    emit('token', text=completion.text)
    finish(config, {'text': completion.text, 'finish_reason': completion.finish_reason, 'engine': 'vllm', 'model': config['model'],
                    'prompt_tokens': len(outputs[0].prompt_token_ids or []), 'output_tokens': len(completion.token_ids)})


def place_pipeline(pipeline, selected, cpu_offload):
    if cpu_offload and selected == 'cuda':
        pipeline.enable_model_cpu_offload()
        emit('status', text='CPU offload 已启用：按需将模型组件移入 GPU')
        return 'model_cpu_offload'
    pipeline.to(selected)
    if cpu_offload:
        emit('status', text='当前设备不使用 CUDA CPU offload，按所选设备运行')
    return 'disabled'


def media(config):
    if config.get('media_format') == 'comfyui':
        from comfy_media import run
        return run(config)
    import json
    if (Path(config['model']) / 'modular_model_index.json').is_file():
        index = json.loads((Path(config['model']) / 'modular_model_index.json').read_text(encoding='utf-8'))
        if index.get('_class_name') != 'AnimaModularPipeline':
            raise ValueError('当前仅支持 Anima 类型的模块化 Diffusers 模型')
        from modular_media import anima
        return anima(config)
    import torch
    from diffusers import AutoPipelineForText2Image, DiffusionPipeline
    from diffusers.utils import export_to_video
    selected = device(config['device'])
    dtype = torch.float16 if selected == 'cuda' else torch.float32
    loader = AutoPipelineForText2Image if config['workflow'] == 't2i' else DiffusionPipeline
    pipeline = loader.from_pretrained(config['model'], torch_dtype=dtype, local_files_only=True, trust_remote_code=False)
    pipeline.set_progress_bar_config(disable=True)
    if config.get('sampler', 'euler') == 'euler':
        from diffusers import EulerDiscreteScheduler, FlowMatchEulerDiscreteScheduler
        scheduler = pipeline.scheduler
        if isinstance(scheduler, FlowMatchEulerDiscreteScheduler):
            pipeline.scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler.config)
        elif 'FlowMatch' in type(scheduler).__name__:
            pipeline.scheduler = FlowMatchEulerDiscreteScheduler.from_config(scheduler.config)
        elif hasattr(scheduler, 'alphas_cumprod'):
            pipeline.scheduler = EulerDiscreteScheduler.from_config(scheduler.config)
        else:
            raise ValueError('此模型暂不支持 Euler 适配，请选择模型默认采样器')
    offload = place_pipeline(pipeline, selected, config.get('cpu_offload', True))
    parameters = inspect.signature(pipeline.__call__).parameters
    generator = torch.Generator(device='cuda' if selected == 'cuda' else 'cpu').manual_seed(config['seed'])
    values = {'prompt': config['prompt'], 'negative_prompt': config['negative_prompt'], 'num_inference_steps': config['steps'],
              'width': config['width'], 'height': config['height'], 'guidance_scale': config['guidance_scale'], 'generator': generator}
    if config['workflow'] == 'r2v':
        if 'image' not in parameters: raise ValueError('所选视频 Pipeline 不接受参考图 image，请选择图生视频模型')
        if config.get('image_path'):
            from PIL import Image
            with Image.open(config['image_path']) as reference:
                if reference.width * reference.height > 20000000: raise ValueError('参考图片像素过大')
                values['image'] = reference.convert('RGB')
        else: values['image'] = image(config['image'])
    if config['workflow'] != 't2i':
        if 'num_frames' not in parameters: raise ValueError('所选 Pipeline 不提供 num_frames 视频输出')
        values['num_frames'] = config['frames']
    def callback(pipe, step, timestep, tensors):
        emit('progress', step=step + 1, total=config['steps']); return tensors
    if 'callback_on_step_end' in parameters: values['callback_on_step_end'] = callback
    else: emit('status', text='此 Pipeline 不提供逐步回调，生成期间保留运行状态')
    if config['workflow'] == 't2v' and 'prompt' not in parameters: raise ValueError('此视频模型不接受文本提示，请选择 T2V 模型')
    ignored = [key for key in values if key not in parameters]
    if ignored:
        emit('status', text='此 Pipeline 不支持以下参数，将使用其原生行为：' + ', '.join(ignored))
    kwargs = {key: value for key, value in values.items() if key in parameters}
    emit('model_state', phase='generating', text='模型已加载，正在生成')
    result = pipeline(**kwargs)
    folder = Path(config['output_dir'])
    if config['workflow'] == 't2i':
        file = folder / 'image.png'; result.images[0].save(file)
    else:
        if not hasattr(result, 'frames'): raise ValueError('Pipeline 未返回视频帧')
        file = folder / 'video.mp4'; export_to_video(result.frames[0], str(file), fps=config['fps'])
    finish(config, {'file': str(file), 'workflow': config['workflow'], 'seed': config['seed'], 'pipeline': type(pipeline).__name__, 'device': selected, 'cpu_offload': offload, 'scheduler': type(pipeline.scheduler).__name__, 'ignored_parameters': ignored})
