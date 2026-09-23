"""评测观测须保留实际结束信号、完整输出及取消行为；不替代模型质量测试。"""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from workers import mlx_evaluate_worker as evaluator
from test_evaluation import fixture_plan


def response(text, token, count, reason=None):
    return SimpleNamespace(text=text, token=token, generation_tokens=count, finish_reason=reason)


@pytest.mark.parametrize('responses,expected,reason', [
    ([response('4', 19, 1), response('', 151645, 2, 'stop')], '4', 'stop'),
    ([response('', 151645, 1, 'stop')], '', 'stop'),
    ([response('', 101, 1), response('完整🙂', 102, 2, 'length')], '完整🙂', 'length'),
    ([response('尾部', 103, 1, 'length')], '尾部', 'length'),
    ([response('未完成', 104, 1)], '未完成', 'unknown'),
    ([], '', 'unknown'),
])
def test_stream_preserves_final_text_tokens_and_actual_end(responses, expected, reason):
    closed = []
    def stream():
        try:
            yield from responses
        finally:
            closed.append(True)
    text, observation = evaluator.collect_prediction(stream(), lambda: None)
    assert text == expected == ''.join(item.text for item in responses)
    assert observation['output_token_ids'] == [item.token for item in responses]
    assert observation['generated_tokens'] == (responses[-1].generation_tokens if responses else 0)
    assert observation['finish_reason'] == reason
    assert observation['stream_response_count'] == len(responses)
    assert (observation['first_token_seconds'] is None) == (not responses)
    assert observation['generation_seconds'] >= 0
    assert closed == [True]


def test_cancellation_closes_stream_and_does_not_publish_partial_prediction():
    closed, consumed = [], []
    def stream():
        try:
            consumed.append(1)
            yield response('部分', 1, 1)
            consumed.append(2)
            yield response('不能继续', 2, 2)
        finally:
            closed.append(True)
    def cancel():
        raise evaluator.worker.WorkerError('CANCELLED', '本轮取消')
    with pytest.raises(evaluator.worker.WorkerError, match='本轮取消'):
        evaluator.collect_prediction(stream(), cancel)
    assert consumed == [1] and closed == [True]


def test_generator_failure_is_not_reported_as_a_normal_stop():
    def stream():
        yield response('部分', 1, 1)
        raise RuntimeError('执行器中断')
    with pytest.raises(RuntimeError, match='执行器中断'):
        evaluator.collect_prediction(stream(), lambda: None)


def test_lora_report_preserves_both_pass_observations_and_original_scoring(tmp_path, monkeypatch):
    snapshot, rows, criteria = fixture_plan(tmp_path)
    adapter = tmp_path / 'adapter'; adapter.mkdir()
    (adapter / 'adapter_config.json').write_text(json.dumps({'evaluation_plan_digest': snapshot['evaluation_plan_digest']}))
    snapshot.update(adapter_path=str(adapter), model_manifest_digest='a' * 64)
    output = tmp_path / 'output'; output.mkdir()
    observations = {}
    class CompletedPass:
        returncode = 0
        def __init__(self, command, **kwargs):
            variant = command[-1]
            destination = Path(command[command.index('--output-dir') + 1]); destination.mkdir()
            observations[variant] = {row['id']: {'output_token_ids': [1, 151645], 'generated_tokens': 2, 'finish_reason': 'stop'} for row in rows}
            predictions = {'outputs': {row['id']: '对' if variant == 'baseline' else '错' for row in rows}, 'identity': {'pid': 1 if variant == 'baseline' else 2}, 'observations': observations[variant]}
            (destination / 'predictions.json').write_text(json.dumps(predictions))
        def poll(self):
            return self.returncode
    monkeypatch.setattr(evaluator.subprocess, 'Popen', CompletedPass)
    evaluator.run_evaluate(snapshot, {}, output, lambda *args, **kwargs: None, lambda: None)
    report = json.loads((output / 'evaluation-report.json').read_text())
    assert report['observations'] == observations
    assert report['status'] == 'failed' and not report['eligible']
    assert all(item['baseline']['output'] == '对' and item['candidate']['output'] == '错' for item in report['samples'])
