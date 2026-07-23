# Archived — Phase 12 sub-wave (a) sealed-bind-mount attempt

**Status:** SUPERSEDED 2026-07-23 by ADR-018 (Phase 12 sub-wave (a) Dockerfile pre-bake architecture).

## Why this is here

Phase 12 sub-wave (a) ran 9 rounds of in-container shell-script ACL bootstrap debugging before the operator terminated with "kill the per-cmd-pattern-matching approach; use sealed bind-mount just like other services (DLQ consumer pattern)". That pivot (audit findings filed at commit 5c52056, ADR-017-sealed-bind-mount-addendum.md, scripts/seed_ntfy_sealed.py in working tree) shipped on 2026-07-23.

A retrospective audit recommended further simplification: **pre-bake auth.db during image-build time** (BuildKit secrets + multi-stage COPY pattern) rather than the host-side prelude + custom bind-mount approach. The retrospective is locked in ADR-018.

This directory preserves the substrate as a historical record + cautionary tale.

## What's in here

- `seed_ntfy_sealed.py` — the 298-line host-side Python prelude that ran `docker run --rm binwiederhier/ntfy:latest` to populate `configs/ntfy-sealed/auth.db`
- `server.yml` — the sealed config (custom-named; bind-mounted at `/etc/ntfy/server.yml` to dodge ntfy's default config path)
- `ADR-017-sealed-bind-mount-addendum.md` — the architectural-shift ADRe (now with SUPERSEDED banner prepended)

## What was right about this attempt

- ADR-017's 4 LOCKED decisions (split producer/reader, `:latest` image, dev-only log-warn `changeme`, `unless-stopped`) are PRESERVED by ADR-018 — they were design decisions, not implementation details.
- The "deny-all + scoped grants" trust model still applies.
- The 9 lessons filed in `HANDOFF.json#phase_12_subwave_a_audit_findings.brittle_decisions` are still valid: shell-script orchestration inside a container IS brittle by construction.

## What was wrong about this attempt

- Two gitignored directories (`configs/ntfy-sealed/`, `data/ntfy-auth/`) for static sealed config + runtime cache.
- Custom env vars (`NTFY_CONFIG_FILE`, `NTFY_AUTH_DEFAULT_ACCESS`) that override ntfy's defaults.
- A custom-named config file (`server.yml`) to dodge ntfy's default config path.

Per the audit retrospective, all three of these were over-engineering. ADR-018 collapses to:
- `/etc/ntfy/auth.db` (ntfy's NATURAL config-rooted path; build-time-baked)
- `/var/cache/ntfy/*` (runtime cache, bind-mounted `:rw` from `./data/ntfy-cache/`)
- No custom env vars; no custom-named config file

## Reference

- **Previous architecture ADRe:** `ADR-017-sealed-bind-mount-addendum.md` (this directory)
- **New architecture ADRe:** `docs/adr/ADR-018-phase-12-dockerfile-buildkit-secrets.md`
- **Audit findings (preserved):** `.planning/HANDOFF.json#phase_12_subwave_a_audit_findings` (scope_lock flipped from LOCKED → SUPERSEDED_BY_PIVOT, all historical kept)
- **Operator-facing audit doc:** `docs/planning/phase-12-subwave-a-audit.md` (SUPERSEDED banner at top)
