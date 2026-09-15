"""自包含控制服务的打包入口，不包含模型或训练依赖。"""

import hashlib
import json
from pathlib import Path
import sys

from ailab_control.__main__ import main


def verify_source_contract():
    from adapters.nvidia_text import adapter
    root = Path(adapter.__file__).resolve().parents[2]
    sources = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
               for prefix in ('workers', 'adapters') for path in (root / prefix).rglob('*.py')}
    return {'source_code_digest': adapter.source_identity(), 'sources': sources,
            'model_execution': False, 'device_probe': False}

if __name__ == "__main__":
    if sys.argv[1:] == ['--verify-source-contract']:
        print(json.dumps(verify_source_contract(), ensure_ascii=False, sort_keys=True))
    else:
        main()
