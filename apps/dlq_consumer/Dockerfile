# dlq-consumer — InfoTriage dead-letter queue consumer (Phase 7)
# Build context: project root
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
RUN pip install --no-deps /build/contracts

# 2. Install DLQ consumer requirements
COPY apps/dlq_consumer/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy source
COPY apps/dlq_consumer/ .

# 4. Drop root before running (least privilege)
RUN useradd --no-create-home --shell /usr/sbin/nologin dlq-consumer
USER dlq-consumer

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
CMD ["python", "worker.py"]
