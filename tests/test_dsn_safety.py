#!/usr/bin/env python3
"""tests/test_dsn_safety.py — always-run regression guard: no test may target production Postgres.

Phase-6 gap closure: db_live fixtures once carried a hardcoded production DSN
fallback and a hardcoded prod-port reachability probe, so any `pytest` run with
prod reachable TRUNCATEd every infotriage table (the direct cause of "SAB shows
no items"). This guard fails whenever that pattern is reintroduced.

NOT a db_live test — runs on every pytest invocation.
"""
import os
import pathlib
import re

# The host port docker-compose maps the production Postgres to. This number
# appears here ONLY because this guard exists to reject it — no other file
# under tests/ may reference it.
PROD_HOST_PORT = 22000

TESTS_DIR = pathlib.Path(__file__).resolve().parent

# (1) libpq DSN literal targeting the prod host port
_DSN_RE = re.compile(rf"postgresql://[^\s\"']*:{PROD_HOST_PORT}\b")
# (2) socket reachability probe using the prod port literal
_PROBE_RE = re.compile(
    rf"create_connection\(\s*\(\s*['\"][^'\"]+['\"]\s*,\s*{PROD_HOST_PORT}\b"
)


def test_no_test_file_targets_prod_port():
    """No *.py under tests/ (except this guard) may carry a prod-port DSN or socket probe."""
    self_path = pathlib.Path(__file__).resolve()
    offenders = []
    for py in sorted(TESTS_DIR.rglob("*.py")):
        if py.resolve() == self_path:
            continue  # this guard legitimately names the prod port
        text = py.read_text(encoding="utf-8")
        if _DSN_RE.search(text) or _PROBE_RE.search(text):
            offenders.append(str(py.relative_to(TESTS_DIR.parent)))
    assert not offenders, (
        f"Test files target the production Postgres host port {PROD_HOST_PORT}: "
        f"{offenders} — tests must resolve their DSN from INFOTRIAGE_TEST_DSN only."
    )


def test_test_dsn_is_not_prod_port():
    """If INFOTRIAGE_TEST_DSN is set, its port must not be the production host port."""
    dsn = os.environ.get("INFOTRIAGE_TEST_DSN")
    if not dsn:
        return  # nothing to check — db_live tests skip anyway
    import psycopg

    info = psycopg.conninfo.conninfo_to_dict(dsn)
    port = int(info.get("port") or 5432)
    assert port != PROD_HOST_PORT, (
        f"INFOTRIAGE_TEST_DSN points at the production Postgres host port "
        f"{PROD_HOST_PORT} — use an isolated test DB (see docker-compose.test.yml)."
    )
