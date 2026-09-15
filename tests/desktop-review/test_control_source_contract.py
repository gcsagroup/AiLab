"""空工作目录读取 NVIDIA 纯参数合同与源码身份，不导入计算依赖。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]


def test_control_contract_runs_from_empty_directory_without_device_probe(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/desktop/control_entry.py'), '--verify-source-contract'],
                            cwd=tmp_path, env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': f'{ROOT / "services/control"}:{ROOT}'},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    contract = json.loads(result.stdout)
    assert contract['model_execution'] is False and contract['device_probe'] is False
    names = ('adapters/nvidia_text/adapter.py', 'workers/nvidia_worker.py', 'adapters/mlx_text/recipe.py',
             'adapters/mlx_text/generation.py', 'adapters/mlx_text/evaluation.py')
    sources = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    assert all(contract['sources'][name] == value for name, value in sources.items())
    assert contract['source_code_digest'] == hashlib.sha256(json.dumps(sources, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def test_staging_contains_nvidia_contract_worker_and_fixed_dependency_list():
    spec = importlib.util.spec_from_file_location('stage_contract_test', ROOT / 'scripts/desktop/stage_control.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    directory = ROOT / '.artifacts/desktop'; directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='contract-stage-test-', dir=directory) as temporary:
        staged = Path(temporary)
        module.stage(ROOT, staged)
        manifest = json.loads((staged / 'build-manifest.json').read_text())
        for name in ('adapters/nvidia_text/adapter.py', 'adapters/nvidia_text/requirements.txt', 'workers/nvidia_worker.py'):
            expected = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            assert manifest['files'][name] == expected
            assert hashlib.sha256((staged / name).read_bytes()).hexdigest() == expected
