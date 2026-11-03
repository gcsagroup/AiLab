import json
import os
from pathlib import Path
import sys

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'


def main():
    config = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    if config['kind'] == 'sft':
        from sft import run
        run(config)
    else:
        from common import emit
        from inference import llama, vllm, media
        emit('model_state', phase='loading', text='正在加载模型')
        try:
            {'llama': llama, 'vllm': vllm, 'diffusers': media}[config['engine']](config)
        finally:
            # The supervisor's confirmed process exit is the resource-release boundary.
            emit('model_state', phase='unloading', text='正在卸载模型并退出推理进程')


if __name__ == '__main__': main()
