"""独立人工修订、来源不变与恢复合同；受控字节夹具不作为媒体生成证据。"""
import copy
import hashlib
from pathlib import Path
import struct
import threading

import pytest

from test_control import rig, post, setup_task, submit, wait_attempt
from test_media_flow import media_attempt
from test_backup_restore import plan_restore
from ailab_control.api import create_app
from ailab_control.backup import Backup
from ailab_control.service import Settings
from ailab_control.storage import Fault
from ailab_control.work_revisions import WorkRevisions, mp4_duration_ms
import ailab_control.work_revisions as module


def box(name, body):
    return struct.pack('>I', len(body) + 8) + name + body


def movie(duration=2000, scale=1000, version=0):
    prefix = bytes([version, 0, 0, 0])
    if version == 0:
        header = prefix + b'\0' * 8 + struct.pack('>II', scale, duration) + b'\0' * 80
    else:
        header = prefix + b'\0' * 16 + struct.pack('>IQ', scale, duration) + b'\0' * 80
    return box(b'ftyp', b'isom\0\0\0\0') + box(b'moov', box(b'mvhd', header)) + box(b'mdat', b'fixture-not-decoded')


def saved_work(rig, kind='text', raw=None):
    client, service, *_ = rig
    if kind == 'text':
        project, _, task = setup_task(rig, '受控原文字')
        done = wait_attempt(client, submit(rig, task)[0]['id'])
        attempt = service.store.get('attempt', done['id'])
    else:
        project, attempt, _, _ = media_attempt(rig, kind, movie() if kind == 'video' and raw is None else raw)
    public = post(client, '/works', {'attempt_id': attempt['id'], 'name': '人工修订合同作品'}, 'save-' + attempt['id'])
    work = service.store.get('work', public['id'])
    return WorkRevisions(service), work, attempt


def payload(work, content, parent=None, kind='text'):
    return {'expected_revision': work['revision'], 'parent_revision_id': parent, 'content_kind': kind, 'content': content}


def test_text_versions_keep_original_bytes_recipe_snapshot_and_newline_diff(rig):
    manager, work, attempt = saved_work(rig)
    service = rig[1]
    original = manager.view(work['id'])['original']['content']
    artifact = service.store.get('artifact', work['artifact_id'])
    before_bytes = Path(artifact['storage_path']).read_bytes()
    first = manager.create(work['id'], payload(work, {'text': '人工修订一'}), 'first')
    revision = first['revision']
    assert revision['parent_revision_id'] is None and revision['editor'] == 'user_action'
    assert original['text'] in revision['changes']['diff'] and '+人工修订一' in revision['changes']['diff']
    assert revision['source_artifact_sha256'] == hashlib.sha256(before_bytes).hexdigest()
    second = manager.create(work['id'], payload(first['work'], {'text': '人工修订一\n'}, revision['id']), 'newline')
    assert 'No newline at end of file' in second['revision']['changes']['diff']
    current = service.store.get('work', work['id'])
    assert {key: value for key, value in current.items() if key not in {'revision', 'current_revision_id'}} == {key: value for key, value in work.items() if key != 'revision'}
    assert current['current_revision_id'] == second['revision']['id'] and current['revision'] == 3
    assert Path(artifact['storage_path']).read_bytes() == before_bytes
    assert service.store.get('attempt', attempt['id']) == attempt
    assert manager.generation_recipe(work['id']) == work['recipe']
    view = manager.view(work['id'])
    assert view['original']['content'] == original and len(view['items']) == 2
    assert all(item['generation_recipe_changed'] is False and item['media_content_changed'] is False for item in view['items'])
    # 人工文件不混入原运行的输出列表。
    assert all(item['attempt_id'] == attempt['id'] for item in service.public(attempt)['artifacts'])


def test_lost_save_receipt_reuses_original_revision_even_after_later_revision(rig):
    manager, work, _ = saved_work(rig)
    request = payload(work, {'text': '第一次修订'})
    first = manager.create(work['id'], request, 'lost-receipt')
    second = manager.create(work['id'], payload(first['work'], {'text': '第二次修订'}, first['revision']['id']), 'second')
    assert manager.create(work['id'], request, 'lost-receipt') == first
    assert rig[1].store.get('work', work['id'])['current_revision_id'] == second['revision']['id']
    assert len(rig[1].store.list('work-revision')) == 2
    with pytest.raises(Fault) as error:
        manager.create(work['id'], {**request, 'content': {'text': '同键不同内容'}}, 'lost-receipt')
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'


@pytest.mark.parametrize('damage', ['stale_revision', 'old_parent', 'wrong_kind', 'bool_revision', 'unknown_field', 'empty_text', 'too_long'])
def test_invalid_or_stale_revisions_do_not_advance_current(rig, damage):
    manager, work, _ = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '先保存的修订'}), 'first')
    request = payload(first['work'], {'text': '不能错误覆盖'}, first['revision']['id'])
    if damage == 'stale_revision': request['expected_revision'] = 1
    elif damage == 'old_parent': request['parent_revision_id'] = None
    elif damage == 'wrong_kind': request['content_kind'] = 'voice_script'
    elif damage == 'bool_revision': request['expected_revision'] = True
    elif damage == 'unknown_field': request['content']['runtime'] = {'seed': 0}
    elif damage == 'empty_text': request['content']['text'] = ''
    else: request['content']['text'] = '文' * 16001
    with pytest.raises(Fault): manager.create(work['id'], request, 'invalid')
    assert rig[1].store.get('work', work['id']) == first['work']
    assert len(rig[1].store.list('work-revision')) == 1


def test_parallel_saves_have_one_current_winner_and_do_not_reparent(rig, monkeypatch):
    manager, work, _ = saved_work(rig)
    barrier = threading.Barrier(2)
    original_copy = module.copy_asset
    def synchronized_copy(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        barrier.wait(timeout=5)
        return result
    monkeypatch.setattr(module, 'copy_asset', synchronized_copy)
    outputs = []
    def save(text):
        try: outputs.append(manager.create(work['id'], payload(work, {'text': text}), hashlib.sha256(text.encode()).hexdigest()))
        except Fault as error: outputs.append(error.code)
    threads = [threading.Thread(target=save, args=(text,)) for text in ['甲方修订', '乙方修订']]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=6)
    assert all(not thread.is_alive() for thread in threads)
    assert len(outputs) == 2 and outputs.count('REVISION_CONFLICT') == 1
    assert len(rig[1].store.list('work-revision')) == 1
    assert rig[1].store.get('work', work['id'])['revision'] == 2


@pytest.mark.parametrize('damage', ['original_file', 'recipe', 'source_state', 'parent_file'])
def test_damaged_sources_or_parent_files_reject_new_revisions(rig, damage):
    manager, work, attempt = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '第一版'}), 'first')
    service = rig[1]
    if damage in {'original_file', 'parent_file'}:
        artifact = service.store.get('artifact', work['artifact_id'] if damage == 'original_file' else first['revision']['artifact_id'])
        path = Path(artifact['storage_path']); path.chmod(0o600); path.write_text('被改变')
    elif damage == 'recipe':
        value = service.store.get('work', work['id']); value['recipe']['input']['prompt'] = '伪造生成输入'
        with service.store.transaction(): service.store.put('work', value)
    else:
        attempt['compute_outcome'] = 'failed'
        with service.store.transaction(): service.store.put('attempt', attempt)
    with pytest.raises(Fault):
        manager.create(work['id'], payload(first['work'], {'text': '第二版'}, first['revision']['id']), 'second')
    assert len(service.store.list('work-revision')) == 1


def test_tts_revision_changes_only_sidecar_script_and_original_export_is_explicit(rig):
    manager, work, attempt = saved_work(rig, 'audio')
    assert manager.view(work['id'])['original']['content']['text'] == attempt['snapshot']['input']['prompt']
    before = manager.export_selection(work['id'], None, work['project_id'])
    first = manager.create(work['id'], payload(work, {'text': '只保存文字，不再合成语音。'}, kind='voice_script'), 'tts-script')
    revised = manager.export_selection(work['id'], first['revision']['id'], work['project_id'])
    original = manager.export_selection(work['id'], None, work['project_id'])
    assert original['files'] == before['files'] and original['metadata']['revision'] is None
    assert original['work']['version_id'] == work['artifact_id']
    assert revised['files'][0] == before['files'][0] and len(revised['files']) == 2
    assert revised['files'][1]['path'] == 'revision/voice-script.txt'
    assert Path(revised['files'][1]['source']).read_text() == '只保存文字，不再合成语音。'
    assert revised['recipe'] == original['recipe'] == attempt['snapshot']
    assert revised['metadata']['media_content_changed'] is False


def test_subtitle_sidecar_uses_sealed_mp4_duration_and_escapes_plain_text(rig):
    manager, work, _ = saved_work(rig, 'video')
    view = manager.view(work['id'])
    assert view['duration_ms'] == 2000 and view['original']['content'] == {'cues': []}
    content = {'cues': [{'start_ms': 0, 'end_ms': 1000, 'text': '蓝色陶瓷杯'}, {'start_ms': 1000, 'end_ms': 2000, 'text': '<柔和> & 温暖'}]}
    first = manager.create(work['id'], payload(work, content, kind='subtitles'), 'caption')
    selected = manager.export_selection(work['id'], first['revision']['id'], work['project_id'])
    subtitle = Path(selected['files'][1]['source']).read_text()
    assert subtitle.startswith('WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\n')
    assert '&lt;柔和&gt; &amp; 温暖' in subtitle
    assert selected['files'][0]['path'] == 'work/video.mp4'
    assert first['revision']['content'] == content


@pytest.mark.parametrize('cues', [
    [{'start_ms': True, 'end_ms': 1000, 'text': '不能用布尔时间'}],
    [{'start_ms': 0, 'end_ms': 2001, 'text': '超过真实时长'}],
    [{'start_ms': 0, 'end_ms': 0, 'text': '零时长'}],
    [{'start_ms': 0.0, 'end_ms': 1000, 'text': '时间不是整数'}],
    [{'start_ms': 0, 'end_ms': 1000, 'text': '第一句'}, {'start_ms': 500, 'end_ms': 1500, 'text': '重叠'}],
    [{'start_ms': 0, 'end_ms': 1000, 'text': '不允许\n\n伪字幕块'}],
])
def test_subtitle_time_and_payload_rejections_are_atomic(rig, cues):
    manager, work, _ = saved_work(rig, 'video')
    with pytest.raises(Fault): manager.create(work['id'], payload(work, {'cues': cues}, kind='subtitles'), 'invalid-caption')
    assert rig[1].store.get('work', work['id']) == work and not rig[1].store.list('work-revision')


@pytest.mark.parametrize('raw', [movie(duration=0), movie(scale=0), movie(duration=2**32 - 1), movie()[:-1], box(b'moov', box(b'free', b'unknown')), movie(version=1, duration=2**64 - 1)])
def test_unknown_mp4_duration_is_not_replaced_by_ui_or_recipe_value(raw):
    with pytest.raises(Fault) as error: mp4_duration_ms(raw)
    assert error.value.code == 'SUBTITLE_DURATION_UNKNOWN'
    assert mp4_duration_ms(movie(version=1, duration=3000)) == 3000


def test_export_selects_fixed_revision_and_rejects_foreign_revision(rig):
    manager, work, _ = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '需要固定导出的第一版'}), 'first')
    selected = manager.export_selection(work['id'], first['revision']['id'], work['project_id'])
    manager.create(work['id'], payload(first['work'], {'text': '后来的第二版'}, first['revision']['id']), 'second')
    again = manager.export_selection(work['id'], first['revision']['id'], work['project_id'])
    assert again['files'] == selected['files'] and again['metadata'] == selected['metadata']
    assert again['work']['version_id'] == first['revision']['id']
    other_manager, other, _ = saved_work(rig)
    with pytest.raises(Fault): other_manager.export_selection(other['id'], first['revision']['id'], other['project_id'])
    with pytest.raises(Fault) as error: manager.export_selection(work['id'], first['revision']['id'], other['project_id'])
    assert error.value.code == 'PROJECT_MISMATCH'


def test_public_preview_and_export_metadata_do_not_expand_private_context(rig):
    manager, work, _ = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '公开受控文字'}), 'first')
    record = rig[1].store.get('work-revision', first['revision']['id'])
    record['private_context'] = {'credential': 'private-value-not-for-preview'}
    record['changes']['private_context'] = 'private-value-not-for-preview'
    with rig[1].store.transaction(): rig[1].store.put('work-revision', record)
    import json
    visible = json.dumps(manager.view(work['id']), ensure_ascii=False)
    metadata = json.dumps(manager.export_selection(work['id'], record['id'], work['project_id'])['metadata'], ensure_ascii=False)
    assert 'private-value-not-for-preview' not in visible + metadata
    assert 'model_path' not in visible + metadata and 'snapshot' not in manager.public_revision(record)


def test_original_image_export_does_not_require_text_revision_support(rig):
    manager, work, attempt = saved_work(rig, 'image')
    selected = manager.export_selection(work['id'], None, work['project_id'])
    assert selected['work']['version_id'] == work['artifact_id'] and len(selected['files']) == 1
    assert manager.generation_recipe(work['id']) == attempt['snapshot']
    with pytest.raises(Fault) as error: manager.view(work['id'])
    assert error.value.code == 'WORK_REVISION_UNSUPPORTED'


def test_backup_restore_preserves_revision_bytes_and_accepts_only_valid_snapshot_lineage(rig, tmp_path):
    manager, work, attempt = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '恢复后仍保留的人工版本'}), 'first')
    selected = manager.export_selection(work['id'], first['revision']['id'], work['project_id'])
    old_bytes = Path(selected['files'][1]['source']).read_bytes()
    backup = Backup(rig[1]); saved = backup.create()
    plan = plan_restore(rig, backup, saved, tmp_path / '恢复作品修订')
    result = backup.restore({'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'restore-revisions')
    service = create_app(Settings(Path(result['restored_path']), 'restore-token')).state.service
    try:
        restored = WorkRevisions(service)
        view = restored.view(work['id'])
        assert view['current_revision_id'] == first['revision']['id']
        exported = restored.export_selection(work['id'], first['revision']['id'], work['project_id'])
        assert Path(exported['files'][1]['source']).read_bytes() == old_bytes
        assert exported['metadata']['revision']['source_snapshot_digest'] == attempt['snapshot_digest']
        source = service.store.get('attempt', attempt['id'])
        assert source['snapshot_digest'] != attempt['snapshot_digest']
        current = service.store.get('work', work['id'])
        second = restored.create(work['id'], payload(current, {'text': '恢复后显式新建修订'}, first['revision']['id']), 'after-restore')
        assert second['revision']['source_snapshot_digest'] == source['snapshot_digest']
        corrupted = copy.deepcopy(source)
        corrupted['restoration']['historical_artifacts_unchanged'] = False
        with service.store.transaction(): service.store.put('attempt', corrupted)
        with pytest.raises(Fault) as error: restored.export_selection(work['id'], first['revision']['id'], work['project_id'])
        assert error.value.code == 'WORK_REVISION_SOURCE_MISMATCH'
    finally:
        service.close()
