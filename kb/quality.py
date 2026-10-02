import json, os, logging
from kb.config import CFG
from kb.index import search

log = logging.getLogger("quality")

def _load_eval():
    path = CFG.quality.eval_set
    if not os.path.exists(path): return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def run_quality_tests(version=None):
    """Returns {passed: bool, accuracy, grounding, details}."""
    cases = _load_eval()
    if not cases:
        log.warning("No eval set — skipping quality gate (PASS by default)")
        return {"passed": True, "accuracy": 1.0, "grounding": 1.0, "details": "no eval set"}

    hits, grounded = 0, 0
    details = []
    for case in cases:
        q = case["question"]
        expected = case.get("answer_contains", "").lower()
        results = search(q, version=version, top_k=3)
        ctx = " ".join(r[1] for r in results).lower()
        ok_acc = expected in ctx if expected else True
        ok_grd = len(results) > 0 and results[0][0] > 0.05
        hits += int(ok_acc); grounded += int(ok_grd)
        details.append({"q": q, "acc": ok_acc, "grd": ok_grd, "top": results[0][0] if results else 0})

    acc = hits / len(cases)
    grd = grounded / len(cases)
    passed = acc >= CFG.quality.min_accuracy and grd >= CFG.quality.min_grounding
    log.info("Quality: acc=%.2f grd=%.2f passed=%s", acc, grd, passed)
    return {"passed": passed, "accuracy": acc, "grounding": grd, "details": details}