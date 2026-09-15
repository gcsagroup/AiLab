"""内置媒体二进制路由与探测身份；不把探测夹具作为模型运行证据。"""

import json
from pathlib import Path
import sys

import pytest

from test_control import rig


def executable(path, facts):
    path.write_text('#!' + str(Path(sys.executable).resolve()) + '\nimport json\nprint(' + repr(json.dumps(facts)) + ')\n')
    path.chmod(0o700)
    return path


def evidence():
    return {'python': '3.13.9', 'dependencies': {'torch': '2.14.0'}, 'device_ready': True, 'sources': {'worker.py': 'a' * 64}, 'runtime_manifest_sha256': 'b' * 64}


@pytest.mark.parametrize('kind,prefix', [('image', 'media'), ('video', 'media'), ('audio', 'audio')])
def test_bundled_worker_is_explicit_default_and_routes_fixed_modes(rig, tmp_path, kind, prefix):
    service = rig[1]
    binary = executable(tmp_path / ('ailab-' + prefix), evidence())
    setattr(service.settings, 'bundled_' + prefix + '_worker', binary)
    result = service.media.environment(kind)
    assert result['ready'] is True and result['execution_backend'] == 'bundled'
    assert result['identity']['bundled_worker'] == str(binary)
    snapshot, output = tmp_path / 'snapshot.json', tmp_path / 'out'
    command = service.media.command(snapshot, output, kind, preflight=True)
    assert command == [str(binary), '--mode', 'preflight', '--snapshot', str(snapshot), '--output-dir', str(output)]
    assert service.media.command(snapshot, output, kind)[1:3] == ['--mode', 'run']
    settings = service.get_settings()
    assert settings[prefix + '_execution_backend'] == 'bundled'
    assert settings['bundled_' + prefix + '_worker_available'] is True


@pytest.mark.parametrize('damage', ['device', 'sources', 'digest', 'dependencies', 'malformed'])
def test_incomplete_bundle_probe_does_not_claim_ready_or_fall_back(rig, tmp_path, damage):
    service = rig[1]
    facts = evidence()
    if damage == 'device': facts['device_ready'] = False
    elif damage == 'sources': facts['sources'] = {}
    elif damage == 'digest': facts['runtime_manifest_sha256'] = 'unverified'
    elif damage == 'dependencies': facts['dependencies'] = {}
    else: facts = 'bad-probe'
    binary = executable(tmp_path / 'ailab-audio', facts)
    service.settings.bundled_audio_worker = binary
    result = service.media.environment('audio')
    assert result['ready'] is False and result['execution_backend'] == 'bundled'
    assert service.media.command(tmp_path / 'snapshot', tmp_path / 'out', 'audio')[0] == str(binary)


def test_external_environment_selection_wins_even_if_invalid(rig, tmp_path):
    service = rig[1]
    binary = executable(tmp_path / 'ailab-audio', evidence())
    service.settings.bundled_audio_worker = binary
    selected = tmp_path / 'missing-python'
    service.settings.audio_python = selected
    assert service.media.bundled('audio') is None
    assert service.media.environment('audio')['ready'] is False
    assert service.media.command(tmp_path / 'snapshot', tmp_path / 'out', 'audio')[0] == str(selected)
    assert service.get_settings()['audio_execution_backend'] == 'external_python'


def test_bundle_change_invalidates_probe_and_null_restores_explicit_bundle(rig, tmp_path):
    client, service, *_ = rig
    binary = executable(tmp_path / 'ailab-audio', evidence())
    service.settings.bundled_audio_worker = binary
    first = service.media.environment('audio')
    facts = evidence(); facts['device_ready'] = False
    executable(binary, facts)
    second = service.media.environment('audio')
    assert second['digest'] != first['digest'] and second['ready'] is False
    service.settings.audio_python = Path(sys.executable)
    response = client.patch('/api/v1/settings', json={'expected_revision': 1, 'audio_python': None})
    assert response.status_code == 200 and response.json()['audio_execution_backend'] == 'bundled'
    assert service.settings.audio_python is None and service.media.cache == {}
