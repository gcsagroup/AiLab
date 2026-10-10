"""固定 Jetson 组合的接纳与拒绝边界；真实硬件证据另存。"""

import json

import pytest

from test_completion import completion_fixture
from test_adapter import adapter
from ailab_control.remote.protocol import ProtocolError


@pytest.mark.parametrize("mutation", [None, "arch", "torch_build", "torch_release", "numpy", "missing"])
def test_jetson_profile_requires_exact_build_and_architecture(mutation):
    versions = dict(adapter.JETSON_VERSIONS); machine = "aarch64"
    if mutation == "arch": machine = "x86_64"
    if mutation == "torch_build": versions["torch"] = "2.8.0a0+other"
    if mutation == "torch_release": versions["torch"] = "2.8.0"
    if mutation == "numpy": versions["numpy"] = "2.4.2"
    if mutation == "missing": del versions["peft"]
    profile, _, cuda = adapter.runtime_profile(versions, machine)
    assert profile == (adapter.JETSON_PROFILE if mutation is None else None)
    if mutation is None: assert cuda == "12.9"


def test_existing_cuda_profile_stays_fixed():
    versions = {**adapter.VERSIONS, "torch": "2.10.0+cu128"}
    assert adapter.runtime_profile(versions, "x86_64")[2] == "12.8"
    versions["torch"] = "2.11.0"
    assert adapter.runtime_profile(versions, "x86_64")[0] is None


@pytest.mark.parametrize("mutation", [None, "arch", "cuda", "versions", "name", "capability", "missing_devices", "missing_profile"])
def test_completion_requires_fixed_jetson_identity(tmp_path, mutation):
    snapshot, effective, artifacts = completion_fixture(tmp_path)
    path = tmp_path / "environment.json"
    report = json.loads(path.read_text())
    report.update(runtime_profile=adapter.JETSON_PROFILE, machine="aarch64", versions=adapter.JETSON_VERSIONS,
                  cuda_runtime="12.9", devices=[{"name": "Orin", "capability": [8, 7]}])
    if mutation == "arch": report["machine"] = "x86_64"
    if mutation == "cuda": report["cuda_runtime"] = "12.8"
    if mutation == "versions": report["versions"] = adapter.VERSIONS
    if mutation == "name": report["devices"][0]["name"] = "Other"
    if mutation == "capability": report["devices"][0]["capability"] = [9, 0]
    if mutation == "missing_devices": report["devices"] = []
    if mutation == "missing_profile": del report["runtime_profile"]
    path.write_text(json.dumps(report))
    if mutation is None:
        assert adapter.validate_completion(snapshot, effective, artifacts, tmp_path)
    else:
        with pytest.raises(ProtocolError): adapter.validate_completion(snapshot, effective, artifacts, tmp_path)
