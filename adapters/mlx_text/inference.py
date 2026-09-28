"""固定本机文本组合的缓存配置与实际回读；不保存 KV 内容或跨请求复用。"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
from adapters.mlx_text.generation import FIELDS as GENERATION_FIELDS, resolve as resolve_generation

SCHEMA = 'mlx-inference-v2'
FIELDS = {'kv_precision', 'prefill_step_size'} | GENERATION_FIELDS
PRESETS = {
    'default': {'kv_precision': 'auto', 'prefill_step_size': 2048},
    'low_memory': {'kv_precision': 'q4', 'prefill_step_size': 512},
    'low_latency': {'kv_precision': 'auto', 'prefill_step_size': 4096},
}


class InferenceError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def resolve(runtime):
    precision = runtime.get('kv_precision', 'auto')
    block = runtime.get('prefill_step_size', 2048)
    if type(precision) is not str or precision not in {'auto', 'q4'}:
        raise InferenceError('UNSUPPORTED_PARAMETER', '推理缓存精度只接受 auto 或 q4。')
    if type(block) is not int or block not in {512, 2048, 4096}:
        raise InferenceError('UNSUPPORTED_PARAMETER', '提示词分块只接受 512、2048 或 4096 个词元。')
    return {'kv_precision': precision, 'prefill_step_size': block, 'kv_bits': 4 if precision == 'q4' else None,
            'kv_group_size': 64, 'quantized_kv_start': 0, 'max_kv_size': None,
            'prefix_cache': 'disabled', **resolve_generation(runtime)}


def identity(snapshot, effective, prompt_tokens, template_digest):
    """配方区分输入、基座、适配器和缓存策略；不使用可转移的历史缓存。"""
    value = {'schema_version': SCHEMA, 'model_manifest_digest': snapshot['model_manifest_digest'],
             'adapter_manifest_digest': snapshot.get('adapter_manifest_digest'),
             'tokenization_recipe_digest': effective.get('tokenization_recipe_digest') or snapshot.get('tokenization_recipe_digest'),
             'template_sha256': template_digest,
             'prompt_tokens_sha256': hashlib.sha256(json.dumps(prompt_tokens, separators=(',', ':')).encode()).hexdigest(),
             'prompt_tokens': len(prompt_tokens), 'engine': 'mlx', 'device_id': 'apple-gpu',
             'versions': {name: importlib.metadata.version(name) for name in ('mlx', 'mlx-lm')},
             'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'generation_source_sha256': hashlib.sha256((Path(__file__).parent / 'generation.py').read_bytes()).hexdigest(),
             'worker_source_sha256': hashlib.sha256((Path(__file__).resolve().parents[2] / 'workers/mlx_worker.py').read_bytes()).hexdigest(),
             'runtime': {name: effective[name] for name in ('seed', 'max_tokens', 'temperature', 'top_p', *sorted(resolve({})))}}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return value, hashlib.sha256(encoded.encode()).hexdigest()


def initial_cache_summary(cache, expected_layers=24):
    """建立后立即观察每层为空，拒绝传入已有缓存或模型自定义缓存。"""
    from mlx_lm.models.cache import KVCache
    if type(expected_layers) is not int or expected_layers not in (24, 28) or len(cache) != expected_layers or any(type(layer) is not KVCache for layer in cache):
        raise InferenceError('CACHE_CONFIG_MISMATCH', '当前模型必须新建对应层数的普通 KV 缓存。')
    layers = [{'index': index, 'class': type(layer).__name__, 'offset': layer.offset,
               'empty': layer.empty(), 'keys_absent': layer.keys is None,
               'values_absent': layer.values is None, 'nbytes': layer.nbytes}
              for index, layer in enumerate(cache)]
    if any(not layer['empty'] or not layer['keys_absent'] or not layer['values_absent'] or layer['offset'] != 0 or layer['nbytes'] != 0 for layer in layers):
        raise InferenceError('CACHE_NOT_EMPTY', '新运行的推理缓存并非全空，拒绝使用历史内容。')
    return {'initially_empty': True, 'layer_count': len(cache), 'layers': layers,
            'scope': '本次创建后、调用模型之前逐层读取；不导出缓存内容。'}


def cache_summary(cache, precision, expected_layers=24):
    """仅回读实际层类型、形状、精度与分配量；不序列化缓存中的用户内容。"""
    from mlx_lm.models.cache import KVCache, QuantizedKVCache
    expected = QuantizedKVCache if precision == 'q4' else KVCache
    if type(expected_layers) is not int or expected_layers not in (24, 28) or len(cache) != expected_layers or any(type(layer) is not expected for layer in cache):
        raise InferenceError('CACHE_CONFIG_MISMATCH', '实际推理缓存类型或层数与固定 Qwen 组合不符。')
    layers = []
    for index, layer in enumerate(cache):
        if layer.offset <= 0 or layer.keys is None or layer.values is None:
            raise InferenceError('CACHE_NOT_POPULATED', '生成后推理缓存为空，无法证明缓存策略已执行。')
        if precision == 'q4' and (layer.bits != 4 or layer.group_size != 64):
            raise InferenceError('CACHE_CONFIG_MISMATCH', '实际量化缓存精度或分组不符。')
        def arrays(value):
            return [{'shape': list(item.shape), 'dtype': str(item.dtype), 'nbytes': item.nbytes}
                    for item in (value if isinstance(value, (tuple, list)) else (value,))]
        layers.append({'index': index, 'class': type(layer).__name__, 'offset': layer.offset,
                       'nbytes': layer.nbytes, 'keys': arrays(layer.keys), 'values': arrays(layer.values),
                       'bits': layer.bits if precision == 'q4' else None,
                       'group_size': layer.group_size if precision == 'q4' else None})
    if len({layer['offset'] for layer in layers}) != 1:
        raise InferenceError('CACHE_CONFIG_MISMATCH', '实际推理缓存层的词元位置不一致。')
    return {'layer_count': len(cache), 'total_allocated_bytes': sum(layer['nbytes'] for layer in layers),
            'layers': layers, 'cross_request_reuse': False,
            'scope': '结束时 KV 数组分配字节；不代表进程或计算峰值，不包含模型权重。'}
