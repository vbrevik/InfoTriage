#!/usr/bin/env python3
"""test_ingest_telegram.py — unit tests for the Telegram SOCMINT adapter."""
import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# The adapter lives under a hyphenated directory; add it to the path for import.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "apps" / "ingest-telegram")
)
import telegram_ingest


@pytest.fixture
def fake_message():
    """Return a fake Telethon message object."""
    return SimpleNamespace(
        id=42,
        date=datetime.datetime(2026, 7, 21, 10, 0, 0, tzinfo=datetime.timezone.utc),
        text="Breaking news from the front line.\nMore details follow.",
    )


@pytest.fixture
def fake_client(fake_message):
    """Return a fake Telegram client that yields one message per channel."""

    class _FakeClient:
        def __init__(self):
            self._entities = {}

        async def get_entity(self, channel):
            entity = SimpleNamespace(id=channel)
            self._entities[channel] = entity
            return entity

        def iter_messages(self, entity, limit=None, offset_date=None):
            return _FakeAsyncIterator([fake_message])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    return _FakeClient()


class _FakeAsyncIterator:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


@pytest.mark.asyncio
async def test_ingest_emits_item_with_discipline_and_reliability(
    fake_client, fake_message
):
    """Adapter emits Items with SOCMINT discipline and default Admiralty rating."""
    items = await telegram_ingest.ingest(
        since="7d",
        channels=["testchannel"],
        dry_run=True,
        _client=fake_client,
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_type == "telegram"
    assert item.discipline == "SOCMINT"
    assert item.admiralty_reliability == "C3"
    assert item.url == "https://t.me/testchannel/42"
    assert "front line" in item.title


@pytest.mark.asyncio
async def test_ingest_title_falls_back_to_channel_and_id(fake_client):
    """Empty message text produces a fallback title."""
    fake_client.iter_messages = (
        lambda entity, limit=None, offset_date=None: _FakeAsyncIterator(
            [
                SimpleNamespace(
                    id=7, date=datetime.datetime.now(tz=datetime.timezone.utc), text=""
                )
            ]
        )
    )

    items = await telegram_ingest.ingest(
        since="7d",
        channels=["testchannel"],
        dry_run=True,
        _client=fake_client,
    )
    assert items[0].title == "telegram:testchannel:7"


@pytest.mark.asyncio
async def test_ingest_no_channels_raises():
    """ingest() exits when no channels are configured."""
    with pytest.raises(SystemExit):
        await telegram_ingest.ingest(
            since="7d", channels=[], dry_run=True, _client=None
        )


@pytest.mark.asyncio
async def test_ingest_dry_run_does_not_persist(monkeypatch, fake_client, fake_message):
    """In dry-run mode no store or bus calls are made."""

    def _fake_build_store():
        raise AssertionError("build_store should not be called in dry run")

    def _fake_build_bus():
        raise AssertionError("build_bus should not be called in dry run")

    monkeypatch.setattr(telegram_ingest, "build_store", _fake_build_store)
    monkeypatch.setattr(telegram_ingest, "build_bus", _fake_build_bus)

    items = await telegram_ingest.ingest(
        since="7d",
        channels=["testchannel"],
        dry_run=True,
        _client=fake_client,
    )
    assert len(items) == 1


@pytest.mark.asyncio
async def test_message_to_item_sets_discipline_and_reliability(fake_client):
    """Every mapped item carries SOCMINT discipline and the default rating."""

    class _BadMessage:
        id = 1
        date = datetime.datetime.now(tz=datetime.timezone.utc)
        text = "x"

    item = telegram_ingest._message_to_item("ch", _BadMessage())
    assert item.discipline == "SOCMINT"
    assert item.admiralty_reliability == "C3"


def test_parse_since_hours_and_days():
    """parse_since converts relative windows to UTC datetimes."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    dt = telegram_ingest.parse_since("24h")
    assert now - datetime.timedelta(hours=24, minutes=1) < dt < now

    dt = telegram_ingest.parse_since("7d")
    assert (
        now - datetime.timedelta(days=7, minutes=1)
        < dt
        < now - datetime.timedelta(days=6)
    )


def test_parse_since_invalid_raises():
    """parse_since rejects malformed window strings."""
    with pytest.raises(ValueError, match="Invalid --since"):
        telegram_ingest.parse_since("1week")


def test_load_channels_prefers_cli():
    """load_channels prefers explicit CLI list over env var."""
    assert telegram_ingest.load_channels(["a", "b"]) == ["a", "b"]


def test_create_client_raises_without_credentials(monkeypatch):
    """_create_client exits cleanly when Telegram credentials are missing."""
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    with pytest.raises(SystemExit):
        telegram_ingest._create_client()
