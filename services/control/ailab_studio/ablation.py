"""Lossless TOML editing: visual fields override advanced text; originals stay intact."""
import copy
import os
from pathlib import Path
import tomlkit

TEMPLATES = Path(__file__).parent / 'templates'


def flatten(value, prefix=''):
    result = {}
    for key, item in value.items():
        name = prefix + key
        if isinstance(item, dict):
            result.update(flatten(item, name + '.'))
        else:
            result[name] = item
    return result


def templates():
    basic = tomlkit.parse((TEMPLATES / 'abliterix.toml').read_text(encoding='utf-8')).unwrap()
    fields = flatten(basic)
    # A historical machine path is a reference, not a usable default output directory.
    fields['optimization.checkpoint_dir'] = ''
    fields['detection.llm_judge'] = False
    fields['model.backend'] = 'hf'
    return {'fields': fields, 'reference': (TEMPLATES / 'abliterix_all.toml').read_text(encoding='utf-8'),
            'advanced': '', 'notes': '表单字段覆盖同名 TOML 项。高级模板含历史路径，使用前请修改。'}


def compose(text, fields, model, output):
    try:
        doc = tomlkit.parse(text)
    except Exception as exc:
        raise ValueError(f'TOML 格式错误：{exc}') from exc
    for section in ('model', 'optimization', 'detection'):
        if section in doc and not isinstance(doc[section], dict):
            raise ValueError(f'{section} 必须为 TOML 表')
    allowed = flatten(tomlkit.parse((TEMPLATES / 'abliterix.toml').read_text(encoding='utf-8')).unwrap())
    for dotted, value in fields.items():
        if dotted not in allowed:
            raise ValueError(f'不是可视化配置字段：{dotted}')
        original = allowed[dotted]
        if type(value) is not type(original) and not (type(original) is float and type(value) in (int, float)):
            raise ValueError(f'{dotted} 的值类型错误')
        parts = dotted.split('.'); node = doc
        for part in parts[:-1]:
            if part not in node:
                node[part] = tomlkit.table()
            node = node[part]
            if not isinstance(node, dict):
                raise ValueError(f'{part} 必须为 TOML 表')
        node[parts[-1]] = copy.deepcopy(value)
    if 'model' not in doc: doc['model'] = tomlkit.table()
    doc['model']['model_id'] = model
    backend = doc['model'].get('backend', 'hf')
    if backend not in ('hf', 'vllm'): raise ValueError('推理后端应为 hf 或 vllm')
    doc['model']['backend'] = backend
    order = doc['model'].get('dtype_fallback_order')
    if order is not None:
        if not isinstance(order, list) or any(x not in ('float32', 'bfloat16', 'float16', 'auto') for x in order):
            raise ValueError('优先精度仅支持 float32、bfloat16、float16，留空自动选择')
        if not order: del doc['model']['dtype_fallback_order']
    if doc.get('steering', {}).get('steering_mode', 'direct') not in ('direct', 'lora'):
        raise ValueError('修改方式应为 direct 或 lora')
    if 'optimization' not in doc: doc['optimization'] = tomlkit.table()
    checkpoint = doc['optimization'].get('checkpoint_dir')
    if not checkpoint:
        doc['optimization']['checkpoint_dir'] = str(Path(output) / 'checkpoints')
    elif not Path(checkpoint).is_absolute():
        raise ValueError('检查点目录必须是绝对路径，或留空使用任务目录')
    trials = doc['optimization'].get('num_trials', 1)
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise ValueError('试验次数必须大于零')
    detection = doc.get('detection', {})
    if detection.get('llm_judge') and not os.environ.get(detection.get('llm_judge_api_key_env', '')):
        raise ValueError('已启用 LLM 裁判，但服务进程中缺少指定 API Key 环境变量')
    doc['non_interactive'] = True
    doc['non_interactive_output_dir'] = str(Path(output) / 'model')
    return tomlkit.dumps(doc)
