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
  6. `ntfy user list` inside the container reports BOTH producer + reader —
     behavioral check that the ADR-018 pre-baked auth.db actually made it into
     the running image (works against any build substrate that places a
     populated auth.db at /etc/ntfy/auth.db).

Usage:
    make ntfy-up
    python3 -m pytest tests/test_ntfy_health.py -q
"""
from __future__ import annotations

import base64
import os
import subprocess
import urllib.error
import urllib.request


NTFY_BASE_URL: str = os.environ.get("NTFY_BASE_URL", "http://127.0.0.1:22070")
NTFY_TOPIC: str = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i") + "-smoke"


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


def test_ntfy_prebaked_users_via_docker_exec() -> None:
    """`ntfy user list` inside the container MUST report producer + reader.

    Per ADR-018 (Dockerfile pre-bake): the bcrypt-only auth.db is baked into
    the image at build time via BuildKit secrets. This is a behavioral check
    against the RUNNING container, so it holds for any substrate that places a
    populated auth.db at /etc/ntfy/auth.db (it also passed under the archived
    sealed-bind-mount attempt).
    """
    r = subprocess.run(
        [
            "docker",
            "exec",
            "infotriage-ntfy",
            "ntfy",
            "user",
            "list",
            "--auth-file",
            "/etc/ntfy/auth.db",
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    # ntfy prints the user list to stderr in some versions; check both streams.
    out = r.stdout + r.stderr
    assert r.returncode == 0, f"`ntfy user list` failed inside container: {out!r}"
    assert "producer" in out, (
        f"pre-baked auth.db lacks `producer` user — re-run `make ntfy-build` "
        f"(ntfy user list output: {out!r})"
    )
    assert "reader" in out, (
        f"pre-baked auth.db lacks `reader` user — re-run `make ntfy-build` "
        f"(ntfy user list output: {out!r})"
    )


if __name__ == "__main__":
    test_ntfy_container_running()
    test_ntfy_root_responds()
    test_ntfy_publish_denied_without_auth()
    test_ntfy_publish_with_producer_succeeds()
    test_ntfy_publish_with_reader_denied()
    test_ntfy_prebaked_users_via_docker_exec()
    print("tests/test_ntfy_health.py — PASS")
