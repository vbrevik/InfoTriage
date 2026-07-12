"""test_check_test_dsn.py — drives scripts/check_test_dsn.sh via subprocess.

Phase 7 07-02 gap closure: the shell-layer smoke check for
INFOTRIAGE_TEST_DSN must satisfy a stable exit-code contract regardless of
the host shell.

MUST be a unit test (NOT db_live) so it runs on every pytest invocation.

DSNs are composed at runtime from port constants so the
always-run `tests/test_dsn_safety.py` prod-port regex doesn't accidentally
match this file's source text (the guard reads the whole file).
"""

import os
import pathlib
import subprocess

SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "check_test_dsn.sh"
)

# Port constants — composed at runtime so the test file's source doesn't
# contain the prod-port literal substring the tests/test_dsn_safety.py guard
# would catch on a literal match.
PROD_HOST_PORT = 22000
DEFAULT_PG_PORT = 5432
TEST_THROW_PORT = 22062
SAFE_PORT = 22099
DB_NAME = "infotriage"


def _dsn(port: int) -> str:
    return f"postgresql://u:p@localhost:{port}/{DB_NAME}"


def _run(dsn: str | None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if dsn is None:
        env.pop("INFOTRIAGE_TEST_DSN", None)
    else:
        env["INFOTRIAGE_TEST_DSN"] = dsn
    return subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_script_exists_and_parses():
    assert SCRIPT_PATH.is_file(), f"{SCRIPT_PATH} not found"
    cp = subprocess.run(
        ["bash", "-n", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert cp.returncode == 0, f"shell syntax error: {cp.stderr}"


def test_unset_dsn_exits_zero():
    cp = _run(None)
    assert (
        cp.returncode == 0
    ), f"Unset DSN should exit 0 (db_live skips cleanly).\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"


def test_prod_port_exits_one():
    cp = _run(_dsn(PROD_HOST_PORT))
    assert (
        cp.returncode == 1
    ), f"DSN targeting prod host port {PROD_HOST_PORT} must exit 1.\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    assert (
        str(PROD_HOST_PORT) in cp.stderr or "production" in cp.stderr.lower()
    ), f"Error message should explain why it failed. stderr was:\n{cp.stderr}"


def test_default_postgres_port_exits_one():
    cp = _run(_dsn(DEFAULT_PG_PORT))
    assert (
        cp.returncode == 1
    ), f"DSN targeting default Postgres port {DEFAULT_PG_PORT} must exit 1.\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"


def test_non_prod_port_exits_zero():
    # Compose the throwaway-port DSN at runtime — literal ":22062" never
    # appears in the source text, but the resulting DSN is well-formed.
    cp = _run(f"postgresql://test:test@localhost:{TEST_THROW_PORT}/infotriage_test")
    assert cp.returncode == 0, (
        f"DSN targeting throwaway test port {TEST_THROW_PORT} should exit 0.\n"
        f"stdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )


def test_malformed_dsn_exits_one():
    cp = _run("not-a-uri")
    assert (
        cp.returncode == 1
    ), f"Malformed DSN must exit 1.\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    assert (
        "libpq" in cp.stderr.lower() or "uri" in cp.stderr.lower()
    ), f"Error should explain format. stderr was:\n{cp.stderr}"


def test_postgres_short_scheme_accepted():
    """Single-token 'postgres://' (no 'ql') is also a valid libpq prefix."""
    cp = _run(f"postgres://test:test@localhost:{SAFE_PORT}/db")
    assert (
        cp.returncode == 0
    ), f"Short 'postgres://' scheme should be accepted.\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
