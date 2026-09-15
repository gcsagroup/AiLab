"""单机事务存储；业务状态与事件在同一事务提交。"""

import contextlib
import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def identifier(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


class Fault(Exception):
    def __init__(self, code, message, status=400, **details):
        self.code, self.message, self.status, self.details = code, message, status, details
        super().__init__(message)


class Store:
    def __init__(self, path):
        from .migrations import connect
        self.path = Path(path)
        self.lock = threading.RLock()
        self.db = connect(self.path)
        self._closed = False

    def close(self):
        """显式关闭真实连接；只有成功关闭后才登记，失败可重试。"""
        with self.lock:
            if not self._closed:
                self.db.close()
                self._closed = True

    @contextlib.contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def get(self, kind, resource_id):
        with self.lock:
            if kind == "project":
                row = self.db.execute("SELECT body FROM projects WHERE id=?", (resource_id,)).fetchone()
            else:
                row = self.db.execute("SELECT body FROM resources WHERE id=? AND kind=?", (resource_id, kind)).fetchone()
            if not row:
                raise Fault("RESOURCE_NOT_FOUND", "记录不存在。", 404)
            return json.loads(row[0])

    def put(self, kind, value):
        if kind == "project":
            self.db.execute("INSERT INTO projects VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (value["id"], encode(value)))
        else:
            self.db.execute("INSERT INTO resources VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body", (value["id"], kind, value["project_id"], encode(value)))

    def list(self, kind, project_id=None):
        with self.lock:
            if kind == "project":
                rows = self.db.execute("SELECT body FROM projects ORDER BY rowid").fetchall()
            elif project_id:
                self.get("project", project_id)
                rows = self.db.execute("SELECT body FROM resources WHERE kind=? AND project_id=? ORDER BY rowid", (kind, project_id)).fetchall()
            else:
                rows = self.db.execute("SELECT body FROM resources WHERE kind=? ORDER BY rowid", (kind,)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def page(self, kind, project_id=None, cursor=None, limit=100, *, task_id=None, operation=None, descending=False, execution_target_id=None):
        """按原 rowid 顺序只读取当前页，游标必须属于同一查询范围。"""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise Fault("INVALID_PAGE_LIMIT", "每页条数必须为 1 至 200 的整数。")
        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            raise Fault("INVALID_CURSOR", "列表游标已失效，请重新加载。")
        if type(descending) is not bool:
            raise Fault("INVALID_PAGE_ORDER", "列表排序参数无效。")
        if cursor is not None:
            if descending:
                if not cursor.startswith("desc:") or not cursor.removeprefix("desc:"):
                    raise Fault("INVALID_CURSOR", "列表排序已变化，请从第一页重新加载。")
                cursor = cursor.removeprefix("desc:")
            elif cursor.startswith("desc:"):
                raise Fault("INVALID_CURSOR", "列表游标与排序不一致，请重新加载。")
        with self.lock:
            table, clauses, parameters = "projects", [], []
            if kind != "project":
                table = "resources INDEXED BY resources_attempt_task" if kind == "attempt" and task_id else "resources"
                if kind == "attempt" and task_id:
                    clauses.append("kind='attempt'")
                else:
                    clauses.append("kind=?"); parameters.append(kind)
                if project_id:
                    self.get("project", project_id)
                    clauses.append("project_id=?"); parameters.append(project_id)
                if task_id:
                    clauses.append("json_extract(body,'$.task_id')=?"); parameters.append(task_id)
                if operation:
                    clauses.append("json_extract(body,'$.snapshot.operation')=?"); parameters.append(operation)
                if execution_target_id:
                    clauses.append("json_extract(body,'$.execution_target_id')=?"); parameters.append(execution_target_id)
            scope = " AND ".join(clauses) or "1"
            after = None
            if cursor is not None:
                row = self.db.execute(f"SELECT rowid FROM {table} WHERE {scope} AND id=?", [*parameters, cursor]).fetchone()
                if row is None:
                    raise Fault("INVALID_CURSOR", "列表游标已失效，请重新加载。")
                after = row[0]
            seek, seek_values = (f" AND rowid{'<' if descending else '>'}?", [after]) if after is not None else ("", [])
            order = " DESC" if descending else ""
            rows = self.db.execute(f"SELECT id,body FROM {table} WHERE {scope}{seek} ORDER BY rowid{order} LIMIT ?", [*parameters, *seek_values, limit + 1]).fetchall()
            return {"items": [json.loads(row[1]) for row in rows[:limit]],
                    "next_cursor": ("desc:" if descending else "") + rows[limit - 1][0] if len(rows) > limit else None}

    def replay(self, scope, key, payload):
        if not key or len(key) > 200 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise Fault("IDEMPOTENCY_KEY_REQUIRED", "请提供 1 至 200 位可见英文字符的 Idempotency-Key。")
        row = self.db.execute("SELECT request_digest,response FROM commands WHERE scope=? AND key=?", (scope, key)).fetchone()
        if row:
            if row[0] != digest(payload):
                raise Fault("IDEMPOTENCY_CONFLICT", "此命令键已用于不同内容，请使用新的命令键。", 409)
            return json.loads(row[1])
        return None

    def remember(self, scope, key, payload, response):
        self.db.execute("INSERT INTO commands VALUES(?,?,?,?)", (scope, key, digest(payload), encode(response)))

    def event(self, attempt, event_type, payload):
        sequence = attempt["last_event_sequence"] + 1
        event = {"schema_version": "1.1", "attempt_id": attempt["id"], "sequence": sequence,
                 "type": event_type, "created_at": now(), "payload": payload}
        self.db.execute("INSERT INTO events VALUES(?,?,?)", (attempt["id"], sequence, encode(event)))
        attempt["last_event_sequence"] = sequence
        self.put("attempt", attempt)
        return event

    def events(self, attempt_id, after, limit):
        with self.lock:
            self.get("attempt", attempt_id)
            rows = self.db.execute("SELECT body FROM events WHERE attempt_id=? AND sequence>? ORDER BY sequence LIMIT ?", (attempt_id, after, limit)).fetchall()
            items = [json.loads(r[0]) for r in rows]
            return {"items": items, "next_cursor": items[-1]["sequence"] if items else after}

    def backup(self, destination):
        with self.lock, sqlite3.connect(destination) as backup:
            self.db.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Fault("BACKUP_FAILED", "备份完整性检查失败。", 500)
