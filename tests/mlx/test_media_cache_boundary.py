"""未开放媒体/跨请求缓存的真实入口拒绝矩阵；不加载模型或构造缓存。"""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test_inference_worker import frozen_snapshot


CASES = [
    ('media-a', 'input', 'media', [{'sha256': 'a' * 64}]),
    ('media-b', 'input', 'media', [{'sha256': 'b' * 64}]),
    ('media-ab', 'input', 'media', [{'sha256': 'a' * 64}, {'sha256': 'b' * 64}]),
    ('media-ba', 'input', 'media', [{'sha256': 'b' * 64}, {'sha256': 'a' * 64}]),
    ('processor-a', 'input', 'processor', {'id': 'same-processor', 'revision': 'a'}),
    ('processor-b', 'input', 'processor', {'id': 'same-processor', 'revision': 'b'}),
    ('preprocess-224', 'input', 'preprocess', {'resize': [224, 224]}),
    ('preprocess-384', 'input', 'preprocess', {'resize': [384, 384]}),
    ('prefix-reuse', 'runtime', 'prefix_cache', {'mode': 'reuse', 'key': 'same-text'}),
    ('media-reuse', 'runtime', 'media_cache', {'mode': 'reuse', 'key': 'same-text'}),
]


@pytest.fixture
def unopened_runtime(monkeypatch):
    """真实入口仍运行；只将禁止到达的第三方加载/计算入口替换为计数拒绝桩。"""
    import workers.mlx_worker as worker
    calls = []

    def forbidden(name):
        def call(*args, **kwargs):
            calls.append(name)
            raise AssertionError('未开放请求不得到达：' + name)
        return call

    core = ModuleType('mlx.core'); core.gpu = 'forbidden-gpu'
    core.set_default_device = forbidden('device'); core.random = SimpleNamespace(seed=forbidden('seed'))
    mlx = ModuleType('mlx'); mlx.core = core
    lm = ModuleType('mlx_lm'); lm.load = forbidden('model-load'); lm.stream_generate = forbidden('generate')
    utils = ModuleType('mlx_lm.utils'); utils.load_tokenizer = forbidden('tokenizer-load'); lm.utils = utils
    for name, module in [('mlx', mlx), ('mlx.core', core), ('mlx_lm', lm), ('mlx_lm.utils', utils)]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(worker, 'run_generate', forbidden('worker-generate'))
    monkeypatch.setattr(worker, 'initial_cache_summary', forbidden('cache'))
    monkeypatch.setattr(worker, 'watch_controller', lambda: None)
    monkeypatch.setattr(worker.signal, 'signal', lambda *_: None)
    monkeypatch.setattr(worker.os, 'environ', dict(os.environ))
    monkeypatch.setattr(subprocess, 'Popen', forbidden('process'))
    monkeypatch.setattr(socket, 'create_connection', forbidden('network'))
    return calls


@pytest.mark.parametrize('case,section,field,value', CASES, ids=[item[0] for item in CASES])
@pytest.mark.parametrize('entry', ['validate_snapshot', 'preflight_main', 'worker_main'])
def test_media_and_reuse_requests_rejected_before_loading(tmp_path, monkeypatch, capsys, unopened_runtime, entry, case, section, field, value):
    import workers.mlx_worker as worker
    from adapters.mlx_text import preflight
    snapshot = frozen_snapshot(tmp_path)
    snapshot['input']['prompt'] = '同一文字输入'
    snapshot[section][field] = copy.deepcopy(value)
    # 若主入口忽略字段，会继续进入加载；这个已存在的身份不能掩盖拒绝原因。
    snapshot['tokenization_recipe_digest'] = 'c' * 64
    expected = 'UNSUPPORTED_INPUT' if section == 'input' else 'UNSUPPORTED_PARAMETER'
    output = tmp_path / 'output'
    before = copy.deepcopy(snapshot)
    model_before = {p.name: p.read_bytes() for p in (tmp_path / 'model').iterdir()}
    if entry == 'validate_snapshot':
        with pytest.raises(worker.WorkerError) as error:
            worker.validate_snapshot(snapshot, output)
        assert error.value.code == expected
    else:
        path = tmp_path / 'snapshot.json'; path.write_text(json.dumps(snapshot))
        monkeypatch.setattr(sys, 'argv', ['entry', '--snapshot', str(path), '--output-dir', str(output)])
        if entry == 'preflight_main':
            assert preflight.main() == 1
            result = json.loads(capsys.readouterr().out)
            assert result['can_submit'] is False and [item['code'] for item in result['blocking']] == [expected]
        else:
            events = []
            monkeypatch.setattr(worker, 'emit', lambda kind, **payload: events.append({'type': kind, **payload}))
            assert worker.main() == 1
            assert len(events) == 1 and events[0]['type'] == 'error' and events[0]['code'] == expected
    assert snapshot == before
    assert {p.name: p.read_bytes() for p in (tmp_path / 'model').iterdir()} == model_before
    assert unopened_runtime == [] and not output.exists()
