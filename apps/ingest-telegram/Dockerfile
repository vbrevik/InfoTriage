# ingest-telegram adapter (Phase 11)
# Build context: project root (compose uses context: . / dockerfile: apps/ingest-telegram/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs without their external deps
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# 2. Install adapter dependencies + JSON formatter for structured logging (Phase 7)
COPY apps/ingest-telegram/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt json-log-formatter

# 3. Copy adapter source
COPY apps/ingest-telegram/ .

COPY libs/contracts/src/contracts/uvicorn-log-config.json /app/uvicorn-log-config.json

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/uvicorn-log-config.json"]
