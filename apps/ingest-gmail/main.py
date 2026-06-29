#!/usr/bin/env python3
"""main.py — ingest-gmail FastAPI trigger app.

Wraps gmail_ingest.ingest() in the standard make_trigger_app single-instance
lock pattern (D-01/D-02). Uvicorn serves on 0.0.0.0:8000 (port 22012 on host,
per D-03).

Run in container:
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
from gmail_ingest import ingest
from ingest_common import make_trigger_app

app = make_trigger_app(ingest, name="ingest-gmail")
