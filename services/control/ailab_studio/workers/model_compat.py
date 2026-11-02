"""Narrow API bridge for local Spark 2.5 code; no weight or source-file edits."""
import functools
import inspect
import json
import sys
from pathlib import Path
from common import emit


def install(model_path, trusted):
    if not trusted: return {}
    document = json.loads((Path(model_path) / 'config.json').read_text(encoding='utf-8'))
    if document.get('model_type') != 'spark2_5': return {}
    import transformers.masking_utils as masks
    for name in ('create_causal_mask', 'create_sliding_window_causal_mask'):
        original = getattr(masks, name)
        if getattr(original, '_ailab_legacy_bridge', False): continue
        parameters = inspect.signature(original).parameters
        if 'inputs_embeds' not in parameters or 'cache_position' in parameters: continue

        def bridge(fn):
            @functools.wraps(fn)
            def compatible(*args, **kwargs):
                if 'input_embeds' in kwargs: kwargs['inputs_embeds'] = kwargs.pop('input_embeds')
                position = kwargs.pop('cache_position', None)
                if kwargs.get('position_ids') is None and position is not None:
                    kwargs['position_ids'] = position.unsqueeze(0)
                return fn(*args, **kwargs)
            compatible._ailab_legacy_bridge = True
            return compatible
        setattr(masks, name, bridge(original))
    emit('status', text='已启用 Spark 2.5 掩码接口兼容：input_embeds → inputs_embeds，使用 position_ids 传递位置。模型文件保持原样。')
    from transformers.dynamic_module_utils import get_class_from_dynamic_module
    reference = document.get('auto_map', {}).get('AutoModelForCausalLM')
    if reference:
        cls = get_class_from_dynamic_module(reference, model_path, local_files_only=True)
        base = getattr(sys.modules[cls.__module__], 'Spark2_5Model', None)
        if base is not None and not getattr(base.forward, '_ailab_hidden_states', False):
            forward = base.forward

            @functools.wraps(forward)
            def with_hidden_states(self, *args, **kwargs):
                if not kwargs.get('output_hidden_states', getattr(self.config, 'output_hidden_states', False)):
                    return forward(self, *args, **kwargs)
                states = []
                # HF residual convention: input to each decoder layer, then final normalized output.
                handles = [layer.register_forward_pre_hook(lambda module, values: states.append(values[0])) for layer in self.layers]
                try:
                    result = forward(self, *args, **kwargs)
                    result['hidden_states'] = (*states, result.last_hidden_state)
                    return result
                finally:
                    for handle in handles: handle.remove()
            with_hidden_states._ailab_hidden_states = True
            base.forward = with_hidden_states
            emit('status', text='已启用 Spark 2.5 隐藏状态输出：提取各层输入和最终归一化输出，供 HF 消融分析使用。')
    # Local Spark code expects B,H,S,D from eager attention, unlike generic SDPA adapters.
    return {'attn_implementation': 'eager'}
