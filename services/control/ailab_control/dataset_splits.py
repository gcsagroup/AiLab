"""先用固定 CPU 配方检查，再按来源组预览并原子登记独立子集。"""

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
from types import SimpleNamespace

from .assets import copy_asset, file_hash, regular_path, verify_manifest
from .storage import Fault, digest, encode, identifier, now

ALGORITHM = 'source-group-sha256-v1'
ACTIVE = {'preparing', 'cancelling'}
COUNTS = ('input_samples', 'accepted_samples', 'excluded_samples', 'ignored_lines', 'supervised_tokens', 'shifted_supervised_tokens')
PROOF_FILES = ('split-manifest.json', 'sample-checks.jsonl', 'check-report.json')
PROOF_FIELDS = {'schema_version', 'algorithm', 'source_dataset_id', 'source_version_id', 'source_manifest_digest', 'model_id', 'model_manifest_digest',
    'max_seq_length', 'split_seed', 'validation_fraction_bps', 'counts', 'check_identity_digest', 'tokenization_recipe_digest', 'train_manifest', 'validation_manifest',
    'group_assignments', 'checks_manifest', 'validation_use', 'duplicate_policy', 'train_dataset_id', 'train_version_id', 'validation_dataset_id', 'validation_version_id', 'split_digest'}
HEX = re.compile(r'[0-9a-f]{64}')
SPLIT_REF_FIELDS = ('id', 'split_digest', 'plan_digest', 'manifest_digest', 'source_dataset_id', 'source_version_id', 'source_manifest_digest',
    'train_dataset_id', 'train_version_id', 'train_manifest_digest', 'validation_dataset_id', 'validation_version_id', 'validation_manifest_digest',
    'check_identity_digest', 'tokenization_recipe_digest', 'max_seq_length', 'split_seed', 'validation_fraction_bps')
ISSUES = {
    'INVALID_SOURCE_DATASET': '原件每行必须提供有效的 source_id 和 messages，请修正后重新导入。',
    'TOKENIZER_ENVIRONMENT_UNAVAILABLE': '缺少已验证的 CPU 分词依赖。',
    'TOKENIZER_VERSION_UNSUPPORTED': '当前 Python 或分词依赖版本未通过固定配方验证。',
    'RECIPE_VERSION_UNSUPPORTED': '监督配方源码与已验证版本不同。',
    'TOKENIZER_IDENTITY_UNSUPPORTED': '分词文件与固定 Qwen tokenizer 不同。',
    'SUPERVISION_CONTRACT_MISMATCH': '监督计数与实际标签不一致，整次检查已停止。',
    'INVALID_CHECK_REQUEST': '分词检查请求无效，请重新准备计划。',
    'INVALID_SOURCE_ID': '原件需要非空且有效的 source_id 来源组。',
    'INVALID_SOURCE_SAMPLE': '原件每行必须仅包含 source_id 和 messages。',
    'INVALID_SOURCE_JSON': '原件包含无效 JSON、重复键或无效编码。',
    'DATASET_CHANGED': '原件在检查期间发生变化，请重新准备计划。',
    'CHECK_IO_FAILED': '检查文件读写未完成，未生成可应用结果。',
    'TOKENIZER_UNVERIFIED': '分词器文件未通过固定来源核验。',
    'TOKENIZER_CHANGED': '分词环境已变化，请重新准备计划。',
    'RUNTIME_UNSUPPORTED': 'CPU 分词检查依赖版本未通过验证。',
    'RECIPE_UNVERIFIED': '监督配方与固定版本不一致。',
    'TEMPLATE_UNSUPPORTED': '聊天模板不属于已验证的监督配方。',
    'SPECIAL_TOKEN_MISMATCH': '分词器特殊词元与监督配方不一致。',
    'ROLE_MASK_UNRELIABLE': '无法可靠确定助手监督位置。',
}


def failure(code, message):
    raise Fault(code, message, 409)


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('JSON 键重复')
            result[key] = item
        return result
    def invalid(_value):
        raise ValueError('JSON 数值无效')
    return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid)


def manifest(directory):
    return [{'path': item.name, 'size': item.stat().st_size, 'sha256': file_hash(item)} for item in sorted(directory.iterdir()) if item.is_file()]


def staged_manifest(directory):
    return [{'path': item.relative_to(directory).as_posix(), 'size': item.stat().st_size, 'sha256': file_hash(item)} for item in sorted(directory.rglob('*')) if item.is_file()]


def split_content_identity(proof):
    """内容身份不含数据库 ID、时间、绝对路径或派生版本随机号。"""
    names = ('schema_version', 'algorithm', 'source_manifest_digest', 'model_manifest_digest', 'max_seq_length', 'split_seed',
             'validation_fraction_bps', 'counts', 'check_identity_digest', 'tokenization_recipe_digest', 'train_manifest',
             'validation_manifest', 'group_assignments', 'checks_manifest', 'validation_use', 'duplicate_policy')
    return {name: proof[name] for name in names}


def valid_manifest(items, names):
    return (isinstance(items, list) and len(items) == len(names) and all(isinstance(item, dict) and set(item) == {'path', 'size', 'sha256'}
            and type(item['size']) is int and item['size'] >= 0 and isinstance(item['sha256'], str) and HEX.fullmatch(item['sha256']) for item in items)
            and {item['path'] for item in items} == set(names))


def portable_split_ref(ref):
    """固定引用白名单；不接受路径或未知扩展进入可移植报告。"""
    if not isinstance(ref, dict) or set(ref) != set(SPLIT_REF_FIELDS):
        failure('DATASET_SPLIT_CHANGED', '来源组引用字段不完整或含未知扩展。')
    for name in SPLIT_REF_FIELDS:
        value = ref[name]
        if name.endswith('digest'):
            valid = isinstance(value, str) and HEX.fullmatch(value)
        elif name in {'max_seq_length', 'split_seed', 'validation_fraction_bps'}:
            low, high = {'max_seq_length': (32, 2048), 'split_seed': (0, 2**32 - 1), 'validation_fraction_bps': (1, 9999)}[name]
            valid = type(value) is int and low <= value <= high
        else:
            prefix = 'dataset-split' if name == 'id' else 'version' if name.endswith('version_id') else 'dataset'
            valid = isinstance(value, str) and re.fullmatch(prefix + r'-[0-9a-f]{32}', value)
        if not valid:
            failure('DATASET_SPLIT_CHANGED', '来源组引用包含无效身份字段。')
    return {name: ref[name] for name in SPLIT_REF_FIELDS}


def verify_check_report(report, rows=None):
    """输出可以导出为证明，所有层级只保留合同已声明的字段。"""
    from adapters.mlx_text.split_check import RUNTIME, SAMPLE_EXCLUSIONS, VERSION
    from adapters.mlx_text.recipe import RECIPE_ID, TEMPLATE_SHA256
    def keys(value, names):
        if not isinstance(value, dict) or set(value) != set(names):
            failure('DATASET_CHECK_OUTPUT_INVALID', '监督检查包含未知字段或缺少固定字段。')
    def checksum(value):
        return isinstance(value, str) and HEX.fullmatch(value)
    keys(report, ('schema_version', 'check_identity', 'check_identity_digest', *COUNTS, 'exclusion_counts', 'token_labels_examples', 'packing', 'ignore_index', 'pad_id', 'shift'))
    identity = report['check_identity']
    keys(identity, ('checker_version', 'checker_implementation_sha256', 'source_sha256', 'model_manifest_digest', 'model_manifest_verification', 'max_seq_length', 'runtime', 'recipe', 'tokenization_recipe_digest'))
    if (type(report['schema_version']) is not int or report['schema_version'] != 1 or report['packing'] is not False or type(report['ignore_index']) is not int or report['ignore_index'] != -100
            or type(report['pad_id']) is not int or report['pad_id'] < 0 or report['shift'] != 'input_ids[:-1] 预测 labels[1:]'
            or any(type(report[name]) is not int or report[name] < 0 for name in COUNTS)
            or identity['checker_version'] != VERSION or identity['model_manifest_verification'] != 'control_service'
            or identity['runtime'] != RUNTIME or type(identity['max_seq_length']) is not int or not 32 <= identity['max_seq_length'] <= 2048
            or any(not checksum(identity[name]) for name in ('checker_implementation_sha256', 'source_sha256', 'model_manifest_digest', 'tokenization_recipe_digest'))
            or digest(identity) != report['check_identity_digest']):
        failure('DATASET_CHECK_OUTPUT_INVALID', '监督检查身份、范围或计数无效。')
    recipe = identity['recipe']
    keys(recipe, ('recipe_id', 'tokenizer_files', 'template_sha256', 'max_seq_length', 'packing', 'supervision', 'recipe_implementation_sha256'))
    files = recipe['tokenizer_files']
    if (not isinstance(files, dict) or not {'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt'} <= set(files) <= {'tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt', 'chat_template.jinja'}
            or any(not checksum(value) for value in files.values()) or recipe['recipe_id'] != RECIPE_ID or recipe['template_sha256'] != TEMPLATE_SHA256
            or not checksum(recipe['recipe_implementation_sha256']) or type(recipe['max_seq_length']) is not int or recipe['max_seq_length'] != identity['max_seq_length'] or recipe['packing'] is not False
            or recipe['supervision'] != 'assistant_content_and_im_end' or hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest() != identity['tokenization_recipe_digest']):
        failure('DATASET_CHECK_OUTPUT_INVALID', '监督配方或分词文件身份无效。')
    exclusions = report['exclusion_counts']
    if not isinstance(exclusions, dict) or not set(exclusions) <= SAMPLE_EXCLUSIONS or any(type(value) is not int or value < 1 for value in exclusions.values()) or sum(exclusions.values()) != report['excluded_samples']:
        failure('DATASET_CHECK_OUTPUT_INVALID', '样本排除原因或计数无效。')
    examples = report['token_labels_examples']
    if not isinstance(examples, list) or len(examples) != min(3, report['accepted_samples']):
        failure('DATASET_CHECK_OUTPUT_INVALID', '监督预览必须对应前最多三条有效样本。')
    for index, sample in enumerate(examples):
        keys(sample, ('line', 'input_ids', 'labels', 'assistant_spans', 'supervised_tokens', 'shifted_supervised_tokens'))
        if any(type(sample[name]) is not int or sample[name] < 1 for name in ('line', 'supervised_tokens', 'shifted_supervised_tokens')):
            failure('DATASET_CHECK_OUTPUT_INVALID', '监督预览样本行号或计数无效。')
        ids, labels, spans = sample['input_ids'], sample['labels'], sample['assistant_spans']
        if (not isinstance(ids, list) or not 1 <= len(ids) <= identity['max_seq_length'] or any(type(value) is not int or value < 0 for value in ids)
                or not isinstance(labels, list) or len(labels) != len(ids) or any(type(value) is not int or value not in (-100, ids[position]) for position, value in enumerate(labels))
                or sum(value != -100 for value in labels) != sample['supervised_tokens'] or sum(value != -100 for value in labels[1:]) != sample['shifted_supervised_tokens']
                or not isinstance(spans, list) or not spans):
            failure('DATASET_CHECK_OUTPUT_INVALID', '监督预览词元、标签或边界无效。')
        positions = set()
        for span in spans:
            keys(span, ('message_index', 'start', 'end'))
            if any(type(value) is not int for value in span.values()) or span['message_index'] < 0 or not 0 <= span['start'] < span['end'] <= len(labels) or positions.intersection(range(span['start'], span['end'])):
                failure('DATASET_CHECK_OUTPUT_INVALID', '监督预览的助手范围无效。')
            positions.update(range(span['start'], span['end']))
        if positions != {position for position, value in enumerate(labels) if value != -100}:
            failure('DATASET_CHECK_OUTPUT_INVALID', '监督标签和助手范围不一致。')
        if rows is not None:
            line, original = rows[index]
            if sample['line'] != line or any(span['message_index'] >= len(original['messages']) or original['messages'][span['message_index']]['role'] != 'assistant' for span in spans):
                failure('DATASET_CHECK_OUTPUT_INVALID', '监督预览不是原件前几条有效样本的助手范围。')


def preview_from_report(plan, report, prepared=None):
    recipe = report['check_identity']['recipe']
    files = [item for items in (prepared or {}).values() for item in items]
    return {**{name: plan[name] for name in ('source_version_id', 'source_manifest_digest', 'model_manifest_digest')},
            'check_identity_digest': report['check_identity_digest'], 'tokenization_recipe_digest': report['check_identity']['tokenization_recipe_digest'],
            'tokenizer_files': recipe['tokenizer_files'], 'recipe_implementation_sha256': recipe['recipe_implementation_sha256'],
            'exclusion_counts': report['exclusion_counts'], 'token_labels_examples': report['token_labels_examples'],
            'max_samples': 3, 'new_files': len(files), 'new_bytes': sum(item['size'] for item in files)}


def verify_ready_plan(plan, get_dataset, get_model, resolve_path=lambda path: path):
    """ready 阶段的备份与应用共用精确闭包核验，旧请求路径永不执行。"""
    try:
        if plan.get('status') != 'ready':
            failure('DATASET_SPLIT_NOT_READY', '仅已完成的来源组预览可以应用。')
        directory = Path(resolve_path(plan['storage_path']))
        names = ['request.json', 'check/sample-checks.jsonl', 'check/check-report.json', 'train/train.jsonl', 'validation/validation.jsonl',
                 'proof/split-manifest.json', 'proof/sample-checks.jsonl', 'proof/check-report.json']
        if not valid_manifest(plan['staged_manifest'], names):
            failure('DATASET_SPLIT_PLAN_CHANGED', '计划暂存必须包含固定的八份完整文件。')
        verify_manifest(directory, plan['staged_manifest'])
        if not isinstance(plan['prepared'], dict) or set(plan['prepared']) != {'train', 'validation', 'proof'}:
            failure('DATASET_SPLIT_PLAN_CHANGED', '计划缺少两份子集和独立证明。')
        for role in ('train', 'validation', 'proof'):
            if not valid_manifest(plan['prepared'][role], PROOF_FILES if role == 'proof' else [role + '.jsonl']):
                failure('DATASET_SPLIT_PLAN_CHANGED', '计划的派生文件清单无效。')
            verify_manifest(directory / role, plan['prepared'][role])
        source, model = get_dataset(plan['source_dataset_id']), get_model(plan['model_id'])
        if source['project_id'] != plan['project_id'] or model['project_id'] != plan['project_id'] or source['manifest'] != plan['source_manifest'] or model['manifest'] != plan['model_manifest'] or model['manifest_digest'] != plan['model_manifest_digest'] or digest(model['manifest']) != model['manifest_digest']:
            failure('DATASET_SPLIT_PLAN_CHANGED', '来源组预览引用的源文件或模型清单不一致。')
        verify_manifest(Path(resolve_path(model['storage_path'])), model['manifest'])
        request = strict_json((directory / 'request.json').read_bytes())
        if (not isinstance(request, dict) or set(request) != {'schema_version', 'dataset_path', 'dataset_sha256', 'model_path', 'model_manifest_digest', 'max_seq_length'}
                or type(request['schema_version']) is not int or request['schema_version'] != 1 or request['dataset_sha256'] != source['manifest'][0]['sha256']
                or request['model_manifest_digest'] != model['manifest_digest'] or type(request['max_seq_length']) is not int or request['max_seq_length'] != plan['max_seq_length']
                or any(not isinstance(request[name], str) or not Path(request[name]).is_absolute() for name in ('dataset_path', 'model_path'))):
            failure('DATASET_SPLIT_PLAN_CHANGED', '冻结 CPU 请求身份不一致。')
        intent = plan['apply_intent']
        if not isinstance(intent, dict) or set(intent) != {'split_id', 'train_dataset_id', 'train_version_id', 'validation_dataset_id', 'validation_version_id'}:
            failure('DATASET_SPLIT_PLAN_CHANGED', '计划缺少固定登记意图。')
        split = {name: plan[name] for name in ('project_id', 'plan_digest', 'split_digest', 'source_dataset_id', 'source_version_id', 'source_manifest_digest', 'model_id', 'model_manifest_digest', 'max_seq_length', 'split_seed', 'validation_fraction_bps', 'check_identity_digest', 'tokenization_recipe_digest', 'counts')}
        split.update(id=intent['split_id'], schema_version=1, algorithm=ALGORITHM, status='ready', storage_path=str(Path(plan['storage_path']) / 'proof'),
                     manifest=plan['prepared']['proof'], manifest_digest=digest(plan['prepared']['proof']))
        children = {}
        for role in ('train', 'validation'):
            items = plan['prepared'][role]
            split.update({role + '_dataset_id': intent[role + '_dataset_id'], role + '_version_id': intent[role + '_version_id'], role + '_manifest_digest': digest(items)})
            children[intent[role + '_dataset_id']] = {'id': intent[role + '_dataset_id'], 'project_id': plan['project_id'], 'schema': 'sft', 'dataset_split_id': intent['split_id'],
                'dataset_split_role': role, 'source_dataset_id': source['id'], 'version_id': intent[role + '_version_id'], 'manifest': items, 'manifest_digest': digest(items), 'storage_path': str(Path(plan['storage_path']) / role)}
        ref = verify_split_record(split, lambda resource_id: children.get(resource_id) or get_dataset(resource_id), resolve_path)
        report = strict_json((directory / 'check/check-report.json').read_bytes())
        checker = plan['checker_identity']
        if (not isinstance(checker, dict) or set(checker) != {'executable_sha256', 'checker_sha256', 'recipe_sha256'}
                or any(not isinstance(value, str) or not HEX.fullmatch(value) for value in checker.values())
                or checker['checker_sha256'] != report['check_identity']['checker_implementation_sha256']
                or checker['recipe_sha256'] != report['check_identity']['recipe']['recipe_implementation_sha256']
                or plan['preview'] != preview_from_report(plan, report, plan['prepared'])):
            failure('DATASET_SPLIT_PLAN_CHANGED', '预览内容或检查器身份与冻结监督证据不一致。')
        for name in ('sample-checks.jsonl', 'check-report.json'):
            if (directory / 'check' / name).read_bytes() != (directory / 'proof' / name).read_bytes():
                failure('DATASET_SPLIT_PLAN_CHANGED', 'CPU 检查原件与派生证明副本不一致。')
        return ref
    except (KeyError, TypeError, ValueError, OSError):
        failure('DATASET_SPLIT_PLAN_CHANGED', '来源组预览缺少完整暂存证据或固定登记意图。')


def verify_split_record(split, get_dataset, resolve_path=lambda path: path):
    """只读核验冻结证明和三份数据，适用于当前库、导出和备份映射目录。"""
    try:
        count_names = {*COUNTS, 'source_groups', 'train_samples', 'validation_samples', 'train_groups', 'validation_groups'}
        if (type(split.get('schema_version')) is not int or split['schema_version'] != 1 or split.get('algorithm') != ALGORITHM or split.get('status') != 'ready'
                or not valid_manifest(split['manifest'], PROOF_FILES) or not isinstance(split.get('counts'), dict) or set(split['counts']) != count_names
                or any(type(value) is not int or value < 0 for value in split['counts'].values())):
            failure('DATASET_SPLIT_CHANGED', '来源组证明结构不受支持。')
        proof_dir = Path(resolve_path(split['storage_path']))
        verify_manifest(proof_dir, split['manifest'])
        if digest(split['manifest']) != split['manifest_digest']:
            failure('DATASET_SPLIT_CHANGED', '来源组证明清单摘要不一致。')
        proof = strict_json((proof_dir / 'split-manifest.json').read_bytes())
        if not isinstance(proof, dict) or proof.pop('plan_digest', None) != split['plan_digest'] or set(proof) != PROOF_FIELDS or digest(proof) != split['plan_digest']:
            failure('DATASET_SPLIT_CHANGED', '来源组证明摘要不一致。')
        if digest(split_content_identity(proof)) != split['split_digest'] or proof.get('split_digest') != split['split_digest']:
            failure('DATASET_SPLIT_CHANGED', '来源组划分内容身份不一致。')
        for name in ('source_dataset_id', 'source_version_id', 'source_manifest_digest', 'model_id', 'model_manifest_digest', 'max_seq_length', 'split_seed', 'validation_fraction_bps', 'counts', 'check_identity_digest', 'tokenization_recipe_digest', 'algorithm'):
            if split[name] != proof[name]:
                failure('DATASET_SPLIT_CHANGED', '来源组证明与登记字段不一致。')
        source = get_dataset(split['source_dataset_id'])
        if (source['project_id'] != split['project_id'] or source.get('schema') != 'sft' or source.get('dataset_split_id')
                or source['version_id'] != split['source_version_id'] or source['manifest_digest'] != split['source_manifest_digest']
                or len(source['manifest']) != 1 or digest(source['manifest']) != source['manifest_digest']):
            failure('DATASET_SPLIT_CHANGED', '来源原件版本与划分证明不一致。')
        source_dir = Path(resolve_path(source['storage_path']))
        verify_manifest(source_dir, source['manifest'])
        children = {}
        for role in ('train', 'validation'):
            child = get_dataset(split[role + '_dataset_id'])
            if (child['project_id'] != split['project_id'] or child.get('schema') != 'sft' or child.get('dataset_split_id') != split['id']
                    or child.get('dataset_split_role') != role or child.get('source_dataset_id') != source['id']
                    or child['id'] != proof[role + '_dataset_id'] or child['version_id'] != split[role + '_version_id'] or child['version_id'] != proof[role + '_version_id']
                    or child['manifest'] != proof[role + '_manifest'] or not valid_manifest(child['manifest'], [role + '.jsonl'])
                    or child['manifest_digest'] != split[role + '_manifest_digest'] or digest(child['manifest']) != child['manifest_digest']):
                failure('DATASET_SPLIT_CHANGED', '派生子集角色、版本或清单与来源证明不一致。')
            child_dir = Path(resolve_path(child['storage_path']))
            verify_manifest(child_dir, child['manifest'])
            children[role] = child_dir / (role + '.jsonl')
        report = strict_json((proof_dir / 'check-report.json').read_bytes())
        verify_check_report(report)
        if (not isinstance(report, dict) or digest(report['check_identity']) != split['check_identity_digest']
                or report['check_identity_digest'] != split['check_identity_digest']
                or report['check_identity']['source_sha256'] != source['manifest'][0]['sha256']
                or report['check_identity']['model_manifest_digest'] != split['model_manifest_digest']
                or report['check_identity']['max_seq_length'] != split['max_seq_length']
                or report['check_identity']['tokenization_recipe_digest'] != split['tokenization_recipe_digest']):
            failure('DATASET_SPLIT_CHANGED', '监督检查身份与来源组证明不一致。')
        if not valid_manifest(proof['checks_manifest'], ['sample-checks.jsonl', 'check-report.json']):
            failure('DATASET_SPLIT_CHANGED', '逐行监督证据清单不完整。')
        declared = {item['path']: item for item in split['manifest']}
        if any(declared[item['path']] != item for item in proof['checks_manifest']):
            failure('DATASET_SPLIT_CHANGED', '逐行监督证据摘要不一致。')
        rows, counts, _ = group_evidence(source_dir / source['manifest'][0]['path'], proof_dir / 'sample-checks.jsonl', split['max_seq_length'])
        verify_check_report(report, rows)
        groups, assignments, blocking = group_assignment(rows, split['split_seed'], split['validation_fraction_bps'])
        if blocking or proof['group_assignments'] != assignments:
            failure('DATASET_SPLIT_CHANGED', '来源组隔离结果与固定算法不一致。')
        for role, path in children.items():
            chosen = [sample for _, sample in rows if groups[sample['source_id']] == role]
            expected = b''.join((encode({'messages': sample['messages']}) + '\n').encode() for sample in chosen)
            if path.read_bytes() != expected:
                failure('DATASET_SPLIT_CHANGED', '子集内容不是来源组证明声明的有效样本。')
            counts[role + '_samples'] = len(chosen)
            counts[role + '_groups'] = sum(value == role for value in groups.values())
        counts['source_groups'] = len(groups)
        if counts != split['counts'] or any(report[name] != counts[name] for name in COUNTS):
            failure('DATASET_SPLIT_CHANGED', '来源组计数与实际样本不一致。')
        return portable_split_ref({name: split[name] for name in SPLIT_REF_FIELDS})
    except (KeyError, TypeError, ValueError, OSError):
        failure('DATASET_SPLIT_CHANGED', '来源组证明缺失或结构无效，尚不能使用。')


def group_evidence(source_file, checks_file, max_seq_length, check_cancel=lambda: None):
    rows, counts, exclusions = [], Counter({name: 0 for name in COUNTS}), Counter()
    with source_file.open('rb') as original, checks_file.open('rb') as checked:
        for number, raw in enumerate(original, 1):
            check_cancel()
            row = strict_json(checked.readline())
            if not isinstance(row, dict) or set(row) != {'line', 'line_sha256', 'messages_sha256', 'source_id', 'status', 'code', 'input_tokens', 'supervised_tokens', 'shifted_supervised_tokens'} or type(row.get('line')) is not int or row['line'] != number or row.get('line_sha256') != hashlib.sha256(raw).hexdigest():
                failure('DATASET_CHECK_OUTPUT_INVALID', '逐行检查与原件物理行不一致。')
            if not raw.strip():
                if row.get('status') != 'ignored' or row.get('code') != 'BLANK_LINE' or row.get('source_id') is not None or row.get('messages_sha256') is not None or any(type(row.get(name)) is not int or row[name] != 0 for name in ('input_tokens', 'supervised_tokens', 'shifted_supervised_tokens')):
                    failure('DATASET_CHECK_OUTPUT_INVALID', '空白行检查结果无效。')
                counts['ignored_lines'] += 1
                continue
            sample = strict_json(raw)
            if not isinstance(sample, dict) or set(sample) != {'source_id', 'messages'}:
                failure('DATASET_SPLIT_SOURCE_REQUIRED', '原件每行必须仅包含 source_id 和 messages。')
            group = sample['source_id']
            if not isinstance(group, str) or not group.strip() or group.strip() != group or len(group.encode()) > 256:
                failure('DATASET_SPLIT_SOURCE_REQUIRED', '每条原件需要有效的 source_id，不能用行号代替来源。')
            if row.get('source_id') != group or row.get('messages_sha256') != digest({'messages': sample['messages']}) or row.get('status') not in {'accepted', 'excluded'}:
                failure('DATASET_CHECK_OUTPUT_INVALID', '逐行检查的来源或内容摘要不一致。')
            counts['input_samples'] += 1
            counts[row['status'] + '_samples'] += 1
            if row['status'] == 'accepted':
                if (row.get('code') is not None or any(type(row.get(name)) is not int for name in ('input_tokens', 'supervised_tokens', 'shifted_supervised_tokens'))
                        or not 0 < row['shifted_supervised_tokens'] <= row['supervised_tokens'] <= row['input_tokens'] <= max_seq_length):
                    failure('DATASET_CHECK_OUTPUT_INVALID', '接受样本缺少有效的移位监督词元。')
                messages = sample['messages']
                if not isinstance(messages, list) or any(not isinstance(message, dict) or set(message) != {'role', 'content'} or message['role'] not in {'user', 'assistant', 'system'} or not isinstance(message['content'], str) for message in messages):
                    failure('DATASET_CHECK_OUTPUT_INVALID', '接受样本的消息结构无效。')
                counts['supervised_tokens'] += row['supervised_tokens']
                counts['shifted_supervised_tokens'] += row['shifted_supervised_tokens']
                rows.append((number, sample))
            else:
                if row.get('input_tokens') is not None or any(type(row.get(name)) is not int or row[name] != 0 for name in ('supervised_tokens', 'shifted_supervised_tokens')) or not isinstance(row.get('code'), str) or not re.fullmatch(r'[A-Z_]{1,80}', row['code']):
                    failure('DATASET_CHECK_OUTPUT_INVALID', '排除样本计数或原因无效。')
                exclusions[row['code']] += 1
        if checked.read(1):
            failure('DATASET_CHECK_OUTPUT_INVALID', '逐行检查含有原件之外的记录。')
    return rows, dict(counts), dict(exclusions)


def group_assignment(rows, seed, fraction):
    from .evaluation import normalized_prompt
    ordered = sorted({sample['source_id'] for _, sample in rows}, key=lambda group: (digest([ALGORITHM, seed, group]), group))
    blocking, prompts = [], {}
    if len(ordered) < 2:
        blocking.append({'code': 'DATASET_SPLIT_TOO_FEW_GROUPS', 'message': '有效监督样本至少需要两个独立来源组；不会把同组拆到两侧。'})
    count = max(1, min(len(ordered) - 1, (len(ordered) * fraction + 5000) // 10000))
    validation = set(ordered[:count]) if len(ordered) >= 2 else set()
    groups = {group: 'validation' if group in validation else 'train' for group in ordered}
    for number, sample in rows:
        role = groups[sample['source_id']]
        for message in sample['messages']:
            if message['role'] != 'user':
                continue
            prompt = normalized_prompt(message['content'])
            opposite = 'validation' if role == 'train' else 'train'
            previous = prompts.get((prompt, opposite))
            if previous is not None:
                train_line, validation_line = (number, previous) if role == 'train' else (previous, number)
                blocking.append({'code': 'DATASET_SPLIT_DUPLICATE_PROMPT',
                    'message': f'训练原件行 {train_line} 与验证原件行 {validation_line} 的规范化提示词相同，请核查来源和数据，不能据此宣称隔离通过。',
                    'line': validation_line, 'related_line': train_line})
                break
            prompts.setdefault((prompt, role), number)
        if len(blocking) >= 20:
            break
    return groups, [{'source_id': group, 'subset': role} for group, role in groups.items()], blocking


def write_file(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class DatasetSplits:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.root = regular_path(service.root / 'assets')
        self.processes = {}
        with self.store.transaction():
            for record in self.store.list('dataset-split-plan'):
                if record['status'] in ACTIVE:
                    record.update(status='recovery_required', updated_at=now(), blocking=[{'code': 'DATASET_SPLIT_INTERRUPTED', 'message': '上次检查中断，暂存证据保留；请取消后重新准备，不会自动运行。'}])
                    self.store.put('dataset-split-plan', record)

    @staticmethod
    def public(record):
        private = {'storage_path', 'manifest', 'source_manifest', 'model_manifest', 'checker_identity', 'prepared', 'process_identity', 'process_pid', 'staged_manifest', 'apply_intent'}
        return {key: value for key, value in record.items() if key not in private}

    def get(self, plan_id):
        return self.public(self.store.get('dataset-split-plan', plan_id))

    def plans(self, project_id, source_dataset_id=None, cursor=None, limit=100):
        with self.store.lock:
            self.store.get('project', project_id)
            if source_dataset_id:
                if self.store.get('dataset', source_dataset_id)['project_id'] != project_id:
                    raise Fault('PROJECT_MISMATCH', '来源原件不属于当前项目。', 403)
            if type(limit) is not int or not 1 <= limit <= 200 or cursor is not None and (not isinstance(cursor, str) or not cursor):
                failure('INVALID_CURSOR', '分页参数或游标无效，请重新读取计划列表。')
            query = "kind='dataset-split-plan' AND project_id=?"
            parameters = [project_id]
            if source_dataset_id:
                query += " AND json_extract(body,'$.source_dataset_id')=?"
                parameters.append(source_dataset_id)
            if cursor:
                row = self.store.db.execute('SELECT rowid FROM resources WHERE ' + query + ' AND id=?', [*parameters, cursor]).fetchone()
                if row is None:
                    failure('INVALID_CURSOR', '计划列表游标不属于当前项目或原件，请重新读取。')
                query += ' AND rowid>?'
                parameters.append(row[0])
            rows = self.store.db.execute('SELECT id,body FROM resources WHERE ' + query + ' ORDER BY rowid LIMIT ?', [*parameters, limit + 1]).fetchall()
            return {'items': [self.public(json.loads(row[1])) for row in rows[:limit]], 'next_cursor': rows[limit - 1][0] if len(rows) > limit else None}

    def command(self, request, output):
        settings = self.service.settings
        args = ['--snapshot', str(request), '--output-dir', str(output), '--controller-pid', str(os.getpid())]
        if not settings.worker_python and settings.bundled_worker:
            return [str(settings.bundled_worker), '--mode', 'dataset-check', *args]
        if not settings.worker_python or not settings.worker_python.is_file():
            failure('DATASET_CHECK_ENVIRONMENT_REQUIRED', '请先配置支持 CPU 分词检查的本机执行环境。')
        return [str(settings.worker_python), '-B', '-m', 'adapters.mlx_text.split_check', *args]

    def checker_identity(self):
        from adapters.mlx_text import recipe, split_check
        settings = self.service.settings
        executable = settings.worker_python or settings.bundled_worker
        if not executable or not executable.is_file():
            failure('DATASET_CHECK_ENVIRONMENT_REQUIRED', '请先配置支持 CPU 分词检查的本机执行环境。')
        return {'executable_sha256': file_hash(executable.resolve(strict=True)), 'checker_sha256': file_hash(Path(split_check.__file__)), 'recipe_sha256': file_hash(Path(recipe.__file__))}

    def inputs(self, payload):
        source = self.store.get('dataset', payload['source_dataset_id'])
        model = self.store.get('model', payload['model_id'])
        if any(item['project_id'] != payload['project_id'] for item in (source, model)):
            raise Fault('PROJECT_MISMATCH', '原件和模型必须属于当前项目。', 403)
        if source.get('schema') != 'sft' or len(source.get('manifest', [])) != 1 or not 0 < source.get('total_bytes', 0) <= 64 * 1024 * 1024 or source.get('dataset_split_id'):
            failure('DATASET_SPLIT_SOURCE_REQUIRED', '请选择不超过 64 MiB、带 source_id 的单文件 SFT 原件；不能再次划分已派生子集。')
        config = model.get('model_config', {})
        if model.get('modality', 'text') != 'text' or config.get('model_type') != 'qwen2' or config.get('hidden_size') != 896 or config.get('num_hidden_layers') != 24 or config.get('quantization') or config.get('quantization_config'):
            failure('MODEL_UNVERIFIED', '当前来源组检查仅支持固定 Qwen2.5-0.5B-Instruct 原权重的分词器。')
        for item in (source, model):
            if digest(item['manifest']) != item['manifest_digest']:
                failure('ASSET_MANIFEST_CHANGED', '资产清单与登记不一致，请重新导入。')
            verify_manifest(Path(item['storage_path']), item['manifest'])
        if 'source_manifest_digest' in payload and (source['manifest_digest'] != payload['source_manifest_digest'] or source['version_id'] != payload['source_version_id'] or model['manifest_digest'] != payload['model_manifest_digest']):
            failure('DATASET_SPLIT_INPUT_CHANGED', '原件或模型版本已变化，请重新准备计划。')
        return source, model

    def prepare(self, payload, key):
        scope = 'dataset-split-prepare'
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return self.get(previous['id'])
            self.store.get('project', payload['project_id'])
        source, model = self.inputs(payload)
        checker = self.checker_identity()
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return self.get(previous['id'])
            if self.service.closed.is_set():
                raise Fault('SERVICE_STOPPING', '控制服务正在关闭，请稍后重新准备。', 503)
            if any(item['status'] in ACTIVE for item in self.store.list('dataset-split-plan')):
                failure('DATASET_SPLIT_BUSY', '已有来源组检查正在运行，请先完成或取消。')
            if self.store.get('dataset', source['id']) != source or self.store.get('model', model['id']) != model:
                failure('DATASET_SPLIT_INPUT_CHANGED', '准备期间资产发生变化，请重试。')
            record = self.service.resource('dataset-split-plan', payload['project_id'], **{key: value for key, value in payload.items() if key != 'project_id'},
                status='preparing', updated_at=now(), plan_digest=None, counts=None, blocking=[], warnings=[],
                applied_split_id=None, train_dataset_id=None, validation_dataset_id=None, preview=None,
                source_version_id=source['version_id'], source_manifest_digest=source['manifest_digest'], model_manifest_digest=model['manifest_digest'],
                source_manifest=source['manifest'], model_manifest=model['manifest'], checker_identity=checker)
            record['storage_path'] = str(self.root / ('.split-' + record['id']))
            record['apply_intent'] = {'split_id': identifier('dataset-split'), 'train_dataset_id': identifier('dataset'), 'validation_dataset_id': identifier('dataset'),
                                      'train_version_id': identifier('version'), 'validation_version_id': identifier('version')}
            self.store.put('dataset-split-plan', record)
            self.store.remember(scope, key, payload, {'id': record['id']})
            thread = threading.Thread(target=self.execute, args=(record['id'],), daemon=True, name='dataset-split-' + record['id'])
            self.service.threads.add(thread)
            try:
                thread.start()
            except Exception:
                self.service.threads.discard(thread)
                record.update(status='failed', blocking=[{'code': 'DATASET_SPLIT_START_FAILED', 'message': 'CPU 检查未启动，请重新准备计划。'}])
                self.store.put('dataset-split-plan', record)
            return self.public(record)

    def check_cancel(self, plan_id):
        if self.service.closed.is_set() or self.store.get('dataset-split-plan', plan_id)['status'] == 'cancelling':
            failure('DATASET_SPLIT_CANCELLED', '检查已停止，没有登记派生数据。')

    def has_live_processes(self):
        with self.store.lock:
            return any(process.poll() is None or self.service.group_present(process.pid) for process in self.processes.values())

    def unresolved(self):
        return any(record['status'] in ACTIVE | {'recovery_required'} for record in self.store.list('dataset-split-plan'))

    def stop_owned(self, plan_id, process):
        try:
            if process.poll() is None:
                self.service._signal(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.service._signal(process, signal.SIGKILL)
                    process.wait(timeout=2)
            if self.service.group_present(process.pid):
                self.service._signal(process, signal.SIGKILL)
                deadline = time.monotonic() + 0.5
                while self.service.group_present(process.pid) and time.monotonic() < deadline:
                    time.sleep(0.02)
            stopped = process.poll() is not None and not self.service.group_present(process.pid)
        except (OSError, subprocess.TimeoutExpired):
            stopped = False
        if stopped:
            with self.store.lock:
                self.processes.pop(plan_id, None)
        return stopped

    def close(self):
        with self.store.lock:
            owned = list(self.processes.items())
        for plan_id, process in owned:
            if not self.stop_owned(plan_id, process):
                with self.store.transaction():
                    record = self.store.get('dataset-split-plan', plan_id)
                    record.update(status='recovery_required', blocking=[{'code': 'DATASET_SPLIT_STOP_UNKNOWN', 'message': 'CPU 检查退出尚未确认，原暂存和所有权记录保留。'}], updated_at=now())
                    self.store.put('dataset-split-plan', record)

    def cancel(self, plan_id, key):
        scope, payload = 'dataset-split-cancel:' + plan_id, {}
        with self.store.transaction():
            previous = self.store.replay(scope, key, payload)
            record = self.store.get('dataset-split-plan', plan_id)
            if previous and record['status'] != 'recovery_required':
                return self.public(record)
            if record['status'] == 'applied':
                failure('DATASET_SPLIT_ALREADY_APPLIED', '划分已登记，请保留其来源记录。')
            if record['status'] == 'recovery_required':
                pid = record.get('process_pid')
                process = self.processes.get(plan_id)
                if process and not self.stop_owned(plan_id, process):
                    failure('DATASET_SPLIT_STOP_UNKNOWN', '原 CPU 检查尚未确认退出，请稍后核实，暂存证据不会被删除。')
                if pid:
                    current, original = self.service.process_identity(pid), record.get('process_identity', {})
                    exited = current.get('status') == 'absent' and not self.service.group_present(pid)
                    reused = current.get('status') == original.get('status') == 'present' and current.get('identity_digest') != original.get('identity_digest')
                    if not exited and not reused:
                        failure('DATASET_SPLIT_STOP_UNKNOWN', '原 CPU 检查退出结果仍不明确，暂存证据不会被删除。')
            record.update(status='cancelling' if record['status'] in ACTIVE else 'cancelled', updated_at=now())
            if record['status'] == 'cancelled':
                try:
                    self.discard_stage(record)
                except (Fault, OSError):
                    record.update(status='recovery_required', blocking=[{'code': 'DATASET_SPLIT_STAGE_CLEANUP_FAILED', 'message': '检查已停止，但暂存清理尚未完成；已保留现状，请重试取消。'}])
                    record.pop('staged_manifest', None)
            self.store.put('dataset-split-plan', record)
            if not previous:
                self.store.remember(scope, key, payload, {'id': plan_id})
            return self.public(record)

    def discard_stage(self, record):
        """只清理已退出检查的本计划暂存，原件和正式资产不在此目录内。"""
        if record.get('storage_path'):
            directory = Path(record['storage_path'])
            if directory != self.root / ('.split-' + record['id']):
                failure('DATASET_SPLIT_STAGE_CHANGED', '计划暂存位置与登记不一致，未清理文件。')
            if directory.exists():
                regular_path(directory)
                if any(path.is_symlink() for path in directory.rglob('*')):
                    failure('DATASET_SPLIT_STAGE_CHANGED', '计划暂存出现符号链接，未清理文件。')
                shutil.rmtree(directory)
        record['storage_path'] = None
        record.pop('staged_manifest', None)

    def run_checker(self, plan_id, request, output):
        from adapters.mlx_text import split_check
        command = self.command(request, output)
        # 临时流只在当前调用中持有；不把原 stdout/stderr 写入计划或诊断。
        import tempfile
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=self.service.worker_environment(), start_new_session=True,
                                       cwd=str(Path(split_check.__file__).resolve().parents[2]))
            with self.store.lock:
                self.processes[plan_id] = process
            try:
                with self.store.transaction():
                    record = self.store.get('dataset-split-plan', plan_id)
                    record.update(process_pid=process.pid, process_identity=self.service.process_identity(process.pid))
                    self.store.put('dataset-split-plan', record)
                deadline = time.monotonic() + 300
                while process.poll() is None:
                    self.check_cancel(plan_id)
                    if time.monotonic() >= deadline:
                        failure('DATASET_CHECK_TIMEOUT', 'CPU 分词检查超时，没有登记派生数据。')
                    if stdout.tell() > 1024 * 1024 or stderr.tell() > 8 * 1024 * 1024:
                        failure('DATASET_CHECK_OUTPUT_INVALID', '检查器输出超出固定范围，未采用结果。')
                    time.sleep(0.05)
                self.check_cancel(plan_id)
                stdout.seek(0)
                data = stdout.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    failure('DATASET_CHECK_OUTPUT_INVALID', '检查器输出超出固定范围，未采用结果。')
                result = strict_json(data)
                if not isinstance(result, dict) or result.get('kind') != 'dataset-check' or result.get('schema_version') != 1 or type(result.get('ok')) is not bool or process.returncode not in (0, 1):
                    failure('DATASET_CHECK_OUTPUT_INVALID', '检查器未返回完整可验证结果。')
                if not result['ok'] or process.returncode != 0:
                    first = (result.get('blocking') or [{}])[0]
                    code = first.get('code') if isinstance(first, dict) else None
                    message = ISSUES.get(code)
                    if not message:
                        code, message = 'DATASET_CHECK_FAILED', 'CPU 分词检查未完成，请核对来源字段、分词器和固定依赖。'
                    details = {'line': first['line']} if isinstance(first, dict) and type(first.get('line')) is int and first['line'] > 0 else {}
                    raise Fault(code, message, 409, **details)
                return result
            finally:
                if not self.stop_owned(plan_id, process):
                    failure('DATASET_SPLIT_STOP_UNKNOWN', 'CPU 检查退出尚未确认，原暂存和所有权记录保留。')

    def verify_check_identity(self, record, report, model):
        from adapters.mlx_text import recipe, split_check
        identity = report.get('check_identity')
        if not isinstance(identity, dict) or digest(identity) != report.get('check_identity_digest'):
            failure('DATASET_CHECK_OUTPUT_INVALID', '分词检查身份摘要不一致。')
        config = strict_json((Path(model['storage_path']) / 'tokenizer_config.json').read_bytes())
        template = config.get('chat_template')
        if not isinstance(template, str) or hashlib.sha256(template.encode()).hexdigest() != recipe.TEMPLATE_SHA256:
            failure('TOKENIZER_UNVERIFIED', '分词模板不属于固定配方。')
        expected_recipe, recipe_digest = recipe.build_recipe(Path(model['storage_path']), SimpleNamespace(chat_template=template), 'train', record['max_seq_length'])
        if (identity.get('source_sha256') != record['source_manifest'][0]['sha256'] or identity.get('model_manifest_digest') != record['model_manifest_digest']
            or identity.get('max_seq_length') != record['max_seq_length'] or identity.get('checker_version') != split_check.VERSION
            or identity.get('checker_implementation_sha256') != record['checker_identity']['checker_sha256']
            or identity.get('recipe') != expected_recipe or identity.get('tokenization_recipe_digest') != recipe_digest
            or identity.get('runtime') != split_check.RUNTIME or self.checker_identity() != record['checker_identity']):
            failure('DATASET_CHECK_IDENTITY_CHANGED', '检查器、模型分词文件或监督配方身份发生变化，请重新准备。')
        return recipe_digest

    def checked_rows(self, record, source, output, result):
        artifacts = result.get('artifacts')
        if not isinstance(artifacts, dict) or set(artifacts) != {'sample-checks.jsonl', 'check-report.json'}:
            failure('DATASET_CHECK_OUTPUT_INVALID', '检查器产物清单不完整。')
        expected = []
        for name, item in artifacts.items():
            if not isinstance(item, dict) or type(item.get('size_bytes')) is not int or not 0 <= item['size_bytes'] <= 256 * 1024 * 1024 or not isinstance(item.get('sha256'), str) or not HEX.fullmatch(item['sha256']):
                failure('DATASET_CHECK_OUTPUT_INVALID', '检查产物摘要或大小无效。')
            expected.append({'path': name, 'size': item['size_bytes'], 'sha256': item['sha256']})
        verify_manifest(output, expected)
        report = strict_json((output / 'check-report.json').read_bytes())
        if not isinstance(report, dict) or result.get('check_identity_digest') != report.get('check_identity_digest') or result.get('source_sha256') != source['manifest'][0]['sha256']:
            failure('DATASET_CHECK_OUTPUT_INVALID', '检查报告和原件身份不一致。')
        source_file = Path(source['storage_path']) / source['manifest'][0]['path']
        rows, counts, exclusions = group_evidence(source_file, output / 'sample-checks.jsonl', record['max_seq_length'], lambda: self.check_cancel(record['id']))
        verify_check_report(report, rows)
        if any(type(report.get(name)) is not int or report[name] != counts[name] or result.get(name) != counts[name] for name in COUNTS) or report.get('exclusion_counts') != exclusions:
            failure('DATASET_CHECK_OUTPUT_INVALID', '检查计数与逐行证据不一致。')
        return rows, counts, report

    def derive(self, record, source, output, result, directory, model):
        rows, counts, report = self.checked_rows(record, source, output, result)
        recipe_digest = self.verify_check_identity(record, report, model)
        groups, assignments, blocking = group_assignment(rows, record['split_seed'], record['validation_fraction_bps'])
        counts.update(source_groups=len(groups), train_samples=0, validation_samples=0, train_groups=0, validation_groups=0)
        preview = preview_from_report(record, report)
        if blocking:
            return {'counts': counts, 'blocking': blocking, 'preview': preview}
        child_dirs = {role: directory / role for role in ('train', 'validation')}
        for child in child_dirs.values():
            child.mkdir(mode=0o700)
        for role, child in child_dirs.items():
            selected = [sample for _, sample in rows if groups[sample['source_id']] == role]
            counts[role + '_samples'] = len(selected)
            counts[role + '_groups'] = sum(value == role for value in groups.values())
            write_file(child / (role + '.jsonl'), b''.join((encode({'messages': sample['messages']}) + '\n').encode() for sample in selected))
        proof = directory / 'proof'
        proof.mkdir(mode=0o700)
        for name in ('sample-checks.jsonl', 'check-report.json'):
            write_file(proof / name, (output / name).read_bytes())
        identity = {name: record[name] for name in ('source_dataset_id', 'source_version_id', 'source_manifest_digest', 'model_id', 'model_manifest_digest', 'max_seq_length', 'split_seed', 'validation_fraction_bps')}
        identity.update(schema_version=1, algorithm=ALGORITHM, counts=counts, check_identity_digest=report['check_identity_digest'], tokenization_recipe_digest=recipe_digest,
            train_manifest=manifest(child_dirs['train']), validation_manifest=manifest(child_dirs['validation']),
            group_assignments=assignments, checks_manifest=manifest(output), validation_use='holdout_only_no_validation_loss', duplicate_policy='normalized_user_prompt_cross_subset_rejected',
            **{name: record['apply_intent'][name] for name in ('train_dataset_id', 'train_version_id', 'validation_dataset_id', 'validation_version_id')})
        split_digest = digest(split_content_identity(identity))
        identity['split_digest'] = split_digest
        plan_digest = digest(identity)
        write_file(proof / 'split-manifest.json', (encode({**identity, 'plan_digest': plan_digest}) + '\n').encode())
        prepared = {**{role: manifest(path) for role, path in child_dirs.items()}, 'proof': manifest(proof)}
        preview = preview_from_report(record, report, prepared)
        return {'counts': counts, 'blocking': [], 'plan_digest': plan_digest, 'split_digest': split_digest, 'check_identity_digest': report['check_identity_digest'], 'tokenization_recipe_digest': recipe_digest,
                'prepared': prepared, 'preview': preview,
                'warnings': [{'code': 'DATASET_SPLIT_SEMANTIC_REVIEW_REQUIRED', 'message': '已检查来源组与相同提示词；近似或语义重复仍需人工核查，留出集尚未运行验证损失。'}]}

    def execute(self, plan_id):
        try:
            record = self.store.get('dataset-split-plan', plan_id)
            self.check_cancel(plan_id)
            source, model = self.inputs(record)
            directory = Path(record['storage_path'])
            directory.mkdir(mode=0o700)
            regular_path(directory)
            request = {'schema_version': 1, 'dataset_path': str(Path(source['storage_path']) / source['manifest'][0]['path']), 'dataset_sha256': source['manifest'][0]['sha256'],
                'model_path': model['storage_path'], 'model_manifest_digest': model['manifest_digest'], 'max_seq_length': record['max_seq_length']}
            write_file(directory / 'request.json', encode(request).encode())
            result = self.run_checker(plan_id, directory / 'request.json', directory / 'check')
            prepared = self.derive(record, source, directory / 'check', result, directory, model)
            self.inputs(record)
            prepared['staged_manifest'] = staged_manifest(directory)
            with self.store.transaction():
                self.check_cancel(plan_id)
                record = self.store.get('dataset-split-plan', plan_id)
                record.update(**prepared, status='blocked' if prepared['blocking'] else 'ready', updated_at=now())
                self.store.put('dataset-split-plan', record)
        except (Fault, OSError, ValueError, TypeError, KeyError) as error:
            issue = {'code': error.code, 'message': error.message, **{key: value for key, value in error.details.items() if key == 'line'}} if isinstance(error, Fault) else {'code': 'DATASET_CHECK_OUTPUT_INVALID', 'message': '检查文件或结果未通过核验，暂存证据保留，没有登记派生数据。'}
            with self.store.transaction():
                record = self.store.get('dataset-split-plan', plan_id)
                unknown = issue['code'] == 'DATASET_SPLIT_STOP_UNKNOWN'
                cancelled = not unknown and (record['status'] == 'cancelling' or issue['code'] == 'DATASET_SPLIT_CANCELLED')
                record.update(status='recovery_required' if unknown else 'cancelled' if cancelled else 'failed', blocking=[] if cancelled else [issue], updated_at=now())
                directory = Path(record['storage_path']) if record.get('storage_path') else None
                try:
                    if cancelled:
                        self.discard_stage(record)
                    elif not unknown and directory and directory.exists():
                        regular_path(directory)
                        record['staged_manifest'] = staged_manifest(directory)
                except (Fault, OSError):
                    record['status'] = 'recovery_required'
                self.store.put('dataset-split-plan', record)
        finally:
            with self.store.lock:
                self.service.threads.discard(threading.current_thread())
            self.service._release_if_idle()

    def applied(self, record):
        return {'split': self.public(self.store.get('dataset-split', record['applied_split_id'])),
                'train_dataset': self.service.public(self.store.get('dataset', record['train_dataset_id'])),
                'validation_dataset': self.service.public(self.store.get('dataset', record['validation_dataset_id']))}

    def apply(self, payload, key):
        try:
            self.apply_record(payload, key)
        except OSError:
            raise Fault('DATASET_SPLIT_IO_FAILED', '派生文件登记尚未完成，原计划及固定意图保留，可用原命令重试。', 409) from None
        self.cleanup_applied(payload['plan_id'])
        return self.applied(self.store.get('dataset-split-plan', payload['plan_id']))

    def cleanup_applied(self, plan_id):
        with self.store.transaction():
            record = self.store.get('dataset-split-plan', plan_id)
            if record.get('stage_cleanup_status') == 'completed':
                return
            owned = {'id': plan_id, 'storage_path': str(self.root / ('.split-' + plan_id))}
            record['warnings'] = [item for item in record.get('warnings', []) if item['code'] != 'DATASET_SPLIT_STAGE_CLEANUP_PENDING']
            try:
                self.discard_stage(owned)
                record['stage_cleanup_status'] = 'completed'
            except (Fault, OSError):
                record['stage_cleanup_status'] = 'pending'
                record['warnings'].append({'code': 'DATASET_SPLIT_STAGE_CLEANUP_PENDING', 'message': '来源组已完整登记并可用，部分临时文件仍待清理；重试应用命令可继续清理。'})
            self.store.put('dataset-split-plan', record)

    def apply_record(self, payload, key):
        scope = 'dataset-split-apply'
        with self.store.transaction():
            previous = self.store.replay(scope, key, payload)
            record = self.store.get('dataset-split-plan', payload['plan_id'])
            if record['plan_digest'] != payload['plan_digest']:
                failure('DATASET_SPLIT_PLAN_CHANGED', '预览摘要不一致，请重新读取计划。')
            if record['status'] == 'applied':
                response = self.applied(record)
                if not previous:
                    self.store.remember(scope, key, payload, {'id': record['id']})
                return response
            if record['status'] != 'ready' or self.service.closed.is_set():
                failure('DATASET_SPLIT_NOT_READY', '计划尚不可应用，请先完成检查并确认预览。')
        source, model = self.inputs(record)
        if self.checker_identity() != record['checker_identity']:
            failure('DATASET_CHECK_IDENTITY_CHANGED', '检查环境已变化，请重新准备计划。')
        verify_ready_plan(record, lambda resource_id: self.store.get('dataset', resource_id), lambda resource_id: self.store.get('model', resource_id))
        directory = regular_path(record['storage_path'])
        with self.store.transaction():
            previous = self.store.replay(scope, key, payload)
            latest = self.store.get('dataset-split-plan', record['id'])
            if latest['status'] == 'applied':
                if not previous:
                    self.store.remember(scope, key, payload, {'id': record['id']})
                return self.applied(latest)
            if latest != record or self.store.get('dataset', source['id']) != source or self.store.get('model', model['id']) != model or self.service.closed.is_set():
                failure('DATASET_SPLIT_PLAN_CHANGED', '应用期间计划或资产状态已变化，请重新读取。')
            split = self.service.resource('dataset-split', record['project_id'], schema_version=1, status='ready', algorithm=ALGORITHM,
                **{name: record[name] for name in ('plan_digest', 'split_digest', 'source_dataset_id', 'source_version_id', 'source_manifest_digest', 'model_id', 'model_manifest_digest', 'max_seq_length', 'split_seed', 'validation_fraction_bps', 'check_identity_digest', 'tokenization_recipe_digest', 'counts')}, plan_id=record['id'])
            split['id'] = record['apply_intent']['split_id']
            children = {}
            for role in ('train', 'validation'):
                items = record['prepared'][role]
                destination = copy_asset(directory / role, self.service.root / 'assets', items, digest(items))
                child = self.service.resource('dataset', record['project_id'], name=source['name'][:100] + (' · 训练集' if role == 'train' else ' · 留出验证集'),
                    revision=1, version_id=record['apply_intent'][role + '_version_id'], status='ready', schema='sft', manifest=items, manifest_digest=digest(items), total_bytes=items[0]['size'],
                    storage_path=str(destination), entrypoint=items[0]['path'], sample_count=record['counts'][role + '_samples'], sha256=items[0]['sha256'],
                    checks={'encoding': 'passed', 'structure': 'passed', 'tokenization': 'passed', 'quality': 'not_run', 'split_leakage': 'passed'},
                    dataset_split_id=split['id'], dataset_split_role=role, source_dataset_id=source['id'])
                child['id'] = record['apply_intent'][role + '_dataset_id']
                children[role] = child
            proof_manifest = record['prepared']['proof']
            proof_path = copy_asset(directory / 'proof', self.service.root / 'assets', proof_manifest, digest(proof_manifest))
            split.update(train_dataset_id=children['train']['id'], validation_dataset_id=children['validation']['id'], storage_path=str(proof_path), manifest=proof_manifest, manifest_digest=digest(proof_manifest))
            for role, child in children.items():
                split.update({role + '_version_id': child['version_id'], role + '_manifest_digest': child['manifest_digest']})
            verify_split_record(split, lambda dataset_id: next((child for child in children.values() if child['id'] == dataset_id), source if source['id'] == dataset_id else None))
            for child in children.values():
                self.store.put('dataset', child)
            self.store.put('dataset-split', split)
            latest.update(status='applied', applied_split_id=split['id'], train_dataset_id=children['train']['id'], validation_dataset_id=children['validation']['id'], updated_at=now())
            latest.update(storage_path=None, stage_cleanup_status='pending')
            latest.pop('staged_manifest', None)
            latest.pop('prepared', None)
            self.store.put('dataset-split-plan', latest)
            self.store.remember(scope, key, payload, {'id': record['id']})
            return self.applied(latest)

    def training_fields(self, task, dataset, model):
        if task['operation'] != 'train' or task['kind'] != 'text':
            return {}
        if dataset.get('dataset_split_role') == 'validation':
            failure('DATASET_SPLIT_VALIDATION_NOT_TRAINABLE', '留出验证集不能用于训练，请选择配对训练集。')
        if not dataset.get('dataset_split_id'):
            # 冻结的历史检查点只按原有合同恢复；普通新训练不能继承此例外。
            if task['draft'].get('checkpoint_id'):
                checkpoint = self.store.get('checkpoint', task['draft']['checkpoint_id'])
                original = self.store.get('attempt', checkpoint['source_attempt_id'])['snapshot']
                if not original.get('dataset_split_ref') and original.get('dataset_id') == dataset['id']:
                    return {}
            failure('DATASET_SPLIT_REQUIRED', '训练前请按 source_id 预览并应用来源组划分，再选择派生训练集。')
        split = self.store.get('dataset-split', dataset['dataset_split_id'])
        if split['project_id'] != task['project_id'] or split['train_dataset_id'] != dataset['id'] or dataset.get('dataset_split_role') != 'train':
            failure('DATASET_SPLIT_CHANGED', '训练集与来源组证明引用不一致。')
        if not model or split['model_manifest_digest'] != model['manifest_digest'] or split['max_seq_length'] != task['draft']['runtime']['max_seq_length']:
            failure('DATASET_SPLIT_CHECK_EXPIRED', '模型分词版本或最大序列长度已变化，请重新准备来源组划分。')
        return {'dataset_split_ref': verify_split_record(split, lambda dataset_id: self.store.get('dataset', dataset_id))}
