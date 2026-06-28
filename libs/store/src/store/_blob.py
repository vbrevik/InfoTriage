#!/usr/bin/env python3
"""_blob.py — content-addressed blob store helpers.

All stdlib — no third-party imports. Exposes three module-level functions:

    put_blob(root, data) -> sha256_hex
    get_blob(root, blob_hash) -> bytes
    _shard_path(root, h) -> Path  (internal helper, exposed for testing)

Blob paths are sharded 2 levels deep:
    root/<h[:2]>/<h[2:4]>/<h>

Writes are atomic via tmp-sibling + os.replace() (POSIX rename guarantee).
Any write failure cleans up the temp file and re-raises — fail loud, no
silent data loss (must-NOT prohibition, R4).

Path-traversal guard: get_blob() validates the hash with a fullmatch on
[0-9a-f]{64} before constructing any path (T-02-02 security control).
"""
import hashlib
import os
import re
from pathlib import Path

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _shard_path(root: Path, h: str) -> Path:
    """Return the sharded blob path for hash h under root.

    Layout: root/<h[:2]>/<h[2:4]>/<h>
    """
    return root / h[:2] / h[2:4] / h


def _validate_hash(blob_hash: str) -> None:
    """Raise ValueError if blob_hash is not 64-char lowercase hex.

    This is the path-traversal guard (T-02-02). Called before any filesystem
    access in get_blob so that inputs like '../../etc/passwd' never reach
    _shard_path().
    """
    if not _HEX64.fullmatch(blob_hash):
        raise ValueError(
            f"Invalid blob hash {blob_hash!r}: must be 64 lowercase hex characters"
        )


def put_blob(root: Path, data: bytes) -> str:
    """Store bytes at a content-addressed sharded path under root.

    Returns the sha256 hex digest of data.

    If the destination already exists (duplicate put), returns the hash
    immediately — content-dedup no-op, no write (R4 idempotency).

    On write failure: cleans up the temp file and re-raises. Never returns
    a success response for a failed write (must-NOT: no silent data loss).
    """
    h = hashlib.sha256(data).hexdigest()
    dest = _shard_path(root, h)
    if dest.exists():
        return h  # dedup no-op — identical bytes already stored
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(str(tmp), str(dest))  # atomic POSIX rename; NOT os.rename (anti-pattern)
    except Exception:
        tmp.unlink(missing_ok=True)  # never leave a partial write on disk
        raise  # fail loud — caller must see the error
    return h


def get_blob(root: Path, blob_hash: str) -> bytes:
    """Return bytes for the blob identified by blob_hash.

    Raises:
        ValueError: if blob_hash is not a 64-char lowercase hex string
                    (path-traversal guard T-02-02 — validated before any I/O).
        FileNotFoundError: if no blob with that hash has been stored.
    """
    _validate_hash(blob_hash)  # traversal guard first — no filesystem access before this
    return _shard_path(root, blob_hash).read_bytes()
    # FileNotFoundError propagates — caller handles; we never swallow misses
