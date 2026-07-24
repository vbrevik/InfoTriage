"""CCIR registry — single source of truth invariants + legacy-parity checks.

These lock the registry to the values that were previously hardcoded across
digest.py / sab_html.py / views.py / triage_score.py, so the migration is
provably behavior-preserving (except the intentional SIR-3 drift fix).
"""

from contracts.ccir import (
    CCIR,
    CCIR_ORDER,
    COP_CCIR,
    active_ccir_enum,
    active_specs,
    build_scorer_block,
)


def test_registry_active_ccirs_in_order():
    # 12 migrated requirements + FFIR-4 (frontier AI/LLM landscape, added
    # 2026-07-24 to split frontier-model news from own-local-capability FFIR-3).
    assert [c.id for c in active_specs()] == [
        "PIR-1",
        "PIR-2",
        "PIR-3",
        "PIR-4",
        "PIR-5",
        "PIR-6",
        "SIR-1",
        "SIR-2",
        "SIR-3",
        "FFIR-1",
        "FFIR-2",
        "FFIR-3",
        "FFIR-4",
    ]


def test_every_spec_has_required_fields():
    for c in CCIR:
        assert c.id and c.title and c.scorer_line
        assert isinstance(c.cop, bool)
        assert isinstance(c.pmesii, tuple) and c.pmesii
        assert isinstance(c.tessoc, tuple) and c.tessoc


def test_ccir_order_matches_legacy_literal():
    assert CCIR_ORDER == [
        ("PIR-1", "Russland / Ukraina"),
        ("PIR-2", "Nordområdene & Arktis"),
        ("PIR-3", "NATO & europeisk sikkerhet"),
        ("PIR-4", "Hybrid- & cybertrusler"),
        ("PIR-5", "Stormaktsrivalisering"),
        ("PIR-6", "OSINT & etterforskning"),
        ("SIR-1", "Midtøsten & US-Iran"),
        ("SIR-2", "Sport — VM 2026 (FIFA)"),
        ("SIR-3", "NATO-toppmøtet i Ankara"),
        ("FFIR-1", "Norsk forsvar & sikkerhetspolitikk"),
        ("FFIR-2", "Norsk politikk & samfunn"),
        ("FFIR-3", "Egen teknologikapabilitet"),
        ("FFIR-4", "Frontier AI & LLM-landskap"),
    ]


def test_cop_ccir_matches_legacy_set():
    assert COP_CCIR == {
        "FFIR-1",
        "FFIR-2",
        "FFIR-3",
        "FFIR-4",
        "PIR-3",
        "SIR-2",
        "SIR-3",
    }


def test_scorer_block_lists_active_ids_and_examples():
    block = build_scorer_block()
    for cid in ["PIR-1", "SIR-2", "SIR-3", "FFIR-3"]:
        assert cid in block
    assert "Bellingcat identifies Russian officer" in block  # worked example


def test_scorer_enum_includes_sir3_regression():
    # SIR-3 was absent from the legacy enum (drift bug); registry restores it.
    enum = active_ccir_enum()
    assert "SIR-3" in enum
    assert enum.endswith("| none")
