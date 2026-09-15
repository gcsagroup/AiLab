"""人工修订的字符、字幕数量和实际 UTF-8 文件边界；不运行模型。"""
import pytest

from ailab_control.storage import Fault
from ailab_control.work_revisions import content_bytes, validate_content


@pytest.mark.parametrize('kind', ['text', 'voice_script'])
@pytest.mark.parametrize('text', ['文' * 16000, '𠮷' + '文' * 15999, '𠮷' * 16000])
def test_text_at_character_limit_round_trips_utf8(kind, text):
    content = {'text': text}
    assert validate_content(kind, content) == content
    assert content_bytes(kind, content).decode('utf-8') == text


@pytest.mark.parametrize('kind', ['text', 'voice_script'])
def test_text_over_character_limit_is_rejected(kind):
    with pytest.raises(Fault):
        validate_content(kind, {'text': '𠮷' * 16001})


@pytest.mark.parametrize('text', ['文' * 500, '𠮷' + '文' * 499, '𠮷' * 500])
def test_subtitle_at_per_cue_limit_round_trips(text):
    content = {'cues': [{'start_ms': 0, 'end_ms': 2000, 'text': text}]}
    assert validate_content('subtitles', content, 2000) == content
    assert text in content_bytes('subtitles', content).decode('utf-8')


def test_200_cues_at_total_character_limit_are_valid():
    cues = [{'start_ms': i * 10, 'end_ms': (i + 1) * 10, 'text': '字' * 80} for i in range(200)]
    cues[-1]['text'] = '𠮷' + '字' * 79
    assert sum(len(cue['text']) for cue in cues) == 16000
    assert validate_content('subtitles', {'cues': cues}, 2000) == {'cues': cues}
    data = content_bytes('subtitles', {'cues': cues})
    assert len(data) <= 65536 and data.count(b' --> ') == 200


@pytest.mark.parametrize('damage', ['count', 'per_cue', 'total'])
def test_subtitle_actual_limits_reject(damage):
    cues = [{'start_ms': i * 10, 'end_ms': (i + 1) * 10, 'text': '字' * 80} for i in range(200)]
    if damage == 'count':
        cues.append({'start_ms': 2000, 'end_ms': 2010, 'text': '多一条'})
    elif damage == 'per_cue':
        cues[0]['text'] = '字' * 501
    else:
        cues[0]['text'] += '字'
    with pytest.raises(Fault):
        validate_content('subtitles', {'cues': cues}, 2010)
