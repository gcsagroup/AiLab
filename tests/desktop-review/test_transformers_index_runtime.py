"""静态映射保持原类型、顺序和覆盖规则；坏索引必须拒绝。"""

import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("transformers_index_runtime", Path(__file__).resolve().parents[2] / "scripts/desktop/transformers_index_runtime.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def document():
    return {"schema_version": 1, "transformers_version": "4.57.6", "prefix": "models", "groups": [
        [["torch", "vision"], [["models.z", ["Shared", "Z"]], ["models.a", ["Shared", "A"]]]],
        [[], [["models.b", ["Shared", "B"]]]],
    ]}


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


def test_groups_modules_types_and_last_owner_are_preserved():
    actual = runtime.decode_models_index(encode(document()))
    assert list(actual) == [frozenset({"torch", "vision"}), frozenset()]
    assert list(actual[frozenset({"torch", "vision"})]) == ["models.z", "models.a"]
    assert all(type(tags) is frozenset and all(type(names) is set for names in modules.values()) for tags, modules in actual.items())
    owners = {name: module for modules in actual.values() for module, names in modules.items() for name in names}
    assert owners == {"Shared": "models.b", "Z": "models.z", "A": "models.a", "B": "models.b"}


@pytest.mark.parametrize("groups", [[], [[[], []]], [[[], [["models.empty", []]]]]])
def test_empty_maps_and_exports_keep_upstream_structure(groups):
    value = document()
    value["groups"] = groups
    actual = runtime.decode_models_index(encode(value))
    assert len(actual) == len(groups)


@pytest.mark.parametrize("field,value", [("schema_version", True), ("schema_version", 2), ("transformers_version", "4.58.0"), ("prefix", "models.albert"), ("groups", {})])
def test_wrong_version_scope_or_shape_is_rejected(field, value):
    data = document()
    data[field] = value
    with pytest.raises(ValueError):
        runtime.decode_models_index(encode(data))


@pytest.mark.parametrize("groups", [
    [None], [[[]]], [[[], {}]], [[["torch", "torch"], []]],
    [[[], []], [[], []]], [[[], [["models.a", []], ["models.a", []]]]],
    [[[], [["models.a", ["A", "A"]]]]], [[[], [["../outside", ["A"]]]]],
    [[[], [[1, ["A"]]]]], [[[], [["models.a", [1]]]]], [[[], [["models.a", "A"]]]],
])
def test_duplicate_or_malformed_mapping_is_rejected(groups):
    data = document()
    data["groups"] = groups
    with pytest.raises(ValueError):
        runtime.decode_models_index(encode(data))


@pytest.mark.parametrize("raw", [b"", b"[1]", b"null", b"{bad", b"x" * (runtime.MAX_INDEX_BYTES + 1)])
def test_invalid_or_oversized_document_is_rejected(raw):
    with pytest.raises(ValueError):
        runtime.decode_models_index(raw)


def test_duplicate_header_and_unknown_field_are_rejected():
    raw = encode(document()).replace(b'"schema_version": 1', b'"schema_version": 1, "schema_version": 1')
    with pytest.raises(ValueError, match="重复字段"):
        runtime.decode_models_index(raw)
    value = document()
    value["unexpected"] = True
    with pytest.raises(ValueError):
        runtime.decode_models_index(encode(value))


def test_load_reads_current_file_without_caching(tmp_path):
    path = tmp_path / runtime.INDEX_NAME
    first = document()
    path.write_bytes(encode(first))
    assert runtime.load_models_index(tmp_path / "__init__.py") == runtime.decode_models_index(encode(first))
    second = document()
    second["groups"] = [[[], [["models.changed", ["Current"]]]]]
    path.write_bytes(encode(second))
    assert runtime.load_models_index(tmp_path / "__init__.py") == {frozenset(): {"models.changed": {"Current"}}}


def test_symbolic_link_and_oversized_file_are_rejected(tmp_path):
    target = tmp_path / "target.json"
    target.write_bytes(encode(document()))
    path = tmp_path / runtime.INDEX_NAME
    path.symlink_to(target)
    with pytest.raises(OSError):
        runtime.load_models_index(tmp_path / "__init__.py")
    path.unlink()
    path.write_bytes(b" " * (runtime.MAX_INDEX_BYTES + 1))
    with pytest.raises(ValueError):
        runtime.load_models_index(tmp_path / "__init__.py")


@pytest.mark.parametrize("module", ["utils", "other.foo", "models"])
def test_module_must_belong_to_models_subtree(module):
    value = document()
    value["groups"] = [[[], [[module, ["A"]]]]]
    with pytest.raises(ValueError):
        runtime.decode_models_index(encode(value))


@pytest.mark.parametrize("failure", ["fdopen", "read", "fstat"])
def test_open_descriptor_is_closed_after_failures(tmp_path, monkeypatch, failure):
    (tmp_path / runtime.INDEX_NAME).write_bytes(encode(document()))
    original_fdopen, original_fstat = runtime.os.fdopen, runtime.os.fstat
    descriptors, calls = [], []

    class Stream:
        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.raw.__exit__(*args)

        def fileno(self):
            return self.raw.fileno()

        def read(self, size):
            if failure == "read":
                raise OSError("代表性读取故障")
            return self.raw.read(size)

    def opening(descriptor, *args):
        descriptors.append(descriptor)
        if failure == "fdopen":
            raise OSError("代表性文件包装故障")
        return Stream(original_fdopen(descriptor, *args))

    def inspecting(descriptor):
        calls.append(descriptor)
        if failure == "fstat" and len(calls) == 2:
            raise OSError("代表性读取后状态故障")
        return original_fstat(descriptor)

    monkeypatch.setattr(runtime.os, "fdopen", opening)
    monkeypatch.setattr(runtime.os, "fstat", inspecting)
    with pytest.raises(OSError, match="代表性"):
        runtime.load_models_index(tmp_path / "__init__.py")
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        original_fstat(descriptors[0])


def test_modification_during_read_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / runtime.INDEX_NAME
    path.write_bytes(encode(document()))
    original_fdopen = runtime.os.fdopen

    class Stream:
        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.raw.__exit__(*args)

        def fileno(self):
            return self.raw.fileno()

        def read(self, size):
            raw = self.raw.read(size)
            path.write_bytes(b"changed")
            return raw

    monkeypatch.setattr(runtime.os, "fdopen", lambda fd, *args: Stream(original_fdopen(fd, *args)))
    with pytest.raises(ValueError, match="读取期间变化"):
        runtime.load_models_index(tmp_path / "__init__.py")
