# ADR-017 addendum — SUPERSEDED BY ADR-018 (2026-07-23)

> **STATUS: SUPERSEDED.** This addendum documented the sealed-bind-mount
> architecture that shipped at commit 5c52056. On audit retrospective the
> operator elected to simplify further via Dockerfile pre-bake + BuildKit secrets:
> see `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md`. This document is
> preserved here for historical reference + post-mortem.

---

# ADR-017 addendum — sealed bind-mount replaces in-container ACL bootstrap

**Date:** 2026-07-23
**Status:** Note (addendum to ADR-017)
**Authors:** Operator pre-review + Buffy (sub-wave (a) iterative audit)
**Supersedes:** none (extends ADR-017 — its 4 LOCKED decisions remain in force)
**Cross-cites:** ADR-017 §Decisions 1-4, ADR-015 §Open Items 3, ADR-016 airgap-and-safety-doctrine

## Context

After 9+ iterations of attempting to make `docker compose up -d ntfy` succeed
with an in-container shell-script bootstrap that ran `ntfy user add` + `ntfy
access` at every container start, the SUB-WAVE (A) audit (2026-07-23) concluded:

| Root cause                                         | Encountered in iteration |
| -------------------------------------------------- | ------------------------ |
| Image ENTRYPOINT vs `command:` sh-vs-binary trap   | r1-r2                     |
| `\` \"` YAML escape vs `$$` compose escape trap    | r3-r4                     |
| AWK output-format coupling to ntfy CLI version     | r5-r6                     |
| Sentinel `{ grep -v 'X' || [$?-eq 1]; }` break     | r7                       |
| Bbrace-group `if ! { X && Y }` boolean inversion   | r8                       |
| Disagreement between basher-truthable ground state | r9 (final)               |

The operator (Vidar) terminated the iteration with the directive:

> "Kill the per-cmd-pattern-matching approach and use docker compose base
> 64-bind-mount of a sealed auth.db + server.yml just like other services
>  (DLQ consumer pattern). This avoids all the ntfy CLI bootstrap fragility
>  entirely."

This addendum records the resulting architectural shift. **ADR-017's 4
LOCKED decisions remain in force** — they were preserved as design
constraints, not implementation choices:

## Preserved constraints (from ADR-017)

1. **Split producer + reader users** — preserved (the seed script creates
   both).
2. **`:latest` image** — preserved (still on `binwiederhier/ntfy:latest`).
3. **Dev-only log-warn on `changeme`** — preserved (the seed script logs
   WARNING on default-detected, does NOT fail-fast).
4. **`unless-stopped` restart** — preserved (the previous `on-failure:2`
   variant is gone alongside the bootstrap that needed it).

## Architecture shift

### Before (rejected)
The container ran a 14-step in-container shell script on every `docker
compose up`. The script:
- Tolerated `"already exists"` lines via `{ grep -v || true; }`
- Asserted post-condition via `if ! ntfy user list | awk | grep -qx ...`
- Exited 3 on assertion failure so operators noticed immediately

This was, ultimately, a fragile layered set of per-binary-version escape
sequences whose ground truth (per-invocation) we could only see via
long-form captures, not sub-second debugging.

### After (current)
A host-side one-time prep script (`scripts/seed_ntfy_sealed.py`, called via
`make ntfy-seed`) produces two sealed files at `configs/ntfy-sealed/`:

- `server.yml` — checked in (mild config; bind-mounted `:ro`)
- `auth.db` — gitignored (bcrypt hashes of producer/reader creds)

`docker-compose.yml` `ntfy:` volume mount:
```yaml
volumes:
  - ./configs/ntfy-sealed/server.yml:/etc/ntfy/server.yml:ro
  - ./configs/ntfy-sealed/auth.db:/etc/ntfy/auth.db:ro
  - ./data/ntfy-cache:/var/cache/ntfy:rw   # only cache is rw
```

The container starts via the default ENTRYPOINT (`ntfy serve`) with **no
`command:` override, no `entrypoint:` override, and no in-container shell
orchestration**.

## Files

- `scripts/seed_ntfy_sealed.py` — `make ntfy-seed` invokes this; idempotent
  (skips if `auth.db` is already valid), supports `--force` to wipe and
  reseed. Uses `docker run --rm binwiederhier/ntfy:latest` to invoke
  `ntfy user add` / `ntfy access` from a one-shot container.
- `configs/ntfy-sealed/server.yml` — checked-in sealed config; ntfy 2.x
  schema (base-url, auth-file, auth-default-access, user-db, cache-db).
- `configs/ntfy-sealed/auth.db` — gitignored sealed ACL bundle; written
  once, mounted `:ro`, never modified by container.
- `docker-compose.yml` `ntfy:` — entrypoint/command removed; sealed binds
  in their place.
- `tests/test_ntfy_health.py` — adds 2 new tests for sealed-bundle
  invariants (`test_sealed_artifacts_present` +
  `test_server_yaml_schema_valid`).

## ADR-018 backlog (unaffected by this addendum)

ADR-018 still owns:
- `:2.27.0+` image re-pin (currently on `:latest`)
- Commit-time secret scanner for `changeme` defaults
- Production-rollout gate definition

This addendum is implementation-only. It does not change the design.

## Operator workflow

```bash
# One-time prep (idempotent):
make ntfy-seed

# Bring up the sealed ntfy container:
make ntfy-up

# Smoke-test deny-all:
make ntfy-publish-test  # expect HTTP 401

# Re-seed if you change credentials in .env:
make ntfy-seed -- --force
```
