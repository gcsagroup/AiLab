"""普通模型对照输入在任何权重加载前验证；不伪造推理结果。"""
import json
import pytest
from test_model_evaluation import comparison
from workers.mlx_worker import validate_comparison_model, WorkerError, snapshot_manifest, canonical_digest
from adapters.mlx_text.evaluation import model_evaluation_identity


def ordinary(tmp_path, quantized=False):
    snapshot, base, candidate, output = comparison(tmp_path)
    if not quantized:
        config = json.loads((candidate / 'config.json').read_text()); config.pop('quantization')
        (candidate / 'config.json').write_text(json.dumps(config))
        (candidate / 'model.safetensors').write_bytes(b'different-ordinary-weight-contract')
        entries, identity = snapshot_manifest(candidate)
        snapshot.update(candidate_model_manifest=entries, candidate_model_manifest_digest=identity)
    snapshot['evaluation_kind'] = 'capability_comparison'
    pair = {k: v for k, v in snapshot['model_comparison'].items() if k.startswith(('baseline_', 'candidate_model_'))}
    pair.update(kind='capability_comparison', candidate_model_manifest_digest=snapshot['candidate_model_manifest_digest'])
    snapshot.update(model_comparison=pair, model_comparison_digest=canonical_digest(pair))
    snapshot.pop('quality_plan_ref')
    return snapshot, base, candidate, output


@pytest.mark.parametrize('quantized', [False, True])
def test_ordinary_model_pair_supports_both_local_weight_formats_without_admission_binding(tmp_path, quantized):
    snapshot, base, candidate, output = ordinary(tmp_path, quantized)
    assert validate_comparison_model(snapshot, output, base) == candidate
    recipe, identity = model_evaluation_identity(snapshot, 'd' * 64)
    assert recipe['quality_plan_ref_digest'] is None and recipe['evaluation_kind'] == 'capability_comparison'


@pytest.mark.parametrize('mutation', ['changed_file', 'same_model', 'tokenizer_changed', 'wrong_pair', 'adapter', 'dataset', 'output_overlap', 'wrong_quantization'])
def test_ordinary_comparison_rejects_invalid_inputs(tmp_path, mutation):
    snapshot, base, candidate, output = ordinary(tmp_path)
    if mutation == 'changed_file': (candidate / 'model.safetensors').write_bytes(b'changed')
    if mutation == 'same_model': snapshot['candidate_model_path'] = str(base)
    if mutation == 'tokenizer_changed':
        (candidate / 'tokenizer_config.json').write_text('{"changed":true}')
        entries, identity = snapshot_manifest(candidate); snapshot.update(candidate_model_manifest=entries, candidate_model_manifest_digest=identity)
        snapshot['model_comparison']['candidate_model_manifest_digest'] = identity
        snapshot['model_comparison_digest'] = canonical_digest(snapshot['model_comparison'])
    if mutation == 'wrong_pair': snapshot['model_comparison']['baseline_model_id'] = 'other'
    if mutation == 'adapter': snapshot['adapter_path'] = str(base)
    if mutation == 'dataset': snapshot['dataset_path'] = str(base / 'data.jsonl')
    if mutation == 'output_overlap': output = candidate / 'output'
    if mutation == 'wrong_quantization':
        config = json.loads((candidate / 'config.json').read_text()); config['quantization'] = {'bits': 8}
        (candidate / 'config.json').write_text(json.dumps(config))
        entries, identity = snapshot_manifest(candidate); snapshot.update(candidate_model_manifest=entries, candidate_model_manifest_digest=identity)
    with pytest.raises(WorkerError): validate_comparison_model(snapshot, output, base)
