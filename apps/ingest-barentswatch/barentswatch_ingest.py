#!/usr/bin/env python3
"""barentswatch_ingest.py — BarentsWatch AIS adapter for InfoTriage.

Polls the BarentsWatch AIS API for vessel positions in a configured area and
emits each position report as an Item.

Environment variables:
    BARENTSWATCH_CLIENT_ID     — OAuth2 client_id (required)
    BARENTSWATCH_CLIENT_SECRET — OAuth2 client_secret (required)
    BARENTSWATCH_AREA          — bounding box "lat_min,lon_min,lat_max,lon_max"
                                 (optional; falls back to a default Norwegian-Arctic box)
    INFOTRIAGE_PG_DSN          — PostgreSQL libpq connection string
    INFOTRIAGE_AMQP_DSN        — AMQP URL for RabbitMQ
    INFOTRIAGE_BLOB_ROOT       — filesystem root for blob storage (default: data/blobs)
"""
import argparse
import asyncio
import datetime
import logging
import os
from typing import Optional

import httpx
from contracts import BusClient, Item
from ingest_common import build_bus, build_store, parse_since, persist_and_publish
from store._protocol import Store

log = logging.getLogger(__name__)

# Default Admiralty reliability for sensor-derived AIS data.
DEFAULT_ADMIRALTY_RELIABILITY = "A1"

# BarentsWatch endpoints
TOKEN_URL = "https://id.barentswatch.no/connect/token"
HISTORIC_URL = "https://historic.ais.barentswatch.no/v1/historic/combined"

# Default bounding box: a slice of the Norwegian Arctic (Barents Sea / Svalbard-ish)
DEFAULT_AREA = "74.0,15.0,81.0,35.0"

# Retry/backoff configuration for transient API failures
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 2
_RETRYABLE_STATUS_CODES = frozenset({408, 429, 502, 503, 504})

# Module-level token cache: (access_token, expires_at_utc)
_TOKEN_CACHE: Optional[tuple[str, datetime.datetime]] = None


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _load_credentials() -> tuple[str, str]:
    """Load OAuth2 credentials from env vars, exiting cleanly if missing."""
    client_id = os.environ.get("BARENTSWATCH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("BARENTSWATCH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit(
            "BarentsWatch credentials missing. "
            "Set BARENTSWATCH_CLIENT_ID and BARENTSWATCH_CLIENT_SECRET."
        )
    return client_id, client_secret


def _load_area(cli_area: Optional[str] = None) -> str:
    """Return the configured area string, defaulting to env var then DEFAULT_AREA."""
    area = (
        cli_area
        or os.environ.get("BARENTSWATCH_AREA", DEFAULT_AREA).strip()
        or DEFAULT_AREA
    )
    # Validate early so bad configuration fails before any API call.
    try:
        _bbox_to_polygon(area)
    except ValueError as exc:
        log.error(
            "Invalid BARENTSWATCH_AREA / --area: %s. "
            "Expected format: lat_min,lon_min,lat_max,lon_max",
            exc,
        )
        raise SystemExit(1) from exc
    return area


def _clear_token_cache() -> None:
    """Clear the module-level OAuth2 token cache."""
    global _TOKEN_CACHE
    _TOKEN_CACHE = None


def _bbox_to_polygon(area: str) -> list[list[list[float]]]:
    """Convert 'lat_min,lon_min,lat_max,lon_max' to a GeoJSON polygon.

    Raises ValueError if the string is malformed.
    """
    parts = area.split(",")
    if len(parts) != 4:
        raise ValueError(
            f"Invalid area bbox: {area!r}; expected lat_min,lon_min,lat_max,lon_max"
        )
    lat_min, lon_min, lat_max, lon_max = [float(p.strip()) for p in parts]
    return [
        [
            [lon_min, lat_min],
            [lon_max, lat_min],
            [lon_max, lat_max],
            [lon_min, lat_max],
            [lon_min, lat_min],
        ]
    ]


# ---------------------------------------------------------------------------
# OAuth2 + API calls
# ---------------------------------------------------------------------------


async def _get_token(
    client: httpx.AsyncClient, client_id: str, client_secret: str
) -> str:
    """Fetch or return a cached OAuth2 access token for the ais scope."""
    global _TOKEN_CACHE
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    if _TOKEN_CACHE is not None:
        token, expires = _TOKEN_CACHE
        if expires > now + datetime.timedelta(minutes=1):
            return token
        _TOKEN_CACHE = None

    log.debug("fetching BarentsWatch OAuth2 token")
    resp = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "ais",
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    access_token: str = payload["access_token"]
    expires_in = payload.get("expires_in", 3600)
    _TOKEN_CACHE = (access_token, now + datetime.timedelta(seconds=expires_in))
    return access_token


async def fetch_positions(
    client: httpx.AsyncClient,
    token: str,
    area: str,
    since: Optional[datetime.datetime] = None,
) -> list[dict]:
    """Query the BarentsWatch historic AIS API for vessels inside a bounding box.

    Args:
        client: httpx.AsyncClient (or compatible mock).
        token: OAuth2 access token.
        area: bounding box string "lat_min,lon_min,lat_max,lon_max".
        since: UTC datetime; reports older than this are filtered server-side
               via the API's fromTime parameter.

    Returns:
        List of AIS report dictionaries.
    """
    polygon = _bbox_to_polygon(area)
    since_dt = since or (
        datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(hours=1)
    )
    body: dict = {
        "geometry": {
            "type": "Polygon",
            "coordinates": polygon,
        },
        "fromTime": since_dt.isoformat(),
    }
    log.debug("fetching AIS positions for area=%s since=%s", area, since_dt.isoformat())
    resp = await client.post(
        HISTORIC_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()
    # The API returns either a list or a dict with a results key; be tolerant.
    if isinstance(data, list):
        return data
    return data.get("results", []) or []


async def _fetch_with_retries(
    client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    area: str,
    since: Optional[datetime.datetime],
) -> list[dict]:
    """Fetch AIS positions with token-refresh on 401 and retry on transient errors.

    Retries up to ``_MAX_RETRIES`` times with exponential backoff on network
    failures and retryable HTTP status codes (408, 429, 502, 503, 504).
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            token = await _get_token(client, client_id, client_secret)
            return await fetch_positions(client, token, area, since)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                log.warning(
                    "BarentsWatch token rejected; retrying once with fresh token"
                )
                _clear_token_cache()
                token = await _get_token(client, client_id, client_secret)
                return await fetch_positions(client, token, area, since)
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                log.warning(
                    "BarentsWatch API returned %d (attempt %d/%d); retrying",
                    status,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS * (2**attempt))
                continue
            raise
        except httpx.RequestError as exc:
            if attempt < _MAX_RETRIES:
                log.warning(
                    "BarentsWatch API request error: %s (attempt %d/%d); retrying",
                    exc,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                )
                await asyncio.sleep(_RETRY_DELAY_SECONDS * (2**attempt))
                continue
            raise
    # All retry attempts exhausted for retryable request errors.
    # The loop always returns or raises, so this is unreachable; kept for type
    # checker completeness.
    return []


# ---------------------------------------------------------------------------
# AIS report → Item mapping
# ---------------------------------------------------------------------------


def _position_to_item(data: dict) -> Item:
    """Map a raw BarentsWatch AIS report to an InfoTriage Item."""
    mmsi = data.get("mmsi", "unknown")
    name = data.get("name") or data.get("vesselName") or f"vessel-{mmsi}"
    lat = data.get("latitude", data.get("lat"))
    lon = data.get("longitude", data.get("lon"))
    msg_time = data.get("msgtime") or data.get("timestamp")
    if msg_time:
        ts = datetime.datetime.fromisoformat(msg_time.replace("Z", "+00:00"))
    else:
        ts = datetime.datetime.now(tz=datetime.timezone.utc)
    sog = data.get("speedOverGround", data.get("sog"))
    cog = data.get("courseOverGround", data.get("cog"))
    destination = data.get("destination", "Unknown")
    title = f"AIS: {name} ({mmsi}) near {destination}"
    summary_parts = [f"MMSI: {mmsi}"]
    if lat is not None and lon is not None:
        summary_parts.append(f"Position: {lat:.5f}, {lon:.5f}")
    if sog is not None:
        summary_parts.append(f"SOG: {sog} kn")
    if cog is not None:
        summary_parts.append(f"COG: {cog}°")
    item = Item(
        source="barentswatch",
        source_type="ais",
        url=f"urn:mmsi:{mmsi}",
        title=title,
        ts=ts,
        lang="und",
        summary="; ".join(summary_parts),
        discipline="MASINT/AIS",
        admiralty_reliability=DEFAULT_ADMIRALTY_RELIABILITY,
    )
    return item


# ---------------------------------------------------------------------------
# Main ingest coroutine
# ---------------------------------------------------------------------------


async def ingest(
    since: Optional[str] = None,
    area: Optional[str] = None,
    dry_run: bool = False,
    _client: Optional[httpx.AsyncClient] = None,
) -> list[Item]:
    """Fetch BarentsWatch AIS positions and emit Items.

    Args:
        since: Relative window like "24h" or "7d".
        area: Bounding box "lat_min,lon_min,lat_max,lon_max" (defaults to env).
        dry_run: If True, build Items but do not persist or publish.
        _client: Optional injected httpx.AsyncClient for tests.

    Returns:
        List of Items produced.
    """
    client_id, client_secret = _load_credentials()
    area_str = _load_area(area)
    since_str = since or os.environ.get("BARENTSWATCH_SINCE", "24h")
    since_dt = parse_since(since_str)

    produced: list[Item] = []
    log.info(
        "barentswatch ingest start: area=%s since=%s dry_run=%s",
        area_str,
        since_str,
        dry_run,
    )

    store: Optional[Store] = None
    bus: Optional[BusClient] = None
    if not dry_run:
        store = build_store()
        bus = build_bus()

    client_ctx = _client or httpx.AsyncClient()
    async with client_ctx as client:
        positions = await _fetch_with_retries(
            client, client_id, client_secret, area_str, since_dt
        )
        log.info("barentswatch fetched %d positions", len(positions))
        for pos in positions:
            item = _position_to_item(pos)
            produced.append(item)
            if dry_run:
                continue
            assert store is not None and bus is not None
            await persist_and_publish(store, bus, item)

    if not dry_run and bus is not None:
        close_fn = getattr(bus, "close", None)
        if callable(close_fn):
            await close_fn()

    log.info("barentswatch ingest complete: %d items produced", len(produced))
    return produced


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest BarentsWatch AIS vessel positions into InfoTriage."
    )
    parser.add_argument(
        "--since",
        default=os.environ.get("BARENTSWATCH_SINCE", "24h"),
        help="Window like 24h or 7d",
    )
    parser.add_argument(
        "--area",
        default=os.environ.get("BARENTSWATCH_AREA", DEFAULT_AREA),
        help="Bounding box lat_min,lon_min,lat_max,lon_max",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build Items without persisting or publishing",
    )
    return parser


def main() -> None:
    """Synchronous CLI entry point."""
    parser = _build_argument_parser()
    args = parser.parse_args()
    import asyncio

    asyncio.run(ingest(since=args.since, area=args.area, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
