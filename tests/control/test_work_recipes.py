"""原配方复用与收藏的临时库合同；受控产物字节不作为模型生成证据。"""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from test_control import rig, post
from test_media_flow import media_attempt
from test_work_revisions import movie, payload as revision_payload
from ailab_control.api import Draft, NvidiaRuntime
from ailab_control.assets import file_hash
from ailab_control.service import Service
from ailab_control.storage import Fault, digest


def recipe_work(rig, kind='text', *, adapter=False, remote=False):
    client, service, *_ = rig
    if kind == 'text':
        project = post(client, '/projects', {'name': '原配方临时库'})
        task = post(client, '/tasks', {'project_id': project['id'], 'name': '来源夹具', 'kind': kind, 'operation': 'generate'})
        snapshot = {'kind': kind, 'operation': 'generate', 'input': {'prompt': '原始问题'}, 'runtime': task['draft']['runtime']}
        attempt = service.resource('attempt', project['id'], task_id=task['id'], state='finalizing', state_version=1,
                                   snapshot=snapshot, snapshot_digest=digest(snapshot), compute_outcome='succeeded',
                                   collection_state='not_started', collection_version=0, last_event_sequence=0)
        primary = service.root / 'runs' / attempt['id'] / 'output' / 'result.txt'
        primary.parent.mkdir(parents=True)
        primary.write_text('原生成正文\n')
        attempt['output_manifest_ref'] = service.seal_manifest({'artifacts': [{'path': 'result.txt', 'media_type': 'text/plain', 'sha256': file_hash(primary)}]})
        with service.store.transaction():
            service.store.put('attempt', attempt)
        assert service.collect(attempt['id'])['state'] == 'succeeded'
        attempt = service.store.get('attempt', attempt['id'])
    else:
        project, attempt, _, _ = media_attempt(rig, kind, movie() if kind == 'video' else None)
    model = service.resource('model', project['id'], name='元数据模型夹具', modality=kind, version_id='model-version-original', manifest_digest='a' * 64)
    refs = {'model': model}
    recipe = attempt['snapshot']
    recipe.update(model_id=model['id'], model_version_id=model['version_id'], model_manifest_digest=model['manifest_digest'],
                  requested_config=copy.deepcopy(recipe['runtime']), effective_config={'fixture_only': True},
                  model_path='/fixture-only/model', preflight_id='fixture-preflight', environment={'fixture_only': True},
                  workflow_id='fixture-workflow', checkpoint_id='fixture-checkpoint')
    if kind == 'image':
        recipe['input'] = {'prompt': '原图片正向词', 'negative_prompt': '原图片负向词'}
    if kind == 'audio':
        recipe['input'] = {'prompt': '原配音文案'}
    if kind == 'video':
        material = service.resource('material', project['id'], name='输入图片元数据', kind='image', version_id='material-version-original', manifest_digest='b' * 64)
        refs['material'] = material
        recipe.update(input={'material_id': material['id']}, material_id=material['id'], material_version_id=material['version_id'], input_image_manifest_digest=material['manifest_digest'])
    if adapter:
        adapted = service.resource('adapter', project['id'], name='适配器元数据', version_id='adapter-version-original', manifest_digest='c' * 64,
                                   base_model_id=model['id'], base_model_version_id=model['version_id'], base_manifest_digest=model['manifest_digest'], training_recipe_digest='d' * 64)
        refs['adapter'] = adapted
        recipe.update(adapter_id=adapted['id'], adapter_version_id=adapted['version_id'], adapter_manifest_digest=adapted['manifest_digest'], adapter_training_recipe_digest=adapted['training_recipe_digest'])
    if remote:
        target = service.resource('execution-target', project['id'], name='离线元数据目标', origin='https://fixture.invalid:9443', executor_id='fixture-executor',
                                  revision=1, transport='https', validation_scope='network_remote')
        refs['execution-target'] = target
        recipe.update(execution_target_id=target['id'], execution_target=service.remote_execution.target_fields(target),
                      runtime=NvidiaRuntime().model_dump())
    attempt['snapshot_digest'] = digest(recipe)
    with service.store.transaction():
        for resource_kind, resource in refs.items():
            service.store.put(resource_kind, resource)
        service.store.put('attempt', attempt)
    public = post(client, '/works', {'attempt_id': attempt['id'], 'name': '原配方作品'}, 'save-' + attempt['id'])
    return service.store.get('work', public['id']), attempt, refs


def reuse(client, work, key='reuse-one', **extra):
    return client.post(f"/api/v1/works/{work['id']}/reuse-task", json={'project_id': work['project_id'], **extra}, headers={'Idempotency-Key': key})


def inventory(service):
    return {kind: copy.deepcopy(service.store.list(kind)) for kind in ('task', 'attempt', 'work', 'work-revision', 'artifact')}


def rewrite_recipe(service, work, attempt, change):
    change(attempt['snapshot'])
    attempt['snapshot_digest'] = digest(attempt['snapshot'])
    work['recipe'] = copy.deepcopy(attempt['snapshot'])
    with service.store.transaction():
        service.store.put('work', work)
        service.store.put('attempt', attempt)


@pytest.mark.parametrize('kind', ['text', 'image', 'audio', 'video'])
def test_four_original_recipes_create_only_normal_draft_without_compute(rig, monkeypatch, kind):
    client, service, *_ = rig
    work, attempt, _ = recipe_work(rig, kind)
    original_task = service.store.get('task', attempt['task_id'])
    original_task.update(immutable_draft=True, workflow_id='fixture-workflow', workflow_step_id='fixture-step')
    with service.store.transaction():
        service.store.put('task', original_task)
    before = inventory(service)
    original_bytes = {artifact['id']: file_hash(Path(artifact['storage_path'])) for artifact in before['artifact']}
    def forbidden(*args, **kwargs):
        pytest.fail('配方读取与复用不能进入检查、计算或默认目标新建路径')
    for name in ('new_task', 'environment', 'preflight', 'submit'):
        monkeypatch.setattr(service, name, forbidden)
    monkeypatch.setattr(service.execution_targets, 'client', forbidden)
    view = client.get(f"/api/v1/works/{work['id']}/recipe", params={'project_id': work['project_id']})
    assert view.status_code == 200, view.text
    body = view.json()
    assert body['recipe'] == work['recipe'] and body['source_attempt_id'] == attempt['id']
    assert inventory(service) == before
    created = reuse(client, work)
    assert created.status_code == 200, created.text
    task = created.json()
    assert task['draft']['input'] == work['recipe']['input'] and task['draft']['runtime'] == work['recipe']['runtime']
    assert task['draft']['model_id'] == work['recipe']['model_id'] and task['draft']['execution_target_id'] is None
    assert task['source_work_id'] == work['id'] and task['source_attempt_id'] == attempt['id']
    assert task['source_recipe_digest'] == digest(work['recipe']) and task['draft_revision'] == 1
    assert set(task['draft']) == set(Draft.model_fields)
    assert task['draft']['checkpoint_id'] is None and task['draft']['dataset_id'] is None
    assert task['kind'] == kind and task['operation'] == 'generate'
    assert not {'immutable_draft', 'workflow_id', 'preflight_id'} & set(task)
    after = inventory(service)
    assert after.pop('task') == [*before.pop('task'), task] and after == before
    assert {artifact['id']: file_hash(Path(artifact['storage_path'])) for artifact in after['artifact']} == original_bytes


@pytest.mark.parametrize('kind,content,content_kind', [
    ('text', {'text': '后来人工改写正文'}, 'text'),
    ('audio', {'text': '后来人工改写配音文案'}, 'voice_script'),
    ('video', {'cues': [{'start_ms': 0, 'end_ms': 1000, 'text': '后来人工字幕'}]}, 'subtitles'),
])
def test_manual_revision_never_replaces_original_generation_input(rig, kind, content, content_kind):
    client, service, *_ = rig
    work, attempt, _ = recipe_work(rig, kind)
    revised = service.work_revisions.create(work['id'], revision_payload(work, content, kind=content_kind), 'manual')
    before = inventory(service)
    created = reuse(client, work)
    assert created.status_code == 200, created.text
    assert created.json()['draft']['input'] == attempt['snapshot']['input']
    assert service.store.get('work', work['id'])['current_revision_id'] == revised['revision']['id']
    for resource_kind in ('attempt', 'work', 'work-revision', 'artifact'):
        assert service.store.list(resource_kind) == before[resource_kind]


def test_same_key_is_atomic_replay_even_after_draft_edits_and_source_disappears(rig):
    client, service, *_ = rig
    work, _, refs = recipe_work(rig)
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = list(pool.map(lambda _: service.work_recipes.reuse(work['id'], {'project_id': work['project_id'], 'name': None}, 'concurrent'), range(8)))
    first = tasks[0]
    assert all(task == first for task in tasks) and len(service.store.list('task')) == 2
    draft = copy.deepcopy(first['draft']); draft['input']['prompt'] = '新草稿修改'
    saved = client.patch(f"/api/v1/tasks/{first['id']}/draft", json={'expected_revision': 1, 'draft': draft})
    assert saved.status_code == 200 and saved.json()['source_recipe_digest'] == first['source_recipe_digest']
    with service.store.transaction():
        service.store.db.execute('DELETE FROM resources WHERE id=?', (refs['model']['id'],))
    assert reuse(client, work, 'concurrent').json() == first
    conflict = reuse(client, work, 'concurrent', name='另一名称')
    assert conflict.status_code == 409 and conflict.json()['error']['code'] == 'IDEMPOTENCY_CONFLICT'
    assert len(service.store.list('task')) == 2


def test_failed_atomic_commit_rolls_back_task_and_key_then_retry_creates_once(rig, monkeypatch):
    client, service, *_ = rig
    work, _, _ = recipe_work(rig)
    original = service.store.remember
    def fail_remember(*args):
        raise Fault('FIXTURE_COMMIT_FAILURE', '夹具模拟原子提交失败', 500)
    monkeypatch.setattr(service.store, 'remember', fail_remember)
    before = inventory(service)
    failed = reuse(client, work)
    assert failed.status_code == 500 and inventory(service) == before
    monkeypatch.setattr(service.store, 'remember', original)
    assert reuse(client, work).status_code == 200 and len(service.store.list('task')) == len(before['task']) + 1


def test_original_local_overrides_remote_project_default_and_remote_keeps_identity(rig):
    client, service, *_ = rig
    local, _, _ = recipe_work(rig)
    remote, _, refs = recipe_work(rig, remote=True)
    default_target = {**refs['execution-target'], 'id': 'target-local-project-default', 'project_id': local['project_id']}
    project = service.store.get('project', local['project_id'])
    project['default_execution_target_id'] = default_target['id']
    with service.store.transaction():
        service.store.put('execution-target', default_target)
        service.store.put('project', project)
    assert reuse(client, local).json()['draft']['execution_target_id'] is None
    created = reuse(client, remote)
    assert created.status_code == 200, created.text
    assert created.json()['draft']['execution_target_id'] == refs['execution-target']['id']
    assert created.json()['draft']['runtime'] == remote['recipe']['runtime']


@pytest.mark.parametrize('resource_kind', ['model', 'adapter', 'material', 'execution-target'])
@pytest.mark.parametrize('failure', ['missing', 'project', 'version', 'digest'])
def test_reference_failure_creates_zero_tasks_and_remains_viewable(rig, resource_kind, failure):
    client, service, *_ = rig
    work, _, refs = recipe_work(rig, 'video' if resource_kind == 'material' else 'text', adapter=resource_kind == 'adapter', remote=resource_kind == 'execution-target')
    resource = refs[resource_kind]
    with service.store.transaction():
        if failure == 'missing':
            service.store.db.execute('DELETE FROM resources WHERE id=?', (resource['id'],))
        else:
            field = {'project': 'project_id', 'version': 'executor_id' if resource_kind == 'execution-target' else 'version_id',
                     'digest': 'origin' if resource_kind == 'execution-target' else 'manifest_digest'}[failure]
            resource[field] = 'changed-fixture'
            service.store.put(resource_kind, resource)
    before = inventory(service)
    assert client.get(f"/api/v1/works/{work['id']}/recipe", params={'project_id': work['project_id']}).status_code == 200
    failed = reuse(client, work)
    assert failed.status_code == (403 if failure == 'project' else 409), failed.text
    assert failed.json()['error']['code'] == {'missing': 'WORK_RECIPE_REFERENCE_MISSING', 'project': 'PROJECT_MISMATCH'}.get(failure, 'WORK_RECIPE_REFERENCE_CHANGED')
    assert inventory(service) == before


@pytest.mark.parametrize('mutation', ['runtime_extra', 'runtime_type', 'input_extra', 'missing_model', 'missing_material', 'bad_material', 'adapter_base', 'adapter_training', 'model_modality'])
def test_invalid_original_projection_or_base_is_rejected_without_partial_task(rig, mutation):
    client, service, *_ = rig
    work, attempt, refs = recipe_work(rig, 'video' if mutation in {'missing_material', 'bad_material'} else 'text', adapter=mutation.startswith('adapter_'))
    def change(recipe):
        if mutation == 'runtime_extra': recipe['runtime']['unexpected'] = '封存字段'
        if mutation == 'runtime_type': recipe['runtime']['max_tokens'] = True
        if mutation == 'input_extra': recipe['input']['revision_text'] = '人工修订'
        if mutation == 'missing_model': recipe['model_id'] = None
        if mutation == 'missing_material': recipe['input']['material_id'] = None
        if mutation == 'bad_material': recipe['material_id'] = 'wrong-material'
    rewrite_recipe(service, work, attempt, change)
    if mutation == 'adapter_base':
        refs['adapter']['base_model_version_id'] = 'other-version'
        with service.store.transaction():
            service.store.put('adapter', refs['adapter'])
    if mutation == 'adapter_training':
        refs['adapter']['training_recipe_digest'] = 'changed-training-recipe'
        with service.store.transaction():
            service.store.put('adapter', refs['adapter'])
    if mutation == 'model_modality':
        refs['model']['modality'] = 'image'
        with service.store.transaction():
            service.store.put('model', refs['model'])
    before = inventory(service)
    failed = reuse(client, work)
    assert failed.status_code == 409, failed.text
    assert inventory(service) == before


def test_adapter_reuse_and_reference_outside_first_page_are_resolved_by_id(rig):
    client, service, *_ = rig
    work, _, refs = recipe_work(rig, adapter=True)
    # 移到默认第一页之外，编号定位不依赖列表缓存。
    with service.store.transaction():
        service.store.db.execute('DELETE FROM resources WHERE id=?', (refs['model']['id'],))
        for index in range(205):
            service.store.put('model', service.resource('model', work['project_id'], name=f'分页占位 {index}'))
        service.store.put('model', refs['model'])
    first_page = client.get('/api/v1/models', params={'project_id': work['project_id'], 'limit': 100}).json()
    assert refs['model']['id'] not in {item['id'] for item in first_page['items']}
    created = reuse(client, work)
    assert created.status_code == 200, created.text
    assert created.json()['draft']['adapter_id'] == refs['adapter']['id']


@pytest.mark.parametrize('damage', ['recipe', 'snapshot_digest', 'attempt_project', 'attempt_missing', 'artifact_missing', 'output_changed'])
def test_damaged_original_source_rejects_view_and_reuse(rig, damage):
    client, service, *_ = rig
    work, attempt, _ = recipe_work(rig)
    with service.store.transaction():
        if damage == 'recipe':
            work['recipe']['input']['prompt'] = '仅作品被篡改'; service.store.put('work', work)
        if damage == 'snapshot_digest':
            attempt['snapshot_digest'] = '0' * 64; service.store.put('attempt', attempt)
        if damage == 'attempt_project':
            attempt['project_id'] = 'wrong-project'; service.store.put('attempt', attempt)
        if damage == 'attempt_missing':
            work['source_attempt'] = 'missing-attempt'; service.store.put('work', work)
        if damage == 'artifact_missing':
            service.store.db.execute('DELETE FROM resources WHERE id=?', (work['artifact_id'],))
        if damage == 'output_changed':
            original = Path(service.store.get('artifact', work['artifact_id'])['storage_path'])
            original.chmod(0o600); original.write_text('篡改产物')
    before = inventory(service)
    for response in (client.get(f"/api/v1/works/{work['id']}/recipe", params={'project_id': work['project_id']}), reuse(client, work)):
        assert response.status_code in {403, 404, 409}, response.text
        assert '人工修订' not in response.json()['error']['message']
    assert inventory(service) == before


def test_project_missing_key_and_strict_payload_guards_create_nothing(rig):
    client, service, *_ = rig
    work, _, _ = recipe_work(rig)
    before = inventory(service)
    wrong = 'other-project'
    path = f"/api/v1/works/{work['id']}"
    assert client.get(path + '/recipe').status_code == 422
    assert client.get(path + '/recipe', params={'project_id': wrong}).status_code == 403
    assert reuse(client, work, project_id=wrong).status_code == 403
    assert client.patch(path + '/favorite', json={'project_id': wrong, 'favorite': True}).status_code == 403
    assert client.post(path + '/reuse-task', json={'project_id': work['project_id']}).json()['error']['code'] == 'IDEMPOTENCY_KEY_REQUIRED'
    for extra in ({'name': '  '}, {'name': 3}, {'draft': {}}, {'source_work_id': work['id']}):
        assert reuse(client, work, **extra).status_code == 422
    for value in (1, 0, 'true', 'false', None):
        assert client.patch(path + '/favorite', json={'project_id': work['project_id'], 'favorite': value}).status_code == 422
    assert client.patch(path + '/favorite', json={'project_id': work['project_id'], 'favorite': True, 'recipe': {}}).status_code == 422
    assert client.get('/api/v1/works/missing/recipe', params={'project_id': work['project_id']}).status_code == 404
    assert inventory(service) == before


def test_lineage_cannot_be_replaced_by_draft_save(rig):
    client, service, *_ = rig
    work, _, _ = recipe_work(rig)
    task = reuse(client, work).json()
    for field in ('source_work_id', 'source_attempt_id', 'source_recipe_digest'):
        payload = {'expected_revision': 1, 'draft': task['draft'], field: 'replacement'}
        assert client.patch(f"/api/v1/tasks/{task['id']}/draft", json=payload).status_code == 422
        draft = {**task['draft'], field: 'replacement'}
        assert client.patch(f"/api/v1/tasks/{task['id']}/draft", json={'expected_revision': 1, 'draft': draft}).status_code == 422
    assert service.store.get('task', task['id']) == task


def test_old_model_without_modality_and_work_without_name_use_valid_defaults(rig):
    client, service, *_ = rig
    work, _, refs = recipe_work(rig)
    del work['name']; del refs['model']['modality']
    with service.store.transaction():
        service.store.put('work', work)
        service.store.put('model', refs['model'])
    created = reuse(client, work)
    assert created.status_code == 200 and created.json()['name'] == '作品 · 配方复用'


def test_favorite_alone_preserves_newest_revision_and_old_missing_flag(rig):
    client, service, *_ = rig
    work, _, _ = recipe_work(rig)
    del work['favorite']
    with service.store.transaction():
        service.store.put('work', work)
    assert client.get(f"/api/v1/works/{work['id']}").json()['favorite'] is False
    assert service.work_recipes.view(work['id'], work['project_id'])['work']['favorite'] is False
    assert 'favorite' not in service.store.get('work', work['id'])
    revised = service.work_revisions.create(work['id'], revision_payload(work, {'text': '较新人工修订'}), 'manual-favorite')
    before = inventory(service)
    path = f"/api/v1/works/{work['id']}/favorite"
    for favorite in (True, True, False):
        result = client.patch(path, json={'project_id': work['project_id'], 'favorite': favorite})
        assert result.status_code == 200 and result.json()['favorite'] is favorite
        stored = service.store.get('work', work['id'])
        assert stored.pop('favorite') is favorite and stored == before['work'][0]
        assert result.json()['current_revision_id'] == revised['revision']['id']
    for kind in ('task', 'attempt', 'work-revision', 'artifact'):
        assert service.store.list(kind) == before[kind]


def test_reopen_retains_reused_draft_lineage_and_favorite(rig):
    client, service, *_ = rig
    work, _, _ = recipe_work(rig)
    task = reuse(client, work, name='重开后继续编辑').json()
    assert client.patch(f"/api/v1/works/{work['id']}/favorite", json={'project_id': work['project_id'], 'favorite': True}).status_code == 200
    service.close()
    reopened = Service(service.settings)
    try:
        assert reopened.store.get('task', task['id']) == task
        assert reopened.store.get('work', work['id'])['favorite'] is True
        assert reopened.work_recipes.view(work['id'], work['project_id'])['source_recipe_digest'] == task['source_recipe_digest']
        assert reopened.store.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    finally:
        reopened.close()
