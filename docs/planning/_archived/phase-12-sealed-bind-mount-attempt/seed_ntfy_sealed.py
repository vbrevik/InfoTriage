#!/usr/bin/env python3
"""One-time sealed ntfy ACL bootstrap runner (Phase 12 sub-wave (a)).

Replaces the in-container shell-script bootstrap that lived inside
`docker-compose.yml`'s `command:` field — that pattern hit 9+ iterations of
fragility (entrypoint escaping, sentinel-pattern booleans, awk/grep output-
format coupling). This script runs ONCE on the host to produce a sealed
`configs/ntfy-sealed/{server.yml, auth.db}` pair that we then bind-mount
`:ro` into the ntfy container.

Per ADR-017 (Phase 12 sub-wave (a) ACL amendments):
  - Decision 1: split producer (write-only) + reader (read-only) users.
  - Decision 3: dev-only log-warn on `changeme` default, NO fail-fast.
  - Decision 4 (now moot): unless-stopped restart, but no boot-time
    bootstrap failures to retry because there is no boot-time bootstrap.

Per ADR-016 (airgap): no outbound; everything happens via the ntfy CLI
running in an ephemeral docker container. ntfy handles bcrypt hashing
internally — we never store plaintext passwords anywhere.

Usage:
    python3 scripts/seed_ntfy_sealed.py         # idempotent; skip if up-to-date
    python3 scripts/seed_ntfy_sealed.py --force # wipe + reseed auth.db
    make ntfy-seed                              # operator-facing entry point
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEALED_DIR = ROOT / "configs" / "ntfy-sealed"
AUTH_DB = SEALED_DIR / "auth.db"
SERVER_YML = SEALED_DIR / "server.yml"
NTFY_IMAGE = os.environ.get("NTFY_IMAGE", "binwiederhier/ntfy:latest")
TOPIC_PREFIX = os.environ.get("NTFY_TOPIC_PREFIX", "cnr-cat-i")

# Per ADR-017 Decision 3 — sentinel for "operator didn't override `.env`".
# `ntfy user add --password` is hit on every docker-run call; we only WARN on
# these (no fail-fast, per Decision 3).
DEFAULT_PASSWORD = "changeme"  # noqa: S105 — intentional dev-default sentinel

# CRITICAL (code-review audit 2026-07-23, finding #2): the prev version's
# `_env_or_default(...) or "producer"` short-circuit always swallowed the
# `"producer"` fallback because `_env_or_default` returns `"changeme"` truthy
# on missing env. The fix: separate helpers with the right fallback values.
DEFAULT_PRODUCER_USER = "producer"
DEFAULT_READER_USER = "reader"

OK = 0
STATE_UNCHANGED = 5  # distinct from OK=0; monitors can grep STATE_UNCHANGED events
EXIT_BAD_INVOCATION = 2
EXIT_SEED_FAILED = 3
EXIT_BAD_DB = 4

_DEFAULT_WARN = (
    "[seed] WARNING: {} is dev-default '{}'; override in .env for production "
    "(per ADR-017 Decision 3 - log-warn only, NO fail-fast). "
    "Production gate: commit-time secret scanner (a future ADR)."
)


def _get_username(env_key: str, fallback: str) -> str:
    """Return env value when set and non-empty; otherwise the literal fallback.

    Distinct from passwords: usernames have a stable default like 'producer'
    or 'reader'. We never fall through to a password sentinel for usernames.
    """
    val = os.environ.get(env_key, "").strip()
    return val if val else fallback


def _get_password(env_key: str) -> str:
    """Return env value when set and non-empty; otherwise the dev sentinel.

    Distinct from usernames: passwords default to a sentinelled placeholder
    so ADR-017 Decision 3 (log-warn on dev-default) has a stable target.
    """
    val = os.environ.get(env_key, "").strip()
    return val if val else DEFAULT_PASSWORD


def _devwarn(name: str, value: str) -> None:
    """Per ADR-017 Decision 3 - log-warn on dev-default `changeme` passwords."""
    if value == DEFAULT_PASSWORD:
        print(_DEFAULT_WARN.format(name, DEFAULT_PASSWORD), file=sys.stderr)


def _invoke_ntfy(
    args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run `ntfy <args>` in an ephemeral container with the sealed dir mounted.

    Absolute path matters: docker resolves relative binds against the daemon's
    CWD, which is not our project root. We use `os.getcwd()` because the
    operator always invokes through `make ntfy-seed` from project root.

    CRITICAL (audit finding #1): every caller MUST pass `--auth-file
    /work/auth.db` if the operation touches the auth db. The probe in
    `_sealed_already_valid()` MUST also include it - otherwise the probe
    runs against ntfy's empty default auth-db path inside the ephemeral
    container and silently returns exit 0 on an unpopulated host-side
    sealed/auth.db.
    """
    bind = f"{os.getcwd()}/configs/ntfy-sealed:/work:rw"
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        bind,
        NTFY_IMAGE,
        "ntfy",
        *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _sealed_already_valid(producer_user: str, reader_user: str) -> bool:
    """Skip rebuild iff auth.db exists + is a valid SQLite db + has BOTH users.

    Code-review audit (2026-07-23) flagged the prior version's hollow probe:
    it called `ntfy user list` WITHOUT `--auth-file`, so it was running
    against the ephemeral container's empty default auth-db path. The fix:
    probe with the explicit `--auth-file /work/auth.db` who is the mount
    point for the sealed bundle.

    Per audit finding #4: a freshly-bcrypt-seeded auth.db with two users is
    far under 1024 bytes, so the prior `st_size < 1024` check was both wrong
    AND non-load-bearing (the probe was the real gate). We drop the size
    heuristic entirely; the SQLite probe via `ntfy user list --json` is
    authoritative.
    """
    if not AUTH_DB.exists() or AUTH_DB.stat().st_size == 0:
        return False
    list_result = _invoke_ntfy(
        ["user", "list", "--auth-file", "/work/auth.db", "--json"],
        check=False,
    )
    if list_result.returncode != 0:
        return False
    stdout = list_result.stdout or ""
    return producer_user in stdout and reader_user in stdout


def _ensure_sealed_dir() -> None:
    SEALED_DIR.mkdir(parents=True, exist_ok=True)
    if not (SEALED_DIR / ".gitkeep").exists():
        (SEALED_DIR / ".gitkeep").write_text(
            "# See scripts/seed_ntfy_sealed.py - sealed ACL bundle lives here.\n",
            encoding="utf-8",
        )
    # Defensive: never accidentally clobber server.yml with empty content.
    if not SERVER_YML.exists():
        src = ROOT / "configs" / "ntfy-sealed" / "server.yml"
        if src.exists() and src != SERVER_YML:
            shutil.copy(src, SERVER_YML)
        else:
            print(
                f"[seed] FATAL: {SERVER_YML} is missing; restore from git or "
                "rerun `git checkout configs/ntfy-sealed/server.yml`."
                " Recovery: re-run the same command (idempotent for the seeded user).",
                file=sys.stderr,
            )
            sys.exit(EXIT_BAD_INVOCATION)


def _wipe_auth_db() -> None:
    if AUTH_DB.exists():
        AUTH_DB.unlink()
        print(f"[seed] wiped {AUTH_DB}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="wipe auth.db and reseed from scratch (drops existing users)",
    )
    args = parser.parse_args()

    producer_user = _get_username("NTFY_PRODUCER_USER", DEFAULT_PRODUCER_USER)
    producer_pw = _get_password("NTFY_PRODUCER_PASSWORD")
    reader_user = _get_username("NTFY_READER_USER", DEFAULT_READER_USER)
    reader_pw = _get_password("NTFY_READER_PASSWORD")

    _devwarn("NTFY_PRODUCER_PASSWORD", producer_pw)
    _devwarn("NTFY_READER_PASSWORD", reader_pw)

    _ensure_sealed_dir()

    if not args.force and _sealed_already_valid(producer_user, reader_user):
        print(
            f"[seed] STATE_UNCHANGED: {AUTH_DB} already valid (>=2 users found: "
            f"{producer_user!r}, {reader_user!r}); skipping rebuild "
            "(use --force to wipe and reseed). Exits with STATE_UNCHANGED exit code (5).",
            file=sys.stderr,
        )
        return STATE_UNCHANGED

    if args.force:
        _wipe_auth_db()

    # Build the per-call arg lists. ntfy CLI accepts --user, --password per call.
    seeds: list[list[str]] = [
        [
            "user",
            "add",
            "--auth-file",
            "/work/auth.db",
            "--user",
            producer_user,
            "--password",
            producer_pw,
            "--role",
            "user",
        ],
        [
            "user",
            "add",
            "--auth-file",
            "/work/auth.db",
            "--user",
            reader_user,
            "--password",
            reader_pw,
            "--role",
            "user",
        ],
        [
            "access",
            "--auth-file",
            "/work/auth.db",
            f"{TOPIC_PREFIX}*",
            "everyone",
            "deny-all",
        ],
        [
            "access",
            "--auth-file",
            "/work/auth.db",
            f"{TOPIC_PREFIX}*",
            producer_user,
            "write-only",
        ],
        [
            "access",
            "--auth-file",
            "/work/auth.db",
            f"{TOPIC_PREFIX}*",
            reader_user,
            "read-only",
        ],
    ]
    for seed in seeds:
        r = _invoke_ntfy(seed, check=False)
        # ntfy user add returns 0 (created) or 1 (already exists). Tolerate 1
        # as idempotent; anything else propagates noise and we keep going -
        # the post-condition probe below is the real gate.
        if r.returncode not in (0, 1):
            print(
                f"[seed] WARN: ntfy {' '.join(seed[:3])} exited "
                f"{r.returncode}: {r.stderr.strip()}"
            )

    # Post-condition probe: list users via the sealed auth.db path with the
    # explicit flag. If we don't see both producer AND reader in the JSON
    # output, fail loudly.
    list_result = _invoke_ntfy(
        ["user", "list", "--auth-file", "/work/auth.db", "--json"],
        check=False,
    )
    stdout = list_result.stdout or ""
    if producer_user not in stdout or reader_user not in stdout:
        print(
            f"[seed] FATAL: post-condition failed - "
            f"producer={producer_user!r} or reader={reader_user!r} not in auth.db.\n"
            f"  ntfy user list stdout: {stdout!r}\n"
            f"  ntfy user list stderr: {list_result.stderr!r}\n"
            "  Inspect: docker run --rm -v $PWD/configs/ntfy-sealed:/work:rw "
            f"{NTFY_IMAGE} ntfy user list --auth-file /work/auth.db"
            "\n"
            "  Recovery: re-run the same command (idempotent for the seeded user).",
            file=sys.stderr,
        )
        return EXIT_SEED_FAILED

    print(
        f"[seed] OK: {AUTH_DB} populated with producer (write-only) + "
        f"reader (read-only) on {TOPIC_PREFIX}*. Container start will use "
        "the sealed bind-mount - no in-container bootstrap needed."
    )
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
