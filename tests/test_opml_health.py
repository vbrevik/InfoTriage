"""Tests for opml-health admin dashboard (Phase 7)."""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Ensure project root is on sys.path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_admin_module_imports():
    """Verify admin.py imports without requiring live services."""
    from apps.opml_health.admin import app, SERVICES  # noqa: F401

    assert len(SERVICES) > 0, "SERVICES registry must not be empty"


def test_services_registry():
    """Verify all expected services are in the registry."""
    from apps.opml_health.admin import SERVICES

    names = [s[0] for s in SERVICES]
    expected = {"ingest-imap", "triage", "brief", "freshrss", "rssbridge", "feeds"}
    for exp in expected:
        assert exp in names, f"Missing service in registry: {exp}"


def test_health_endpoint_structure():
    """Verify /health returns 200 with 'ok' body."""
    from apps.opml_health.admin import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_admin_health_all_up():
    """When all services respond 200, overall status is 'up'."""
    from apps.opml_health.admin import app, SERVICES
    from fastapi.testclient import TestClient

    async def mock_get(*args, **kwargs):
        resp = AsyncMock()
        resp.status_code = 200
        return resp

    with patch("apps.opml_health.admin.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_client

        client = TestClient(app)
        resp = client.get("/admin/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "up"
        assert data["up"] == len(SERVICES)
        assert data["down"] == 0


@pytest.mark.asyncio
async def test_admin_health_some_down():
    """When at least one service is down, overall status is 'degraded'."""
    from apps.opml_health.admin import app
    from fastapi.testclient import TestClient

    async def mock_get(*args, **kwargs):
        url = kwargs.get("url") or (args[0] if args else "")
        # Mark the triage service as down; all others up
        if "triage" in url:
            raise TimeoutError("triage unreachable")
        resp = AsyncMock()
        resp.status_code = 200
        return resp

    with patch("apps.opml_health.admin.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_client

        client = TestClient(app)
        resp = client.get("/admin/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["down"] >= 1


@pytest.mark.asyncio
async def test_admin_health_all_down():
    """When all services are down, overall status is 'down'."""
    from apps.opml_health.admin import app, SERVICES
    from fastapi.testclient import TestClient

    async def mock_get(*args, **kwargs):
        raise ConnectionError("connection refused")

    with patch("apps.opml_health.admin.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_client

        client = TestClient(app)
        resp = client.get("/admin/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "down"
        assert data["down"] == len(SERVICES)


@pytest.mark.asyncio
async def test_admin_health_error_handling():
    """Services that raise exceptions are reported as 'down'."""
    from apps.opml_health.admin import app, SERVICES
    from fastapi.testclient import TestClient

    async def mock_get(*args, **kwargs):
        raise TimeoutError("read timed out")

    with patch("apps.opml_health.admin.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_client

        client = TestClient(app)
        resp = client.get("/admin/health")
        assert resp.status_code == 200
        data = resp.json()
        # All services show error, overall is down
        assert data["down"] == len(SERVICES)
