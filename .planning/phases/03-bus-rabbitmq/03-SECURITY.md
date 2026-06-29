---
phase: "03"
slug: bus-rabbitmq
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-29
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| caller → RabbitMQBus | DSN supplied by caller from `INFOTRIAGE_AMQP_DSN` env var | AMQP credentials (sensitive) |
| app → RabbitMQ | Event payloads cross into AMQP messages | JSON-serialized dict (non-sensitive item IDs + metadata) |
| RabbitMQ → app | Consumed messages decoded from JSON | Event payloads (trusted broker, internal network only) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | Tampering | DSN handling in RabbitMQBus | high | mitigate | DSN stored in `self.amqp_url`; never appears in any log call; dev-only default documented with explicit comment "never log the DSN (T-03-01)" | closed |
| T-03-02 | Tampering | AMQP message injection | medium | accept | JSON serialization only; payload schema validation deferred to Phase 5/6 consumers | closed |
| T-03-03 | Denial of Service | RabbitMQ connection flood | low | mitigate | `_ensure_connection()` implements exponential backoff `min(delay * 2, 30.0)` — reconnect rate capped at max 30s between attempts | closed |
| T-03-SC | Tampering | aio-pika supply chain (binary wheels) | high | mitigate | Official `aio-pika>=9.0` package pinned in `requirements-dev.txt`; legitimacy audit passed at plan time (RESEARCH Package Legitimacy Audit, disposition Approved) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `high` count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-02 | AMQP message injection: JSON serialization is sufficient at bus layer; full schema validation with Pydantic models is a Phase 5/6 consumer responsibility. Payloads are internal-only (no external input reaches RabbitMQ directly). | gsd-security-auditor | 2026-06-29 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-29 | 4 | 4 | 0 | gsd-secure-phase (L1 grep-depth, ASVS level 1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (AR-03-01)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-29
