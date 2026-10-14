"""以完整计数核对阈值删失区间；只给上界，不制造精确耗时或零样本。"""
import math
from collections import Counter

ACTIONS = {'navigate_models', 'open_settings', 'close_settings', 'open_task', 'preview_preset'}
NAMES = {'pointerdown', 'pointerup', 'click', 'keydown', 'keyup'}


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def key(item):
    return item['name'], item['startTime']


def analyze_intervals(report, action, warmup, samples):
    problems = []
    if report.get('reason') != 'manual' or report.get('hidden') is not False or report.get('ready') is not True:
        problems.append('记录未准备完成、曾不可见或未手动完整结束')
    if report.get('thresholdMs') != 16:
        problems.append('采样阈值不是16毫秒')
    dropped = report.get('droppedEntriesCount')
    if report.get('observerMode') != 'live' or 'droppedEntriesCount' not in report or (dropped is not None and (type(dropped) is not int or dropped != 0)):
        problems.append('观察器不是实时模式，或明确报告丢弃记录／无效计数')
    observed, entries = report['observedInputs'], report['entries']
    for item in observed:
        if item.get('name') not in NAMES or item.get('action') not in ACTIONS | {'other'} or not number(item.get('startTime')):
            raise ValueError('原生输入类别或时间无效')
    by_key = {key(item): item for item in observed}
    if len(by_key) != len(observed):
        problems.append('输入时间标识重复，不能唯一关联')
    if report['inputs'] != [item for item in observed if item['action'] != 'other']:
        problems.append('操作输入与完整输入清单不一致')
    before, after = report.get('countsBefore'), report.get('countsAfter')
    counts = Counter(item['name'] for item in observed)
    if not isinstance(before, dict) or not isinstance(after, dict) or any(
        type(before.get(name)) is not int or type(after.get(name)) is not int or before[name] < 0
        or after[name] - before[name] != counts[name] for name in NAMES
    ):
        problems.append('浏览器事件总数与原生监听数不一致或系统不支持计数')
    reported = {}
    for entry in entries:
        if any(not number(entry.get(name)) for name in ['startTime', 'duration', 'processingStart', 'processingEnd', 'interactionId']):
            raise ValueError('事件计时包含无效数字')
        if entry['processingEnd'] < entry['processingStart'] or entry['processingStart'] < entry['startTime']:
            raise ValueError('事件处理时间顺序不成立')
        if int(entry['interactionId']) != entry['interactionId'] or entry['duration'] < 16:
            raise ValueError('交互编号或事件阈值无效')
        if entry['processingEnd'] - entry['startTime'] > entry['duration'] + 8:
            raise ValueError('处理时间超出包含量化余量的事件时长')
        if key(entry) not in by_key or entry.get('action') != by_key[key(entry)]['action']:
            problems.append('事件没有对应原生输入')
        if key(entry) in reported:
            problems.append('事件重复上报')
        reported[key(entry)] = entry
    if report.get('unmatchedEntries') != []:
        problems.append('存在未匹配的系统事件，不能把未上报项解释为阈值删失')
    missing = [item for item in report['inputs'] if key(item) not in reported]
    if report.get('missing') != missing:
        problems.append('未上报清单不完整')
    inputs = [item for item in observed if item['action'] == action]
    primary = [item for item in inputs if item['name'] == 'click']
    if len(primary) != warmup + samples:
        problems.append(f'预期{warmup + samples}次操作，实际{len(primary)}次')
    # 本入口只分析已完整捕获的鼠标点击三元组；键盘另验，不猜测交互分组。
    groups = [inputs[index:index + 3] for index in range(0, len(inputs), 3)]
    intervals, used_ids = [], set()
    for index, group in enumerate(groups):
        if [item['name'] for item in group] != ['pointerdown', 'pointerup', 'click'] or any(
            a['startTime'] > b['startTime'] for a, b in zip(group, group[1:])
        ):
            problems.append(f'操作{index + 1}不是完整有序点击')
            continue
        timed = [reported[key(item)] for item in group if key(item) in reported]
        ids = {item['interactionId'] for item in timed}
        if 0 in ids or len(ids) > 1 or ids & used_ids:
            problems.append(f'操作{index + 1}的系统交互编号冲突')
        used_ids.update(ids)
        # Event Timing 将时长量化；额外保留完整8ms余量，不依赖具体舍入方向。
        # 低于16ms上报阈值的事件只记[0,24]区间，不能当成0ms或精确24ms。
        lower = max([max(0, entry['duration'] - 8) for entry in timed], default=0)
        upper = max([reported[key(item)]['duration'] + 8 if key(item) in reported else 24 for item in group])
        if index >= warmup:
            intervals.append({'lower_ms': lower, 'upper_ms': upper, 'reported_events': len(timed), 'censored_events': 3 - len(timed)})
    if len(intervals) != samples:
        problems.append('正式完整点击数量不足')
    complete = not problems
    lower = sorted(x['lower_ms'] for x in intervals)[math.ceil(samples * .95) - 1] if complete else None
    upper = sorted(x['upper_ms'] for x in intervals)[math.ceil(samples * .95) - 1] if complete else None
    status = 'incomplete' if not complete else 'passed_upper_bound' if upper <= 300 else 'failed' if lower > 300 else 'indeterminate'
    return {'action': action, 'complete': complete, 'status': status, 'planned_samples': samples,
            'observed_operations': len(primary), 'formal_intervals_ms': intervals,
            'p95_ms': None, 'p95_lower_bound_ms': lower, 'p95_upper_bound_ms': upper,
            'measurement': '原生点击事件至下一次渲染的系统计时区间；按完整pointerdown/pointerup/click中最大时长分组，不含后续异步业务完成时间。',
            'drop_diagnostic_available': dropped is not None,
            'delivery_basis': '依Event Timing实时观察器交付契约与完整输入计数对照解释阈值删失；额外丢弃诊断未提供时保持null，不宣称读到了零。',
            'problems': problems}
