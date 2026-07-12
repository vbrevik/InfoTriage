"""Syntax and import validation for scripts/set_newsapi_ttl.py.

This test ensures the helper script stays syntactically valid and can be
imported, so it won't break when run in CI or local automation.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "set_newsapi_ttl.py"


def test_script_exists():
    """The helper script must exist at the expected path."""
    assert SCRIPT.exists(), f"Expected script at {SCRIPT}"


def test_script_compiles():
    """The helper script must compile without syntax errors."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Syntax error in {SCRIPT}: {result.stderr}"


def test_script_has_main():
    """The helper script must define a main() function and __main__ guard."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "main" in names, f"{SCRIPT} should define a main() function"

    # Simpler check: source contains the standard guard
    assert 'if __name__ == "__main__":' in SCRIPT.read_text(
        encoding="utf-8"
    ), f"{SCRIPT} should contain a standard __main__ guard"


def test_script_rejects_invalid_ttl():
    """The helper script should exit non-zero for an invalid TTL argument."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "not-a-number"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 2
    ), f"Expected usage error for invalid TTL, got {result.returncode}"
