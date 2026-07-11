#!/usr/bin/env bash
# check_test_dsn.sh — shell-layer safety check for INFOTRIAGE_TEST_DSN.
#
# Refuses to let an operator run `make test-full` (or any pytest run that
# resolves db_live fixtures) with a DSN that targets the production host port
# (22000) or the default Postgres port (5432). Belt-and-suspenders against the
# Pattern documented in HANDOFF/STATE.md: a test fixture that defaults to a
# production DSN will TRUNCATE the live DB on pytest run.
#
# Behavior:
#   * INFOTRIAGE_TEST_DSN unset           -> exit 0 (db_live tests will skip)
#   * DSN does not parse as libpq URI     -> exit 1
#   * DSN host port is 5432 (default)     -> exit 1 (matches test_dsn_safety.py)
#   * DSN host port is 22000 (prod map)   -> exit 1 (matches test_dsn_safety.py)
#   * Any other non-prod port             -> exit 0
#
# Usage:
#   scripts/check_test_dsn.sh               # use current env
#   INFOTRIAGE_TEST_DSN=postgres://... scripts/check_test_dsn.sh
#
# Exit codes:
#   0  safe to run pytest
#   1  ambient DSN would target prod/default-port Postgres; abort

set -euo pipefail

DSN="${INFOTRIAGE_TEST_DSN:-}"
PROD_HOST_PORT=22000
DEFAULT_PG_PORT=5432

red()   { printf '\033[31m%s\033[0m\n' "$1" >&2; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

if [[ -z "$DSN" ]]; then
    green "OK \u2014 INFOTRIAGE_TEST_DSN unset; db_live tests will skip cleanly."
    exit 0
fi

# Validate libpq URI shape (postgres:// or postgresql://, no whitespace).
if ! [[ "$DSN" =~ ^postgres(ql)?:// ]] || [[ "$DSN" =~ [[:space:]] ]]; then
    red "ERROR \u2014 INFOTRIAGE_TEST_DSN is not a libpq URI: $DSN"
    red "  expected form: postgresql://user:password@host:port/db"
    exit 1
fi

# Extract host:port (after the @, before the /db)
HOST_PORT=$(printf '%s' "$DSN" | sed -E 's|^[^@]*@([^/]+)/.*$|\1|')
HOST="${HOST_PORT%:*}"
PORT="${HOST_PORT##*:}"

# If there's no colon, port defaulted -- treat as ephemeral-safe.
if [[ "$HOST" == "$PORT" ]]; then
    green "OK \u2014 INFOTRIAGE_TEST_DSN has no port: $DSN (assumed non-prod)"
    exit 0
fi

if [[ "$PORT" == "$PROD_HOST_PORT" ]]; then
    red "ERROR \u2014 INFOTRIAGE_TEST_DSN points at the production Postgres host port $PROD_HOST_PORT: $DSN"
    red "  pytest would TRUNCATE the live DB on every db_live test."
    red "  Fix: unset the variable OR point at the throwaway test DB on $DEFAULT_PG_PORT or 22062 (see docker-compose.test.yml)."
    exit 1
fi

if [[ "$PORT" == "$DEFAULT_PG_PORT" ]]; then
    red "ERROR \u2014 INFOTRIAGE_TEST_DSN points at the default Postgres port $DEFAULT_PG_PORT: $DSN"
    red "  If this is host-side testing, confirm with operator; the dev Postgres maps host $PROD_HOST_PORT."
    exit 1
fi

green "OK \u2014 INFOTRIAGE_TEST_DSN points at non-prod port ${PORT} (host=${HOST}); db_live tests will run."
exit 0
