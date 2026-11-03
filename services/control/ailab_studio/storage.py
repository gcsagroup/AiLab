"""Small durable job journal, with a portable exclusive owner lock."""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path


def uid():
    return uuid.uuid4().hex


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.guard = (self.root / 'studio.lock').open('a+b')
        self.guard.seek(0)
        if os.name == 'nt':
            import msvcrt
            if not self.guard.read(1):
                self.guard.write(b'0'); self.guard.flush()
            self.guard.seek(0)
            msvcrt.locking(self.guard.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / 'studio.sqlite3', check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body TEXT, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, body TEXT);
            CREATE INDEX IF NOT EXISTS events_job ON events(job,seq);''')
        self.db.commit()

    def put(self, kind, value):
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?)', (kind, value['id'], json.dumps(value, ensure_ascii=False, allow_nan=False)))
        return value

    def get(self, kind, key):
        with self.lock:
            row = self.db.execute('SELECT body FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()
        if not row:
            raise ValueError('记录不存在')
        return json.loads(row[0])

    def delete(self, kind, key):
        with self.lock, self.db:
            self.db.execute('DELETE FROM records WHERE kind=? AND id=?', (kind, key))

    def list(self, kind, limit=100):
        with self.lock:
            rows = self.db.execute('SELECT body FROM records WHERE kind=? ORDER BY rowid DESC LIMIT ?', (kind, limit)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def event(self, job, event):
        value = {**event, 'time': time.time()}
        with self.lock, self.db:
            self.db.execute('INSERT INTO events(job,body) VALUES(?,?)', (job, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    def events(self, job, after=0):
        with self.lock:
            rows = self.db.execute('SELECT seq,body FROM events WHERE job=? AND seq>? ORDER BY seq LIMIT 250', (job, after)).fetchall()
        return [{'seq': row[0], **json.loads(row[1])} for row in rows]

    def close(self):
        self.db.close()
        self.guard.close()
