"""临时真实修订的历史分页合同；仅受控字节执行器，不运行真实模型。"""
import copy
from pathlib import Path

import pytest

from test_control import rig, post, submit, wait_attempt
from test_work_revisions import saved_work, payload
from ailab_control.storage import Fault


def add_revision(manager, work, number):
    result = manager.create(work['id'], payload(work, {'text': f'人工修订 {number:03d}\n'}, work.get('current_revision_id')), f'revision-{number}')
    return result['work'], result['revision']


def test_http_history_recovers_oldest_after_one_hundred_revisions(rig, tmp_path):
    client, service, *_ = rig
    manager, work, attempt = saved_work(rig)
    original_work = copy.deepcopy(work)
    original = manager.view(work['id'])['original']
    revisions = []
    for number in range(1, 102):
        work, revision = add_revision(manager, work, number)
        revisions.append(revision)

    # 同项目的另一作品也有修订，不能因分页而混入本作品。
    other_task = post(client, '/tasks', {'project_id': work['project_id'], 'name': '另一作品', 'kind': 'text', 'operation': 'generate'})
    draft = service.store.get('task', attempt['task_id'])['draft']
    response = client.patch(f"/api/v1/tasks/{other_task['id']}/draft", json={'expected_revision': other_task['draft_revision'], 'draft': draft})
    assert response.status_code == 200, response.text
    other_attempt = wait_attempt(client, submit(rig, response.json())[0]['id'])
    other_work = post(client, '/works', {'attempt_id': other_attempt['id'], 'name': '同项目另一作品'}, 'other-work')
    _, foreign_revision = add_revision(manager, other_work, 999)

    database_before = tuple(service.store.db.iterdump())
    changes_before = service.store.db.total_changes
    original_artifact = service.store.get('artifact', work['artifact_id'])
    original_bytes = Path(original_artifact['storage_path']).read_bytes()
    url = f"/api/v1/works/{work['id']}/revisions"
    first = client.get(url).json()
    assert [item['id'] for item in first['items']] == [item['id'] for item in revisions[1:]]
    cursor = first['items'][0]['revision']
    response = client.get(url, params={'before_revision': cursor})
    assert response.status_code == 200, response.text
    oldest = response.json()
    assert [item['id'] for item in oldest['items']] == [revisions[0]['id']]
    assert first['has_more'] and first['next_before_revision'] == cursor
    assert oldest['has_more'] is False and oldest['next_before_revision'] is None
    assert oldest['items'][0]['parent_revision_id'] is None
    assert '+人工修订 001' in oldest['items'][0]['changes']['diff']

    seen, cursor = [], None
    while True:
        query = {'limit': 7}
        if cursor is not None:
            query['before_revision'] = cursor
        page = client.get(url, params=query).json()
        assert page['original'] == original
        assert page['current_revision_id'] == work['current_revision_id'] and page['work_revision'] == work['revision']
        assert 1 <= len(page['items']) <= 7
        numbers = [item['revision'] for item in page['items']]
        assert numbers == sorted(numbers) and (cursor is None or max(numbers) < cursor)
        seen.extend(page['items'])
        if not page['has_more']:
            assert page['next_before_revision'] is None
            break
        cursor = page['next_before_revision']
        assert cursor == min(numbers)
    assert len(seen) == len({item['id'] for item in seen}) == 101
    assert {item['id'] for item in seen} == {item['id'] for item in revisions}
    assert foreign_revision['id'] not in {item['id'] for item in seen}
    second = next(item for item in seen if item['id'] == revisions[1]['id'])
    assert second['parent_revision_id'] == revisions[0]['id']
    assert '-人工修订 001' in second['changes']['diff'] and '+人工修订 002' in second['changes']['diff']
    assert tuple(service.store.db.iterdump()) == database_before and service.store.db.total_changes == changes_before
    assert service.store.get('attempt', attempt['id']) == attempt
    assert service.store.get('work', work['id']) == work
    assert manager.generation_recipe(work['id']) == original_work['recipe']
    assert Path(original_artifact['storage_path']).read_bytes() == original_bytes

    # 从历史页选中的旧编号进入真实导出计划，不跟随当前版本指针。
    target = tmp_path / '最早修订导出计划'; target.mkdir()
    grant = post(client, '/export-grants', {'path': str(target)})
    plan = post(client, '/exports/prepare', {'project_id': work['project_id'], 'object_type': 'work', 'object_id': work['id'], 'target_dir': str(target), 'grant_id': grant['grant_id'], 'work_revision_id': oldest['items'][0]['id']})
    assert plan['can_export'] and plan['object_version_id'] == revisions[0]['id']
    assert any(item['path'] == 'revision/revised-text.txt' for item in plan['files'])
    assert service.store.get('work', work['id']) == work


def test_cursor_is_exclusive_and_remains_stable_after_new_revision(rig):
    manager, work, _ = saved_work(rig)
    original = manager.view(work['id'])
    assert original['items'] == [] and original['next_before_revision'] is None and not original['has_more']
    revisions = []
    for number in range(1, 4):
        work, revision = add_revision(manager, work, number)
        revisions.append(revision)
    first = manager.view(work['id'], limit=2)
    assert [item['id'] for item in first['items']] == [item['id'] for item in revisions[1:]]
    work, newest = add_revision(manager, work, 4)
    older = manager.view(work['id'], limit=2, before_revision=first['next_before_revision'])
    assert [item['id'] for item in older['items']] == [revisions[0]['id']]
    assert older['current_revision_id'] == newest['id'] and older['work_revision'] == newest['revision']
    assert older['original'] == original['original'] and older['next_before_revision'] is None
    empty = manager.view(work['id'], limit=1, before_revision=revisions[0]['revision'])
    assert empty['items'] == [] and not empty['has_more'] and empty['next_before_revision'] is None
    assert empty['current_revision_id'] == newest['id'] and empty['original'] == original['original']


@pytest.mark.parametrize('field,value', [
    ('limit', 0), ('limit', 101), ('limit', True), ('limit', 1.5), ('limit', '1'),
    ('before_revision', 0), ('before_revision', -1), ('before_revision', True), ('before_revision', 1.5), ('before_revision', '2'),
])
def test_service_rejects_invalid_pagination_before_reading_work(rig, field, value):
    with pytest.raises(Fault) as error:
        rig[1].work_revisions.view('missing-work', **{field: value})
    assert error.value.code == 'WORK_REVISION_INVALID' and error.value.status == 422


@pytest.mark.parametrize('field,value', [
    ('limit', '0'), ('limit', '101'), ('limit', 'invalid'), ('limit', '1.5'),
    ('before_revision', '0'), ('before_revision', '-1'), ('before_revision', 'invalid'), ('before_revision', '1.5'),
])
def test_http_rejects_invalid_pagination(rig, field, value):
    response = rig[0].get('/api/v1/works/missing-work/revisions', params={field: value})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize('damaged', ['current', 'history', 'original'])
def test_history_pages_still_verify_current_original_and_returned_files(rig, damaged):
    manager, work, _ = saved_work(rig)
    work, first = add_revision(manager, work, 1)
    work, current = add_revision(manager, work, 2)
    artifact_id = {'current': current['artifact_id'], 'history': first['artifact_id'], 'original': work['artifact_id']}[damaged]
    artifact = rig[1].store.get('artifact', artifact_id)
    path = Path(artifact['storage_path']); path.chmod(0o600); path.write_text('受控损坏')
    before = tuple(rig[1].store.db.iterdump())
    with pytest.raises(Fault):
        manager.view(work['id'], limit=1, before_revision=current['revision'])
    assert tuple(rig[1].store.db.iterdump()) == before
    assert rig[1].store.get('work', work['id']) == work
