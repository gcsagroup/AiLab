"""Architecture-only inspection. Never imports model-owned code or opens weights."""
import json
import os
import subprocess
from pathlib import Path
from .catalog import local_path
from .runtimes import interpreter


def check_model(studio, raw):
    folder = local_path(raw)
    config = json.loads((folder / 'config.json').read_text(encoding='utf-8'))
    architectures = config.get('architectures', [])
    auto_map = config.get('auto_map', {})
    missing = []
    for value in auto_map.values():
        if isinstance(value, str):
            name = value.split('--')[-1].split('.')[0] + '.py'
            if not (folder / name).is_file(): missing.append(name)
    results = []
    for backend, runtime in [('hf', 'ablation'), ('vllm', 'vllm')]:
        item = {'backend': backend, 'status': 'not_installed', 'detail': '环境未安装'}
        try: installed = studio.runtimes.resolve(runtime)
        except ValueError:
            results.append(item); continue
        try:
            run = subprocess.run([str(interpreter(installed['path'])), str(Path(__file__).parent / 'workers' / 'compatibility.py'),
                                  backend, json.dumps({'model_type': config.get('model_type'), 'architectures': architectures})],
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
                                 env={**os.environ, 'PYTHONUTF8': '1', 'HF_HUB_OFFLINE': '1'},
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            lines = [x[8:] for x in run.stdout.splitlines() if x.startswith('@@AILAB ')]
            if run.returncode or not lines: raise ValueError(run.stderr[-600:] or '环境检查失败')
            item.update(json.loads(lines[-1]))
            if backend == 'hf' and item['status'] == 'unsupported' and auto_map:
                item.update(status='custom_code_required', detail='需要模型自定义代码和 trust_remote_code；静态检查不能确认代码兼容性。')
                if missing: item.update(status='unsupported', detail='缺少自定义代码：' + ', '.join(sorted(set(missing))))
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            item.update(status='unknown', detail=str(exc))
        results.append(item)
    return {'architectures': architectures, 'model_type': config.get('model_type'), 'quantization': config.get('quantization_config'),
            'backends': results, 'note': '仅检查当前环境的架构注册表；未加载权重。量化格式、设备内存和消融层结构仍需运行验证。'}
