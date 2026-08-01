# Phase 12: CNR alerting / dissemination — Specification

**Created:** 2026-08-01
**Ambiguity score:** 0.155 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

A CNR CAT I 🚩 verdict produces exactly one authenticated push to the local ntfy server (7-field payload, dedupe-collapsed across `verdict.ready`/`sab.published`) within the throttle envelope, while the SAB stays the canonical artifact — no manual refresh needed.

## Background

Sub-wave (a) is already shipped: `infotriage-ntfy` container (binwiederhier/ntfy) runs healthy with `apps/ntfy/Dockerfile`, deny-all auth default, and `make ntfy-up`/`ntfy-publish-test` targets. Nothing else exists: `apps/alerting/` is absent — no outbox, emitter, throttling, or failure-mode tests. Decision substrate is locked: ADR-015 (D1 CAT I only, D2 ntfy single channel, D3 7-field payload, D4 3-tier throttling, D5 DLX+outbox), ADR-016 (airgap doctrine, supersedes ADR-004), and the INTEGRATED-SUB-WAVE verdict bundling Phase 13 (producer-side `articles.body` UPSERT) as sub-wave (f). Schema substrate `009-articles-body.sql` is applied; brief-side `_SELECT`/`_ENRICHMENT_SQL` already read `a.body`.

## Requirements

1. **CAT I alert emission**: A CAT I 🚩 enrichment triggers exactly one ntfy push carrying the 7-field payload (`alert_id, sab_excerpt, dedupe_id, cnr_tier, item_link, pmseii_tags, deep_link`).
   - Current: No emitter exists; CAT I verdicts are only visible on SAB refresh
   - Target: Emitter consumes `verdict.ready` AND `sab.published`; first event fires the push, second is suppressed via `dedupe_id` (atomic check-and-set, no race window)
   - Acceptance: Publishing a CAT I `verdict.ready` then its `sab.published` yields exactly 1 message on `cnr-cat-i`, 7-of-7 fields populated; the reverse order also yields exactly 1

2. **Dedupe**: `dedupe_id = sha256(f"{item_id}|{cnr_tier}").hexdigest()[:16]` with a 24h suppression TTL.
   - Current: No dedupe store
   - Target: Same item re-scored/replayed within 24h → no re-alert; after 24h TTL expiry → may alert again
   - Acceptance: Test proves same (item_id, cnr_tier) twice → same hash, one alert; TTL-expired entry alerts again (clock injected)

3. **Throttling (3-tier, sliding windows)**: ≤5 alerts pass per sliding 60s window, ≤10 per sliding 10min window; overflow collapses into one PMESII-grouped digest alert per hour.
   - Current: No throttle
   - Target: 5th alert in any 60s window passes; 6th collapses into the hourly digest (never silently dropped — digest enumerates suppressed alert_ids)
   - Acceptance: Boundary test: alerts #1–5 in 60s delivered individually, #6 absent from topic but present in the next digest; digest fires ≤1/hour

4. **Outbox + DLX (no alert lost)**: Failed ntfy publishes retry with 1s then 5s backoff, then dead-letter to `outbox.dlx.queue`; broker outage relies on unacked redelivery.
   - Current: No outbox
   - Target: Emitter acks `verdict.ready` only after successful outbox enqueue; ntfy-down → 3 attempts → DLX (logged to audit); RabbitMQ-down → message redelivered on broker restart (no local spool)
   - Acceptance: Test with ntfy stubbed dead: message lands in `outbox.dlx.queue` after 3 attempts, audit row written; kill-and-restart broker test (or mocked nack path): alert delivered post-restart

5. **Deep link**: `item_link`/`deep_link` are `obsidian://` URIs opening the item's vault note.
   - Current: ADR-015 Open Item 2 was undecided (`sab://` vs alternatives)
   - Target: `obsidian://open?vault=<vault>&file=<item-note-path>`; no custom protocol handler installed
   - Acceptance: Generated URI matches the Obsidian URI grammar and the note path the vault-writer produces for that item; link for an item with a written note opens it (manual UAT check)

6. **ntfy ACL**: deny-all default; `cnr-cat-i` requires bearer token for read AND write; `cnr-cat-i-debug`/`-test` are write-only (reads gated to operator UID).
   - Current: Container ships `NTFY_AUTH_DEFAULT_ACCESS=deny-all`; topic ACLs not provisioned
   - Target: Tokens provisioned via env (never committed); unauthenticated publish to `cnr-cat-i` is rejected; emitter fails closed (refuses to start) if its token env is missing/empty
   - Acceptance: `curl` without auth → 403; with token → 200; emitter started without `NTFY_TOKEN` exits non-zero with stderr message

7. **Body UPSERT — bundled Phase 13 sub-wave (f)**: All 7 ingest adapters (gmail, imap, youtube, telegram, barentswatch, acled, obsidian) UPSERT `articles.body` at ingest.
   - Current: `articles.body` column exists (009), brief-side reads it, but no adapter populates it
   - Target: Each adapter writes full body where the source has one; bodyless items (AIS pings, photo-only posts) keep `body` NULL — never empty-string; no size cap (TEXT), backstopped by a >1MB transcript test
   - Acceptance: Per-adapter test asserts body persisted for a body-bearing fixture and NULL for a bodyless fixture; scorer input remains `title + summary[:512]` (see P3)

8. **SAB stays canonical (SC 2)**: The push is a pointer, not a record.
   - Current: n/a (no alerting exists)
   - Target: Alert carries excerpt (≤500 chars) + links back to vault/SAB; adapter failure in sub-wave (f) degrades link-view to summary-only without blocking alert firing
   - Acceptance: Payload contains no field capable of reconstructing the item beyond the capped excerpt; alerting tests pass with `articles.body` NULL for all rows

## Boundaries

**In scope:**
- `apps/alerting/` — outbox layer (b), payload emitter (c), 3-tier throttle (d), failure-mode tests (e)
- ntfy topic ACL provisioning + token wiring (topping off shipped sub-wave (a))
- Producer-side `articles.body` UPSERT in all 7 ingest adapters — bundled Phase 13 sub-wave (f)
- Contract events for outbox flow as needed (`outbox.*`)

**Out of scope:**
- CAT II / full-tier alerting — D1 locks CAT I only; future re-baseline must cite 12-CONTEXT.md
- Any second push channel (email, Slack, APNs, upstream ntfy.sh) — D2 single channel; ADR-016 airgap
- Custom `sab://` macOS protocol handler — decided against (obsidian:// chosen, zero install)
- Alert history/archive UI — P5 prohibition; SAB is the record
- Scorer changes — body never feeds the scorer prompt (999.2 R2 spec, P3)
- Multi-user topic fan-out / M3 auth — Milestone 3

## Constraints

- ADR-016: local-only LLM + read-only ingest invariants; ntfy binds 127.0.0.1, no upstream relay (P1)
- ADR-007 DLX pattern is the outbox substrate — reuse existing RabbitMQ topology idioms in `_bus_rabbitmq.py`
- ADR-013 drives the `dedupe_id` formula and D4 PMESII collapse trigger
- Throttle windows are sliding, not fixed-clock
- Alert volume assumption: ≤5 CAT I/day typical — 16-hex dedupe truncation acceptable at this volume

## Acceptance Criteria

- [ ] CAT I `verdict.ready` → exactly 1 push on `cnr-cat-i` with 7-of-7 payload fields; subsequent `sab.published` for the same item does not re-fire (and vice versa)
- [ ] `dedupe_id` reproducible; 24h TTL suppression proven with injected clock
- [ ] Sliding-window throttle: #1–5/60s delivered, #6 collapsed into hourly PMESII digest that enumerates suppressed alert_ids; nothing silently dropped
- [ ] ntfy dead → 1s/5s retries → `outbox.dlx.queue` + audit row; broker restart → redelivery (emitter acks only after enqueue)
- [ ] `obsidian://` URI matches the vault-writer's note path for the item
- [ ] Unauthenticated publish to `cnr-cat-i` → 403; emitter without token env fails closed at startup
- [ ] 7/7 adapters: body persisted for body-bearing fixture, NULL (not "") for bodyless fixture; >1MB transcript backstop test passes
- [ ] Alerting suite green with all `articles.body` NULL (failure isolation: body wiring never blocks alerts)
- [ ] Negative: `sab_excerpt` length ≤500 and never sourced from `articles.body` (P2)
- [ ] Negative: scorer prompt input remains `title + summary[:512]` (P3)
- [ ] Negative: an enrichment with `cnr != "I"` produces zero messages on `cnr-cat-i` (P4)
- [ ] Negative: compose config binds ntfy to 127.0.0.1 with no upstream/relay config (P1)

## Edge Coverage

**Coverage:** 19/19 applicable edges resolved · 0 unresolved

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| unclassified | R1 | ✅ covered | Dual-trigger race → atomic dedupe check-and-set (AC 1) |
| adjacency | R2 | ✅ covered | Re-scored item within TTL suppressed; 24h TTL decided (AC 2) |
| empty | R2 | ✅ covered | Non-CAT-I / NULL cnr → no alert at all (D1; AC — P4 negative) |
| encoding | R2 | ⛔ dismissed | item_id is lowercase hex ASCII (sha256 of item) — no normalization ambiguity |
| ordering | R2 | ⛔ dismissed | Single-value hash, no collection ordering exists |
| boundary | R3 | ✅ covered | ≤5 pass semantics: #5 delivered, #6 collapses (AC 3) |
| precision | R3 | ✅ covered | Sliding windows decided — no fixed-clock burst loophole (AC 3) |
| unclassified | R4 | ✅ covered | Total-outage: ack-after-enqueue + broker redelivery, no spool (AC 4) |
| adjacency | R5 | ⛔ dismissed | One URI per item; no merge/collision semantics apply |
| empty | R5 | ⛔ dismissed | Deep-link may 404 until `sab.published` — operator accepted this transient when choosing dual-trigger |
| ordering | R5 | ⛔ dismissed | Single URI, no ordering |
| adjacency | R6 | ⛔ dismissed | Static topic set; no dynamic topic adjacency |
| empty | R6 | ✅ covered | Missing/empty token env → emitter fails closed (AC 6) |
| ordering | R6 | ⛔ dismissed | ACL rules are per-topic constants, no order sensitivity |
| adjacency | R7 | ⛔ dismissed | Body UPSERT is last-write-wins per existing put_item semantics — no new adjacency |
| empty | R7 | ✅ covered | Bodyless item → NULL, never empty string (AC 7) |
| encoding | R7 | 🧪 backstop | No size cap on TEXT; held-out >1MB transcript test — carried into plan-phase must_haves |
| ordering | R7 | ⛔ dismissed | Per-adapter independent writes; no cross-adapter ordering contract |
| unclassified | R8 | ✅ covered | Handled as prohibition P5 + failure-isolation AC 8 |

## Prohibitions (must-NOT)

**Coverage:** 5/5 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| Alerts MUST NOT leave the machine — ntfy binds 127.0.0.1 only, no upstream ntfy.sh relay/APNs | R6 | resolved | test — compose/config assertion (check_kind: node-test; target: tests/test_alerting_prohibitions.py) |
| `sab_excerpt` MUST NOT exceed 500 chars nor ever be sourced from `articles.body` | R1, R8 | resolved | test — payload assertion in emitter tests |
| The scorer prompt MUST NOT include `articles.body` — input stays `title + summary[:512]` | R7 | resolved | test — scorer-input assertion (existing 999.2 R2 spec guard, extended) |
| Non-CAT-I tiers MUST NOT produce messages on `cnr-cat-i` | R1 | resolved | test — negative emitter test (cnr="II" → 0 messages) |
| The push channel MUST NOT become an independent record of intel (no alert archive/history UI) | R8 | resolved | judgment — reviewed at verify-phase against SC 2 |

Canon breadcrumb: bearer-token-in-repo is canon secrets hygiene — owned by global boundary rules + secret scanning; not minted here.

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                    |
|--------------------|-------|------|--------|------------------------------------------|
| Goal Clarity       | 0.90  | 0.75 | ✓      | D1–D5 locked; trigger point decided      |
| Boundary Clarity   | 0.80  | 0.70 | ✓      | INTEGRATED-SUB-WAVE + explicit out-list  |
| Constraint Clarity | 0.85  | 0.65 | ✓      | ADR-016 airgap; ACL + windows locked     |
| Acceptance Criteria| 0.80  | 0.70 | ✓      | 12 pass/fail criteria incl. 4 negatives  |
| **Ambiguity**      | 0.155 | ≤0.20| ✓      |                                          |

## Interview Log

| Round | Perspective    | Question summary                          | Decision locked                                             |
|-------|----------------|-------------------------------------------|-------------------------------------------------------------|
| 1     | Researcher     | Trigger point: verdict.ready vs sab.published? | Both — fire on first, dedupe_id collapses the second     |
| 1     | Researcher     | Deep-link scheme (ADR-015 OI 2)?          | `obsidian://` URI — no custom handler                       |
| 1     | Researcher     | ntfy topic ACL (ADR-015 OI 3)?            | PLAN draft confirmed: deny-all, bearer both directions      |
| edge  | Failure Analyst| Dedupe retention window?                  | 24h TTL                                                     |
| edge  | Failure Analyst| Throttle boundary + window type?          | ≤5 pass, sliding windows                                    |
| edge  | Failure Analyst| Total broker outage persistence?          | Ack-after-enqueue redelivery; no local spool                |
| edge  | Failure Analyst| 5 minor edges batch                       | Accepted (atomic dedupe, 404 transient, fail-closed token, NULL body, >1MB backstop) |
| prob  | Prohibition    | 5 minted prohibitions                     | All 5 accepted (P1 airgap, P2 excerpt, P3 scorer, P4 CAT I-only, P5 no archive) |

---

*Phase: 12-cnr-alerting-dissemination*
*Spec created: 2026-08-01*
*Next step: /gsd-discuss-phase 12 — implementation decisions (outbox module shape, throttle store, token provisioning)*
