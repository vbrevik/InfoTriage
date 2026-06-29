#!/usr/bin/env python3
"""main.py — FastAPI trigger app for ingest-youtube.

Exposes:
    POST /run    — start an ingest run (single-instance lock via make_trigger_app)
    GET  /health — liveness probe

Usage:
    uvicorn main:app --host 0.0.0.0 --port 8000

The POST /run handler returns 200 + {"status": "started"} if idle, or
409 + {"status": "already_running"} if a run is already in progress.
"""
from ingest_common import make_trigger_app

from youtube_ingest import ingest

app = make_trigger_app(ingest, name="ingest-youtube")
