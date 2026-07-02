---
phase: 05
slug: triage-app
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-02
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| LLM/embedding output → Postgres | enrichment TEXT fields (ccir, why, pmesii, tessoc) originate from model output and are persisted | model-generated text |
| caller-supplied vector → pgvector query | float vectors bound into the cosine `find_near_duplicate` query | numeric vectors |
| AMQP broker → worker | `item.ingested` messages cross from RabbitMQ into in-process handlers | JSON payload + headers |
| ccir.md file → scorer prompt | operator-edited file content read into the LLM prompt at runtime | local file content |
| RabbitMQ → worker | `item.ingested` messages enter in-process handlers | JSON payload + headers |
| worker → oMLX | embedding + LLM scoring HTTP calls leave the process | article text |
| worker → RabbitMQ | `verdict.ready` leaves the process after enrichment commit | JSON payload |
| host network → container | published port 22030 and the host oMLX endpoint cross the container boundary | HTTP |
| .env → container runtime | credentials injected via `env_file` at runtime | DSNs, API keys |
| Postgres → shadow_run | enrichment + article rows read into a local ops script | stored article/enrichment text |
| operator → host crontab | manual removal of the fever scoring job | n/a |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Tampering | `put_enrichment`/`find_near_duplicate` SQL (store, worker, shadow_run) | high | mitigate | All SQL uses `%s` bind params; model text and vectors never interpolated into SQL strings. Verified: `_postgres.py:284-374` inline comments cite T-05-01 directly at each call site; `scripts/shadow_run.py`'s `QUERY` uses `%s` for the one runtime arg. | closed |
| T-05-02 | Tampering | `enrichment.score` column | medium | mitigate | `CHECK (score BETWEEN 0 AND 10)` at the schema layer backstops the worker-side `clamp_score`. Verified: `libs/store/sql/006-enrichment.sql:23`. | closed |
| T-05-02 | Information Disclosure | worker/container logs | medium | mitigate | Logs only `item_id`/event names; DSNs never logged (T-03-01 pattern). Verified: live `docker logs infotriage-triage` this session shows only `item.ingested item_id=...` lines; `_bus_rabbitmq.py` log calls pass exception objects/queue names, never a raw DSN string. | closed |
| T-05-03 | Information Disclosure | `RabbitMQBus` DSN | medium | mitigate | DSN sourced from `INFOTRIAGE_AMQP_DSN`; never logged (existing T-03-01 pattern; `consume()` logs nothing sensitive). Verified: `_bus_rabbitmq.py` log lines only reference queue names/exceptions. | closed |
| T-05-03 | Tampering | `LLM_BASE_URL` (worker + container default) | high | mitigate | `get_embedding`/`score_item` use `LLM_BASE_URL` only, pointing at local oMLX/Spark — no cloud host (ADR-004). Verified + **hardened this session**: `docker-compose.yml`'s default was found leaking the host `.env`'s `127.0.0.1` value via Compose substitution (fixed in `d9714fc` to hardcode `http://host.docker.internal:8000/v1`, never falling back to a var that could be shadowed by a cloud URL). | closed |
| T-05-04 | Tampering | `ccir.md` hot-read | low | accept | `ccir.md` is a local operator-owned file; hot-read is intended behavior (D-5); no external write path. | closed (accepted) |
| T-05-04 | Elevation of Privilege | container user | high | mitigate | Dockerfile switches to non-root `USER triage` before `CMD`. Verified live this session: `docker exec infotriage-triage whoami` → `triage`. | closed |
| T-05-05 | Denial of Service | `message.process` requeue loop | medium | accept | Persistent LLM/embedding outage nacks with `requeue=False` → DLQ (not infinite requeue); single-worker M1 accepts this risk; held-out timeout test deferred. Verified partially: real DLQ dead-lettering (20 messages, then stopped) observed live this session when embed calls failed pre-fix — confirms no infinite poison-loop, though a dedicated held-out timeout test was not run. | closed (accepted) |
| T-05-06 | Information Disclosure | published port 22030 | medium | mitigate | Bound to `127.0.0.1` only; not exposed on the LAN. Verified: `docker-compose.yml:126` → `"127.0.0.1:22030:22030"`. | closed |
| T-05-07 | Denial of Service | premature Fever cutover | high | mitigate | Blocking checkpoint enforces >= 10 matching-bucket parity before crontab removal (R6 prohibition). Verified live this session: checkpoint was honored — corrected parity script run, 14/14 confirmed MET, before checking/relying on crontab state. | closed |
| T-05-08 | Tampering | `fever_triage.py` deletion | medium | mitigate | `digest.py` imports `fever_key`/`fever`/`strip_html` from it — plan forbids deleting the file, only the crontab invocation is retired. Verified: file exists (`apps/triage/fever_triage.py`), `digest.py:26` still imports from it. | closed |
| T-05-SC | Tampering | package installs (05-01/02/03/05) | high | accept | No new PyPI packages added in these plans (RESEARCH Package Legitimacy Audit). | closed (accepted) |
| T-05-SC | Tampering | `requirements.txt` (05-04) | high | mitigate | Only already-vetted packages used: `aio-pika`, `psycopg[binary]`, `pgvector` (plan) + `feedgen`, `pydantic`, `PyYAML` (transitive, already used identically in `apps/ingest-imap`, documented in 05-04-SUMMARY.md Deviations). Verified: `apps/triage/requirements.txt` contents match exactly. | closed |

*Status: open · closed · open — below {block_on} threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-1 | T-05-04 (ccir.md hot-read) | Local operator-owned file; hot-read is the intended D-5 behavior; no external write path exists. | Plan-time (05-02-PLAN.md) | 2026-06-30 |
| AR-05-2 | T-05-05 (requeue-loop DoS on persistent outage) | Single-worker M1 deployment; nack(requeue=False)→DLQ prevents infinite poison-looping (confirmed live this session); a dedicated held-out timeout test is deferred as a known M1 risk. | Plan-time (05-03-PLAN.md) | 2026-06-30 |
| AR-05-3 | T-05-SC (no new packages, 05-01/02/03/05) | RESEARCH Package Legitimacy Audit found no new PyPI packages needed for these plans. | Plan-time (05-0{1,2,3,5}-PLAN.md) | 2026-06-27 – 2026-07-02 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-02 | 13 | 13 | 0 | Claude (orchestrator, L1 grep-depth — short-circuit per threats_open:0 AND register_authored_at_plan_time:true AND asvs_level==1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-02
