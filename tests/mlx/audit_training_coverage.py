"""只读核对来源组划分后的任务覆盖；不训练、不改变划分、不判模型质量。"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def audit(index: list[dict], assignments: list[dict]) -> dict:
    groups = {}
    for row in assignments:
        source, subset = row['source_id'], row['subset']
        if not isinstance(source, str) or not source or source in groups:
            raise ValueError('来源组为空或重复，拒绝模糊的划分记录')
        if subset not in {'train', 'validation'}:
            raise ValueError('未知数据子集')
        groups[source] = subset
    if not index:
        raise ValueError('样本索引为空')
    seen = set()
    rows = []
    for row in index:
        for key in ('id', 'category', 'family', 'source_diagnostic_id'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('样本索引缺少有效字段：' + key)
        if row['id'] in seen:
            raise ValueError('样本编号重复')
        seen.add(row['id'])
        source = row['source_diagnostic_id']
        if source not in groups:
            raise ValueError('样本没有来源组划分')
        rows.append((row['category'], row['family'], source, groups[source]))
    if {row[2] for row in rows} != set(groups):
        raise ValueError('划分包含索引之外的来源组')
    categories = sorted({row[0] for row in rows})
    families = sorted({row[:2] for row in rows})
    coverage = []
    for category, family in families:
        counts = Counter(row[3] for row in rows if row[:2] == (category, family))
        coverage.append({'category': category, 'family': family,
                         'train_samples': counts['train'], 'validation_samples': counts['validation']})
    subsets = {}
    for subset in ('train', 'validation'):
        selected = [row for row in rows if row[3] == subset]
        subsets[subset] = {
            'samples': len(selected), 'source_groups': len({row[2] for row in selected}),
            'category_samples': {category: sum(row[0] == category for row in selected) for category in categories},
            'family_count': len({row[:2] for row in selected}),
        }
    return {'status': 'coverage_audited_not_quality_acceptance', 'source_families': len(families),
            'subsets': subsets, 'coverage': coverage,
            'missing_from_training': [row for row in coverage if not row['train_samples']],
            'missing_from_validation': [row for row in coverage if not row['validation_samples']],
            'quality_approved': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--split', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    index_data, split_data = args.index.read_bytes(), args.split.read_bytes()
    result = audit(json.loads(index_data), json.loads(split_data)['group_assignments'])
    result['inputs'] = {str(path): hashlib.sha256(data).hexdigest()
                        for path, data in ((args.index, index_data), (args.split, split_data))}
    # 不覆盖已有报告，也不改写历史索引或分组。
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'source_families': result['source_families'],
                      'missing_from_training': len(result['missing_from_training']),
                      'subsets': result['subsets']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
