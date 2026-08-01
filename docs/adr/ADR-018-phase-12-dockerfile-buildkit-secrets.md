# ADR-018 — Phase 12 sub-wave (a) Dockerfile pre-bake architecture (BuildKit secrets)

**Date:** 2026-07-23
**Status:** Accepted
**Authors:** Operator (audit retrospective pivot) + Buffy
**Supersedes:** ADR-017 sealed-bind-mount addendum (archived 2026-07-23 to `docs/planning/_archived/phase-12-sealed-bind-mount-attempt/ADR-017-sealed-bind-mount-addendum.md`)
**Cross-cites:** ADR-015, ADR-016, ADR-017 phase-12-subwave-a-acl-amendments.md (4 LOCKED decisions preserved), HANDOFF.json `phase_12_subwave_a_final_architecture`, docs/planning/phase-12-subwave-a-audit.md (SUPERSEDED banner)

## Context

Phase 12 sub-wave (a) overran 9 rounds on in-container ACL bootstrap before the operator terminated with "kill the per-cmd-pattern-matching approach; use sealed bind-mount" (audit-logged at commit 5c52056). The sealed-bind-mount architecture shipped, but on review the operator decided the approach was still overcomplicated:

- host-side Python prelude (`scripts/seed_ntfy_sealed.py`)
- custom config file at non-default path (`/etc/ntfy/server.yml`)
- env-var overrides (`NTFY_CONFIG_FILE`, `NTFY_AUTH_DEFAULT_ACCESS`)
- 3 explicit bind mounts + 2 gitignored directories

The audit retrospective recommended pivoting to a simpler model where **ntfy's NATURAL paths are used** and **the prep happens at image-build time**, not container-start time and not via any host-side script. This ADR records the decision.

## Decision A (HIGH) — Dockerfile BuildKit secrets + multi-stage COPY

`apps/ntfy/Dockerfile` pre-bakes `/etc/ntfy/auth.db` during the image build. Plaintext passwords are passed via **BuildKit secrets** (`RUN --mount=type=secret,id=...`) read from `/run/secrets/*` inside the builder stage. The resulting `/etc/ntfy/auth.db` contains only bcrypt hashes (ntfy produces these via its CLI; does not persist plaintext anywhere). The final image then `COPY --from=builder /etc/ntfy/auth.db /etc/ntfy/auth.db` to layer in ONLY the hashed db.

Why this beats prior models:
- **No in-container orchestration at runtime.** The container just runs `ntfy serve`. No shell-script bootstrap, no escape-sequence coupling.
- **No host-side Python prelude.** BuildKit secrets read from `/run/secrets/*.` natively.
- **No env-vars required to wire secrets.** Compose's top-level `secrets:` block with `environment:` source maps project `.env` values to BuildKit secret IDs verbatim.
- **No `:ro` bind vulnerability surface.** The auth.db is baked into the image as a read-only artifact.

## Decision B (MEDIUM) — `docker-compose.yml` build-time secret pathway

The ntfy service block switches from `image: binwiederhier/ntfy:latest` → `build: { context: ./apps/ntfy, secrets: [...] }`. A top-level Compose `secrets:` block maps BuildKit secret IDs to .env variable names:

```yaml
secrets:
  ntfy_producer_password: { environment: NTFY_PRODUCER_PASSWORD }
  ntfy_reader_password:   { environment: NTFY_READER_PASSWORD }
  ntfy_topic_prefix:      { environment: NTFY_TOPIC_PREFIX }
```

Compose auto-loads `.env` for substitution. BuildKit reads the substituted values during build. Plaintext values never appear in `docker history` or image layers.

Requires Docker Compose v2.20.0+ (for `secrets: { environment: ... }` source). Project's current Compose is well within that constraint.

## Decision C (LOW) — Archive prior substrate

The sealed-bind-mount substrate is moved wholesale to `docs/planning/_archived/phase-12-sealed-bind-mount-attempt/`:
- `seed_ntfy_sealed.py` (298-line Python prelude)
- `server.yml` (sealed config)
- `ADR-017-sealed-bind-mount-addendum.md` (the prior ADRe; prepended with a SUPERSEDED tombstone)
- A new `README.md` in the archive dir explains the path-take-was-tried and why it was superseded

`configs/ntfy-sealed/` is deleted entirely. `.gitignore` rule for `configs/ntfy-sealed/*` removed.

The 4 LOCKED decisions from ADR-017 phase-12-subwave-a-acl-amendments.md are **preserved verbatim** (cross-referenced from this ADR); only the implementation substrate changed.

## Consequences

- **Sub-wave (a) collapsed to:** 1 custom Dockerfile + 1 minimal compose change. No host-side script, no separate config file.
- **Validation hook:** `tests/test_ntfy_health.py` repurpose to docker-exec assertion: `docker exec infotriage-ntfy ntfy user list --auth-file /etc/ntfy/auth.db` should contain `producer` and `reader` post-`make ntfy-up`.
- **Phase 12 ship-next dispatch** (`HANDOFF.json#phase_12_subwave_a_final_architecture.ship_next`) now points at sub-waves (b)+(c)+(d) on this foundation.

## Backlog (unchanged by this ADR)

- ADR-018 itself (this document) closes the architecture decision. Outstanding backlog items (`:2.27.0+` image pin per ADR-017 D2; commit-time secret scanner per ADR-017 D3) are still tracked in HANDOFF.json human_actions_pending and remain a future ADR.

## Amendment — bearer token provisioning (Phase 12)

**Date:** 2026-08-01
**Context:** Phase 12 (CNR alerting/dissemination) SPEC R6 requires a **bearer token**
(`Authorization: Bearer tk_...`), not Basic Auth, to publish to the `cnr-cat-i` topic —
the emitter (`apps/alerting/outbox.py`) sends this header on every publish and fails
closed at startup if its token env var is empty.

**Why the BuildKit-secret pre-bake path (Decision A above) does not apply here:**
`ntfy user add` accepts a plaintext password the operator chooses ahead of time, so that
value can ride a BuildKit secret into the builder stage exactly as this ADR describes.
`ntfy token add <user>` is different: it **generates** a random `tk_`-prefixed value at
the moment it runs; there is no equivalent "supply your own token string" flag. A value
that does not exist until the command executes cannot be pre-selected by the operator
and passed in as a build-time secret.

**Resolution:** the token is minted **post-boot**, against the already-running
container, via `make -f ops/Makefile ntfy-token` (idempotent — lists existing tokens for
the producer identity first, only calls `ntfy token add` if none exist). The printed
value is captured by the operator directly into the gitignored `.env` as `NTFY_TOKEN`.
The make target writes no file itself and passes the value to no build argument.

This **extends, not contradicts**, this ADR's core philosophy ("only bcrypt hashes land
in image layers"): a bearer token is used directly on the wire (bearer-equivalent — no
verification step stands between it and a successful publish), so it is strictly
*higher*-value than a password hash and belongs even further from any image layer or
`docker history`, not closer to one.

**ACL matrix — wildcard replaced by explicit per-topic grants:** the two wildcard grants
this ADR originally shipped (`ntfy access producer "<prefix>*" write-only` /
`ntfy access reader "<prefix>*" read-only`) were replaced in `apps/ntfy/Dockerfile` with
4 explicit grants, so topic-vs-wildcard precedence is never relied on:

| Identity | `cnr-cat-i` | `cnr-cat-i-debug` | `cnr-cat-i-test` |
|---|---|---|---|
| producer | read-write | write-only | write-only |
| reader | read-only | (no grant — deny-all) | (no grant — deny-all) |

Live-proven by `make -f ops/Makefile ntfy-acl-check` and `tests/test_alerting_auth.py`.
