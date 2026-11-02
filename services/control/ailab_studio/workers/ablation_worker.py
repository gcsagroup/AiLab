"""Launch the real Abliterix CLI and require exported weights on success."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from common import finish


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    folder = Path(config['output_dir'])
    executable = Path(sys.executable).parent / ('abliterix.exe' if os.name == 'nt' else 'abliterix')
    if not executable.is_file(): raise RuntimeError('所选运行环境中缺少 Abliterix CLI，请重新安装')
    # Validate against the actual installed schema before launching expensive computation.
    import tomllib
    from abliterix.settings import AbliterixConfig
    document = tomllib.loads((folder / 'abliterix.toml').read_text(encoding='utf-8'))
    # BaseSettings reads sys.argv even during model_validate; hide our request-file argument.
    sys.argv = [sys.argv[0], '--config', str(folder / 'abliterix.toml')]
    AbliterixConfig.model_validate(document)
    if document.get('model', {}).get('backend', 'hf') == 'hf':
        from model_compat import install
        install(config['model'], document.get('model', {}).get('trust_remote_code', False))
    from abliterix.cli import main as abliterix_main
    try: abliterix_main()
    except SystemExit as exc:
        if exc.code not in (None, 0): raise RuntimeError(f'Abliterix 退出码 {exc.code}') from exc
    weights = list((folder / 'model').glob('*.safetensors'))
    if not weights: raise RuntimeError('Abliterix 已结束但没有导出 Safetensors 权重，不能标记成功')
    manifest = []
    for file in weights:
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''): digest.update(chunk)
        manifest.append({'name': file.name, 'size': file.stat().st_size, 'sha256': digest.hexdigest()})
    finish(config, {'model_dir': str(folder / 'model'), 'config_file': str(folder / 'abliterix.toml'), 'weights': manifest,
                    'reproduction_dir': str(folder / 'model' / 'reproduce')})


if __name__ == '__main__': main()
