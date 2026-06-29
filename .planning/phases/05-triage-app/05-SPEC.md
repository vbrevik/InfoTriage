# Phase 5: Triage App — Specification

**Created:** 2026-06-29
**Ambiguity score:** 0.149 (gate: ≤ 0.20)
**Requirements:** 7 locked

## Goal

Replace the FreshRSS Fever poll with an event-driven `triage` container that subscribes `item.ingested`, scores each article against `ccir.md` using qwen36, writes enrichment rows to Postgres, deduplicates with mE5-large embeddings, and publishes `verdict.ready`.

## Background

`apps/triage/triage_score.py` is a working scorer (qwen36, ccir.md, returns ccir/cnr/pmesii/tessoc/score/why/bucket) but is driven by `fever_triage.py` polling FreshRSS Fever — not by the event bus. `infotriage.enrichment` exists as a bare stub (id, item_id, created_at only). `infotriage.embeddings` has `vector(1024)` with HNSW cosine index (ready for mE5-large from Phase 2). `ItemIngested` and `VerdictReady` events are fully typed in contracts. 111 live articles exist in `infotriage.articles` from Phase 4. The Store protocol has no enrichment methods. Phase 5 bridges the gap: port the proven scorer behind the bus, add enrichment persistence, add pgvector dedup, retire the Fever poll.

## Requirements

1. **Enrichment schema migration**: Add scoring columns to `infotriage.enrichment` and add Store protocol methods.
   - Current: enrichment table has only `id`, `item_id`, `created_at`; no Store methods for enrichment
   - Target: migration adds `ccir TEXT`, `cnr TEXT`, `score INT`, `bucket TEXT`, `why TEXT`, `pmesii TEXT`, `tessoc TEXT`; `put_enrichment(item_id, fields)` and `get_enrichment(item_id)` added to Store Protocol and PostgresStore; put_enrichment uses ON CONFLICT DO UPDATE (upsert)
   - Acceptance: `\d infotriage.enrichment` shows all 7 new columns; `pytest` tests for `put_enrichment` / `get_enrichment` pass including double-write idempotency

2. **Event subscription**: `triage` container consumes `item.ingested` from RabbitMQ.
   - Current: no container subscribes `item.ingested`; scoring is triggered by FreshRSS Fever poll
   - Target: `triage` service connects to RabbitMQ on startup via `INFOTRIAGE_AMQP_DSN`, subscribes `item.ingested` queue; for each message calls `store.get_item(item_id)`; if article missing → logs warning + acks (not a crash condition)
   - Acceptance: POST one `item.ingested` event to bus → `triage` logs "scoring {item_id}" and enrichment row written within 30 s; container survives missing-article event without crashing

3. **LLM scoring**: Port `triage_score.py` scoring logic to event-driven context; write result to enrichment.
   - Current: `score_item()` in `triage_score.py` takes a dict; returns ccir/cnr/pmesii/tessoc/score/why; not wired to Postgres/bus
   - Target: scoring function called per article; result written via `store.put_enrichment`; malformed LLM JSON → fallback `{ccir:'none', cnr:'Routine', score:0, bucket:'skip', why:'parse error', pmesii:'none', tessoc:'none'}`; score clamped to [0, 10]
   - Acceptance: test item scored → enrichment row contains all 7 fields; malformed-LLM-response fixture → enrichment row written with fallback values (not a crash)

4. **Semantic dedup**: Before LLM scoring, compute mE5-large embedding and skip duplicates.
   - Current: no embedding-based dedup; `infotriage.embeddings` populated only by Phase 2 spike (not in production path)
   - Target: per article, call oMLX `/v1/embeddings` (model `intfloat/multilingual-e5-large`, input `title + " " + summary[:512]`); write vector to `infotriage.embeddings`; cosine similarity ≥ 0.84 vs any embedding in last 7 days → `put_enrichment(bucket='skip', why='duplicate', score=0, ccir='none')`; LLM call skipped for duplicates
   - Acceptance: two manually-verified near-duplicate articles → second gets `bucket='skip'`, why contains 'duplicate', no LLM call made; two clearly-different articles → both scored by LLM; embedding written to `infotriage.embeddings` for every article (duplicates and originals)

5. **verdict.ready publication**: Publish `VerdictReady` event after enrichment commit.
   - Current: `VerdictReady` defined in contracts but never published
   - Target: after `store.put_enrichment()` returns, call `bus.publish("verdict.ready", ...)` with `VerdictReady` fields; publication happens AFTER enrichment commit, never before
   - Acceptance: subscribe `verdict.ready` routing key; process one item through triage → receive valid `VerdictReady` JSON with correct `item_id`, `ccir`, `cnr`, `score`, `bucket`; no `verdict.ready` event if enrichment write fails

6. **Fever shadow-run and cutover**: Validate parity then retire `fever_triage.py` from production.
   - Current: `fever_triage.py` is the live scoring path; no event-driven alternative
   - Target: run new triage scorer against ≥ 10 articles previously scored by old path; verify same `bucket` on each (exact score match not required — LLM is stochastic); on parity confirmed, remove `fever_triage.py` from `scheduler` cron and docker-compose triage stanza
   - Acceptance: shadow-run log shows ≥ 10 items with matching buckets; `docker compose up triage` → no `fever_triage.py` invoked; scheduler has no fever-related cron entries

7. **Triage container**: New `triage` Docker service at port 22030.
   - Current: `apps/triage/` runs on host Python only; no container
   - Target: `apps/triage/` containerized as `triage` service in docker-compose; exposes port 22030; `GET /health` returns 200 when container is up (liveness only — bus disconnect does not make /health return 5xx; bus uses `connect_robust` reconnect); env: `INFOTRIAGE_PG_DSN`, `INFOTRIAGE_AMQP_DSN`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
   - Acceptance: `docker compose up -d triage` → container reaches running state; `curl -s http://localhost:22030/health` returns 200; container remains healthy when RabbitMQ is temporarily unavailable (reconnect, no crash)

## Boundaries

**In scope:**
- `infotriage.enrichment` schema migration (7 new columns)
- Store protocol: `put_enrichment` / `get_enrichment`
- `triage` Docker container (port 22030, GET /health)
- RabbitMQ `item.ingested` consumer
- LLM scoring (qwen36, ccir.md, PMESII/TESSOC enrichment)
- mE5-large embedding dedup (oMLX, 7-day window, cosine ≥ 0.84)
- `infotriage.embeddings` writes (production path)
- `verdict.ready` publication
- Shadow-run parity check + `fever_triage.py` retirement from production

**Out of scope:**
- SAB/digest generation — Phase 6
- CNR alerting / push notifications — Phase 12
- Entity resolution — Phase 8
- CCIR pre-filter cosine similarity (A-1) — Phase 9
- RAG recall — Phase 9
- `infotriage.ccir` table — not used in Phase 5 (stub only; Phase 9 owns it)
- Admiralty reliability scoring (A-4) — post-M1 backlog
- FreshRSS subscription management — remains as-is; triage no longer reads from it
- Multiple concurrent triage worker scaling — single worker is sufficient for M1

## Constraints

- **ADR-004**: all LLM calls use local qwen36 only (`LLM_BASE_URL` → oMLX or Spark); no cloud LLM
- **mE5-large @ threshold 0.84**: locked by R2 spike (ADR-006); threshold is a starting point — recalibrate in Phase 8 on held-out corpus
- **ccir.md re-read per scoring batch**: must not cache at startup; hot edits must take effect on next run (D-5)
- **aio-pika connect_robust**: same pattern as Phase 3 BusClient; `prefetch_count=1` (process one message at a time)
- **infotriage.embeddings**: existing HNSW index on `vector_cosine_ops` (from Phase 2); Phase 5 writes production embeddings into it; do not recreate/drop the index
- **Postgres**: single connection per worker (D-03a); no connection pool in Phase 5

## Acceptance Criteria

- [ ] `\d infotriage.enrichment` shows ccir, cnr, score, bucket, why, pmesii, tessoc columns
- [ ] `put_enrichment` / `get_enrichment` tests pass; double-write is idempotent
- [ ] `docker compose up -d triage` → container running; `GET /health` → 200
- [ ] POST `item.ingested` event → enrichment row written within 30 s
- [ ] Missing-article event does not crash triage (log + ack)
- [ ] Malformed LLM response → fallback enrichment row written (no crash)
- [ ] Score outside [0, 10] is clamped before storage
- [ ] Two near-duplicate articles → second gets `bucket='skip'`, `why` contains 'duplicate'
- [ ] Two distinct articles → both scored by LLM
- [ ] Embedding written to `infotriage.embeddings` for every processed article
- [ ] `verdict.ready` event received after item processed; VerdictReady fields are correct
- [ ] No `verdict.ready` published before enrichment commit
- [ ] Shadow-run shows ≥ 10 items with matching buckets between old and new path
- [ ] `docker compose up triage` → no `fever_triage.py` invoked; no fever cron in scheduler
- [ ] ccir.md hot-edit takes effect on next scoring run (not cached at startup)
- [ ] Container survives temporary RabbitMQ disconnect (reconnect via connect_robust)

## Edge Coverage

**Coverage:** 12/22 applicable edges covered · 3 backstop · 7 dismissed · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| boundary (score 0–10) | R1 | ✅ covered | CHECK constraint + clamp in parser; AC "score clamped to [0,10]" |
| empty (null why) | R1 | ⛔ dismissed | why is nullable TEXT; NULL stored as-is; no behavioral edge |
| encoding (TEXT fields) | R1 | ⛔ dismissed | Standard Postgres TEXT, UTF-8 storage; no length/encoding contract |
| precision (INT score) | R1 | ⛔ dismissed | INT is exact for 0–10; no rounding |
| idempotency (double-write) | R1 | ✅ covered | ON CONFLICT DO UPDATE; AC "double-write is idempotent" |
| concurrency (parallel writes) | R1 | 🧪 backstop | Concurrent put_enrichment under Postgres row-locking — held-out edge test |
| adjacency (duplicate item_id events) | R2 | ✅ covered | R1 upsert idempotency handles duplicate events |
| empty (no messages) | R2 | ⛔ dismissed | Consumer wait loop is standard aio-pika; no correctness edge |
| encoding (item_id) | R2 | ⛔ dismissed | sha256 hex is ASCII-safe; no encoding edge |
| ordering (message order) | R2 | ⛔ dismissed | Each item scored independently; order irrelevant |
| concurrency (parallel consumers) | R2 | 🧪 backstop | Two consumers racing on same queue — prefetch=1 mitigates; held-out edge test |
| boundary (score out of range) | R3 | ✅ covered | Score clamped [0,10] in fallback parser |
| precision (JSON parse failure) | R3 | ✅ covered | Fallback to score=0, ccir='none', cnr='Routine' (same as triage_score.py line 137) |
| concurrency (LLM timeout) | R3 | 🧪 backstop | LLM timeout → retry once then fallback skip — held-out edge test |
| unclassified | R4 | ✅ covered | First article in 7-day window has no prior embeddings → always scored; no false-positive dedup |
| boundary (cnr=none mapping) | R5 | ✅ covered | ccir='none' → cnr='Routine', bucket='skip' (VerdictReady.cnr is Literal['I','II','Routine']) |
| precision (ts timezone) | R5 | ⛔ dismissed | AwareDatetime in contracts enforces UTC; no edge |
| boundary (10-item minimum) | R6 | ⛔ dismissed | Shadow-run is a manual operator process; 10 is guidance, not an enforced hard limit |
| precision (parity definition) | R6 | ✅ covered | Parity = same bucket per item; exact score match not required (LLM is stochastic) |
| idempotency (remove fever twice) | R6 | ⛔ dismissed | Scheduler YAML is declarative; removing fever entry twice is idempotent |
| concurrency | R6 | ⛔ dismissed | N/A — one-time cutover operation |
| unclassified | R7 | ✅ covered | /health returns 200 (liveness only); bus disconnect handled by connect_robust reconnect |

## Prohibitions (must-NOT)

**Coverage:** 4/4 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| MUST NOT ack `item.ingested` before enrichment write committed — a crash between ack and write causes silent data loss | R2 | resolved | verification: test — negative test: mock put_enrichment to raise; assert message is nack'd not ack'd |
| MUST NOT cache `ccir.md` at startup — hot edits must take effect on next scoring run (D-5) | R3 | resolved | verification: test — modify ccir.md between two scoring runs; assert second run uses new content |
| MUST NOT publish `verdict.ready` before enrichment commit — event-before-data race (Phase 6 may query enrichment immediately on receiving event) | R5 | resolved | verification: judgment — code review: `bus.publish()` call must appear after `store.put_enrichment()` returns |
| MUST NOT cut over Fever if shadow-run parity check has < 10 sample items validated | R6 | resolved | verification: judgment — operator confirms shadow-run log shows ≥ 10 matching buckets before removing fever cron |

*Canon breadcrumbs (owned by /gsd-secure-phase, not minted here):*
- *OWASP injection into enrichment TEXT fields → /gsd-secure-phase*
- *AMQP credentials in logs → /gsd-secure-phase (T-04-01 pattern)*
- *Container running as root → /gsd-secure-phase*

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes |
|--------------------|-------|------|--------|-------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | Event-driven scorer with dedup + verdict.ready fully specified |
| Boundary Clarity   | 0.87  | 0.70 | ✓      | Phase 6/8/9/12 separation explicit; CCIR pre-filter (A-1) explicitly excluded |
| Constraint Clarity | 0.83  | 0.65 | ✓      | ADR-004, mE5-large@0.84, 7-day window, connect_robust, no pool |
| Acceptance Criteria| 0.80  | 0.70 | ✓      | 16 pass/fail criteria covering all 7 requirements |
| **Ambiguity**      | 0.149 | ≤0.20| ✓      | Gate passed after 3 rounds |

## Interview Log

| Round | Perspective | Question summary | Decision locked |
|-------|-------------|-----------------|-----------------|
| 1 | Researcher | Who owns enrichment DDL migration? | Phase 5 owns it — adds 7 columns + Store methods |
| 1 | Researcher | Dedup: inline or separate service? | Pre-filter in triage container before LLM call; oMLX embedding API |
| 1 | Researcher | Shadow-run: automated or manual? | Manual comparison of ≥10 items; same bucket = parity; not automated |
| 2 | Simplifier | What's the minimum viable triage? | Event loop + score + enrich + publish; dedup same phase |
| 2 | Researcher | Dedup window? | 7 days — matches ingest query window; mE5-large@0.84 from R2 spike |
| 2 | Boundary | A-1 CCIR cosine pre-filter in scope? | No — explicitly Phase 9 (RAG recall); infotriage.ccir table not used |
| 3 | Boundary | What is explicitly out? | SAB/brief, CNR alerts, entity res, RAG, Admiralty scoring, multi-worker |
| 3 | Boundary | What does "done" look like? | 111 articles scored, enrichment rows written, verdict.ready flowing, fever retired |

*[auto-selected] Rounds run autonomously from codebase context — user invoked with "continue".*

---

*Phase: 05-triage-app*
*Spec created: 2026-06-29*
*Next step: /gsd-discuss-phase 5 — implementation decisions (how to build what's specified above)*
