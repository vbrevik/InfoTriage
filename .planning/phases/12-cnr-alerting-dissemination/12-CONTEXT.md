# Phase 12: CNR alerting / dissemination - Context

**Gathered:** 2026-08-01 (Turn-2; supersedes Turn-1 2026-07-23 — Turn-1 decisions carried forward below)
**Status:** Ready for planning

<domain>
## Phase Boundary

Exactly-once CAT I 🚩 push delivery from bus events to the operator's local ntfy server (7-field payload, dedupe, throttling, outbox/DLX resilience), plus the bundled Phase 13 sub-wave: `articles.body` population at ingest across all 7 adapters. The SAB stays the canonical artifact.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements are locked.** See `12-SPEC.md` for full requirements, boundaries, and acceptance criteria (incl. 12 pass/fail ACs, 19 resolved edges, 5 prohibitions).

Downstream agents MUST read `12-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):** `apps/alerting/` (outbox, emitter, 3-tier throttle, failure-mode tests); ntfy topic ACL provisioning + token wiring; producer-side `articles.body` UPSERT in all 7 ingest adapters (bundled Phase 13 sub-wave f); `outbox.*` contract events as needed.
**Out of scope (from SPEC.md):** CAT II/full-tier alerting; any second push channel (ADR-016 airgap); custom `sab://` macOS handler (obsidian:// chosen); alert history/archive UI (P5); scorer changes (body never feeds scorer, P3); M3 multi-user fan-out.

</spec_lock>

<decisions>
## Implementation Decisions

### Carried forward from Turn-1 (2026-07-23) — still binding
- **T1-01:** Workflow shape `INTEGRATED-SUB-WAVE` — Phase 13 body wiring ships as sub-wave (f) inside this phase. — **Reversibility:** one-way — HANDOFF.json anchors `phase_12_phase_13_depend.verdict`; downstream phases assert body population only after Phase 12 ships.
- **T1-02:** ADR-016 supersedes unrecoverable ADR-004 (airgap doctrine: local-LLM-only + read-only ingest).
- **T1-03:** ADR-015 D1–D5 locked (CAT I only; ntfy single channel; 7-field payload; 3-tier throttle; DLX+outbox).

### Emitter runtime shape
- **D-01:** Standalone `apps/alerting` service in its own container with its own `/health` endpoint on a 22xxx port — same pattern as wiki/brief/triage. Gets its own durable queue `q.alerting` bound to BOTH `verdict.ready` and `sab.published` via the existing widened `ROUTING_KEY_TO_QUEUE` list mechanism (`libs/contracts/src/contracts/_bus_rabbitmq.py`, the `q.wiki` fan-out precedent from commit `ec52292`). — **Reversibility:** costly — compose service, port allocation, and queue bindings are operational surface; folding back into brief later means re-binding queues and killing a container contract.

### Dedupe/throttle state store
- **D-02:** New Postgres table `infotriage.alert_state` via migration `011-alert-state.sql`, accessed through the existing Store protocol (both PostgresStore and InMemoryStore implement — parity like `recall_items`). Columns cover `dedupe_id` PK, `fired_at`, suppression/digest bookkeeping. 24h dedupe TTL = `WHERE fired_at > now() - interval '24 hours'`; sliding windows computed from `fired_at` timestamps. No new infra (no Redis). — **Reversibility:** costly — schema migration + Store protocol surface; exact column layout is planner's discretion but the table-in-Postgres choice is locked.

### Digest alert mechanics
- **D-03:** The alerting service runs its own asyncio hourly tick (no scheduler-container coupling, no piggyback-on-next-alert). If suppressed alerts exist since the last digest: publish exactly ONE message to `cnr-cat-i` — title `⚠ N suppressed CAT I alerts`, body grouped by PMESII tag, each entry carrying item title + `obsidian://` link + `alert_id`. An empty hour emits nothing.

### Body flow into articles.body (sub-wave f)
- **D-04:** Add optional `body: Optional[str]` to the `Item` contract (`libs/contracts/src/contracts/_item.py`); `put_item` UPSERTs it into `articles.body` (NULL when absent — never empty string, per SPEC edge). Adapters with full text set the one field; everything flows through the existing `persist_and_publish` path. InMemory/Postgres parity required. — **Reversibility:** costly — Item is the shared contract every app imports; removing a field later touches all serialization sites.

### Claude's Discretion
- `alert_state` exact column set, index choice, and the sliding-window query shape.
- Alerting service port number (next free 22xxx), Dockerfile layout, healthcheck wiring.
- Token provisioning mechanics (env var names, ntfy user/token bootstrap script) — within SPEC R6's fail-closed constraint.
- Digest message formatting details beyond the grouped structure in D-03.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements (locked)
- `.planning/phases/12-cnr-alerting-dissemination/12-SPEC.md` — Locked requirements — MUST read before planning (8 reqs, 12 ACs, edge coverage, 5 prohibitions)
- `.planning/phases/12-cnr-alerting-dissemination/12-PLAN.md` — Pre-SPEC draft plan; REPLAN against SPEC + this CONTEXT (operator chose "replan after")

### ADR substrate
- `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md` — Primary ADR: D1–D5 locks; §Open Items 2+3 now resolved (obsidian:// URI, ACL confirmed) — update ADR when planning
- `docs/adr/ADR-016-airgap-and-safety-doctrine.md` — local-LLM-only + read-only-ingest invariants; P1 prohibition ground
- `docs/adr/ADR-007-rabbitmq-bus.md` — DLX pattern substrate for outbox (verify exact filename at plan time)
- `docs/adr/ADR-013-recognized-picture-doctrine.md` — dedupe_id formula + PMESII collapse trigger (verify exact filename at plan time)

### Code integration points
- `libs/contracts/src/contracts/_bus_rabbitmq.py` — `ROUTING_KEY_TO_QUEUE` list fan-out (q.wiki precedent, commit `ec52292`) — add `q.alerting`
- `libs/ingest_common/src/ingest_common/persist.py` — `persist_and_publish` admission gate (discipline gate added 2026-08-01) — body rides this path
- `libs/store/sql/009-articles-body.sql` — applied DDL for `articles.body`
- `apps/ntfy/Dockerfile` + `docker-compose.yml` ntfy service — shipped sub-wave (a)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `persist_and_publish` (ingest_common): single choke point for all 7 adapters — body field lands here with zero per-adapter publish changes beyond setting `Item.body`
- Widened `ROUTING_KEY_TO_QUEUE` (list-of-queues): proven fan-out mechanism for adding `q.alerting` without disturbing brief/wiki consumers
- Store protocol dual-impl pattern (`_postgres.py`/`_inmemory.py` parity, e.g. `recall_items`): template for `alert_state` methods
- `apps/wiki/wiki_worker.py`: reference for a consumer service with `--mode` switch, asyncio loop, and `/health` endpoint
- `make ntfy-publish-test` + shipped ntfy container: live target for integration tests

### Established Patterns
- Migration numbering: next free slot is `011-*.sql` (007 discipline, 008 translation-cache, 009 body, 010 backfill)
- Per-service healthcheck + 127.0.0.1-bound 22xxx ports in docker-compose
- Contract events in `libs/contracts/src/contracts/_events.py` with Literal routing keys
- Test conventions: InMemory-first unit tests + `db_live`/`pg_store` fixtures for Postgres variants; `make test-safe` gate (baseline 685/0)

### Integration Points
- Emitter consumes `verdict.ready` + `sab.published` from `infotriage.events` exchange
- `alert_state` table joins the existing `infotriage` schema
- ntfy HTTP API at the compose-internal hostname with bearer token

</code_context>

<specifics>
## Specific Ideas

- Digest title format: `⚠ N suppressed CAT I alerts`, grouped by PMESII tag (D-03)
- Emitter startup must fail closed (non-zero exit + stderr) on missing/empty ntfy token (SPEC R6)
- Never silently drop: every throttled alert must appear in the next digest with its `alert_id`

</specifics>

<deferred>
## Deferred Ideas

- CAT II tier alerting and full-tier re-baseline — future phase; must cite 12-CONTEXT/12-SPEC as baseline
- ntfy iOS/Android app pairing docs for the operator — ops docs, not this phase

</deferred>

---

*Phase: 12-cnr-alerting-dissemination*
*Context gathered: 2026-08-01*
