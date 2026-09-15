"""实际 Torch 状态加载的严格边界；无需读取模型权重。"""

from pathlib import Path
import sys

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("kokoro")
from kokoro.istftnet import AdaIN1d

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters/media"))
from tts_cli import TTSError, strict_state


def fixture():
    module = torch.nn.Sequential(AdaIN1d(4, 8))
    state = {name: value for name, value in module.state_dict().items() if '.norm.' not in name}
    return module, state


def test_official_identity_defaults_are_exact_and_load_strictly():
    module, state = fixture()
    prepared, record = strict_state(module, {'module.' + key: value for key, value in state.items()}, torch)
    module.load_state_dict(prepared, strict=True)
    assert record['module_prefix_removed']
    assert {item['value'] for item in record['identity_defaults']} == {0, 1}
    assert len(record['identity_defaults']) == 2


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'nonidentity', 'mixedprefix'])
def test_other_missing_extra_or_changed_defaults_are_rejected(mutation):
    module, state = fixture()
    if mutation == 'missing':
        state.pop(next(iter(state)))
    elif mutation == 'extra':
        state['unknown'] = torch.ones(1)
    elif mutation == 'nonidentity':
        with torch.no_grad():
            module[0].norm.weight.fill_(2)
    else:
        name = next(iter(state))
        state['module.' + name] = state.pop(name)
    with pytest.raises(TTSError):
        strict_state(module, state, torch)


def test_arbitrary_affine_normalization_defaults_are_not_allowed():
    module = torch.nn.Sequential(torch.nn.InstanceNorm1d(4, affine=True))
    with pytest.raises(TTSError):
        strict_state(module, {}, torch)
