"""固定分片核验的缺失、截断与等长损坏；不访问网络。"""
import hashlib
import json
import sys
from pathlib import Path

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text import prepare_model


@pytest.mark.parametrize('damage', [None, 'missing', 'truncated', 'same_size_corruption'])
def test_verify_only_checks_every_pinned_shard(tmp_path, monkeypatch, capsys, damage):
    weights = {'first.safetensors': b'first', 'last.safetensors': b'last'}
    for name, data in weights.items(): (tmp_path / name).write_bytes(data)
    variant = {'repo': 'fixture/offline', 'revision': 'fixed', 'files': list(weights),
               'weights': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in weights.items()}}
    monkeypatch.setattr(prepare_model, 'VARIANTS', {'fixture': variant})
    monkeypatch.setattr(sys, 'argv', ['prepare_model', '--variant', 'fixture', '--model-dir', str(tmp_path), '--verify-only'])
    target = tmp_path / 'last.safetensors'
    if damage == 'missing': target.unlink()
    elif damage == 'truncated': target.write_bytes(b'las')
    elif damage == 'same_size_corruption': target.write_bytes(b'LAST')
    if damage:
        with pytest.raises((ValueError, FileNotFoundError)): prepare_model.main()
        assert not capsys.readouterr().out
    else:
        prepare_model.main(); result = json.loads(capsys.readouterr().out)
        assert result['verified'] and len(result['files']) == 2
