# Phase 1: Contracts + monorepo skeleton — Specification

**Created:** 2026-06-27
**Ambiguity score:** 0.14 (gate: ≤ 0.20)
**Requirements:** 6 locked

## Goal

Create one shared `libs/contracts` package — pydantic v2 `Item` schema, the four event
schemas, a lossless frontmatter⇆JSONB codec, and a bus-client interface with a working
in-memory implementation — and re-root the repo into `apps/` + `libs/`, with zero behavior
change to the running pipeline (all 56 existing tests still pass).

## Background

The monolith runs as host Python scripts under `bridge/` (gmail/imap/yt → atom), `score/`
(triage_score, digest, fever_triage, sab_html), and `opml/`, with tests in `tests/` (6 files,
~56 tests). There is no `apps/` or `libs/` structure and no shared schema — each script defines
its own ad-hoc item shape. The app-split design (`docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`,
§"The glue") names `libs/contracts` as the single source of truth all apps depend on and that
apps never import each other. `.env.example` already exists at repo root. This phase builds the
contract package and restructures the tree; it does NOT change pipeline behavior, stand up
Postgres/RabbitMQ, or split scripts into containerized apps.

## Requirements

1. **Canonical Item schema**: `libs/contracts` defines an `Item` pydantic v2 model.
   - Current: No shared schema; each script uses an ad-hoc dict/item shape.
   - Target: `Item(BaseModel)` with core (`id, source, source_type, url, title, ts, lang`),
     content (`summary`, `body_ref`), `payload: dict` (source-specific JSON), and
     `attachments: list` (blob refs). `id` is `sha256` of normalized `source_type + url + title`,
     computed at construction. `url` is optional (empty string in the hash when absent);
     `source_type`, `title`, `ts`, `lang` are required/non-null.
   - Acceptance: Constructing an `Item` twice with identical `source_type+url+title` yields the
     same `id`; an `Item` with no `url` constructs successfully; omitting a required field
     raises `ValidationError`. Tests cover all three.

2. **Event schemas**: pydantic v2 models for the four bus events.
   - Current: No event schemas exist.
   - Target: Models for `item.ingested`, `verdict.ready`, `sab.published`, `feed.unhealthy`
     in `libs/contracts`.
   - Acceptance: Each event model validates a well-formed payload and raises `ValidationError`
     on a missing required field. One round-trip test per event.

3. **frontmatter⇆payload codec**: lossless map between Obsidian YAML frontmatter and the
   Postgres JSONB-shaped dict.
   - Current: No codec exists; no defined bridge between markdown-native and JSON-native worlds.
   - Target: `to_frontmatter(payload)` / `from_frontmatter(text)` (or equivalent) that
     round-trip without loss, preserving nested dicts/lists, `None`, unicode, and datetimes
     (ISO-8601 with timezone, no precision loss).
   - Acceptance: A fixture payload containing nested structures, `None`, unicode, and a
     timezone-aware datetime survives `payload → frontmatter → payload` byte-for-value
     unchanged (test asserts deep equality).

4. **Bus-client interface + in-memory impl**: transport-swappable bus client.
   - Current: No bus client or interface exists.
   - Target: An abstract bus-client interface (`publish`, `subscribe`, idempotency by item id)
     plus a working in-memory implementation in `libs/contracts`.
   - Acceptance: Re-publishing the same item `id` is deduped (idempotent — second publish does
     not redeliver); delivery is FIFO per routing key; `subscribe` on an empty queue returns
     nothing (non-blocking no-op). Three tests cover dedup, ordering, empty-subscribe.

5. **Monorepo restructure**: repo split into `apps/` + `libs/`; existing scripts import the
   shared `Item`; tests still green.
   - Current: Scripts live flat under `bridge/`, `score/`, `opml/`; no `apps/`/`libs/`.
   - Target: Tree re-rooted into `apps/` (existing scripts re-homed, NOT split) + `libs/`
     (`libs/contracts`); at least one existing script imports `Item` from `libs/contracts`.
   - Acceptance: `apps/` and `libs/contracts` exist; an existing script imports `Item` from
     contracts; `pytest tests/` passes all 56 tests (count unchanged).

6. **Stale doc fixes**: correct three documentation claims that no longer match reality.
   - Current: Docs (a) call imap/youtube bridges "scaffolded", (b) imply PMESII/TESSOC scoring
     is TODO, (c) claim no `.env.example`.
   - Target: (a) imap/yt described as implemented (`bridge/imap_to_atom.py`,
     `bridge/yt_to_atom.py` exist), (b) PMESII/TESSOC marked done (implemented in `score/`),
     (c) `.env.example` documented as existing.
   - Acceptance: A grep of the named docs shows none of the three stale claims remain; each of
     the three corrections is present.

## Boundaries

**In scope:**
- `libs/contracts` package: `Item`, 4 event schemas, frontmatter⇆payload codec, bus-client
  interface + in-memory implementation
- Monorepo re-root into `apps/` + `libs/` (re-home existing scripts; one importing `Item`)
- Fixing the three stale doc claims
- Tests for Item id, event validation, codec round-trip, bus dedup/ordering/empty
- Import-boundary check proving no `apps/*` package imports another

**Out of scope:**
- Postgres / store implementation, DB schema, live DB wiring — Phase 2 (codec targets the
  JSONB *shape* only, no live database)
- Real RabbitMQ / AMQP transport — Phase 3 (in-memory bus only this phase)
- Splitting `bridge`/`score` into separate containerized apps — Phase 4+ (scripts only re-homed)
- Any `docker-compose.yml` changes — no infra changes this phase
- Any change to pipeline behavior — restructure must be behavior-preserving

## Constraints

- `Item` and event schemas use **pydantic v2** (`model_dump()`/`model_validate()`).
- `Item.id` = `sha256(normalized(source_type + url + title))` — content-stable, the bus
  idempotency/dedup key.
- The 56 existing tests must remain green (behavior-preserving restructure).
- The bus client lives behind an interface so the broker stays swappable (RabbitMQ lands Phase 3).
- No new paid/cloud/SaaS dependencies (NF-2); contracts carries no secrets or hardcoded endpoints.

## Acceptance Criteria

- [ ] `Item` (pydantic v2) exists with all named fields; `id` = sha256 of `source_type+url+title`
- [ ] Same `source_type+url+title` → same `id`; `url`-less item constructs; missing required field → `ValidationError`
- [ ] Four event models (`item.ingested`, `verdict.ready`, `sab.published`, `feed.unhealthy`) exist and validate
- [ ] Codec round-trips a fixture (nested dicts/lists, `None`, unicode, tz-aware datetime) with no loss
- [ ] In-memory bus: dedup by item id, FIFO per routing key, empty-subscribe is a no-op
- [ ] `apps/` + `libs/contracts` exist; an existing script imports `Item` from contracts
- [ ] `pytest tests/` passes all 56 tests (count unchanged)
- [ ] Three stale doc claims corrected (imap/yt implemented, PMESII/TESSOC done, `.env.example` exists)
- [ ] No `apps/*` package imports another `apps/*` package (import-boundary check passes)
- [ ] `libs/contracts` contains no credentials, tokens, or hardcoded host:port endpoints

## Edge Coverage

**Coverage:** 9/15 applicable edges resolved · 0 unresolved (6 dismissed as N/A)

| Category | Requirement | Status | Resolution / Reason |
|----------|-------------|--------|---------------------|
| adjacency | R1 | ✅ covered | Identical source_type+url+title → same id = same item (idempotent); AC#2 |
| empty | R1 | ✅ covered | url optional → empty string in hash; required fields non-null else ValidationError; AC#2 |
| ordering | R1 | ⛔ dismissed | Item is a single record; no collection ordering involved |
| empty | R2 | ✅ covered | Missing required event field → ValidationError; AC#3 |
| adjacency | R2 | ⛔ dismissed | Event schema definitions; no merge/collision semantics |
| ordering | R2 | ⛔ dismissed | Single event records; no ordering |
| boundary | R3 | ✅ covered | Nested dicts/lists, None, unicode preserved at type edges; AC#4 |
| precision | R3 | ✅ covered | Datetime serialized ISO-8601 with timezone, no precision loss; AC#4 |
| adjacency | R4 | ✅ covered | Re-publish same item id → deduped/idempotent; AC#5 |
| empty | R4 | ✅ covered | Subscribe on empty queue → non-blocking no-op; AC#5 |
| ordering | R4 | ✅ covered | FIFO per routing key; AC#5 |
| adjacency | R5 | ⛔ dismissed | Structural restructure requirement; no input-domain edge |
| empty | R5 | ⛔ dismissed | Structural restructure requirement; acceptance is "56 tests pass" |
| ordering | R5 | ⛔ dismissed | Structural restructure requirement; no input-domain edge |
| unclassified | R6 | ⛔ dismissed | Documentation correction; no input-domain edges (edge-free) |

## Prohibitions (must-NOT)

**Coverage:** 2/2 applicable prohibitions resolved · 0 unresolved

| Prohibition (must-NOT statement) | Requirement | Status | Verification / Reason |
|----------------------------------|-------------|--------|------------------------|
| No module under `apps/` may import another `apps/*` package; apps may only import `libs/contracts` | R5 | resolved | verification: test (grep/lint import-boundary check) |
| `libs/contracts` must not embed secrets, credentials, tokens, or hardcoded LLM/broker host:port endpoints | R1–R4 | resolved | verification: judgment (review — endpoints come from `.env` at runtime) |

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                      |
|--------------------|-------|------|--------|--------------------------------------------|
| Goal Clarity       | 0.88  | 0.75 | ✓      | Goal + 5 ROADMAP SC + enumerated Item fields |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Explicit out-of-scope (no DB/RabbitMQ/Docker/split) |
| Constraint Clarity | 0.85  | 0.65 | ✓      | pydantic v2, sha256 id, 56 tests green     |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 10 pass/fail criteria                      |
| **Ambiguity**      | 0.14  | ≤0.20| ✓      |                                            |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

| Round | Perspective     | Question summary                          | Decision locked                                  |
|-------|-----------------|-------------------------------------------|--------------------------------------------------|
| 1     | Researcher      | Schema tech for Item/events?              | pydantic v2                                      |
| 1     | Researcher      | Item.id generation scheme?                | sha256 content hash                              |
| 1     | Simplifier      | P1 depth — surfaces vs impl?              | All three (Item, codec, in-memory bus) implemented |
| 2     | Boundary Keeper | Content-hash input fields?                | source_type + url + title                        |
| 2     | Boundary Keeper | Which 3 stale doc claims in scope?        | imap/yt scaffolded, PMESII/TESSOC done, .env.example |
| 2     | Boundary Keeper | What's explicitly out of scope?           | No Docker changes, no app extraction (+ no live DB/RabbitMQ) |
| 5.5   | Failure Analyst | Item id / codec / bus edge cases          | url optional+collision=same; full codec fidelity; dedup+FIFO+empty-noop |
| 5.6   | Prohibition     | must-NOT invariants                       | No cross-app imports (test); no secrets in contracts (judgment) |

---

*Phase: 01-contracts-monorepo-skeleton*
*Spec created: 2026-06-27*
*Next step: /gsd-discuss-phase 1 — implementation decisions (package layout, codec API shape, bus interface methods)*
