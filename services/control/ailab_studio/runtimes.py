"""Immutable uv environments. vLLM and Abliterix deliberately share one profile."""
import os
import json
import platform
import shutil
import sys
import time
from pathlib import Path

PROFILES = {
    'comfyui': {'name': 'ComfyUI 原生引擎', 'description': '分离主干 / 文本编码器 / VAE · 不转换权重', 'packages': ['imageio[ffmpeg]>=2.37,<3'], 'imports': ['torch', 'safetensors', 'imageio'], 'capabilities': ['t2i', 't2v', 'r2v']},
    'training': {'name': 'SFT 训练', 'description': '独立训练环境 · Transformers / PEFT',
                 'packages': ['torch>=2.7,<3', 'transformers>=5.20,<6', 'peft>=0.21,<1', 'accelerate>=1.10,<2', 'datasets>=4,<5', 'safetensors>=0.6,<1', 'compressed-tensors>=0.18,<1', 'bitsandbytes>=0.49,<1'],
                 'imports': ['torch', 'transformers', 'peft', 'datasets'], 'capabilities': ['sft']},
    'llama': {'name': 'llama.cpp', 'description': 'GGUF 本机推理 · 可选视觉投影模型',
              'packages': ['llama-cpp-python>=0.3.16,<0.4', 'pillow>=11,<13'],
              'imports': ['llama_cpp', 'PIL'], 'capabilities': ['chat']},
    'ablation': {'name': 'Abliterix · HF', 'description': '独立 HF 消融环境，不依赖 vLLM',
                 'packages': ['abliterix==1.12.2', 'pillow>=11,<13', 'tomlkit>=0.13,<1', 'compressed-tensors>=0.18,<1'],
                 'imports': ['abliterix', 'transformers', 'torch'], 'capabilities': ['ablation_hf']},
    'vllm': {'name': 'vLLM', 'description': '可选推理环境；安装后可用于 Abliterix 的 vLLM 后端',
             'packages': ['abliterix[vllm]==1.12.2', 'pillow>=11,<13', 'tomlkit>=0.13,<1'],
             'imports': ['vllm', 'abliterix', 'torch'], 'capabilities': ['chat', 'ablation']},
    'diffusers': {'name': 'Diffusers', 'description': '文生图 / 文生视频 / 参考图生视频',
                  'packages': ['torch>=2.7,<3', 'torchvision>=0.22,<1', 'diffusers>=0.39,<1', 'transformers>=4.56,<5', 'accelerate>=1.10,<2', 'safetensors>=0.6,<1', 'pillow>=11,<13', 'imageio[ffmpeg]>=2.37,<3', 'sentencepiece>=0.2,<1', 'protobuf>=5,<7'],
                  'imports': ['torch', 'torchvision', 'diffusers', 'imageio'], 'capabilities': ['t2i', 't2v', 'r2v']},
}


def interpreter(root):
    return Path(root) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def uv_command():
    if getattr(sys, 'frozen', False):
        binary = Path(sys._MEIPASS) / 'bin' / ('uv.exe' if os.name == 'nt' else 'uv')
        if not binary.is_file(): raise ValueError('安装包缺少 uv 安装器，请重新安装应用')
        return [str(binary)]
    import uv as uv_package
    uv = str(uv_package.find_uv_bin())
    if not Path(uv).is_file():
        raise ValueError('控制环境尚未安装 uv，请先运行控制后端依赖安装命令')
    return [uv]


class Runtimes:
    def __init__(self, studio):
        self.studio = studio
        self.root = studio.environment / 'runtimes'
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self):
        installed = {}
        for key in PROFILES:
            try: installed[key] = self.resolve(key)
            except ValueError: pass
        items = []
        for key, profile in PROFILES.items():
            unsupported = key == 'vllm' and platform.system() != 'Linux'
            items.append({'id': key, **profile, 'supported': not unsupported,
                          'reason': '此配置要求 Linux + NVIDIA；Windows 请在 WSL2 内运行后端。' if unsupported else '',
                          'installed': installed.get(key), 'state': 'ready' if key in installed else 'not_installed'})
        return items

    def resolve(self, key):
        if key not in PROFILES:
            raise ValueError('未知运行环境')
        active = self.root / key / 'active.json'
        if active.is_file(): value = json.loads(active.read_text(encoding='utf-8'))
        else:
            try: value = self.studio.store.get('runtime', key)
            except ValueError:
                raise ValueError(f"尚未安装 {PROFILES[key]['name']} 环境。请在“设置 → 环境管理”中安装；如已有环境，请将环境安装目录设为对应的 environment 文件夹。") from None
        if not interpreter(value['path']).is_file():
            raise ValueError('环境文件缺失，请重新安装环境')
        return value

    def install(self, key, accelerator):
        if key not in PROFILES:
            raise ValueError('未知运行环境')
        if key == 'vllm' and (platform.system() != 'Linux' or accelerator != 'cuda'):
            raise ValueError('vLLM + Abliterix 当前安装配置要求 Linux NVIDIA CUDA；可在 WSL2 中运行后端')
        if accelerator == 'metal' and platform.system() != 'Darwin':
            raise ValueError('Metal 运行环境仅可在 macOS 安装')
        if key != 'llama' and accelerator == 'cuda' and self.studio.hardware['device'] != 'cuda':
            raise ValueError('未检测到 NVIDIA GPU/驱动，请先检查设备')
        uv_command()
        return self.studio.launch('install', {'profile': key, 'accelerator': accelerator}, key, self._install)

    def _install(self, job, run):
        key = job['config']['profile']; accelerator = job['config']['accelerator']
        path = self.root / key / job['id']
        env = {**os.environ, 'UV_CACHE_DIR': str(self.studio.environment / 'cache'), 'UV_PYTHON_INSTALL_DIR': str(self.studio.environment / 'python'), 'HF_HOME': str(self.studio.environment / 'huggingface')}
        if key == 'llama':
            env['CMAKE_ARGS'] = {'cuda': '-DGGML_CUDA=on', 'metal': '-DGGML_METAL=on', 'cpu': '-DGGML_CUDA=off -DGGML_METAL=off'}[accelerator]
        run([*uv_command(), 'venv', '--python', '3.12', str(path)], env=env)
        packages = [*PROFILES[key]['packages'], 'psutil>=7,<8']
        args = [*uv_command(), 'pip', 'install', '--python', str(interpreter(path)), *packages]
        if key in ('training', 'diffusers', 'ablation', 'comfyui') and accelerator == 'cuda':
            args += ['--extra-index-url', 'https://download.pytorch.org/whl/cu128', '--index-strategy', 'unsafe-best-match']
        elif key in ('training', 'diffusers', 'ablation', 'comfyui') and accelerator == 'cpu' and platform.system() != 'Darwin':
            args += ['--extra-index-url', 'https://download.pytorch.org/whl/cpu', '--index-strategy', 'unsafe-best-match']
        if key == 'llama':
            if accelerator == 'cpu':
                args += ['--extra-index-url', 'https://abetlen.github.io/llama-cpp-python/whl/cpu', '--index-strategy', 'unsafe-best-match', '--only-binary', 'llama-cpp-python']
            else: args += ['--no-binary', 'llama-cpp-python']
        if key == 'comfyui':
            run([str(interpreter(path)), str(Path(__file__).parent / 'workers' / 'prepare_comfy.py'), str(path), str(self.studio.environment / 'cache')], env=env)
            args += ['-r', str(path / 'requirements.comfy.txt')]
        run(args, env=env)
        # Imports and accelerator health are checked before changing the active version.
        probe = '; '.join('import ' + name for name in PROFILES[key]['imports'])
        if key != 'llama':
            probe += "; import torch; print('Torch',torch.__version__); "
            if accelerator == 'cuda':
                probe += "assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name(0))"
            elif accelerator == 'metal':
                probe += "assert torch.backends.mps.is_available(), 'MPS unavailable'"
        elif accelerator != 'cpu':
            probe += "; assert llama_cpp.llama_supports_gpu_offload(), 'GPU offload unavailable'"
        run([str(interpreter(path)), '-c', probe], env=env)
        frozen = run([*uv_command(), '--quiet', 'pip', 'freeze', '--python', str(interpreter(path))], env=env, collect=True)
        (path / 'requirements.resolved.txt').write_text(frozen, encoding='utf-8')
        value = {'id': key, 'path': str(path), 'version': job['id'], 'accelerator': accelerator,
                 'created_at': time.time(), 'resolved': frozen, 'previous': None}
        try:
            value['previous'] = self.resolve(key)['path']
        except ValueError:
            pass
        with self.studio.mutex:
            if self.studio.store.get('job', job['id'])['state'] == 'cancelling':
                raise InterruptedError('安装已取消，旧环境保持不变')
            self.studio.store.put('runtime', value)
            active = self.root / key / 'active.json'
            temporary = active.with_suffix('.' + job['id'] + '.tmp')
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary, active)
        return {'runtime': key, 'path': str(path), 'packages': frozen}
