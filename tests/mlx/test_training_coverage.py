"""覆盖按家族整组留出、同名跨类别、来源不完整及重复索引反例。"""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('training_coverage', Path(__file__).with_name('audit_training_coverage.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
audit = module.audit


def sample(identifier, source, family, category='business'):
    return dict(id=identifier, source_diagnostic_id=source, family=family, category=category)


def test_grouped_paraphrases_can_remove_a_whole_family():
    rows = [sample('a1', 'a', '金额'), sample('a2', 'a', '金额'), sample('b1', 'b', '运费')]
    result = audit(rows, [dict(source_id='a', subset='validation'), dict(source_id='b', subset='train')])
    assert result['subsets']['train']['samples'] == 1
    assert result['subsets']['validation']['source_groups'] == 1
    assert result['missing_from_training'] == [dict(category='business', family='金额', train_samples=0, validation_samples=2)]
    assert result['quality_approved'] is False


def test_same_family_name_in_different_categories_is_not_coverage():
    result = audit([sample('a', 'a', '数字'), sample('b', 'b', '数字', 'format')],
                   [dict(source_id='a', subset='train'), dict(source_id='b', subset='validation')])
    assert result['source_families'] == 2
    assert result['missing_from_training'][0]['category'] == 'format'
    assert result['subsets']['train']['category_samples']['format'] == 0


@pytest.mark.parametrize('rows,assignments', [
    ([], []),
    ([sample('a', 'a', '金额')], []),
    ([sample('a', 'a', '金额')], [dict(source_id='a', subset='train'), dict(source_id='extra', subset='validation')]),
    ([sample('a', 'a', '金额')], [dict(source_id='a', subset='train'), dict(source_id='a', subset='validation')]),
    ([sample('a', 'a', '金额')]*2, [dict(source_id='a', subset='train')]),
    ([sample('a', 'a', '')], [dict(source_id='a', subset='train')]),
    ([sample('a', 'a', '金额')], [dict(source_id='a', subset='unknown')]),
])
def test_incomplete_or_ambiguous_inputs_rejected(rows, assignments):
    with pytest.raises(ValueError):
        audit(rows, assignments)
