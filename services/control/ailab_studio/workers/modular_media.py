"""Anima adapter for locally converted Diffusers modular checkpoints."""
from pathlib import Path

from common import device, emit, finish


def anima(config):
    import torch
    from diffusers import AnimaModularPipeline, ClassifierFreeGuidance, FlowMatchEulerDiscreteScheduler

    if config['workflow'] != 't2i':
        raise ValueError('Anima 仅支持文生图')
    selected = device(config['device'])
    if selected == 'cpu':
        torch.set_num_threads(min(torch.get_num_threads(), 8))
    # Keep Anima's original BF16 weights on CPU to avoid doubling RAM use.
    dtype = torch.float16 if selected == 'cuda' else torch.bfloat16 if selected == 'cpu' else torch.float32
    pipeline = AnimaModularPipeline.from_pretrained(config['model'], local_files_only=True)
    def quiet(block):
        if hasattr(block, 'set_progress_bar_config'):
            block.set_progress_bar_config(disable=True)
        for child in getattr(block, 'sub_blocks', {}).values():
            quiet(child)
    quiet(pipeline.blocks)
    component_dtypes = {'default': dtype, 'vae': torch.float32} if selected == 'cpu' else dtype
    pipeline.load_components(torch_dtype=component_dtypes, local_files_only=True,
                             pretrained_model_name_or_path=config['model'])
    pipeline.update_components(guider=ClassifierFreeGuidance(guidance_scale=config['guidance_scale']))
    if not isinstance(pipeline.scheduler, FlowMatchEulerDiscreteScheduler):
        raise ValueError('Anima 模型需要 FlowMatch Euler 调度器')
    offload = 'disabled'
    if selected == 'cuda' and config.get('cpu_offload', True):
        from accelerate import cpu_offload
        # Sequential hooks also fit transformers larger than the GPU memory.
        for component in pipeline.components.values():
            if isinstance(component, torch.nn.Module):
                cpu_offload(component, execution_device=torch.device('cuda'))
        offload = 'sequential_cpu_offload'
    else:
        pipeline.to(selected)
    original_step = pipeline.scheduler.step
    completed = 0

    def step(*args, **kwargs):
        nonlocal completed
        result = original_step(*args, **kwargs)
        completed += 1
        emit('progress', step=completed, total=config['steps'])
        return result

    pipeline.scheduler.step = step
    emit('model_state', phase='generating', text='模型已加载，正在生成')
    images = pipeline(prompt=config['prompt'], negative_prompt=config['negative_prompt'],
                      width=config['width'], height=config['height'], num_inference_steps=config['steps'],
                      generator=torch.Generator(device='cuda' if selected == 'cuda' else 'cpu').manual_seed(config['seed']),
                      output='images')
    file = Path(config['output_dir']) / 'image.png'
    images[0].save(file)
    finish(config, {'file': str(file), 'workflow': 't2i', 'seed': config['seed'],
                    'pipeline': type(pipeline).__name__, 'scheduler': type(pipeline.scheduler).__name__,
                    'device': selected, 'cpu_offload': offload, 'steps': completed})
