#!/usr/bin/env python3
"""test_phase11_gates.py — tests for Phase 11 adapter gates."""
import datetime
import importlib.util
import sys
from pathlib import Path

import pytest
from contracts import Item, require_discipline, require_acled_license
from contracts._phase11_gates import DisciplineRequired, AcledLicenseMissing


TS = datetime.datetime.now(datetime.timezone.utc)


def _item(discipline=None) -> Item:
    return Item(
        source="Test Source",
        source_type="test",
        title="Test Item",
        ts=TS,
        lang="en",
        discipline=discipline,
    )


def test_require_discipline_raises_when_missing():
    """require_discipline rejects items without a discipline tag."""
    item = _item(discipline=None)
    with pytest.raises(DisciplineRequired):
        require_discipline(item)


def test_require_discipline_accepts_valid_discipline():
    """require_discipline passes when discipline is populated."""
    item = _item(discipline="SOCMINT")
    require_discipline(item)  # no exception


def test_require_acled_license_missing_raises(monkeypatch):
    """require_acled_license raises when ACLED_LICENSE_KEY is absent."""
    monkeypatch.delenv("ACLED_LICENSE_KEY", raising=False)
    with pytest.raises(AcledLicenseMissing):
        require_acled_license()


def test_require_acled_license_empty_raises(monkeypatch):
    """require_acled_license raises when ACLED_LICENSE_KEY is empty/whitespace."""
    monkeypatch.setenv("ACLED_LICENSE_KEY", "   ")
    with pytest.raises(AcledLicenseMissing):
        require_acled_license()


def test_require_acled_license_returns_trimmed_key(monkeypatch):
    """require_acled_license returns the trimmed key when present."""
    monkeypatch.setenv("ACLED_LICENSE_KEY", "  abc-123  ")
    assert require_acled_license() == "abc-123"


def _load_acled_ingest():
    """Load the ACLED ingest stub from its file path (package name contains a hyphen)."""
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "apps" / "ingest-acled" / "acled_ingest.py"
    # Use a unique module name per test load to avoid cache collisions.
    module_name = f"acled_ingest_test_{id(module_path)}"
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    # Clean up the unique module entry to avoid polluting sys.modules.
    sys.modules.pop(module_name, None)
    return module


@pytest.mark.asyncio
async def test_acled_ingest_blocks_without_license(monkeypatch):
    """The ACLED ingest stub refuses to run without a valid license."""
    monkeypatch.delenv("ACLED_LICENSE_KEY", raising=False)
    acled_ingest = _load_acled_ingest()

    with pytest.raises(AcledLicenseMissing):
        await acled_ingest.ingest()


@pytest.mark.asyncio
async def test_acled_ingest_runs_with_license(monkeypatch):
    """The ACLED ingest stub completes when a valid license is present."""
    monkeypatch.setenv("ACLED_LICENSE_KEY", "paid-key-123")
    acled_ingest = _load_acled_ingest()

    result = await acled_ingest.ingest()
    assert result is None
