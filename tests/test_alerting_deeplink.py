"""test_alerting_deeplink.py — Phase 12 Plan 01 Task 2.

Cross-module contract test: proves the obsidian:// deep link's decoded
vault-relative path equals the path apps/brief/vault_writer.py actually
writes for the same item (SPEC R5). This is the only guard that catches a
future divergence between the two filename derivations, which would
silently 404 the operator's tap-through.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

from apps.brief.vault_writer import write_item_obsidian

from deep_link import (
    DEFAULT_SAB_FILENAME,
    item_note_link,
    obsidian_note_filename,
    sab_note_link,
)


def _decode_params(uri: str) -> dict[str, str]:
    """Parse the query params of an obsidian://open?... URI, already unquoted."""
    parsed = urlparse(uri)
    query = parse_qs(parsed.query)
    return {k: v[0] for k, v in query.items()}


def _make_item(item_id: str) -> dict:
    return {
        "item_id": item_id,
        "title": "A CAT I test item",
        "summary": "Test summary",
        "source": "Test Source",
        "url": "https://example.com/x",
        "ts": datetime.now(timezone.utc).isoformat(),
        "ccir": "PIR-1",
        "cnr": "I",
        "score": 9,
        "bucket": "keep",
        "why": "Important",
    }


def test_item_note_link_matches_write_item_obsidian_output(monkeypatch, tmp_path):
    """Test 1: decoded file param equals the vault-writer's actual output path."""
    monkeypatch.delenv("INFOTRIAGE_OBSIDIAN_VAULT_NAME", raising=False)
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
    monkeypatch.setenv("INFOTRIAGE_ALERT_NOTE_SUBDIR", "brief-outbox")

    item_id = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"  # sha256-hex-shaped
    item = _make_item(item_id)
    vault_root = tmp_path
    subdir = "brief-outbox"

    written_path = write_item_obsidian(item, vault_root / subdir)
    expected_rel = str(written_path.relative_to(vault_root))

    decoded = _decode_params(item_note_link(item_id))
    assert unquote(decoded["file"]) == expected_rel


def test_obsidian_note_filename_matches_write_item_obsidian(tmp_path):
    """Test 2: filenames match for an item_id with non-word characters."""
    item_id = "abc/def:123 (test)?"
    item = _make_item(item_id)

    written_path = write_item_obsidian(item, tmp_path)

    assert obsidian_note_filename(item_id) == written_path.name


def test_sab_note_link_decoded_file_is_subdir_plus_default_filename(monkeypatch):
    """Test 3: sab_note_link's decoded file param is subdir/obsidian-sab.md."""
    monkeypatch.setenv("INFOTRIAGE_ALERT_NOTE_SUBDIR", "brief-outbox")

    decoded = _decode_params(sab_note_link())

    assert unquote(decoded["file"]) == f"brief-outbox/{DEFAULT_SAB_FILENAME}"


def test_vault_name_with_space_round_trips(monkeypatch):
    """Test 4: a vault name with a space is percent-encoded and round-trips."""
    monkeypatch.setenv("INFOTRIAGE_OBSIDIAN_VAULT_NAME", "My Vault Name")

    uri = sab_note_link()
    assert "My Vault Name" not in uri  # the literal space must not appear raw

    decoded = _decode_params(uri)
    assert decoded["vault"] == "My Vault Name"


def test_overriding_subdir_changes_only_file_prefix(monkeypatch):
    """Test 5: overriding the subdir env var changes only the file param prefix."""
    monkeypatch.setenv("INFOTRIAGE_OBSIDIAN_VAULT_NAME", "obsidian")
    monkeypatch.setenv("INFOTRIAGE_ALERT_NOTE_SUBDIR", "brief-outbox")
    baseline = _decode_params(sab_note_link())

    monkeypatch.setenv("INFOTRIAGE_ALERT_NOTE_SUBDIR", "custom-subdir")
    overridden = _decode_params(sab_note_link())

    assert unquote(overridden["file"]) == f"custom-subdir/{DEFAULT_SAB_FILENAME}"
    assert overridden["vault"] == baseline["vault"]
