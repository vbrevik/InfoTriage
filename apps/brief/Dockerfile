# brief app container (Phase 6, D-13/D-14)
# Build context: project root (compose uses context: . / dockerfile: apps/brief/Dockerfile)
FROM python:3.12-slim

WORKDIR /app

# 1. Copy and install local libs (--no-deps; transitive deps come from requirements.txt)
COPY libs/contracts /build/contracts
COPY libs/store /build/store
RUN pip install --no-deps /build/contracts /build/store

# 2. Install brief requirements + JSON formatter for structured container logging (Phase 7)
COPY apps/brief/requirements.txt .
RUN pip install -r requirements.txt json-log-formatter

# 3. Copy source — apps/ layout preserved: brief imports apps.brief.* absolutely and
#    reaches sibling apps/triage/ (digest.py, sab_html.py, triage_score.py) via sys.path
COPY apps/triage/ apps/triage/
COPY apps/brief/ apps/brief/
# digest.py's module-level CCIR sync guard reads <repo-root>/ccir.md (DRIFT-1);
# apps/ sits at /app, so the guard resolves to /app/ccir.md
COPY ccir.md .

# 4. Drop root before running (least privilege, T-05-04 pattern from triage)
RUN useradd --no-create-home --shell /usr/sbin/nologin brief
USER brief

# Secrets arrive at runtime via env_file (.env) only — no credential ARG/ENV (NF-6)
EXPOSE 22040
CMD ["uvicorn", "apps.brief.main:app", "--host", "0.0.0.0", "--port", "22040"]
