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
    # ntfy 2.26.x will NOT create the auth DB from `ntfy user add` — it errors
    # "auth-file does not exist; please start the server at least once". The
    # SQLite schema is only created by the server. So start `ntfy serve` just
    # long enough to initialise $NTFY_AUTH_FILE, kill it, then seed against the
    # created DB. (This is the rock the sealed-bind-mount attempt kept hitting.)
    ntfy serve --cache-file /tmp/cache.db >/tmp/ntfy-serve.log 2>&1 & \
    SRV=$!; \
    for _ in $(seq 1 50); do [ -f "$NTFY_AUTH_FILE" ] && break; sleep 0.2; done; \
    kill "$SRV" 2>/dev/null || true; wait "$SRV" 2>/dev/null || true; \
    test -f "$NTFY_AUTH_FILE" || { echo "FATAL: $NTFY_AUTH_FILE not created"; cat /tmp/ntfy-serve.log; exit 1; }; \
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
