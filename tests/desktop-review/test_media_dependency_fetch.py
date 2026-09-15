"""固定媒体依赖来源下载器的缓存、路径及失败清理边界。"""

import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("media_dependency_fetch", Path(__file__).resolve().parents[2] / "scripts/desktop/fetch_media_dependencies.py")
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)
CONTENT = b"small official dependency fixture"


def source(tmp_path, **changes):
    item = {"filename": "fixture-1.0.whl", "sha256": hashlib.sha256(CONTENT).hexdigest(), "source": "https://files.pythonhosted.org/packages/fixture.whl", **changes}
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({"schema_version": 1, "profile": "fixture", "files": [item]}))
    return path


class Response(io.BytesIO):
    def __init__(self, content=CONTENT, url="https://files.pythonhosted.org/packages/fixture.whl"):
        super().__init__(content)
        self.url = url


def test_download_then_verified_cache_does_not_contact_network(tmp_path, monkeypatch):
    manifest, cache = source(tmp_path), tmp_path / "cache with spaces"
    monkeypatch.setattr(fetcher, "urlopen", lambda *args, **kwargs: Response())
    fetcher.fetch(manifest, cache)
    assert (cache / "fixture-1.0.whl").read_bytes() == CONTENT
    monkeypatch.setattr(fetcher, "urlopen", lambda *args, **kwargs: pytest.fail("已校验缓存不应联网"))
    fetcher.fetch(manifest, cache)
    assert len(list(cache.iterdir())) == 1


@pytest.mark.parametrize("changes", [
    {"filename": "../outside.whl"}, {"filename": "/outside.whl"}, {"sha256": "not-a-digest"},
    {"source": "http://files.pythonhosted.org/packages/fixture.whl"},
    {"source": "https://example.test/fixture.whl"},
    {"source": "https://user:secret@files.pythonhosted.org/fixture.whl"},
    {"source": "https://files.pythonhosted.org:8443/fixture.whl"},
])
def test_invalid_source_rejected_before_network(tmp_path, monkeypatch, changes):
    monkeypatch.setattr(fetcher, "urlopen", lambda *args, **kwargs: pytest.fail("无效来源不得访问网络"))
    with pytest.raises(ValueError):
        fetcher.fetch(source(tmp_path, **changes), tmp_path / "cache")
    assert not (tmp_path / "outside.whl").exists()


@pytest.mark.parametrize("content,url", [(b"tampered", "https://files.pythonhosted.org/fixture.whl"), (CONTENT, "https://example.test/fixture.whl")])
def test_failed_download_leaves_no_file(tmp_path, monkeypatch, content, url):
    monkeypatch.setattr(fetcher, "urlopen", lambda *args, **kwargs: Response(content, url))
    cache = tmp_path / "cache"
    with pytest.raises(ValueError):
        fetcher.fetch(source(tmp_path), cache)
    assert list(cache.iterdir()) == []


def test_existing_tampered_cache_and_symlink_are_rejected(tmp_path):
    manifest, cache = source(tmp_path), tmp_path / "cache"
    cache.mkdir()
    target = cache / "fixture-1.0.whl"
    target.write_bytes(b"changed")
    with pytest.raises(ValueError):
        fetcher.fetch(manifest, cache)
    target.unlink()
    external = tmp_path / "original.whl"
    external.write_bytes(CONTENT)
    target.symlink_to(external)
    with pytest.raises(ValueError):
        fetcher.fetch(manifest, cache)
    assert external.read_bytes() == CONTENT and target.is_symlink()
