import json
import sys
import ast
from importlib.metadata import version, distribution

backend, raw = sys.argv[1:]
config = json.loads(raw)
if backend == 'hf':
    source = distribution('transformers').locate_file('transformers/models/auto/modeling_auto.py')
    mapping = None
    for node in ast.parse(source.read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MODEL_FOR_CAUSAL_LM_MAPPING_NAMES' for t in node.targets):
            if isinstance(node.value, ast.Call): mapping = dict(ast.literal_eval(node.value.args[0]))
    if mapping is None: raise RuntimeError('无法静态读取当前 Transformers 架构注册表')
    supported = config['model_type'] in mapping
    package = 'transformers'
else:
    from vllm import ModelRegistry
    supported = any(x in ModelRegistry.get_supported_archs() for x in config['architectures'])
    package = 'vllm'
print('@@AILAB ' + json.dumps({'status': 'supported' if supported else 'unsupported', 'version': version(package),
      'detail': '架构已注册' if supported else '当前环境未注册该架构'}))
