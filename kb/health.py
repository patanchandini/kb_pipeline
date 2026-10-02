import time, logging
from kb.index import search
from kb.storage import connect

log = logging.getLogger("health")

def _probe_retrieval():
    try:
        r = search("health probe", top_k=1)
        return True
    except Exception as e:
        log.error("Retrieval probe failed: %s", e)
        return False

def _probe_db():
    try:
        with connect() as c:
            c.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False

def health_check(version, window_seconds=300, interval=10):
    """Run health checks for window_seconds. Return True if all pass."""
    deadline = time.time() + window_seconds
    while time.time() < deadline:
        if not (_probe_db() and _probe_retrieval()):
            return False
        time.sleep(interval)
    return True