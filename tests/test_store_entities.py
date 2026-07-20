#!/usr/bin/env python3
"""tests/test_store_entities.py — contract tests for entity store methods (Phase 8).

Tests run against both InMemoryStore and PostgresStore. The postgres param is
auto-skipped when INFOTRIAGE_TEST_DSN is unset or the test DB is unreachable.
"""
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


def _make_item(item_id: str = "item-001") -> Item:
    return Item(
        source="TestSource",
        source_type="rss",
        url=f"https://example.com/{item_id}",
        title="Test Item",
        ts=_ts(),
        lang="en",
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
        # Truncate entity-related tables for isolation
        import psycopg

        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(
                "TRUNCATE infotriage.ccir, infotriage.entity_links, infotriage.entities, "
                "infotriage.embeddings, infotriage.enrichment, infotriage.audit, "
                "infotriage.articles RESTART IDENTITY CASCADE"
            )
        with PostgresStore(dsn=dsn, blob_root=tmp_path / "blobs") as s:
            yield s


def _seed_item(store_impl) -> Item:
    """Put a minimal Item into the store and return it."""
    item = _make_item()
    store_impl.put_item(item)
    return item


def test_put_get_entity_roundtrip(store):
    """put_entity returns an id; get_entity returns the stored entity."""
    item = _seed_item(store)
    entity_id = store.put_entity(
        name="NATO",
        name_norm="nato",
        lang="en",
        type="ORG",
        embedding=None,
    )
    assert entity_id
    got = store.get_entity(entity_id)
    assert got is not None
    assert got["name"] == "NATO"
    assert got["name_norm"] == "nato"
    assert got["lang"] == "en"
    assert got["type"] == "ORG"


def test_put_entity_idempotent(store):
    """put_entity twice for the same (name_norm, lang) updates in place."""
    item = _seed_item(store)
    entity_id_1 = store.put_entity(
        name="NATO",
        name_norm="nato",
        lang="en",
        type="ORG",
        embedding=None,
    )
    entity_id_2 = store.put_entity(
        name="NATO (updated)",
        name_norm="nato",
        lang="en",
        type="GPE",
        embedding=None,
    )
    assert entity_id_1 == entity_id_2
    got = store.get_entity(entity_id_1)
    assert got["name"] == "NATO (updated)"
    assert got["type"] == "GPE"


def test_put_entity_preserves_embedding(store):
    """A None embedding must not overwrite an existing embedding."""
    item = _seed_item(store)
    vec = [1.0] + [0.0] * 1023
    entity_id = store.put_entity(
        name="NATO",
        name_norm="nato",
        lang="en",
        type="ORG",
        embedding=vec,
    )
    store.put_entity(
        name="NATO",
        name_norm="nato",
        lang="en",
        type="ORG",
        embedding=None,
    )
    got = store.get_entity(entity_id)
    assert list(got["embedding"]) == vec


def test_link_entity_idempotent_for_item(store):
    """link_entity is idempotent for (entity_id, item_id, mention)."""
    item = _seed_item(store)
    entity_id = store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
    )
    store.link_entity(entity_id, item.id, "NATO", "en")
    store.link_entity(entity_id, item.id, "NATO", "en")
    links = store.get_entity_links(item.id)
    assert len(links) == 1
    assert links[0]["name"] == "NATO"
    assert links[0]["mention"] == "NATO"


def test_get_entity_links(store):
    """get_entity_links returns rows joined to canonical entity names."""
    item = _seed_item(store)
    entity_id = store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
    )
    store.link_entity(entity_id, item.id, "NATO", "en")
    links = store.get_entity_links(item.id)
    assert len(links) == 1
    assert links[0]["entity_id"] == entity_id
    assert links[0]["name"] == "NATO"
    assert links[0]["mention"] == "NATO"
    assert links[0]["lang"] == "en"


def test_get_entity_by_name_norm(store):
    """get_entity_by_name_norm returns the entity for (name_norm, lang)."""
    _seed_item(store)
    entity_id = store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
    )
    got = store.get_entity_by_name_norm("nato", "en")
    assert got is not None
    assert got["id"] == entity_id
    assert got["name"] == "NATO"
    assert store.get_entity_by_name_norm("nato", "no") is None
    assert store.get_entity_by_name_norm("oslo", "en") is None


def test_get_all_entities_aggregates_aliases_and_links(store):
    """get_all_entities returns all entities with aliases and link_count."""
    item1 = _seed_item(store)
    item2 = _make_item("item-002")
    store.put_item(item2)
    entity_id = store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
    )
    store.put_entity(name="Oslo", name_norm="oslo", lang="en", type="GPE", embedding=None)
    store.link_entity(entity_id, item1.id, "NATO", "en")
    store.link_entity(entity_id, item2.id, "NATO", "en")
    store.link_entity(entity_id, item2.id, "НАТО", "ru")
    all_entities = store.get_all_entities()
    assert len(all_entities) == 2
    # Sorted by link_count desc, so NATO first
    nato = all_entities[0]
    assert nato["name"] == "NATO"
    assert nato["name_norm"] == "nato"
    assert nato["type"] == "ORG"
    assert nato["aliases"] == ["NATO (en)", "НАТО (ru)"]
    assert nato["link_count"] == 2
    oslo = all_entities[1]
    assert oslo["name"] == "Oslo"
    assert oslo["aliases"] == []
    assert oslo["link_count"] == 0


def test_get_all_entities_empty(store):
    """get_all_entities returns an empty list when no entities exist."""
    _seed_item(store)
    assert store.get_all_entities() == []


def test_find_similar_entity_returns_match_above_threshold(store):
    """find_similar_entity returns the nearest entity with cosine >= threshold."""
    _seed_item(store)
    vec_a = [1.0] + [0.0] * 1023
    vec_b = [0.99] + [0.01] * 1023  # very similar to vec_a
    vec_c = [0.0, 1.0] + [0.0] * 1022  # orthogonal to vec_a
    store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=vec_a
    )
    store.put_entity(
        name="Oslo", name_norm="oslo", lang="en", type="GPE", embedding=vec_c
    )

    match = store.find_similar_entity(vec_b, threshold=0.85)
    assert match is not None
    assert match["name"] == "NATO"
    assert "entity_id" in match


def test_find_similar_entity_ignores_null_embeddings(store):
    """find_similar_entity must not return entities without embeddings."""
    _seed_item(store)
    store.put_entity(
        name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
    )
    match = store.find_similar_entity([1.0] + [0.0] * 1023, threshold=0.85)
    assert match is None


@pytest.mark.skipif(
    not _PG_UP,
    reason="INFOTRIAGE_TEST_DSN unset or test DB unreachable — db_live test skipped",
)
@pytest.mark.db_live
def test_entity_links_cross_language(tmp_path):
    """Postgres-only: cross-language mentions link to the same entity_id."""
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
        item1 = _make_item("item-en")
        item2 = _make_item("item-ru")
        s.put_item(item1)
        s.put_item(item2)
        entity_id = s.put_entity(
            name="NATO", name_norm="nato", lang="en", type="ORG", embedding=None
        )
        s.link_entity(entity_id, item1.id, "NATO", "en")
        s.link_entity(entity_id, item2.id, "НАТО", "ru")
        links1 = s.get_entity_links(item1.id)
        links2 = s.get_entity_links(item2.id)
        assert len(links1) == 1
        assert len(links2) == 1
        assert links1[0]["entity_id"] == entity_id
        assert links2[0]["entity_id"] == entity_id
        assert links2[0]["mention"] == "НАТО"
