# InfoTriage MVP poller container — one synchronous loop instead of the event bus.
# Build context: project root (compose uses context: . / dockerfile: apps/mvp/Dockerfile)
#
# Layout follows apps/brief/Dockerfile: apps/ tree preserved so cross-app
# imports (triage_score, emitter, outbox, vault_writer) resolve over PYTHONPATH.
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install worker requirements (includes all transitive deps for the above libs)
COPY apps/mvp/requirements.txt .
RUN pip install -r requirements.txt json-log-formatter

# 3. Copy source — apps/ layout preserved so this poller reaches the shipped
#    modules as importable packages: triage_score (scorer), alerting lane
#    (emitter/outbox/deep_link/throttle/dedupe), brief (vault_writer).
ENV PYTHONPATH=/app:/app/apps/triage:/app/apps/alerting:/app/apps/brief
COPY apps/triage/triage_score.py apps/triage/triage_score.py
COPY apps/alerting/ apps/alerting/
COPY apps/brief/ apps/brief/
COPY apps/mvp/ apps/mvp/
# triage_score's module-level CCIR guard reads <repo-root>/ccir.md relative to
# apps/triage/, which sits at /app — so the guard resolves to /app/ccir.md
COPY ccir.md .

# 4. Drop root before running (least privilege, T-05-04 pattern from triage)
RUN useradd --no-create-home --shell /usr/sbin/nologin mvp
USER mvp

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
EXPOSE 22017
CMD ["python", "apps/mvp/poller.py"]
