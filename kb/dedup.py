import numpy as np
from kb.config import CFG

def _cos(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return float(np.dot(a, b) / (na * nb))

def is_duplicate(new_chunks, existing_texts):
    """Return (is_dup, score). Near-dup if ANY chunk matches existing above threshold."""
    if not existing_texts: return False, 0.0
    from kb.index import embed
    new_vecs = [embed(c) for c in new_chunks]
    # sample existing for perf
    sample = existing_texts[-500:]
    ex_vecs = [embed(t) for t in sample]
    best = 0.0
    for nv in new_vecs:
        for ev in ex_vecs:
            s = _cos(nv, ev)
            if s > best: best = s
            if best >= CFG.dedup.near_threshold: break
    return best >= CFG.dedup.near_threshold, round(best, 4)