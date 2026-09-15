"""界面上下文使用真实 SQLite；只建普通草稿，不加载模型或执行任务。"""

import copy
from concurrent.futures import ThreadPoolExecutor
import contextlib
import json
from pathlib import Path
import sqlite3
import sys
import threading

import pytest

from test_control import rig, post
from test_backup_restore import plan_restore
from ailab_control.backup import Backup
from ailab_control.service import Service, Settings
from ailab_control.storage import Fault, encode


EMPTY = {"project_id": None, "projects": {}}


def context(**changes):
    return {"page": "home", "kind": "text", "module_tab": "generate", "data_tab": "local",
            "task_id": None, "workflow_id": None, **changes}


def resources(rig):
    client, service, *_ = rig
    values = []
    for name, kind in (("项目甲", "text"), ("项目乙", "image")):
        project = post(client, "/projects", {"name": name})
        task = post(client, "/tasks", {"project_id": project["id"], "name": name + "草稿", "kind": kind, "operation": "generate"})
        workflow = service.resource("workflow-run", project["id"], name=name + "工作流夹具", status="draft")
        with service.store.transaction():
            service.store.put("workflow-run", workflow)
        values.append((project, task, workflow))
    return values


def patch(client, project, value):
    return client.patch("/api/v1/ui-context", json={"project_id": project["id"], "context": value})


def saved_settings(service):
    row = service.store.db.execute("SELECT body FROM app_settings WHERE id=1").fetchone()
    return json.loads(row[0]) if row else None


def store_context(service, value):
    settings = {**service.user_settings, "ui_context": value}
    with service.store.transaction():
        service.store.db.execute("INSERT INTO app_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (encode(settings),))
        service.user_settings = settings


def test_old_library_ui_read_is_empty_and_does_not_write(rig):
    client, service, *_ = rig
    before = service.store.db.total_changes
    response = client.get("/api/v1/ui-context")
    assert response.status_code == 200 and response.json() == EMPTY
    assert saved_settings(service) is None and service.store.db.total_changes == before
    assert "ui_context" not in client.get("/api/v1/settings").json()


def test_two_project_contexts_survive_real_sqlite_close_and_reopen(rig):
    client, service, *_ = rig
    (pa, ta, _), (pb, _, wb) = resources(rig)
    ca, cb = context(task_id=ta["id"]), context(kind="image", module_tab="history", workflow_id=wb["id"])
    assert patch(client, pa, ca).status_code == 200
    response = patch(client, pb, cb)
    expected = {"project_id": pb["id"], "projects": {pa["id"]: ca, pb["id"]: cb}}
    assert response.status_code == 200 and response.json() == expected
    assert "ui_context" not in client.get("/api/v1/settings").json()
    service.close()
    reopened = Service(copy.copy(service.settings))
    try:
        assert reopened.get_ui_context() == expected
        assert reopened.store.get("task", ta["id"])["draft"] == ta["draft"]
    finally:
        reopened.close()


def test_context_is_bound_to_library_even_with_identical_project_and_task_ids(rig, tmp_path):
    client, service, *_ = rig
    (project, task, _), _ = resources(rig)
    ca = context(task_id=task["id"])
    assert patch(client, project, ca).status_code == 200
    other = Service(Settings(tmp_path / "独立工作库", "independent-test-token"))
    try:
        with other.store.transaction():
            other.store.put("project", project)
            other.store.put("task", task)
        assert other.get_ui_context() == EMPTY
        other.update_ui_context({"project_id": project["id"], "context": context(page="models")})
        assert service.get_ui_context()["projects"][project["id"]] == ca
    finally:
        other.close()


@pytest.mark.parametrize("field,index", [("task_id", 1), ("workflow_id", 2)])
def test_cross_project_selection_is_rejected_without_any_write(rig, field, index):
    client, service, *_ = rig
    first, second = resources(rig)
    assert patch(client, first[0], context()).status_code == 200
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    response = patch(client, first[0], context(**{field: second[index]["id"]}))
    assert response.status_code == 403 and response.json()["error"]["code"] == "PROJECT_MISMATCH"
    assert saved_settings(service) == before and service.user_settings == memory


@pytest.mark.parametrize("field,value", [("page", "settings"), ("kind", "other"), ("module_tab", "run"),
                                         ("data_tab", "remote"), ("task_id", 5), ("workflow_id", True),
                                         ("body", {"worker_python": "/bin/sh"})])
def test_ui_context_rejects_unknown_fields_and_invalid_types(rig, field, value):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    response = patch(client, project, context(**{field: value}))
    assert response.status_code == 422
    assert saved_settings(service) is None


@pytest.mark.parametrize("field", list(context()))
def test_context_requires_each_explicit_field(rig, field):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    value = context(); value.pop(field)
    assert patch(client, project, value).status_code == 422
    assert saved_settings(service) is None


def test_payload_cannot_replace_all_projects_or_select_task_and_workflow(rig):
    client, service, *_ = rig
    (project, task, workflow), _ = resources(rig)
    assert patch(client, project, context(task_id=task["id"], workflow_id=workflow["id"])).status_code == 422
    response = client.patch("/api/v1/ui-context", json={"project_id": project["id"], "context": context(), "projects": {}})
    assert response.status_code == 422
    assert client.patch("/api/v1/ui-context", json={"project_id": None, "context": context()}).status_code == 422
    assert saved_settings(service) is None


@pytest.mark.parametrize("field", ["project_id", "task_id", "workflow_id"])
def test_nonexistent_selection_is_rejected_without_write(rig, field):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    payload = {"project_id": project["id"], "context": context()}
    if field == "project_id":
        payload[field] = "project-does-not-exist"
    else:
        payload["context"][field] = "missing-selection"
    response = client.patch("/api/v1/ui-context", json=payload)
    assert response.status_code in {404, 409}
    assert response.json()["error"]["code"] in {"RESOURCE_NOT_FOUND", "UI_CONTEXT_REFERENCE_MISSING"}
    assert saved_settings(service) is None


def test_ui_write_preserves_environment_caches_and_business_revisions(rig):
    client, service, *_ = rig
    (project, task, _), _ = resources(rig)
    cache = ("cache-key", {"ready": True})
    service.environment_cache = cache
    service.media.cache["fixed"] = "media-cache-marker"
    before = copy.deepcopy(service.user_settings)
    assert patch(client, project, context(task_id=task["id"])).status_code == 200
    assert {k: v for k, v in service.user_settings.items() if k != "ui_context"} == before
    assert service.environment_cache is cache and service.media.cache == {"fixed": "media-cache-marker"}
    assert service.store.get("project", project["id"]) == project
    assert service.store.get("task", task["id"]) == task
    assert service.store.list("attempt") == []


def test_environment_and_ui_updates_preserve_each_other_under_concurrent_requests(rig):
    client, service, *_ = rig
    (pa, _, _), (pb, _, _) = resources(rig)
    assert patch(client, pa, context()).status_code == 200
    start = threading.Barrier(2)
    def environment():
        start.wait(timeout=3)
        return client.patch("/api/v1/settings", json={"expected_revision": 1, "worker_python": sys.executable})
    def ui():
        start.wait(timeout=3)
        return patch(client, pb, context(page="data", data_tab="market"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        env, selection = pool.submit(environment), pool.submit(ui)
        assert env.result(timeout=5).status_code == selection.result(timeout=5).status_code == 200
    saved = saved_settings(service)
    assert saved["revision"] == 2 and saved["worker_python"] == sys.executable
    assert set(saved["ui_context"]["projects"]) == {pa["id"], pb["id"]}
    assert saved == service.user_settings
    assert patch(client, pa, context(page="assets")).status_code == 200
    assert saved_settings(service)["worker_python"] == sys.executable and service.user_settings["revision"] == 2


def test_failed_ui_transaction_preserves_database_and_memory(rig, monkeypatch):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    assert patch(client, project, context()).status_code == 200
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    transaction = service.store.transaction
    @contextlib.contextmanager
    def failed_commit():
        with transaction():
            yield
            raise sqlite3.OperationalError("夹具模拟提交前失败")
    with monkeypatch.context() as scope:
        scope.setattr(service.store, "transaction", failed_commit)
        assert patch(client, project, context(page="assets")).status_code == 500
    assert saved_settings(service) == before and service.user_settings == memory


def test_missing_objects_are_normalized_only_in_response_and_cross_project_is_not_hidden(rig):
    client, service, *_ = rig
    (pa, _, _), (pb, tb, _) = resources(rig)
    value = {"project_id": "project-gone", "projects": {"project-gone": context(), pa["id"]: context(task_id="task-gone")}}
    store_context(service, value)
    before = saved_settings(service)
    response = client.get("/api/v1/ui-context")
    assert response.status_code == 200 and response.json() == {"project_id": None, "projects": {pa["id"]: context()}}
    assert saved_settings(service) == before
    store_context(service, {"project_id": pa["id"], "projects": {pa["id"]: context(task_id=tb["id"])}})
    assert client.get("/api/v1/ui-context").status_code == 403


def test_updating_one_project_does_not_write_normalized_other_project(rig):
    client, service, *_ = rig
    (pa, _, _), (pb, _, _) = resources(rig)
    old = context(task_id="task-removed")
    store_context(service, {"project_id": pa["id"], "projects": {pa["id"]: old}})
    response = patch(client, pb, context(page="models"))
    assert response.status_code == 200
    assert response.json()["projects"][pa["id"]] == context()
    assert saved_settings(service)["ui_context"]["projects"][pa["id"]] == old


def test_ui_routes_require_auth_and_do_not_expand_settings_write_contract(rig):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    payload = {"project_id": project["id"], "context": context()}
    for method in ("GET", "PATCH"):
        response = client.request(method, "/api/v1/ui-context", json=payload if method == "PATCH" else None,
                                  headers={"Authorization": "Bearer wrong-test-token"})
        assert response.status_code == 401
    response = client.patch("/api/v1/settings", json={"expected_revision": 1, "worker_python": sys.executable, "ui_context": EMPTY})
    assert response.status_code == 422
    assert saved_settings(service) is None


def test_ui_patch_obeys_library_switch_and_backup_write_gates(rig):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    for flag, code in (("activation_pending", "LIBRARY_SWITCH_PENDING"), ("maintenance_pending", "CLEANUP_BUSY")):
        setattr(service, flag, True)
        if flag == "activation_pending": service.activation_deadline = float("inf")
        try:
            result = patch(client, project, context())
            assert result.status_code == 409 and result.json()["error"]["code"] == code
            assert client.get("/api/v1/ui-context").status_code == 200
        finally:
            setattr(service, flag, False)
    assert saved_settings(service) is None


@pytest.mark.parametrize("with_ui", [False, True])
def test_old_and_new_backups_restore_ui_without_inheriting_environment(rig, tmp_path, with_ui):
    client, service, *_ = rig
    (project, task, _), _ = resources(rig)
    assert client.patch("/api/v1/settings", json={"expected_revision": 1, "worker_python": sys.executable}).status_code == 200
    expected = EMPTY
    if with_ui:
        selected = context(task_id=task["id"])
        assert patch(client, project, selected).status_code == 200
        expected = {"project_id": project["id"], "projects": {project["id"]: selected}}
    manager = Backup(service); backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "恢复目标")
    restored = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-ui")
    reopened = Service(Settings(Path(restored["restored_path"]), "restored-ui-test-token"))
    try:
        assert reopened.get_ui_context() == expected
        assert reopened.user_settings["worker_python"] is None
        assert reopened.user_settings["revision"] == 3
        assert ("ui_context" in reopened.user_settings) is with_ui
    finally:
        reopened.close()


@pytest.mark.parametrize("damage", ["extra", "null", "missing", "cross_project", "unknown_project"])
def test_backup_rejects_invalid_ui_structure_or_references(rig, damage):
    _, service, *_ = rig
    (pa, _, _), (_, tb, _) = resources(rig)
    value = {"project_id": pa["id"], "projects": {pa["id"]: context()}}
    if damage == "extra": value["projects"][pa["id"]]["worker_python"] = "/bin/sh"
    elif damage == "null": value = None
    elif damage == "missing": value["projects"][pa["id"]]["task_id"] = "task-missing"
    elif damage == "cross_project": value["projects"][pa["id"]]["task_id"] = tb["id"]
    else: value["projects"]["project-missing"] = context()
    store_context(service, value)
    before = saved_settings(service)
    with pytest.raises(Fault) as caught:
        Backup(service).create()
    assert caught.value.code in {"UI_CONTEXT_INVALID", "UI_CONTEXT_REFERENCE_MISSING", "PROJECT_MISMATCH"}
    assert not list((service.root / "backups").glob("backup-*"))
    assert saved_settings(service) == before


def test_recent_tasks_accepts_all_eight_slots_and_survives_reopen(rig):
    client, service, *_ = rig
    (project, _, workflow), _ = resources(rig)
    selected = {}
    originals = []
    for kind in ("text", "image", "video", "audio"):
        for operation in ("train", "generate"):
            task = post(client, "/tasks", {"project_id": project["id"], "name": kind + operation,
                                           "kind": kind, "operation": operation})
            selected[kind + ":" + operation] = task["id"]
            originals.append(task)
    # 查看工作流不应清掉先前选择的八份普通草稿。
    view = context(workflow_id=workflow["id"], recent_tasks=selected)
    expected = {"project_id": project["id"], "projects": {project["id"]: view}}
    response = patch(client, project, view)
    assert response.status_code == 200 and response.json() == expected
    assert saved_settings(service)["ui_context"] == expected
    assert client.get("/api/v1/ui-context").json() == expected
    assert [service.store.get("task", task["id"]) for task in originals] == originals
    assert service.store.list("attempt") == []
    service.close()
    reopened = Service(copy.copy(service.settings))
    try:
        assert reopened.get_ui_context() == expected
        assert reopened.store.list("attempt") == []
    finally:
        reopened.close()


def test_recent_tasks_omitted_old_context_and_explicit_clear_keep_distinct_shapes(rig):
    client, service, *_ = rig
    (pa, ta, _), (pb, _, _) = resources(rig)
    old = context(task_id=ta["id"])
    assert patch(client, pa, old).status_code == 200
    assert saved_settings(service)["ui_context"]["projects"][pa["id"]] == old
    assert client.get("/api/v1/ui-context").json()["projects"][pa["id"]] == old
    selected = context(recent_tasks={"text:generate": ta["id"]})
    assert patch(client, pa, selected).status_code == 200
    cleared = context(recent_tasks={})
    assert patch(client, pa, cleared).json()["projects"][pa["id"]] == cleared
    assert saved_settings(service)["ui_context"]["projects"][pa["id"]] == cleared
    assert patch(client, pa, selected).status_code == 200
    # 仍按整段 context 替换；旧调用方省略字段不是保留上次映射的部分补丁。
    assert patch(client, pa, old).json()["projects"][pa["id"]] == old
    assert patch(client, pb, context(page="models")).status_code == 200
    assert saved_settings(service)["ui_context"]["projects"][pa["id"]] == old


@pytest.mark.parametrize("invalid", [None, [], "text:generate", {"text:run": "task-any"},
    {"text:generate": None}, {"text:generate": True}, {"text:generate": 1},
    {"text:generate": []}, {"text:generate": {}}, {"text:generate": ""},
    {"text:generate": "x" * 101},
    {**{kind + ":" + operation: "task-any" for kind in ("text", "image", "video", "audio")
        for operation in ("train", "generate")}, "text:evaluate": "task-any"}])
def test_recent_tasks_rejects_invalid_keys_size_and_value_types(rig, invalid):
    client, service, *_ = rig
    (project, _, _), _ = resources(rig)
    assert patch(client, project, context()).status_code == 200
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    response = patch(client, project, context(recent_tasks=invalid))
    assert response.status_code == 422
    assert saved_settings(service) == before and service.user_settings == memory


RECENT_REFERENCE_ERRORS = [
    ("missing", "UI_CONTEXT_REFERENCE_MISSING", 409),
    ("cross_project", "PROJECT_MISMATCH", 403),
    ("wrong_kind", "UI_CONTEXT_TASK_MISMATCH", 409),
    ("wrong_operation", "UI_CONTEXT_TASK_MISMATCH", 409),
    ("workflow", "UI_CONTEXT_WORKFLOW_TASK", 409),
    ("empty_workflow", "UI_CONTEXT_WORKFLOW_TASK", 409),
    ("fixed", "UI_CONTEXT_FIXED_TASK", 409),
]


def invalid_recent_reference(service, first, second, damage):
    pa, ta, wa = first
    _, tb, _ = second
    slot, task_id = "text:generate", ta["id"]
    if damage == "missing":
        task_id = "task-missing"
    elif damage == "cross_project":
        slot, task_id = "image:generate", tb["id"]
    elif damage == "wrong_kind":
        slot = "image:generate"
    elif damage == "wrong_operation":
        slot = "text:train"
    else:
        changed = copy.deepcopy(ta)
        if damage == "fixed":
            changed["immutable_draft"] = True
        else:
            changed["workflow_ref"] = {"workflow_run_id": wa["id"]} if damage == "workflow" else {}
        with service.store.transaction():
            service.store.put("task", changed)
    return {"project_id": pa["id"], "projects": {pa["id"]: context(recent_tasks={slot: task_id})}}


@pytest.mark.parametrize("damage,code,status", RECENT_REFERENCE_ERRORS)
def test_recent_tasks_save_rejects_invalid_reference_without_writes(rig, damage, code, status):
    client, service, *_ = rig
    first, second = resources(rig)
    value = invalid_recent_reference(service, first, second, damage)
    assert patch(client, first[0], context()).status_code == 200
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    response = patch(client, first[0], value["projects"][first[0]["id"]])
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert saved_settings(service) == before and service.user_settings == memory


@pytest.mark.parametrize("damage,code,status", RECENT_REFERENCE_ERRORS[1:])
def test_recent_tasks_read_does_not_hide_existing_invalid_reference(rig, damage, code, status):
    client, service, *_ = rig
    first, second = resources(rig)
    store_context(service, invalid_recent_reference(service, first, second, damage))
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    response = client.get("/api/v1/ui-context")
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert saved_settings(service) == before and service.user_settings == memory


def test_recent_tasks_deleted_reference_is_removed_only_from_read_response(rig):
    client, service, *_ = rig
    (pa, ta, _), (pb, _, _) = resources(rig)
    retained = post(client, "/tasks", {"project_id": pa["id"], "name": "仍在的训练草稿",
                                      "kind": "text", "operation": "train"})
    selected = context(recent_tasks={"text:generate": ta["id"], "text:train": retained["id"]})
    assert patch(client, pa, selected).status_code == 200
    with service.store.transaction():
        service.store.db.execute("DELETE FROM resources WHERE id=?", (ta["id"],))
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    response = client.get("/api/v1/ui-context")
    assert response.status_code == 200
    assert response.json()["projects"][pa["id"]] == context(recent_tasks={"text:train": retained["id"]})
    assert saved_settings(service) == before and service.user_settings == memory
    assert patch(client, pb, context(page="models")).status_code == 200
    assert saved_settings(service)["ui_context"]["projects"][pa["id"]] == selected


@pytest.mark.parametrize("damage,code,_status", RECENT_REFERENCE_ERRORS)
def test_recent_tasks_backup_rejects_invalid_reference(rig, damage, code, _status):
    _, service, *_ = rig
    first, second = resources(rig)
    store_context(service, invalid_recent_reference(service, first, second, damage))
    before, memory = saved_settings(service), copy.deepcopy(service.user_settings)
    with pytest.raises(Fault) as caught:
        Backup(service).create()
    assert caught.value.code == code
    assert saved_settings(service) == before and service.user_settings == memory
    assert not list((service.root / "backups").glob("backup-*"))


def test_recent_tasks_backup_restore_preserves_selection_and_old_project_shape(rig, tmp_path):
    client, service, *_ = rig
    (pa, ta, _), (pb, tb, _) = resources(rig)
    ca = context(recent_tasks={"text:generate": ta["id"]})
    cb = context(kind="image", task_id=tb["id"])
    assert patch(client, pa, ca).status_code == patch(client, pb, cb).status_code == 200
    expected = {"project_id": pb["id"], "projects": {pa["id"]: ca, pb["id"]: cb}}
    manager = Backup(service)
    backup = manager.create()
    plan = plan_restore(rig, manager, backup, tmp_path / "仅测试的新恢复目录")
    result = manager.restore({"plan_id": plan["id"], "plan_digest": plan["plan_digest"]}, "restore-recent-tasks")
    reopened = Service(Settings(Path(result["restored_path"]), "restored-recent-test-token"))
    try:
        assert reopened.get_ui_context() == saved_settings(reopened)["ui_context"] == expected
        assert reopened.store.get("task", ta["id"]) == ta
        assert reopened.store.get("task", tb["id"]) == tb
        assert reopened.store.list("attempt") == []
    finally:
        reopened.close()
