import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/control'))
from ailab_studio.service import Studio


def test_environment_directory_persists_and_preserves_assets(tmp_path):
    root = tmp_path / 'state'; default = tmp_path / 'install' / 'environment'
    studio = Studio(root, default)
    old_paths = studio.paths()
    new = tmp_path / 'custom' / 'environment'
    try:
        with pytest.raises(ValueError): studio.save_environment('relative/path')
        assert studio.save_environment(str(new))['environment_dir'] == str(new)
        assert studio.runtimes.root == new / 'runtimes'
        assert studio.paths() == old_paths
        assert default.exists()
    finally: studio.close()
    restored = Studio(root, default)
    try:
        assert restored.environment == new
        assert restored.default_environment == default
        restored.llm._update(phase='loaded')
        with pytest.raises(ValueError, match='卸载'): restored.save_environment('')
        restored.llm._update(phase='unloaded')
        restored.save_environment('')
        assert restored.environment == default
    finally: restored.close()
