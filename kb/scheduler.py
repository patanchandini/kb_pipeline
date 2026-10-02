import time, json, threading, logging
from datetime import datetime, timedelta
from kb.config import CFG
from kb.storage import connect, audit

log = logging.getLogger("scheduler")

def enqueue_retry(job, payload=None):
    next_ts = time.time() + CFG.retry.delays_minutes[0] * 60
    with connect() as c:
        c.execute("INSERT INTO retries(job,payload,attempt,next_run) VALUES(?,?,?,?)",
                  (job, json.dumps(payload or {}), 0, next_ts))
    log.info("Enqueued retry for %s at +%dmin", job, CFG.retry.delays_minutes[0])

def _process_retry(row):
    delays = CFG.retry.delays_minutes
    attempt = row["attempt"] + 1
    payload = json.loads(row["payload"] or "{}")
    try:
        from kb.activation import try_activate
        result = try_activate(**payload)
        if result.get("activated"):
            with connect() as c:
                c.execute("UPDATE retries SET status='done' WHERE id=?", (row["id"],))
            return True
    except Exception as e:
        log.exception("Retry job failed: %s", e)

    if attempt >= len(delays):
        with connect() as c:
            c.execute("UPDATE retries SET status='failed' WHERE id=?", (row["id"],))
        audit("system", "retry_exhausted", {"job": row["job"]})
        return False

    next_delay = delays[attempt] - delays[attempt - 1] if attempt < len(delays) else delays[-1]
    with connect() as c:
        c.execute("UPDATE retries SET attempt=?, next_run=? WHERE id=?",
                  (attempt, time.time() + next_delay * 60, row["id"]))
    log.info("Retry #%d scheduled in %d min", attempt, next_delay)
    return False

def retry_loop(stop_event: threading.Event):
    log.info("Retry loop started")
    while not stop_event.is_set():
        now = time.time()
        with connect() as c:
            due = list(c.execute("SELECT * FROM retries WHERE status='pending' AND next_run<=?", (now,)))
        for row in due:
            _process_retry(row)
        stop_event.wait(20)

def in_maintenance_window(now=None) -> bool:
    now = now or datetime.utcnow()
    start_s, end_s = CFG.schedule.maintenance_window.split("-")
    sh, sm = map(int, start_s.split(":"))
    eh, em = map(int, end_s.split(":"))
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= now <= end