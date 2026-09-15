"""控制合同用独立 CPU 夹具；固定词元仅测试文件映射，不代表真实分词。"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.mlx_text import recipe, split_check

parser = argparse.ArgumentParser()
parser.add_argument('--snapshot', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
parser.add_argument('--controller-pid')
parser.add_argument('--fixture-mode', default='success')
args = parser.parse_args()
if args.fixture_mode == 'slow':
    time.sleep(30)
if args.fixture_mode == 'bad-json':
    print('PRIVATE_CHECK_STDOUT /Users/private/fixture token=private')
    print('PRIVATE_CHECK_STDERR', file=sys.stderr)
    sys.exit(1)
request = json.loads(args.snapshot.read_text())
model = Path(request['model_path'])
template = json.loads((model / 'tokenizer_config.json').read_text())['chat_template']
frozen_recipe, recipe_digest = recipe.build_recipe(model, SimpleNamespace(chat_template=template), 'train', request.get('max_seq_length', request.get('runtime', {}).get('max_seq_length')))
if args.fixture_mode == 'preflight':
    print(json.dumps({'can_submit': True, 'blocking': [], 'effective_config': request['runtime'], 'recipe': frozen_recipe,
                     'check_report': {'fixture_only': True}, 'tokenization_recipe_digest': recipe_digest}))
    sys.exit(0)
identity = {'checker_version': split_check.VERSION, 'checker_implementation_sha256': split_check.digest_file(Path(split_check.__file__)),
            'source_sha256': request['dataset_sha256'], 'model_manifest_digest': request['model_manifest_digest'], 'model_manifest_verification': 'control_service',
            'max_seq_length': request['max_seq_length'], 'runtime': split_check.RUNTIME, 'recipe': frozen_recipe, 'tokenization_recipe_digest': recipe_digest}
identity_digest = hashlib.sha256(split_check.canonical(identity)).hexdigest()
counts = Counter({name: 0 for name in ('input_samples', 'accepted_samples', 'excluded_samples', 'ignored_lines', 'supervised_tokens', 'shifted_supervised_tokens')})
checks, examples, exclusions = [], [], Counter()
for number, raw in enumerate(Path(request['dataset_path']).read_bytes().splitlines(keepends=True), 1):
    row = {'line': number, 'line_sha256': hashlib.sha256(raw).hexdigest(), 'messages_sha256': None, 'source_id': None, 'status': 'ignored', 'code': 'BLANK_LINE',
           'input_tokens': 0, 'supervised_tokens': 0, 'shifted_supervised_tokens': 0}
    if not raw.strip():
        counts['ignored_lines'] += 1
    else:
        sample = split_check.strict_json(raw)
        if set(sample) != {'source_id', 'messages'} or not sample['source_id'].strip():
            print(json.dumps({'schema_version': 1, 'kind': 'dataset-check', 'ok': False, 'failure_scope': 'input',
                              'blocking': [{'code': 'INVALID_SOURCE_DATASET', 'message': 'PRIVATE_UNTRUSTED_TEXT', 'line': number}]}))
            sys.exit(1)
        row.update(source_id=sample['source_id'], messages_sha256=hashlib.sha256(split_check.canonical({'messages': sample['messages']})).hexdigest())
        counts['input_samples'] += 1
        if any('[exclude]' in message['content'] for message in sample['messages']):
            row.update(status='excluded', code='SEQUENCE_TOO_LONG', input_tokens=None)
            counts['excluded_samples'] += 1
            exclusions['SEQUENCE_TOO_LONG'] += 1
        else:
            row.update(status='accepted', code=None, input_tokens=4, supervised_tokens=2, shifted_supervised_tokens=2)
            counts.update(accepted_samples=1, supervised_tokens=2, shifted_supervised_tokens=2)
            if len(examples) < 3:
                examples.append({'line': number, 'input_ids': [1, 2, 3, 4], 'labels': [-100, -100, 3, 4],
                                 'assistant_spans': [{'message_index': 1, 'start': 2, 'end': 4}], 'supervised_tokens': 2, 'shifted_supervised_tokens': 2})
    checks.append(row)
if args.fixture_mode == 'wrong-line':
    checks[-1]['line'] = 999
report = {'schema_version': 1, 'check_identity': identity, 'check_identity_digest': identity_digest, **counts,
          'exclusion_counts': dict(exclusions), 'token_labels_examples': examples, 'packing': False, 'ignore_index': -100, 'pad_id': 0, 'shift': 'input_ids[:-1] 预测 labels[1:]'}
args.output_dir.mkdir()
(args.output_dir / 'sample-checks.jsonl').write_bytes(b''.join(split_check.canonical(row) + b'\n' for row in checks))
(args.output_dir / 'check-report.json').write_bytes(split_check.canonical(report) + b'\n')
artifacts = {name: {'sha256': split_check.digest_file(args.output_dir / name), 'size_bytes': (args.output_dir / name).stat().st_size}
             for name in ('sample-checks.jsonl', 'check-report.json')}
print(json.dumps({'schema_version': 1, 'kind': 'dataset-check', 'ok': True, 'check_identity_digest': identity_digest,
                  'source_sha256': request['dataset_sha256'], **counts, 'artifacts': artifacts}))
