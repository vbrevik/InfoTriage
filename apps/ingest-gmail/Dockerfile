FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps: transitive deps come from requirements.txt)
#    D-10: COPY + pip install --no-deps pattern for all local libs
COPY libs/contracts /build/contracts
COPY libs/store /build/store
COPY libs/ingest_common /build/ingest_common
RUN pip install --no-deps /build/contracts /build/store /build/ingest_common

# 2. Install adapter requirements (includes all transitive deps for the above)
COPY apps/ingest-gmail/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy adapter source
COPY apps/ingest-gmail/ .

# SECURITY: No ARG/ENV carrying CLIENT_SECRET, REFRESH_TOKEN, or CLIENT_ID.
# All credentials come from .env via docker-compose env_file at runtime (NF-6, D-07).

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
