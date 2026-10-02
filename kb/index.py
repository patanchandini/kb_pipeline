import hashlib, numpy as np
from kb.config import CFG

def embed(text: str) -> np.ndarray:
    """Deterministic hash-embedding. Swap with sentence-transformers/OpenAI in prod."""
    dim = CFG.embedding.dim
    vec = np.zeros(dim, dtype=np.float32)
    for tok in text.lower().split():
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h // dim) % dim] += 0.5
    n = np.linalg.norm(vec)
    return vec / n if n > 0 else vec

def search(query: str, version: int = None, top_k: int = 3):
    from kb.storage import connect
    import json
    qv = embed(query)
    with connect() as c:
        sql = "SELECT chunk_id, doc_id, version, text, embedding FROM chunks"
        params = ()
        if version is not None:
            sql += " WHERE version<=?"
            params = (version,)
        rows = list(c.execute(sql, params))
    scored = []
    for r in rows:
        ev = np.array(json.loads(r["embedding"]), dtype=np.float32)
        s = float(np.dot(qv, ev))
        scored.append((s, r["text"], r["doc_id"]))
    scored.sort(reverse=True)
    return scored[:top_k]