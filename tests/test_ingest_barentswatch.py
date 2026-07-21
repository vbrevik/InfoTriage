#!/usr/bin/env python3
"""test_ingest_barentswatch.py — unit tests for the BarentsWatch AIS adapter."""
import datetime
import sys
from pathlib import Path

import httpx
import pytest

# The adapter lives under a hyphenated directory; add it to the path for import.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "apps" / "ingest-barentswatch")
)
import barentswatch_ingest


@pytest.fixture
def fake_position():
    """Return a fake BarentsWatch AIS report."""
    return {
        "mmsi": 123456789,
        "name": "Test Vessel",
        "latitude": 78.22,
        "longitude": 15.65,
        "msgtime": "2026-07-21T10:00:00Z",
        "speedOverGround": 12.5,
        "courseOverGround": 95,
        "destination": "Longyearbyen",
    }


@pytest.fixture
def fake_client(fake_position):
    """Return a fake httpx.AsyncClient that returns one AIS position."""

    class _FakeResponse:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("HTTP error")

    class _FakeClient:
        def __init__(self):
            self.token_calls = 0
            self.post_urls = []

        async def post(self, url, **kwargs):
            self.post_urls.append(url)
            if "connect/token" in url:
                return _FakeResponse({"access_token": "fake-token", "expires_in": 3600})
            return _FakeResponse([fake_position])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    return _FakeClient()


@pytest.fixture
def creds_env(monkeypatch):
    """Provide fake BarentsWatch OAuth2 credentials for tests that call ingest()."""
    monkeypatch.setenv("BARENTSWATCH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("BARENTSWATCH_CLIENT_SECRET", "fake-client-secret")
    return monkeypatch


@pytest.mark.asyncio
async def test_ingest_emits_item_with_discipline_and_reliability(
    fake_client, fake_position, creds_env
):
    """Adapter emits Items with MASINT/AIS discipline and default Admiralty rating."""
    barentswatch_ingest._TOKEN_CACHE = None
    items = await barentswatch_ingest.ingest(
        since="7d",
        area="74.0,15.0,81.0,35.0",
        dry_run=True,
        _client=fake_client,
    )
    assert len(items) == 1
    item = items[0]
    assert item.source_type == "ais"
    assert item.discipline == "MASINT/AIS"
    assert item.admiralty_reliability == "A1"
    assert item.url == "urn:mmsi:123456789"
    assert "Test Vessel" in item.title
    assert "Longyearbyen" in item.title


@pytest.mark.asyncio
async def test_ingest_dry_run_does_not_persist(
    monkeypatch, fake_client, fake_position, creds_env
):
    """In dry-run mode no store or bus calls are made."""

    def _fake_build_store():
        raise AssertionError("build_store should not be called in dry run")

    def _fake_build_bus():
        raise AssertionError("build_bus should not be called in dry run")

    monkeypatch.setattr(barentswatch_ingest, "build_store", _fake_build_store)
    monkeypatch.setattr(barentswatch_ingest, "build_bus", _fake_build_bus)
    barentswatch_ingest._TOKEN_CACHE = None

    items = await barentswatch_ingest.ingest(
        since="7d",
        area="74.0,15.0,81.0,35.0",
        dry_run=True,
        _client=fake_client,
    )
    assert len(items) == 1


def test_bbox_to_polygon_parses_simple_bbox():
    """_bbox_to_polygon converts a bbox string to a GeoJSON polygon."""
    polygon = barentswatch_ingest._bbox_to_polygon("74.0,15.0,81.0,35.0")
    assert polygon == [
        [
            [15.0, 74.0],
            [35.0, 74.0],
            [35.0, 81.0],
            [15.0, 81.0],
            [15.0, 74.0],
        ]
    ]


def test_bbox_to_polygon_invalid_raises():
    """_bbox_to_polygon rejects malformed bbox strings."""
    with pytest.raises(ValueError, match="Invalid area bbox"):
        barentswatch_ingest._bbox_to_polygon("not,a,bbox")


def test_position_to_item_falls_back_when_name_missing():
    """_position_to_item builds a title even when optional fields are absent."""
    pos = {
        "mmsi": 987654321,
        "msgtime": "2026-07-21T12:00:00Z",
    }
    item = barentswatch_ingest._position_to_item(pos)
    assert item.source_type == "ais"
    assert item.discipline == "MASINT/AIS"
    assert "987654321" in item.title


def test_parse_since_hours_and_days():
    """parse_since converts relative windows to UTC datetimes."""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    dt = barentswatch_ingest.parse_since("24h")
    assert now - datetime.timedelta(hours=24, minutes=1) < dt < now

    dt = barentswatch_ingest.parse_since("7d")
    assert (
        now - datetime.timedelta(days=7, minutes=1)
        < dt
        < now - datetime.timedelta(days=6)
    )


def test_parse_since_invalid_raises():
    """parse_since rejects malformed window strings."""
    with pytest.raises(ValueError, match="Invalid --since"):
        barentswatch_ingest.parse_since("1week")


def test_load_area_prefers_cli():
    """_load_area prefers explicit CLI value over env var."""
    assert barentswatch_ingest._load_area("1,2,3,4") == "1,2,3,4"


def test_missing_credentials_aborts(monkeypatch):
    """_load_credentials exits cleanly when OAuth2 credentials are missing."""
    monkeypatch.delenv("BARENTSWATCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("BARENTSWATCH_CLIENT_SECRET", raising=False)
    with pytest.raises(SystemExit):
        barentswatch_ingest._load_credentials()


@pytest.mark.asyncio
async def test_ingest_retries_on_401_then_succeeds(
    fake_position, creds_env, monkeypatch
):
    """A 401 from the AIS API triggers one token refresh and retry."""
    calls = {"fetch": 0}

    class _FakeResponse:
        def __init__(self, payload, status=200):
            self._payload = payload
            self.status_code = status

        def json(self):
            return self._payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("HTTP error")

    class _401Client:
        def __init__(self):
            self.post_urls = []

        async def post(self, url, **kwargs):
            self.post_urls.append(url)
            if "connect/token" in url:
                return _FakeResponse({"access_token": "fake-token", "expires_in": 3600})
            calls["fetch"] += 1
            if calls["fetch"] == 1:
                request = httpx.Request("POST", url)
                response = httpx.Response(401, request=request)
                raise httpx.HTTPStatusError(
                    "Unauthorized", request=request, response=response
                )
            return _FakeResponse([fake_position])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    barentswatch_ingest._TOKEN_CACHE = (
        "stale-token",
        datetime.datetime.now(tz=datetime.timezone.utc),
    )
    items = await barentswatch_ingest.ingest(
        since="7d",
        area="74.0,15.0,81.0,35.0",
        dry_run=True,
        _client=_401Client(),
    )
    assert len(items) == 1
    assert calls["fetch"] == 2
    # Token cache should have been refreshed (stale token evicted, new token set).
    assert barentswatch_ingest._TOKEN_CACHE is not None
    assert barentswatch_ingest._TOKEN_CACHE[0] == "fake-token"
