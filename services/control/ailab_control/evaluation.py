"""冻结文本评测计划与候选门禁；结果不因事后改阈值而变成合格。"""

import json
from pathlib import Path
import tempfile
import unicodedata

from .assets import authorized_path, copy_asset, file_hash, regular_path, safe_json, verify_manifest
from .storage import Fault, digest, encode, identifier, now

CATEGORIES = ("business", "format", "regression", "behavior")


def strict_json(contents):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("重复 JSON 字段")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("JSON 不接受非有限数")

    return json.loads(contents, object_pairs_hook=pairs, parse_constant=constant)


def read_rows(path):
    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise Fault("INVALID_EVALUATION_DATA", "评测集需为不超过 4 MiB 的 JSONL 文件。")
    try:
        rows = [strict_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise Fault("INVALID_EVALUATION_DATA", "评测集必须使用 UTF-8 严格 JSONL，不能含重复字段。") from None
    if not 4 <= len(rows) <= 64:
        raise Fault("INVALID_EVALUATION_DATA", "评测集需包含 4—64 条样本，四类别均非空。")
    ids, prompts, counts = set(), set(), dict.fromkeys(CATEGORIES, 0)
    for index, row in enumerate(rows, 1):
        valid = isinstance(row, dict) and set(row) == {"id", "category", "prompt", "rule"}
        if not valid or not isinstance(row["id"], str) or not 1 <= len(row["id"]) <= 80 or row["id"] in ids or not isinstance(row["category"], str) or row["category"] not in CATEGORIES or not isinstance(row["prompt"], str) or not row["prompt"].strip() or len(row["prompt"]) > 16000:
            raise Fault("INVALID_EVALUATION_DATA", "评测样本字段、编号、类别或提示词无效。", line=index)
        ids.add(row["id"])
        prompt = normalized_prompt(row["prompt"])
        if prompt in prompts:
            raise Fault("EVALUATION_DUPLICATE_PROMPT", "评测集包含规范化后完全重复的提示词。", line=index)
        prompts.add(prompt)
        counts[row["category"]] += 1
        rule = row["rule"]
        if not isinstance(rule, dict) or not isinstance(rule.get("type"), str):
            raise Fault("INVALID_EVALUATION_RULE", "评测规则必须为声明式对象。", line=index)
        kind = rule["type"]
        if kind == "manual":
            valid = set(rule) == {"type", "instruction"} and isinstance(rule["instruction"], str) and bool(rule["instruction"].strip())
        elif kind == "contains_all":
            valid = set(rule) == {"type", "keywords"} and isinstance(rule["keywords"], list) and 1 <= len(rule["keywords"]) <= 20 and all(isinstance(value, str) and 0 < len(value) <= 256 for value in rule["keywords"])
        elif kind in {"exact", "json_equals"}:
            expected = rule.get("expected")
            valid = set(rule) == {"type", "expected"} and (isinstance(expected, str) and bool(expected.strip()) and len(expected) <= 16000 if kind == "exact" else isinstance(expected, (dict, list)))
        else:
            valid = False
        if not valid:
            raise Fault("INVALID_EVALUATION_RULE", "不支持的评测规则或字段。", line=index)
    if not all(counts.values()):
        raise Fault("EVALUATION_CATEGORY_MISSING", "业务、格式、正常回归、目标行为四类别必须均非空。")
    return rows, counts


def normalized_prompt(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def passes(output, rule):
    if not isinstance(output, str) or rule["type"] == "manual":
        return False
    if rule["type"] == "exact":
        return output.strip() == rule["expected"]
    if rule["type"] == "contains_all":
        return all(value in output for value in rule["keywords"])
    try:
        return digest(strict_json(output)) == digest(rule["expected"])
    except ValueError:
        return False


def validate_scored_report(attempt, report, plan, expected_loads):
    """准入独立重算规则和进程身份，不信任报告中的通过标志。"""
    if report.get("schema_version") != "text-rules-v1" or report.get("eligible") is not True or report.get("status") != "passed" or report.get("prospective_plan_bound") is not True or report.get("blocking") != [] or report.get("manual_pending") != 0 or report.get("unknown") != 0:
        raise Fault("EVALUATION_FAILED", "候选未通过全部预定规则，或仍需人工评审。", 409)
    loads = report.get("independent_loads", {})
    if not isinstance(loads, dict) or set(loads) != {"baseline", "candidate"}:
        raise Fault("INDEPENDENT_LOAD_REQUIRED", "报告缺少基线与候选的独立加载证据。", 409)
    for variant, expected in expected_loads.items():
        identity = loads[variant]
        if not isinstance(identity, dict) or type(identity.get("pid")) is not int or identity["pid"] <= 0 or any(identity.get(key) != value for key, value in expected.items()):
            raise Fault("INDEPENDENT_LOAD_REQUIRED", "独立加载证据与本次冻结输入不一致。", 409)
    if loads["baseline"]["pid"] == loads["candidate"]["pid"] or attempt.get("process", {}).get("pid") in {loads["baseline"]["pid"], loads["candidate"]["pid"]}:
        raise Fault("INDEPENDENT_LOAD_REQUIRED", "基线与候选没有分别在独立进程加载。", 409)
    rows, counts = read_rows(Path(plan["evaluation_dataset_path"]))
    samples = report.get("samples")
    if not isinstance(samples, list) or len(samples) != len(rows):
        raise Fault("EVALUATION_REPORT_INVALID", "报告逐样本结果不完整。", 409)
    totals = {variant: dict.fromkeys(CATEGORIES, 0) for variant in ("baseline", "candidate")}
    for row, sample in zip(rows, samples):
        if not isinstance(sample, dict) or any(sample.get(key) != value for key, value in row.items()):
            raise Fault("EVALUATION_REPORT_INVALID", "报告样本与冻结评测集不一致。", 409)
        for variant in ("baseline", "candidate"):
            result = sample.get(variant)
            if not isinstance(result, dict) or not isinstance(result.get("output"), str) or row["rule"]["type"] == "manual":
                raise Fault("EVALUATION_REPORT_INVALID", "报告缺少真实输出或仍需人工评审。", 409)
            passed = passes(result["output"], row["rule"])
            if result.get("status") != ("passed" if passed else "failed"):
                raise Fault("EVALUATION_REPORT_INVALID", "报告计分与冻结规则不一致。", 409)
            totals[variant][row["category"]] += passed
    rates = {variant: {category: totals[variant][category] / counts[category] for category in CATEGORIES} for variant in totals}
    expected_counts = {variant: {category: {"passed": totals[variant][category], "total": counts[category], "manual_pending": 0, "unknown": 0, "pass_rate": rates[variant][category]} for category in CATEGORIES} for variant in totals}
    if report.get("counts") != expected_counts or report.get("regression_pass_rate_delta") != rates["candidate"]["regression"] - rates["baseline"]["regression"]:
        raise Fault("EVALUATION_REPORT_INVALID", "报告汇总与重新核算的逐样本结果不一致。", 409)
    if any(rates["candidate"][category] < plan["criteria"]["category_min_pass_rate"][category] for category in CATEGORIES) or rates["candidate"]["regression"] - rates["baseline"]["regression"] < -plan["criteria"]["regression_tolerance"]:
        raise Fault("EVALUATION_FAILED", "重新核算后候选未通过冻结阈值。", 409)


class Evaluation:
    def __init__(self, service):
        self.service, self.store = service, service.store

    def create_plan(self, payload, key=None):
        with self.store.transaction():
            if key and (previous := self.store.replay("evaluation-plan", key, payload)):
                return previous
            self.store.get("project", payload["project_id"])
        roots = [regular_path(path) for path in self.service.settings.import_roots]
        if payload.get("dataset_grant_id"):
            grant = self.service.grants.get(payload["dataset_grant_id"])
            if grant is None:
                raise Fault("IMPORT_GRANT_EXPIRED", "文件选择已失效，请重新选择评测集。", 403)
            roots.append(grant)
        source = authorized_path(payload["dataset_path"], roots)
        rows, counts = read_rows(source)
        with tempfile.TemporaryDirectory(prefix="evaluation-plan-", dir=self.service.root) as directory:
            temporary = Path(directory)
            (temporary / "evaluation.jsonl").write_text("".join(encode(row) + "\n" for row in rows), encoding="utf-8")
            (temporary / "criteria.json").write_text(encode(payload["criteria"]) + "\n", encoding="utf-8")
            fields = {}
            for kind, name in (("dataset", "evaluation.jsonl"), ("criteria", "criteria.json")):
                path = temporary / name
                manifest = [{"path": name, "size": path.stat().st_size, "sha256": file_hash(path)}]
                identity = digest(manifest)
                destination = copy_asset(path, self.service.root / "assets", manifest, identity)
                fields.update({f"evaluation_{kind}_manifest": manifest, f"evaluation_{kind}_manifest_digest": identity, f"evaluation_{kind}_path": str(destination / name)})
        fields["evaluation_plan_digest"] = digest({key: fields[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
        with self.store.transaction():
            if key and (previous := self.store.replay("evaluation-plan", key, payload)):
                return previous
            plan = self.service.resource("evaluation-plan", payload["project_id"], name=payload["name"], revision=1, status="frozen", criteria=payload["criteria"], sample_count=len(rows), category_counts=counts,
                overlap_check_scope="规范化提示词完全重复检查；近重复与语义泄漏需人工审查", **fields)
            self.store.put("evaluation-plan", plan)
            response = self.service.public(plan)
            if key:
                self.store.remember("evaluation-plan", key, payload, response)
            return response

    def plan_fields(self, plan):
        for kind in ("dataset", "criteria"):
            path = regular_path(plan[f"evaluation_{kind}_path"])
            verify_manifest(path.parent, plan[f"evaluation_{kind}_manifest"])
            if digest(plan[f"evaluation_{kind}_manifest"]) != plan[f"evaluation_{kind}_manifest_digest"]:
                raise Fault("EVALUATION_PLAN_CHANGED", "评测计划文件身份不一致。", 409)
        fields = {key: value for key, value in plan.items() if key.startswith("evaluation_")}
        if digest({key: fields[key] for key in ("evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")}) != fields["evaluation_plan_digest"]:
            raise Fault("EVALUATION_PLAN_CHANGED", "评测计划摘要不一致。", 409)
        if strict_json(Path(fields["evaluation_criteria_path"]).read_text()) != plan["criteria"]:
            raise Fault("EVALUATION_PLAN_CHANGED", "评测规则与冻结记录不一致。", 409)
        fields["evaluation_plan_id"] = plan["id"]
        return fields

    def no_overlap(self, plan, dataset):
        rows, _ = read_rows(Path(plan["evaluation_dataset_path"]))
        prompts = {normalized_prompt(row["prompt"]) for row in rows}
        path = Path(dataset["storage_path"]) / dataset["manifest"][0]["path"]
        for index, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            row = strict_json(line)
            if any(normalized_prompt(message["content"]) in prompts for message in row["messages"] if message["role"] == "user"):
                raise Fault("DATASET_EVALUATION_OVERLAP", "训练数据与冻结评测集包含相同提示词，请先分离数据。", 409, line=index)

    def new_task(self, payload, key=None):
        if payload.get("candidate_model_id"):
            return self.new_model_task(payload, key)
        with self.store.transaction():
            if key and (previous := self.store.replay("evaluation-task", key, payload)):
                return previous
            adapter = self.store.get("adapter", payload["adapter_id"])
            plan = self.store.get("evaluation-plan", payload["evaluation_plan_id"])
            if any(item["project_id"] != payload["project_id"] for item in (adapter, plan)):
                raise Fault("PROJECT_MISMATCH", "适配器与评测计划须属于当前项目。", 403)
            self.plan_fields(plan)
            draft = {"kind": "text", "operation": "evaluate", "model_id": adapter["base_model_id"], "dataset_id": None, "adapter_id": adapter["id"], "evaluation_plan_id": plan["id"],
                     "input": {"prompt": ""}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", **plan["criteria"]["generation"]}}
            task = self.service.resource("task", payload["project_id"], name=payload["name"], kind="text", operation="evaluate", draft_revision=1, draft=draft)
            self.store.put("task", task)
            if key:
                self.store.remember("evaluation-task", key, payload, task)
            return task

    def new_model_task(self, payload, key=None):
        with self.store.transaction():
            if key and (previous := self.store.replay("evaluation-task", key, payload)):
                return previous
            candidate = self.store.get("model", payload["candidate_model_id"])
            plan = self.store.get("evaluation-plan", payload["evaluation_plan_id"])
            if payload.get("adapter_id") or any(item["project_id"] != payload["project_id"] for item in (candidate, plan)):
                raise Fault("PROJECT_MISMATCH", "量化模型和评测计划须属于当前项目，不能同时选择适配器。", 403)
        self.plan_fields(plan)
        base, source, comparison, artifacts = self.service.conversion.quality_source(candidate)
        observed = [("model", candidate), ("model", base), ("attempt", source), ("evaluation-plan", plan), *[("artifact", artifact) for artifact in artifacts]]
        with self.store.transaction():
            if key and (previous := self.store.replay("evaluation-task", key, payload)):
                return previous
            if any(self.store.get(kind, item["id"]) != item for kind, item in observed):
                raise Fault("EVALUATION_IDENTITY_MISMATCH", "创建评测检查期间来源发生变化，请重试。", 409)
            if not candidate.get("quality_plan_ref"):
                binding = {"schema_version": "quantized-model-quality-v1", "model_comparison_digest": digest(comparison), "evaluation_plan_id": plan["id"], "evaluation_plan_digest": plan["evaluation_plan_digest"], "frozen_at": now()}
                candidate["quality_plan_ref"] = {**binding, "digest": digest(binding)}
                self.store.put("model", candidate)
            draft = {"kind": "text", "operation": "evaluate", "evaluation_kind": "quantized_model", "model_id": base["id"], "candidate_model_id": candidate["id"], "dataset_id": None, "adapter_id": None, "evaluation_plan_id": plan["id"],
                     "input": {"prompt": ""}, "runtime": {"engine": "mlx", "device_id": "apple-gpu", **plan["criteria"]["generation"]}}
            task = self.service.resource("task", payload["project_id"], name=payload["name"], kind="text", operation="evaluate", draft_revision=1, draft=draft)
            self.store.put("task", task)
            if key:
                self.store.remember("evaluation-task", key, payload, task)
            return task

    def model_fields(self, task):
        draft = task["draft"]
        if draft.get("evaluation_kind") != "quantized_model" or draft.get("operation") != "evaluate" or not draft.get("candidate_model_id") or draft.get("adapter_id") or draft.get("dataset_id") or draft.get("checkpoint_id"):
            raise Fault("MODEL_COMPARISON_UNSUPPORTED", "权重量化评测需要独立量化模型、固定原权重和方案，不能混用适配器或训练数据。", 409)
        candidate = self.store.get("model", draft["candidate_model_id"])
        if candidate["project_id"] != task["project_id"]:
            raise Fault("PROJECT_MISMATCH", "量化模型须属于当前项目。", 403)
        base, source, comparison, _ = self.service.conversion.quality_source(candidate)
        binding = candidate.get("quality_plan_ref")
        if not isinstance(binding, dict) or binding.get("schema_version") != "quantized-model-quality-v1" or binding.get("digest") != digest({key: value for key, value in binding.items() if key != "digest"}) or binding.get("model_comparison_digest") != digest(comparison) or base["id"] != draft["model_id"]:
            raise Fault("MODEL_QUALITY_PLAN_CHANGED", "此量化模型的首次准入方案或原权重身份无效。", 409)
        return {"evaluation_kind": "quantized_model", "model_id": base["id"], "model_version_id": base["version_id"], "candidate_model_id": candidate["id"], "candidate_model_version_id": candidate["version_id"],
                "candidate_model_path": candidate["storage_path"], "candidate_model_manifest": candidate["manifest"], "candidate_model_manifest_digest": candidate["manifest_digest"],
                "model_comparison": comparison, "model_comparison_digest": digest(comparison), "quality_plan_ref": binding}

    def report(self, attempt):
        if attempt["snapshot"]["operation"] != "evaluate":
            raise Fault("RESOURCE_NOT_FOUND", "此记录不是独立评测。", 404)
        if attempt["compute_outcome"] != "succeeded" or attempt["collection_state"] != "succeeded":
            raise Fault("EVALUATION_NOT_READY", "评测计算和报告收集尚未全部完成。", 409)
        artifact = self.service.delivery.artifact_for_path(attempt, "evaluation-report.json")
        manifest = attempt["output_manifest_ref"]
        if digest({key: value for key, value in manifest.items() if key != "digest"}) != manifest["digest"]:
            raise Fault("EVALUATION_REPORT_INVALID", "原执行产物清单身份不一致。", 409)
        entry = next((item for item in manifest["artifacts"] if item["path"] == "evaluation-report.json"), None)
        if not entry or entry["sha256"] != artifact["sha256"]:
            raise Fault("EVALUATION_REPORT_INVALID", "评测报告已偏离原执行产物清单。", 409)
        return safe_json(Path(artifact["storage_path"])), artifact

    def record(self, attempt, detailed=True):
        if attempt["snapshot"]["operation"] != "evaluate":
            raise Fault("RESOURCE_NOT_FOUND", "此记录不是独立评测。", 404)
        result = self.service.public(attempt)
        # 列表不携带所有产物正文；明细报告只在单条接口返回。
        result.pop("artifacts", None)
        result.update(adapter_id=attempt["snapshot"].get("adapter_id"), evaluation_kind=attempt["snapshot"].get("evaluation_kind", "adapter"), candidate_model_id=attempt["snapshot"].get("candidate_model_id"), evaluation_plan_id=attempt["snapshot"]["evaluation_plan_id"], report=None, report_error=None)
        if attempt["collection_state"] == "succeeded":
            try:
                report, artifact = self.report(attempt)
                result.update(report=report if detailed else {key: value for key, value in report.items() if key not in {"samples", "independent_loads"}}, report_artifact_id=artifact["id"])
            except (Fault, OSError, ValueError) as error:
                result["report_error"] = {"code": error.code if isinstance(error, Fault) else "EVALUATION_REPORT_INVALID", "message": "评测报告缺失或完整性检查失败。"}
        return result

    def validate_eligible(self, attempt, adapter):
        snapshot = attempt["snapshot"]
        if attempt["project_id"] != adapter["project_id"]:
            raise Fault("PROJECT_MISMATCH", "所选评测不属于候选所在项目。", 403)
        if snapshot["operation"] != "evaluate":
            raise Fault("EVALUATION_REQUIRED", "所选记录不是独立评测。", 409)
        source = self.store.get("attempt", adapter["source_attempt_id"])
        plan = self.store.get("evaluation-plan", snapshot["evaluation_plan_id"])
        base = self.store.get("model", adapter["base_model_id"])
        if any(item["project_id"] != adapter["project_id"] for item in (attempt, source, plan, base)):
            raise Fault("PROJECT_MISMATCH", "评测来源或固定依赖不属于当前项目。", 403)
        if any(item["snapshot_digest"] != digest(item["snapshot"]) for item in (attempt, source)) or source["snapshot"]["operation"] != "train" or source["compute_outcome"] != "succeeded" or source["collection_state"] != "succeeded":
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "来源训练或评测的完整快照身份无效。", 409)
        self.plan_fields(plan)
        verify_manifest(Path(adapter["storage_path"]), adapter["manifest"])
        verify_manifest(Path(base["storage_path"]), base["manifest"])
        if source["snapshot"].get("evaluation_plan_id") != plan["id"] or source["snapshot"].get("evaluation_plan_digest") != plan["evaluation_plan_digest"] or plan["created_at"] > source["snapshot"]["submitted_at"] or adapter["config"].get("evaluation_plan_digest") != plan["evaluation_plan_digest"]:
            raise Fault("POSTHOC_EVALUATION", "来源训练未在提交前绑定此冻结计划，事后评测不能准入。", 409)
        expected = {"adapter_id": adapter["id"], "adapter_manifest_digest": adapter["manifest_digest"], "adapter_training_recipe_digest": adapter["training_recipe_digest"], "model_id": base["id"], "model_manifest_digest": base["manifest_digest"], **{key: plan[key] for key in ("evaluation_plan_digest", "evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")}}
        if any(snapshot.get(key) != value for key, value in expected.items()) or adapter["base_manifest_digest"] != base["manifest_digest"]:
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "评测与候选、基座或计划身份不匹配。", 409)
        report, artifact = self.report(attempt)
        if any(report.get(key) != value for key, value in expected.items() if key not in {"adapter_id", "model_id"}) or report.get("criteria") != plan["criteria"]:
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "报告与冻结输入身份不匹配。", 409)
        expected_loads = {variant: {"variant": variant, "model_manifest_digest": base["manifest_digest"], "adapter_manifest_digest": adapter["manifest_digest"] if variant == "candidate" else None, "evaluation_plan_digest": plan["evaluation_plan_digest"], "tokenization_recipe_digest": snapshot["tokenization_recipe_digest"], "generation": plan["criteria"]["generation"]} for variant in ("baseline", "candidate")}
        validate_scored_report(attempt, report, plan, expected_loads)
        return artifact

    def register(self, adapter_id, payload, key):
        if payload.get("candidate_type") == "quantized_model":
            return self.register_model(adapter_id, payload, key)
        if not payload["evaluation_ids"]:
            raise Fault("EVALUATION_REQUIRED", "请先完成独立评测，再选择通过的评测记录登记。", 409)
        with self.store.transaction():
            if previous := self.store.replay(f"register:{adapter_id}", key, payload):
                return previous
            adapter = self.store.get("adapter", adapter_id)
            attempts = [self.store.get("attempt", evaluation_id) for evaluation_id in dict.fromkeys(payload["evaluation_ids"])]
            observed = [("adapter", adapter), ("attempt", self.store.get("attempt", adapter["source_attempt_id"])), ("model", self.store.get("model", adapter["base_model_id"]))]
            for attempt in attempts:
                if attempt["project_id"] != adapter["project_id"]:
                    raise Fault("PROJECT_MISMATCH", "所选评测不属于候选所在项目。", 403)
                if attempt["snapshot"]["operation"] != "evaluate":
                    raise Fault("EVALUATION_REQUIRED", "所选记录不是独立评测。", 409)
                observed.extend([("attempt", attempt), ("evaluation-plan", self.store.get("evaluation-plan", attempt["snapshot"]["evaluation_plan_id"]))])
        # 大文件哈希与逐样本重算在事务之外执行，不能阻塞其他运行的取消。
        artifacts = [self.validate_eligible(attempt, adapter) for attempt in attempts]
        observed.extend(("artifact", artifact) for artifact in artifacts)
        with self.store.transaction():
            if previous := self.store.replay(f"register:{adapter_id}", key, payload):
                return previous
            if any(self.store.get(kind, item["id"]) != item for kind, item in observed):
                raise Fault("EVALUATION_IDENTITY_MISMATCH", "登记检查期间来源记录发生变化，请重新核实后登记。", 409)
            existing = [item for item in self.store.list("candidate", adapter["project_id"]) if item.get("adapter_id") == adapter_id]
            candidate = existing[0] if existing else self.service.resource("candidate", adapter["project_id"], name=adapter["name"], status="registered", quality_status="passed", adapter_id=adapter_id, adapter_version_id=adapter["version_id"], manifest_digest=adapter["manifest_digest"], base_model_id=adapter["base_model_id"], base_model_version_id=adapter["base_model_version_id"], base_manifest_digest=adapter["base_manifest_digest"], source_attempt_id=adapter["source_attempt_id"], evaluation_ids=list(dict.fromkeys(payload["evaluation_ids"])), report_artifact_ids=[item["id"] for item in artifacts], version_id=identifier("candidate-version"), quality_scope="仅通过此冻结文本规则集；试用仍需要精确基座与适配器。")
            self.store.put("candidate", candidate)
            response = self.service.public(candidate)
            self.store.remember(f"register:{adapter_id}", key, payload, response)
            return response

    def validate_model_eligible(self, attempt, candidate):
        snapshot = attempt["snapshot"]
        if attempt["project_id"] != candidate["project_id"]:
            raise Fault("PROJECT_MISMATCH", "所选评测不属于量化模型所在项目。", 403)
        if snapshot.get("operation") != "evaluate" or snapshot.get("evaluation_kind") != "quantized_model":
            raise Fault("EVALUATION_REQUIRED", "量化模型准入需要原权重与该模型的独立质量比较。", 409)
        if attempt.get("snapshot_digest") != digest(snapshot) or snapshot.get("candidate_model_id") != candidate["id"]:
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "评测快照或量化候选身份不一致。", 409)
        plan = self.store.get("evaluation-plan", snapshot["evaluation_plan_id"])
        if plan["project_id"] != candidate["project_id"]:
            raise Fault("PROJECT_MISMATCH", "评测计划不属于当前项目。", 403)
        self.plan_fields(plan)
        fields = self.model_fields({"project_id": candidate["project_id"], "draft": {"operation": "evaluate", "evaluation_kind": "quantized_model", "candidate_model_id": candidate["id"], "model_id": snapshot.get("model_id")}})
        binding = fields["quality_plan_ref"]
        if binding.get("evaluation_plan_id") != plan["id"] or binding.get("evaluation_plan_digest") != plan["evaluation_plan_digest"] or not isinstance(binding.get("frozen_at"), str) or plan["created_at"] > binding["frozen_at"] or binding["frozen_at"] > snapshot.get("submitted_at", ""):
            raise Fault("MODEL_QUALITY_PLAN_MISMATCH", "此报告没有使用量化模型首次固定的准入方案，其他方案仅能作为对照。", 409)
        expected = {key: value for key, value in fields.items() if key != "candidate_model_path"}
        expected.update({key: plan[key] for key in ("evaluation_plan_digest", "evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")})
        if any(snapshot.get(key) != value for key, value in expected.items()) or snapshot.get("evaluation_plan_created_at") != plan["created_at"]:
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "评测没有绑定当前原模型、量化产物和冻结方案的完整身份。", 409)
        report, artifact = self.report(attempt)
        recipe = snapshot.get("effective_config", {}).get("model_evaluation_recipe")
        recipe_digest = snapshot.get("effective_config", {}).get("model_evaluation_recipe_digest")
        if not isinstance(recipe, dict) or digest(recipe) != recipe_digest or recipe.get("model_comparison_digest") != fields["model_comparison_digest"] or recipe.get("evaluation_plan_digest") != plan["evaluation_plan_digest"] or recipe.get("quality_plan_ref_digest") != binding["digest"] or recipe.get("tokenization_recipe_digest") != snapshot.get("tokenization_recipe_digest"):
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "评测执行配方未完整绑定两份权重、分词器和冻结规则。", 409)
        expected_report = {"evaluation_kind": "quantized_model", "prospective_basis": "first_quantized_model_evaluation", "model_comparison": fields["model_comparison"], "model_comparison_digest": fields["model_comparison_digest"], "quality_plan_ref_digest": binding["digest"],
                           "model_manifest_digest": snapshot["model_manifest_digest"], "candidate_model_manifest_digest": candidate["manifest_digest"], "criteria": plan["criteria"], "model_evaluation_recipe_digest": recipe_digest,
                           **{key: plan[key] for key in ("evaluation_plan_digest", "evaluation_dataset_manifest_digest", "evaluation_criteria_manifest_digest")}}
        if any(report.get(key) != value for key, value in expected_report.items()) or report.get("rules_implementation_sha256") != snapshot["tokenization_recipe"].get("evaluation_implementation_sha256"):
            raise Fault("EVALUATION_IDENTITY_MISMATCH", "评测报告与提交时的来源、执行代码或规则不一致。", 409)
        expected_loads = {variant: {"variant": variant, "evaluation_kind": "quantized_model", "model_manifest_digest": snapshot["model_manifest_digest"] if variant == "baseline" else candidate["manifest_digest"], "adapter_manifest_digest": None,
                                    "evaluation_plan_digest": plan["evaluation_plan_digest"], "tokenization_recipe_digest": snapshot["tokenization_recipe_digest"], "generation": plan["criteria"]["generation"], "model_evaluation_recipe_digest": recipe_digest,
                                    "input_quantization": None if variant == "baseline" else fields["model_comparison"]["quantization"]} for variant in ("baseline", "candidate")}
        validate_scored_report(attempt, report, plan, expected_loads)
        return artifact

    def register_model(self, model_id, payload, key):
        if not payload["evaluation_ids"]:
            raise Fault("EVALUATION_REQUIRED", "请先完成权重量化独立评测，再选择通过的记录登记。", 409)
        scope = f"register-model:{model_id}"
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            model = self.store.get("model", model_id)
            if not model.get("source_attempt_id") or not model.get("source_model_id"):
                raise Fault("MODEL_COMPARISON_UNSUPPORTED", "此模型没有可核实的量化转换来源。", 409)
            attempts = [self.store.get("attempt", evaluation_id) for evaluation_id in dict.fromkeys(payload["evaluation_ids"])]
            observed = [("model", model), ("model", self.store.get("model", model["source_model_id"])), ("attempt", self.store.get("attempt", model["source_attempt_id"]))]
            for attempt in attempts:
                if attempt["project_id"] != model["project_id"]:
                    raise Fault("PROJECT_MISMATCH", "评测与量化模型须属于同一项目。", 403)
                if attempt["snapshot"].get("evaluation_kind") != "quantized_model":
                    raise Fault("EVALUATION_REQUIRED", "量化准入不能使用适配器评测或普通运行。", 409)
                observed.extend([("attempt", attempt), ("evaluation-plan", self.store.get("evaluation-plan", attempt["snapshot"]["evaluation_plan_id"]))])
        _, _, _, conversion_artifacts = self.service.conversion.quality_source(model)
        observed.extend(("artifact", artifact) for artifact in conversion_artifacts)
        artifacts = [self.validate_model_eligible(attempt, model) for attempt in attempts]
        observed.extend(("artifact", artifact) for artifact in artifacts)
        with self.store.transaction():
            if previous := self.store.replay(scope, key, payload):
                return previous
            if any(self.store.get(kind, item["id"]) != item for kind, item in observed):
                raise Fault("EVALUATION_IDENTITY_MISMATCH", "登记检查期间原权重、候选或评测记录发生变化。", 409)
            existing = [item for item in self.store.list("candidate", model["project_id"]) if item.get("candidate_type") == "quantized_model" and item.get("model_id") == model_id]
            quality_scope = "仅通过此量化模型首次固定的文本规则集；不代表其他任务或普遍质量、速度收益。"
            candidate = existing[0] if existing else self.service.resource("candidate", model["project_id"], candidate_type="quantized_model", adapter_id=None, model_id=model_id, model_version_id=model["version_id"], name=model["name"], status="registered", quality_status="passed", manifest_digest=model["manifest_digest"],
                source_model_id=model["source_model_id"], source_model_version_id=model["source_model_version_id"], source_manifest_digest=model["source_manifest_digest"], source_attempt_id=model["source_attempt_id"],
                quality_plan_ref=model["quality_plan_ref"], evaluation_ids=list(dict.fromkeys(payload["evaluation_ids"])), report_artifact_ids=[artifact["id"] for artifact in artifacts], version_id=identifier("candidate-version"), default_engine="mlx", format="mlx-safetensors", quality_scope=quality_scope)
            self.store.put("candidate", candidate)
            model.update(status="quality_approved", quality_status="passed", quality_candidate_id=candidate["id"], quality_scope=quality_scope)
            self.store.put("model", model)
            response = self.service.public(candidate)
            self.store.remember(scope, key, payload, response)
            return response
