# 12-CONTEXT — Phase 12 (CNR alerting / dissemination)

## Operator Decisions (Turn-1, 2026-07-23)

- **Workflow shape — `INTEGRATED-SUB-WAVE`.** Phase 13 (producer-side article body wiring) ships as a dependent sub-wave **inside** the Phase 12 PLAN rather than as a separate milestone phase. Both alerting layer + `body` payload delivery land lock-step; no degraded `/sab?view=links` URL extraction on day 1.
- **ADR-004 resolution — ADR-016 supersede confirmed.** `docs/adr/ADR-016-airgap-and-safety-doctrine.md` (`Accepted` 2026-07-23) stands as the canonical codification of the operative "ADR-004" stance. ADR-004 itself remains unrecoverable per git archaeology; ADR-016 codifies the operative stance across `ROADMAP.md`, `ADR-014 §Cross-Cutting`, `docker-compose.yml`, and `apps/llm-router.py`.

## Locked ADR Substrate (carry-forward into PLAN)

- **ADR-015** (`docs/adr/ADR-015-cnr-alerting-channels-and-payload.md`) — 5 locked sub-decisions: **(D1)** CAT I 🚩 only. **(D2)** `ntfy` local-server as single primary channel. **(D3)** 7-field structured payload (`alert_id, sab_excerpt, dedupe_id, cnr_tier, item_link, pmseii_tags, deep_link`). **(D4)** 3-tier throttling (5/min, 10/10min, 1h PMESII collapse). **(D5)** DLX + outbox failure modes. §Open Items 1 ✅ RESOLVED 2026-07-23 via ADR-016 supersede; §Open Items 2 (`sab://` URI scheme) + 3 (ntfy topic ACL) deferred to PLAN.
- **ADR-016** (`docs/adr/ADR-016-airgap-and-safety-doctrine.md`) — Status: `Accepted 2026-07-23`. Codifies `local-llm-only` + `read-only-ingest` invariants post ADR-004 unrecoverability. `§If-read-only-impossible` carries the Gmail App Passwords 2SV hard-block (2026-06-29, `ROADMAP.md` Phase 4 §SC 3) as the first-operative-firing precedent.
- **Cross-ADR cross-cites:**
  - **ADR-007** (`rabbitmq-bus`) — DLX pattern is the substrate for the D5 outbox failure delivery.
  - **ADR-013** (`recognized-picture-doctrine`) — confidence-tier gating drives the `dedupe_id` sha formula + D4 PMESII 1h-collapse trigger.
  - **ADR-014** (`socmint-legal-and-tos`) — SOCMINT ingest licensing precedent. ADR-014 §Cross-Cutting now cross-cites ADR-016 (in-place rename ADR-004 → ADR-016 applied 2026-07-23).

## Sub-wave Integration Rationale

- **Lock-step delivery.** Schema substrate is in place: `libs/store/sql/009-articles-body.sql` applied (`feat(schema)` commit); consumer-side `_ENRICHMENT_SQL` (apps/brief/main.py) and `_SELECT` (apps/brief/consumer.py) already fetch `a.body`. Shipping Phase 13 as a sub-wave inside Phase 12 means `/sab?view=links` reads full body on day 1 — no `summary-only` degraded-UX window for CAT I 🚩 hits.
- **Architectural separation preserved.** `apps/triage/triage_score.py` scores on `title + summary[:512]` only (Phase 999.2 R2 spec). Producer-side body UPSERT does **not** feed the scorer prompt, does **not** feed the alert payload (which derives from `enrichment.cnr/why/pmseii/created_at` + `summary` per ADR-015 D3), and does **not** touch `ntfy` channels. Body population is bound to the ingest layer; scorer's 512-char cap and ADR-013 confidence tiering are unaffected.
- **Failure-isolation.** If a Phase 13 sub-wave UPSERT step fails for a specific adapter (`apps/ingest-{gmail,imap,youtube,telegram,barentswatch,acled,obsidian}`), the rollback path is **`link-view-reverts-to-summary-only`** (Phase 12 alerting stays up; the operator's CAT I workflow runs through the Obsidian deep-link, not the link view). The body population failure does **not** block alert firing.

## Phase 12 Success Criteria (per `.planning/ROADMAP.md` §Phase 12)

- **SC 1.** CNR CAT I 🚩 post-write publishes a push to `ntfy` local-server (ADR-016-friendly) with SAB excerpt + `dedupe_id`.
- **SC 2.** SAB remains the canonical artifact (push + deep-link route to Obsidian, not into a separate push-only format).

## Open Items for Turns 2-3

1. Confirm the 5 locked sub-decisions (D1–D5 from ADR-015) operator-confirmed at the discuss-phase level — i.e. no late-stage architectural revisions.
2. Sub-wave breakdown for the Phase 12 PLAN:
   - **Phase 12 sub-waves:** `(a)` ntfy container service, `(b)` outbox layer w/ DLX, `(c)` payload emitter, `(d)` throttling (5/min, 10/10min, 1h PMESII collapse), `(e)` failure-mode tests.
   - **Phase 13 sub-wave (bundled):** `(f)` producer-side body UPSERT for the 7 ingest adapters.
3. `sab://` URI scheme shape (operator pick on ADR-015 §Open Items 2).
4. `ntfy` topic ACL specifics (operator pick on ADR-015 §Open Items 3).

## Cross-ADR Citations Summary

- `ADR-007` (rabbitmq-bus) — outbox failure delivery via DLX.
- `ADR-013` (recognized-picture-doctrine) — `dedupe_id` formula + D4 PMESII 1h-collapse trigger.
- `ADR-014` (socmint-legal-and-tos) — SOCMINT licensing precedent; local-only LLM (now cross-cites ADR-016).
- `ADR-015` (cnr-alerting-channels-and-payload) — **Primary ADR for Phase 12**.
- `ADR-016` (airgap-and-safety-doctrine, supersedes ADR-004) — `local-llm-only` + `read-only-ingest` invariants.

## Downstream Phase Implications

- **Phase 14+ assumption correction.** Future phases (Phase 14, M3, etc.) that reference `articles.body` population can ASSERT body population is complete only AFTER Phase 12 has shipped (machine-checkable ground: `HANDOFF.json` `phase_12_phase_13_depend.verdict = INTEGRATED-SUB-WAVE`). The "Phase 13 bundled in Phase 12 PLAN sub-wave" choice means Phase 13 is no longer independently shippable; any downstream ADR/PLAN that treats Phase 13 as a separate, prior-stage phase must be revised to cite 12-CONTEXT.md's locked-Phase-12-shipped gate.
- **M3 readiness gate.** Milestone 3 (multi-user / team server) §Auth/topic ACL must NOT mirror the `articles.body = NULL` assumption from before this change; new M3 ADRs should explicitly cite 12-CONTEXT.md §Sub-wave Integration Rationale as the schema baseline (body populated at ingest).
- **Future-tier re-baseline.** Any future phase that revisits CNR tier coverage (CAT I → CAT II or full-tier) or `articles.body`-population state must cite 12-CONTEXT.md §Phase 12 Success Criteria + §Sub-wave Integration Rationale as the locked-Phase-12 baseline rather than redefine from earlier phases.

## Pending Sub-sections

- **12-PLAN.md** — to be drafted (chained into `/gsd-plan-phase 12` after discuss-phase concludes): wave ordering, sub-wave sequencing, failure-isolation test scaffolding.
- **12-VERIFICATION.md** + **12-VALIDATION.md** — to be filled at PLAN-execution time per Phase 7 §Nyquist checklist.

## Update Provenance

- **Filed.** 2026-07-23 during `/gsd-discuss-phase 12` Turn-1.
- **Decision sources.** Operator answer to `ask_user` Q1 (workflow shape — option 3: parallel + Phase 13 sub-wave in Phase 12 PLAN) + Q2 (ADR-004 path — option 1: confirm ADR-016 supersede).
- **HANDOFF.json anchor.** `phase_12_phase_13_depend.verdict = "INTEGRATED-SUB-WAVE"`; `phase_13_ingest_body_wiring.bundled_in_phase_12 = true`.
