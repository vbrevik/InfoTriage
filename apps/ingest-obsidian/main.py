#!/usr/bin/env python3
"""main.py — FastAPI trigger app for ingest-obsidian (D-01/D-02).

Builds the POST /run + GET /health FastAPI app via make_trigger_app().
"""
from ingest_common import make_trigger_app

from obsidian_ingest import ingest

app = make_trigger_app(ingest, name="ingest-obsidian")
