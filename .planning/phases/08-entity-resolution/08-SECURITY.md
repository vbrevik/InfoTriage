---
phase: 08
slug: entity-resolution
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-24
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| LLM output → entities | NER text and type originate from qwen36; may hallucinate mentions | Extracted entity name/type strings, local-only (ADR-004) |
| embedding output → pgvector | mE5-large vectors from local oMLX; tampering requires host access | 1024-dim float vectors, local-only |
| Postgres → Obsidian | Obsidian files are derived from Postgres; operator may edit files, but canonical truth remains in DB | Entity names, aliases, link counts (read-only projection) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Information disclosure | LLM NER output | medium | mitigate | No PII handling change; NER output is stored in Postgres only. Verified: `apps/triage/entities.py` makes no external network calls (no `requests`/`httpx`/`smtplib`/webhook) beyond the injected local `chat_fn`/`embed_fn` (routes through local oMLX/Spark per ADR-004) — no egress path for entity data. | closed |
| T-08-02 | Tampering | entity_links upsert | high | mitigate | ON CONFLICT / delete-before-insert prevents duplicate links on re-process. Verified: `PostgresStore.link_entity()` (`libs/store/src/store/_postgres.py:561`) uses `INSERT ... ON CONFLICT (entity_id, item_id, mention) DO NOTHING` — idempotent by construction; re-processing an item cannot create duplicate or tampered links. | closed |
| T-08-03 | Denial of service | embedding call failure | medium | mitigate | Embedding failure is caught; entity created with NULL vector, linking disabled for that entity. Verified: `embed_entity_name()` (`apps/triage/entities.py:146`) wraps the embed call in `try/except Exception`, returns `None` on any failure — never raises into the caller, never blocks entity creation or item scoring. | closed |
| T-08-04 | Elevation | none | low | accept | No new network-facing surface beyond existing worker/vault_writer. Verified: no server/listener/route additions in `apps/triage/entities.py` (no `FastAPI`, no bound port, no HTTP server) — Phase 8 adds only library functions called from the existing triage worker process. | closed |

*Status: open · closed · open — below `high` threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (`high`) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-08-01 | T-08-04 | Elevation-of-privilege surface is low severity and Phase 8 adds no new network-facing component (library functions only, called from the existing worker process) — no additional attack surface to mitigate. | Plan-time disposition (08-PLAN.md), confirmed at audit | 2026-07-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-24 | 4 | 4 | 0 | /gsd-secure-phase (orchestrator, L1 grep-depth — short-circuit rule: register plan-time-authored, ASVS L1, threats_open: 0) |

State B (no prior SECURITY.md): threat register built directly from `08-PLAN.md`'s `<threat_model>` block (`register_authored_at_plan_time: true`). Both `08-01-SUMMARY.md` and `08-02-SUMMARY.md` were checked for `## Threat Flags` entries — none present, so no threats beyond the plan-time register were surfaced during execution. All 4 mitigations verified directly against current implementation (line-level evidence above), not assumed from the plan's claims.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-24
