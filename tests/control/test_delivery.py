"""实验适配器、来源隔离和真实本机文件导出验收。"""

import copy
import errno
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time

import pytest

from test_control import rig, post, setup_task, submit, wait_attempt
from ailab_control.assets import file_hash
from ailab_control.storage import Fault, digest, encode


def trained_fixture(rig, prompt=""):
    from dataset_split_fixtures import setup_split
    client, service, source, _ = rig
    inputs = setup_split(rig, service.test_monkeypatch)
    project, model, dataset = inputs['project'], inputs['model'], inputs['train_dataset']
    task = post(client, '/tasks', {'project_id': project['id'], 'name': '有来源组证明的训练夹具', 'kind': 'text', 'operation': 'train'})
    task['draft'].update(model_id=model['id'], input={'prompt': prompt})
    task["draft"]["dataset_id"] = dataset["id"]
    response = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": task["draft_revision"], "draft": task["draft"]})
    assert response.status_code == 200, response.text
    attempt, _ = submit(rig, response.json())
    done = wait_attempt(client, attempt["id"])
    assert done["state"] == "succeeded", done
    return project, model, done


def prepare(rig, object_type, object_id, project_id, target, **selection):
    client = rig[0]
    target.mkdir(exist_ok=True)
    grant = post(client, "/export-grants", {"path": str(target)})
    plan = post(client, "/exports/prepare", {"project_id": project_id, "object_type": object_type, "object_id": object_id, "target_dir": str(target), "grant_id": grant["grant_id"], "include_base": False, **selection})
    assert plan["can_export"], plan
    assert "source_files" not in plan
    return plan


def export(rig, plan, key="export-once"):
    client = rig[0]
    payload = {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}
    record = post(client, "/exports", payload, key)
    wait_attempt(client, record["attempt_id"])
    return client.get(f"/api/v1/exports/{record['id']}").json(), payload


def test_historical_work_export_keeps_selected_revision_in_api(rig, tmp_path):
    from test_work_revisions import saved_work, payload
    client, service, *_ = rig
    manager, work, _ = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '用户选择的第一版'}), 'revision-first')
    plan = prepare(rig, 'work', work['id'], work['project_id'], tmp_path / '固定修订导出',
                   work_revision_id=first['revision']['id'])
    record, _ = export(rig, plan)
    manager.create(work['id'], payload(first['work'], {'text': '不应替换原选择的第二版'}, first['revision']['id']), 'revision-second')
    before = service.store.get('export', record['id'])
    history = client.get(f"/api/v1/exports/{record['id']}").json()
    assert 'work_revision_id' in history, history
    assert history['work_revision_id'] == first['revision']['id']
    assert 'selection_warning' not in history
    assert service.store.get('export', record['id']) == before


def work_export_fixture(rig, tmp_path, revised=True):
    from test_work_revisions import saved_work, payload
    manager, work, attempt = saved_work(rig)
    first = manager.create(work['id'], payload(work, {'text': '固定人工第一版'}), 'first')
    revision_id = first['revision']['id'] if revised else None
    plan = prepare(rig, 'work', work['id'], work['project_id'], tmp_path / '历史版本', work_revision_id=revision_id)
    record, _ = export(rig, plan)
    manager.create(work['id'], payload(first['work'], {'text': '后来的人工第二版'}, first['revision']['id']), 'second')
    return record, plan, revision_id, work, attempt


@pytest.mark.parametrize('revised', [False, True])
@pytest.mark.parametrize('legacy_plan', [False, True])
def test_work_selection_projection_keeps_original_or_fixed_revision_without_writes(rig, tmp_path, revised, legacy_plan):
    client, service, *_ = rig
    record, plan, revision_id, work, attempt = work_export_fixture(rig, tmp_path, revised)
    if legacy_plan:
        # 旧记录没有快捷字段时，仅从仍受摘要绑定的 object.json 核实。
        stored = service.store.get('export-plan', plan['id'])
        stored.pop('work_revision_id')
        with service.store.transaction(): service.store.put('export-plan', stored)
    originals = {kind: service.store.list(kind) for kind in ('work', 'work-revision', 'export', 'export-plan', 'task', 'attempt')}
    files = {str(path): file_hash(path) for path in Path(record['verified_path']).rglob('*') if path.is_file()}
    history = client.get(f"/api/v1/exports/{record['id']}").json()
    listed = client.get(f"/api/v1/exports?project_id={work['project_id']}").json()['items'][0]
    for response in (history, listed):
        assert 'work_revision_id' in response and response['work_revision_id'] == revision_id
        assert 'selection_warning' not in response
    assert {kind: service.store.list(kind) for kind in originals} == originals
    assert {str(path): file_hash(path) for path in Path(record['verified_path']).rglob('*') if path.is_file()} == files
    assert service.store.get('attempt', attempt['id']) == attempt


def test_legacy_export_submit_replay_projects_version_without_second_export(rig, tmp_path, monkeypatch):
    client, service, *_ = rig
    project_record = service.delivery.export_record
    def old_response(record):
        response = project_record(record)
        response.pop('work_revision_id', None)
        response.pop('selection_warning', None)
        return response
    with monkeypatch.context() as patch:
        patch.setattr(service.delivery, 'export_record', old_response)
        record, plan, revision_id, _, _ = work_export_fixture(rig, tmp_path)
    assert 'work_revision_id' not in record
    before = {kind: service.store.list(kind) for kind in ('export', 'export-plan', 'task', 'attempt')}
    replayed = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'export-once')
    assert replayed['id'] == record['id'] and replayed['work_revision_id'] == revision_id
    assert 'selection_warning' not in replayed
    assert {kind: service.store.list(kind) for kind in before} == before


@pytest.mark.parametrize('fails', [False, True])
def test_export_submit_replay_returns_current_terminal_record_without_changing_ledger(rig, tmp_path, fails):
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '终态响应重放')
    if fails:
        source = Path(service.store.get('model', model['id'])['storage_path']) / 'config.json'
        source.chmod(0o600)
        source.write_text('{}')
    current, command = export(rig, plan)
    assert current['state'] == ('failed' if fails else 'succeeded')
    assert current['error'] if fails else current['verified_path']
    original_response = service.store.replay('export', 'export-once', command)
    assert original_response['state'] == 'queued' and original_response['verified_path'] is None and original_response['error'] is None
    before = {kind: service.store.list(kind) for kind in ('export', 'export-plan', 'task', 'attempt')}
    replayed = post(client, '/exports', command, 'export-once')
    assert {kind: service.store.list(kind) for kind in before} == before
    assert service.store.replay('export', 'export-once', command) == original_response
    assert replayed == current


@pytest.mark.parametrize('damage', [
    'missing_plan', 'plan_digest', 'record_digest', 'plan_project', 'plan_object', 'plan_type',
    'plan_selection', 'plan_version', 'missing_object', 'duplicate_object', 'duplicate_source',
    'missing_contents', 'contents_changed', 'source_size', 'source_digest', 'missing_selected_version',
    'missing_revision_id', 'metadata_object', 'revision_id', 'revision_work', 'revision_project',
    'revision_source', 'revision_artifact', 'unknown_type', 'duplicate_json_key', 'false_original',
])
def test_work_export_unknown_selection_never_defaults_or_rewrites_history(rig, tmp_path, damage):
    client, service, *_ = rig
    exported, public_plan, _, _, _ = work_export_fixture(rig, tmp_path)
    record = service.store.get('export', exported['id'])
    plan = service.store.get('export-plan', public_plan['id'])
    source = next(entry for entry in plan['source_files'] if entry['path'] == 'object.json')
    metadata = json.loads(source['contents'])
    reseal = False
    if damage == 'missing_plan': record['plan_id'] = 'export-plan-unavailable'
    elif damage == 'plan_digest': plan['plan_digest'] = '0' * 64
    elif damage == 'record_digest': record['plan_digest'] = '0' * 64
    elif damage in ('plan_project', 'plan_object', 'plan_type'):
        plan[{'plan_project': 'project_id', 'plan_object': 'object_id', 'plan_type': 'object_type'}[damage]] = 'wrong-link'
        reseal = True
    elif damage == 'plan_selection': plan['work_revision_id'] = None
    elif damage == 'plan_version': plan['object_version_id'] = 'wrong-version'; reseal = True
    elif damage == 'missing_object': plan['files'] = [entry for entry in plan['files'] if entry['path'] != 'object.json']; reseal = True
    elif damage == 'duplicate_object': plan['files'].append(copy.deepcopy(next(entry for entry in plan['files'] if entry['path'] == 'object.json'))); reseal = True
    elif damage == 'duplicate_source': plan['source_files'].append(copy.deepcopy(source))
    elif damage == 'missing_contents': source.pop('contents')
    elif damage == 'contents_changed': source['contents'] += ' '
    elif damage == 'source_size': source['size'] += 1
    elif damage == 'source_digest': source['sha256'] = '0' * 64
    else:
        if damage == 'missing_selected_version': metadata.pop('selected_version')
        elif damage == 'missing_revision_id': metadata['selected_version'].pop('revision_id')
        elif damage == 'metadata_object': metadata['id'] = 'wrong-work'
        elif damage == 'revision_id': metadata['revision']['id'] = 'wrong-revision'
        elif damage == 'revision_work': metadata['revision']['work_id'] = 'wrong-work'
        elif damage == 'revision_project': metadata['revision']['project_id'] = 'wrong-project'
        elif damage == 'revision_source': metadata['revision']['source_attempt_id'] = 'wrong-attempt'
        elif damage == 'revision_artifact': metadata['revision']['source_artifact_id'] = 'wrong-artifact'
        elif damage == 'unknown_type': metadata['selected_version']['type'] = 'latest'
        elif damage == 'false_original': metadata['selected_version']['type'] = 'original'
        source['contents'] = encode(metadata) + '\n'
        if damage == 'duplicate_json_key': source['contents'] = source['contents'].replace('{', '{"id":"ambiguous",', 1)
        source.update(size=len(source['contents'].encode()), sha256=hashlib.sha256(source['contents'].encode()).hexdigest())
        entry = next(entry for entry in plan['files'] if entry['path'] == 'object.json')
        entry.update(size=source['size'], sha256=source['sha256'])
        reseal = True
    if reseal:
        fields = ('project_id', 'object_type', 'object_id', 'object_version_id', 'target_dir', 'include_base', 'files', 'dependencies')
        plan['plan_digest'] = record['plan_digest'] = digest({name: plan[name] for name in fields})
    # 即使旧记录残留一个快捷字段，也不能越过冻结证据的未知结论。
    record['work_revision_id'] = None
    with service.store.transaction():
        service.store.put('export-plan', plan)
        service.store.put('export', record)
    before = {kind: service.store.list(kind) for kind in ('export', 'export-plan', 'work', 'work-revision')}
    response = client.get(f"/api/v1/exports/{record['id']}")
    assert response.status_code == 200, response.text
    assert 'work_revision_id' not in response.json()
    assert response.json()['selection_warning'] == '无法核实这条历史导出选择的作品版本，请返回作品重新选择后导出。'
    assert {kind: service.store.list(kind) for kind in before} == before


def test_adapter_saved_as_experimental_and_bound_to_base(rig):
    client, service, _, _ = rig
    project, model, trained = trained_fixture(rig)
    adapter = post(client, f"/attempts/{trained['id']}/adapters", {"name": "实验适配器"}, "save-adapter")
    assert adapter["status"] == "experimental" and adapter["quality_status"] == "not_evaluated"
    assert adapter["base_model_id"] == model["id"]
    assert adapter["base_manifest_digest"] == model["manifest_digest"]
    assert adapter["training_recipe_digest"] == trained["snapshot"]["tokenization_recipe_digest"]
    assert adapter == post(client, f"/attempts/{trained['id']}/adapters", {"name": "实验适配器"}, "save-adapter")
    assert len(client.get(f"/api/v1/adapters?project_id={project['id']}").json()["items"]) == 1
    assert len(client.get(f"/api/v1/models?project_id={project['id']}").json()["items"]) == 1
    assert client.post(f"/api/v1/candidates/{adapter['id']}/register", json={}).status_code == 409
    task = post(client, "/tasks", {"project_id": project["id"], "kind": "text", "operation": "generate", "name": "显式试用适配器"})
    task["draft"].update(model_id=model["id"], adapter_id=adapter["id"], input={"prompt": "试用"})
    saved = client.patch(f"/api/v1/tasks/{task['id']}/draft", json={"expected_revision": 1, "draft": task["draft"]}).json()
    checked = post(client, f"/tasks/{task['id']}/preflight", {"draft_revision": saved["draft_revision"]})
    assert checked["can_submit"]
    assert checked["warnings"][0]["code"] == "EXPERIMENTAL_ADAPTER"
    run, _ = submit(rig, saved, "adapter-trial")
    complete = wait_attempt(client, run["id"])
    assert complete["state"] == "succeeded"
    assert complete["snapshot"]["adapter_manifest_digest"] == adapter["manifest_digest"]
    assert complete["snapshot"]["adapter_training_recipe_digest"] == adapter["training_recipe_digest"]


def test_adapter_wrong_base_and_changed_provenance_are_rejected(rig):
    client, service, _, _ = rig
    project, model, trained = trained_fixture(rig, "__bad_adapter_origin__")
    response = client.post(f"/api/v1/attempts/{trained['id']}/adapters", json={}, headers={"Idempotency-Key": "bad-origin"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ADAPTER_PROVENANCE_MISMATCH"


@pytest.mark.parametrize("object_type", ["model", "adapter", "work", "report"])
def test_four_export_objects_integrity_portability_and_idempotency(rig, tmp_path, object_type):
    client, service, _, _ = rig
    project, model, trained = trained_fixture(rig)
    if object_type == "model":
        object_id = model["id"]
    elif object_type == "adapter":
        object_id = post(client, f"/attempts/{trained['id']}/adapters", {}, "adapter")["id"]
    elif object_type == "work":
        generated_task = post(client, "/tasks", {"project_id": project["id"], "name": "生成文字作品", "kind": "text", "operation": "generate"})
        generated_task["draft"].update(model_id=model["id"], input={"prompt": "生成作品正文"})
        saved = client.patch(f"/api/v1/tasks/{generated_task['id']}/draft", json={"expected_revision": 1, "draft": generated_task["draft"]}).json()
        generated = wait_attempt(client, submit(rig, saved, "work-generate")[0]["id"])
        object_id = post(client, "/works", {"attempt_id": generated["id"], "name": "文字作品"}, "work")["id"]
    else:
        object_id = trained["id"]
    plan = prepare(rig, object_type, object_id, project["id"], tmp_path / "明确写授权的导出目录")
    record, payload = export(rig, plan)
    assert record["state"] == "succeeded", record
    assert (record["object_type"], record["object_id"]) == (object_type, object_id)
    assert record["independent_use"] == "not_verified"
    assert post(client, "/exports", payload, "export-once")["id"] == record["id"]
    assert len(client.get(f"/api/v1/exports?project_id={project['id']}").json()["items"]) == 1
    directory = Path(record["verified_path"])
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["complete"] and manifest["plan_digest"] == plan["plan_digest"]
    assert str(service.root) not in json.dumps(manifest)
    for entry in manifest["files"]:
        output = directory / entry["path"]
        assert file_hash(output) == entry["sha256"] and output.stat().st_size == entry["size"]
    if object_type == "adapter":
        assert plan["dependencies"][0]["included"] is False
        assert not (directory / "base_model").exists()
    if (directory / "recipe.json").exists():
        assert str(service.root) not in (directory / "recipe.json").read_text()
    task = client.get(f"/api/v1/tasks/{record['task_id']}").json()
    assert task["kind"] == task["operation"] == "export" and task["export_id"] == record["id"]
    assert client.post(f"/api/v1/tasks/{task['id']}/preflight", json={"draft_revision": 1}).status_code == 409


def test_read_grant_does_not_authorize_export_and_wrong_project_fails(rig, tmp_path):
    client, service, source, _ = rig
    project, model, _ = setup_task(rig)
    target = tmp_path / "未写授权目录"
    target.mkdir()
    read_grant = post(client, "/import-grants", {"path": str(target)})
    body = {"project_id": project["id"], "object_type": "model", "object_id": model["id"], "target_dir": str(target), "grant_id": read_grant["grant_id"]}
    assert client.post("/api/v1/exports/prepare", json=body).status_code == 403
    write_grant = post(client, "/export-grants", {"path": str(target)})
    other = post(client, "/projects", {"name": "另一个项目"})
    body.update(project_id=other["id"], grant_id=write_grant["grant_id"])
    assert client.post("/api/v1/exports/prepare", json=body).status_code == 403
    assert not list(target.iterdir())


def test_export_detects_source_change_after_plan(rig, tmp_path):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "导出")
    internal = service.store.get("model", model["id"])
    source = Path(internal["storage_path"]) / "config.json"
    source.chmod(0o600)
    source.write_text("{}")
    record, _ = export(rig, plan)
    assert record["state"] == "failed" and record["verified_path"] is None
    assert record["error"]["code"] == "EXPORT_SOURCE_CHANGED"
    assert not list((tmp_path / "导出").glob("ailab-*"))


def test_export_disk_full_blocks_plan(rig, tmp_path, monkeypatch):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    target = tmp_path / "空间不足目录"
    target.mkdir()
    grant = post(client, "/export-grants", {"path": str(target)})
    import ailab_control.delivery as delivery
    usage = delivery.shutil.disk_usage(target)
    monkeypatch.setattr(delivery.shutil, "disk_usage", lambda _: usage._replace(free=0))
    plan = post(client, "/exports/prepare", {"project_id": project["id"], "object_type": "model", "object_id": model["id"], "target_dir": str(target), "grant_id": grant["grant_id"]})
    assert not plan["can_export"] and plan["blocking"][0]["code"] == "DISK_FULL"
    assert client.post("/api/v1/exports", json={"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, headers={"Idempotency-Key": "no-space"}).status_code == 409


def test_cancel_before_publication_never_publishes_complete_package(rig, tmp_path, monkeypatch):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "取消导出")
    entered, release = threading.Event(), threading.Event()
    verify = service.delivery.verify_export

    def before_publish(*args):
        result = verify(*args)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(service.delivery, "verify_export", before_publish)
    record = post(client, "/exports", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "cancel-export")
    assert entered.wait(3)
    attempt = client.get(f"/api/v1/attempts/{record['attempt_id']}").json()
    requested = post(client, f"/attempts/{attempt['id']}/cancel", {"expected_state_version": attempt["state_version"]}, "stop-export")
    assert requested["state"] == "cancelling" and requested["stop_status"] == "pending"
    release.set()
    done = wait_attempt(client, attempt["id"])
    assert done["state"] == "cancelled" and done["stop_status"] == "confirmed"
    final = client.get(f"/api/v1/exports/{record['id']}").json()
    assert final["verified_path"] is None
    assert not list((tmp_path / "取消导出").glob("ailab-*"))


def test_export_registration_failure_recovers_existing_package_without_copy(rig, tmp_path, monkeypatch):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "登记失败")
    original = service.store.put
    injected = False

    def fail_once(kind, value):
        nonlocal injected
        if kind == "export" and value.get("verified_path") and not injected:
            injected = True
            raise OSError("本测试注入登记失败")
        return original(kind, value)

    monkeypatch.setattr(service.store, "put", fail_once)
    record = post(client, "/exports", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "register-failure")
    pending = wait_attempt(client, record["attempt_id"], lambda item: bool(item.get("recovery_required")))
    existing = list((tmp_path / "登记失败").glob("ailab-*"))
    assert len(existing) == 1 and pending["state"] not in {"failed", "succeeded", "cancelled"}
    checksums = {str(path): file_hash(path) for path in existing[0].rglob("*") if path.is_file()}
    counts = {kind: len(service.store.list(kind)) for kind in ('export', 'task', 'attempt')}
    current = client.get(f"/api/v1/exports/{record['id']}").json()
    assert current['allowed_actions'] == ['reconcile']
    assert current['error'] == {'code': 'EXPORT_REGISTRATION_PENDING',
                                'message': '导出结果尚未确认，请核实原导出；不会重新运行模型。'}
    rejected = client.post(f"/api/v1/attempts/{pending['id']}/reconcile", json={'expected_state_version': pending['state_version'] - 1}, headers={'Idempotency-Key': 'stale-recovery'})
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'REVISION_CONFLICT'
    assert service.store.get('attempt', pending['id'])['state_version'] == pending['state_version']
    def no_new_export(*args): raise AssertionError('核实既存包不能重新导出或启动线程')
    start = threading.Thread.start
    def no_export_thread(thread):
        if thread.name.startswith('export-'): no_new_export()
        return start(thread)
    monkeypatch.setattr(service.delivery, 'run_export', no_new_export)
    monkeypatch.setattr(threading.Thread, 'start', no_export_thread)
    command = {"expected_state_version": pending["state_version"]}
    recovered = post(client, f"/attempts/{pending['id']}/reconcile", command, "recover-published")
    assert recovered["state"] == "succeeded"
    assert recovered == post(client, f"/attempts/{pending['id']}/reconcile", command, "recover-published")
    assert {str(path): file_hash(path) for path in existing[0].rglob("*") if path.is_file()} == checksums
    assert {kind: len(service.store.list(kind)) for kind in counts} == counts
    result = client.get(f"/api/v1/exports/{record['id']}").json()
    assert result['id'] == record['id'] and result['verified_path'] == str(existing[0]) and result['allowed_actions'] == []


def test_sqlite_registration_failure_recovers_published_package_without_new_execution(rig, tmp_path, monkeypatch):
    """通过独立连接注入真实 SQLite 写失败；不替换导出器或登记方法。"""
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    target_plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '登记事务失败')
    other_plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '不受影响的导出')
    plan_id = target_plan['id']
    assert plan_id.startswith('export-plan-') and len(plan_id.removeprefix('export-plan-')) == 32
    assert all(c in '0123456789abcdef' for c in plan_id.removeprefix('export-plan-'))
    trigger = 'acceptance_export_registration_failure'
    # Store.put 使用 INSERT ... ON CONFLICT；首次发布后的非空路径才被拒绝。
    # 回滚后 catch 分支登记空路径，因而可正常显示“待核实”。
    statement = f"""CREATE TRIGGER {trigger} BEFORE INSERT ON resources
        WHEN NEW.kind = 'export'
        AND json_extract(NEW.body, '$.plan_id') = '{plan_id}'
        AND json_extract(NEW.body, '$.verified_path') IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'AILAB_ACCEPTANCE_REGISTRATION_FAILURE'); END"""
    connection = sqlite3.connect(service.store.path)
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()

    def reject_process(*args, **kwargs):
        raise AssertionError('导出及核实不能启动模型或其它子进程')

    monkeypatch.setattr('subprocess.Popen', reject_process)
    try:
        # 触发器仍存在时，另一个计划可完成，不能扩大为整库写入失败。
        other, _ = export(rig, other_plan, 'sqlite-other-plan')
        assert other['state'] == 'succeeded'
        record = post(client, '/exports', {'plan_id': plan_id, 'plan_digest': target_plan['plan_digest']}, 'sqlite-target-plan')
        pending = wait_attempt(client, record['attempt_id'], lambda item: bool(item.get('recovery_required')))
        current = client.get(f"/api/v1/exports/{record['id']}").json()
        assert pending['state'] not in {'succeeded', 'failed', 'cancelled'}
        assert current['allowed_actions'] == ['reconcile'] and current['verified_path'] is None
        assert current['error']['code'] == 'EXPORT_REGISTRATION_PENDING'
        stored = service.store.get('export', record['id'])
        final = Path(stored['final_path'])
        assert final.is_dir() and not Path(stored['partial_path']).exists()
        plan = service.store.get('export-plan', plan_id)
        service.delivery.verify_export(final, stored, plan)
        files_before = {str(p.relative_to(final)): file_hash(p) for p in final.rglob('*') if p.is_file()}
        counts = {kind: len(service.store.list(kind)) for kind in ('export', 'export-plan', 'task', 'attempt')}
    finally:
        connection = sqlite3.connect(service.store.path)
        try:
            connection.execute(f'DROP TRIGGER {trigger}')
            connection.commit()
            assert connection.execute('SELECT name FROM sqlite_master WHERE type=? AND name=?', ('trigger', trigger)).fetchall() == []
        finally:
            connection.close()

    def reject_copy(*args, **kwargs):
        raise AssertionError('核实完整包不能新建导出线程或重新复制')

    monkeypatch.setattr(service.delivery, 'run_export', reject_copy)
    command = {'expected_state_version': pending['state_version']}
    recovered = post(client, f"/attempts/{record['attempt_id']}/reconcile", command, 'sqlite-recover-original')
    assert recovered == post(client, f"/attempts/{record['attempt_id']}/reconcile", command, 'sqlite-recover-original')
    assert recovered['id'] == record['attempt_id'] and recovered['state'] == 'succeeded'
    assert recovered['terminal_reason'] == 'EXPORT_RECOVERED' and recovered['recovery_required'] is False
    result = client.get(f"/api/v1/exports/{record['id']}").json()
    assert result['id'] == record['id'] and result['task_id'] == record['task_id']
    assert result['verified_path'] == str(final) and result['allowed_actions'] == [] and result['error'] is None
    assert {kind: len(service.store.list(kind)) for kind in counts} == counts
    assert {str(p.relative_to(final)): file_hash(p) for p in final.rglob('*') if p.is_file()} == files_before
    assert len(service.store.list('attempt')) == 2
    assert all(a['executor_type'] == 'export' for a in service.store.list('attempt'))


def test_empty_final_collision_stays_unconfirmed_and_reconcile_preserves_files(rig, tmp_path, monkeypatch):
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    target = tmp_path / '空目录碰撞'
    plan = prepare(rig, 'model', model['id'], project['id'], target)
    verify = service.delivery.verify_export
    injected = False

    def collide_after_partial_verified(directory, record, frozen_plan):
        nonlocal injected
        manifest = verify(directory, record, frozen_plan)
        if directory == Path(record['partial_path']) and not injected:
            # 复制和校验已完成，发布前只创建一个空目录，确定性复现原生碰撞。
            Path(record['final_path']).mkdir()
            injected = True
        return manifest

    monkeypatch.setattr(service.delivery, 'verify_export', collide_after_partial_verified)
    record = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'empty-final-collision')
    pending = wait_attempt(client, record['attempt_id'], lambda item: bool(item.get('recovery_required')))
    stored = service.store.get('export', record['id'])
    final, partial = Path(stored['final_path']), Path(stored['partial_path'])
    assert injected and final.is_dir() and list(final.iterdir()) == []
    verify(partial, stored, service.store.get('export-plan', plan['id']))
    current = client.get(f"/api/v1/exports/{record['id']}").json()
    assert current['verified_path'] is None and current['allowed_actions'] == ['reconcile']
    assert current['error'] == {'code': 'EXPORT_REGISTRATION_PENDING',
                                'message': '导出结果尚未确认，请核实原导出；不会重新运行模型。'}

    def tree_identity():
        result = {}
        for path in [target, *target.rglob('*')]:
            info = path.lstat()
            result[str(path)] = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                                 info.st_mtime_ns, info.st_ctime_ns, file_hash(path) if path.is_file() else None)
        return result

    before = tree_identity()
    counts = {kind: len(service.store.list(kind)) for kind in ('export', 'export-plan', 'task', 'attempt', 'artifact')}
    def no_new_export(*args): raise AssertionError('核实碰撞目录不能重新复制或启动导出线程')
    start = threading.Thread.start
    def no_export_thread(thread):
        if thread.name.startswith('export-'): no_new_export()
        return start(thread)
    monkeypatch.setattr(service.delivery, 'run_export', no_new_export)
    monkeypatch.setattr(threading.Thread, 'start', no_export_thread)
    command = {'expected_state_version': pending['state_version']}
    result = post(client, f"/attempts/{pending['id']}/reconcile", command, 'reconcile-empty-final')
    assert result['id'] == pending['id'] and result['state'] == 'failed' and result['terminal_reason'] == 'EXPORT_INTERRUPTED'
    assert result == post(client, f"/attempts/{pending['id']}/reconcile", command, 'reconcile-empty-final')
    result_export = client.get(f"/api/v1/exports/{record['id']}").json()
    assert result_export['id'] == record['id'] and result_export['verified_path'] is None
    assert result_export['error']['code'] == 'EXPORT_INTERRUPTED' and result_export['allowed_actions'] == []
    assert tree_identity() == before
    assert {kind: len(service.store.list(kind)) for kind in counts} == counts


@pytest.mark.parametrize('partial', [False, True])
def test_export_reconcile_without_complete_package_fails_without_recopy(rig, tmp_path, monkeypatch, partial):
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '未完成导出')
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, 'start', lambda _: None)
        record = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'unstarted-export')
    service.threads.clear()
    stored = service.store.get('export', record['id'])
    if partial:
        directory = Path(stored['partial_path'])
        directory.mkdir()
        (directory / 'unfinished.txt').write_text('只写入了部分内容')
    target = Path(stored['target_dir'])
    files = {str(path): file_hash(path) for path in target.rglob('*') if path.is_file()}
    counts = {kind: len(service.store.list(kind)) for kind in ('export', 'task', 'attempt')}
    current = client.get(f"/api/v1/exports/{record['id']}").json()
    assert current['allowed_actions'] == ['reconcile']
    def no_new_export(*args): raise AssertionError('核实未完成包不能重新导出或启动线程')
    start = threading.Thread.start
    def no_export_thread(thread):
        if thread.name.startswith('export-'): no_new_export()
        return start(thread)
    monkeypatch.setattr(service.delivery, 'run_export', no_new_export)
    monkeypatch.setattr(threading.Thread, 'start', no_export_thread)
    command = {'expected_state_version': current['state_version']}
    result = post(client, f"/attempts/{record['attempt_id']}/reconcile", command, 'reconcile-unstarted')
    assert result['state'] == 'failed' and result['terminal_reason'] == 'EXPORT_INTERRUPTED'
    assert result == post(client, f"/attempts/{record['attempt_id']}/reconcile", command, 'reconcile-unstarted')
    final = client.get(f"/api/v1/exports/{record['id']}").json()
    assert final['verified_path'] is None and final['error']['code'] == 'EXPORT_INTERRUPTED'
    assert {kind: len(service.store.list(kind)) for kind in counts} == counts
    assert {str(path): file_hash(path) for path in target.rglob('*') if path.is_file()} == files
    assert not Path(stored['final_path']).exists()


def test_export_missing_source_after_plan_keeps_original_and_never_publishes(rig, tmp_path):
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "缺文件")
    internal = service.store.get("model", model["id"])
    target = Path(internal["storage_path"]) / "config.json"
    target.rename(target.with_suffix(".preserved"))
    record, _ = export(rig, plan)
    assert record["state"] == "failed" and record["verified_path"] is None
    assert target.with_suffix(".preserved").is_file()
    assert not list((tmp_path / "缺文件").glob("ailab-*"))


@pytest.mark.parametrize('stage', ['write', 'flush', 'fsync'])
@pytest.mark.parametrize('error_number', [errno.ENOSPC, errno.EIO])
def test_export_write_failure_keeps_partial_unpublished(rig, tmp_path, monkeypatch, stage, error_number):
    from ailab_control.service import Service
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    target = tmp_path / "写入失败"
    plan = prepare(rig, "model", model["id"], project["id"], target)
    original_open, original_fsync = Path.open, os.fsync
    source = Path(service.store.get('model', model['id'])['storage_path'])
    source_files = {p.name: p.read_bytes() for p in source.iterdir()}
    failed_descriptors = set()
    injected = []

    def fail():
        injected.append(stage)
        raise OSError(error_number, "本测试注入存储写入失败")

    class InterruptedFile:
        def __init__(self, stream):
            self.stream = stream
            failed_descriptors.add(stream.fileno())
        def __enter__(self): return self
        def __exit__(self, *args):
            failed_descriptors.discard(self.stream.fileno())
            return self.stream.__exit__(*args)
        def write(self, block):
            if stage == 'write':
                # 先实际落下部分内容，才能证明失败后没有把部分包当完整包。
                self.stream.write(block[:max(1, len(block) // 2)])
                self.stream.flush()
                fail()
            return self.stream.write(block)
        def flush(self):
            self.stream.flush()
            if stage == 'flush': fail()
        def fileno(self): return self.stream.fileno()

    def fail_write(path, mode="r", *args, **kwargs):
        if mode == "xb" and path.name == "config.json" and any(part.endswith(".partial") for part in path.parts):
            return InterruptedFile(original_open(path, mode, *args, **kwargs))
        return original_open(path, mode, *args, **kwargs)

    def fail_sync(descriptor):
        if stage == 'fsync' and descriptor in failed_descriptors: fail()
        return original_fsync(descriptor)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fail_write)
        patch.setattr(os, 'fsync', fail_sync)
        record, _ = export(rig, plan)
    assert injected == [stage]
    assert record["state"] == "failed" and record["verified_path"] is None
    assert record["error"]["code"] == "EXPORT_INCOMPLETE"
    stored = service.store.get('export', record['id'])
    partial, final = Path(stored['partial_path']), Path(stored['final_path'])
    partial_files = {str(p.relative_to(partial)): p.read_bytes() for p in partial.rglob('*') if p.is_file()}
    assert set(partial_files) == {'model/config.json'}
    contents = partial_files['model/config.json']
    assert contents and source_files['config.json'].startswith(contents)
    assert (len(contents) < len(source_files['config.json'])) == (stage == 'write')
    assert not final.exists() and not (partial / 'manifest.json').exists()
    old_attempt = service.store.get('attempt', record['attempt_id'])

    # 用户重新检查后创建新导出；旧失败及部分文件保持，既有资产不修改。
    recovered_plan = prepare(rig, 'model', model['id'], project['id'], target)
    recovered, _ = export(rig, recovered_plan, 'export-after-storage-recovery')
    assert recovered['state'] == 'succeeded' and recovered['id'] != record['id']
    output = Path(recovered['verified_path'])
    manifest = json.loads((output / 'manifest.json').read_text())
    assert manifest['complete'] is True
    for entry in manifest['files']:
        assert (output / entry['path']).stat().st_size == entry['size']
        assert file_hash(output / entry['path']) == entry['sha256']
    assert {p.name: p.read_bytes() for p in source.iterdir()} == source_files
    assert {str(p.relative_to(partial)): p.read_bytes() for p in partial.rglob('*') if p.is_file()} == partial_files
    assert service.store.get('export', record['id']) == stored
    assert service.store.get('attempt', record['attempt_id']) == old_attempt
    service.close()
    reopened = Service(service.settings)
    try:
        assert reopened.store.get('export', record['id']) == stored
        assert reopened.store.get('attempt', record['attempt_id']) == old_attempt
        assert reopened.delivery.export_record(reopened.store.get('export', recovered['id']))['state'] == 'succeeded'
        attempts = reopened.store.list('attempt')
        assert len(attempts) == 2 and all(item['executor_type'] == 'export' for item in attempts)
    finally:
        reopened.close()


def test_export_interruption_reconciles_without_copy_or_model_execution(rig, tmp_path, monkeypatch):
    from ailab_control.service import Service
    client, service, _, _ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, "model", model["id"], project["id"], tmp_path / "中断")
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", lambda _: None)
        record = post(client, "/exports", {"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "interrupted")
    # 模拟未启动复制前中断，只留数据库意图；不复用夹具进程作计算证据。
    service.threads.clear()
    service.close()
    reopened = Service(service.settings)
    try:
        attempt = reopened.store.get("attempt", record["attempt_id"])
        assert attempt["recovery_required"] and attempt["stop_status"] == "unknown"
        recovered = reopened.reconcile(attempt["id"], {"expected_state_version": attempt["state_version"]}, "reconcile-export")
        assert recovered["state"] == "failed" and recovered["terminal_reason"] == "EXPORT_INTERRUPTED"
        assert len(reopened.store.list("attempt")) == 1
        assert not list((tmp_path / "中断").iterdir())
    finally:
        reopened.close()


@pytest.mark.parametrize('field,value', [
    (None, None),
    ('schema_version', 'unknown'),
    ('object_type', 'adapter'),
    ('object_id', 'model-other'),
    ('object_version_id', 'version-other'),
    ('object_version_id', None),
    ('complete', 'false'),
    ('complete', 1),
    ('complete', float('nan')),
    ('independent_use', 'verified'),
    ('extra_verification', 'verified'),
])
def test_restarted_export_checks_manifest_identity_without_recopy(rig, tmp_path, monkeypatch, field, value):
    """登记中断后的真实文件包仍须绑定原物件与版本；文件摘要正确不能代替清单身份。"""
    from ailab_control.service import Service
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '清单身份核实')
    original_put = service.store.put
    failed_once = False

    def fail_registration(kind, record):
        nonlocal failed_once
        if kind == 'export' and record.get('verified_path') and not failed_once:
            failed_once = True
            raise OSError('只注入一次发布后登记中断')
        return original_put(kind, record)

    def reject_execution(*args, **kwargs):
        raise AssertionError('清单核实不得重新导出、复制或运行模型')

    monkeypatch.setattr('subprocess.Popen', reject_execution)
    monkeypatch.setattr(service.store, 'put', fail_registration)
    record = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'identity-export')
    wait_attempt(client, record['attempt_id'], lambda item: bool(item.get('recovery_required')))
    directory = Path(service.store.get('export', record['id'])['final_path'])
    service.close()
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if field is not None:
        if value is None:
            manifest.pop(field)
        else:
            manifest[field] = value
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + '\n')
    files = {str(p.relative_to(directory)): file_hash(p) for p in directory.rglob('*') if p.is_file()}

    reopened = Service(service.settings)
    try:
        monkeypatch.setattr(reopened.delivery, 'run_export', reject_execution)
        counts = {kind: len(reopened.store.list(kind)) for kind in ('export', 'task', 'attempt')}
        attempt = reopened.store.get('attempt', record['attempt_id'])
        assert attempt['recovery_required']
        result = reopened.reconcile(attempt['id'], {'expected_state_version': attempt['state_version']}, 'identity-reconcile')
        current = reopened.delivery.export_record(reopened.store.get('export', record['id']))
        if field is None:
            assert result['state'] == 'succeeded' and result['terminal_reason'] == 'EXPORT_RECOVERED'
            assert current['verified_path'] == str(directory) and current['error'] is None
        else:
            assert result['state'] == 'failed' and result['terminal_reason'] == 'EXPORT_INTERRUPTED'
            assert current['verified_path'] is None and current['error']['code'] == 'EXPORT_INTERRUPTED'
        assert {kind: len(reopened.store.list(kind)) for kind in counts} == counts
        assert {str(p.relative_to(directory)): file_hash(p) for p in directory.rglob('*') if p.is_file()} == files
    finally:
        reopened.close()


@pytest.mark.parametrize('entry_kind', [
    'unchanged', 'ordinary_directory', 'manifest_symlink', 'payload_symlink',
    'dangling_symlink', 'directory_symlink', 'fifo',
])
def test_restarted_export_rejects_nonregular_tree_entries(rig, tmp_path, monkeypatch, entry_kind):
    """真实停机重开后，拒绝清单链接与被文件集合检查漏掉的特殊目录项。"""
    import os
    import stat
    from ailab_control.service import Service
    client, service, *_ = rig
    project, model, _ = setup_task(rig)
    plan = prepare(rig, 'model', model['id'], project['id'], tmp_path / '目录项恢复')
    original_put = service.store.put
    failed_once = False

    def fail_registration(kind, record):
        nonlocal failed_once
        if kind == 'export' and record.get('verified_path') and not failed_once:
            failed_once = True
            raise OSError('测试发布后的登记中断')
        return original_put(kind, record)

    def reject_execution(*args, **kwargs):
        raise AssertionError('核实目录项不得重新复制或执行模型')

    monkeypatch.setattr('subprocess.Popen', reject_execution)
    monkeypatch.setattr(service.store, 'put', fail_registration)
    record = post(client, '/exports', {'plan_id': plan['id'], 'plan_digest': plan['plan_digest']}, 'tree-export')
    wait_attempt(client, record['attempt_id'], lambda item: bool(item.get('recovery_required')))
    directory = Path(service.store.get('export', record['id'])['final_path'])
    service.close()
    outside = tmp_path / '包外夹具'
    outside.mkdir()
    if entry_kind in {'manifest_symlink', 'payload_symlink'}:
        path = directory / ('manifest.json' if entry_kind == 'manifest_symlink' else plan['files'][0]['path'])
        external = outside / '相同内容'
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
    elif entry_kind == 'dangling_symlink':
        (directory / '额外链接').symlink_to(outside / '不存在')
    elif entry_kind == 'directory_symlink':
        (outside / '未声明内容.txt').write_text('此内容不得混入完整导出包')
        (directory / '额外目录链接').symlink_to(outside, target_is_directory=True)
    elif entry_kind == 'fifo':
        os.mkfifo(directory / '额外管道')
    elif entry_kind == 'ordinary_directory':
        (directory / '普通空目录').mkdir()

    def tree():
        result = {}
        for root in (directory, outside):
            for path in root.rglob('*'):
                mode = path.lstat().st_mode
                contents = os.readlink(path) if stat.S_ISLNK(mode) else file_hash(path) if stat.S_ISREG(mode) else None
                result[str(path)] = (stat.S_IFMT(mode), contents)
        return result

    before = tree()
    reopened = Service(service.settings)
    try:
        monkeypatch.setattr(reopened.delivery, 'run_export', reject_execution)
        counts = {kind: len(reopened.store.list(kind)) for kind in ('export', 'task', 'attempt')}
        attempt = reopened.store.get('attempt', record['attempt_id'])
        command = {'expected_state_version': attempt['state_version']}
        result = reopened.reconcile(attempt['id'], command, 'tree-reconcile')
        assert reopened.reconcile(attempt['id'], command, 'tree-reconcile') == result
        current = reopened.delivery.export_record(reopened.store.get('export', record['id']))
        if entry_kind in {'unchanged', 'ordinary_directory'}:
            assert result['state'] == 'succeeded' and result['terminal_reason'] == 'EXPORT_RECOVERED'
            assert current['verified_path'] == str(directory)
        else:
            assert result['state'] == 'failed' and result['terminal_reason'] == 'EXPORT_INTERRUPTED'
            assert current['verified_path'] is None and current['error']['code'] == 'EXPORT_INTERRUPTED'
        assert {kind: len(reopened.store.list(kind)) for kind in counts} == counts
        assert tree() == before
    finally:
        reopened.close()
