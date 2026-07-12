#!/usr/bin/env python3
"""tests/test_store_blob.py — unit tests for the content-addressed blob store.

Covers R4 requirements:
- put_blob(root, data) → sha256 hex; file at root/<h[:2]>/<h[2:4]>/<h>
- get_blob(root, h) → identical bytes
- Duplicate put_blob of identical bytes → exactly one file, no error (idempotency)
- Distinct bytes → distinct hashes, distinct paths
- get_blob("../../etc/passwd") → ValueError (traversal guard, T-02-02)
- get_blob on valid-but-absent hash → FileNotFoundError
- Induced write failure → no file at final path, re-raises (atomicity, must-NOT)
"""
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from store._blob import get_blob, put_blob


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Basic round-trip
# ---------------------------------------------------------------------------


def test_put_returns_sha256(tmp_path):
    data = b"hello world"
    h = put_blob(tmp_path, data)
    assert h == _sha256(data)


def test_get_returns_original_bytes(tmp_path):
    data = b"hello world"
    h = put_blob(tmp_path, data)
    assert get_blob(tmp_path, h) == data


def test_roundtrip_empty_bytes(tmp_path):
    data = b""
    h = put_blob(tmp_path, data)
    assert get_blob(tmp_path, h) == data


# ---------------------------------------------------------------------------
# Sharded path layout
# ---------------------------------------------------------------------------


def test_shard_path(tmp_path):
    data = b"sharded content"
    h = put_blob(tmp_path, data)
    expected = tmp_path / h[:2] / h[2:4] / h
    assert expected.exists(), f"Expected blob file at {expected}"


def test_shard_path_correct_content(tmp_path):
    data = b"check content matches path"
    h = put_blob(tmp_path, data)
    dest = tmp_path / h[:2] / h[2:4] / h
    assert dest.read_bytes() == data


# ---------------------------------------------------------------------------
# Idempotency — duplicate put of identical bytes
# ---------------------------------------------------------------------------


def test_dedup_single_file(tmp_path):
    data = b"identical bytes"
    h1 = put_blob(tmp_path, data)
    h2 = put_blob(tmp_path, data)
    assert h1 == h2, "Same bytes must produce same hash"
    # Only one file should exist under the shard directory
    parent = tmp_path / h1[:2] / h1[2:4]
    blobs = list(parent.iterdir())
    assert len(blobs) == 1, f"Expected 1 file, got {len(blobs)}: {blobs}"


def test_dedup_no_error(tmp_path):
    data = b"dedup no error"
    put_blob(tmp_path, data)
    put_blob(tmp_path, data)  # must not raise


# ---------------------------------------------------------------------------
# Distinct bytes produce distinct hashes and paths
# ---------------------------------------------------------------------------


def test_distinct_payloads_distinct_hashes(tmp_path):
    h1 = put_blob(tmp_path, b"payload A")
    h2 = put_blob(tmp_path, b"payload B")
    assert h1 != h2


def test_distinct_payloads_distinct_paths(tmp_path):
    h1 = put_blob(tmp_path, b"alpha content")
    h2 = put_blob(tmp_path, b"beta content")
    p1 = tmp_path / h1[:2] / h1[2:4] / h1
    p2 = tmp_path / h2[:2] / h2[2:4] / h2
    assert p1 != p2
    assert p1.exists()
    assert p2.exists()


# ---------------------------------------------------------------------------
# Traversal guard (T-02-02)
# ---------------------------------------------------------------------------


def test_traversal_guard_relative_path(tmp_path):
    with pytest.raises(ValueError):
        get_blob(tmp_path, "../../etc/passwd")


def test_traversal_guard_short_hash(tmp_path):
    # A 63-char hex string — not 64
    with pytest.raises(ValueError):
        get_blob(tmp_path, "a" * 63)


def test_traversal_guard_uppercase(tmp_path):
    # 64 chars but uppercase (not lowercase hex)
    with pytest.raises(ValueError):
        get_blob(tmp_path, "A" * 64)


def test_traversal_guard_non_hex(tmp_path):
    with pytest.raises(ValueError):
        get_blob(tmp_path, "z" * 64)


# ---------------------------------------------------------------------------
# Miss — valid-format hash that doesn't exist
# ---------------------------------------------------------------------------


def test_get_absent_hash_raises_file_not_found(tmp_path):
    # A valid sha256-format hash that was never written
    absent = "a" * 64
    with pytest.raises(FileNotFoundError):
        get_blob(tmp_path, absent)


# ---------------------------------------------------------------------------
# Atomicity — induced write failure leaves no final-path file
# ---------------------------------------------------------------------------


def test_atomic_write_failure_no_final_file(tmp_path):
    """An induced write failure must leave no file at the final sharded path.

    Monkeypatch Path.write_bytes to raise, assert:
    - the exception propagates (fail-loud, no silent success)
    - the final destination path does not exist
    - no .tmp file left behind
    """
    data = b"atomic failure test payload"
    h = _sha256(data)
    dest = tmp_path / h[:2] / h[2:4] / h
    tmp_file = dest.parent / (h + ".tmp")

    original_write_bytes = Path.write_bytes

    def patched_write_bytes(self, data):
        if self.suffix == ".tmp":
            raise OSError("simulated write failure")
        return original_write_bytes(self, data)

    with patch.object(Path, "write_bytes", patched_write_bytes):
        with pytest.raises(OSError, match="simulated write failure"):
            put_blob(tmp_path, data)

    assert not dest.exists(), f"Final path must not exist after write failure: {dest}"
    assert not tmp_file.exists(), f"Temp file must be cleaned up: {tmp_file}"
