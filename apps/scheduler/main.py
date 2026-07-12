"""
main.py — InfoTriage scheduler entrypoint.

Builds and starts the APScheduler BackgroundScheduler, then blocks
until interrupted. Graceful shutdown on KeyboardInterrupt or SystemExit.
"""

import logging
import time

from contracts import setup_logging
from scheduler_main import build_scheduler

setup_logging("scheduler")
log = logging.getLogger(__name__)


def main() -> None:
    scheduler = build_scheduler()
    scheduler.start()
    log.info("InfoTriage scheduler started — firing adapters on schedule.")
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        log.info("Shutting down scheduler...")
        scheduler.shutdown()
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
