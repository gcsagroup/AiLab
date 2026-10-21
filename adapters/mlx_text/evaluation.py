"""固定文本评测规则；只解析声明式数据，不运行数据中的表达式或代码。"""

import json
import hashlib
import math
from datetime import datetime
from pathlib import Path

from workers.mlx_worker import WorkerError as InputError, canonical_digest, verify_snapshot_manifest

CATEGORIES = ("business", "format", "regression", "behavior")
RULES = {"exact", "contains_all", "json_equals", "manual"}
VERSION = "text-rules-v1"


class EvaluationError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError("JSON 出现重复字段")
            result[key] = item
        return result

    def constant(_):
        raise ValueError("JSON 不接受非有限数")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=constant)


def rate(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise EvaluationError("INVALID_EVALUATION_CRITERIA", f"{name} 必须为 0 到 1 的有限数")
    return value


def load_plan(snapshot):
    paths = {}
    for kind in ("dataset", "criteria"):
        field = f"evaluation_{kind}"
        path = Path(snapshot.get(field + "_path", ""))
        if not path.is_absolute() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise EvaluationError("EVALUATION_PLAN_REQUIRED", "评测集与规则必须是已冻结的本地小文件")
        try:
            verify_snapshot_manifest(path, snapshot.get(field + "_manifest"), snapshot.get(field + "_manifest_digest"), field.upper())
        except InputError as exc:
            raise EvaluationError(exc.code, str(exc)) from exc
        paths[kind] = path
    plan_digest = canonical_digest({key: snapshot[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
    if snapshot.get("evaluation_plan_digest") != plan_digest:
        raise EvaluationError("EVALUATION_PLAN_CHANGED", "评测计划摘要与样本／规则版本不匹配")
    try:
        criteria = strict_json(paths["criteria"].read_text())
        rows = [strict_json(line) for line in paths["dataset"].read_text().splitlines() if line.strip()]
    except (ValueError, UnicodeError) as exc:
        raise EvaluationError("INVALID_EVALUATION_DATA", "评测集或规则不是严格 JSON") from exc
    if isinstance(criteria, dict) and criteria.get("schema_version") == "gsm8k-cot-8shot-v1" and snapshot.get("evaluation_kind") == "capability_comparison":
        from .benchmark import validate_plan
        try:
            validate_plan(rows, criteria)
        except ValueError as error:
            raise EvaluationError("BENCHMARK_CHANGED", str(error)) from error
        return rows, criteria, plan_digest
    if not isinstance(criteria, dict) or set(criteria) != {"schema_version", "category_min_pass_rate", "regression_tolerance", "generation"} or criteria["schema_version"] != VERSION:
        raise EvaluationError("INVALID_EVALUATION_CRITERIA", "评测规则版本或字段不支持")
    thresholds = criteria["category_min_pass_rate"]
    if not isinstance(thresholds, dict) or set(thresholds) != set(CATEGORIES):
        raise EvaluationError("INVALID_EVALUATION_CRITERIA", "必须为业务、格式、正常回归、目标行为分别规定阈值")
    for category, value in thresholds.items():
        rate(value, category)
        if value == 0:
            raise EvaluationError("INVALID_EVALUATION_CRITERIA", "各类别通过率阈值必须大于 0，不能把未评测类别算作通过")
    rate(criteria["regression_tolerance"], "regression_tolerance")
    generation = criteria["generation"]
    if not isinstance(generation, dict) or set(generation) != {"max_tokens", "temperature", "top_p", "seed"} or any(type(generation[key]) not in (int, float) or not math.isfinite(generation[key]) for key in ("temperature", "top_p")) or generation["temperature"] != 0 or generation["top_p"] != 1 or type(generation["max_tokens"]) is not int or not 1 <= generation["max_tokens"] <= 512 or type(generation["seed"]) is not int or not 0 <= generation["seed"] < 2**32:
        raise EvaluationError("INVALID_EVALUATION_CRITERIA", "首个评测组合固定贪心生成，输出限 1—512 词元并显式固定 seed")
    if not 4 <= len(rows) <= 64:
        raise EvaluationError("INVALID_EVALUATION_DATA", "评测集需包含 4—64 条样本且四类别均非空")
    ids, categories = set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "category", "prompt", "rule"} or not isinstance(row["id"], str) or not row["id"] or len(row["id"]) > 80 or row["id"] in ids or row["category"] not in CATEGORIES or not isinstance(row["prompt"], str) or not row["prompt"].strip() or len(row["prompt"]) > 16000:
            raise EvaluationError("INVALID_EVALUATION_DATA", "评测样本字段、编号、类别或提示词无效")
        ids.add(row["id"])
        categories.add(row["category"])
        rule = row["rule"]
        if not isinstance(rule, dict) or rule.get("type") not in RULES:
            raise EvaluationError("INVALID_EVALUATION_RULE", "不支持的规则类型")
        kind = rule["type"]
        if kind == "manual":
            valid = set(rule) == {"type", "instruction"} and isinstance(rule["instruction"], str) and bool(rule["instruction"].strip())
        elif kind == "contains_all":
            valid = set(rule) == {"type", "keywords"} and isinstance(rule["keywords"], list) and 1 <= len(rule["keywords"]) <= 20 and all(isinstance(item, str) and 0 < len(item) <= 256 for item in rule["keywords"])
        else:
            valid = set(rule) == {"type", "expected"} and (isinstance(rule["expected"], str) and bool(rule["expected"].strip()) and len(rule["expected"]) <= 16000 if kind == "exact" else isinstance(rule["expected"], (dict, list)))
        if not valid:
            raise EvaluationError("INVALID_EVALUATION_RULE", "评测规则内容或字段无效")
    if categories != set(CATEGORIES):
        raise EvaluationError("EVALUATION_CATEGORY_MISSING", "业务、格式、正常回归、目标行为的验证集均必须非空")
    return rows, criteria, plan_digest


def model_plan_bound(snapshot):
    """量化准入固定在第一次评测建任务时，不冒称训练前冻结。"""
    binding = snapshot.get("quality_plan_ref", {})
    try:
        frozen = datetime.fromisoformat(binding["frozen_at"])
        created = datetime.fromisoformat(snapshot["evaluation_plan_created_at"])
        submitted = datetime.fromisoformat(snapshot["submitted_at"]) if snapshot.get("submitted_at") else frozen
        return bool(frozen.tzinfo and created.tzinfo and submitted.tzinfo and created <= frozen <= submitted
                    and binding["evaluation_plan_id"] == snapshot["evaluation_plan_id"] and binding["evaluation_plan_digest"] == snapshot["evaluation_plan_digest"])
    except (KeyError, TypeError, ValueError):
        return False


def model_evaluation_identity(snapshot, tokenization_recipe_digest, candidate_recipe_digest=None):
    root = Path(__file__).resolve().parents[2]
    sources = ["adapters/mlx_text/evaluation.py", "adapters/mlx_text/recipe.py", "adapters/mlx_text/preflight.py", "workers/mlx_evaluate_worker.py", "workers/mlx_worker.py", "adapters/mlx_text/benchmark.py", "adapters/mlx_text/evaluation_journal.py"]
    recipe = {"schema_version": "mlx-model-evaluation-v1", "evaluation_kind": snapshot.get("evaluation_kind"), "model_comparison_digest": snapshot["model_comparison_digest"], "evaluation_plan_digest": snapshot["evaluation_plan_digest"],
              "quality_plan_ref_digest": snapshot.get("quality_plan_ref", {}).get("digest"), "tokenization_recipe_digest": tokenization_recipe_digest,
              "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources}}
    if snapshot.get("evaluation_kind") == "capability_comparison":
        recipe["candidate_tokenization_recipe_digest"] = candidate_recipe_digest or snapshot.get("effective_config", {}).get("candidate_tokenization_recipe_digest")
        import importlib.metadata
        import platform
        versions = {}
        for name in ("mlx", "mlx-lm", "transformers", "tokenizers", "numpy"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        recipe["runtime"] = {"python": platform.python_version(), "versions": versions}
    return recipe, canonical_digest(recipe)


def score_rule(output, rule):
    if not isinstance(output, str):
        return {"status": "unknown", "reason": "缺少真实文本输出"}
    kind = rule["type"]
    if kind == "manual":
        return {"status": "pending", "reason": rule["instruction"]}
    if kind == "exact":
        passed = output.strip() == rule["expected"]
        reason = "去除首尾空白后精确相同" if passed else "与预定答案不相同"
    elif kind == "contains_all":
        missing = [keyword for keyword in rule["keywords"] if keyword not in output]
        passed = not missing
        reason = "所有区分大小写的关键词均出现" if passed else "缺少关键词：" + "、".join(missing)
    else:
        try:
            actual = strict_json(output)
            passed = canonical_digest(actual) == canonical_digest(rule["expected"])
            reason = "完整输出可解析且 JSON 值完全相等" if passed else "JSON 值与预定对象不相等"
        except ValueError:
            passed, reason = False, "完整输出不是严格 JSON，不能剥离说明或代码围栏后假定合格"
    return {"status": "passed" if passed else "failed", "reason": reason}


def summarize(rows, criteria, baseline, candidate, prospective):
    samples = []
    totals = {name: {category: {"passed": 0, "total": 0, "manual_pending": 0, "unknown": 0} for category in CATEGORIES} for name in ("baseline", "candidate")}
    for row in rows:
        current = {"id": row["id"], "category": row["category"], "prompt": row["prompt"], "rule": row["rule"]}
        for name, outputs in (("baseline", baseline), ("candidate", candidate)):
            output = outputs.get(row["id"])
            scored = score_rule(output, row["rule"])
            current[name] = {"output": output, **scored}
            count = totals[name][row["category"]]
            count["total"] += 1
            count["passed"] += scored["status"] == "passed"
            count["manual_pending"] += scored["status"] == "pending"
            count["unknown"] += scored["status"] == "unknown"
        samples.append(current)
    for categories in totals.values():
        for count in categories.values():
            count["pass_rate"] = count["passed"] / count["total"] if count["total"] else None
    blocking = []
    for category in CATEGORIES:
        count = totals["candidate"][category]
        if not count["total"] or count["pass_rate"] < criteria["category_min_pass_rate"][category]:
            blocking.append({"code": "CATEGORY_THRESHOLD_FAILED", "category": category})
    regression_delta = totals["candidate"]["regression"]["pass_rate"] - totals["baseline"]["regression"]["pass_rate"]
    if regression_delta < -criteria["regression_tolerance"]:
        blocking.append({"code": "REGRESSION_LIMIT_FAILED", "category": "regression"})
    pending = sum(count["manual_pending"] for categories in totals.values() for count in categories.values())
    unknown = sum(count["unknown"] for categories in totals.values() for count in categories.values())
    if pending:
        blocking.append({"code": "MANUAL_REVIEW_PENDING", "count": pending})
    if unknown:
        blocking.append({"code": "EVALUATION_OUTPUT_MISSING", "count": unknown})
    if not prospective:
        blocking.append({"code": "POSTHOC_EVALUATION", "message": "来源训练没有绑定同一冻结计划，事后评测不能准入"})
    status = "unknown" if unknown else "needs_review" if pending else "failed" if blocking else "passed"
    return {"schema_version": VERSION, "status": status, "eligible": not blocking, "prospective_plan_bound": prospective, "counts": totals, "criteria": criteria, "regression_pass_rate_delta": regression_delta, "manual_pending": pending, "unknown": unknown, "blocking": blocking, "samples": samples, "quality_scope": "仅代表本冻结文本规则集；不代表其他任务或人工语义质量"}
