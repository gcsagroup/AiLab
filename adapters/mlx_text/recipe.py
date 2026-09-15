"""可审计的 Qwen 多轮助手监督配方，不使用库默认的全词元损失。"""

import hashlib
import json
from collections import Counter
from pathlib import Path

RECIPE_ID = "qwen25-assistant-only-v1"
TEMPLATE_SHA256 = "cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f"


def build_recipe(model_path, tokenizer, operation, max_seq_length):
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(model_path).iterdir()) if p.name in {"tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "chat_template.jinja"}}
    recipe = {"recipe_id": {"train": RECIPE_ID, "generate": "qwen25-generation-v1", "quantize": "qwen25-quantization-v1", "evaluate": "qwen25-evaluation-v1"}[operation], "tokenizer_files": files, "template_sha256": hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(), "max_seq_length": max_seq_length, "packing": False, "supervision": "assistant_content_and_im_end" if operation == "train" else None, "recipe_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if operation == "evaluate":
        recipe["evaluation_implementation_sha256"] = hashlib.sha256(Path(__file__).with_name("evaluation.py").read_bytes()).hexdigest()
    return recipe, hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()


class RecipeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def tokenize_sample(tokenizer, sample, max_seq_length):
    template = tokenizer.chat_template
    if not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != TEMPLATE_SHA256:
        raise RecipeError("TEMPLATE_UNSUPPORTED", "聊天模板未通过当前监督配方验证")
    if not isinstance(sample, dict) or set(sample) != {"messages"}:
        raise RecipeError("INVALID_SAMPLE", "样本必须且只能包含 messages")
    messages = sample["messages"]
    if not isinstance(messages, list) or not messages:
        raise RecipeError("NO_SUPERVISION", "样本没有对话")
    expected = "user"
    assistant_count = 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise RecipeError("MEDIA_OR_TOOLS_UNSUPPORTED", "首个配方只接受纯文本 role 与 content")
        role, content = message["role"], message["content"]
        if not isinstance(content, str):
            raise RecipeError("MEDIA_OR_TOOLS_UNSUPPORTED", "当前配方不支持媒体内容")
        if not content.strip():
            raise RecipeError("EMPTY_CONTENT", "消息或回答为空")
        if any(marker in content for marker in tokenizer.all_special_tokens):
            raise RecipeError("RESERVED_TOKEN", "消息包含模板保留标记")
        if index == 0 and role == "system":
            continue
        if role != expected:
            raise RecipeError("INVALID_ROLES", "需要用户与助手交替的完整对话")
        expected = "assistant" if role == "user" else "user"
        assistant_count += role == "assistant"
    if not assistant_count or messages[-1]["role"] != "assistant":
        raise RecipeError("NO_SUPERVISION", "样本必须以完整助手回答结束")
    ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if len(ids) > max_seq_length:
        raise RecipeError("SEQUENCE_TOO_LONG", "样本超过序列长度，完整排除且不截断")
    labels = [-100] * len(ids)
    spans = []
    eos = tokenizer.convert_tokens_to_ids("<|im_end|>")
    if eos != 151645:
        raise RecipeError("SPECIAL_TOKEN_MISMATCH", "结束标记编号与已验证模板不同")
    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue
        prefix = tokenizer.apply_chat_template(messages[:index], tokenize=True, add_generation_prompt=True)
        through = tokenizer.apply_chat_template(messages[:index + 1], tokenize=True, add_generation_prompt=False)
        if ids[:len(prefix)] != prefix or ids[:len(through)] != through:
            raise RecipeError("ROLE_MASK_UNRELIABLE", "分词前缀不稳定，不能确定助手位置")
        ends = [i for i in range(len(prefix), len(through)) if ids[i] == eos]
        if len(ends) != 1:
            raise RecipeError("ROLE_MASK_UNRELIABLE", "助手回答结束位置不唯一")
        end = ends[0] + 1
        if end <= len(prefix) + 1:
            raise RecipeError("NO_SUPERVISION", "回答没有有效内容词元")
        labels[len(prefix):end] = ids[len(prefix):end]
        spans.append({"message_index": index, "start": len(prefix), "end": end})
    return {"input_ids": ids, "labels": labels, "assistant_spans": spans,
            "supervised_tokens": sum(x != -100 for x in labels)}


def collate_samples(samples, pad_id):
    """标签仍与输入位置对齐；损失函数只在训练处移位一次。"""
    width = max(len(sample["input_ids"]) for sample in samples)
    return {
        "input_ids": [s["input_ids"] + [pad_id] * (width - len(s["input_ids"])) for s in samples],
        "labels": [s["labels"] + [-100] * (width - len(s["labels"])) for s in samples],
    }


def check_dataset(tokenizer, dataset_path, max_seq_length, check_cancel=lambda: None):
    samples, exclusions = [], []
    with Path(dataset_path).open() as stream:
        for line_no, line in enumerate(stream, 1):
            check_cancel()
            if not line.strip():
                continue
            try:
                sample = tokenize_sample(tokenizer, json.loads(line), max_seq_length)
                sample["line"] = line_no
                samples.append(sample)
            except (RecipeError, json.JSONDecodeError) as exc:
                exclusions.append({"line": line_no, "code": getattr(exc, "code", "INVALID_JSON"), "message": str(exc)})
    report = {"recipe_id": RECIPE_ID, "template_sha256": TEMPLATE_SHA256, "input_samples": len(samples) + len(exclusions), "accepted_samples": len(samples), "excluded_samples": len(exclusions), "exclusions": exclusions, "exclusion_counts": dict(Counter(item["code"] for item in exclusions)), "supervised_tokens": sum(s["supervised_tokens"] for s in samples), "token_labels_examples": samples[:3], "packing": False, "pad_id": tokenizer.pad_token_id, "ignore_index": -100, "shift": "input_ids[:-1] 预测 labels[1:]"}
    return samples, report
