"""图片适配器保存的来源与参数边界；小夹具不作为模型训练证据。"""

import json
from pathlib import Path
import struct

import pytest

from test_control import rig, post
from ailab_control.assets import file_hash
from ailab_control.media import DEFAULTS
from ailab_control.storage import digest


def trained(rig, damage=None):
    client, service, source, _ = rig
    project = post(client, '/projects', {'name': '图片训练来源合同'})
    model_dir = source / '固定基座'; model_dir.mkdir()
    (model_dir / 'manifest.json').write_text('{"fixture":true}')
    model_manifest = [{'path': 'manifest.json', 'size': (model_dir / 'manifest.json').stat().st_size, 'sha256': file_hash(model_dir / 'manifest.json')}]
    model = service.resource('model', project['id'], name='仅验证保存合同的基座', version_id='version-fixture', manifest=model_manifest, manifest_digest=digest(model_manifest), storage_path=str(model_dir), model_config={}, format='safetensors')
    with service.store.transaction(): service.store.put('model', model)
    task = post(client, '/tasks', {'project_id': project['id'], 'name': '完整产物合同夹具', 'kind': 'image', 'operation': 'train'})
    dataset_manifest = [{'path': 'dataset.json', 'size': 1, 'sha256': 'd' * 64}]
    runtime = dict(DEFAULTS[('image', 'train')])
    snapshot = {'kind': 'image', 'operation': 'train', 'runtime': runtime, 'model_id': model['id'], 'model_version_id': model['version_id'], 'model_manifest': model_manifest, 'model_manifest_digest': model['manifest_digest'], 'dataset_manifest': dataset_manifest, 'dataset_manifest_digest': digest(dataset_manifest), 'media_recipe_digest': 'e' * 64}
    attempt = service.resource('attempt', project['id'], task_id=task['id'], state='finalizing', state_version=1, snapshot=snapshot, snapshot_digest=digest(snapshot), compute_outcome='succeeded', collection_state='not_started', collection_version=0, last_event_sequence=0, terminal_reason=None)
    output = service.root / 'runs' / attempt['id'] / 'output'; result = output / 'result'; result.mkdir(parents=True)
    header = json.dumps({'fixture': {'dtype': 'F32', 'shape': [1], 'data_offsets': [0, 4]}}).encode()
    weight = result / 'pytorch_lora_weights.safetensors'; weight.write_bytes(struct.pack('<Q', len(header)) + header + struct.pack('<f', 1))
    report = {'model_manifest_sha256': model_manifest[0]['sha256'], 'dataset_sha256': 'd' * 64, 'adapter_sha256': file_hash(weight), 'frozen_parameter_sha256_before': 'f' * 64, 'frozen_parameter_sha256_after': 'f' * 64, 'size': 512, 'steps': 12, 'seed': 0, 'rank': 4, 'alpha': 4, 'learning_rate': 0.0001, 'losses': [{'step': step, 'loss': 1 / step} for step in range(1, 13)]}
    effective = {'media_recipe_digest': snapshot['media_recipe_digest'], 'source_model_unchanged': True}
    if damage == 'base': report['model_manifest_sha256'] = 'b' * 64
    elif damage == 'dataset': report['dataset_sha256'] = 'b' * 64
    elif damage == 'weight': report['adapter_sha256'] = 'b' * 64
    elif damage == 'frozen': report['frozen_parameter_sha256_after'] = 'b' * 64
    elif damage == 'loss': report['losses'][-1]['loss'] = float('nan')
    elif damage == 'step': report['losses'][-1]['step'] = 11
    elif damage == 'runtime': report['learning_rate'] = 0.01
    elif damage == 'recipe': effective['media_recipe_digest'] = 'b' * 64
    (result / 'training.json').write_text(json.dumps(report))
    entries = [{'path': 'result/' + file.name, 'sha256': file_hash(file), 'media_type': 'application/json' if file.suffix == '.json' else 'application/octet-stream'} for file in sorted(result.iterdir())]
    attempt['output_manifest_ref'] = service.seal_manifest({'artifacts': entries, 'effective_config': effective})
    with service.store.transaction(): service.store.put('attempt', attempt)
    assert service.collect(attempt['id'])['state'] == 'succeeded'
    return attempt


def test_image_adapter_retains_exact_two_files_and_stays_experimental(rig):
    client, service, *_ = rig
    attempt = trained(rig)
    adapter = post(client, f"/attempts/{attempt['id']}/adapters", {}, 'image-save')
    assert adapter['status'] == 'experimental' and adapter['quality_status'] == 'not_evaluated'
    assert adapter['modality'] == 'image'
    assert adapter['training_recipe_digest'] == attempt['snapshot']['media_recipe_digest']
    stored = service.store.get('adapter', adapter['id'])
    assert sorted(item.name for item in Path(stored['storage_path']).iterdir()) == ['pytorch_lora_weights.safetensors', 'training.json']
    assert post(client, f"/attempts/{attempt['id']}/adapters", {}, 'image-save') == adapter


@pytest.mark.parametrize('damage', ['base', 'dataset', 'weight', 'frozen', 'loss', 'step', 'runtime', 'recipe'])
def test_image_adapter_bad_provenance_or_training_evidence_rejected(rig, damage):
    client, service, *_ = rig
    attempt = trained(rig, damage)
    response = client.post(f"/api/v1/attempts/{attempt['id']}/adapters", json={}, headers={'Idempotency-Key': 'reject-' + damage})
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'ADAPTER_PROVENANCE_MISMATCH'
    assert not service.store.list('adapter')
