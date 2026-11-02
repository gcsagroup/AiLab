"""Native split-weight inference. No Diffusers conversion or weight export."""
import sys
from pathlib import Path
from common import device, emit, finish, image


def validate_architecture(architecture, actual, workflow):
    allowed = {'anima': {'Anima'}, 'sd15': {'SD15'}, 'sdxl': {'SDXL'},
               'flux': {'Flux', 'FluxSchnell'}, 'wan21': {'WAN21_I2V'} if workflow == 'r2v' else {'WAN21_T2V'}}
    if actual not in allowed.get(architecture, set()):
        raise ValueError(f'所选架构/工作流与主干不匹配：{architecture}/{workflow}，实际为 {actual}；不会转换权重')


def condition_values(conditioning, values):
    return [[tensor, {**metadata, **values}] for tensor, metadata in conditioning]


def run(config):
    import torch
    import numpy as np
    from PIL import Image
    selected = device(config['device'])
    source = Path(config['runtime_path']) / 'comfyui'
    if not (source / 'comfy' / 'sd.py').is_file():
        raise ValueError('请先安装 ComfyUI 原生引擎环境')
    sys.path.insert(0, str(source))
    sys.argv = ['ailab-comfy', '--disable-dynamic-vram', '--fp32-vae']
    if selected == 'cpu': sys.argv += ['--cpu']
    elif selected == 'cuda': sys.argv += ['--lowvram' if config.get('cpu_offload', True) else '--highvram']
    import comfy.options
    comfy.options.enable_args_parsing()
    import comfy.sd
    import comfy.sample
    import comfy.utils
    torch.set_num_threads(min(torch.get_num_threads(), 8))
    architecture = config['comfy_architecture']
    options = {'dtype': torch.bfloat16} if selected == 'cpu' and architecture in ('anima', 'flux', 'wan21') else {}
    model = comfy.sd.load_diffusion_model(config['model'], model_options=options, disable_dynamic=True)
    if model is None: raise ValueError('原生引擎无法识别所选主干权重；不会转换格式')
    validate_architecture(architecture, type(model.model.model_config).__name__, config['workflow'])
    clip_type = {'flux': comfy.sd.CLIPType.FLUX, 'wan21': comfy.sd.CLIPType.WAN}.get(architecture, comfy.sd.CLIPType.STABLE_DIFFUSION)
    encoders = [config['text_encoder']]
    if architecture in ('sdxl', 'flux'): encoders.append(config['text_encoder_2'])
    clip = comfy.sd.load_clip(encoders, clip_type=clip_type, disable_dynamic=True)
    vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(config['vae'], safe_load=True), dtype=torch.float32)
    if vae.first_stage_model is None: raise ValueError('无法识别 VAE 权重')
    with torch.inference_mode():
        positive = clip.encode_from_tokens_scheduled(clip.tokenize(config['prompt']))
        negative = clip.encode_from_tokens_scheduled(clip.tokenize(config['negative_prompt']))
        if architecture == 'flux': positive = condition_values(positive, {'guidance': config['guidance_scale']})
        latent_format = model.get_model_object('latent_format')
        h, w = config['height'], config['width']
        scale = latent_format.spacial_downscale_ratio
        if h % scale or w % scale: raise ValueError(f'此主干的宽高必须为 {scale} 的倍数')
        shape = [1, latent_format.latent_channels]
        if latent_format.latent_dimensions == 3:
            shape += [1 if config['workflow'] == 't2i' else (config['frames'] - 1) // 4 + 1]
        latent = torch.zeros([*shape, h // scale, w // scale])
        if config['workflow'] == 'r2v':
            import comfy.clip_vision
            reference = Image.open(config['image_path']).convert('RGB') if config.get('image_path') else image(config['image'])
            pixels = torch.from_numpy(np.asarray(reference.resize((w, h))).copy()).float().unsqueeze(0) / 255
            video = torch.full((config['frames'], h, w, 3), 0.5)
            video[:1] = pixels
            encoded = vae.encode(video)
            mask = torch.ones((1, 1, latent.shape[2], encoded.shape[-2], encoded.shape[-1]))
            mask[:, :, :1] = 0
            vision = comfy.clip_vision.load(config['clip_vision'])
            if vision is None: raise ValueError('无法识别 CLIP Vision 权重')
            values = {'concat_latent_image': encoded, 'concat_mask': mask, 'clip_vision_output': vision.encode_image(pixels)}
            positive, negative = condition_values(positive, values), condition_values(negative, values)
        emit('model_state', phase='generating', text='原始组件已加载，正在生成')
        def callback(step, x0, x, total): emit('progress', step=step + 1, total=total)
        scheduler = 'normal' if architecture in ('sd15', 'sdxl') else 'simple'
        samples = comfy.sample.sample(model, comfy.sample.prepare_noise(latent, config['seed']), config['steps'],
            1.0 if architecture == 'flux' else config['guidance_scale'], 'euler', scheduler,
            positive, negative, latent, callback=callback, disable_pbar=True, seed=config['seed'])
        emit('status', text='正在解码生成素材')
        decoded = vae.decode(samples).cpu().float().clamp(0, 1)
        # Video VAEs retain a batch axis, including Anima's single-frame output.
        if decoded.ndim == 5 and decoded.shape[0] == 1: decoded = decoded[0]
        if decoded.ndim != 4 or decoded.shape[-1] != 3:
            raise ValueError(f'VAE 输出形状不受支持：{tuple(decoded.shape)}')
        frames = (decoded.numpy() * 255).round().astype(np.uint8)
        folder = Path(config['output_dir'])
        if config['workflow'] == 't2i':
            file = folder / 'image.png'; Image.fromarray(frames[0]).save(file)
        else:
            import imageio.v2 as imageio
            file = folder / 'video.mp4'
            imageio.mimwrite(str(file), frames, fps=config['fps'], codec='libx264', macro_block_size=1)
    finish(config, {'file': str(file), 'workflow': config['workflow'], 'seed': config['seed'],
                    'engine': 'comfyui', 'architecture': architecture, 'device': selected,
                    'scheduler': scheduler, 'sampler': 'euler', 'media_format': 'comfyui',
                    'cpu_offload': selected == 'cuda' and config.get('cpu_offload', True),
                    'components': {key: config.get(key) for key in ('model', 'text_encoder', 'text_encoder_2', 'vae', 'clip_vision')}})
