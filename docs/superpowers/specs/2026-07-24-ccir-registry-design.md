# CCIR Registry — single source of truth for Commander's Critical Information Requirements

**Status:** Design (approved direction: Python registry, runtime-derived, generated doc+feeds)
**Date:** 2026-07-24
**Author:** InfoTriage / forensic-audit follow-up

## Problem

A CCIR (PIR / FFIR / SIR) is currently defined and referenced across **8 sites** that drift
independently. Adding, editing, or retiring one requirement means hand-editing all of them:

| Site | What it holds today |
|------|---------------------|
| `ccir.md` (prose) | human description + carve-out rules |
| `ccir.md` (PMESII/TESSOC tables) | which CCIR maps to each operational domain / threat actor |
| `apps/triage/triage_score.py` (prompt) | the CCIR bullet list + JSON-schema enum |
| `apps/triage/triage_score.py` (examples/SAMPLE) | few-shot worked examples + sample items |
| `apps/triage/digest.py` `CCIR_ORDER` | SAB render order (list of `(id, title)`) |
| `apps/triage/sab_html.py` `CCIR_ORDER` | **duplicate** of the above (known drift, "DRIFT-1") |
| `apps/brief/views.py` `_COP_CCIR` | COP-vs-CIP membership set |
| `apps/opml/feeds.opml` | the feed group that collects for that CCIR |

Plus tests that assert counts (`test_opml_check.py`, `test_opml_roundtrip.py`) and a baseline
(`tests/baselines/triage_sample_baseline.txt`).

A partial guard already exists — `digest.py` raises if `CCIR_ORDER` and the `- **CODE**` bullet
count in `ccir.md` diverge — which proves the drift risk is real but only covers 2 of the 8 sites.

This recurs constantly: **SIR** requirements are explicitly time-bounded ("oppheves ved endt
hendelse"). WC2026 (SIR-2) just ended; the NATO-Ankara summit (SIR-3) will; new crises open new
SIRs. Each add/retire is an 8-site edit today.

## Goal

Editing the full lifecycle of a CCIR — add / edit / **retire** — becomes a **one-place edit** in a
single registry. Retiring WC2026 becomes flipping one `active` flag. Every other artifact (scorer
prompt, render order, COP filter, feed sources, prose doc) derives from the registry, with drift
made impossible for code and test-guarded for generated files.

**Success check:** retiring SIR-2 = set `active=False` on one dataclass entry; after that, the
scorer never emits SIR-2, the SAB renders no SIR-2 section, `feeds.opml` has no WC2026 group,
`ccir.md` has no SIR-2 block, and the full test suite is green — with no other source edits.

## Non-goals

- Not changing the scoring model, CNR tiers, PMESII/TESSOC frameworks, or the SAB UI.
- Not a general config system — scoped to CCIR definitions only.
- Not touching unrelated OPML groups (Norske aviser, NewsAPI, etc.) — only CCIR-owned feed groups.

## Design

### Home

`libs/contracts/src/contracts/ccir.py`. `libs/contracts` is already imported by both
`apps/triage` and `apps/brief`, so a single module is reachable everywhere without new deps.

### Data model

```python
@dataclass(frozen=True)
class FeedSpec:
    text: str                    # "BBC Sport Football"
    xml_url: str
    html_url: str = ""
    warn: bool = False           # renders the ⚠️ marker in feeds.opml

@dataclass(frozen=True)
class Example:
    title: str
    ccir: str
    cnr: str                     # "I" | "II" | "none"
    pmesii: str
    tessoc: str
    score: int
    why: str                     # Norwegian, <=12 words

@dataclass(frozen=True)
class CCIRSpec:
    id: str                      # "PIR-1"
    title: str                   # "Russland / Ukraina"  (SAB section title)
    scorer_line: str             # prompt bullet body (no id/title prefix)
    cop: bool                    # COP (True) vs CIP (False)
    pmesii: tuple[str, ...]      # associated operational domains
    tessoc: tuple[str, ...]      # associated threat actors
    description: str = ""        # long prose for ccir.md
    feeds: tuple[FeedSpec, ...] = ()
    examples: tuple[Example, ...] = ()
    disambiguation: tuple[str, ...] = ()   # "X vs Y → …" guide lines
    active: bool = True          # False = retired (kept for history / re-activation)

CCIR: list[CCIRSpec] = [ ... 12 current requirements ... ]
```

`id` prefix (`PIR` / `FFIR` / `SIR`) is derivable for grouping; no separate `kind` field.

### Runtime derivations (no build step, cannot drift)

Exposed from `contracts.ccir`:

- `active_specs() -> list[CCIRSpec]` — `[c for c in CCIR if c.active]`, canonical order.
- `CCIR_ORDER = [(c.id, c.title) for c in active_specs()]` — imported by **both** `digest.py`
  and `sab_html.py`; the duplicate literal is deleted from both.
- `COP_CCIR = frozenset(c.id for c in active_specs() if c.cop)` — replaces the hardcoded set in
  `apps/brief/views.py`.
- `build_scorer_block() -> str` — renders the prompt's CCIR bullet list, the JSON-schema enum
  (`"<PIR-1 | … | none>"`), the worked examples, and the disambiguation guide from `active_specs()`.
  `triage_score.py` interpolates this string instead of hardcoding those sections.

### Generated files (`make ccir-sync` + drift test)

- `render_ccir_md() -> str` and `render_feeds_opml_ccir_groups() -> str` produce `ccir.md` (prose
  + PMESII/TESSOC tables) and the CCIR-owned `<outline>` groups of `feeds.opml` from the registry.
- `make ccir-sync` writes both files.
- `tests/test_ccir_registry_sync.py` asserts the on-disk files equal the rendered output — fails
  if anyone hand-edits `ccir.md` or a CCIR feed group. This **replaces** the partial `digest.py`
  guard (which is removed).
- Non-CCIR OPML groups are preserved verbatim: the renderer only rewrites the regions between
  explicit `<!-- ccir:begin --> / <!-- ccir:end -->` markers (or equivalent), leaving Norske
  aviser / NewsAPI / etc. untouched.

### Retirement (the recurring case)

Set `active=False`. The spec stays in the registry (definition, examples, feeds preserved) but is
excluded from every derivation and generated file. Re-activation = flip back to `True` and
`make ccir-sync`. This matches SIR lifecycle semantics and supports recurring events.

## Migration plan (outline — detailed steps go to the implementation plan)

1. Author `contracts/ccir.py` with `CCIRSpec`/`FeedSpec`/`Example` and port the 12 current CCIRs
   verbatim from the 8 sites (scorer lines, titles, COP membership, PMESII/TESSOC, examples, feeds).
2. Add the derivations (`CCIR_ORDER`, `COP_CCIR`, `build_scorer_block`) and rewire
   `digest.py`, `sab_html.py`, `views.py`, `triage_score.py` to import them; delete the duplicated
   literals and the partial `digest.py` guard.
3. Add `render_ccir_md` / `render_feeds_opml_ccir_groups`, the `make ccir-sync` target, and
   `test_ccir_registry_sync.py`. Run `ccir-sync`; confirm zero diff against the current files
   (proves the port is faithful).
4. Update `test_opml_check.py` / `test_opml_roundtrip.py` to derive expected counts from the
   registry; regenerate `triage_sample_baseline.txt`.
5. **First real use:** set SIR-2 `active=False`; run `make ccir-sync`; full suite green with SIR-2
   gone everywhere. This is the WC2026 removal, done the new way.

## Testing

- `test_ccir_registry_sync.py` — generated files match the registry.
- Registry-derived assertions replace count literals in the OPML tests.
- Existing scorer/renderer tests must stay green after the rewire (behavior-preserving port).
- A retirement test: with a spec `active=False`, it appears in none of the derivations.

## Risks

- **Faithful port:** step 3's zero-diff check is the guard — if `make ccir-sync` produces a diff
  against the current hand-written files, the registry data is wrong; fix data until diff is empty.
- **feeds.opml marker regions:** must preserve non-CCIR groups exactly; the marker-bounded rewrite
  and the sync test cover this.
- **Scorer prompt wording:** `build_scorer_block()` must reproduce the current prompt text closely
  enough that scoring behavior is unchanged; validated by the existing triage tests + baseline.
