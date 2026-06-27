#!/usr/bin/env python3
"""test_ingest_paths.py — path-depth regression tests for apps/ingest scripts.

After the Phase 1 git mv from flat bridge/ to apps/ingest/ (one level deeper),
each script's repo-root computation must add a dirname level. CR-01: imap and yt
were missed and resolved ROOT to .../InfoTriage/apps instead of the repo root,
silently breaking .env/credential loading and feed output paths.
"""
import os


def test_imap_root_resolves_to_repo_root():
    import imap_to_atom

    # ROOT must be the repo root (which contains apps/ingest/), not apps/ itself (CR-01).
    assert os.path.basename(imap_to_atom.ROOT) != "apps"
    assert os.path.isdir(os.path.join(imap_to_atom.ROOT, "apps", "ingest"))


def test_yt_root_resolves_to_repo_root():
    import yt_to_atom

    assert os.path.basename(yt_to_atom.ROOT) != "apps"
    assert os.path.isdir(os.path.join(yt_to_atom.ROOT, "apps", "ingest"))
