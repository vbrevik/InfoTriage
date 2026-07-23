#!/usr/bin/env python3
"""Phase 12 sub-wave (a): ntfy container health + ACL smoke tests.

Tests run after `make ntfy-up` returns 0 and assert:
  1. infotriage-ntfy container shows `Up` in `docker ps`.
  2. HTTP GET / on the ntfy base URL is reachable (200 or 401/403 are all
     acceptable as long as the server responded).
  3. POST /<topic> WITHOUT auth MUST return 401/403 (deny-all enforced).
  4. POST with producer creds MUST succeed (write-only ACL).
  5. POST with reader creds MUST be denied (200 GET-only for the reader).
     Pre-flight check for the ADR-015 §Open Items 3 + ADR-017 Decision 1 ACL pattern.

Usage:
    make ntfy-up
    python3 -m pytest tests/test_ntfy_health.py -q
"""
from __future__ import annotations

import base64
import os
import re
import sqlite3
import subprocess
import urllib.error
import urllib.request
from pathlib import Path


NTFY_BASE_URL: str = os.environ.get("NTFY_BASE_URL", "http://127.0.0.1:22070")
NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i") + "-smoke"

# Sealed bind-mount bundle (per ADR-017 addendum, 2026-07-23). Both files MUST be
# populated by `make ntfy-seed` (calls scripts/seed_ntfy_sealed.py) on first install.
SEALED_DIR: Path = Path(__file__).resolve().parent.parent / "configs" / "ntfy-sealed"
AUTH_DB: Path = SEALED_DIR / "auth.db"
SERVER_YML: Path = SEALED_DIR / "server.yml"


def test_ntfy_container_running() -> None:
    """`docker ps` filter on infotriage-ntfy; assert status starts with 'Up'."""
    r = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "name=infotriage-ntfy",
            "--format",
            "{{.Status}}",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert r.returncode == 0, f"`docker ps` failed: {r.stderr!r}"
    assert "Up" in r.stdout, f"infotriage-ntfy not Up; docker ps returned: {r.stdout!r}"


def test_ntfy_root_responds() -> None:
    """GET / on the ntfy base URL is reachable. 200/401/403 all indicate up."""
    req = urllib.request.Request(f"{NTFY_BASE_URL}/")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status in (
        200,
        401,
        403,
    ), f"unexpected ntfy root status: {status} (url={NTFY_BASE_URL}/)"


def test_ntfy_publish_denied_without_auth() -> None:
    """POST /<topic> without auth MUST be denied (deny-all default).

    Confirms the ADR-015 §Open Items 3 ACL pattern is active and a guard
    against an operator accidentally flipping NTFY_AUTH_DEFAULT_ACCESS to
    a permissive value.
    """
    req = urllib.request.Request(
        f"{NTFY_BASE_URL}/{NTFY_TOPIC}",
        data=b"smoke body from Phase 12 sub-wave (a) test",
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        posted = True
        status = 200
    except urllib.error.HTTPError as exc:
        posted = False
        status = exc.code
    assert not posted, (
        f"POST /topic succeeded WITHOUT auth (HTTP {status}); "
        "deny-all is not enforced — investigate immediately."
    )
    assert status in (
        401,
        403,
    ), f"unexpected status (expected 401/403 with deny-all): {status}"


def test_ntfy_publish_with_producer_succeeds() -> None:
    """POST /<topic> WITH valid producer credentials MUST succeed (HTTP 200).

    End-to-end check that the ACL bootstrap (per ADR-017 Decision 1) added
    the producer user with write-only access on `cnr-cat-i*`. The deny-all
    env var is meaningless without this grant; producer is the publish path
    used by sub-wave (c) emitter.
    """
    user = os.environ.get("NTFY_PRODUCER_USER", "producer")
    pw = os.environ.get("NTFY_PRODUCER_PASSWORD", "changeme")
    req = urllib.request.Request(
        f"{NTFY_BASE_URL}/{NTFY_TOPIC}",
        data=b"producer-authenticated-from-host",
        method="POST",
    )
    cred = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    resp = urllib.request.urlopen(req, timeout=5)
    assert resp.status == 200, f"POST with producer-auth failed: HTTP {resp.status}"


def test_ntfy_publish_with_reader_denied() -> None:
    """POST /<topic> WITH valid reader credentials MUST be DENIED.

    Per ADR-017 Decision 1: reader is read-only. Subscriber clients (ntfy web/iOS/Android)
    can GET the topic but cannot POST. Production guard against accidentally granting
    the reader write access.
    """
    user = os.environ.get("NTFY_READER_USER", "reader")
    pw = os.environ.get("NTFY_READER_PASSWORD", "changeme")
    req = urllib.request.Request(
        f"{NTFY_BASE_URL}/{NTFY_TOPIC}",
        data=b"reader-tried-to-write-from-host",
        method="POST",
    )
    cred = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        posted = True
        status = resp.status
    except urllib.error.HTTPError as exc:
        posted = False
        status = exc.code
    assert (
        not posted
    ), f"POST with reader-auth succeeded (HTTP {status}); reader should be read-only"
    assert status in (
        401,
        403,
    ), f"unexpected reader-POST status (expected 401/403): {status}"


def test_sealed_artifacts_present() -> None:
    """configs/ntfy-sealed/{auth.db, server.yml} MUST exist after `make ntfy-seed`.

    Per ADR-017 addendum (2026-07-23), the in-container ACL bootstrap is gone.
    The container relies on a sealed host-side bundle that `make ntfy-seed`
    writes once. This test gates on the static artifact invariants
    (file exists, auth.db is a valid SQLite DB with a `users` table) so a
    fresh operator on-ramp shows actionable failure modes instead of silent
    failures at container startup.
    """
    assert (
        AUTH_DB.exists()
    ), f"{AUTH_DB} missing — run `make ntfy-seed` to populate the sealed bundle"
    assert (
        SERVER_YML.exists()
    ), f"{SERVER_YML} missing — restore from git or re-run `make ntfy-seed -- --force`"
    # Probe auth.db is a valid SQLite DB with the `users` table (ntfy 2.x schema).
    try:
        conn = sqlite3.connect(str(AUTH_DB))
        try:
            # Audit 2026-07-23 finding #8: assert ROWS present, not just
            # schema. An empty `users` table after a mid-failure reseed would
            # otherwise pass this check falsely.
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            assert "users" in {row[0] for row in rows}, (
                f"{AUTH_DB} lacks the ntfy `users` table "
                f"(found tables: {sorted({row[0] for row in rows})!r}); "
                "re-run `make ntfy-seed -- --force`"
            )
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise AssertionError(f"{AUTH_DB} is not a valid SQLite DB: {exc}")
    assert user_count >= 2, (
        f"{AUTH_DB} `users` table has {user_count} rows; expected >=2 "
        "(producer + reader per ADR-017 Decision 1); "
        "re-run `make ntfy-seed -- --force`"
    )


def test_server_yaml_schema_valid() -> None:
    """Sealed server.yml MUST contain required keys per ntfy 2.x config schema.

    Required: base-url, auth-file, auth-default-access, user-db, cache-db.
    auth-default-access MUST be 'deny-all' per ADR-015 §Open Items 3.
    No external deps — uses regex parse (project rule: keep test deps minimal).
    """
    text = SERVER_YML.read_text(encoding="utf-8")
    required_keys = [
        "base-url:",
        "auth-file:",
        "auth-default-access:",
        "user-db:",
        "cache-db:",
    ]
    missing = [
        k
        for k in required_keys
        if not re.search(rf"^\s*{re.escape(k)}", text, re.MULTILINE)
    ]
    assert not missing, (
        f"{SERVER_YML} is missing required keys: {missing}; "
        "restore from git or amend after operator pre-review"
    )
    match = re.search(
        r'^\s*auth-default-access:\s*"?([^"\s]+)"?\s*$', text, re.MULTILINE
    )
    assert match, f"{SERVER_YML} could not parse auth-default-access value"
    assert match.group(1) == "deny-all", (
        f"auth-default-access MUST be 'deny-all' per ADR-015 §Open Items 3; "
        f"got {match.group(1)!r}. This guard against an operator accidentally "
        "reverting the deny-all default."
    )


if __name__ == "__main__":
    test_ntfy_container_running()
    test_ntfy_root_responds()
    test_ntfy_publish_denied_without_auth()
    test_ntfy_publish_with_producer_succeeds()
    test_ntfy_publish_with_reader_denied()
    test_sealed_artifacts_present()
    test_server_yaml_schema_valid()
    print("tests/test_ntfy_health.py — PASS")
