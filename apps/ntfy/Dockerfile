# syntax=docker/dockerfile:1.7
# Phase 12 sub-wave (a) — Dockerfile pre-bake architecture (ADR-018)
#
# Architecture:
# - Builder stage runs `ntfy user add` + `ntfy access` against /etc/ntfy/auth.db
# - PLAINTEXT passwords arrive via BuildKit secrets — NEVER land in image layers
#   (mounted at /run/secrets/* only for the duration of the RUN instruction)
# - Builder then COPYs ONLY /etc/ntfy/auth.db (which contains ONLY bcrypt hashes)
#   into the final image. The only persistent artifact is the bcrypt'd db.
# - The :rw bind at /var/cache/ntfy (runtime cache + per-user-stats) is separate
#   from the pre-baked auth.db at /etc/ntfy/auth.db, so they never collide.
#
# Required BuildKit secrets (docker-compose.yml maps them from project .env):
#   ntfy_producer_password  → NTFY_PRODUCER_PASSWORD
#   ntfy_reader_password    → NTFY_READER_PASSWORD
#   ntfy_topic_prefix       → NTFY_TOPIC_PREFIX (e.g. cnr-cat-i)

FROM binwiederhier/ntfy:latest AS builder

# `ntfy user`/`ntfy access` read server config from env: point them at the
# auth.db we are baking. NTFY_PASSWORD is ntfy's documented non-interactive
# password input for `ntfy user add`.
ENV NTFY_AUTH_FILE=/etc/ntfy/auth.db \
    NTFY_AUTH_DEFAULT_ACCESS=deny-all

RUN --mount=type=secret,id=ntfy_producer_password \
    --mount=type=secret,id=ntfy_reader_password \
    --mount=type=secret,id=ntfy_topic_prefix \
    set -eu; \
    mkdir -p /etc/ntfy; \
    TOPIC="$(cat /run/secrets/ntfy_topic_prefix)"; \
    NTFY_PASSWORD="$(cat /run/secrets/ntfy_producer_password)" \
        ntfy user add producer; \
    NTFY_PASSWORD="$(cat /run/secrets/ntfy_reader_password)" \
        ntfy user add reader; \
    ntfy access producer "${TOPIC}*" write-only; \
    ntfy access reader "${TOPIC}*" read-only

# Final stage: pure ntfy image, only the (already-bcrypt'd) auth.db is layered in.
# Plaintext passwords are NOT in any image layer — only bcrypt-derived hashes.
FROM binwiederhier/ntfy:latest
COPY --from=builder /etc/ntfy/auth.db /etc/ntfy/auth.db
