# ingest-obsidian — Obsidian Web Clipper clip ingestion adapter (D-10/D-11)
# Build context: project root (docker build -f apps/ingest-obsidian/Dockerfile .)
# No credentials in image layers (D-07/NF-6): all secrets come from .env via env_file.
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs without transitive deps
#    (their transitive deps come from requirements.txt below)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# 2. Install adapter requirements (all transitive deps)
COPY apps/ingest-obsidian/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy adapter source
COPY apps/ingest-obsidian/ .

# Vault articles-inbox is bind-mounted read-only at container runtime:
#   ${OBSIDIAN_VAULT_PATH}/articles-inbox:/vault/articles-inbox:ro  (Plan 06)
# The OBSIDIAN_VAULT_PATH env var points to /vault inside the container.

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
