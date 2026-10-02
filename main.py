import os
import threading
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from kb.logging_setup import setup_logging
from kb.config import CFG
from kb.storage import init_db
from kb.scheduler import retry_loop


setup_logging()
log = logging.getLogger("main")


def main():
    init_db()
    stop = threading.Event()

    # Retry worker thread (15/30/60-min retries)
    threading.Thread(target=retry_loop, args=(stop,), daemon=True).start()

    # Daily staging + activation cron
    from kb.activation import scheduled_activation_job
    minute, hour = CFG.schedule.daily_update_cron.split()[:2]
    sched = BackgroundScheduler()
    sched.add_job(scheduled_activation_job, CronTrigger(minute=minute, hour=hour))
    sched.start()
    log.info("Scheduler started (cron=%s)", CFG.schedule.daily_update_cron)

    # Uvicorn — read PORT from env (Render sets this dynamically)
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    log.info("Starting Uvicorn on port %d", port)
    try:
        uvicorn.run("kb.runtime:app", host="0.0.0.0", port=port, reload=False)
    finally:
        stop.set()
        sched.shutdown(wait=False)


if __name__ == "__main__":
    main()