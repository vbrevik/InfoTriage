# opml-health + admin dashboard (standalone service)
# Build context: project root
# Health port: 22032
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install service requirements
COPY apps/opml_health/requirements.txt .
RUN pip install -r requirements.txt

# 3. Copy source — apps/ layout preserved: opml_health imports apps.opml_health.*
#    absolutely and reaches sibling apps/opml/ (_check.py) via sys.path.
COPY apps/opml_health/ apps/opml_health/
COPY apps/opml/ apps/opml/

# 4. Drop root (least privilege)
RUN useradd --no-create-home --shell /usr/sbin/nologin opml-health
USER opml-health

# Admin server runs on port 22032 (not the CLI worker which uses env var port)
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:22032/health', timeout=3).status == 200 else 1)"

# Phase 7 07-02: ship uvicorn JSON log-config (consumed via log_config= kwarg in admin.py).
# Admin/tooling lifecycle change: was `python -c "..."` one-liner; now `python admin.py`
# so the entry runs a real `if __name__ == "__main__":` block (easier to test/reason-about).
COPY libs/contracts/src/contracts/uvicorn-log-config.json /app/uvicorn-log-config.json

EXPOSE 22032
CMD ["python", "apps/opml_health/admin.py"]
