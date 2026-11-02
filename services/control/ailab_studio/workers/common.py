import base64
import io
import json
import os
from pathlib import Path


def emit(event_type, **value):
    print('@@AILAB ' + json.dumps({'type': event_type, **value}, ensure_ascii=False, allow_nan=False), flush=True)


def finish(config, result):
    path = Path(config['output_dir']) / 'result.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)
    emit('result', **result)


def image(value):
    from PIL import Image
    data = base64.b64decode(value.split(',', 1)[1], validate=True)
    result = Image.open(io.BytesIO(data))
    if result.width * result.height > 20000000: raise ValueError('图片像素超过上限')
    result.load()
    return result.convert('RGB')


def device(requested):
    import torch
    selected = requested
    if selected == 'auto':
        selected = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
    if selected == 'cuda' and not torch.cuda.is_available(): raise ValueError('当前环境 CUDA 不可用')
    if selected == 'mps' and not torch.backends.mps.is_available(): raise ValueError('当前环境 MPS 不可用')
    return selected
