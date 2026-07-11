# ingest-imap adapter container (D-10/D-11)
# Build context: project root (compose uses context: . / dockerfile: apps/ingest-imap/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# 2. Install adapter requirements + JSON formatter for structured container logging (Phase 7)
COPY apps/ingest-imap/requirements.txt .
RUN pip install -r requirements.txt json-log-formatter

# 3. Copy adapter source
COPY apps/ingest-imap/ .

# Phase 7 07-02: ship uvicorn JSON access-log config so HTTP access logs join
# the structured-logging stream (paired with contracts.setup_logging).
COPY libs/contracts/src/contracts/uvicorn-log-config.json /app/uvicorn-log-config.json

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/uvicorn-log-config.json"]
