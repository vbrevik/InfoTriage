# scheduler container — APScheduler 3.x cron driver (D-04, SPEC R5)
# Build context: project root (compose uses context: . / dockerfile: apps/scheduler/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# Install scheduler requirements + JSON formatter for structured logging (Phase 7)
COPY apps/scheduler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt json-log-formatter

# Copy scheduler source
COPY apps/scheduler/ .

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
CMD ["python", "main.py"]
