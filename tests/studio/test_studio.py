"""Portable control integration tests; subprocess fixtures do not claim GPU acceptance."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import threading

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))
from ailab_studio.__main__ import create_app
from ailab_studio.service import Studio, decode_image, process_alive
from ailab_studio.catalog import model_info, recommend
from ailab_studio.contracts import Inference, SFT
from ailab_studio.ablation import templates, compose
from ailab_studio.runtimes import PROFILES, interpreter


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'studio', 'test-token')
    with TestClient(app, base_url='http://127.0.0.1', headers={'Authorization': 'Bearer test-token'}) as c:
        yield c


@pytest.fixture
def studio(tmp_path):
    s = Studio(tmp_path / 'state')
    yield s
    s.close()


def wait(s, key):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        job = s.store.get('job', key)
        if job['state'] in ('succeeded', 'failed', 'cancelled'): return job
        time.sleep(.05)
    raise AssertionError('job did not finish')


def model(tmp_path):
    path = tmp_path / '模型 中文'; path.mkdir()
    (path / 'config.json').write_text(json.dumps({'model_type': 'qwen2', 'max_position_embeddings': 32768}), encoding='utf-8')
    (path / 'model.safetensors').write_bytes(b'fixture-not-real-weights')
    return path


def test_api_auth_origin_and_validation(client):
    assert client.get('/api/v1/studio/status').status_code == 200
    assert client.get('/api/v1/studio/status', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert client.get('/api/v1/studio/status', headers={'Origin': 'http://evil.example'}).status_code == 403
    assert client.get('/api/v1/studio/status', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/api/v1/studio/sft', json={'model': 'x', 'dataset': 'y', 'epochs': -1}).status_code == 422
    assert client.post('/api/v1/studio/sft', json={'model': 'x', 'dataset': 'y', 'shell': 'evil'}).status_code == 422


@pytest.mark.parametrize('endpoint,action', [('llm/load', 'load'), ('inference', 'generate')])
def test_external_gguf_runtime_guidance_and_existing_environment(client, tmp_path, monkeypatch, endpoint, action):
    # An external model need not be registered in the asset catalog or database.
    model_file = tmp_path / 'external.gguf'
    model_file.write_bytes(b'GGUF')
    payload = {'model': str(model_file), 'engine': 'llama', 'workflow': 'chat', 'action': action,
               'messages': [] if action == 'load' else [{'role': 'user', 'content': 'Hello'}]}
    url = '/api/v1/studio/' + endpoint
    response = client.post(url, json=payload)
    assert response.status_code == 400
    assert '设置 → 环境管理' in response.json()['error']['message']
    assert '记录不存在' not in response.text
    studio = client.app.state.studio
    runtime = tmp_path / 'existing-runtime'
    python = interpreter(runtime); python.parent.mkdir(parents=True); python.touch()
    active = studio.runtimes.root / 'llama' / 'active.json'
    active.parent.mkdir(parents=True)
    active.write_text(json.dumps({'path': str(runtime), 'version': 'existing', 'accelerator': 'cpu'}))
    monkeypatch.setattr(studio, 'launch', lambda kind, config, runtime: {'kind': kind, 'config': config, 'runtime': runtime})
    response = client.post(url, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['config']['model'] == str(model_file.resolve())
    assert response.json()['config']['action'] == action
    assert response.json()['config']['runtime_path'] == str(runtime)


def test_paths_scan_and_recommendation(client, tmp_path):
    path = model(tmp_path)
    datasets = tmp_path / 'data'; datasets.mkdir(); (datasets / 'train.jsonl').write_text('{"text":"hello"}\n')
    assert client.post('/api/v1/studio/paths', json={'models': str(tmp_path), 'datasets': str(datasets)}).status_code == 200
    assets = client.get('/api/v1/studio/assets').json()
    assert any(m['path'] == str(path.resolve()) for m in assets['models'])
    assert assets['datasets'][0]['format'] == 'jsonl'
    host = {'device': 'cpu', 'memory_gb': 8, 'gpus': []}
    config = recommend(str(path), 'vllm', host)['config']
    assert config['context_length'] == 2048
    with pytest.raises(ValueError, match='GGUF'): recommend(str(path), 'llama', host)


def test_missing_shard_is_not_loadable(tmp_path):
    path = model(tmp_path)
    (path / 'model.safetensors.index.json').write_text('{"weight_map":{"x":"missing.safetensors"}}')
    with pytest.raises(ValueError, match='分片'): model_info(str(path))


def test_visual_ablation_fields_and_advanced_roundtrip(tmp_path):
    import tomllib
    t = templates()
    original = tomllib.loads((ROOT / 'abliterix.toml').read_text(encoding='utf-8'))
    from ailab_studio.ablation import flatten
    assert set(t['fields']) == set(flatten(original))
    text = '# preserve comment\n[model]\nmax_model_len=2048\n[steering.component_strength_ranges]\n"attn.k_proj"=[0.55,0.95]\n'
    merged = compose(text, t['fields'], '/models/local', tmp_path)
    parsed = tomllib.loads(merged)
    assert '# preserve comment' in merged
    assert parsed['model']['max_model_len'] == 2048
    assert parsed['model']['backend'] == 'hf'
    assert parsed['model']['model_id'] == '/models/local'
    assert parsed['steering']['component_strength_ranges']['attn.k_proj'] == [.55, .95]
    assert parsed['non_interactive'] is True
    assert parsed['optimization']['checkpoint_dir'] == str(tmp_path / 'checkpoints')


def test_ablation_no_silent_backend_change(tmp_path):
    with pytest.raises(ValueError, match='推理后端'): compose('[model]\nbackend="invalid"', {}, 'model', tmp_path)
    with pytest.raises(ValueError, match='TOML'): compose('[bad', {}, 'model', tmp_path)
    with pytest.raises(ValueError, match='可视化'): compose('', {'arbitrary': 'x'}, 'model', tmp_path)
    assert 'trust_remote_code = true' in compose('[model]\ntrust_remote_code=true', {}, 'model', tmp_path).replace('trust_remote_code=true', 'trust_remote_code = true')


def test_real_process_events_exit_and_persistence(studio):
    def target(job, run):
        run([sys.executable, '-u', '-c', 'import json; print("@@AILAB " + json.dumps({"type":"metric","step":1,"loss":2.5})); print("完成"); print("\\r 50%|progress|@@AILAB " + json.dumps({"type":"progress","step":4,"total":8}))'])
        return {'checked': True}
    job = studio.launch('sft', {}, 'training', target)
    done = wait(studio, job['id'])
    assert done['state'] == 'succeeded'
    events = studio.store.events(job['id'])
    assert any(e.get('loss') == 2.5 for e in events)
    assert any(e.get('type') == 'progress' and e.get('step') == 4 and e.get('total') == 8 for e in events)
    assert any(e.get('text') == '完成' for e in events)
    assert not process_alive(done)
    assert studio.store.events(job['id'], events[-1]['seq']) == []


def test_cancel_owns_process_and_releases_lease(studio):
    def target(job, run):
        run([sys.executable, '-u', '-c', 'import time; print("started", flush=True); time.sleep(60)'])
    job = studio.launch('sft', {}, 'training', target)
    deadline = time.monotonic() + 10
    while not process_alive(studio.store.get('job', job['id'])) and time.monotonic() < deadline: time.sleep(.05)
    queued = studio.launch('inference', {}, 'llama', lambda j, r: {'ok': True})
    assert studio.store.get('job', queued['id'])['state'] == 'queued'
    studio.cancel(job['id'])
    final = wait(studio, job['id'])
    assert final['state'] == 'cancelled'
    assert not process_alive(final)
    next_job = studio.launch('inference', {}, 'llama', lambda j, r: {'ok': True})
    assert wait(studio, next_job['id'])['state'] == 'succeeded'


def test_failed_process_not_success(studio):
    job = studio.launch('inference', {}, 'llama', lambda j, run: run([sys.executable, '-c', 'raise RuntimeError("worker failed")']))
    assert wait(studio, job['id'])['state'] == 'failed'


def test_shared_runtime_training_isolation(studio):
    assert 'sft' in PROFILES['training']['capabilities']
    assert set(PROFILES['vllm']['capabilities']) == {'chat', 'ablation'}
    assert 'torch' not in sys.modules
    assert studio.runtimes.list()[0]['state'] == 'not_installed'


def test_conversation_roundtrip(client):
    body = {'title': 'test', 'model': '/local/model', 'engine': 'vllm', 'messages': [{'role': 'user', 'content': '你好'}]}
    saved = client.post('/api/v1/studio/conversations', json=body).json()
    assert saved['id']
    body['messages'].append({'role': 'assistant', 'content': '您好'})
    assert client.post('/api/v1/studio/conversations/' + saved['id'], json=body).status_code == 200
    assert 'messages' not in client.get('/api/v1/studio/conversations').json()['items'][0]
    assert client.get('/api/v1/studio/conversations/' + saved['id']).json()['messages'][-1]['content'] == '您好'


def test_media_input_contracts():
    config = Inference(model='x', engine='diffusers', workflow='t2i', prompt='cat')
    assert config.sampler == 'euler'
    with pytest.raises(ValueError):
        Inference(model='x', engine='diffusers', workflow='t2i', prompt='cat', sampler='unknown')
    with pytest.raises(ValueError): Inference(model='x', engine='diffusers', workflow='r2v')
    with pytest.raises(ValueError): Inference(model='x', workflow='t2i')
    with pytest.raises(ValueError): decode_image('https://example.com/image.png')
    with pytest.raises(ValueError): Inference(model='x', messages=[{'role': 'assistant', 'content': 'x'}])
    with pytest.raises(ValueError): SFT(model='x', dataset='y', max_steps=0)


def test_local_modular_anima_discovery(tmp_path):
    (tmp_path / 'modular_model_index.json').write_text(json.dumps({'_class_name': 'AnimaModularPipeline'}))
    info = model_info(str(tmp_path))
    assert info['format'] == 'diffusers'
    assert info['architecture'] == 'AnimaModularPipeline'


def test_recovery_never_reexecutes(tmp_path):
    s = Studio(tmp_path)
    s.store.put('job', {'id': 'dead', 'state': 'running', 'kind': 'sft', 'runtime': 'training'})
    s.stopping = True; s.wake.set(); s.scheduler.join(); s.store.close()
    restarted = Studio(tmp_path)
    try:
        assert restarted.store.get('job', 'dead')['state'] == 'interrupted'
        assert not restarted.threads
    finally: restarted.close()


def test_preview_rejects_outside_path(studio, tmp_path):
    outside = tmp_path / 'outside.png'; outside.write_bytes(b'x')
    studio.store.put('job', {'id': 'bad', 'state': 'succeeded', 'output_dir': str(studio.root / 'jobs' / 'bad'), 'result': {'file': str(outside)}})
    with pytest.raises(ValueError, match='路径'): studio.preview('bad')


def test_sft_supervision_masks_prompt_and_rejects_overflow():
    sys.path.insert(0, str(ROOT / 'services/control/ailab_studio/workers'))
    from sft import encode_row
    class Tokenizer:
        chat_template = 'fixture'
        def apply_chat_template(self, messages, tokenize, add_generation_prompt):
            result = []
            for m in messages: result += [1 if m['role'] == 'user' else 2, *[ord(c) for c in m['content']], 3]
            return result + ([2] if add_generation_prompt else [])
    c = {'max_length': 100, 'loss_scope': 'assistant', 'text_column': 'text'}
    row = {'messages': [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'yes'}]}
    encoded = encode_row(row, Tokenizer(), c)
    assert encoded['labels'][:5] == [-100] * 5
    assert encoded['labels'][5:] == [ord('y'), ord('e'), ord('s'), 3]
    with pytest.raises(ValueError, match='超过'): encode_row(row, Tokenizer(), {**c, 'max_length': 5})
    with pytest.raises(ValueError, match='纯文本'): encode_row({'text': 'abc'}, Tokenizer(), c)


def test_store_exclusive_lock(studio):
    with pytest.raises(OSError): Studio(studio.root)


def test_chat_completion_persists_without_ui(studio):
    messages = [{'role': 'user', 'content': '你好', 'image': None}]
    studio.store.put('conversation', {'id': 'session', 'messages': messages, 'model': 'fixture'})
    job = studio.launch('inference', {'conversation_id': 'session', 'messages': messages}, 'llama', lambda j, run: {'text': '您好'})
    assert wait(studio, job['id'])['state'] == 'succeeded'
    assert studio.store.get('conversation', 'session')['messages'][-1]['content'] == '您好'


def test_failed_environment_update_keeps_active_runtime(studio, monkeypatch):
    old = {'id': 'training', 'path': str(Path(sys.executable).parent.parent), 'version': 'previous'}
    studio.store.put('runtime', old)
    monkeypatch.setattr('ailab_studio.runtimes.uv_command', lambda: [sys.executable])
    def fail_install(job, run):
        run([sys.executable, '-c', 'raise RuntimeError("install failed")'])
    monkeypatch.setattr(studio.runtimes, '_install', fail_install)
    job = studio.runtimes.install('training', 'cpu')
    assert wait(studio, job['id'])['state'] == 'failed'
    assert studio.runtimes.resolve('training')['version'] == 'previous'


def test_downloaded_dataset_split_separation(tmp_path):
    sys.path.insert(0, str(ROOT / 'services/control/ailab_studio/workers'))
    from sft import dataset_files
    for name in ('train-0000.parquet', 'validation-0000.parquet', 'test-0000.parquet', 'dataset_info.json'):
        (tmp_path / name).write_text('fixture')
    train, validation = dataset_files(tmp_path)
    assert [p.name for p in train] == ['train-0000.parquet']
    assert [p.name for p in validation] == ['validation-0000.parquet']
