---
phase: 2
slug: storage-postgres-blobs
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-06-28
---

# Phase 2 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| repo → compose runtime | Connection credentials cross into the running Postgres container | DB password (dev default) |
| developer machine → PyPI | Package installs pull third-party code | psycopg, pgvector, numpy, feedgen wheels |
| caller → blob store | `blob_hash` supplied to `get_blob` builds a filesystem path | untrusted hash string |
| caller → SQL | `Item` field values cross into SQL executed against Postgres | title/url/summary/payload |
| env → store / digest | Connection DSN (credentials) enters the process from `INFOTRIAGE_PG_DSN` | DB DSN with credentials |
| query vector → pgvector | numpy arrays serialized into `vector(1024)` parameters | embedding floats |
| scored verdict → store | LLM-derived verdict fields cross into persisted `Item.payload` | ccir/cnr/score/why metadata |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering (SQLi) | PostgresStore + digest persistence SQL | high | mitigate | All values bind via psycopg3 `%s`/array params; identifiers static fully-qualified `infotriage.*`; no f-string/concat SQL (verified: 0 f-string SQL in `_postgres.py`). | closed |
| T-02-02 | Tampering (path traversal) | `_blob.get_blob` path construction | high | mitigate | `_validate_hash` rejects any hash not matching `^[0-9a-f]{64}$` before building a path (`_HEX64.fullmatch` → `ValueError`); hash is content-derived in `put_blob`. | closed |
| T-02-03 | Information Disclosure | docker-compose credentials / `INFOTRIAGE_PG_DSN` | high | mitigate | Real creds come from `.env` via `INFOTRIAGE_PG_DSN` (gitignored, line 1); DSN read from env only, never logged. Compose dev password hardened post-execution: `127.0.0.1`-only bind + `${POSTGRES_PASSWORD:-…}` override (commit 8cf8654). No hardcoded secret in `libs/`/`apps/`. | closed |
| T-02-04 | Tampering | `Item.payload` → JSONB | medium | mitigate | Persisted via `psycopg.types.json.Jsonb()` adapter (parameterized); no raw-dict, no eval/pickle. | closed |
| T-02-05 | Denial of Service | unbounded `list_items` / `render_atom` | low | mitigate | Both carry a `limit` (default 200 / 50) bounding result materialization. Below `block_on` threshold (non-blocking). | closed |
| T-02-06 | Information Disclosure | LLM verdict fields persisted to `payload` | low | accept | Verdict fields (ccir/cnr/score/why) are non-secret triage metadata. PII/secrets-in-payload review deferred per SPEC breadcrumb. Below `block_on` threshold (non-blocking). | closed |
| T-02-SC | Tampering (supply chain) | psycopg / pgvector / numpy / feedgen wheels | high | mitigate | Pinned official packages in `pyproject.toml` (`psycopg[binary]>=3.3`, `pgvector>=0.4.2`, `numpy>=1.24`); RESEARCH Package Legitimacy Audit disposition Approved (no [ASSUMED]/[SLOP]). | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-02-01 | T-02-06 | LLM verdict fields (ccir/cnr/score/why) are non-secret triage metadata, not credentials/PII. Dedicated PII/secrets-in-payload review deferred to a later phase per SPEC breadcrumb. | vidar@brevik.net | 2026-06-28 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-28 | 7 | 7 | 0 | Claude (gsd-secure-phase, ASVS L1 grep-depth) |

Notes:
- All 4 phase-2 PLANs carried a plan-time `<threat_model>` (`register_authored_at_plan_time: true`); ASVS L1 + `threats_open: 0` ⇒ L1 grep-depth verification, no deep auditor pass required.
- Each high-severity mitigation independently confirmed in code at audit time (not taken from SUMMARY claims): `_postgres.py` (T-02-01/04), `_blob.py` (T-02-02), `.gitignore` + `docker-compose.yml` (T-02-03), `pyproject.toml` (T-02-SC).
- Background commit-review finding on the original compose service (LAN exposure + un-overridable credential) was remediated in commit 8cf8654, strengthening T-02-03.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-28
