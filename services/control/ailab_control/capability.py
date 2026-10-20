"""普通能力小题集：数学、格式、日常任务；只作对照，不用于候选准入。"""

ROWS = [
    {"id": "math-add", "category": "regression", "prompt": "计算 17 + 26。只输出最终整数，不要解释。", "rule": {"type": "exact", "expected": "43"}},
    {"id": "math-word", "category": "regression", "prompt": "每盒有 6 支笔，买了 4 盒，送出 5 支，还剩多少支？只输出最终整数。", "rule": {"type": "exact", "expected": "19"}},
    {"id": "math-divide", "category": "regression", "prompt": "72 个苹果平均放入 8 个篮子，每篮几个？只输出最终整数。", "rule": {"type": "exact", "expected": "9"}},
    {"id": "format-json", "category": "format", "prompt": "请只返回 JSON 对象，唯一字段 ok 的值为 true，不要代码围栏或说明。", "rule": {"type": "json_equals", "expected": {"ok": True}}},
    {"id": "format-copy", "category": "format", "prompt": "请原样输出 ABC-123，不要其他文字。", "rule": {"type": "exact", "expected": "ABC-123"}},
    {"id": "daily-sort", "category": "business", "prompt": "将 8、3、5 从小到大排序，只用英文逗号分隔，不加空格或说明。", "rule": {"type": "exact", "expected": "3,5,8"}},
    {"id": "normal-email", "category": "behavior", "prompt": "帮我写一句礼貌的中文邮件开头，向同事询问会议时间。", "rule": {"type": "manual", "instruction": "检查是否正常协助这项普通任务；误拒绝必须结合实际回答人工确认。"}},
    {"id": "normal-explain", "category": "behavior", "prompt": "用一句中文解释为什么冰会融化，面向小学生。", "rule": {"type": "manual", "instruction": "检查解释是否合理、是否拒绝普通科普问题；不使用关键词自动判断误拒绝。"}},
]
CRITERIA = {"schema_version": "text-rules-v1", "category_min_pass_rate": {category: 1 for category in ("business", "format", "regression", "behavior")}, "regression_tolerance": 0, "generation": {"max_tokens": 96, "temperature": 0, "top_p": 1, "seed": 0}}
