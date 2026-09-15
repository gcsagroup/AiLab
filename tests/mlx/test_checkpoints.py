"""真实 MLX CPU 张量检查点；验证轨迹和损坏拒绝，不充当 Qwen 设备验收。"""

import copy
import json
from pathlib import Path
import random
import sys
import threading
import time

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from mlx.utils import tree_flatten
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from adapters.mlx_text.checkpoint import CheckpointError, TrainingControl, compatibility, digest, restore_checkpoint, save_checkpoint, verify_checkpoint


@pytest.fixture(autouse=True)
def cpu_device():
    previous = mx.default_device()
    mx.set_default_device(mx.cpu)
    yield
    mx.set_default_device(previous)


def setup():
    mx.random.seed(31); random.seed(31)
    model = nn.Linear(3, 2)
    optimizer = optim.AdamW(learning_rate=0.01, betas=[0.9, 0.999], eps=1e-8, bias_correction=True, weight_decay=0)
    optimizer.init(model.trainable_parameters())
    initial = {key: mx.array(value) for key, value in tree_flatten(model.trainable_parameters())}
    snapshot = {"attempt_id": "attempt-original", "operation": "train", "runtime": {"steps": 6, "seed": 31}, "model_manifest_digest": "a" * 64, "dataset_manifest_digest": "b" * 64, "tokenization_recipe_digest": "c" * 64}
    return model, optimizer, initial, snapshot


def step(model, optimizer):
    inputs = mx.random.normal((4, 3)) * random.random()
    loss, grads = nn.value_and_grad(model, lambda current: mx.mean(current(inputs) ** 2))(model)
    optimizer.update(model, grads); mx.eval(model.parameters(), optimizer.state, loss)
    return float(loss.item())


def test_resume_restores_optimizer_rng_and_exact_trajectory(tmp_path):
    model, optimizer, initial, snapshot = setup()
    losses = [step(model, optimizer) for _ in range(2)]
    checkpoint = save_checkpoint(tmp_path, snapshot, model, optimizer, initial, losses, 4)
    path = tmp_path / checkpoint["relative_path"]
    expected_losses = losses + [step(model, optimizer) for _ in range(4)]
    expected_weights = {key: mx.array(value) for key, value in tree_flatten(model.parameters())}
    model2, optimizer2, _, snapshot2 = setup(); snapshot2["attempt_id"] = "attempt-new"
    restored, saved_initial = restore_checkpoint(path, checkpoint["manifest_digest"], snapshot2, model2, optimizer2)
    actual_losses = restored + [step(model2, optimizer2) for _ in range(4)]
    assert expected_losses == actual_losses
    assert all(bool(mx.array_equal(value, dict(tree_flatten(model2.parameters()))[key])) for key, value in expected_weights.items())
    assert all(bool(mx.array_equal(value, saved_initial[key])) for key, value in initial.items())
    assert int(optimizer2.step.item()) == 6


@pytest.mark.parametrize("change", ["truncated", "metadata", "extra", "symlink", "wrong_runtime", "wrong_recipe", "wrong_digest"])
def test_incomplete_or_incompatible_checkpoint_is_rejected(tmp_path, change):
    model, optimizer, initial, snapshot = setup()
    checkpoint = save_checkpoint(tmp_path, snapshot, model, optimizer, initial, [step(model, optimizer)], 4)
    path = tmp_path / checkpoint["relative_path"]
    expected = compatibility(snapshot)
    if change == "truncated":
        (path.parent / "state.safetensors").write_bytes(b"broken")
    elif change == "metadata":
        value = json.loads(path.read_text()); value["step"] = 2; path.write_text(json.dumps(value))
    elif change == "extra":
        (path.parent / "unexpected.txt").write_text("新增文件")
    elif change == "symlink":
        link = tmp_path / "redirect.json"; link.symlink_to(path); path = link
    elif change == "wrong_runtime":
        expected["runtime"] = {**expected["runtime"], "steps": 12}
    elif change == "wrong_recipe":
        expected["tokenization_recipe_digest"] = "f" * 64
    else:
        checkpoint["manifest_digest"] = "e" * 64
    with pytest.raises(CheckpointError):
        verify_checkpoint(path, checkpoint["manifest_digest"], expected)


def command(root, sequence, action, **fields):
    directory = root / "control/commands"; directory.mkdir(parents=True, exist_ok=True)
    value = {"command_id": f"command-{sequence}", "sequence": sequence, "attempt_id": "attempt-original", "action": action, **fields}
    temporary = directory / f".command-{sequence}.tmp"
    temporary.write_text(json.dumps(value)); temporary.rename(directory / f"command-{sequence}.json")


def test_live_pause_ack_requires_saved_checkpoint_and_explicit_resume(tmp_path):
    model, optimizer, initial, snapshot = setup()
    losses = [step(model, optimizer)]
    events = []
    command(tmp_path, 1, "pause")
    control = TrainingControl(tmp_path, snapshot, lambda kind, **value: events.append({"type": kind, **value}), lambda: None)
    observations = []
    def controller():
        deadline = time.monotonic() + 5
        while not events and time.monotonic() < deadline:
            time.sleep(0.01)
        checkpoint = events[0]["checkpoint"]
        verify_checkpoint(tmp_path / checkpoint["relative_path"], checkpoint["manifest_digest"])
        observations.append(events[0]["result"] == "confirmed")
        command(tmp_path, 2, "resume", checkpoint_digest="0" * 64)
        while len(events) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        observations.append(events[1]["result"] == "failed" and not events[1]["continuing"])
        command(tmp_path, 3, "resume", checkpoint_digest=checkpoint["manifest_digest"])
    thread = threading.Thread(target=controller, daemon=True)
    thread.start()
    control.safe_point(model, optimizer, initial, losses, 4)
    thread.join(timeout=5)
    assert not thread.is_alive() and observations == [True, True] and events[-1]["result"] == "confirmed"


def test_failed_checkpoint_continues_training_with_explicit_failure(tmp_path, monkeypatch):
    model, optimizer, initial, snapshot = setup()
    events = []; command(tmp_path, 1, "pause")
    def fail(*args):
        raise OSError("测试写入失败")
    monkeypatch.setattr("adapters.mlx_text.checkpoint.save_checkpoint", fail)
    control = TrainingControl(tmp_path, snapshot, lambda kind, **value: events.append(value), lambda: None)
    control.safe_point(model, optimizer, initial, [], 4)
    assert events == [{"command_id": "command-1", "action": "pause", "result": "failed", "code": "CHECKPOINT_WRITE_FAILED", "message": "测试写入失败", "continuing": True}]
