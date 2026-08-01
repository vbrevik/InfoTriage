# alerting worker container (Phase 12 — CNR alerting dissemination)
# Build context: project root (compose uses context: . / dockerfile: apps/alerting/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install worker requirements (includes all transitive deps for the above libs)
COPY apps/alerting/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy worker source
COPY apps/alerting/ .

# 4. Drop root before running (least privilege)
RUN useradd --no-create-home --shell /usr/sbin/nologin alerting
USER alerting

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (T-12-02)
EXPOSE 22050
CMD ["python", "alerting_worker.py"]
