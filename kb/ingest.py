import os, hashlib, json, logging
from datetime import datetime
from kb.config import CFG
from kb.storage import connect, audit

log = logging.getLogger("ingest")

def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(65536), b""):
            h.update(blk)
    return h.hexdigest()

def discover(docs_dir):
    out = []
    for root, _, files in os.walk(docs_dir):
        for f in files:
            if f.lower().endswith((".txt", ".md", ".json")):
                out.append(os.path.join(root, f))
    return out

def detect_changes(paths):
    """Return list of (path, reason) for new/modified docs only."""
    changes = []
    with connect() as c:
        known = {r["path"]: r["content_hash"] for r in
                 c.execute("SELECT path, content_hash FROM documents WHERE status!='deleted'")}
    for p in paths:
        h = file_hash(p)
        if p not in known:
            changes.append((p, "new"))
        elif known[p] != h:
            changes.append((p, "modified"))
    return changes

def load_text(path):
    if path.endswith(".json"):
        with open(path) as f:
            data = json.load(f)
        return data.get("text", json.dumps(data))
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()

def chunk_text(text, size, overlap):
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i+size]))
        i += size - overlap
    return [c for c in chunks if c.strip()]

def register_document(path, content_hash, chunks, version, status="staging"):
    from kb.index import embed
    doc_id = hashlib.sha1(path.encode()).hexdigest()[:16]
    with connect() as c:
        c.execute("""INSERT INTO documents(doc_id,path,content_hash,version,status,updated_at)
                     VALUES(?,?,?,?,?,?)
                     ON CONFLICT(doc_id) DO UPDATE SET
                       content_hash=excluded.content_hash,
                       version=excluded.version,
                       status=excluded.status,
                       updated_at=excluded.updated_at""",
                  (doc_id, path, content_hash, version, status, datetime.utcnow().isoformat()))
        c.execute("DELETE FROM chunks WHERE doc_id=? AND version=?", (doc_id, version))
        for i, ch in enumerate(chunks):
            cid = hashlib.sha1(f"{doc_id}:{version}:{i}".encode()).hexdigest()
            c.execute("INSERT INTO chunks(chunk_id,doc_id,version,text,embedding) VALUES(?,?,?,?,?)",
                      (cid, doc_id, version, ch, json.dumps(embed(ch).tolist())))
    return doc_id

def run_ingest(actor="system"):
    """Full ingestion cycle: discover → change-detect → dedup → validate → register."""
    from kb.dedup import is_duplicate
    from kb.validate import validate_file, quarantine

    paths = discover(CFG.paths.docs_dir)
    changes = detect_changes(paths)
    log.info("Detected %d change(s)", len(changes))
    results = {"new": [], "modified": [], "duplicates": [], "quarantined": []}

    # Preload existing chunk hashes for dedup
    with connect() as c:
        existing = [r["text"] for r in c.execute("SELECT text FROM chunks")]

    for path, reason in changes:
        ok, err = validate_file(path)
        if not ok:
            quarantine(path, err)
            results["quarantined"].append({"path": path, "reason": err})
            audit(actor, "quarantine", {"path": path, "reason": err})
            continue

        text = load_text(path)
        chunks = chunk_text(text, CFG.chunk.size, CFG.chunk.overlap)
        dup, score = is_duplicate(chunks, existing)
        if dup:
            results["duplicates"].append({"path": path, "score": score})
            audit(actor, "duplicate_skipped", {"path": path, "score": score})
            continue

        version = 1
        with connect() as c:
            row = c.execute("SELECT version FROM documents WHERE path=?", (path,)).fetchone()
            if row: version = row["version"] + 1

        register_document(path, file_hash(path), chunks, version, status="staging")
        results[reason].append({"path": path, "version": version, "chunks": len(chunks)})
        existing.extend(chunks)

    audit(actor, "ingest_complete", results)
    return results