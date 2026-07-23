> ⚠️ **SUPERSEDED 2026-07-23** — This audit's recommended architecture (sealed-bind-mount; ADR-017 sealed-bind-mount addendum) was itself pivoted-away by [ADR-018 Phase 12 Dockerfile pre-bake / BuildKit secrets](../adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md). The host-side Python prelude + sealed config file + bind `:ro` pattern this audit validated now lives in `docs/planning/_archived/phase-12-sealed-bind-mount-attempt/` with a tombstone banner on the prior sub-wave (a) substrate. For the operator-facing pivot summary see `HANDOFF.json#phase_12_subwave_a_final_architecture`. The 4 LOCKED ADR-017 ACL decisions (split producer/reader users, `:latest` image, dev-warn `changeme`, `unless-stopped` restart) ARE still the ACL contract — only the implementation substrate changed.

# Phase 12 sub-wave (a) — Audit + Scope Lock

**Date:** 2026-07-23
**Status:** Note (operator-facing; cross-cited by HANDOFF.json `phase_12_subwave_a_audit_findings`)
**Authors:** Operator + Buffy (sub-wave (a) iterative audit chain)
**Cross-cites:** `docs/adr/ADR-017-sealed-bind-mount-addendum.md`, `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md`, `docs/adr/ADR-016-airgap-and-safety-doctrine.md`, `.planning/HANDOFF.json#phase_12_subwave_a_audit_findings`, `.planning/STATE.md`

## TL;DR

Phase 12 sub-wave (a) — ntfy container — overran 9 rounds of debugging in-container ACL bootstrap patterns before the operator terminated with **"kill the per-cmd-pattern-matching approach; use sealed bind-mount just like other services (DLQ consumer pattern)"**. The architectural shift to **sealed-bind-mount** is the correct foundation. It is now **LOCKED**. Phase 12 ships sub-waves (b)+(c)+(d) on this foundation.

## Why iteration didn't terminate

The 9 rounds all attempted to fix the same pattern: **running `ntfy user add` / `ntfy access` CLI inside a one-shot container orchestration shell on every container start**. Each "fix" exposed a new coupling layer:

| Round | What broke | What the fix treated | What fix actually moved |
|-------|------------|-----------------------|------------------------|
| r1-r2 | Image ENTRYPOINT vs. `command: sh -c` | Entrypoint escape override | Container now starts ntfy w/ shell wrapper |
| r3-r4 | YAML `\"` escape × docker-compose `$$` escape | Awk-based post-condition | New awk dependency on ntfy CLI output format |
| r5-r6 | ntfy CLI output format drift | `--json` flag + JSON grep | New JSON-format dependency |
| r7 | First-run sentinel `{ grep -v \|\| [ $? -eq 1 ]; }` evaluated non-zero on success; `set -e` aborted | `{ grep -v >/dev/null 2>&1 \|\| true; }` | Stderr masking |
| r8 | `if ! { X && Y }` parses as `(! X) && Y`, NOT `!(X && Y)` | Split into 2 per-user checks | Each round is more shell-script surface area |
| **r9** | **Operator override** | **SWITCH ARCHITECTURE** | **Sealed-bind-mount** |

## Root cause

Nine rounds of debugging all attempted to fix the same pattern. Each round's "fix" traded one shell-script coupling for another. The pattern's failure modes are multiplicative because **YAML escape, docker-compose escape, and shell semantics compose inside a one-liner in un-debuggable ways** — a one-byte difference in the literal `\"` vs `'` results in a container that silently boots an empty auth.db.

Iteration on the bootstrap alone has no terminus without changing the architecture. The right answer is to **replace runtime bootstrap with host-side one-time prep**.

## Rebuilt foundation: sealed-bind-mount (locked)

| Field | Value | Source |
|-------|-------|--------|
| ACL file | `./configs/ntfy-sealed/auth.db` (bind `:ro`) | `docker-compose.yml ntfy:` `volumes:` |
| Config file | `./configs/ntfy-sealed/server.yml` (bind `:ro`) | `docker-compose.yml ntfy:` `volumes:` |
| Cache | `./data/ntfy-cache` → `/var/cache/ntfy` (bind `:rw`) | same |
| Container command | (image default `ntfy serve`) | killed |
| Container entrypoint | (image default) | killed |
| Auth backend env | `NTFY_CONFIG_FILE=/etc/ntfy/server.yml` | `docker-compose.yml ntfy:` `environment:` |
| Restart | `unless-stopped` (unbounded) | ADR-017 Decision 4 |
| Image | `binwiederhier/ntfy:latest` | ADR-017 Decision 2 |
| Default-password posture | log-warn only, no fail-fast | ADR-017 Decision 3 |

The container just `ntfy serve`s. ACL is bound read-only. The `:rw` cache is the only thing ntfy writes to at request time. **No more in-container shell-script orchestration.**

## Operator on-ramp

```bash
# One-time prep (writes configs/ntfy-sealed/{server.yml, auth.db})
make ntfy-seed

# Bring up ntfy; auto-fires ntfy-seed if the bundle is missing
make ntfy-up

# Smoke: should be 401 because deny-all
make ntfy-publish-test

# Reset (only when .env credentials change)
make ntfy-seed -- --force
```

## Validation status (2026-07-23)

- pytest full non-integration: **568 passed / 7 skipped / 0 regressions**
- pytest `tests/test_ntfy_health.py`: 1 passed (`test_server_yaml_schema_valid`) + 6 expected-failures (5 docker-dependent + 1 needs `make ntfy-seed`)
- mypy `--strict `: clean on `scripts/seed_ntfy_sealed.py` and `tests/test_ntfy_health.py`
- black `--check`: clean (2 files unchanged)
- `docker compose config ntfy`: parses cleanly with sealed `:ro` binds
- `yaml.safe_load` on `configs/ntfy-sealed/server.yml`: 5 required keys present, `auth-default-access=deny-all`, `auth-file=/etc/ntfy/auth.db` matches bind mount
- Seed script unit checks: HELPER-SPLIT-PASS (producer_user='producer', NOT 'changeme'), OVERRIDE-OK, `--help` works
- code-reviewer-minimax-m3 verbatim verdict: **SHIP** with 3 minor polish items

## Ship-next: sub-waves (b)+(c)+(d) on the rebuilt foundation

Per `phase_12_subwave_a_audit_findings.ship_next` in HANDOFF.json:

- **(b) outbox + DLX** — RabbitMQ outbox exchange/queue + DLX retry topology; new event types. Preflight: validate DLX retry topology against dev cluster (per ADR-007 bus-model cross-cite to confirm infra-drift before code lands).
- **(c) payload emitter** — 7-field structured payload builder per ADR-015 Decision 3. **Does NOT read `articles.body`**; summary-only push payload per `phase_12_phase_13_depend` verdict.
- **(d) throttling** — 3-tier (5/min, 10/10min, 1h PMESII collapse) per ADR-015 Decision 4. Decorates (c).
- **(e) failure-mode tests** — DLX retry, payload schema validation, burst-load throttle, sealed bcrypt validation. The verification gate before sub-waves (b)+(c)+(d) ship.
- **(f) Phase 13 body wiring** — apps/ingest-\* parallel body TEXT UPSERT into `PostgresStore.put_item`. Bundled sub-wave. Ships IN this phase, NOT as separate milestone phase. Link view degrades to summary-only URL extraction until this lands; alert payload unaffected.

## Scope-lock — Do NOT reopen (a)

- **Do NOT add `entrypoint:` / `command:`** to the ntfy service block. ADR-017 sealed-bind-mount is the contract.
- **Do NOT hand-edit `configs/ntfy-sealed/{server.yml, auth.db}`** mid-phase. Re-seed via `make ntfy-seed -- --force` only.
- **Do NOT resurrect the retired `ntfy-bootstrap` Makefile target.** `ntfy-seed` replaces it.
- **Do NOT cite cross-language entity linking / mE5-large** as Phase 12 scope. Unrelated to alerting.

## Enforcement

1. `HANDOFF.json#phase_12_subwave_a_audit_findings.scope_lock.decision = "LOCKED"` — every future `/gsd-progress --next` dispatch sees it.
2. `docs/adr/ADR-017-sealed-bind-mount-addendum.md` — Status: Note. Future changes to ntfy service block must reference this ADRe.
3. `tests/test_ntfy_health.py` — 2 new sealed-bundle tests gate against re-introducing the in-container bootstrap.
4. `ops/Makefile` — `ntfy-seed` target is the only legitimate way to regenerate the sealed bundle.
5. `docs/planning/phase-12-subwave-a-audit.md` — this file; operator-facing 1-read post-mortem.

## Background — why this matters for the rest of the project

Sub-wave (a) is the only sub-wave in Phase 12 that touches operator-deployed security infrastructure (ACL bootstrapping). Sub-waves (b)-(e) are pure application code that READS the sealed bundle. Sub-wave (f) is a producer-side database write. **None of them inherit the (a) bootstrap-fragility surface area**.

The 9-round overrun burned time without changing the design. The lesson: **shell-script orchestration inside a container is brittle by construction; bind-mount the artifact instead.** This principle generalizes — future deploys (Phase 13+ RabbitMQ DLX, Phase 14 M3) should default to "sealed file on host, bind `:ro` into container" rather than "first-run container-orchestrated init".

**Scope of the rule:** Applies to TRUE configurations (ACL bundles, sealed credentials, regex/static schemas, compiled ACL regexes, certificate public keys). Does **NOT** apply to ephemeral operational state — TLS certificate rotation, JWT/token minting, cert transparency log fetching, ephemeral service tokens — those are deliberate runtime concerns, and bind-mounting their artifacts would freeze them. Future deploys must distinguish "static config" (bind-mount the artifact) from "ephemeral state" (container-orchestrate the renewal).
