# scheduler container — APScheduler 3.x cron driver (D-04, SPEC R5)
# Build context: project root (compose uses context: . / dockerfile: apps/scheduler/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Install scheduler requirements + JSON formatter for structured logging (Phase 7)
COPY apps/scheduler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt json-log-formatter

# 2. Install the contracts lib (--no-deps; transitive runtime deps live in
#    requirements.txt — see the appended pydantic/PyYAML/aio-pika entries).
#    scheduler_main.py does `from contracts import setup_logging`, so the package
#    must be importable. This was missing since Phase 5 — masked by the absence
#    of a live scheduler container start in the test suite. (Phase 7 07-03
#    runtime-deps fix.)
COPY libs/contracts /build/contracts
RUN pip install --no-deps /build/contracts

# 3. Copy scheduler source
COPY apps/scheduler/ .

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
CMD ["python", "main.py"]
