import base64
import json
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_studio.service import Studio
from ailab_studio.__main__ import create_app
from ailab_studio.ablation import compose
from fastapi.testclient import TestClient


def until(fn, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := fn(): return value
        time.sleep(.05)
    raise AssertionError('condition timed out')


def test_global_fifo_pause_resume_cancel(tmp_path):
    s = Studio(tmp_path)
    def ticking(j, run):
        run([sys.executable, '-u', '-c', 'import time\nfor i in range(500):\n print(i,flush=True); time.sleep(.1)'])
    try:
        first = s.launch('sft', {}, 'training', ticking)
        until(lambda: s.store.events(first['id']))
        second = s.launch('ablation', {}, 'ablation', lambda j, r: {'ok': True})
        third = s.launch('inference', {}, 'llama', lambda j, r: {'ok': True})
        assert s.store.get('job', second['id'])['state'] == 'queued'
        s.pause(first['id']); until(lambda: s.store.get('job', first['id'])['state'] == 'paused')
        time.sleep(.2); before = len(s.store.events(first['id'])); time.sleep(.5)
        assert len(s.store.events(first['id'])) == before
        assert s.store.get('job', second['id'])['state'] == 'queued'
        s.pause(second['id']); s.resume(first['id'])
        until(lambda: len(s.store.events(first['id'])) > before)
        s.cancel(first['id'])
        until(lambda: s.store.get('job', third['id'])['state'] == 'succeeded')
        assert s.store.get('job', second['id'])['state'] == 'paused'
        s.resume(second['id']); until(lambda: s.store.get('job', second['id'])['state'] == 'succeeded')
    finally: s.close()


def test_concurrency_setting_and_queued_cancel(tmp_path):
    s = Studio(tmp_path)
    def sleeper(j, run): run([sys.executable, '-c', 'import time;time.sleep(30)'])
    try:
        one = s.launch('sft', {}, 'training', sleeper)
        two = s.launch('inference', {}, 'llama', sleeper)
        until(lambda: one['id'] in s.active)
        assert two['id'] not in s.active
        s.save_settings({'max_concurrent_tasks': 2}); until(lambda: two['id'] in s.active)
        three = s.launch('ablation', {}, 'ablation', sleeper); s.cancel(three['id'])
        assert s.store.get('job', three['id'])['state'] == 'cancelled'
        assert three['id'] not in s.active
        s.save_settings({'max_concurrent_tasks': 1})
        assert len(s.active) == 2
    finally: s.close()


def test_media_chunks_and_single_conversation(tmp_path):
    with TestClient(create_app(tmp_path, 'token'), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer token'}) as c:
        base = '/api/v1/studio'
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==')
        upload = c.post(base + '/materials/uploads', json={'name': 'pixel.png', 'size': len(png)}).json()
        path = base + '/materials/uploads/' + upload['id']
        assert c.post(path + '/chunk', json={'offset': 1, 'data': base64.b64encode(png).decode()}).status_code == 400
        assert c.post(path + '/chunk', json={'offset': 0, 'data': base64.b64encode(png).decode()}).status_code == 200
        material = c.post(path + '/complete', json={}).json()
        assert material['kind'] == 'image' and material['source'] == 'imported'
        assert c.get(base + '/materials').json()['items'][0]['id'] == material['id']
        content = c.get(base + '/materials/' + material['id'] + '/content?offset=0&length=524288').json()
        assert base64.b64decode(content['data']) == png
        old = c.post(base + '/conversations', json={'messages': [{'role': 'user', 'content': 'old'}]}).json()
        new = c.post(base + '/conversations', json={}).json()
        assert c.get(base + '/conversations/' + old['id']).status_code == 400
        assert [x['id'] for x in c.get(base + '/conversations').json()['items']] == [new['id']]
        assert c.post(base + '/settings', json={'max_concurrent_tasks': 0}).status_code == 422
        assert c.post(base + '/settings', json={'max_concurrent_tasks': 3}).json()['max_concurrent_tasks'] == 3


def test_architecture_check_without_weights(tmp_path):
    folder = tmp_path / 'model'; folder.mkdir()
    (folder / 'config.json').write_text(json.dumps({'model_type': 'custom', 'architectures': ['CustomModel'], 'auto_map': {'AutoConfig': 'config.Custom'}}))
    with TestClient(create_app(tmp_path / 'state', 'token'), base_url='http://127.0.0.1', headers={'Authorization': 'Bearer token'}) as c:
        result = c.post('/api/v1/studio/ablation/compatibility', json={'model': str(folder)}).json()
        assert result['architectures'] == ['CustomModel']
        assert all(x['status'] == 'not_installed' for x in result['backends'])


def test_hf_auto_precision_and_lora(tmp_path):
    import tomllib
    config = tomllib.loads(compose('', {'model.backend': 'hf', 'model.dtype_fallback_order': [], 'steering.steering_mode': 'lora'}, '/local', tmp_path))
    assert config['model']['backend'] == 'hf'
    assert 'dtype_fallback_order' not in config['model']
    assert config['steering']['steering_mode'] == 'lora'


def test_quantized_training_is_explicit_and_lora_only(tmp_path, monkeypatch):
    from ailab_studio.contracts import SFT
    folder = tmp_path / 'nvfp4'; folder.mkdir()
    (folder / 'config.json').write_text(json.dumps({'model_type': 'spark2_5', 'quantization_config': {'quant_method': 'compressed-tensors', 'format': 'nvfp4-pack-quantized'}}))
    (folder / 'model.safetensors').write_bytes(b'not-loaded-by-this-contract-test')
    data = tmp_path / 'train.jsonl'; data.write_text('{"text":"hello"}')
    s = Studio(tmp_path / 'state')
    try:
        monkeypatch.setattr(s.runtimes, 'resolve', lambda key: {'path': '/fake', 'version': 'test'})
        monkeypatch.setattr(s, 'launch', lambda kind, config, runtime: config)
        result = s.submit('sft', SFT(model=str(folder), dataset=str(data), trust_remote_code=True))
        assert result['weight_loading'] == 'dequantize'
        assert result['base_quantization']['format'] == 'nvfp4-pack-quantized'
        assert result['trust_remote_code'] is True
        with pytest.raises(ValueError, match='LoRA'):
            s.submit('sft', SFT(model=str(folder), dataset=str(data), method='full'))
    finally: s.close()


def test_result_event_preserves_artifact_kind(tmp_path, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control/ailab_studio/workers'))
    from common import finish
    finish({'output_dir': str(tmp_path)}, {'kind': 'lora_adapter', 'metrics': {'train_loss': 1.2}})
    result = json.loads(capsys.readouterr().out.removeprefix('@@AILAB '))
    assert result['type'] == 'result' and result['kind'] == 'lora_adapter'
    assert json.loads((tmp_path / 'result.json').read_text())['metrics']['train_loss'] == 1.2


def test_material_deletion_preserves_original_and_blocks_in_use(tmp_path):
    studio = Studio(tmp_path / 'state')
    original = tmp_path / 'original.png'
    original.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes(32))
    try:
        item = studio.materials.add(original, 'imported')
        studio.store.put('job', {'id':'busy', 'state':'paused', 'config':{'material_id':item['id']}})
        with pytest.raises(ValueError, match='任务使用'): studio.materials.delete(item['id'])
        assert Path(item['path']).is_file()
        studio.store.delete('job', 'busy')
        studio.materials.delete(item['id'])
        assert original.is_file() and not Path(item['path']).exists()
        assert not studio.store.list('material')
        malicious = studio.materials.add(original, 'imported')
        studio.store.put('material', {**malicious, 'path': str(original)})
        with pytest.raises(ValueError, match='路径无效'): studio.materials.delete(malicious['id'])
        assert original.is_file()
    finally: studio.close()
