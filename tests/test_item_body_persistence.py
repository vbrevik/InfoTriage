#!/usr/bin/env python3
"""tests/test_item_body_persistence.py — SPEC R7 producer-side body write path.

Parameterized over InMemoryStore and PostgresStore (postgres auto-skipped
when INFOTRIAGE_TEST_DSN is unset or the test DB is unreachable — matches
the pattern in tests/test_store_entities.py).

Covers: byte-identical round-trip, NULL-not-empty-string coercion (None,
empty string, whitespace-only), ON CONFLICT DO UPDATE refresh/clear
semantics, and the >=1MB oversized-body backstop (SPEC R7 "no size cap").
"""
from __future__ import annotations

import datetime
import os
import socket

import pytest

from contracts import Item
from store import InMemoryStore


TEST_DSN_ENV = "INFOTRIAGE_TEST_DSN"


def _test_db_reachable() -> bool:
    """Return True if the INFOTRIAGE_TEST_DSN test DB accepts a TCP connection within 1s."""
    import psycopg

    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        return False
    try:
        info = psycopg.conninfo.conninfo_to_dict(dsn)
    except psycopg.Error:
        return False
    host = str(info.get("host") or "localhost")
    port = int(info.get("port") or 5432)
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


_PG_UP = _test_db_reachable()

_pg_live_skipif = (
    pytest.mark.db_live,
    pytest.mark.skipif(
        not _PG_UP,
        reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
    ),
)


def _ts() -> datetime.datetime:
    from datetime import timezone

    return datetime.datetime.now(timezone.utc)


def _make_item(item_id: str = "item-001", body: str | None = None) -> Item:
    return Item(
        source="TestSource",
        source_type="rss",
        url=f"https://example.com/{item_id}",
        title="Test Item",
        ts=_ts(),
        lang="en",
        body=body,
    )


@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=_pg_live_skipif),
    ]
)
def store(request, tmp_path):
    """Yield a fresh Store implementation for each parametrized variant."""
    if request.param == "inmemory":
        yield InMemoryStore(blob_root=tmp_path / "blobs")
    else:
        from store import PostgresStore

        dsn = os.environ.get(TEST_DSN_ENV)
        PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs").init_schema()
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                "TRUNCATE infotriage.ccir, infotriage.entity_links, infotriage.entities, "
                "infotriage.embeddings, infotriage.enrichment, infotriage.audit, "
                "infotriage.articles RESTART IDENTITY CASCADE"
            )
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            yield s


def _assert_null_in_db(store_impl, item_id: str) -> None:
    """For PostgresStore only: assert the raw column is SQL NULL, not ''."""
    from store import PostgresStore

    if not isinstance(store_impl, PostgresStore):
        return
    row = (
        store_impl.cursor()
        .execute("SELECT body FROM infotriage.articles WHERE id = %s", (item_id,))
        .fetchone()
    )
    assert row["body"] is None
    store_impl._conn.rollback()


# -------------------------------------------------------------------------
# Test 1: multi-paragraph body round-trips byte-identically
# -------------------------------------------------------------------------


def test_body_round_trips_byte_identical(store):
    body = "Paragraph one.\n\nParagraph two, with more detail.\n\nParagraph three."
    item = _make_item(body=body)
    store.put_item(item)
    got = store.get_item(item.id)
    assert got is not None
    assert got.body == body


# -------------------------------------------------------------------------
# Test 2/3/4: bodyless / empty-string / whitespace-only all persist as NULL
# -------------------------------------------------------------------------


@pytest.mark.parametrize("raw_body", [None, "", "   \n\t  "])
def test_bodyless_variants_persist_as_null(store, raw_body):
    item = _make_item(item_id=f"bodyless-{raw_body!r}", body=raw_body)
    store.put_item(item)
    got = store.get_item(item.id)
    assert got is not None
    assert got.body is None
    _assert_null_in_db(store, item.id)


# -------------------------------------------------------------------------
# Test 5/6: ON CONFLICT DO UPDATE — body refreshes and clears
# -------------------------------------------------------------------------


def test_reput_with_changed_body_updates(store):
    item = _make_item(item_id="reput-1", body="original text")
    store.put_item(item)
    updated = _make_item(item_id="reput-1", body="new text")
    assert updated.id == item.id  # body is not part of identity (D-04)
    store.put_item(updated)
    got = store.get_item(item.id)
    assert got.body == "new text"


def test_reput_with_no_body_clears_to_null(store):
    item = _make_item(item_id="reput-2", body="will be cleared")
    store.put_item(item)
    cleared = _make_item(item_id="reput-2", body=None)
    assert cleared.id == item.id
    store.put_item(cleared)
    got = store.get_item(item.id)
    assert got.body is None
    _assert_null_in_db(store, item.id)


# -------------------------------------------------------------------------
# Test 7 (backstop): SPEC R7 encoding backstop — no size cap.
# Do NOT shrink this test for speed; it is the explicit "no truncation"
# proof for a column with no documented size limit.
# -------------------------------------------------------------------------


def test_oversized_body_round_trips_with_no_truncation(store):
    oversized = "x" * 1_100_000  # >=1MB, generated at test time (not committed)
    item = _make_item(item_id="oversized-1", body=oversized)
    store.put_item(item)
    got = store.get_item(item.id)
    assert got is not None
    assert len(got.body) == len(oversized)
    assert got.body == oversized


# -------------------------------------------------------------------------
# Test 8: identity unaffected by body (contract-level, store-independent)
# -------------------------------------------------------------------------


def test_body_does_not_affect_item_identity():
    a = _make_item(item_id="same-url", body="body A")
    b = _make_item(item_id="same-url", body="body B, totally different")
    assert a.id == b.id
