#!/usr/bin/env python3
"""FastAPI integration tests for /sab view endpoints (ADR-012).

These tests exercise the full FastAPI app with the Postgres store mocked,
verifying that COP, CIP, and CRP views are wired correctly through the
HTTP surface.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_row(
    item_id: str = "item-1",
    ccir: str = "PIR-1",
    cnr: str = "II",
    score: int = 8,
    pmesii: str = "Military",
    tessoc: str = "Sabotage",
    title: str = "Test Title",
    source: str = "TestSource",
    url: str = "http://example.com",
    summary: str = "Test summary",
    embedding: list[float] | None = None,
) -> dict:
    return {
        "item_id": item_id,
        "ccir": ccir,
        "cnr": cnr,
        "score": score,
        "bucket": "keep",
        "why": title,
        "pmesii": pmesii,
        "tessoc": tessoc,
        "title": title,
        "source": source,
        "url": url,
        "summary": summary,
        "embedding": embedding,
    }


@pytest.fixture
def sample_rows():
    # Provide dummy embeddings so semantic clustering treats each row as a
    # singleton cluster rather than dropping items without embeddings.
    return [
        # COP match
        _make_row(
            item_id="cop-1",
            ccir="FFIR-1",
            pmesii="Political",
            tessoc="Espionage",
            title="COP Item",
            embedding=[0.1, 0.2, 0.3],
        ),
        # CIP match
        _make_row(
            item_id="cip-1",
            ccir="PIR-4",
            pmesii="Information",
            tessoc="Sabotage",
            title="CIP Item",
            embedding=[0.4, 0.5, 0.6],
        ),
        # Neither COP nor CIP
        _make_row(
            item_id="other-1",
            ccir="PIR-5",
            pmesii="Social",
            tessoc="none",
            title="Other Item",
            embedding=[0.7, 0.8, 0.9],
        ),
    ]


@pytest.fixture
def client(sample_rows):
    from fastapi.testclient import TestClient
    from apps.brief import main as brief_main

    # Patch _fetch_rows so the endpoint never touches Postgres/RabbitMQ.
    # The view-filter logic in the endpoint is still exercised.
    with patch.object(brief_main, "_fetch_rows", return_value=sample_rows):
        with patch.dict(os.environ, {"BRIEF_CONSUME": "0"}, clear=False):
            yield TestClient(brief_main.app)


def test_sab_default_returns_html(client):
    """Default /sab returns HTML."""
    resp = client.get("/sab")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_sab_view_cop_filters_items(client):
    """?view=cop returns HTML containing only COP-matching items."""
    resp = client.get("/sab?view=cop")
    assert resp.status_code == 200
    html = resp.text
    assert "COP Item" in html
    assert "CIP Item" not in html
    assert "Other Item" not in html


def test_sab_view_cip_filters_items(client):
    """?view=cip returns HTML containing only CIP-matching items."""
    resp = client.get("/sab?view=cip")
    assert resp.status_code == 200
    html = resp.text
    assert "CIP Item" in html
    assert "COP Item" not in html
    assert "Other Item" not in html


def test_sab_view_crp_filters_by_ccir(client):
    """?view=crp&ccir=PIR-4 returns only matching CCIR."""
    resp = client.get("/sab?view=crp&ccir=PIR-4")
    assert resp.status_code == 200
    html = resp.text
    assert "CIP Item" in html
    assert "COP Item" not in html
    assert "Other Item" not in html


def test_sab_view_crp_requires_param(client):
    """CRP view without any filter params returns 422."""
    resp = client.get("/sab?view=crp")
    assert resp.status_code == 422


def test_sab_mode_list_view_cop(client):
    """?mode=list&view=cop returns markdown list filtered to COP."""
    resp = client.get("/sab?mode=list&view=cop")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    text = resp.text
    assert "COP Item" in text
    assert "CIP Item" not in text
    assert "Other Item" not in text


def test_sab_mode_list_view_cip(client):
    """?mode=list&view=cip returns markdown list filtered to CIP."""
    resp = client.get("/sab?mode=list&view=cip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    text = resp.text
    assert "CIP Item" in text
    assert "COP Item" not in text
    assert "Other Item" not in text


def test_sab_mode_list_view_crp(client):
    """?mode=list&view=crp&ccir=PIR-4 returns markdown list filtered by CRP."""
    resp = client.get("/sab?mode=list&view=crp&ccir=PIR-4")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    text = resp.text
    assert "CIP Item" in text
    assert "COP Item" not in text
    assert "Other Item" not in text


def test_sab_view_crp_filters_by_pmesii(client):
    """?view=crp&pmesii=Information returns only matching PMESII domain."""
    resp = client.get("/sab?view=crp&pmesii=Information")
    assert resp.status_code == 200
    html = resp.text
    assert "CIP Item" in html
    assert "COP Item" not in html
    assert "Other Item" not in html


def test_sab_view_crp_filters_by_tessoc(client):
    """?view=crp&tessoc=Sabotage returns only matching TESSOC category."""
    resp = client.get("/sab?view=crp&tessoc=Sabotage")
    assert resp.status_code == 200
    html = resp.text
    assert "CIP Item" in html
    assert "COP Item" not in html
    assert "Other Item" not in html


def test_sab_view_crp_filters_by_min_score(client):
    """?view=crp&min_score=9 returns only items with score >= 9."""
    resp = client.get("/sab?view=crp&min_score=9")
    assert resp.status_code == 200
    html = resp.text
    assert "COP Item" not in html
    assert "CIP Item" not in html
    assert "Other Item" not in html


def test_sab_view_unknown_returns_422(client):
    """An unknown view value returns a 422 error."""
    resp = client.get("/sab?view=unknown")
    assert resp.status_code == 422


# ---- /vault endpoint tests --------------------------------------------------


def test_vault_default_returns_markdown(client):
    """/vault returns the Obsidian SAB projection as markdown."""
    resp = client.get("/vault")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    text = resp.text
    assert "# InfoTriage · Obsidian SAB" in text
    assert "COP Item" in text
    assert "CIP Item" in text
    assert "Other Item" in text


def test_vault_view_cop_filters_items(client):
    """?view=cop returns vault markdown containing only COP-matching items."""
    resp = client.get("/vault?view=cop")
    assert resp.status_code == 200
    text = resp.text
    assert "COP Item" in text
    assert "CIP Item" not in text
    assert "Other Item" not in text


def test_vault_view_cip_filters_items(client):
    """?view=cip returns vault markdown containing only CIP-matching items."""
    resp = client.get("/vault?view=cip")
    assert resp.status_code == 200
    text = resp.text
    assert "CIP Item" in text
    assert "COP Item" not in text
    assert "Other Item" not in text


def test_vault_view_crp_filters_by_ccir(client):
    """?view=crp&ccir=PIR-4 returns only matching CCIR."""
    resp = client.get("/vault?view=crp&ccir=PIR-4")
    assert resp.status_code == 200
    text = resp.text
    assert "CIP Item" in text
    assert "COP Item" not in text
    assert "Other Item" not in text


def test_vault_view_crp_requires_param(client):
    """CRP view without any filter params returns 422."""
    resp = client.get("/vault?view=crp")
    assert resp.status_code == 422


def test_vault_view_unknown_returns_422(client):
    """An unknown view value on /vault returns a 422 error."""
    resp = client.get("/vault?view=unknown")
    assert resp.status_code == 422
