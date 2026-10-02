import sqlite3, json, threading
from contextlib import contextmanager
from kb.config import CFG

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  chunk_hash TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL,           -- active | staging | quarantined | deleted
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  text TEXT NOT NULL,
  embedding TEXT NOT NULL,
  FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
);
CREATE TABLE IF NOT EXISTS versions (
  version INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  snapshot_path TEXT NOT NULL,
  status TEXT NOT NULL,           -- staging | active | rolled_back | rejected
  notes TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT,
  action TEXT,
  detail TEXT
);
CREATE TABLE IF NOT EXISTS retries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job TEXT NOT NULL,
  payload TEXT,
  attempt INTEGER DEFAULT 0,
  next_run REAL NOT NULL,
  status TEXT DEFAULT 'pending'
);
"""

def init_db():
    with connect() as c:
        c.executescript(SCHEMA)

@contextmanager
def connect():
    with _lock:
        c = sqlite3.connect(CFG.paths.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

def audit(actor, action, detail=""):
    from datetime import datetime
    with connect() as c:
        c.execute("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)",
                  (datetime.utcnow().isoformat(), actor, action, json.dumps(detail)))