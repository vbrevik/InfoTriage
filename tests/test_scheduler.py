"""
tests/test_scheduler.py — R5: scheduler fires adapters; 409 logged as 'skipped'.

APScheduler 3.x + sync httpx pattern verified here.
"""
import logging
import pathlib
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import smoke: verify APScheduler 3.x import path (not 4.x)
# ---------------------------------------------------------------------------

def test_apscheduler_3x_import():
    """Regression: ensure we use 3.x BackgroundScheduler, not 4.x Scheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler  # noqa: F401
    from apscheduler.triggers.cron import CronTrigger  # noqa: F401


# ---------------------------------------------------------------------------
# fire_adapter behaviour
# ---------------------------------------------------------------------------

def _make_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def _make_mock_client(post_side_effect=None, post_return=None):
    """Build a mock httpx.Client context manager."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    if post_side_effect is not None:
        mock_client.post.side_effect = post_side_effect
    elif post_return is not None:
        mock_client.post.return_value = post_return
    return mock_client


def test_fire_adapter_200_logs_started(caplog):
    """A 200 response must be logged as '[name] started (200)'."""
    import scheduler_main

    with caplog.at_level(logging.INFO, logger="scheduler_main"):
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value = _make_mock_client(post_return=_make_response(200))
            scheduler_main.fire_adapter("ingest-imap", "http://ingest-imap:8000/run")

    assert any("started" in r.message for r in caplog.records), (
        f"Expected 'started' in logs; got: {[r.message for r in caplog.records]}"
    )


def test_fire_adapter_409_logs_skipped(caplog):
    """A 409 response must be logged as '[name] skipped — already running (409)'."""
    import scheduler_main

    with caplog.at_level(logging.INFO, logger="scheduler_main"):
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value = _make_mock_client(post_return=_make_response(409))
            scheduler_main.fire_adapter("ingest-imap", "http://ingest-imap:8000/run")

    assert any("skipped" in r.message for r in caplog.records), (
        f"Expected 'skipped' in logs; got: {[r.message for r in caplog.records]}"
    )


def test_fire_adapter_200_then_409_sequence(caplog):
    """First call 200→'started', second call 409→'skipped': simulate overlapping run."""
    import scheduler_main

    responses = [_make_response(200), _make_response(409)]
    call_count = 0

    def fake_post(url, **kwargs):
        nonlocal call_count
        resp = responses[call_count]
        call_count += 1
        return resp

    with caplog.at_level(logging.INFO, logger="scheduler_main"):
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value = _make_mock_client(post_side_effect=fake_post)
            scheduler_main.fire_adapter("ingest-imap", "http://ingest-imap:8000/run")
            scheduler_main.fire_adapter("ingest-imap", "http://ingest-imap:8000/run")

    messages = [r.message for r in caplog.records]
    started = [m for m in messages if "started" in m]
    skipped = [m for m in messages if "skipped" in m]
    assert len(started) == 1, f"Expected 1 'started' log, got {started}"
    assert len(skipped) == 1, f"Expected 1 'skipped' log, got {skipped}"


def test_fire_adapter_connection_error_does_not_raise(caplog):
    """A connection error must be caught and logged — never raised out of the job."""
    import httpx
    import scheduler_main

    with caplog.at_level(logging.ERROR, logger="scheduler_main"):
        with patch("httpx.Client") as mock_cls:
            mock_cls.return_value = _make_mock_client(
                post_side_effect=httpx.ConnectError("refused")
            )
            # Must NOT raise
            scheduler_main.fire_adapter("ingest-imap", "http://ingest-imap:8000/run")

    assert any(
        "error" in r.message.lower() or "connection" in r.message.lower()
        for r in caplog.records
    ), f"Expected connection error log; got: {[r.message for r in caplog.records]}"


def test_no_async_client_in_scheduler_main():
    """Regression: AsyncClient MUST NOT appear in scheduler_main (APScheduler 3.x jobs are threaded)."""
    src = pathlib.Path("apps/scheduler/scheduler_main.py").read_text()
    assert "AsyncClient" not in src, (
        "scheduler_main.py must use httpx.Client (sync) — APScheduler 3.x jobs run in threads"
    )


def test_no_apscheduler4x_api_in_scheduler_main():
    """Regression: 4.x import 'from apscheduler import Scheduler' must not appear."""
    src = pathlib.Path("apps/scheduler/scheduler_main.py").read_text()
    assert "from apscheduler import Scheduler" not in src, (
        "Forbidden: 4.x APScheduler API detected in scheduler_main.py"
    )


def test_schedule_env_vars_referenced():
    """scheduler_main must reference all four SCHEDULE_* env vars."""
    src = pathlib.Path("apps/scheduler/scheduler_main.py").read_text()
    for var in ("SCHEDULE_IMAP", "SCHEDULE_YOUTUBE", "SCHEDULE_GMAIL", "SCHEDULE_OBSIDIAN"):
        assert var in src, f"scheduler_main.py is missing env var reference: {var}"


def test_adapter_urls_use_internal_port():
    """All adapter URLs must use service name + internal port 8000 (not 2201x)."""
    src = pathlib.Path("apps/scheduler/scheduler_main.py").read_text()
    for name in ("ingest-imap", "ingest-youtube", "ingest-gmail", "ingest-obsidian"):
        assert f"http://{name}:8000/run" in src, (
            f"scheduler_main.py missing internal URL for {name}"
        )
