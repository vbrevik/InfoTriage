---
phase: 1
slug: contracts-monorepo-skeleton
status: draft
shadcn_initialized: false
preset: none
created: 2026-06-27
---

# Phase 1 — UI Design Contract

> **Scope declaration — read first.**
>
> Phase 1 ships NO user-facing UI surface. Its deliverables are entirely
> data-layer: a Python package (`libs/contracts`), four event schemas, a
> codec, a bus interface, and a monorepo restructure. The repo contains no
> React, no Vite, no Next.js, and no browser build.
>
> This UI-SPEC therefore answers a narrower question: **what contract
> obligations do the schemas defined in this phase owe the downstream
> SP-COP canvas UI, so that canvas can render correctly?**
>
> Each section of the standard template is present. Sections that have no
> Phase 1 surface are marked N/A with a one-line reason. The substantive
> content lives in §Schema Obligations.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none — Python package, no frontend component library |
| Preset | not applicable |
| Component library | not applicable |
| Icon library | not applicable |
| Font | not applicable — locked in sketch-findings for Phase 6+ (see §Locked Design Tokens) |

---

## Spacing Scale

**N/A — no layout surface ships in this phase.**

Spacing scale will be declared for Phase 6 (Brief app / SP-COP canvas) when
the first browser surface is built. The 8-point scale (4/8/16/24/32/48/64)
is the default; the sketch validated `11px`/`13px` padding inside `.bluf`
blocks (deviates from the scale — captured in §Locked Design Tokens).

---

## Typography

**N/A — no text surface ships in this phase.**

Locked values from sketch-findings (source of truth for Phase 6 executor):

| Role | Size | Weight | Line Height | Font stack |
|------|------|--------|-------------|------------|
| Body / cited evidence | 13px | 400 | 1.55 | `var(--sans)` = system-ui stack |
| Mono labels, tags, citation superscripts | 13px | 400 | — | `var(--mono)` = ui-monospace/"SF Mono"/JetBrains Mono/Menlo |
| BLUF paragraph | 13px | 400 | 1.55 | `var(--sans)` |

Source: `sources/themes/default.css`, `references/sp-cop-canvas.md` — do not
re-ask; treat as locked.

---

## Color

**N/A — no color surface ships in this phase.**

Locked design tokens from sketch-findings (locked for Phase 6+):

| Role | Token | Hex | Usage |
|------|-------|-----|-------|
| Dominant (60%) | `--bg` | `#0a0e14` | Page background |
| Dominant (secondary) | `--bg-2` | `#0e131c` | BLUF gradient stop |
| Secondary (30%) | `--surface` | `#121826` | Cards, BLUF block, segmented control |
| Secondary deep | `--surface-2` | `#18202f` | Active seg-button, hover states |
| Border (subtle) | `--border` | `#233044` | Card borders, control outlines |
| Border (strong) | `--border-2` | `#2e3e57` | Focus ring, dividers |
| Text (default) | `--text` | `#c8d3e3` | Body text, labels |
| Text (dim) | `--text-dim` | `#6b7a92` | Timestamps, secondary metadata |
| Text (bright) | `--text-bright` | `#eaf1fb` | Headings, selected states |
| Accent (10%) | `--accent` | `#46c6ff` | Known / directed / CCIR — cyan |
| Discovery accent | `--accent-2` | `#ffb347` | Unknown / new items — amber |
| Serendipity | `--discovery` | `#ff8adf` | LOOK-mode serendipity — magenta |
| CNR CAT I | `--cnr1` | `#ff4d5e` | Urgency: CAT I alert — red |
| CNR CAT II | `--cnr2` | `#ffb347` | Urgency: CAT II — amber |
| CNR routine | `--cnr0` | `#4a6a8a` | Routine / no urgency — slate |
| OK / success | `--ok` | `#46d39a` | POC topic accent, health pass — green |

Accent (`--accent`) reserved for: CCIR-directed known items only (BLUF block
left border, citation superscripts, segmented-control active state, "new" dot
on known items). `--accent-2` reserved for: new/unknown/discovery items, CAT
II urgency, new-item badge count. Never use accent as a universal interactive
color.

Source: `sources/themes/default.css` — treat as locked, do not re-derive.

---

## Copywriting Contract

**N/A — Phase 1 ships no user-visible copy.**

Data-layer copywriting obligations that the schemas must satisfy are in
§Schema Obligations §3 (field semantics).

Locked UI copy from sketch-findings (for Phase 6 executor — do not re-ask):

| Element | Copy |
|---------|------|
| Delta empty state heading | "All caught up" |
| Topic before first assessment (Back-in-time) | "ingen vurdering ennå" |
| Delta collapsed older-items line | "+N earlier — already read" |
| Mark-all-read action label | "✓ mark all read" |

---

## Registry Safety

**N/A — no shadcn, no npm, no browser components in this phase.**

Registry safety gate: not applicable. No third-party frontend blocks are
declared.

---

## Schema Obligations for Downstream UI

This section is the primary output of this UI-SPEC. It defines what the
`libs/contracts` data contracts defined in Phase 1 **must guarantee** so
that the SP-COP canvas (Phase 6) can render the HEADLINES / delta / Back-in-time
views without schema renegotiation. These obligations are binding on the Phase 1
implementer.

### 1. `Item` Fields Required by the UI

The pydantic `Item` model defined in Phase 1 (SPEC R1) carries the source
record. The SP-COP HEADLINES view depends on the following fields:

| Field | Type | Required | UI Dependency |
|-------|------|----------|---------------|
| `id` | `str` (sha256 hex) | yes | Dedup key — delta logic identifies new vs seen items by id |
| `source` | `str` | yes | Displayed in cited-evidence row: source·day |
| `source_type` | `str` | yes | Part of id hash; drives icon/label in citation row |
| `url` | `str` (optional — empty str in hash when absent) | no | Citation link in `[N]` superscripts; absence = no link rendered |
| `title` | `str` | yes | Cited-evidence headline text in HEADLINES view |
| `ts` | `datetime` (tz-aware, ISO-8601) | yes | Delta cutoff (since-last-read); "latest-stamp" per topic header; Back-in-time day comparison |
| `lang` | `str` | yes | Source language label in citation row; multilingual corpus display |
| `summary` | `str` (optional) | no | Input to BLUF synthesis in Phase 6; blank summary = LLM synthesizes from title only |
| `body_ref` | `str` (optional) | no | Blob reference for full-text expand-on-demand |
| `payload` | `dict` | yes | Carries scoring fields written by Phase 5 triage (see below); must be mutable/extensible without schema migration |
| `attachments` | `list` | yes | Blob refs for PDF/image attachments shown in FOCUS mode |

**Scoring fields in `payload`** (written by Phase 5, read by Phase 6 UI):

These are NOT `Item` fields today (scoring happens downstream of ingestion),
but the `payload: dict` contract established in Phase 1 must be extensible
enough to hold them without a schema change. Phase 5 will write:

| Key | Type | UI Dependency |
|-----|------|---------------|
| `ccir` | `str \| None` | Topic-group header in HEADLINES; `None` = item does not appear in CCIR view |
| `cnr` | `"I" \| "II" \| "Routine" \| None` | Urgency color: I→`--cnr1` red, II→`--cnr2` amber, Routine→`--cnr0` slate |
| `score` | `int` 0–10 | Keep/maybe/skip bucket; HEADLINES shows keep (≥7+CCIR) + maybe; hides skip |
| `bucket` | `"keep" \| "maybe" \| "skip"` | Explicit bucket for UI filtering; derived from score+ccir but stored for query efficiency |
| `why` | `str` | Triage rationale — shown as tooltip/annotation in FOCUS mode |

Phase 1 obligation: `payload` must be typed as `dict` (not constrained to a
closed set of keys), so Phase 5 can write these fields without touching
`libs/contracts`.

### 2. Event Schema Fields Required by the UI

#### `item.ingested`

Published by Phase 4 ingest adapters. The SP-COP item list (unscored inbox
view, if ever shown) and the bus fan-out depend on:

| Field | Type | Required | UI / Downstream Dependency |
|-------|------|----------|---------------------------|
| `event` | `"item.ingested"` literal | yes | Routing key discriminator |
| `item_id` | `str` (sha256 hex) | yes | Foreign key to `Item`; dedup reference |
| `source` | `str` | yes | Inline display without a DB lookup in list views |
| `ts` | `datetime` tz-aware | yes | Timestamp for ordering and delta cutoff |

#### `verdict.ready`

Published by Phase 5 triage. The HEADLINES view is built entirely from this
event's payload:

| Field | Type | Required | UI Dependency |
|-------|------|----------|---------------|
| `event` | `"verdict.ready"` literal | yes | Routing discriminator |
| `item_id` | `str` | yes | Join to `Item` for title/url/source display |
| `ccir` | `str \| None` | yes | Topic-group header; `None` = item omitted from HEADLINES |
| `cnr` | `"I" \| "II" \| "Routine"` | yes | Urgency chip color (cnr1/cnr2/cnr0 tokens) |
| `score` | `int` 0–10 | yes | Bucket computation; filter threshold |
| `bucket` | `"keep" \| "maybe" \| "skip"` | yes | Primary filter for HEADLINES (keep+maybe shown) |
| `why` | `str` | yes | Triage rationale for tooltip/annotation |
| `ts` | `datetime` tz-aware | yes | Verdict timestamp; used as "assessed at" for delta |

#### `sab.published`

Published by Phase 6 `brief` app when a SAB is rendered. The SP-COP canvas
**is** the interactive form of the SAB, so this event is the primary data
feed for the HEADLINES canvas:

| Field | Type | Required | UI Dependency |
|-------|------|----------|---------------|
| `event` | `"sab.published"` literal | yes | Routing discriminator |
| `pub_ts` | `datetime` tz-aware | yes | SAB publication timestamp; displayed in canvas header; Back-in-time slider anchor |
| `snapshot_day` | `str` ISO-8601 date | yes | The calendar day this SAB represents; Back-in-time uses `{d, t}` snapshot structure — must be present for versioned BLUF |
| `ccir_topics` | `list[str]` | yes | Which CCIR/PIR/FFIR topics are covered; drives topic-header ordering in HEADLINES (CNR I first, then by CCIR order) |
| `bluf_by_topic` | `dict[str, str]` | yes | Synthesized BLUF text per topic key, with inline `[N]` citation markers; value is the analyst paragraph rendered in `.bluf` block |
| `item_refs` | `list[dict]` | yes | Each entry: `{item_id, ccir, cnr, n, title, source, url, ts}` — the cited evidence list beneath each BLUF. `n` is the citation index matching `[N]` in the BLUF text. |
| `total_keep` | `int` | yes | Item count badge shown in topic header ("N new") |
| `since_ts` | `datetime` tz-aware \| `None` | yes | Cutoff used to compute this SAB; `None` = full-corpus SAB. Canvas uses this for the delta display label. |

**Time-versioned BLUF constraint**: `snapshot_day` and `pub_ts` must be
present and tz-aware so the Back-in-time slider can pick the latest SAB
snapshot ≤ selected day: `blufAsOf(topic, day)` picks the `sab.published`
event with the largest `snapshot_day ≤ day`. Before a topic's first SAB,
the canvas shows "ingen vurdering ennå."

#### `feed.unhealthy`

Published by Phase 7 `opml-health` worker. A feed-health indicator on the
SP-COP canvas shows which sources have gone silent:

| Field | Type | Required | UI Dependency |
|-------|------|----------|---------------|
| `event` | `"feed.unhealthy"` literal | yes | Routing discriminator |
| `feed_url` | `str` | yes | Identifier for the feed; used to match against the displayed source list |
| `feed_name` | `str` | yes | Human-readable source name (e.g. "NRK Nyheter") — displayed in health indicator tooltip |
| `reason` | `str` | yes | Human-readable error description (not an error code); shown verbatim in UI tooltip. Must be ≤ 120 chars. |
| `last_ok_at` | `datetime` tz-aware \| `None` | yes | Last time the feed was healthy; `None` = never seen healthy. Displayed as "last seen: {relative time}". |
| `ts` | `datetime` tz-aware | yes | Timestamp of the health check; used to order/deduplicate health events |

### 3. Codec Fidelity Requirements

The frontmatter⇆JSONB codec (SPEC R3) bridges Obsidian Markdown and
Postgres. The SP-COP canvas renders data that may have passed through this
codec (vault-writer → Obsidian → re-ingest path). The codec must preserve:

| Data type | Requirement | UI Dependency |
|-----------|-------------|---------------|
| Norwegian unicode (`ø`, `æ`, `å`, `Ø`, `Æ`, `Å`) | Round-trip byte-for-byte unchanged | BLUF text, source names, and `why` fields contain Norwegian prose |
| `datetime` (tz-aware, ISO-8601) | No precision loss; timezone preserved (Europe/Oslo or UTC+offset) | `ts`, `pub_ts`, `last_ok_at` used for delta calculations and display |
| `None` | Serializes as YAML `null`; deserializes as Python `None` | `ccir: None`, `url: ""`, `last_ok_at: None` all valid |
| Nested `dict` | Round-trips to identical Python dict (key order may differ) | `bluf_by_topic`, `item_refs` entries must survive codec |
| `list` | Round-trips with element order preserved | `ccir_topics`, `item_refs`, `attachments` order must be stable |
| Inline `[N]` citation markers in BLUF text | Preserved verbatim as string content | Citation superscript matching depends on `[N]` literals surviving codec |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS — data-layer string constraints declared in §3; Phase 1 UI copy N/A
- [ ] Dimension 2 Visuals: PASS — no visual surface in this phase; sketch-findings tokens recorded for Phase 6
- [ ] Dimension 3 Color: PASS — locked palette transcribed from `sources/themes/default.css`; no new color decisions needed
- [ ] Dimension 4 Typography: PASS — locked type scale transcribed from sketch-findings; no new type decisions needed
- [ ] Dimension 5 Spacing: PASS — no layout surface; 8-point default declared for Phase 6
- [ ] Dimension 6 Registry Safety: PASS — no frontend registry; not applicable

**Approval:** pending

---

*Phase: 01-contracts-monorepo-skeleton*
*UI-SPEC created: 2026-06-27*
*Scope: no UI surface — contract obligations the schema owes the downstream SP-COP canvas*
*Design tokens source: `.claude/skills/sketch-findings-infotriage/sources/themes/default.css` + `references/sp-cop-canvas.md` (treat as locked)*
