"""内置媒体启动前必须验证当前文件闭包，不能只相信相同版本号。"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("media_bundle_entry", Path(__file__).resolve().parents[2] / "scripts/desktop/media_entry.py")
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)


def seal(root):
    files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file() and path.name != "runtime-manifest.json"}
    (root / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}))


def fixture(tmp_path, monkeypatch, profile="diffusers"):
    runtime = tmp_path / profile
    internal = runtime / "_internal"
    internal.mkdir(parents=True)
    (internal / "source-manifest.json").write_text(json.dumps({"profile": profile}))
    (internal / "payload.bin").write_bytes(b"same-version-original-bytes")
    (runtime / ("ailab-" + profile)).write_bytes(b"fixed-entry")
    seal(runtime)
    tools = tmp_path / "media-tools"
    (tools / "bin").mkdir(parents=True)
    (tools / "bin/ffmpeg").write_bytes(b"fixed-ffmpeg")
    (tools / "bin/ffprobe").write_bytes(b"fixed-ffprobe")
    seal(tools)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return runtime, tools


def test_valid_complete_runtime_and_tools_pass(tmp_path, monkeypatch):
    runtime, _ = fixture(tmp_path, monkeypatch)
    root, source = entry.manifest()
    assert root == runtime / "_internal" and source["profile"] == "diffusers"


@pytest.mark.parametrize("change", ["bytes", "missing", "extra", "symlink", "broken-symlink", "manifest-traversal"])
def test_changed_runtime_is_rejected_before_dispatch(tmp_path, monkeypatch, change):
    runtime, _ = fixture(tmp_path, monkeypatch)
    payload = runtime / "_internal/payload.bin"
    if change == "bytes":
        payload.write_bytes(b"same-version-replaced-bytes")
    elif change == "missing":
        payload.unlink()
    elif change == "extra":
        (runtime / "_internal/unlisted.json").write_text("{}")
    elif change == "symlink":
        external = tmp_path / "outside.bin"
        external.write_bytes(payload.read_bytes())
        payload.unlink()
        payload.symlink_to(external)
    elif change == "broken-symlink":
        payload.unlink()
        payload.symlink_to(runtime / "missing.bin")
    else:
        path = runtime / "runtime-manifest.json"
        data = json.loads(path.read_text())
        data["files"]["../outside.bin"] = "a" * 64
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        entry.manifest()


def test_replaced_ffmpeg_is_rejected_before_diffusers_dispatch(tmp_path, monkeypatch):
    _, tools = fixture(tmp_path, monkeypatch)
    (tools / "bin/ffmpeg").write_bytes(b"replacement-with-the-same-version")
    with pytest.raises(ValueError):
        entry.manifest()


def test_cpu_audio_does_not_require_unrelated_video_tools(tmp_path, monkeypatch):
    _, tools = fixture(tmp_path, monkeypatch, profile="kokoro")
    (tools / "runtime-manifest.json").unlink()
    _, source = entry.manifest()
    assert source["profile"] == "kokoro"


def test_diffusers_recipe_environment_binds_both_complete_manifests(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(repository))
    from adapters.media import preflight
    runtime, tools = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "version_info", (3, 13))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))))
    monkeypatch.setattr(preflight.importlib.metadata, "version", lambda name: preflight.VERSIONS[name])
    monkeypatch.setattr(preflight.importlib.metadata, "distributions", lambda **kwargs: [])
    first = preflight.environment()
    assert first["runtime_manifest_sha256"] == hashlib.sha256((runtime / "runtime-manifest.json").read_bytes()).hexdigest()
    assert first["media_tools_manifest_sha256"] == hashlib.sha256((tools / "runtime-manifest.json").read_bytes()).hexdigest()
    (tools / "runtime-manifest.json").write_text('{"changed":"tools"}')
    second = preflight.environment()
    assert first["media_tools_manifest_sha256"] != second["media_tools_manifest_sha256"]
    assert first["runtime_manifest_sha256"] == second["runtime_manifest_sha256"]
    (runtime / "runtime-manifest.json").write_text('{"changed":"runtime"}')
    assert second["runtime_manifest_sha256"] != preflight.environment()["runtime_manifest_sha256"]


def test_frozen_environment_is_independent_of_repeated_import_paths(tmp_path, monkeypatch):
    repository = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(repository))
    from adapters.media import preflight
    runtime, _ = fixture(tmp_path, monkeypatch)
    internal = runtime / "_internal"
    metadata = internal / "fixture_media-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: fixture-media\nVersion: 1.0\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "version_info", (3, 13))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))))
    monkeypatch.setattr(preflight.importlib.metadata, "version", lambda name: preflight.VERSIONS[name])
    sys.path.insert(0, str(internal))
    first = preflight.environment()
    sys.path.insert(0, str(internal))
    sys.path.insert(0, str(internal))
    second = preflight.environment()
    assert first == second
    assert first["packages"] == [("fixture-media", "1.0")]


def alias_runtime(tmp_path, alias_kind="symlink"):
    root = tmp_path / "runtime"
    root.mkdir()
    target = root / "a.bin"
    target.write_bytes(b"original-payload")
    alias = root / "b.bin"
    if alias_kind == "hardlink":
        os.link(target, alias)
    else:
        alias.symlink_to(target.name)
    (root / "z.bin").write_bytes(b"last-file")
    # 固定顺序让修改明确发生在首次读取、别名复用或后续文件检查之间。
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("a.bin", "b.bin", "z.bin")}
    (root / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}))
    return root


def count_hashes(monkeypatch, on_update=None):
    original = entry.hashlib.sha256
    observed = {"hashes": 0, "bytes": 0}

    class Hash:
        def __init__(self):
            self.value = original()
            observed["hashes"] += 1

        def update(self, chunk):
            self.value.update(chunk)
            observed["bytes"] += len(chunk)
            if on_update:
                on_update(observed)

        def hexdigest(self):
            return self.value.hexdigest()

    monkeypatch.setattr(entry.hashlib, "sha256", Hash)
    return observed


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_same_inode_alias_hashes_bytes_once_but_checks_every_path(tmp_path, monkeypatch, alias_kind):
    root = alias_runtime(tmp_path, alias_kind)
    expected_bytes = sum((root / name).stat().st_size for name in ("a.bin", "z.bin", "runtime-manifest.json"))
    observed = count_hashes(monkeypatch)
    entry.verify_files(root)
    assert observed == {"hashes": 3, "bytes": expected_bytes}


def test_same_inode_alias_with_different_expected_hash_is_rejected(tmp_path):
    root = alias_runtime(tmp_path)
    manifest = root / "runtime-manifest.json"
    data = json.loads(manifest.read_text())
    data["files"]["b.bin"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="文件摘要不一致：b.bin"):
        entry.verify_files(root)


@pytest.mark.parametrize("change", ["rewrite", "replace"])
def test_changed_file_cannot_reuse_digest_at_later_alias(tmp_path, monkeypatch, change):
    root = alias_runtime(tmp_path)
    target = root / "a.bin"
    previous = target.stat()
    original_open = entry.os.open
    calls = 0

    def changing_open(path, flags, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if change == "rewrite":
                target.write_bytes(b"modified-payload")
                os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            else:
                replacement = tmp_path / "replacement.bin"
                replacement.write_bytes(b"modified-payload")
                os.replace(replacement, target)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(entry.os, "open", changing_open)
    with pytest.raises(ValueError, match="文件摘要不一致：b.bin"):
        entry.verify_files(root)


@pytest.mark.parametrize("change", ["rewrite", "replace"])
def test_file_changed_during_read_is_rejected(tmp_path, monkeypatch, change):
    root = alias_runtime(tmp_path)
    target = root / "a.bin"
    changed = False

    def on_update(observed):
        nonlocal changed
        if changed or observed["hashes"] != 1:
            return
        changed = True
        if change == "rewrite":
            target.write_bytes(b"modified-payload")
        else:
            replacement = tmp_path / "replacement.bin"
            replacement.write_bytes(b"modified-payload")
            os.replace(replacement, target)

    count_hashes(monkeypatch, on_update)
    with pytest.raises(ValueError, match="校验期间变化|文件摘要不一致"):
        entry.verify_files(root)
    assert changed


@pytest.mark.parametrize("change", ["rewrite-earlier", "replace-alias", "outside-alias"])
def test_final_identity_check_rejects_changes_after_alias_was_checked(tmp_path, monkeypatch, change):
    root = alias_runtime(tmp_path)
    outside = tmp_path / "outside.bin"
    outside.write_bytes((root / "a.bin").read_bytes())
    original_open = entry.os.open

    def changing_open(path, flags, *args, **kwargs):
        if Path(path).name == "z.bin":
            if change == "rewrite-earlier":
                (root / "a.bin").write_bytes(b"modified-payload")
            elif change == "replace-alias":
                (root / "b.bin").unlink()
                (root / "b.bin").write_bytes(b"original-payload")
            else:
                (root / "b.bin").unlink()
                (root / "b.bin").symlink_to(outside)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(entry.os, "open", changing_open)
    with pytest.raises(ValueError, match="校验期间变化"):
        entry.verify_files(root)


def test_next_call_rehashes_unchanged_files_and_rejects_later_changes(tmp_path, monkeypatch):
    root = alias_runtime(tmp_path)
    observed = count_hashes(monkeypatch)
    entry.verify_files(root)
    first = dict(observed)
    entry.verify_files(root)
    assert observed == {key: value * 2 for key, value in first.items()}
    (root / "a.bin").write_bytes(b"modified-payload")
    with pytest.raises(ValueError, match="文件摘要不一致：a.bin"):
        entry.verify_files(root)


def test_equal_bytes_in_different_files_are_not_treated_as_inode_aliases(tmp_path, monkeypatch):
    root = alias_runtime(tmp_path)
    (root / "b.bin").unlink()
    (root / "b.bin").write_bytes((root / "a.bin").read_bytes())
    observed = count_hashes(monkeypatch)
    entry.verify_files(root)
    assert observed["hashes"] == 4


def test_parent_directory_cannot_be_replaced_by_link_to_same_inodes(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    parent = root / "nested"
    parent.mkdir(parents=True)
    (parent / "a.bin").write_bytes(b"same-current-inode")
    (root / "z.bin").write_bytes(b"trigger-after-reading")
    files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("nested/a.bin", "z.bin")}
    (root / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}))
    original_open = entry.os.open

    def changing_open(path, flags, *args, **kwargs):
        if Path(path).name == "z.bin":
            moved = tmp_path / "moved-parent"
            parent.rename(moved)
            parent.symlink_to(moved, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(entry.os, "open", changing_open)
    with pytest.raises(ValueError, match="目录在校验期间变化"):
        entry.verify_files(root)
