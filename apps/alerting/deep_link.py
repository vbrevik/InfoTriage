#!/usr/bin/env python3
"""deep_link.py — obsidian:// deep-link URI construction for CAT I alerts.

Derives the same vault-relative note path that `apps/brief/vault_writer.py`
actually writes for the item note, and the SAB note's known filename, so an
alert's `deep_link` / `item_link` never 404 the operator's tap-through
(SPEC R5). Env is read at call time (not import time) so tests can
monkeypatch the vault name / note subdirectory per-test.

Assumption A-01 (see 12-01-PLAN.md objective): `deep_link` -> the item's own
vault note; `item_link` -> the SAB note in the same vault.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote

DEFAULT_VAULT_NAME = "obsidian"
DEFAULT_NOTE_SUBDIR = "brief-outbox"
DEFAULT_SAB_FILENAME = "obsidian-sab.md"


def obsidian_note_filename(item_id: str) -> str:
    """Derive the note filename for item_id.

    Mirrors apps/brief/vault_writer.py::write_item_obsidian's safe_id regex
    exactly (strip everything outside word characters and hyphen, append .md).
    """
    safe_id = re.sub(r"[^\w\-]", "", str(item_id))
    return f"{safe_id}.md"


def _vault_name() -> str:
    """Resolve the Obsidian-registered vault display name.

    INFOTRIAGE_OBSIDIAN_VAULT_NAME wins when set; otherwise falls back to the
    basename of OBSIDIAN_VAULT_PATH; otherwise the literal "obsidian".
    """
    name = os.environ.get("INFOTRIAGE_OBSIDIAN_VAULT_NAME", "").strip()
    if name:
        return name
    vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if vault_path:
        basename = os.path.basename(vault_path.rstrip("/"))
        if basename:
            return basename
    return DEFAULT_VAULT_NAME


def _note_subdir() -> str:
    """Resolve the vault-relative note subdirectory (no leading/trailing slash)."""
    subdir = os.environ.get("INFOTRIAGE_ALERT_NOTE_SUBDIR", DEFAULT_NOTE_SUBDIR)
    return subdir.strip().strip("/")


def obsidian_deep_link(rel_path: str, vault_name: str) -> str:
    """Build an obsidian://open?vault=...&file=... URI.

    Parameter order is stable: vault first, then file. Both are
    percent-encoded with an empty safe set so path separators inside
    rel_path are encoded consistently.
    """
    return (
        f"obsidian://open?vault={quote(vault_name, safe='')}"
        f"&file={quote(rel_path, safe='')}"
    )


def item_note_link(item_id: str) -> str:
    """The obsidian:// URI opening the item's own vault note."""
    subdir = _note_subdir()
    filename = obsidian_note_filename(item_id)
    rel_path = f"{subdir}/{filename}" if subdir else filename
    return obsidian_deep_link(rel_path, _vault_name())


def sab_note_link() -> str:
    """The obsidian:// URI opening the SAB note in the same vault."""
    subdir = _note_subdir()
    rel_path = f"{subdir}/{DEFAULT_SAB_FILENAME}" if subdir else DEFAULT_SAB_FILENAME
    return obsidian_deep_link(rel_path, _vault_name())
