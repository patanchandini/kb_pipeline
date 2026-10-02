import time, uuid, logging
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from kb import metrics as M
from kb.index import search
from kb.security import require_role, scan_injection
from kb.masking import mask, mask_hits
from kb.versions import get_active_version
from kb.activation import scheduled_activation_job, try_activate
from kb.ingest import run_ingest

log = logging.getLogger("runtime")
app = FastAPI(title="KB Pipeline")

class ChatIn(BaseModel):
    message: str
    user_id: str | None = None

@app.on_event("startup")
def _startup():
    M.serve_metrics()
    M.KB_VERSION.set(get_active_version())

@app.get("/healthz")
def healthz():
    return {"ok": True, "version": get_active_version()}

@app.post("/chat")
def chat(body: ChatIn):
    t0 = time.time()
    try:
        unsafe, pat = scan_injection(body.message)
        if unsafe:
            M.INJECTION_BLOCKED.inc()
            M.FAILURES.labels("injection").inc()
            raise HTTPException(status_code=400, detail="unsafe_input")

        results = search(body.message, top_k=3)
        if not results:
            M.ESCALATIONS.inc()
            return {"answer": "I don't know.", "confidence": 0.0, "escalated": True}

        top_score = results[0][0]
        raw_answer = " ".join(r[1] for r in results[:2])[:800]
        safe_answer = mask(raw_answer)
        masked_n = mask_hits(raw_answer)
        if masked_n: M.MASKED.inc(masked_n)

        if top_score < 0.15:
            M.ESCALATIONS.inc()
            escalated = True
        else:
            escalated = False

        M.CONFIDENCE.observe(top_score)
        M.REQUESTS.labels("chat", "ok").inc()
        return {"answer": safe_answer, "confidence": round(top_score, 3), "escalated": escalated}
    except HTTPException:
        M.REQUESTS.labels("chat", "rejected").inc()
        raise
    except Exception as e:
        M.FAILURES.labels("chat").inc()
        log.exception("chat failed: %s", e)
        raise HTTPException(status_code=500, detail="internal_error")
    finally:
        M.LATENCY.labels("chat").observe(time.time() - t0)

# --- Admin endpoints (role-gated) ---

@app.post("/admin/ingest")
@require_role("editor")
def admin_ingest(x_api_key: str = Header(None)):
    return run_ingest(actor="editor")

@app.post("/admin/activate")
@require_role("admin")
def admin_activate(x_api_key: str = Header(None)):
    return scheduled_activation_job()

@app.post("/admin/rollback/{version}")
@require_role("admin")
def admin_rollback(version: int, x_api_key: str = Header(None)):
    from kb.versions import rollback_to
    rollback_to(version)
    M.KB_VERSION.set(version)
    return {"rolled_back_to": version}