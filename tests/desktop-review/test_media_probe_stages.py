"""用小文件、导入替身和真实资源追踪器验证阶段测量，不加载模型。"""

import builtins
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("media_entry_stages", Path(__file__).resolve().parents[2] / "scripts/desktop/media_entry.py")
entry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(entry)


def seal(root):
    files = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in root.rglob("*") if path.is_file() and path.name != "runtime-manifest.json"}
    (root / "runtime-manifest.json").write_text(json.dumps({"schema_version": 1, "files": files}))


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    def make(profile="diffusers"):
        root = tmp_path / profile / "_internal"
        root.mkdir(parents=True)
        source = {"profile": profile, "python": entry.platform.python_version(), "required_dependencies": {"fixture-media": "1.0"},
                  "sources": {"worker": "a" * 64}, "requirements_lock_sha256": "b" * 64}
        (root / "source-manifest.json").write_text(json.dumps(source))
        (root / "payload.bin").write_bytes(b"complete-runtime")
        seal(root.parent)
        tools = tmp_path / "media-tools"
        tools.mkdir(exist_ok=True)
        (tools / "ffmpeg").write_bytes(b"complete-media-tools")
        seal(tools)
        monkeypatch.setattr(entry, "resources", lambda: root)
        monkeypatch.setattr(entry.importlib.metadata, "version", lambda name: "1.0")
        monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))))
        monkeypatch.setitem(sys.modules, "diffusers", SimpleNamespace(StableDiffusionPipeline=object(), StableVideoDiffusionPipeline=object()))
        monkeypatch.setitem(sys.modules, "peft", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "misaki", SimpleNamespace(zh=object()))
        return root, source, tools
    return make


def stages(stderr):
    records = [json.loads(line[len(entry.PROBE_STAGE_PREFIX):]) for line in stderr.splitlines() if line.startswith(entry.PROBE_STAGE_PREFIX)]
    for record in records:
        assert set(record) == {"stage", "status", "elapsed_seconds"}
        assert record["stage"] in entry.PROBE_STAGES
        assert record["status"] in {"succeeded", "failed"}
        assert type(record["elapsed_seconds"]) in (int, float)
        assert math.isfinite(record["elapsed_seconds"]) and record["elapsed_seconds"] >= 0
    return records


@pytest.mark.parametrize("profile", ["diffusers", "kokoro"])
def test_main_records_complete_stages_and_real_tracker_without_changing_facts(runtime, monkeypatch, capsys, profile):
    root, source, _ = runtime(profile)
    monkeypatch.setattr(sys, "argv", ["fixed-media", "--mode", "probe"])
    assert entry.main() == 0
    captured = capsys.readouterr()
    records = stages(captured.err)
    expected = ["runtime_files", *(["media_tools_files"] if profile == "diffusers" else []),
                "dependency_versions", "torch_import", "engine_imports", "tracker_start", "tracker_reap"]
    assert [record["stage"] for record in records] == expected
    assert all(record["status"] == "succeeded" for record in records)
    facts = json.loads(captured.out)
    assert set(facts) == {"profile", "python", "dependencies", "device_ready", "interpreter_flags", "resource_tracker_ready", "sources", "runtime_manifest_sha256", "requirements_lock_sha256"}
    assert facts["dependencies"] == source["required_dependencies"]
    assert facts["profile"] == profile and facts["device_ready"] is True and facts["resource_tracker_ready"] is True
    assert facts["runtime_manifest_sha256"] == hashlib.sha256((root.parent / "runtime-manifest.json").read_bytes()).hexdigest()
    assert facts["sources"] == source["sources"] and facts["requirements_lock_sha256"] == source["requirements_lock_sha256"]


def test_non_probe_manifest_and_dispatch_do_not_emit_stages(runtime, monkeypatch, capsys):
    runtime()
    entry.manifest()
    monkeypatch.setattr(sys, "argv", ["fixed-media", "--mode", "preflight", "--snapshot", "fixture.json", "--output-dir", "fixture-output"])
    monkeypatch.setattr(entry, "worker", lambda args, mode, profile: 17)
    assert entry.main() == 17
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("target,expected", [("runtime", [("runtime_files", "failed")]),
                                            ("tools", [("runtime_files", "succeeded"), ("media_tools_files", "failed")])])
def test_file_failure_retains_completed_checks(runtime, capsys, target, expected):
    root, _, tools = runtime()
    (root / "payload.bin" if target == "runtime" else tools / "ffmpeg").write_bytes(b"changed")
    with pytest.raises(ValueError):
        entry.manifest(probe_stages=True)
    captured = capsys.readouterr()
    assert [(record["stage"], record["status"]) for record in stages(captured.err)] == expected
    assert not captured.out
    assert str(root) not in captured.err and "payload.bin" not in captured.err


@pytest.mark.parametrize("failure,expected", [("versions", ["dependency_versions"]),
                                           ("torch", ["dependency_versions", "torch_import"]),
                                           ("peft", ["dependency_versions", "torch_import", "engine_imports"])])
def test_version_and_import_failure_stop_at_failed_stage(runtime, monkeypatch, capsys, failure, expected):
    root, source, _ = runtime()
    if failure == "versions":
        monkeypatch.setattr(entry.importlib.metadata, "version", lambda name: "wrong")
    else:
        original_import = builtins.__import__
        def fail_import(name, *args, **kwargs):
            if name == failure:
                raise ImportError("PRIVATE_STAGE_TOKEN /Users/private/model")
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", fail_import)
    with pytest.raises((ValueError, ImportError)):
        entry.probe(root, source)
    captured = capsys.readouterr()
    records = stages(captured.err)
    assert [record["stage"] for record in records] == expected
    assert [record["status"] for record in records] == ["succeeded"] * (len(expected) - 1) + ["failed"]
    assert not captured.out and "PRIVATE_STAGE_TOKEN" not in captured.err and "/Users/private/model" not in captured.err


def test_tracker_start_failure_closes_both_pipe_descriptors(runtime, monkeypatch, capsys):
    root, source, _ = runtime()
    descriptors = os.pipe()
    monkeypatch.setattr(entry.os, "pipe", lambda: descriptors)
    def failed_start(*args, **kwargs):
        raise OSError("PRIVATE_STAGE_TOKEN /Users/private/executor")
    monkeypatch.setattr(entry.subprocess, "Popen", failed_start)
    with pytest.raises(OSError):
        entry.probe(root, source)
    records = stages(capsys.readouterr().err)
    assert records[-1]["stage"] == "tracker_start" and records[-1]["status"] == "failed"
    assert "tracker_reap" not in {record["stage"] for record in records}
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "stdout", "stderr"])
def test_tracker_reap_preserves_original_deadline_cleanup_and_failure(runtime, monkeypatch, capsys, failure):
    root, source, _ = runtime()
    calls = []
    class Tracker:
        returncode = 2 if failure == "nonzero" else 0
        def communicate(self, timeout=None):
            calls.append(("communicate", timeout))
            if failure == "timeout" and timeout is not None:
                raise subprocess.TimeoutExpired("fixed-tracker", timeout)
            return (b"unexpected" if failure == "stdout" else b"", b"PRIVATE_STAGE_TOKEN" if failure == "stderr" else b"")
        def kill(self):
            calls.append(("kill",))
    monkeypatch.setattr(entry.subprocess, "Popen", lambda *args, **kwargs: Tracker())
    with pytest.raises(ValueError):
        entry.probe(root, source)
    captured = capsys.readouterr()
    records = stages(captured.err)
    assert records[-2]["stage"] == "tracker_start" and records[-2]["status"] == "succeeded"
    assert records[-1]["stage"] == "tracker_reap" and records[-1]["status"] == "failed"
    assert calls == ([("communicate", 15), ("kill",), ("communicate", None)] if failure == "timeout" else [("communicate", 15)])
    assert not captured.out and "PRIVATE_STAGE_TOKEN" not in captured.err


@pytest.mark.parametrize("elapsed", [float("nan"), float("inf"), -1.0])
def test_invalid_clock_values_are_not_serialized(monkeypatch, capsys, elapsed):
    samples = iter([0.0, elapsed])
    monkeypatch.setattr(entry.time, "monotonic", lambda: next(samples))
    with entry.probe_stage("torch_import"):
        pass
    assert capsys.readouterr().err == ""


def test_stage_marker_starts_a_new_line_and_flushes_before_next_stage(capsys):
    print("dependency-output-without-newline", end="", file=sys.stderr)
    with entry.probe_stage("torch_import"):
        pass
    captured = capsys.readouterr()
    assert captured.err.startswith("dependency-output-without-newline\n" + entry.PROBE_STAGE_PREFIX)
    assert len(stages(captured.err)) == 1
