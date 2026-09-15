"""中文配音输入和固定来源负例；本文件不冒充真实音频生成证据。"""

import json
from pathlib import Path
import sys
import socket
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "adapters/media"))
import tts_cli as tts
import tts_prepare as prepare


def snapshot(tmp_path):
    return {"kind": "audio", "operation": "generate", "model_path": str(tmp_path / "model"), "model_manifest_digest": "a" * 64,
            "input": {"prompt": "你好，这是本机中文语音测试。"},
            "runtime": {"engine": "kokoro", "device_id": "cpu", "voice": "zf_xiaobei", "speed": 1.0, "seed": 0, "sample_rate": 24000}}


@pytest.mark.parametrize("field,value,code", [("device_id", "mps", "INVALID_CONFIG"), ("voice", "任意远程音色", "INVALID_CONFIG"), ("sample_rate", 44100, "INVALID_CONFIG"), ("speed", True, "INVALID_CONFIG"), ("speed", float("nan"), "INVALID_CONFIG"), ("speed", 3, "INVALID_CONFIG"), ("seed", -1, "INVALID_CONFIG"), ("seed", True, "INVALID_CONFIG")])
def test_unsupported_runtime_rejected_before_model_read(tmp_path, field, value, code):
    body = snapshot(tmp_path)
    body["runtime"][field] = value
    with pytest.raises(tts.TTSError) as error:
        tts.validate(body, tmp_path / "output")
    assert error.value.code == code
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("text", ["", "   ", "Hello world", "中文与English混合", "中文字" * 200, "你好🙂", "中文かな", "中文é"])
def test_invalid_text_does_not_silently_skip_or_truncate(tmp_path, text):
    body = snapshot(tmp_path)
    body["input"]["prompt"] = text
    with pytest.raises(tts.TTSError) as error:
        tts.validate(body, tmp_path / "output")
    assert error.value.code == "INVALID_TTS_TEXT"


def test_model_manifest_and_original_source_are_required(tmp_path):
    body = snapshot(tmp_path)
    model = Path(body["model_path"])
    model.mkdir()
    (model / "untrusted.pth").write_bytes("不会加载任意文件".encode())
    with pytest.raises(tts.TTSError) as error:
        tts.validate(body, tmp_path / "output")
    assert error.value.code == "MODEL_IDENTITY_CHANGED"


def test_prepared_blob_size_digest_and_symlink_checked(tmp_path):
    path = tmp_path / "小文件.bin"
    path.write_bytes(b"fixed")
    expected = {"size": 5, "sha256": prepare.file_hash(path)}
    assert prepare.verify(path, expected) == expected["sha256"]
    path.write_bytes(b"other")
    with pytest.raises(ValueError): prepare.verify(path, expected)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(ValueError): prepare.verify(link, {"size": 5})


def test_source_manifest_is_fixed_and_download_budget_bounded():
    assert set(prepare.FILES) == {"config.json", "kokoro-v1_0.pth", "voices/zf_xiaobei.pt"}
    assert sum(item["size"] for item in prepare.FILES.values()) < 330_000_000
    assert prepare.REVISION == "f3ff3571791e39611d31c381e3a41a3af07b4987"


def test_inference_python_network_is_rejected_before_connect():
    with tts.offline_mode(), pytest.raises(tts.TTSError) as error:
        socket.create_connection(("example.com", 443))
    assert error.value.code == "NETWORK_NOT_ALLOWED"


def test_real_cli_invalid_text_returns_preflight_contract(tmp_path):
    body = snapshot(tmp_path)
    body["input"]["prompt"] = "你好🙂"
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(body))
    result = subprocess.run([sys.executable, "-B", str(ROOT / "adapters/media/tts_cli.py"), "--snapshot", str(path), "--output-dir", str(tmp_path / "output"), "--preflight"], capture_output=True, text=True, timeout=10)
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["can_submit"] is False
    assert report["blocking"][0]["code"] == "INVALID_TTS_TEXT"
    assert not (tmp_path / "output").exists()


def test_frozen_environment_reads_complete_bundle_metadata_and_ignores_vendored_paths(tmp_path, monkeypatch):
    internal = tmp_path / "_internal"
    internal.mkdir()
    required = {"kokoro": "0.9.4", "misaki": "0.9.4"}
    (internal / "source-manifest.json").write_text(json.dumps({"profile": "kokoro", "required_dependencies": required}))
    (tmp_path / "runtime-manifest.json").write_text('{"files": {}}')
    for name, version in required.items():
        folder = internal / f"{name}-{version}.dist-info"
        folder.mkdir()
        (folder / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n")
    vendor = internal / "vendored"
    unrelated = vendor / "unrelated-99.dist-info"
    unrelated.mkdir(parents=True)
    (unrelated / "METADATA").write_text("Name: unrelated\nVersion: 99\n")
    monkeypatch.syspath_prepend(str(vendor))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    environment = tts.environment_snapshot()
    assert environment["dependencies"] == [("kokoro", "0.9.4"), ("misaki", "0.9.4")]
    assert environment["runtime_manifest_sha256"] == prepare.file_hash(tmp_path / "runtime-manifest.json")
    (internal / "misaki-0.9.4.dist-info/METADATA").write_text("Name: misaki\nVersion: 0.9.3\n")
    with pytest.raises(tts.TTSError) as error:
        tts.environment_snapshot()
    assert error.value.code == "ENVIRONMENT_CHANGED"
