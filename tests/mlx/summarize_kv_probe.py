"""核对已封存 KV 实算报告并生成中文汇总；不加载模型，也不改原报告。"""
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.artifacts/m2-kv'
NAMES = {'functional': 'functional-20260910-v1', 'performance': 'performance-20260910-v1',
         'quality': 'quality-20260910-v1', 'v2_quality': 'low-memory-v2-20260910-v1',
         'v2_acceptance': 'low-memory-v2-acceptance-20260910-v1'}


def main():
    reports = {key: json.loads((BASE / name / 'report.json').read_text()) for key, name in NAMES.items()}
    assert [len(reports[key]['cases']) for key in NAMES] == [18, 68, 36, 12, 36]
    assert all(reports[key]['source_unchanged'] for key in ('functional', 'performance', 'quality'))
    q = reports['quality']['cases']
    quality = [{'model': model, 'preset': preset, 'correct': sum(c['answer_correct'] for c in q if c['model'] == model and c['preset'] == preset), 'total': 6}
               for model in ('bf16', 'weight_q4') for preset in ('default', 'low_memory', 'low_latency')]
    assert [row['correct'] for row in quality] == [4, 1, 4, 5, 0, 5]
    assert all(c['auto_chunking_token_ids_equal'] for c in q if c['preset'] == 'low_latency')
    v2 = reports['v2_quality']
    assert v2['status'] == 'passed_no_regression' and v2['original_fixed_tasks_correct'] == 9
    assert all(c['token_ids_equal_original_default'] and c['instrumentation_tokens_match_default'] and c['instrumentation_tokens_match_candidate'] and c['logit_comparison']['argmax_equal'] for c in v2['cases'])
    acceptance = reports['v2_acceptance']
    assert acceptance['status'] == 'passed' and acceptance['source_models_unchanged'] and acceptance['source_adapter_unchanged'] and acceptance['adapter_recipe_distinct']
    assert Counter(c['category'] for c in acceptance['cases']) == {'performance': 18, 'isolation': 8, 'adapter_isolation': 4, 'cancel': 4, 'cancel_recovery': 2}
    assert all(c['execution']['process_group_gone'] for key in ('functional', 'performance', 'quality', 'v2_quality', 'v2_acceptance') for c in reports[key]['cases'])
    cancels = [c for c in acceptance['cases'] if c['category'] == 'cancel']
    assert all(c['execution']['returncode'] == 130 for c in cancels)
    assert all(c['actual_output_tokens'] == [128, 128, 128] for key in ('performance', 'v2_acceptance') for c in reports[key]['performance_medians'])
    refs = [{'key': key, 'path': str((BASE / name / 'report.json').relative_to(ROOT)), 'sha256': hashlib.sha256((BASE / name / 'report.json').read_bytes()).hexdigest()} for key, name in NAMES.items()]
    summary = {'schema_version': 'kv-acceptance-summary-v1', 'date': '2026-09-10', 'scope': '固定本机 Qwen2.5-0.5B 两种权重；原执行源码见各报告摘要，后续产品集成另验',
               'q4_cache_decision': 'No-Go', 'low_memory_v2_decision': 'passed_no_regression', 'quality': quality,
               'v2_original_fixed_tasks_correct': 9, 'v2_original_fixed_tasks_total': 12,
               'model_processes': {'total': 194, 'completed': 190, 'cancelled_as_requested': 4, 'includes_read_only_logits_observers': 24},
               'v2_first_step_logits': {'argmax_equal': 12, 'exact_equal': sum(c['logit_comparison']['exact_equal'] for c in v2['cases']), 'max_abs': max(c['logit_comparison']['max_abs'] for c in v2['cases']), 'max_rmse': max(c['logit_comparison']['rmse'] for c in v2['cases'])},
               'cancel_to_exit_seconds': [c['execution']['cancel_to_exit_seconds'] for c in cancels],
               'original_performance_medians': reports['performance']['performance_medians'], 'v2_independent_performance_medians': acceptance['performance_medians'], 'references': refs}
    (BASE / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    model_name = {'bf16': 'BF16 权重', 'weight_q4': '4 bit 权重'}
    preset_name = {'default': '默认 auto/2048', 'low_memory': '旧候选 q4/512', 'low_latency': '长输入低延迟 auto/4096'}
    lines = ['# 本机文本运行预设与 KV 缓存实算封存', '', '日期：2026-09-10。**原 q4/512 缓存候选 No-Go；新 auto/512 候选通过固定题无新增回归、隔离、取消与性能检查。** 本文只覆盖固定本机执行器，前端应用、提交、配方重载和最终搬移安装包另有验收，不能据此宣布完整 M2 或跨设备通过。', '',
             '## 组合与证据口径', '', '本机 Apple M5 Max、128 GiB 内存，macOS 26.6.2；Python 3.13.9、MLX 0.32.2、MLX-LM 0.31.3。模型为 Qwen2.5-0.5B-Instruct 的原 BF16 与本地 affine 4 bit/group 64 权重；模型和 LoRA 原文件摘要在各轮结束后保持不变。性能输入经真实模板分词后为 62、1022、3582 token；每项 max_tokens=128、seed=0、temperature=0、top_p=1，所有性能轮实际输出均为 128 token。', '',
             '共 194 个模型进程：190 个正常完成、4 个按要求取消，其中 24 个为首步 logits 的独立只读观察进程。这个数量是执行统计，不能当作回答全部正确。原计划和 q4 失败报告保留；v2 在新目录先保存计划，再独立运行。', '',
             '## 原候选的功能与质量', '', '基础 18/18 执行成功；性能 68/68 包括 2 次暖机、54 次三轮交错对照和 12 次归因。24 层缓存均实际回读：每次初始为空，普通缓存为 KVCache，q4 为 QuantizedKVCache。长输入结束时普通 KV 45 MiB，q4 KV 12.65625 MiB。', '',
             '| 权重 | 配置 | 严格固定题正确数 |', '| --- | --- | --- |']
    lines += [f"| {model_name[c['model']]} | {preset_name[c['preset']]} | {c['correct']}/6 |" for c in quality]
    lines += ['', '固定题是加法、编号提取、裸 JSON、长文本前／中／尾代号检索。普通 auto/2048 与 auto/4096 的 12 对输出 token ID 完全相同；默认 BF16 加法答错，两个默认权重的 JSON 加了围栏，均按原规则记错。q4/512 的 6 次长检索全部失败，并出现重复和结构损坏，因此保持 No-Go。源代码复核只确认调用与上游合同一致，不能将失败根因断言为某个上游内核缺陷。', '',
              '## 新 auto/512 候选', '', 'v2 只将 KV 恢复模型计算精度，保留 512 token 分块。12 个原固定题的全部输出 token ID 与原默认完全相同；原默认正确数仍为 9/12，结论是没有新增回归。12 对首步完整词表 logits 均有限、argmax 相同，6 个短题逐元素相同；6 个长题存在舍入差异，最大绝对差 %.6f，最大 RMSE %.6f，不能称数值完全一致。' % (summary['v2_first_step_logits']['max_abs'], summary['v2_first_step_logits']['max_rmse']), '',
              'v2 另跑 36/36：18 次独立性能、8 次 A/B 请求与两种权重交错、4 次真实 LoRA 关闭／开启／关闭／开启、4 次在实际 Prefill／Decode 事件后取消、2 次取消后恢复。每次新缓存为空，重复输出分别匹配自身冷启动；适配器身份不同。4 次取消退出码为 130、无 completed，进程组自然回收约 92—123 ms；恢复输出与取消前一致。', '',
              '## 性能与取舍', '', '表中均为 3 次中位数。TTFT 从建立本次缓存前到首个引擎词元，排除模型加载；生成峰值是在生成前重置 MLX 计数后的峰值，包含已加载权重。它不是整机内存或进程 RSS。各原报告另存加载时间、Decode 速度、整个进程墙钟、RSS 和所有单次值。', '',
              '| 轮次／配置 | 权重 | 输入 token | TTFT ms | 生成峰值 MiB | KV MiB |', '| --- | --- | --- | --- | --- | --- |']
    for row in reports['performance']['performance_medians']:
        if row['prompt_tokens'] == 3582:
            m = row['metrics']; label = {'diagnostic_auto_512': '原归因 auto/512', 'diagnostic_q4_2048': '原归因 q4/2048'}.get(row['preset'], preset_name.get(row['preset']))
            lines.append(f"| {label} | {model_name[row['model']]} | 3582 | {m['first_token_seconds']*1000:.2f} | {m['mlx_generation_peak_bytes']/1048576:.2f} | {m['final_kv_allocated_bytes']/1048576:.5g} |")
    for row in acceptance['performance_medians']:
        m = row['metrics']; lines.append(f"| v2 独立 auto/512 | {model_name[row['model']]} | {row['prompt_tokens']} | {m['first_token_seconds']*1000:.2f} | {m['mlx_generation_peak_bytes']/1048576:.2f} | {m['final_kv_allocated_bytes']/1048576:.5g} |")
    lines += ['', 'auto/512 在中长输入降低了生成峰值，KV 大小保持原样，代价是首 token 更慢；短输入没有稳定内存收益。原 auto/512 归因与 v2 独立测量是不同轮次，不能合成同轮统计或使用不同时间的单次结果计算保证收益。auto/4096 在本机长输入三轮均略快于各自默认，BF16 中位 169.43→160.01 ms，4 bit 权重 166.76→160.63 ms；后者峰值从 1047.65 增到 1187.53 MiB，不能宣称通用加速或更省内存。', '',
              '## 剩余边界与复核', '', '未开放 NVIDIA／远程、其它模型、旋转窗口、跨请求前缀复用、推测解码、多模态缓存和 Prefill／Decode 分离。前缀命中率记录 null（未启用），不是 100%。q4 缓存后续必须作为新候选重新立项，不能通过改名复用本次失败证据。新增产品字段或执行源码后的快照必须重新 preflight，旧证据不回写成新版本。', '',
              '汇总脚本 `tests/mlx/summarize_kv_probe.py` 实际读取以下封存报告，断言数量、质量、token 对照、进程回收和性能输出长度，并生成 `.artifacts/m2-kv/summary.json`。历史源码摘要以各报告和 frozen-plan 为准。', '']
    lines += [f"- `{r['path']}`，SHA-256 `{r['sha256']}`" for r in refs]
    (ROOT / 'adapters/mlx_text/PRESETS_ACCEPTANCE.md').write_text('\n'.join(lines) + '\n')
    print('通过：5 份封存报告一致；已生成中文验收报告与 summary.json。')


if __name__ == '__main__':
    main()
