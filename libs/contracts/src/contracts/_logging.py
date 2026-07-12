"""_logging.py — shared structured JSON logging for InfoTriage services.

Configures a root logger that emits JSON to stdout and, when writable, to a
rotating file under ``/data/logs/<service>.log``.  The file rotates daily and
keeps 7 days of backups.

Usage:
    from contracts import setup_logging

    setup_logging("brief")
    import logging
    log = logging.getLogger(__name__)
    log.info("brief consumer started")

Environment:
    LOG_LEVEL  — DEBUG/INFO/WARNING/ERROR/CRITICAL (default INFO)
"""

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path

try:
    from json_log_formatter import JSONFormatter
except Exception:  # pragma: no cover - fallback if package missing
    JSONFormatter = None

__all__ = ["setup_logging"]

# Guard against installing handlers multiple times (e.g., tests importing many modules)
_LOGGING_CONFIGURED = False


class _PlainJSONFormatter(logging.Formatter):
    """Fallback JSON formatter when json-log-formatter is not installed."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}
        return json.dumps(payload, default=str)


def _writable_log_dir(preferred: Path) -> Path:
    """Return a writable log directory, falling back to a temp dir if needed."""
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        # Test writability
        test_file = preferred / ".write_test"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return preferred
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "infotriage-logs"
        fallback.mkdir(parents=True, exist_ok=True)
        # Emit the warning to stderr before the real logger is configured
        print(
            f"WARNING: Log directory {preferred} is not writable; falling back to {fallback}",
            file=sys.stderr,
        )
        return fallback


def setup_logging(service_name: str) -> None:
    """Configure JSON logging to stdout and a daily-rotating file.

    The log file lands at ``/data/logs/<service>.log`` (overridable via
    ``INFOTRIAGE_LOG_DIR``).  Daily rotation keeps 7 backups.

    This function is idempotent: repeated calls are no-ops.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    preferred_dir = Path(os.environ.get("INFOTRIAGE_LOG_DIR", "/data/logs"))
    log_dir = _writable_log_dir(preferred_dir)

    if JSONFormatter is not None:
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = _PlainJSONFormatter()

    handlers: list[logging.Handler] = []

    # stdout handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    # daily rotating file handler (only if log dir is writable)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / f"{service_name}.log",
        when="midnight",
        backupCount=7,
        utc=True,
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    # Avoid duplicate handlers if setup_logging is called more than once
    if root.handlers:
        root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)

    _LOGGING_CONFIGURED = True
