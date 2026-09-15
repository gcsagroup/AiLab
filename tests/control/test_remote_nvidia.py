"""正式草稿、默认目标与 CUDA 阻断，不用 CPU 测试冒充 NVIDIA 验收。"""

import pytest

from test_control import rig, post, setup_task
from test_remote_transfers import remote_rig, executions


def test_project_default_applies_only_to_new_text_drafts_and_is_isolated(remote_rig):
    client, service, server, project, target, *_ = remote_rig
    before = post(client, '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': '原本机草稿'})
    state = client.get(f"/api/v1/projects/{project['id']}/execution-default").json()
    changed = post(client, f"/projects/{project['id']}/execution-default", {'execution_target_id': target['id'], 'expected_revision': state['revision']})
    after = post(client, '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': '新远端草稿'})
    assert after['draft']['execution_target_id'] == target['id']
    assert after['draft']['runtime']['engine'] == 'transformers' and after['draft']['runtime']['precision'] == 'bfloat16'
    assert client.get(f"/api/v1/tasks/{before['id']}").json()['draft']['runtime']['engine'] == 'mlx'
    media = post(client, '/tasks', {'project_id': project['id'], 'kind': 'audio', 'operation': 'generate', 'name': '媒体仍按已登记组合'})
    assert media['draft']['runtime']['engine'] == 'kokoro' and not media['draft'].get('execution_target_id')
    another = post(client, '/projects', {'name': '另一项目'})
    rejected = client.post(f"/api/v1/projects/{another['id']}/execution-default", json={'execution_target_id': target['id'], 'expected_revision': 1})
    assert rejected.status_code == 403
    post(client, f"/projects/{project['id']}/execution-default", {'execution_target_id': None, 'expected_revision': changed['revision']})
    assert client.get(f"/api/v1/tasks/{after['id']}").json()['draft']['execution_target_id'] == target['id']


def test_nvidia_public_preflight_uses_real_remote_probe_and_never_uploads_when_blocked(remote_rig):
    client, service, server, project, target, *_ = remote_rig
    task = post(client, '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': 'NVIDIA 环境阻断'})
    draft = {**task['draft'], 'execution_target_id': target['id'], 'input': {'prompt': '说明验证范围。'},
             'runtime': {'engine': 'transformers', 'device_id': 'cuda:0', 'precision': 'bfloat16', 'max_tokens': 16, 'temperature': 0.0, 'top_p': 1.0, 'seed': 0}}
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'draft': draft, 'expected_revision': 1})
    assert response.status_code == 200, response.text
    task = response.json()
    check = post(client, f"/tasks/{task['id']}/preflight", {'draft_revision': task['draft_revision']})
    assert check['can_submit'] is False
    assert check['environment']['engine'] == 'transformers'
    assert check['environment']['execution_target_id'] == target['id']
    assert check['environment']['ready'] is False
    assert any(item['code'] in {'NVIDIA_LINUX_REQUIRED', 'CUDA_UNAVAILABLE', 'ENVIRONMENT_VERSION_MISMATCH'} for item in check['blocking'])
    result = client.post(f"/api/v1/tasks/{task['id']}/attempts", json={'preflight_id': check['id'], 'expected_revision': task['draft_revision']}, headers={'Idempotency-Key': 'blocked'})
    assert result.status_code == 409 and result.json()['error']['code'] == 'PREFLIGHT_BLOCKED'
    assert executions(server) == []
    assert list((server.data / 'blobs').iterdir()) == []


@pytest.mark.parametrize('changes', [{'kv_precision': 'q4'}, {'prefill_step_size': 512}, {'max_tokens': 513}, {'precision': 'float32'}, {'stop': ['重复', '重复']}])
def test_nvidia_draft_rejects_unsupported_runtime_without_silent_mapping(remote_rig, changes):
    client, _, _, project, target, *_ = remote_rig
    task = post(client, '/tasks', {'project_id': project['id'], 'kind': 'text', 'operation': 'generate', 'name': '参数边界'})
    draft = {**task['draft'], 'execution_target_id': target['id'], 'runtime': {'engine': 'transformers', 'device_id': 'cuda:0', 'precision': 'bfloat16', 'max_tokens': 16, **changes}}
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'draft': draft, 'expected_revision': 1})
    assert response.status_code == 422
