# Phase 12: CNR alerting / dissemination - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-01
**Phase:** 12-cnr-alerting-dissemination
**Areas discussed:** Emitter runtime shape, Dedupe/throttle state store, Digest alert mechanics, Body flow into articles.body

---

## Emitter runtime shape

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone container | Own service + /health on 22xxx, q.alerting fan-out binding (q.wiki precedent) | ✓ |
| Inside brief consumer | Fewer containers, couples alerts to SAB render lifecycle | |

**User's choice:** Standalone container
**Notes:** Failure isolation was the deciding rationale (matches 12-CONTEXT Turn-1 failure-isolation stance).

---

## Dedupe/throttle state store

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres table | infotriage.alert_state via Store protocol, migration 011; TTL + sliding windows from fired_at | ✓ |
| In-process memory | Zero schema, but restart forgets 24h dedupe → re-alerts | |
| ntfy cache as dedupe | Pushes correctness into third-party cache; can't express windows/digest | |

**User's choice:** Postgres table
**Notes:** Durability across emitter restarts required by exactly-once AC.

---

## Digest alert mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| Emitter timer, grouped msg | asyncio hourly tick; one grouped-by-PMESII message; empty hour → silence | ✓ |
| Scheduler container cron | Reuses scheduler but adds HTTP surface + coupling | |
| Next-alert piggyback | No timer, but suppressed burst + silence never reported | |

**User's choice:** Emitter timer, grouped message
**Notes:** "Never silently drop" — every suppressed alert_id must appear in the next digest.

---

## Body flow into articles.body

| Option | Description | Selected |
|--------|-------------|----------|
| Item.body field + store | Optional field on Item contract; put_item UPSERTs; NULL when absent | ✓ |
| Separate store.put_body call | Two-step write breaks atomicity, doubles adapter wiring | |
| Derive from blob body_ref | Re-decodes blobs, lossy for binary MIME/PDF | |

**User's choice:** Item.body field + store
**Notes:** Single shared path through persist_and_publish; InMemory/Postgres parity required.

## Claude's Discretion

- alert_state column set, indexes, window-query shape
- Alerting service port, Dockerfile, healthcheck
- Token provisioning mechanics (within fail-closed constraint)
- Digest formatting details

## Deferred Ideas

- CAT II / full-tier alerting (future phase, cite 12-SPEC baseline)
- ntfy mobile-app pairing docs for the operator (ops docs)
