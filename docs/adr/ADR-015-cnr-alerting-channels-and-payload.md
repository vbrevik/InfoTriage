# ADR-015 — CNR Alerting Channels and Payload

**Status.** Proposed (2026-07-23). Drafted for **Phase 12 (CNR alerting / dissemination)**,
the final M2 phase. Locks the five sub-decisions so that `/gsd-discuss-phase 12` can
run with a tight scope (target: 3 turns instead of ~10) and `/gsd-plan-phase 12`
can produce a concrete wave breakdown without re-litigating channel/payload.

Continues the ADR lineage in `docs/adr/` (ADR-001..014). References —

* `ROADMAP.md` (Phase 12 entry + locked success criteria)
* `ccir.md` (CNR tier definitions)
* ADR-007 (bus + DLX substrate for the at-least-once outbox)
* ADR-013 (RIP doctrine — deep-link target rationale)
* ADR-014 (SOCMINT legal/ToS — local-only acceptance shape precedent)
* ADR-016 (read-only / local-first posture — **file currently missing**; see §Open Items)

---

## Context

Phase 12 will deliver a real-time notification lane so that a CNR CAT I 🚩 alert
does not require the operator to manually refresh the SAB. ROADMAP scope-locks
the success criterion as:

> 1. A CNR CAT I 🚩 post-write publishes a push (ntfy local-server preferred;
>    ADR-016-friendly) with SAB excerpt + dedupe ID.
> 2. The SAB remains the canonical artifact.

Several decisions are still open: tier coverage beyond CAT I, channel choice,
payload shape details, throttling, and failure-mode handling. ADR-015 here locks
those decisions so the planning surface for Phase 12 is tight, parallel development
is unblocked, and the `/gsd-discuss-phase 12` turn count drops from ~10 adaptive
questions down to ~3 (validate-confirm-confirm).

---

## Decision 1 — Tier coverage: CAT I 🚩 only

**Push only on CAT I 🚩.** CAT II 📋 stays SAB-only (the SAB IS the dagsbrief
treatment per `ccir.md` §CNR). Routine tier stays silent (omitted per `ccir.md`
§Routine NB).

### Rationale

* **CAT I is rare and high-signal.** Pushing on CAT II / Routine would create
  alert fatigue and erode the signal-to-noise advantage that CAT I inheritently has.
* **`ccir.md` carve-out honored.** *«Skal aldri drukne i bunken»* — CAT I
  *«must never drown in the pile»*. Treating CAT II the same way inverts this.
* **ROADMAP scope alignment.** Phase 12 SC 1 specifically lists CAT I only as the
  push target. Adding CAT II push would require re-scoping what Phase 12 ships.

### Out of scope (deferred)

CAT II push behavior — mutually exclusive with v1. May be added in a later phase
via optional quiet-hour windows or a secondary operator-tuned channel. Routine
remains forever silent (per `ccir.md`).

---

## Decision 2 — Channel: ntfy local-server (single primary)

**Single primary push channel: `ntfy` local-server** (`binwieder/ntfy` Docker
image, exposed on `localhost:2586`). Multi-channel re-delegation deferred.

### Rationale

* **ADR-016-aligned (local-first posture).** ADR-016 file is missing from
  `docs/adr/` (see §Open Items) but its stance is referenced across
  `ROADMAP.md`, ADR-014 Cross-Cutting §5, and the all-local-LLM rule. Local ntfy
  keeps the push inside the operator's Mac; no cloud-mediated push service, no
  outbound dependencies. See ADR-014 Cross-Cutting for the canonical reference
  of *«local-only tooling that satisfies platform Terms-of-Service»*.
* **ADR-014 precedent.** SOCMINT legal/ToS posture already accepts operator-
  managed local tooling that satisfies Telegram ToS without LLM-training; ntfy
  local-server is a structurally equivalent acceptance shape.
* **ARCHITECTURE.md alignment.** Already called out at lines ~181 + ~262 as the
  CAT I 🚩 dissemination path alongside the SAB.
* **Deployment cost is bounded.** +1 container (`ntfy`); +1 published port
  (localhost:2586 — D-03-compliant via `127.0.0.1`-only bind).

### Alternatives considered (rejected)

| Channel | Reject reason |
|---|---|
| Email (SMTP) | Outbound dependency + ADR-016 local-first break |
| Pushover / Pushbullet | Cloud-mediated; ADR-016 break |
| Signal (operator-managed) | Non-trivial new dependency; ecosystem mismatch with on-prem posture |
| Apple Push / FCM | Proprietary + cloud; hard ADR-016 break |
| No push (SAB-only) | Defeats the *«should not require manually refreshing the SAB»* goal |
| Multi-channel v1 (ntfy + email + Slack) | Defer to v2; v1 ships ntfy + outbox proven path |

---

## Decision 3 — Payload shape

JSON-encoded body posted to the ntfy topic `cnr-cat-i`. Shape:

| Field | Type | Source | Notes |
|---|---|---|---|
| `title` | string | `enrichment.why` first 80 chars (or summary first 80 if empty) | Single-line, no markdown |
| `sab_excerpt` | string | `summary` first 280 chars, ending at sentence boundary (`. `) if found | For mobile legibility |
| `dedupe_id` | string | `hashlib.sha256(f"{item_id}@{cnr_tier}".encode()).hexdigest()[:16]` | Stable *within* a CNR tier; cross-tier escalation (CAT II→CAT I) produces a fresh id + fresh push |
| `deep_link` | string | `obsidian://show-note?path=/Vault/items/<slugified-title>` | Always Obsidian; SAB URI reserved for future |
| `verified_pmseii` | string | `enrichment.pmseii` primary (e.g. `Military`, `Infrastructure`) | For at-a-glance operator relevance |
| `timestamp` | ISO-8601 UTC | `enrichment.created_at` with `Z` suffix | |
| `source_count` | int | `len(items)` after dedup collapse | If >1, item appears across multiple sources |

### Rationale* **`dedupe_id` collapses duplicate pushes within a tier.** When the same logical alert is published across overlapping sources (R3 entity-linked cross-language mentions), the dedupe_id (keyed on `item_id + cnr_tier`) is identical and downstream idempotency suppresses re-pushes within 24h (Decision 4). Cross-tier escalation (e.g. CAT II promoted to CAT I as evidence mounts) yields a *new* dedupe_id, so the escalation surfaces as a fresh push — not a suppression.
* **`deep_link` consistently targets Obsidian.** `ccir.md` + ADR-013 frame the
  operator's view as the *RIP layered in COP/CIP/CRP*. The canonical vault
  artifact backs the RIP; the SAB is a view. `sab://` URI is reserved but
  unimplemented pending Phase 12 wave plan.
* **280-char excerpt matches the operator's mobile reality.** Mobile push
  readability is the operator's daily workload; SAB-side deeper content is one
  tap away via the Obsidian deep-link.
* **`verified_pmseii` at-a-glance.** Addresses the operator's *«is this for me?»*
  question during a page. The field is the LLM-assigned primary PMESII domain
  per `ccir.md` §PMESII.

---

## Decision 4 — Throttling

Three-tier throttling, ordered by descending priority:

1. **Per-dedupe-ID idempotency.** `dedupe_id` already pushed in last 24h →
   suppress. Outbox table indexed by `dedupe_id`; rejection short-circuits at
   enqueue. Faster than going through retry.
2. **Per-tier sliding-window rate-limit.** Max **5 CAT I pushes per 10-minute
   sliding window** per channel (`localhost:2586`). Excess items queued; if
   still queued past 30 min, collapse to a single *«tier-1 burst»* multi-item
   alert (see §Payload shape §More-burst).
3. **PMESII-domain collapse.** ≥3 CAT I hits on the same primary `verified_pmseii`
   domain within 1h → coalesce to a single *«burst»* alert listing items by
   `pmseii + dedupe_id + title`. Addresses multi-theatre escalation moments
   (e.g. simultaneous NATO + Russia activity on Infrastructure).

### Rationale

* **Dedupe-24h prevents duplicate floods** across source overlap. R3 entity-linked
  cross-language mentions hit this path frequently.
* **Sliding-window rate-limit** is the simplest consumer-side rate governance;
  ADR-007 already discusses per-consumer queue caps in the bus topology layer.
* **PMESII-domain collapse** is a *«many simultaneous events»* natural feature.
  Reading operators can read a 4-item Infrastructure burst faster than 4 pinned pushes.

### Tier collapse is Phase 12 success-criterion-aligned

ROADMAP SC 1's *«publishes a push … with SAB excerpt + dedupe ID»* is met by
the simple-push path. Burst-mode is an enhancement to that contract and does
not relax it.

---

## Decision 5 — Failure modes

Outbox + at-least-once delivery anchored on the **RabbitMQ durable queue + DLX**
pattern (ADR-007) plus a PostgreSQL `cnr_outbox` table.

| Mode | Behavior |
|---|---|
| ntfy reachable | Direct push; outbox row marked `delivered_at = NOW()` after `200 OK` |
| ntfy unreachable | Persist to `cnr_outbox`; retry exp-backoff: 1m, 5m, 30m |
| 3 retry failures | Emit operator event (analogous to `feed.unhealthy` from `opml_health`, ADR-007) onto the bus; secondary channel (operator-direct email OR SAB red flag) |
| Outbox durable | Across container restarts; sized for 24h backlog with no SLA on the tail |
| Dead-letter rate-limit | 1 per hour to avoid re-flooding on ntfy-server recovery |

### Rationale

* **ADR-007's DLX pattern is the project-standard at-least-once delivery shape.**
  The CNR outbox layers on top rather than introducing a separate broker.
  RabbitMQ durability + Postgres outbox = sink-or-fail semantics on restart.
* **`opml_health` `feed.unhealthy` is the canonical operator-event precedent.**
  The same event schema + bus routing applies.
* **Rate-limited dead-letter is the simplest flood-prevention rule.** Operator
  wakes up to *«notifications failed, see outbox»* not to a 200-push burst when
  ntfy comes back.

---

## Cross-phase / cross-ADR alignment

* **ADR-013 (RIP doctrine).** Push payload's `deep_link` is Obsidian, the canonical
  vault artifact that backs the **Recognized Intelligence Picture** layered in the
  Common Operational Picture (COP) / Common Intelligence Picture (CIP) / Common
  Relevant Picture (CRP) framework. The inline SAB reminder honors that framing.
* **ADR-007 (RabbitMQ bus).** Outbox + dead-letter pattern is the bus's native
  primitives; no new infrastructure. R1 RabbitMQ round-trip + DLX (Phase 0 spike)
  validated the pattern at scale.
* **ADR-014 (SOCMINT legal/ToS).** Local-only channel decision mirrors the SOCMINT
  *«operator-managed, no LLM training»* pattern. Neither pushes to cloud nor relies
  on third-party crypto.* **Phase 13 (`phase_13_ingest_body_wiring`).** Phase 12 alerting reads from `verdict.ready` events + `enrichment` rows — computed by `triage_score.py` over `title + summary[:512]` per Phase 5 R2 spec (*never* the full body) and emits payloads derived from `enrichment.cnr`, `enrichment.why`, `enrichment.pmseii`, and `enrichment.created_at` — **not** from `articles.body`. Once Phase 13 wires `body TEXT` population in `apps/ingest-*` (per HANDOFF.json entry + `libs/store/sql/009-articles-body.sql`), an optional `body_excerpt` field may be added to §Payload shape **additively** without changing the rest of the contract. **Parallel Phase 12/13 dispatch is therefore safe by construction** — Phase 12 never reads `articles.body`, so Phase 13's body-population work is opaque to the alerting path.

---

## Consequences

### Positive

* **Operators get CAT I alerts without manual SAB refresh** — the stated Phase 12
  goal.
* **Local-first preserves privacy posture** consistent with ADR-013 / ADR-014 /
  ADR-016-stance (the all-local-LLM rule from `ROADMAP.md`).
* **Idempotent dedupe-ID prevents alert floods** across source overlaps and
  cross-language mentions (R3 entity linking).
* **Outbox is a proven pattern from ADR-007** — no novel infrastructure.

### Negative / surface area additions

* **+1 container** (`ntfy` local-server). +1 published port (localhost:2586).
  D-03 compliance audit needed for the new container before prod cutover.
* **Outbox adds an operational failure-mode** surface area. Operators + downstream
  tooling must monitor the bus operator events (e.g., paged on the
  *«notifications failed»* event).
* **280-char payload cap may be too short** for SAB slides with dense multi-source
  content. Consider a *«more»* deep-link to the SAB-served slide as a future
  enhancement (the Obsidian deep-link already provides a richer ticket in).

---

## References

* `ccir.md` §CNR — `CAT I 🚩 varsle straks` / `CAT II 📋 dagsbrief` / `Routine utelat`
* `.planning/ROADMAP.md` §Phase 12 — *«CNR CAT I 🚩 post-write publishes a push
  (ntfy local-server preferred; ADR-016-friendly) with SAB excerpt + dedupe ID»*
* `docs/adr/ADR-007-rabbitmq-bus.md` — bus + DLX pattern (outbox substrate)
* `docs/adr/ADR-013-recognized-picture-doctrine.md` — RIP framing (deep-link target rationale)
* `docs/adr/ADR-014-socmint-legal-and-tos.md` — local-only acceptance shape (channel precedent)
* ADR-016 referenced in `ROADMAP.md` *«all-local-LLM rule (ADR-016) is never
  revisited by a phase»* and ADR-014 Cross-Cutting; **ADR-016 file is missing
  from `docs/adr/`** — see §Open Items below.
* `docs/ARCHITECTURE.md` §Dissemination (~line 181 + ~line 262) — prior ntfy mentions
* `apps/opml_health/service.py` — `feed.unhealthy` operator-event precedent

---

## Open Items

* ✅ **RESOLVED 2026-07-23.** ADR-016 ("Airgap & Safety Doctrine: Local LLMs and
  Read-Only Ingest (supersedes ADR-004)") has been written and **Accepted**
  (`docs/adr/ADR-016-airgap-and-safety-doctrine.md`). ADR-015 can
  therefore reach *Accepted* status. Resolution trail lives at
  `.planning/HANDOFF.json` key `adr_004_resolved` — `resolution:
  superseded_by_adr_016`, `status: Accepted`,
  `migration_status: completed_2026-07-23_in-place_rename_applied`.
  Original blocker provenance: ROADMAP overview + ADR-014 §Cross-Cutting
  (renamed 004→016 in place) + `docker-compose.yml` local-only endpoints
  + `apps/llm-router.py` whitelist + archive audit (no ADR-004 file ever
  on disk per `git ls-files`, deletion log, fsck, reflog search).
  No remaining Turn-1 ask for `/gsd-discuss-phase 12`; ADR-015 →
  *Accepted* is unblocked.
* **SAB deep-link URI scheme.** `sab://` is reserved-but-unimplemented; pending
  Phase 12 wave plan. Does not block ADR-015 Acceptance because the Obsidian
  deep-link already covers the operator's primary action.
* **Push authentication topic ACL.** ntfy topics are ACL-able per topic; default
  `cnr-cat-i` is operator-only. Worth specifying in the Phase 12 PLAN rather
  than this ADR (configuration-level, not architectural).
