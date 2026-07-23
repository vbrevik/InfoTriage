# ADR-017 — Phase 12 sub-wave (a) ntfy ACL amendments

**Date:** 2026-07-23
**Status:** Accepted
**Authors:** Operator pre-review + Buffy audit
**Supersedes:** none
**Cross-cites:** ADR-015 §Open Items 3, ADR-016 airgap-and-safety-doctrine

## Context

Phase 12 sub-wave (a) ntfy push-channel implementation surfaced 4 design decisions during the bootstrap-debug review. Operator pre-review locked the answers this turn (`/gsd-discuss-phase 12` Turn-N via ask_user):

### Decision 1 (HIGH) — READ access: **split producer + reader**
Two ACL rows in `auth.db`:
- `producer` user (write-only) — used by sub-wave (c) emitter.
- `reader` user (read-only) — used by ntfy web/iOS/Android subscribers.

Most granular; doubles auth.db entries; aligns with ADR-006 microservice-decoupling + ADR-013 recognized-picture doctrine (each role has its own trust boundary).

### Decision 2 (MEDIUM) — Image pin: **ship on `:latest`**
`binwiederhier/ntfy:2.26.3` is not yet published to Docker Hub. `:latest` accepted for dev path; re-pin to `:2.27.0+` on next publish. Production rollout requires re-pin + ADR-018 supersession.

### Decision 3 (MEDIUM) — Default password: **dev-only log-warn (no fail-fast)**
`NTFY_PRODUCER_PASSWORD` and `NTFY_READER_PASSWORD` default to `changeme`. Bootstrap logs a WARNING when default is detected and proceeds (does NOT exit). Production rollout requires external gate (`.env` override + commit-time secret scanner) — a future ADR.

### Decision 4 (LOW) — Restart: **`unless-stopped` (unbounded)**
Original default restored. Risk of silent restart-loop on bootstrap regression accepted; post-condition `exit 3` surfaces immediately to operator logs via container exit + log inspection.

## Consequences

- **Producer side** (sub-wave (c) emitter, future): uses `NTFY_PRODUCER_USER` + `NTFY_PRODUCER_PASSWORD` as bearer.
- **Reader side** (ntfy web/iOS/Android): uses `NTFY_READER_USER` + `NTFY_READER_PASSWORD` as subscriber.
- **`:latest` risk**: dev-acceptable; pre-release blocker for production. ADR-018 will harden.
- **Bootstrap script**: warns-only on defaults (no exit), 2 users (producer + reader), 5 access grants (deny-all + producer write-only + reader read-only), post-condition checks both users present before `exec ntfy serve`.

## Implementation

- `docs/adr/ADR-017-phase-12-subwave-a-acl-amendments.md` — this file.
- `docker-compose.yml` `ntfy:` service — bootstrap script + env vars rewritten.
- `.env.example` — NTFY_PRODUCER / NTFY_READER vars added (NTFY_OPERATOR_* removed).
- `tests/test_ntfy_health.py` — 5 tests now (container, root, deny, producer, reader).

## Backlog

- **999.x follow-up**: pre-release ADR-018 covers `:2.27.0+` pin + commit-time secret scanner + bounded `on-failure:2` restart.


## Implementation substrate

The 4 LOCKED decisions above are PRESERVED by ADR-018 (Dockerfile pre-bake architecture, 2026-07-23). ADR-018 collapses the implementation substrate from the prior sealed-bind-mount attempt (commit 5c52056 + ADR-017 addendum) into 1 custom Dockerfile + 1 compose change, replacing the host-side prep script + custom-named config + env-var overrides. See `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md` for the implementation substrate.
