"""本产品转换产物的纯文件检查；不将外部可执行模型作为普通权重导入。"""

from .assets import file_hash, regular_path, safe_json
from .storage import Fault, digest

FORMATS = {"torchscript": "model.pt", "onnx": "model.onnx", "coreml": "model.mlpackage"}


def format_manifest(directory):
    directory = regular_path(directory)
    metadata = safe_json(directory / "ailab-format.json")
    target = metadata.get("format")
    if target not in FORMATS or metadata.get("schema_version") != 1 or metadata.get("entrypoint") != FORMATS[target] or metadata.get("context_length") != 128 or metadata.get("precision") != "float32" or metadata.get("device") != "cpu":
        raise Fault("CONVERTED_FORMAT_INVALID", "转换格式、形状或运行设备不符合已验证合同。", 409)
    files = sorted(directory.rglob("*"))
    if len(files) > 100:
        raise Fault("CONVERTED_FORMAT_INVALID", "转换目录文件过多。", 409)
    manifest = []
    support = {"ailab-format.json", "config.json", "tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja", "generation_config.json", "LICENSE", "README.md"}
    for path in files:
        regular_path(path)
        if path.is_dir():
            continue
        relative = path.relative_to(directory).as_posix()
        model_file = relative == FORMATS[target] or target == "onnx" and relative == "model.onnx.data" or target == "coreml" and relative in {"model.mlpackage/Manifest.json", "model.mlpackage/Data/com.apple.CoreML/model.mlmodel", "model.mlpackage/Data/com.apple.CoreML/weights/weight.bin"}
        if relative not in support and not model_file:
            raise Fault("CONVERTED_FORMAT_INVALID", "转换模型包含合同以外的文件。", 409)
        if path.suffix == ".json":
            value = safe_json(path)
            if value.get("auto_map") or value.get("trust_remote_code"):
                raise Fault("MODEL_LOAD_TRUST_REQUIRED", "转换产物不接受自定义代码。", 409)
        manifest.append({"path": relative, "size": path.stat().st_size, "sha256": file_hash(path)})
    if not (directory / FORMATS[target]).exists() or not (directory / "tokenizer.json").is_file() or not (directory / "config.json").is_file():
        raise Fault("CONVERTED_FORMAT_INVALID", "转换权重、配置或分词器不完整。", 409)
    return {"manifest": manifest, "manifest_digest": digest(manifest), "total_bytes": sum(item["size"] for item in manifest), "metadata": metadata}
