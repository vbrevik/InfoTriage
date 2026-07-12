"""Tests for ops/Makefile targets."""

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = ROOT / "ops" / "Makefile"


@pytest.mark.skipif(not MAKEFILE.exists(), reason="ops/Makefile not found")
def test_makefile_help_target_exists():
    """`make help` in ops/ should succeed and list targets."""
    result = subprocess.run(
        ["make", "-f", str(MAKEFILE), "help"],
        cwd=str(ROOT / "ops"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "up" in result.stdout
    assert "down" in result.stdout
    assert "logs" in result.stdout
    assert "status" in result.stdout
    assert "replay" in result.stdout


@pytest.mark.skipif(not MAKEFILE.exists(), reason="ops/Makefile not found")
def test_makefile_dry_run_targets_parse():
    """Key targets should parse without shell errors in dry-run mode."""
    targets = ["up", "down", "logs", "status", "restart", "seed", "backfill", "replay"]
    for target in targets:
        result = subprocess.run(
            ["make", "-f", str(MAKEFILE), "-n", target],
            cwd=str(ROOT / "ops"),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Target {target} failed: {result.stderr}"
