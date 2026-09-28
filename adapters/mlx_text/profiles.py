"""限定 Qwen 文本结构；结构匹配不代表衍生权重或业务质量已通过。"""


def model_profile(config):
    if not isinstance(config, dict) or config.get('model_type') != 'qwen2' or any(type(config.get(key)) is not int for key in ('hidden_size', 'num_hidden_layers')):
        raise ValueError('模型结构不属于已适配的 Qwen2.5 文本组合')
    for name, hidden, layers, heads, kv_heads, intermediate, vocab, tied in (
        ('qwen25-0.5b', 896, 24, 14, 2, 4864, 151936, True),
        ('qwen25-7b', 3584, 28, 28, 4, 18944, 152064, False),
    ):
        if config.get('hidden_size') != hidden or config.get('num_hidden_layers') != layers:
            continue
        geometry = {'num_attention_heads': heads, 'num_key_value_heads': kv_heads,
                    'intermediate_size': intermediate, 'vocab_size': vocab,
                    'tie_word_embeddings': tied}
        # 保留旧组合的精简配置合同；新组合须显式提供完整结构字段。
        if name == 'qwen25-7b' and any(type(config.get(key)) is not type(value) or config[key] != value for key, value in geometry.items()):
            break
        return {'name': name, 'hidden_size': hidden, 'num_hidden_layers': layers,
                'num_attention_heads': heads, 'num_key_value_heads': kv_heads,
                'head_dim': hidden // heads}
    raise ValueError('仅适配 Qwen2.5-0.5B 与 7B 的固定文本结构')


def adapter_shapes(profile, layers, rank):
    """MLX LoRA A 为输入×秩，B 为秩×输出；不同基座不能互换。"""
    if type(layers) is not int or not 1 <= layers <= profile['num_hidden_layers'] or type(rank) is not int or not 1 <= rank <= 32:
        raise ValueError('适配器层数或秩超出模型范围')
    shapes = {}
    for layer in range(profile['num_hidden_layers'] - layers, profile['num_hidden_layers']):
        for module, width in [('q_proj', profile['hidden_size']), ('v_proj', profile['num_key_value_heads'] * profile['head_dim'])]:
            prefix = f'model.layers.{layer}.self_attn.{module}.'
            shapes[prefix + 'lora_a'] = [profile['hidden_size'], rank]
            shapes[prefix + 'lora_b'] = [rank, width]
    return shapes
