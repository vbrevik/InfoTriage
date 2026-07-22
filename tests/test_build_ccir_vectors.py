"""tests/test_build_ccir_vectors.py — build_ccir_vectors parser tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def parser():
    path = Path(__file__).parent.parent / "scripts" / "build_ccir_vectors.py"
    spec = importlib.util.spec_from_file_location("build_ccir_vectors", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_ccir_vectors"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("build_ccir_vectors", None)


def test_extract_sections_parses_pir_ffir_sir_bullets(parser, tmp_path):
    content = """## PIR — Priority Intelligence Requirements

- **PIR-1 Russland/Ukraina** — krigsutvikling, frontlinjer, våpenstøtte, sanksjoner.
  Vestlig våpenstøtte, opprustning og logistikk.
- **PIR-2 Nordområdene** — Svalbard, ubåter, GIUK-gap, nordlig sjørute.

## FFIR — Friendly Force Information Requirements

- **FFIR-1 Norsk forsvar** — Stortinget, Forsvaret, beredskap.
- **FFIR-2 Norsk politikk** — strategisk/nasjonal betydning.

## SIR — Specific Information Requirements

- **SIR-1 Midtøsten** — IRGC, proxyer, atomprogram.
"""
    path = tmp_path / "ccir.md"
    path.write_text(content, encoding="utf-8")
    sections = parser._extract_sections(path)

    assert set(sections.keys()) == {"PIR-1", "PIR-2", "FFIR-1", "FFIR-2", "SIR-1"}
    assert "Russland/Ukraina" in sections["PIR-1"]
    assert "Vestlig våpenstøtte" in sections["PIR-1"]
    assert "Nordområdene" in sections["PIR-2"]
    assert "Norsk forsvar" in sections["FFIR-1"]
    assert "Midtøsten" in sections["SIR-1"]


def test_extract_sections_ignores_non_bullet_lines(parser, tmp_path):
    content = """## PIR

Some intro text that should not be parsed.

- **PIR-1 Foo** — bar.
  continuation line.

## FFIR

- **FFIR-1 Baz** — qux.
"""
    path = tmp_path / "ccir.md"
    path.write_text(content, encoding="utf-8")
    sections = parser._extract_sections(path)
    assert set(sections.keys()) == {"PIR-1", "FFIR-1"}
    assert "bar" in sections["PIR-1"]
    assert "continuation" in sections["PIR-1"]


def test_extract_sections_empty(parser, tmp_path):
    path = tmp_path / "ccir.md"
    path.write_text("## PIR\n\nNo bullets here.\n", encoding="utf-8")
    sections = parser._extract_sections(path)
    assert sections == {}
