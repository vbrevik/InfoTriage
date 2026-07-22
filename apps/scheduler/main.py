"""
main.py — InfoTriage scheduler entrypoint.

Builds and starts the APScheduler BackgroundScheduler, then blocks
until interrupted. Graceful shutdown on KeyboardInterrupt or SystemExit.
"""

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from contracts import setup_logging
from scheduler_main import build_scheduler

setup_logging("scheduler")
log = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint for Docker; returns 200 OK on /health."""

    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format: str, *args) -> None:  # noqa: D401
        # Suppress default HTTP request logging to avoid console noise.
        pass


def _start_health_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    try:
        server = HTTPServer((host, port), _HealthHandler)
        server.serve_forever()
    except Exception as exc:
        log.error("Scheduler health server failed: %s", exc)


def main() -> None:
    threading.Thread(target=_start_health_server, daemon=True).start()
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
