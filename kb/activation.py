import logging
from kb.config import CFG
from kb.storage import audit
from kb.versions import create_snapshot, set_version_status, rollback_to, get_active_version
from kb.quality import run_quality_tests
from kb.health import health_check
from kb.scheduler import in_maintenance_window, enqueue_retry

log = logging.getLogger("activation")

def build_and_stage(actor="system"):
    """Run quality tests on staging; approve → staging version ready for activation."""
    q = run_quality_tests()
    if not q["passed"]:
        audit(actor, "quality_reject", q)
        return {"staged": False, "reason": "quality_gate_failed", "quality": q}
    version = create_snapshot("staged by " + actor)
    audit(actor, "stage_ok", {"version": version, "quality": q})
    return {"staged": True, "version": version, "quality": q}

def try_activate(version=None, actor="system"):
    """Activate a staged version. Enforces maintenance window + health check."""
    if not in_maintenance_window():
        log.info("Outside maintenance window — deferring activation")
        audit(actor, "activation_deferred", {"version": version})
        return {"activated": False, "reason": "outside_maintenance_window"}

    prev = get_active_version()
    if version is None:
        # pick latest staging
        from kb.storage import connect
        with connect() as c:
            r = c.execute("SELECT MAX(version) v FROM versions WHERE status='staging'").fetchone()
            version = r["v"] if r else None
    if version is None:
        return {"activated": False, "reason": "no_staged_version"}

    set_version_status(version, "activating")
    audit(actor, "activation_begin", {"version": version, "prev": prev})

    ok = health_check(version, window_seconds=CFG.activation.health_check_seconds)
    if not ok:
        log.error("Health check failed for v%s", version)
        audit(actor, "health_check_failed", {"version": version})
        if CFG.activation.auto_rollback and prev:
            rollback_to(prev)
            set_version_status(version, "rolled_back", "auto rollback on health fail")
            return {"activated": False, "reason": "health_check_failed", "rolled_back_to": prev}
        return {"activated": False, "reason": "health_check_failed"}

    set_version_status(version, "active")
    audit(actor, "activation_ok", {"version": version})
    return {"activated": True, "version": version}

def scheduled_activation_job():
    """Called from cron. Stages if needed, then tries to activate inside window.
    On failure, enqueues retries at 15/30/60 minutes."""
    staged = build_and_stage()
    if not staged["staged"]:
        return staged
    res = try_activate(version=staged["version"])
    if not res.get("activated"):
        enqueue_retry("activate", {"version": staged["version"]})
    return res