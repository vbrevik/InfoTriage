# 12-PLAN — Phase 12 (CNR alerting / dissemination)

## 1. Overview

- **Operator decision (2026-07-23, `gsd-discuss-phase 12` Turn-1):** `INTEGRATED-SUB-WAVE`. Phase 13 (producer-side body wiring) ships as sub-wave **(f)** inside this Phase 12 PLAN rather than as a separate milestone phase.
- **5 locked sub-decisions (ADR-015):** D1 CAT I 🚩 only; D2 `ntfy` local-server as single primary channel; D3 7-field structured payload (`alert_id, sab_excerpt, dedupe_id, cnr_tier, item_link, pmseii_tags, deep_link`); D4 3-tier throttling (5/min, 10/10min, 1h PMESII collapse); D5 DLX + outbox failure modes.
- **Substrate on disk:**
  - `docs/adr/ADR-015-cnr-alerting-channels-and-payload.md` (locked)
  - `docs/adr/ADR-016-airgap-and-safety-doctrine.md` (`Accepted` 2026-07-23; supersedes ADR-004)
  - `libs/store/sql/009-articles-body.sql` (DDL applied; `body TEXT NULL`)
  - `apps/brief/main.py::_ENRICHMENT_SQL` + `apps/brief/consumer.py::_SELECT` + `apps/brief/renderer.py::render_links` already fetch `a.body`
- **Phase 12 success criteria (per `.planning/ROADMAP.md` §Phase 12):**
  - **SC 1.** CNR CAT I 🚩 post-write publishes a push to `ntfy` local-server with SAB excerpt + `dedupe_id`.
  - **SC 2.** SAB remains the canonical artifact (push + deep-link route to Obsidian, not into a separate push-only format).

## 2. Sub-wave ordering + dependency graph

```
        (a) ntfy container              ─┐
               │                          │
               ▼                          │
        (b) outbox + DLX                 ─┤
               │                          │
               ▼                          │
        (c) payload emitter              ─┤  Phase 12 main flow
               │                          │
               ▼                          │
        (d) throttling                   ─┤
               │                          │
               ▼                          │
        (e) failure-mode tests           ─┤
                                          │
        (f) Phase 13 body wiring         ─┘  bundled sub-wave
               │
               ▼
        verification + validation     ────  post-execution gates
```

- **(a)** `ntfy` container — standalone infra, no upstream deps.
- **(b)** outbox + DLX — RabbitMQ, depends on infrastructure.
- **(c)** payload emitter — 7-field builder, depends on (b) outbox routing.
- **(d)** throttling — 3-tier + 1h PMESII collapse, wraps/decorates (c) emitter.
- **(e)** failure-mode tests — depends on (a-d) being fully wired.
- **(f)** Phase 13 body wiring — orthogonal data expansion; runs LAST so wire-format inflation doesn't pollute alerting payload tests mid-execution.

## 3. Sub-wave (a) — ntfy container

- **Files:**
  - `docker-compose.yml` (new service `ntfy`)
  - `.env.example` (`NTFY_BASE_URL`, `NTFY_TOPIC_PREFIX`, `NTFY_AUTH_DEFAULT_ACCESS`)
  - `ops/Makefile` (`make ntfy-up`, `make ntfy-logs`, `make ntfy-publish-test`)
- **Compose snippet:**
  ```yaml
  services:
    ntfy:
      image: binwiederhier/ntfy:latest
      command: serve
      ports: ["80:80"]
      volumes: ["ntfy-cache:/var/cache/ntfy", "ntfy-auth:/etc/ntfy"]
      environment:
        - NTFY_AUTH_DEFAULT_ACCESS=deny-all
  ```
- **ACL pattern (per ADR-015 §Open Items 3):**
  - Topic `cnr-cat-i` — operator-only; required bearer token for read/write.
  - Topics `cnr-cat-i-debug`, `cnr-cat-i-test` — write-only; read access gated to operator UID.
- **AC (per ROADMAP SC 1):**
  - Container up; `make ntfy-up` exits 0.
  - `curl -X POST` to `NTFY_BASE_URL/cnr-cat-i` with auth header publishes message; consumer-side logs receipt.

## 4. Sub-wave (b) — outbox + DLX

- **Files:**
  - `apps/alerting/outbox.py` (new)
  - `libs/contracts/src/contracts/_events.py` (`verdict.ready`, `outbox.publish`, `outbox.dlx` event types)
  - `docker-compose.yml` (RabbitMQ DLX wired on existing `verdict.exchange`)
- **Wiring:**
  - Outbox exchange: `outbox.exchange` (fanout, durable).
  - Outbox queue: `outbox.queue` bound to `outbox.exchange`.
  - DLX: `outbox.dlx.exchange` + `outbox.dlx.queue` (TTL-bounded retry queue with exponential backoff).
- **Retry policy:**
  - 1st failure → requeue with 1s delay.
  - 2nd failure → requeue with 5s delay.
  - 3rd failure → DLX (terminal state; logged to `audit.dlq_terminal`).
- **AC:**
  - Failed message after 3 retries lands in `outbox.dlx.queue`; not lost.
  - Force-killed RabbitMQ → outbox retains; restart picks up.

## 5. Sub-wave (c) — payload emitter

- **Files:**
  - `apps/alerting/emitter.py` (new)
  - `apps/alerting/_payload_schema.py` (7-field schema constants per ADR-015 D3)
- **7-field payload (per ADR-015 D3):**
  ```python
  payload = {
      "alert_id":     uuid4().hex,
      "sab_excerpt":  item.summary,                                  # capped at 500 chars
      "dedupe_id":    sha256(f"{item.id}|{enrichment.cnr}").hexdigest()[:16],
      "cnr_tier":     enrichment.cnr,                                # "I" only per D1 lock
      "item_link":    obsidian_deep_link(item.id),                    # sab://item/<id> or obsidian:// URI
      "pmseii_tags":  enrichment.pmesii,                              # dict of P/M/E/S/I/I presence
      "deep_link":    obsidian_deep_link(item.id),                    # alias to item_link
  }
  ```
- **`dedupe_id` formula:** `sha256("{item_id}|{cnr_tier}").hexdigest()[:16]`. Reproducible across multiple emissions of the same CAT I item; 16-hex chars ≈ 64-bit truncation; collisions uncommon at alert volume (≤5 CAT I/day typical per `apps/triage/triage_score.py` scoring).
- **AC:**
  - Valid CAT I hit → 7-of-7 fields populated; `sab://` resolves in Obsidian.
  - `dedupe_id` reproducible (test: hash same item_id + cnr_tier twice → same hash).

## 6. Sub-wave (d) — throttling

- **Files:**
  - `apps/alerting/throttle.py` (new)
  - `apps/alerting/state.py` (sliding-window counters; in-memory + optional Redis)
- **3-tier throttling (per ADR-015 D4 + ADR-013 confidence-tier gating):**
  - **Tier 1 — 5/min cap:** any CNR tag; block any 6th alert within 60s.
  - **Tier 2 — 10/10min cap:** any CNR tag; block any 11th alert within 600s.
  - **Tier 3 — 1h PMESII collapse:** same dominant PMESII key as prior alert in last 60min → collapse to single "still-ongoing" alert (no duplicate push).
- **PMESII 1h-collapse guard:** read `enrichment.pmesii`, extract dominant dimension; if a prior CAT I alert carried the same dominant dimension within 60min → group; emit a single "still-ongoing" annotation instead of a fresh alert.
- **AC:**
  - 6 CAT I alerts in 60s window → only 5 emitted; 6th suppressed with audit line marking suppression reason.
  - Same dominant PMESII twice within 60min → 2nd alert collapsed to "still-ongoing" annotation; not pushed as fresh.

## 7. Sub-wave (e) — failure-mode tests

- **Files:**
  - `tests/test_outbox_failure_recovery.py`
  - `tests/test_ntfy_partition.py`
  - `tests/test_payload_malformat.py`
  - `tests/test_dedupe_id_collision.py`
  - `tests/test_pmseii_collapse_cooldown.py`
- **Test topology:**
  - **1 cross-cutting test** at `persist_and_publish` (bus-layer): inject oversized payload; assert ingestion pipeline still propagates (body-rollback naturally protects against oversize wire-format).
  - **Per-failure-mode unit tests:** outbox failure, ntfy down, malformed payload, duplicate `dedupe_id`.
- **AC:**
  - ntfy down for 5min → outbox retains ≤100 depth (bounded); on restart, all messages flush.
  - Malformed payload (e.g., missing `alert_id`) → caught at emitter's pre-flight; never enters outbox.
  - Duplicate `dedupe_id` within 30s → coalesced; 2nd emission suppressed.

## 8. Sub-wave (f) — Phase 13 body wiring (BUNDLED)

### 8.1 Schema + store changes

- **Files:**
  - `libs/contracts/src/contracts/_models.py` — add `body: Optional[str] = None` field to `Item`.
  - `libs/store/src/store/_postgres.py` — extend `put_item` INSERT:
    - Column list: `id, source, source_type, url, title, ts, lang, summary, body_ref, body, payload, discipline, admiralty_reliability` (13 columns).
    - ON CONFLICT DO UPDATE: add `body = EXCLUDED.body`.
  - `libs/store/src/store/_inmemory.py` — mirror `body` field (test parity).
- **DDL: not changing.** `libs/store/sql/009-articles-body.sql` already adds `body TEXT NULL`; this sub-wave populates the column.

### 8.2 Per-adapter body source (7 ingest adapters)

**Direct MCP/API adapters** — extract `body` from source payload during normalization, cap at 10,000 chars:

- **`apps/ingest-gmail/gmail_ingest.py`**:
  - **Body source:** Gmail MCP-parsed email body (raw `text/plain` or sanitized HTML rendered text).
  - **Cap:** 10,000 chars (post-bleach).
  - **HTML sanitization:** strip `<script>` / `<style>` tags + `on*-attrs` (XSS guard per ADR-016 read-only invariant — must NOT mutate the source blob).

- **`apps/ingest-telegram/telegram_ingest.py`**:
  - **Body source:** Telegram message full body (no special extraction beyond normalization).
  - **Cap:** 10,000 chars.

- **`apps/ingest-acled/acled_ingest.py`**:
  - **Body source:** ACLED event description (full event notes + actor + location).
  - **Cap:** 10,000 chars.

- **`apps/ingest-barentswatch/barentswatch_ingest.py`**:
  - **Body source:** AIS event payload (JSON-stringified).
  - **Cap:** 10,000 chars.

- **`apps/ingest-obsidian/obsidian_ingest.py`**:
  - **Body source:** full Obsidian vault file content (markdown body).
  - **Cap:** 10,000 chars.

**Atom-bridge adapters** — backfill from blob via `body_ref` (NOT re-fetch from source API):

- **`apps/ingest-imap/imap_ingest.py`**:
  - **Body source:** blob via existing `body_ref` (content-addressed hash into `libs/store/src/store/_blob.py`).
  - **Path:** `PostgresStore.get_blob(body_ref).decode("utf-8") → str body`; cap at 10,000 chars.
  - **Why backfill from blob, not re-fetch IMAP:** (a) cheaper (no IMAP round-trip), (b) ADR-016 read-only safe (no source mutation risk), (c) avoids Gmail IMAP rate-limit pressure.

- **`apps/ingest-youtube/youtube_ingest.py`**:
  - **Body source:** blob via existing `body_ref` (transcript bytes already persisted at ingest).
  - **Path:** `PostgresStore.get_blob(body_ref).decode("utf-8") → str transcript`; cap at 10,000 chars.

### 8.3 Sub-wave failure-rollback test surface

Per `HANDOFF.json` `phase_13_ingest_body_wiring.sub_wave_failure_rollback = "link-view-reverts-to-summary-only"`:

- **7 per-adapter rollback tests** (`tests/test_{adapter}_body_rollback.py`):
  - Mock body extraction / blob-read in each adapter to return a non-string type (`dict`, raw bytes, None).
  - Assert: exception caught at adapter layer, `body=None` written, `put_item` proceeds, ingest pipeline completes gracefully.
- **1 cross-cutting rollback test** (`tests/test_phase13_rollback.py`):
  - Inject raw `dict` body at `PostgresStore.put_item` boundary.
  - Assert: psycopg catches via type validation OR body coerced to str; ingest pipeline still propagates.
- **1 link-view reverting test** (`tests/test_link_view_summary_only_rollback.py`):
  - With `articles.body IS NULL`, `/sab?view=links` reads summary-only haystack; URL extraction under-extracts cleanly (no exception).

### 8.4 AC

- 7 adapters each have a body-population test (mock body + assert UPSERT writes both `body_ref` AND `body`).
- 7 adapters each have a body-rollback test (mock non-string body + assert graceful fallback to `body=None`).
- Link view `/sab?view=links` reads `body` post-sub-wave-f (no NULL after re-ingest); fallback to summary-only works on production-shaped NULL bodies.
- `_postgres.py::put_item` INSERT extends to 13 columns; round-trip `get_item` returns Item with `body` populated.

## 9. Cross-cutting considerations

- **ADR-015 D1-D5 cross-cites:** Phase 12 + bundled Phase 13 respect all 5 locked sub-decisions. Any drift from D1 (CAT I only) / D2 (ntfy only) / D3 (7-field payload) / D4 (3-tier throttling) / D5 (DLX+outbox) requires a new ADR supersession, not a code-only edit.
- **ADR-016 read-only invariant guards:**
  - Body extraction (`body = source.text`) — must NOT mutate source API; sanitization is local.
  - HTML sanitization bleaches `<script>` / `<style>` / `on*-attrs` only from cached body, never from the source.
  - Blob backfill is read-only (no source re-fetch).
- **Scorer isolation (`apps/triage/triage_score.py`):** scores on `title + summary[:512]` only; never reads body. Phase 13 sub-wave (f) MUST NOT add body to the scorer prompt (would inflate tokens + latency; cross-doc-locked in `12-CONTEXT.md` §Sub-wave Integration Rationale — body is OUTSIDE the scorer surface).
- **Enrichment/alerting/ingest independence:** body UPSERT runs on the ingest adapter path; throttling's PMESII 1h-collapse reads `enrichment.pmesii` only; alerting path (sub-waves a-e) does NOT read body.

## 10. Risks + decisions locked in

1. **HTML email sanitization (ADR-016 read-only).** Gmail/IMAP returning rich HTML risks XSS / UI breakage when rendering bodies in `/sab?view=links`. **Mitigation:** strip `<script>` / `<style>` / `on*-attrs` before body UPSERT; NEVER modify source.
2. **ATR transcript cap (YouTube).** Audio transcripts easily exceed 50 KB. **Mitigation:** hard 10,000-char cap on `item.body` writes; TOAST tables handle >2 KB transparently, but cap protects wire-format + Postgres heap.
3. **Enrichment race (sub-wave f).** Adapter UPSERTs body while LLM worker scores; 7-field ON CONFLICT may momentarily desync. **Mitigation:** atomic UPSERT (single transaction per DD-5); COALESCE on disambiguating fields.
4. **Bridge body-element ordering.** If `apps/ingest/yt_to_atom.py` / `imap_to_atom.py` is later extended with `<content>` (RFC 4287), `<content>` MUST come AFTER `<summary>` to prevent parser breakage on strict RSS readers. **Phase 13 sub-wave (f) deliberately does NOT touch the bridges — backfill from blob instead.**
5. **Test pyramid bloat.** 7 end-to-end adapter body tests risk brittle CI. **Mitigation:** 1 cross-cutting store/bus rollback test + 7 lightweight unit tests with mock blob returns. CI runtime stays bounded (~5 min target).

## 11. Verification + validation

### 11.1 Nyquist validation gate (per Phase 7 §Nyquist checklist)

- **`12-VERIFICATION.md`** — Nyquist coverage check at plan-exit time; `@codebuff` `/gsd-progress --forensic` passes.
- **`12-VALIDATION.md`** — acceptance criteria gate: SC 1 + SC 2 + sub-wave ACs (a-f) all pass.

### 11.2 Test surface total

| Sub-wave | New tests |
|---|---|
| (a) ntfy container | 1 (publish + auth) |
| (b) outbox + DLX | 3 (retry; DLX terminal; restart) |
| (c) payload emitter | 4 (valid 7-field; `dedupe_id` reproducible; field count; bounds) |
| (d) throttling | 3 (5/min; 10/10min; 1h PMESII collapse cooldown) |
| (e) failure-mode | 5 (outbox failure; ntfy partition; payload malformed; dedupe_id collision; PMESII collapse cooldown) |
| (f) Phase 13 body wiring | 14 (7 per-adapter happy-path + 7 per-adapter rollback) + 1 cross-cutting rollback + 1 link-view summary-only |
| **Total** | **~32 new tests** |

### 11.3 PTD (post-test-determinism) regression

- All sub-wave tests must be deterministic on production-shaped data.
- Mock-heavy test surface (mocks for IMAP / Gmail MCP / Telegram bot / AIS feed / ACLED API / Obsidian file system) ensures locality.

## Pending sub-sections

- **`12-VERIFICATION.md` + `12-VALIDATION.md`** — to be filled at execute-phase time per Nyquist checklist.
- **Execution:** invoke `/gsd-execute-phase 12` after this PLAN is reviewed + committed; sub-waves execute in dependency order (a)→(b)→(c)→(d)→(e)→(f).

## Update provenance

- **Filed:** 2026-07-23 during `/gsd-discuss-phase 12` Turn-1 → Turn-3 → PLAN dispatch.
- **Substrate on disk:** `.planning/phases/12-cnr-alerting-dissemination/12-CONTEXT.md` (Turn-1 captured); this `12-PLAN.md` is the wave-breakdown deliverable.
- **Decision sources:** Operator `ask_user` answers (Turn-1: INTEGRATED-SUB-WAVE; Turn-2: 5 sub-decisions confirmed; Turn-3: `sab://` + ntfy topic ACL picks).
- **HANDOFF.json anchors:**
  - `phase_12_phase_13_depend.verdict = "INTEGRATED-SUB-WAVE"`
  - `phase_12_phase_13_depend.dependency_class = "lock-step"`
  - `phase_13_ingest_body_wiring.bundled_in_phase_12 = true`
  - `phase_13_ingest_body_wiring.sub_wave_failure_rollback = "link-view-reverts-to-summary-only"`
