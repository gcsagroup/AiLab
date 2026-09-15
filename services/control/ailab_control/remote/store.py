"""执行服务与独立工作进程共享的持久记录，不使用主工作库。"""

from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import sqlite3
import threading

from .protocol import ProtocolError, encode, now, transport_scope


class Store:
    def __init__(self, root, transport=None):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "executor.sqlite3", timeout=10, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        with self.transaction():
            self.db.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            previous = self.db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if previous and previous[0] != "1":
                raise ProtocolError("DATABASE_VERSION_UNSUPPORTED", "执行服务数据库版本不受支持。")
            saved = self.db.execute("SELECT value FROM metadata WHERE key='transport'").fetchone()
            effective = saved[0] if saved else "loopback_http" if previous else transport or "loopback_http"
            transport_scope(effective)
            if transport is not None and effective != transport:
                raise ProtocolError("TRANSPORT_MISMATCH", "此执行目录已绑定另一连接方式，请使用独立数据目录。", 409)
            self.transport = effective
            self.validation_scope = transport_scope(effective)
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('transport',?)", (effective,))
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('schema_version','1')")
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('executor_id',?)", ("executor-" + secrets.token_hex(16),))
            self.db.execute("CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY,snapshot_sha TEXT NOT NULL,submit_key TEXT NOT NULL UNIQUE,body TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS commands(key TEXT PRIMARY KEY,request_sha TEXT NOT NULL,attempt_id TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS events(attempt_id TEXT NOT NULL,sequence INTEGER NOT NULL,body TEXT NOT NULL,PRIMARY KEY(attempt_id,sequence))")
            self.db.execute("CREATE TABLE IF NOT EXISTS blobs(sha TEXT PRIMARY KEY,size INTEGER NOT NULL,state TEXT NOT NULL)")
        self.executor_id = self.db.execute("SELECT value FROM metadata WHERE key='executor_id'").fetchone()[0]

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def get(self, attempt_id):
        with self.lock:
            row = self.db.execute("SELECT body FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if row is None:
            raise ProtocolError("ATTEMPT_NOT_FOUND", "执行记录不存在。", 404)
        return json.loads(row[0])

    def put(self, attempt):
        self.db.execute("UPDATE attempts SET body=? WHERE id=?", (encode(attempt), attempt["id"]))

    def event(self, attempt, kind, value):
        attempt["last_event_sequence"] += 1
        event = {"attempt_id": attempt["id"], "sequence": attempt["last_event_sequence"], "type": kind, "created_at": now(), "data": value}
        self.db.execute("INSERT INTO events VALUES(?,?,?)", (attempt["id"], event["sequence"], encode(event)))
        self.put(attempt)
        return event

    def transition(self, attempt, state, **fields):
        if attempt["state"] in {"succeeded", "failed", "cancelled"}:
            return
        attempt.update(state=state, state_version=attempt["state_version"] + 1, **fields)
        self.event(attempt, "state_changed", {"state": state, "state_version": attempt["state_version"], **fields})

    def close(self):
        self.db.close()
