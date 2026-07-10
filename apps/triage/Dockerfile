# triage worker container (D-01)
# Build context: project root (compose uses context: . / dockerfile: apps/triage/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install worker requirements (includes all transitive deps for the above libs)
#    Add json-log-formatter for structured container logging (Phase 7)
COPY apps/triage/requirements.txt .
RUN pip install -r requirements.txt json-log-formatter

# 3. Copy worker source
COPY apps/triage/ .

# 4. Drop root before running (least privilege, T-05-04)
RUN useradd --no-create-home --shell /usr/sbin/nologin triage
USER triage

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
EXPOSE 22030
CMD ["python", "worker.py"]
