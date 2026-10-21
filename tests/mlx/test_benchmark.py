"""完整数据、参考数值规则和恢复边界；不以合成回答冒充模型成绩。"""

import copy
import json
from types import SimpleNamespace

import pytest

from adapters.mlx_text.benchmark import bundled, make_plan, prompt_for, score, validate_plan
from adapters.mlx_text.evaluation_journal import append, read_prefix
from workers.mlx_evaluate_worker import collect_prediction


def test_official_full_split_and_frozen_smoke_are_distinct():
    data, protocol, _ = bundled()
    rows, criteria = make_plan("gsm8k-full")
    smoke, smoke_criteria = make_plan("gsm8k-smoke")
    assert len(data) == len(rows) == 1319 and len(smoke) == 12
    assert len({row["id"] for row in rows}) == 1319
    assert len(protocol["fewshot_config"]["samples"]) == 8
    validate_plan(rows, criteria)
    validate_plan(smoke, smoke_criteria)
    for altered in [rows[:-1], list(reversed(rows)), rows + rows[:1]]:
        with pytest.raises(ValueError):
            validate_plan(altered, criteria)
    changed = copy.deepcopy(criteria)
    changed["generation"]["max_tokens"] = 2048
    with pytest.raises(ValueError):
        validate_plan(rows, changed)


def test_prompt_has_eight_fixed_examples_without_test_answer():
    rows, criteria = make_plan("gsm8k-full")
    row = {**rows[0], "rule": {"expected": "TEST-ANSWER-MUST-NOT-ENTER-PROMPT"}}
    prompt = prompt_for(row, criteria)
    assert prompt.count("Q: ") == 9 and prompt.endswith("A:")
    assert "TEST-ANSWER-MUST-NOT-ENTER-PROMPT" not in prompt
    assert rows[0]["prompt"] in prompt


@pytest.mark.parametrize("output,expected,strict,flexible", [
    ("There were 10; subtract 13. The answer is -3.", "-3", True, True),
    ("The answer is 1,234.", "1234", True, True),
    ("The answer is 1.25.", "1.25", True, True),
    ("The answer is 12.0.", "12", False, False),
    ("The answer is 4. Later I computed 8.", "4", True, False),
    ("I count 4 and 7", "7", False, True),
    ("42", "42", False, True),
    ("The answer is $42.", "42", False, True),
    ("THE ANSWER IS 42.", "42", False, True),
    ("The answer is nan.", "0", False, False),
    ("No answer", "42", False, False),
    ("", "42", False, False),
])
def test_reference_extraction_rules(output, expected, strict, flexible):
    result = score(output, expected)
    assert result["strict_passed"] is strict
    assert result["flexible_passed"] is flexible
    assert result["output"] == output


def test_journal_requires_confirmed_prefix_and_detects_changed_content(tmp_path):
    rows, _ = make_plan("gsm8k-smoke")
    path = tmp_path / "answers.jsonl"
    first = append(path, rows[0], "baseline", "frozen-recipe", "The answer is 3.", {"finish_reason": "stop"}, None)
    # 尚未得到控制层确认的第二题以及残缺尾行不用于恢复。
    append(path, rows[1], "baseline", "frozen-recipe", "answer two", {}, first["digest"])
    with path.open("a") as stream:
        stream.write('{"incomplete":')
    assert read_prefix(path, 1, first["digest"], rows, "baseline", "frozen-recipe") == [first]
    for variant, recipe, head in [("candidate", "frozen-recipe", first["digest"]), ("baseline", "changed", first["digest"]), ("baseline", "frozen-recipe", "wrong")]:
        with pytest.raises(ValueError):
            read_prefix(path, 1, head, rows, variant, recipe)
    path.write_text(path.read_text().replace("The answer is 3.", "The answer is 4."))
    with pytest.raises(ValueError):
        read_prefix(path, 1, first["digest"], rows, "baseline", "frozen-recipe")


def test_stop_sequence_can_span_tokens_and_closes_generator():
    closed = []
    def responses():
        try:
            for index, text in enumerate(["The answer is 4.", "\nQ", ": another question"]):
                yield SimpleNamespace(text=text, token=index, generation_tokens=index + 1, finish_reason=None)
            raise AssertionError("停止条件后不能继续生成")
        finally:
            closed.append(True)
    text, observation = collect_prediction(responses(), lambda: None, ("Q:",))
    assert text == "The answer is 4.\n"
    assert observation["finish_reason"] == "stop_sequence" and closed
