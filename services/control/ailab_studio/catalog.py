"""Local assets and conservative hardware-derived defaults; no heavy imports."""
import json
import platform
import subprocess
from pathlib import Path
import psutil


def hardware():
    result = {'os': platform.system(), 'arch': platform.machine(), 'memory_gb': round(psutil.virtual_memory().total / 1024**3, 1), 'gpus': [], 'device': 'cpu'}
    result.update(hostname=platform.node(), os_release=platform.release(), os_version=platform.version(),
                  cpu_name=platform.processor() or platform.machine(), cpu_physical_cores=psutil.cpu_count(logical=False),
                  cpu_logical_cores=psutil.cpu_count(logical=True), python_version=platform.python_version())
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
                result['cpu_name'] = winreg.QueryValueEx(key, 'ProcessorNameString')[0].strip()
        except OSError: pass
    try:
        p = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, creationflags=0x08000000 if platform.system() == 'Windows' else 0)
        if p.returncode == 0:
            for index, line in enumerate(p.stdout.strip().splitlines()):
                name, memory, driver = line.rsplit(',', 2)
                result['gpus'].append({'index': index, 'name': name.strip(), 'memory_gb': round(float(memory) / 1024, 1), 'driver_version':driver.strip()})
            if result['gpus']:
                result['device'] = 'cuda'
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':
        result['device'] = 'mps'
    return result


def storage_info(path):
    memory = psutil.virtual_memory()
    result = {'memory_available_gb':round(memory.available / 1024**3, 1)}
    try:
        disk = psutil.disk_usage(str(path))
        result.update(disk_total_gb=round(disk.total / 1024**3, 1), disk_free_gb=round(disk.free / 1024**3, 1))
    except OSError: pass
    return result


def local_path(raw):
    path = Path(raw).expanduser()
    if not path.is_absolute() or not path.exists():
        raise ValueError('请选择存在的本机绝对路径')
    return path.resolve()


def model_info(raw):
    path = local_path(raw)
    if path.is_file() and path.suffix.lower() == '.gguf':
        return {'path': str(path), 'name': path.stem, 'format': 'gguf', 'size_gb': round(path.stat().st_size / 1024**3, 2)}
    if not path.is_dir():
        raise ValueError('请选择 GGUF 文件或完整模型目录')
    if (path / 'modular_model_index.json').is_file():
        config = json.loads((path / 'modular_model_index.json').read_text(encoding='utf-8'))
        return {'path': str(path), 'name': path.name, 'format': 'diffusers', 'architecture': config.get('_class_name', '')}
    if (path / 'model_index.json').is_file():
        config = json.loads((path / 'model_index.json').read_text(encoding='utf-8'))
        return {'path': str(path), 'name': path.name, 'format': 'diffusers', 'architecture': config.get('_class_name', '')}
    config_path = path / 'config.json'
    if not config_path.is_file():
        raise ValueError('模型目录缺少 config.json 或 model_index.json')
    config = json.loads(config_path.read_text(encoding='utf-8'))
    weights = list(path.glob('*.safetensors'))
    if not weights:
        raise ValueError('模型目录中没有 Safetensors 权重')
    index = path / 'model.safetensors.index.json'
    if index.exists():
        for file in set(json.loads(index.read_text(encoding='utf-8')).get('weight_map', {}).values()):
            shard = (path / file).resolve()
            if not shard.is_relative_to(path) or not shard.is_file():
                raise ValueError('模型分片缺失或清单路径无效')
    return {'path': str(path), 'name': path.name, 'format': 'safetensors', 'architecture': config.get('model_type', ''),
            'context_length': config.get('max_position_embeddings', config.get('text_config', {}).get('max_position_embeddings', 4096)),
            'vision': 'vision_config' in config, 'quantized': bool(config.get('quantization_config')),
            'size_gb': round(sum(p.stat().st_size for p in weights) / 1024**3, 2)}


def scan(root, kind):
    path = local_path(root)
    if not path.is_dir():
        raise ValueError('资源根路径必须是文件夹')
    items = []
    # Bounded two-level discovery. A user can also paste a deeper exact path.
    candidates = [path, *sorted(path.iterdir())]
    for child in list(candidates[1:]):
        if child.is_dir() and not child.is_symlink():
            candidates.extend(sorted(child.iterdir())[:500])
    for child in candidates[:2000]:
        if child.is_symlink():
            continue
        if kind == 'models':
            try:
                items.append(model_info(str(child)))
            except (ValueError, OSError):
                continue
        elif child.is_file() and child.suffix.lower() in ('.json', '.jsonl', '.parquet'):
            items.append({'path': str(child), 'name': child.name, 'format': child.suffix[1:]})
        elif child.is_dir() and ((child / 'dataset_dict.json').exists() or (child / 'state.json').exists()):
            items.append({'path': str(child), 'name': child.name, 'format': 'hf-dataset'})
    return items


def recommend(raw, engine, host=None):
    host = host or hardware()
    model = model_info(raw)
    if engine == 'llama' and model['format'] != 'gguf':
        raise ValueError('llama.cpp 需要 GGUF 权重，请选择 GGUF 文件')
    if engine == 'vllm' and model['format'] != 'safetensors':
        raise ValueError('此 vLLM 入口需要完整 Safetensors 模型目录')
    if engine == 'diffusers' and model['format'] != 'diffusers':
        raise ValueError('Diffusers 需要带 model_index.json 的完整模型目录')
    memory = host['gpus'][0]['memory_gb'] if host['gpus'] else host['memory_gb'] * 0.5
    ceiling = 8192 if memory >= 24 else 4096 if memory >= 8 else 2048
    context = max(256, min(int(model.get('context_length') or 4096), ceiling))
    return {'model': model, 'config': {'device': host['device'], 'context_length': context,
            'max_tokens': min(512, context // 4), 'temperature': 0.7, 'top_k': 40, 'top_p': 0.95, 'gpu_layers': 0 if host['device'] == 'cpu' else -1,
            'gpu_memory_utilization': 0.75, 'tensor_parallel_size': 1},
            'notes': ['采样参数是通用起点；上下文按模型上限与设备内存保守建议，不保证任意模型都能装入。']}
