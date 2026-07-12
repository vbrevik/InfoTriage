#!/usr/bin/env python3
"""tests/test_validate_entity_threshold.py — tests for the threshold validation script."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "validate_entity_threshold.py"
CORPUS = ROOT / "tests" / "fixtures" / "entity_validation_sample.json"


def test_validation_script_requires_allow_synthetic_without_llm(tmp_path):
    """Without --allow-synthetic and no LLM, the script should fail."""
    env = {"LLM_BASE_URL": "http://127.0.0.1:1/v1"}
    report_path = tmp_path / "should_not_exist.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--report", str(report_path)],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=30,
    )
    assert result.returncode != 0
    assert not report_path.exists()


def test_validation_script_produces_report_with_synthetic_fallback(tmp_path):
    """With --allow-synthetic, the script should produce a report even without LLM."""
    report_path = tmp_path / "999.3-VERDICT.md"
    env = {"LLM_BASE_URL": "http://127.0.0.1:1/v1"}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus",
            str(CORPUS),
            "--report",
            str(report_path),
            "--allow-synthetic",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "999.3 Entity Resolution Threshold Validation" in text
    assert "Recommended `LINK_THRESHOLD`" in text
    assert "WARNING" in text
    assert "synthetic" in text.lower()


def test_validation_script_uses_real_corpus_values(tmp_path):
    """The report should contain values from the fixture corpus."""
    report_path = tmp_path / "999.3-VERDICT.md"
    env = {"LLM_BASE_URL": "http://127.0.0.1:1/v1"}
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus",
            str(CORPUS),
            "--report",
            str(report_path),
            "--allow-synthetic",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    text = report_path.read_text(encoding="utf-8")
    assert "NATO" in text
    assert "НАТО" in text
    assert "Russia" in text
