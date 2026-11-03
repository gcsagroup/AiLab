import sys
from pathlib import Path
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/control'))
sys.path.insert(0, str(ROOT / 'services/control/ailab_studio/workers'))
from ailab_studio.contracts import Inference
from ailab_studio.service import Studio
from comfy_media import validate_architecture


def config(**extra):
    return Inference(**({'model': 'backbone.safetensors', 'engine': 'diffusers', 'workflow': 't2i',
        'media_format': 'comfyui', 'text_encoder': 'encoder.safetensors', 'vae': 'vae.safetensors', 'prompt': 'cat'} | extra))


def test_split_components_required_and_video_contract():
    with pytest.raises(ValueError): config(vae='')
    with pytest.raises(ValueError): config(comfy_architecture='flux')
    with pytest.raises(ValueError): config(workflow='t2v')
    with pytest.raises(ValueError): config(workflow='t2v', comfy_architecture='wan21', frames=16)
    assert config(workflow='t2v', comfy_architecture='wan21', frames=17).frames == 17
    with pytest.raises(ValueError): config(workflow='r2v', comfy_architecture='wan21', material_id='reference')


def test_reject_wrong_native_model_without_conversion():
    validate_architecture('anima', 'Anima', 't2i')
    validate_architecture('wan21', 'WAN21_I2V', 'r2v')
    for arch, actual, workflow in [('anima', 'Flux', 't2i'), ('wan21', 'WAN22_T2V', 't2v'), ('wan21', 'WAN21_T2V', 'r2v')]:
        with pytest.raises(ValueError, match='不会转换'): validate_architecture(arch, actual, workflow)


def test_submission_preserves_original_files_and_uses_native_environment(tmp_path):
    studio = Studio(tmp_path / 'state')
    try:
        paths = {}
        for name in ('model', 'text_encoder', 'vae'):
            path = tmp_path / (name + '.safetensors'); path.write_bytes(b'original weights')
            paths[name] = str(path)
        studio.runtimes.resolve = Mock(return_value={'path': 'native-runtime', 'version': 'test'})
        studio.launch = Mock(return_value={'id': 'queued'})
        studio.submit('inference', config(**paths))
        studio.runtimes.resolve.assert_called_once_with('comfyui')
        submitted = studio.launch.call_args.args[1]
        assert all(submitted[key] == value for key, value in paths.items())
        assert all(Path(value).read_bytes() == b'original weights' for value in paths.values())
        assert not list(tmp_path.glob('**/transformer'))
    finally: studio.close()
