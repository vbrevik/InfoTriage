#!/usr/bin/env python3
"""tests/test_alerting_auth.py — SPEC R6 bearer-token ACL matrix, proven live.

Skips cleanly (module-wide) when the ntfy port is not reachable, following the
same reachability-probe convention as tests/conftest.py's `_test_db_reachable`
(TCP connect within 1s). Cases:
  - unauthenticated publish to the primary topic -> 403
  - publish with a deliberately wrong bearer token -> 401 or 403
  - publish with the real token (read from NTFY_TOKEN env only) -> 200
  - unauthenticated read of the primary topic's json stream -> 403

The real token is read from the environment only — never embedded in this
file. If NTFY_TOKEN is unset, that one case skips with a clear message
instead of failing or hardcoding a credential.

Usage:
    make -f ops/Makefile ntfy-up
    make -f ops/Makefile ntfy-token   # copy the printed value into .env as NTFY_TOKEN
    python -m pytest tests/test_alerting_auth.py -q
"""
from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

import pytest

NTFY_BASE_URL: str = os.environ.get("NTFY_BASE_URL", "http://127.0.0.1:22070")
NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i")


def _ntfy_reachable() -> bool:
    """Return True if the ntfy port accepts a TCP connection within 1s."""
    parsed = urlparse(NTFY_BASE_URL)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _ntfy_reachable(),
    reason=f"ntfy not reachable at {NTFY_BASE_URL} — run `make -f ops/Makefile ntfy-up` first",
)


def _post(*, token: str | None = None, body: bytes = b"test_alerting_auth") -> int:
    """POST to the primary topic; return the HTTP status code."""
    req = urllib.request.Request(
        f"{NTFY_BASE_URL}/{NTFY_TOPIC}", data=body, method="POST"
    )
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _get(*, token: str | None = None) -> int:
    """GET the primary topic's json stream (poll=1, no hang); return the HTTP status code."""
    req = urllib.request.Request(f"{NTFY_BASE_URL}/{NTFY_TOPIC}/json?poll=1")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_unauthenticated_publish_denied() -> None:
    """POST to the primary topic with no Authorization header MUST return 403 (SPEC R6)."""
    status = _post()
    assert status == 403, f"unauthenticated publish returned {status}, expected 403"


def test_wrong_bearer_token_denied() -> None:
    """POST with a deliberately wrong bearer token MUST be denied (401 or 403)."""
    status = _post(token="tk_wrong0000000000000000000000")
    assert status in (
        401,
        403,
    ), f"wrong-token publish returned {status}, expected 401 or 403"


def test_real_bearer_token_accepted() -> None:
    """POST with the real token (read from NTFY_TOKEN env only) MUST return 200 (SPEC R6)."""
    token = os.environ.get("NTFY_TOKEN", "").strip()
    if not token:
        pytest.skip(
            "NTFY_TOKEN not set in the environment — run "
            "`make -f ops/Makefile ntfy-token` and copy the value into .env"
        )
    status = _post(token=token)
    assert status == 200, f"authenticated publish returned {status}, expected 200"


def test_unauthenticated_read_denied() -> None:
    """GET the primary topic's json stream with no Authorization header MUST return 403 (SPEC R6)."""
    status = _get()
    assert status == 403, f"unauthenticated read returned {status}, expected 403"
