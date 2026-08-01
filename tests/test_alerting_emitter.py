"""tests/test_alerting_emitter.py — SPEC R1 dual-trigger exactly-once egress.

Both trigger orders (verdict.ready first vs sab.published first) collapse to
exactly one push via the atomic dedupe claim (Task 1); non-CAT-I inputs on
either event shape produce zero egress; a TTL-expired identity alerts again.
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from contracts import Item
from store import InMemoryStore

from emitter import _extract_cat_i_item_ids, handle_sab_published, handle_verdict_ready
from outbox import NtfyClient


def _make_item(url_seed: str) -> Item:
    return Item(
        source="Test Source",
        source_type="rss",
        url=f"https://example.com/{url_seed}",
        title="A CAT I test item",
        ts=datetime.now(tz=timezone.utc),
        lang="en",
        summary="fallback summary text",
    )


def _seed(store: InMemoryStore, item: Item, *, cnr: str, why: str = "rationale") -> str:
    store.put_item(item)
    store.put_enrichment(
        item.id,
        {
            "ccir": None,
            "cnr": cnr,
            "score": 9,
            "bucket": "keep",
            "why": why,
            "pmesii": "",
            "tessoc": None,
        },
    )
    return item.id


def _verdict_ready(item_id: str, cnr) -> dict:
    payload: dict = {"event": "verdict.ready", "item_id": item_id}
    if cnr is not None:
        payload["cnr"] = cnr
    return payload


def _sab_published(item_refs: list[dict]) -> dict:
    return {"event": "sab.published", "item_refs": item_refs}


def test_verdict_ready_then_sab_published_yields_exactly_one_request(
    stub_ntfy_server, tmp_path
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("order-1")
    item_id = _seed(store, item, cnr="I")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    asyncio.run(handle_verdict_ready(_verdict_ready(item_id, "I"), store, client))
    asyncio.run(
        handle_sab_published(
            _sab_published([{"item_id": item_id, "cnr": "I"}]), store, client
        )
    )

    assert len(handler_cls.requests) == 1


def test_sab_published_then_verdict_ready_yields_exactly_one_request(
    stub_ntfy_server, tmp_path
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("order-2")
    item_id = _seed(store, item, cnr="I")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    asyncio.run(
        handle_sab_published(
            _sab_published([{"item_id": item_id, "cnr": "I"}]), store, client
        )
    )
    asyncio.run(handle_verdict_ready(_verdict_ready(item_id, "I"), store, client))

    assert len(handler_cls.requests) == 1


def test_sab_published_non_cat_i_refs_produce_zero_requests(stub_ntfy_server, tmp_path):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item_a = _make_item("non-cat-i-a")
    item_b = _make_item("non-cat-i-b")
    item_id_a = _seed(store, item_a, cnr="II")
    item_id_b = _seed(store, item_b, cnr="Routine")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    asyncio.run(
        handle_sab_published(
            _sab_published(
                [
                    {"item_id": item_id_a, "cnr": "II"},
                    {"item_id": item_id_b, "cnr": "Routine"},
                ]
            ),
            store,
            client,
        )
    )

    assert len(handler_cls.requests) == 0


@pytest.mark.parametrize("cnr", [None, "II", "Routine"])
def test_verdict_ready_non_cat_i_or_missing_cnr_produces_zero_requests_no_exception(
    stub_ntfy_server, tmp_path, cnr
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item(f"cnr-{cnr}")
    item_id = _seed(store, item, cnr=cnr or "none")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    asyncio.run(handle_verdict_ready(_verdict_ready(item_id, cnr), store, client))

    assert len(handler_cls.requests) == 0


def test_verdict_ready_cat_i_missing_enrichment_row_produces_zero_requests_and_warns(
    stub_ntfy_server, tmp_path, caplog
):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("missing-enrichment")
    store.put_item(item)  # deliberately no put_enrichment call
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    with caplog.at_level("WARNING"):
        asyncio.run(handle_verdict_ready(_verdict_ready(item.id, "I"), store, client))

    assert len(handler_cls.requests) == 0
    assert any("missing item or enrichment" in rec.message for rec in caplog.records)


def test_ttl_expired_identity_alerts_again(stub_ntfy_server, tmp_path):
    base_url, handler_cls = stub_ntfy_server
    store = InMemoryStore(blob_root=tmp_path)
    item = _make_item("ttl-refire")
    item_id = _seed(store, item, cnr="I")
    client = NtfyClient(base_url, "secret-token", "cnr-cat-i")

    now = datetime.now(tz=timezone.utc)
    asyncio.run(
        handle_verdict_ready(_verdict_ready(item_id, "I"), store, client, now=now)
    )
    later = now + timedelta(hours=25)
    asyncio.run(
        handle_verdict_ready(_verdict_ready(item_id, "I"), store, client, now=later)
    )

    assert len(handler_cls.requests) == 2


def test_extract_cat_i_item_ids_filters_by_ref_level_cnr():
    payload = _sab_published(
        [
            {"item_id": "a", "cnr": "I"},
            {"item_id": "b", "cnr": "II"},
            {"item_id": "c", "cnr": "none"},
            {"item_id": "d", "cnr": "I"},
        ]
    )

    assert list(_extract_cat_i_item_ids(payload)) == ["a", "d"]


def test_handle_sab_published_does_not_read_item_id_from_message_headers():
    """Source check: for sab.published the message header identifies the SAB
    snapshot, not an article — the sab branch must never index it for an
    item id (apps/brief/consumer.py publishes with item_id=the snapshot day
    marker, not an article id).
    """
    source = inspect.getsource(handle_sab_published)
    assert 'headers["item_id"]' not in source
    assert "message.headers" not in source


def test_routing_key_to_queue_binds_sab_published_to_q_alerting_second():
    from contracts._bus_rabbitmq import ROUTING_KEY_TO_QUEUE

    assert ROUTING_KEY_TO_QUEUE["sab.published"] == ["q.notify", "q.alerting"]
