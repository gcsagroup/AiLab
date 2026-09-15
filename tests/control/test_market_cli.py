"""真实控制服务入口的受控来源登记边界，不连接任何远端地址。"""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]


def command(root, origin=None):
    args = [sys.executable, '-B', '-m', 'ailab_control', '--data-dir', str(root)]
    if origin is not None:
        args += ['--market-fixture-origin', origin]
    return args


@pytest.mark.parametrize('origin', [None, 'http://127.0.0.1:51871'])
def test_real_cli_only_registers_explicit_fixed_fixture(tmp_path, origin):
    environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'services/control')}
    process = subprocess.Popen(command(tmp_path / 'library', origin), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(10), '服务未报告启动结果'
            connection = json.loads(process.stdout.readline())
        request = urllib.request.Request(f"http://127.0.0.1:{connection['port']}/api/v1/market/sources", headers={'Authorization': 'Bearer ' + connection['token']})
        with urllib.request.urlopen(request, timeout=5) as response:
            sources = json.load(response)['items']
        assert [item['provider_id'] for item in sources] == ([] if origin is None else ['fixture-provider'])
        assert not sources or all(item['source_label'] == '受控测试来源' for item in sources)
        assert all(item['origin'] == origin for item in sources)
    finally:
        process.terminate()
        process.communicate(timeout=15)
    assert process.returncode == 0


@pytest.mark.parametrize('origin', ['https://127.0.0.1:8181', 'http://localhost:8181', 'http://10.0.0.1:8181', 'http://127.0.0.1:8181/path', 'http://u:p@127.0.0.1:8181', 'http://127.0.0.1:08181', 'http://127.0.0.1:0', 'http://127.0.0.1:8181?x=1'])
def test_real_cli_rejects_noncanonical_or_nonloopback_origin(tmp_path, origin):
    result = subprocess.run(command(tmp_path / 'library', origin), env={**os.environ, 'PYTHONPATH': str(ROOT / 'services/control')}, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert result.stdout == ''
    assert '首期来源只允许已登记的固定 127.0.0.1 端口' in result.stderr
