"""数据库游标分页不全量读取，HTTP 过滤和历史顺序保持一致。"""

import json

import pytest

from test_control import rig, post
from ailab_control import storage
from ailab_control.storage import Fault


def seed(service, project, count=9, kind="task"):
    items = []
    with service.store.transaction():
        for index in range(count):
            item = service.resource(kind, project["id"], name=f"历史 {index}")
            if kind == "attempt":
                item.update(task_id="task-even" if index % 2 == 0 else "task-odd", state="cancelled", state_version=1,
                            collection_state="not_started", compute_outcome="cancelled", progress=0,
                            snapshot={"operation": "evaluate" if index % 2 == 0 else "generate", "adapter_id": "adapter-a", "evaluation_plan_id": "plan-a"})
            service.store.put(kind, item); items.append(item)
    return items


def test_page_preserves_insert_order_and_reads_only_current_json(rig, monkeypatch):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "分页"})
    items = seed(service, project, 20)
    decoded, statements = [], []
    original = json.loads
    def loads(value, *args, **kwargs):
        decoded.append(value)
        return original(value, *args, **kwargs)
    monkeypatch.setattr(storage.json, "loads", loads)
    service.store.db.set_trace_callback(statements.append)
    page = service.store.page("task", project["id"], limit=3)
    service.store.db.set_trace_callback(None)
    assert [item["id"] for item in page["items"]] == [item["id"] for item in items[:3]]
    assert page["next_cursor"] == items[2]["id"]
    assert len(decoded) == 4  # 一个项目和当前页三条正文。
    assert any("ORDER BY rowid LIMIT 4" in sql for sql in statements)
    assert all("OFFSET" not in sql for sql in statements)
    second = service.store.page("task", project["id"], page["next_cursor"], 3)
    assert [item["id"] for item in second["items"]] == [item["id"] for item in items[3:6]]


@pytest.mark.parametrize("route,kind", [("tasks", "task"), ("datasets", "dataset"), ("models", "model"), ("materials", "material"), ("works", "work"), ("adapters", "adapter"), ("workflow-runs", "workflow-run"), ("workflow-results", "workflow-result"), ("candidates", "candidate"), ("evaluation-plans", "evaluation-plan")])
def test_http_pages_do_not_use_full_store_list(rig, monkeypatch, route, kind):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "分页"}); items = seed(service, project, kind=kind)
    monkeypatch.setattr(service.store, "list", lambda *_: pytest.fail("集合接口不能全量读取"))
    cursor, seen = None, []
    for _ in range(3):
        response = client.get("/api/v1/" + route, params={"project_id": project["id"], "limit": 3, **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        body = response.json(); seen.extend(item["id"] for item in body["items"]); cursor = body["next_cursor"]
    expected = list(reversed(items)) if route in {"tasks", "works", "workflow-runs"} else items
    assert cursor is None and seen == [item["id"] for item in expected]


def test_cursor_rejects_different_project_kind_or_attempt_filter(rig):
    client, service, *_ = rig
    first = post(client, "/projects", {"name": "一"}); second = post(client, "/projects", {"name": "二"})
    task = seed(service, first)[0]; attempts = seed(service, first, kind="attempt")
    for kind, project_id, cursor, kwargs in [("task", second["id"], task["id"], {}), ("dataset", first["id"], task["id"], {}), ("attempt", first["id"], attempts[1]["id"], {"task_id": "task-even"}), ("attempt", first["id"], attempts[1]["id"], {"operation": "evaluate"})]:
        with pytest.raises(Fault) as captured:
            service.store.page(kind, project_id, cursor, 3, **kwargs)
        assert captured.value.code == "INVALID_CURSOR"
    for query in [{"limit": 0}, {"limit": 201}, {"cursor": ""}, {"cursor": "不存在"}]:
        response = client.get("/api/v1/tasks", params=query)
        assert response.status_code in (400, 422)


@pytest.mark.parametrize("route,parameters", [("attempts", {"task_id": "task-even"}), ("evaluations", {})])
def test_attempt_and_evaluation_filters_are_applied_before_limit(rig, monkeypatch, route, parameters):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "执行分页"}); items = seed(service, project, kind="attempt")
    original = service.store.list
    def bounded(kind, *args):
        assert kind != "attempt", "不能先加载所有执行再过滤"
        return original(kind, *args)
    monkeypatch.setattr(service.store, "list", bounded)
    one = client.get("/api/v1/" + route, params={"project_id": project["id"], "limit": 2, **parameters})
    assert one.status_code == 200, one.text
    expected = list(reversed(items[::2])) if route == "attempts" else items[::2]
    assert [item["id"] for item in one.json()["items"]] == [item["id"] for item in expected[:2]]
    two = client.get("/api/v1/" + route, params={"project_id": project["id"], "limit": 2, "cursor": one.json()["next_cursor"], **parameters})
    assert two.status_code == 200, two.text
    assert [item["id"] for item in two.json()["items"]] == [item["id"] for item in expected[2:4]]


def test_index_queries_use_rowid_range_without_full_scan(rig):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "执行计划"}); seed(service, project)
    for sql, arguments, index in [
        ("SELECT body FROM resources WHERE kind=? AND rowid>? ORDER BY rowid LIMIT ?", ("task", 2, 4), "resources_kind"),
        ("SELECT body FROM resources WHERE project_id=? AND kind=? AND rowid>? ORDER BY rowid LIMIT ?", (project["id"], "task", 2, 4), "resources_project_kind"),
    ]:
        details = " ".join(row[3] for row in service.store.db.execute("EXPLAIN QUERY PLAN " + sql, arguments))
        assert index in details and "rowid>?" in details and "SCAN" not in details and "TEMP B-TREE" not in details


def test_descending_cursor_cannot_be_reused_as_ascending_or_legacy_id(rig):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "排序游标"}); items = seed(service, project)
    one = service.store.page("task", project["id"], limit=3, descending=True)
    assert [item["id"] for item in one["items"]] == [item["id"] for item in reversed(items[-3:])]
    assert one["next_cursor"] == "desc:" + items[-3]["id"]
    for cursor, descending in [(one["next_cursor"], False), (items[-3]["id"], True)]:
        with pytest.raises(Fault) as captured:
            service.store.page("task", project["id"], cursor, 3, descending=descending)
        assert captured.value.code == "INVALID_CURSOR"
    response = client.get("/api/v1/tasks", params={"cursor": items[-3]["id"]})
    assert response.status_code == 400 and response.json()["error"]["code"] == "INVALID_CURSOR"


def test_task_detail_has_bounded_recent_history_and_full_attempt_stays_explicit(rig):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "最近历史"})
    task = post(client, "/tasks", {"project_id": project["id"], "name": "旧任务", "kind": "text", "operation": "generate"})
    attempts = seed(service, project, 105, "attempt")
    with service.store.transaction():
        for value in attempts:
            value.update(task_id=task["id"], collection_version=2, phase="completed", recovery_required=False,
                         output_text="正文" * 16000, snapshot={"operation": "generate", "input": {"prompt": "提示" * 16000}})
            service.store.put("attempt", value)
    detail = client.get("/api/v1/tasks/" + task["id"])
    assert detail.status_code == 200 and len(detail.content) < 128 * 1024
    body = detail.json()
    assert body["draft"] == task["draft"] and len(body["attempts"]) == 100
    assert body["latest_attempt"]["id"] == attempts[-1]["id"]
    assert body["attempts"][0]["collection_version"] == 2 and body["attempts"][0]["phase"] == "completed"
    assert "snapshot" not in body["attempts"][0] and "output_text" not in body["attempts"][0]
    older = client.get("/api/v1/attempts", params={"task_id": task["id"], "cursor": body["attempts_next_cursor"]})
    assert [value["id"] for value in older.json()["items"]] == [value["id"] for value in reversed(attempts[:5])]
    assert older.json()["next_cursor"] is None
    actual = client.get("/api/v1/attempts/" + attempts[-1]["id"]).json()
    assert actual["snapshot"] == attempts[-1]["snapshot"] and actual["output_text"]


def test_recent_tasks_use_indexed_latest_attempt_and_stay_below_host_payload_limit(rig):
    client, service, *_ = rig
    project = post(client, "/projects", {"name": "宿主体积"}); tasks = seed(service, project, 100)
    with service.store.transaction():
        for number, task in enumerate(tasks):
            task.update(kind="text", operation="generate", draft={"input": {"prompt": "中" * 16000}})
            service.store.put("task", task)
            for index in range(10):
                attempt = service.resource("attempt", project["id"], task_id=task["id"], state="cancelled", state_version=1,
                                           compute_outcome="cancelled", collection_state="not_started", output_text="中" * 16000,
                                           snapshot={"operation": "generate", "input": {"prompt": "中" * 16000}})
                service.store.put("attempt", attempt)
                task["expected_latest"] = attempt["id"]
    operations = []
    service.store.db.set_progress_handler(lambda: operations.append(1) or (1 if len(operations) > 1000 else 0), 1000)
    try:
        response = client.get("/api/v1/tasks", params={"project_id": project["id"], "limit": 100})
    finally:
        service.store.db.set_progress_handler(None, 0)
    assert response.status_code == 200, response.text
    assert len(response.content) < 128 * 1024 < 8 * 1024 * 1024
    assert [item["id"] for item in response.json()["items"]] == [item["id"] for item in reversed(tasks)]
    for item, expected in zip(response.json()["items"], reversed(tasks), strict=True):
        assert item["latest_attempt"]["id"] == expected["expected_latest"] and "draft" not in item
    plan = " ".join(row[3] for row in service.store.db.execute("EXPLAIN QUERY PLAN SELECT body FROM resources INDEXED BY resources_attempt_task WHERE kind='attempt' AND json_extract(body,'$.task_id')=? ORDER BY rowid DESC LIMIT 1", (tasks[0]["id"],)))
    assert "resources_attempt_task" in plan and "SCAN" not in plan and "TEMP B-TREE" not in plan
