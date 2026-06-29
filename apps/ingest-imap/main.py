#!/usr/bin/env python3
"""main.py — ingest-imap adapter entry point.

Wires the IMAP ingest coroutine into the shared FastAPI trigger app (D-01):
  POST /run    — start an IMAP ingest run (single-instance lock)
  GET  /health — liveness probe (always 200)

Run: uvicorn main:app --host 0.0.0.0 --port 8000
"""
from ingest_common import make_trigger_app

from imap_ingest import ingest

app = make_trigger_app(ingest, name="ingest-imap")
