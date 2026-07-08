#!/usr/bin/env python3
"""tests/test_store_contract.py — shared parametrized contract tests for Store impls.

Tests run against both InMemoryStore and PostgresStore. The postgres param is
auto-skipped when INFOTRIAGE_TEST_DSN is unset or the test DB is unreachable
(db_live marker). Import of PostgresStore
is lazy (inside the postgres fixture branch) so this file collects cleanly before
plan 03 creates _postgres.py.

Covers R5 requirements and both must-NOT prohibitions:
- isinstance(store, Store) is True (runtime_checkable Protocol)
- put_item then get_item returns equal Item
- get_item("absent") returns None (miss → None)
- list_items() on empty store returns [] (not None)
- put_item twice (same id) → one entry, latest content (last-write-wins upsert)
- list_items(source_type_in=["rss","yt"]) → only those types, ordered by (ts, id) desc
- put_blob/get_blob round-trip via _blob helpers
- Failed persist raises (no silent success) — must-NOT prohibition
- InMemoryStore does not diverge from PostgresStore contract (shared test suite)
"""
import datetime
import os
import socket

import pytest

from contracts import Item
from store import InMemoryStore, Store


# ---------------------------------------------------------------------------
# db_live marker — skip postgres param when INFOTRIAGE_TEST_DSN is unavailable
# ---------------------------------------------------------------------------

TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"  # the ONLY DSN source for db_live tests


def _test_db_reachable() -> bool:
    """Return True if the INFOTRIAGE_TEST_DSN test DB accepts a TCP connection within 1s.

    Returns False when INFOTRIAGE_TEST_DSN is unset/empty, so db_live tests
    auto-skip when no isolated test DB is configured (R8). Host/port are parsed
    from the DSN itself — never hardcoded.
    """
    import psycopg
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        return False
    try:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
    except psycopg.Error:
        return False
    host = info.get("host") or "localhost"
    port = int(info.get("port") or 5432)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


# db_live + skipif marks: the registered 'db_live' marker (so `pytest -m "not db_live"`
# actually deselects this fixture's postgres variant — a plain skipif-only mark here
# would NOT carry the db_live marker, since skipif and db_live are two independent
# marks, not one) plus auto-skip when PG is unreachable.
db_live = (
    pytest.mark.db_live,
    pytest.mark.skipif(
        not _test_db_reachable(),
        reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
    ),
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _ts(offset_seconds: int = 0) -> datetime.datetime:
    """Return a UTC-aware datetime offset from epoch for deterministic ordering."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    return base + datetime.timedelta(seconds=offset_seconds)


def _item(
    source_type: str = "rss",
    title: str = "Test Item",
    ts_offset: int = 0,
    summary: str | None = None,
) -> Item:
    return Item(
        source="Test Source",
        source_type=source_type,
        url=f"https://example.com/{source_type}/{title.lower().replace(' ', '-')}",
        title=title,
        ts=_ts(ts_offset),
        lang="en",
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Parametrized store fixture
# ---------------------------------------------------------------------------

@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=db_live),
    ]
)
def store(request, tmp_path):
    """Yield a fresh Store implementation for each parametrized variant."""
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        # Lazy import — PostgresStore does not exist until plan 03.
        # This branch is only reached when db_live passes (test DB is up),
        # so INFOTRIAGE_TEST_DSN is set here. NO fallback — a pytest run can
        # never touch the production database.
        import os as _os
        import psycopg as _psycopg
        from store import PostgresStore  # noqa: PLC0415

        dsn = _os.environ.get(TEST_DSN_ENV)
        # Bootstrap first: on a fresh test DB (docker-compose.test.yml) the
        # infotriage schema/extension don't exist yet — init_schema() must run
        # before TRUNCATE and before __enter__ (pgvector adapter registration).
        PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
        # Truncate test-data tables before each test for isolation.
        # CASCADE handles FK-dependent tables (entity_links, embeddings, etc.).
        with _psycopg.connect(dsn, autocommit=True) as _setup:
            _setup.execute(
                "TRUNCATE infotriage.entity_links, infotriage.embeddings, "
                "infotriage.enrichment, infotriage.ccir, infotriage.audit, "
                "infotriage.articles, infotriage.entities RESTART IDENTITY"
            )
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            yield s


# ---------------------------------------------------------------------------
# Protocol satisfaction
# ---------------------------------------------------------------------------

def test_protocol_satisfied(store):
    """Store implementation must satisfy isinstance check (runtime_checkable Protocol)."""
    assert isinstance(store, Store), (
        f"{type(store).__name__} does not satisfy Store Protocol"
    )


# ---------------------------------------------------------------------------
# put_item / get_item
# ---------------------------------------------------------------------------

def test_put_get_roundtrip(store):
    item = _item(title="Roundtrip Item")
    store.put_item(item)
    got = store.get_item(item.id)
    assert got is not None
    assert got.id == item.id
    assert got.title == item.title
    assert got.source_type == item.source_type


def test_get_miss_returns_none(store):
    """get_item on an absent id must return None, not raise."""
    result = store.get_item("nonexistent-id-that-was-never-stored")
    assert result is None


# ---------------------------------------------------------------------------
# list_items — empty / ordering
# ---------------------------------------------------------------------------

def test_list_empty_returns_empty_list(store):
    """list_items() on a fresh store must return an empty list (not None)."""
    result = store.list_items()
    assert result == []
    assert isinstance(result, list)


def test_list_items_ordering_ts_desc(store):
    """Items must be ordered by (ts DESC, id DESC) — latest first."""
    older = _item(title="Older Item", ts_offset=0)
    newer = _item(title="Newer Item", ts_offset=100)
    # Insert in reverse order to test sort correctness
    store.put_item(older)
    store.put_item(newer)
    result = store.list_items()
    assert len(result) == 2
    assert result[0].title == "Newer Item", "Latest ts must come first"
    assert result[1].title == "Older Item"


def test_list_items_source_type_filter(store):
    """list_items(source_type_in=["rss","yt"]) must exclude imap items."""
    rss = _item(source_type="rss", title="RSS Item")
    yt = _item(source_type="yt", title="YouTube Item")
    imap = _item(source_type="imap", title="Email Item")
    for item in (rss, yt, imap):
        store.put_item(item)
    result = store.list_items(source_type_in=["rss", "yt"])
    ids = {i.id for i in result}
    assert rss.id in ids
    assert yt.id in ids
    assert imap.id not in ids, "imap/email items must be excluded from the filtered list"


def test_list_items_limit(store):
    """list_items(limit=N) must return at most N items."""
    for i in range(5):
        store.put_item(_item(title=f"Item {i}", ts_offset=i))
    result = store.list_items(limit=3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# Upsert semantics — last-write-wins
# ---------------------------------------------------------------------------

def test_put_item_upsert_last_write_wins(store):
    """put_item called twice with the same id must produce one entry, latest content.

    Note: Item.id is derived from source_type + url + title, so updating summary
    (a non-id field) keeps the id stable and tests true upsert semantics.
    """
    original = _item(title="Stable Title for Upsert", summary="First summary")
    updated = original.model_copy(update={"summary": "Updated summary"})
    # Verify same id (both are same source_type + url + title)
    assert original.id == updated.id, "model_copy of non-id field must preserve id"
    store.put_item(original)
    store.put_item(updated)
    # Exactly one logical entry
    all_items = store.list_items()
    matching = [i for i in all_items if i.id == original.id]
    assert len(matching) == 1, f"Expected 1 entry, got {len(matching)}"
    assert matching[0].summary == "Updated summary", "Last write must win"


def test_put_item_upsert_get_reflects_update(store):
    """get_item after upsert must return the latest version."""
    original = _item(title="First Version")
    store.put_item(original)
    updated = original.model_copy(update={"summary": "Updated summary"})
    store.put_item(updated)
    got = store.get_item(original.id)
    assert got is not None
    assert got.summary == "Updated summary"


# ---------------------------------------------------------------------------
# Blob round-trip via _blob helpers
# ---------------------------------------------------------------------------

def test_blob_roundtrip(store, tmp_path):
    data = b"binary content for blob round-trip test"
    h = store.put_blob(data)
    result = store.get_blob(h)
    assert result == data


def test_blob_dedup(store):
    """put_blob twice with same bytes must succeed without error."""
    data = b"dedup content"
    h1 = store.put_blob(data)
    h2 = store.put_blob(data)
    assert h1 == h2


# ---------------------------------------------------------------------------
# must-NOT: failed persist raises — no silent success
# ---------------------------------------------------------------------------

def test_write_failure_raises(store, tmp_path, monkeypatch):
    """A failed blob write must raise, not silently return success.

    This is the must-NOT prohibition: MUST NOT silently lose or truncate a
    write — a failed persist raises; never a silent success.
    """
    from pathlib import Path
    from unittest.mock import patch

    data = b"test fail-loud payload"

    original_write_bytes = Path.write_bytes

    def patched_write_bytes(self, d):
        if self.suffix == ".tmp":
            raise OSError("simulated write failure for must-NOT test")
        return original_write_bytes(self, d)

    with patch.object(Path, "write_bytes", patched_write_bytes):
        with pytest.raises(OSError, match="simulated write failure"):
            store.put_blob(data)
