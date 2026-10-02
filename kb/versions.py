import os, json, shutil
from datetime import datetime
from kb.config import CFG
from kb.storage import connect, audit

SNAP_DIR = "data/snapshots"

def create_snapshot(notes="staging build") -> int:
    os.makedirs(SNAP_DIR, exist_ok=True)
    with connect() as c:
        docs = [dict(r) for r in c.execute("SELECT * FROM documents")]
        chunks = [dict(r) for r in c.execute("SELECT * FROM chunks")]
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SNAP_DIR, f"snapshot_{ts}.json")
    with open(path, "w") as f:
        json.dump({"documents": docs, "chunks": chunks, "created": ts}, f)
    with connect() as c:
        cur = c.execute("INSERT INTO versions(created_at,snapshot_path,status,notes) VALUES(?,?,?,?)",
                        (datetime.utcnow().isoformat(), path, "staging", notes))
        vid = cur.lastrowid
    audit("system", "snapshot_created", {"version": vid, "path": path})
    return vid

def get_active_version() -> int:
    with connect() as c:
        r = c.execute("SELECT MAX(version) v FROM versions WHERE status='active'").fetchone()
        return r["v"] if r and r["v"] is not None else 0

def set_version_status(version, status, notes=""):
    with connect() as c:
        c.execute("UPDATE versions SET status=?, notes=? WHERE version=?",
                  (status, notes, version))
    audit("system", f"version_{status}", {"version": version, "notes": notes})

def rollback_to(version):
    """Restore DB state from a snapshot."""
    with connect() as c:
        row = c.execute("SELECT snapshot_path FROM versions WHERE version=?", (version,)).fetchone()
    if not row: raise ValueError(f"Version {version} not found")
    with open(row["snapshot_path"]) as f:
        snap = json.load(f)
    with connect() as c:
        c.execute("DELETE FROM documents")
        c.execute("DELETE FROM chunks")
        for d in snap["documents"]:
            c.execute("""INSERT INTO documents(doc_id,path,content_hash,version,status,updated_at)
                         VALUES(?,?,?,?,?,?)""",
                      (d["doc_id"], d["path"], d["content_hash"], d["version"], d["status"], d["updated_at"]))
        for ch in snap["chunks"]:
            c.execute("""INSERT INTO chunks(chunk_id,doc_id,version,text,embedding)
                         VALUES(?,?,?,?,?)""",
                      (ch["chunk_id"], ch["doc_id"], ch["version"], ch["text"], ch["embedding"]))
    set_version_status(version, "active", "rolled back")
    audit("system", "rollback", {"to_version": version})