"""完整优化步检查点：受限 JSON 与 safetensors，不使用 pickle 或进程挂起。"""

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import re
import time
import uuid

SCHEMA = "mlx-training-checkpoint-v1"


class CheckpointError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path, check_cancel=lambda: None):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            check_cancel()
            result.update(block)
    return result.hexdigest()


def compatibility(snapshot):
    root = Path(__file__).resolve().parents[2]
    return {key: snapshot.get(key) for key in ("model_manifest_digest", "dataset_manifest_digest", "tokenization_recipe_digest", "evaluation_plan_digest")} | {
        "runtime": snapshot["runtime"], "device": "apple-gpu",
        "versions": {name: importlib.metadata.version(name) for name in ("mlx", "mlx-lm")},
        "worker_source_sha256": file_hash(root / "workers/mlx_worker.py"),
        "checkpoint_source_sha256": file_hash(Path(__file__)),
        "recipe_source_sha256": file_hash(Path(__file__).with_name("recipe.py")),
    }


def _plain_file(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or path.resolve() != path or not path.is_file() or path.stat().st_size > maximum:
        raise CheckpointError("CHECKPOINT_INVALID", "检查点路径、类型或体积不符合要求")
    return path


def verify_checkpoint(manifest_path, expected_digest, expected_compatibility=None, check_cancel=lambda: None):
    path = _plain_file(manifest_path, 4 * 1024 * 1024)
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("manifest")
        if value.get("schema_version") != SCHEMA or value.get("complete") is not True or value.get("digest") != expected_digest or digest({key: item for key, item in value.items() if key != "digest"}) != expected_digest:
            raise ValueError("manifest")
        for key in ("step", "total_steps", "sample_count", "next_sample_index"):
            if type(value[key]) is not int:
                raise ValueError(key)
        if not 0 <= value["step"] <= value["total_steps"] <= 200 or value["sample_count"] < 1 or value["next_sample_index"] != value["step"] % value["sample_count"]:
            raise ValueError("position")
        if len(value["losses"]) != value["step"] or any(type(item) not in (int, float) or not math.isfinite(item) for item in value["losses"]):
            raise ValueError("losses")
        if expected_compatibility is not None and value["compatibility"] != expected_compatibility:
            raise CheckpointError("CHECKPOINT_INCOMPATIBLE", "检查点的模型、数据、训练配方或执行器版本已变化")
        if len(value["files"]) != 1 or value["files"][0]["path"] != "state.safetensors":
            raise ValueError("files")
        entry = value["files"][0]
        state = _plain_file(path.parent / entry["path"], 256 * 1024 * 1024)
        if state.stat().st_size != entry["size"] or file_hash(state, check_cancel) != entry["sha256"]:
            raise ValueError("file hash")
        if {item.name for item in path.parent.iterdir()} != {"manifest.json", "state.safetensors"}:
            raise ValueError("extra files")
        return value
    except (ValueError, KeyError, TypeError, OSError) as error:
        if isinstance(error, CheckpointError):
            raise
        raise CheckpointError("CHECKPOINT_INVALID", "检查点文件、完整性或训练位置不一致") from error


def _pack(value, arrays):
    import mlx.core as mx
    if isinstance(value, mx.array):
        key = "tensor_" + str(len(arrays)); arrays[key] = value
        return {"type": "array", "key": key, "shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CheckpointError("CHECKPOINT_STATE_UNSUPPORTED", "检查点字典键必须为字符串")
        return {"type": "dict", "items": {key: _pack(item, arrays) for key, item in value.items()}}
    if isinstance(value, (list, tuple)):
        return {"type": "tuple" if isinstance(value, tuple) else "list", "items": [_pack(item, arrays) for item in value]}
    if value is None or type(value) in (str, int, bool) or type(value) is float and math.isfinite(value):
        return {"type": "scalar", "value": value}
    raise CheckpointError("CHECKPOINT_STATE_UNSUPPORTED", "发现不能安全保存的优化状态")


def _unpack(tree, arrays, used, depth=0):
    if depth > 64 or not isinstance(tree, dict):
        raise CheckpointError("CHECKPOINT_INVALID", "检查点状态结构不合法")
    kind = tree.get("type")
    if kind == "array":
        key = tree.get("key")
        if key not in arrays or key in used:
            raise CheckpointError("CHECKPOINT_INVALID", "检查点张量引用缺失或重复")
        value = arrays[key]; used.add(key)
        if list(value.shape) != tree.get("shape") or str(value.dtype) != tree.get("dtype"):
            raise CheckpointError("CHECKPOINT_INVALID", "检查点张量形状或类型不匹配")
        return value
    if kind == "dict" and isinstance(tree.get("items"), dict):
        return {key: _unpack(item, arrays, used, depth + 1) for key, item in tree["items"].items()}
    if kind in {"tuple", "list"} and isinstance(tree.get("items"), list):
        items = [_unpack(item, arrays, used, depth + 1) for item in tree["items"]]
        return tuple(items) if kind == "tuple" else items
    if kind == "scalar":
        value = tree.get("value")
        if value is None or type(value) in (str, int, bool) or type(value) is float and math.isfinite(value):
            return value
    raise CheckpointError("CHECKPOINT_INVALID", "检查点含有不支持的状态类型")


def save_checkpoint(run_dir, snapshot, model, optimizer, initial, losses, sample_count, check_cancel=lambda: None):
    import mlx.core as mx
    from mlx.utils import tree_flatten
    parent = Path(run_dir) / "checkpoints"
    if parent.is_symlink() or parent.resolve() != parent:
        raise CheckpointError("CHECKPOINT_INVALID", "检查点目录不能经符号链接跳转")
    parent.mkdir(mode=0o700, exist_ok=True)
    name = "checkpoint-" + uuid.uuid4().hex
    temporary, destination = parent / ("." + name), parent / name
    temporary.mkdir(mode=0o700)
    arrays = {}
    state = {"weights": dict(tree_flatten(model.trainable_parameters())), "initial": initial,
             "optimizer": optimizer.state, "mlx_rng": list(mx.random.state), "python_rng": random.getstate()}
    mx.eval(state)
    tree = _pack(state, arrays)
    mx.save_safetensors(str(temporary / "state.safetensors"), arrays)
    state_path = temporary / "state.safetensors"
    with state_path.open("rb") as stream:
        os.fsync(stream.fileno())
    value = {"schema_version": SCHEMA, "complete": True, "source_attempt_id": snapshot.get("attempt_id"), "source_snapshot_digest": digest(snapshot),
             "step": len(losses), "total_steps": snapshot["runtime"].get("steps", 4), "next_sample_index": len(losses) % sample_count, "sample_count": sample_count,
             "losses": list(losses), "compatibility": compatibility(snapshot), "tree": tree,
             "files": [{"path": "state.safetensors", "size": state_path.stat().st_size, "sha256": file_hash(state_path, check_cancel)}]}
    value["digest"] = digest(value)
    with (temporary / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    check_cancel()
    temporary.rename(destination)
    descriptor = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    verify_checkpoint(destination / "manifest.json", value["digest"], value["compatibility"], check_cancel)
    return {"relative_path": (destination / "manifest.json").relative_to(run_dir).as_posix(), "manifest_digest": value["digest"], "step": value["step"], "total_steps": value["total_steps"]}


def restore_checkpoint(path, expected_digest, snapshot, model, optimizer, check_cancel=lambda: None):
    import mlx.core as mx
    from mlx.utils import tree_flatten
    value = verify_checkpoint(path, expected_digest, compatibility(snapshot), check_cancel)
    arrays = mx.load(str(Path(path).parent / "state.safetensors"))
    used = set(); state = _unpack(value["tree"], arrays, used)
    if used != set(arrays) or set(state) != {"weights", "initial", "optimizer", "mlx_rng", "python_rng"}:
        raise CheckpointError("CHECKPOINT_INVALID", "检查点缺少完整优化轨迹状态")
    expected = dict(tree_flatten(model.trainable_parameters()))
    for name in ("weights", "initial"):
        if set(state[name]) != set(expected) or any(item.shape != expected[key].shape or item.dtype != expected[key].dtype for key, item in state[name].items()):
            raise CheckpointError("CHECKPOINT_INCOMPATIBLE", "检查点训练模块与当前模型不一致")
    expected_optimizer = dict(tree_flatten(optimizer.state))
    restored_optimizer = dict(tree_flatten(state["optimizer"]))
    if set(expected_optimizer) != set(restored_optimizer) or any(expected_optimizer[key].shape != item.shape or expected_optimizer[key].dtype != item.dtype for key, item in restored_optimizer.items()):
        raise CheckpointError("CHECKPOINT_INCOMPATIBLE", "检查点优化器状态不完整")
    if int(state["optimizer"]["step"].item()) != value["step"] or len(state["mlx_rng"]) != len(mx.random.state) or any(a.shape != b.shape or a.dtype != b.dtype for a, b in zip(state["mlx_rng"], mx.random.state)):
        raise CheckpointError("CHECKPOINT_INVALID", "检查点优化步或随机状态不一致")
    probe = random.Random(); probe.setstate(state["python_rng"])
    verify_checkpoint(path, expected_digest, value["compatibility"], check_cancel)
    model.load_weights(list(state["weights"].items()), strict=False)
    optimizer.state = state["optimizer"]
    # MLX 0.32 的随机状态为只读代理；通过公开的 64 位 seed 恢复同一双 uint32 key。
    key = state["mlx_rng"][0].tolist()
    mx.random.seed((int(key[0]) << 32) | int(key[1]))
    random.setstate(state["python_rng"])
    mx.eval(model.trainable_parameters(), optimizer.state, mx.random.state)
    return value["losses"], state["initial"]


class TrainingControl:
    def __init__(self, run_dir, snapshot, emit, check_cancel):
        self.run_dir, self.snapshot, self.emit, self.check_cancel = Path(run_dir), snapshot, emit, check_cancel
        self.seen, self.sequence, self.paused = set(), 0, None

    def safe_point(self, model, optimizer, initial, losses, sample_count):
        commands = self.run_dir / "control/commands"
        while True:
            self.check_cancel()
            pending = []
            if commands.exists():
                if commands.is_symlink() or commands.resolve() != commands:
                    raise CheckpointError("CHECKPOINT_INVALID", "控制命令目录不能经符号链接跳转")
                for path in commands.glob("*.json"):
                    if path.name in self.seen:
                        continue
                    _plain_file(path, 16384)
                    value = json.loads(path.read_text())
                    if not re.fullmatch(r"command-[a-zA-Z0-9-]+", value.get("command_id", "")) or path.stem != value["command_id"] or value.get("attempt_id") != self.snapshot.get("attempt_id") or type(value.get("sequence")) is not int or value["sequence"] <= self.sequence or value.get("action") not in {"pause", "resume"}:
                        raise CheckpointError("CONTROL_INVALID", "训练控制命令身份或顺序无效")
                    pending.append((value["sequence"], path, value))
            for sequence, path, command in sorted(pending):
                if sequence <= self.sequence:
                    raise CheckpointError("CONTROL_INVALID", "训练控制命令顺序重复")
                self.check_cancel(); self.seen.add(path.name); self.sequence = sequence
                response = {"command_id": command["command_id"], "action": command["action"]}
                try:
                    if command["action"] == "pause":
                        if not self.paused:
                            self.paused = save_checkpoint(self.run_dir, self.snapshot, model, optimizer, initial, losses, sample_count, self.check_cancel)
                        response.update(result="confirmed", checkpoint=self.paused)
                    else:
                        if not self.paused or command.get("checkpoint_digest") != self.paused["manifest_digest"]:
                            raise CheckpointError("CHECKPOINT_MISMATCH", "恢复命令与当前暂停检查点不一致")
                        saved_losses, saved_initial = restore_checkpoint(self.run_dir / self.paused["relative_path"], self.paused["manifest_digest"], self.snapshot, model, optimizer, self.check_cancel)
                        if saved_losses != losses:
                            raise CheckpointError("CHECKPOINT_INVALID", "检查点优化位置与当前暂停位置不一致")
                        initial.clear(); initial.update(saved_initial)
                        response.update(result="confirmed", checkpoint_digest=self.paused["manifest_digest"])
                        self.paused = None
                except Exception as error:
                    if getattr(error, "code", None) == "CANCELLED":
                        raise
                    response.update(result="failed", code=getattr(error, "code", "CHECKPOINT_WRITE_FAILED"), message=str(error)[:1000], continuing=self.paused is None)
                self.emit("control_result", **response)
            if not self.paused:
                return
            time.sleep(0.05)
