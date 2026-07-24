# CCIR Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the 8 scattered CCIR definition sites into one Python registry (`libs/contracts/src/contracts/ccir.py`) that every other artifact derives from, so adding/editing/retiring a requirement is a one-place edit.

**Architecture:** A frozen-dataclass registry (`CCIR: list[CCIRSpec]`) is the single source of truth. Code artifacts (`CCIR_ORDER`, `COP_CCIR`, the scorer prompt block) are derived at import time — no build step, cannot drift. Generated files (`ccir.md`, the CCIR-tagged groups of `feeds.opml`) are rendered by `make ccir-sync` and guarded by a drift test. Retiring a requirement = `active=False`.

**Tech Stack:** Python 3.12, dataclasses, pytest, existing `libs/contracts` package, Make.

## Global Constraints

- Registry module lives at `libs/contracts/src/contracts/ccir.py` and is exported from `contracts/__init__.py`.
- Behavior-preserving port: after each rewire, the existing triage/brief test suite MUST stay green.
- The migration is proven by a **zero-diff check**: `make ccir-sync` against the CURRENT `ccir.md` + `feeds.opml` must produce no diff before any retirement.
- Only CCIR-owned OPML groups (suffixed `(SIR-n)` today) are generated; thematic groups (Norske aviser, Verdensnyheter, Medium, etc.) are preserved verbatim.
- No new third-party dependencies (stdlib + existing deps only).
- `black --check` and `mypy` clean on all changed Python files.

---

### Task 1: CCIR registry data model + ported entries

**Files:**
- Create: `libs/contracts/src/contracts/ccir.py`
- Modify: `libs/contracts/src/contracts/__init__.py` (export `CCIR`, `CCIRSpec`, `active_specs`)
- Test: `tests/test_ccir_registry.py`

**Interfaces:**
- Produces: `CCIRSpec` (frozen dataclass), `FeedSpec`, `Example`, `CCIR: list[CCIRSpec]`, `active_specs() -> list[CCIRSpec]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ccir_registry.py
from contracts.ccir import CCIR, CCIRSpec, active_specs

def test_registry_has_twelve_active_ccirs():
    ids = [c.id for c in active_specs()]
    assert ids == [
        "PIR-1","PIR-2","PIR-3","PIR-4","PIR-5","PIR-6",
        "SIR-1","SIR-2","SIR-3",
        "FFIR-1","FFIR-2","FFIR-3",
    ]

def test_every_spec_has_required_fields():
    for c in CCIR:
        assert c.id and c.title and c.scorer_line
        assert isinstance(c.cop, bool)
        assert isinstance(c.pmesii, tuple) and isinstance(c.tessoc, tuple)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ccir_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: contracts.ccir`.

- [ ] **Step 3: Write the dataclasses + registry**

Create `ccir.py` with `FeedSpec`, `Example`, `CCIRSpec` (fields per the design spec: `id, title, scorer_line, cop, pmesii, tessoc, description="", feeds=(), examples=(), disambiguation=(), active=True`) and the `CCIR` list. Port all 12 current entries verbatim from:
- titles + order: `apps/triage/digest.py` `CCIR_ORDER`
- `scorer_line`: the bullet bodies in `apps/triage/triage_score.py` prompt (lines ~70–86)
- `cop`: `True` for the ids in `apps/brief/views.py` `_COP_CCIR` (`FFIR-1/2/3, PIR-3, SIR-2, SIR-3`), else `False`
- `pmesii`/`tessoc`: the `PMESII: … · TESSOC: …` trailers in `ccir.md`
- `examples`/`disambiguation`: the worked examples + guide lines in `triage_score.py`
- `feeds`: the `(SIR-n)` OPML groups in `apps/opml/feeds.opml` (only SIR-1, SIR-2 today)
- `description`: the prose block per requirement in `ccir.md`

Add `def active_specs(): return [c for c in CCIR if c.active]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ccir_registry.py -q`
Expected: PASS. Then `black libs/contracts/src/contracts/ccir.py && mypy libs/contracts/src/contracts/ccir.py`.

- [ ] **Step 5: Commit**

```bash
git add libs/contracts/src/contracts/ccir.py libs/contracts/src/contracts/__init__.py tests/test_ccir_registry.py
git commit -m "feat(contracts): add CCIR registry (single source of truth)"
```

---

### Task 2: Derive CCIR_ORDER + COP_CCIR; rewire renderers

**Files:**
- Modify: `libs/contracts/src/contracts/ccir.py` (add `CCIR_ORDER`, `COP_CCIR`)
- Modify: `apps/triage/digest.py` (import `CCIR_ORDER`; delete literal + the `ccir.md` sync guard)
- Modify: `apps/triage/sab_html.py` (import `CCIR_ORDER`; delete duplicate literal)
- Modify: `apps/brief/views.py` (import `COP_CCIR`; delete `_COP_CCIR` literal)
- Test: `tests/test_ccir_registry.py` (extend)

**Interfaces:**
- Consumes: `active_specs()` from Task 1.
- Produces: `CCIR_ORDER: list[tuple[str,str]]`, `COP_CCIR: frozenset[str]`.

- [ ] **Step 1: Write the failing test** — assert the derived values equal the current literals

```python
def test_ccir_order_matches_legacy_literal():
    from contracts.ccir import CCIR_ORDER
    assert CCIR_ORDER == [
        ("PIR-1","Russland / Ukraina"),("PIR-2","Nordområdene & Arktis"),
        ("PIR-3","NATO & europeisk sikkerhet"),("PIR-4","Hybrid- & cybertrusler"),
        ("PIR-5","Stormaktsrivalisering"),("PIR-6","OSINT & etterforskning"),
        ("SIR-1","Midtøsten & US-Iran"),("SIR-2","Sport — VM 2026 (FIFA)"),
        ("SIR-3","NATO-toppmøtet i Ankara"),("FFIR-1","Norsk forsvar & sikkerhetspolitikk"),
        ("FFIR-2","Norsk politikk & samfunn"),("FFIR-3","Egen teknologikapabilitet"),
    ]

def test_cop_ccir_matches_legacy_set():
    from contracts.ccir import COP_CCIR
    assert COP_CCIR == {"FFIR-1","FFIR-2","FFIR-3","PIR-3","SIR-2","SIR-3"}
```

- [ ] **Step 2: Run to verify it fails** — `ImportError` on `CCIR_ORDER`.

- [ ] **Step 3: Add derivations + rewire**

In `ccir.py`:
```python
CCIR_ORDER = [(c.id, c.title) for c in active_specs()]
COP_CCIR = frozenset(c.id for c in active_specs() if c.cop)
```
In `digest.py`: replace the literal `CCIR_ORDER = [...]` with `from contracts.ccir import CCIR_ORDER`, and DELETE the `_ccir_md_ids`/`_order_ids` sync-guard block (Task 4's sync test supersedes it). In `sab_html.py`: same import, delete duplicate. In `views.py`: `from contracts.ccir import COP_CCIR as _COP_CCIR` (keep the local name to minimize churn) and delete the literal set.

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_ccir_registry.py tests/test_brief_renderer.py tests/test_brief_views_links.py tests/test_brief_consumer.py -q`. Expected: PASS. `black`/`mypy` clean on the 3 modified app files.

- [ ] **Step 5: Commit**

```bash
git add libs/contracts/src/contracts/ccir.py apps/triage/digest.py apps/triage/sab_html.py apps/brief/views.py tests/test_ccir_registry.py
git commit -m "refactor(triage,brief): derive CCIR_ORDER + COP_CCIR from registry (kill DRIFT-1)"
```

---

### Task 3: Generate the scorer prompt block from the registry

**Files:**
- Modify: `libs/contracts/src/contracts/ccir.py` (add `build_scorer_block`)
- Modify: `apps/triage/triage_score.py` (interpolate the block; remove hardcoded CCIR list/enum/examples)
- Test: `tests/test_ccir_registry.py` (extend); existing `tests/test_triage_score.py` must stay green

**Interfaces:**
- Consumes: `active_specs()`, `Example`.
- Produces: `build_scorer_block() -> str` (renders CCIR bullets, disambiguation, worked examples) and `active_ccir_enum() -> str` (`"PIR-1 | … | none"`).

- [ ] **Step 1: Write the failing test**

```python
def test_scorer_block_lists_active_ids_and_examples():
    from contracts.ccir import build_scorer_block
    block = build_scorer_block()
    for cid in ["PIR-1","SIR-2","FFIR-3"]:
        assert cid in block
    assert "Bellingcat identifies Russian officer" in block  # a ported worked example

def test_scorer_enum_excludes_inactive(monkeypatch):
    from contracts import ccir
    assert "SIR-2" in ccir.active_ccir_enum()
```

- [ ] **Step 2: Run to verify it fails** — `ImportError: build_scorer_block`.

- [ ] **Step 3: Implement `build_scorer_block` + rewire prompt**

In `ccir.py`, render the block from `active_specs()` (bullets = `f"- {c.id} {c.title} — {c.scorer_line}"`; then the disambiguation lines; then the worked examples formatted as the current prompt does). In `triage_score.py`, replace the hardcoded CCIR bullet list, the disambiguation guide, the worked-examples list, and the JSON-schema enum with interpolations of `build_scorer_block()` / `active_ccir_enum()`. Keep the CNR/PMESII/TESSOC framework prose as-is (not CCIR-specific).

- [ ] **Step 4: Run tests** — `python -m pytest tests/test_triage_score.py tests/test_ccir_registry.py -q`. Expected: PASS (scoring behavior unchanged — same prompt text, now generated). `black`/`mypy` clean.

- [ ] **Step 5: Commit**

```bash
git add libs/contracts/src/contracts/ccir.py apps/triage/triage_score.py tests/test_ccir_registry.py
git commit -m "refactor(triage): generate scorer CCIR prompt block from registry"
```

---

### Task 4: Generate ccir.md + feeds.opml groups; sync target + drift test

**Files:**
- Modify: `libs/contracts/src/contracts/ccir.py` (add `render_ccir_md`, `render_feeds_opml_groups`)
- Create: `scripts/ccir_sync.py` (writes both files)
- Modify: `ops/Makefile` (add `ccir-sync` target)
- Modify: `ccir.md` (insert `<!-- ccir:begin -->`/`<!-- ccir:end -->` markers around generated regions)
- Modify: `apps/opml/feeds.opml` (wrap the `(SIR-n)` groups in `<!-- ccir:begin -->`/`<!-- ccir:end -->`)
- Test: `tests/test_ccir_registry_sync.py`

**Interfaces:**
- Consumes: `active_specs()`, `FeedSpec`.
- Produces: `render_ccir_md() -> str`, `render_feeds_opml_groups() -> str`, `scripts/ccir_sync.py` CLI.

- [ ] **Step 1: Write the failing sync test**

```python
# tests/test_ccir_registry_sync.py — the drift guard
from pathlib import Path
from contracts.ccir import render_ccir_md, render_feeds_opml_groups

ROOT = Path(__file__).resolve().parent.parent

def test_ccir_md_in_sync():
    on_disk = (ROOT / "ccir.md").read_text(encoding="utf-8")
    assert render_ccir_md() == on_disk, "ccir.md drifted from registry — run `make ccir-sync`"

def test_feeds_opml_ccir_groups_in_sync():
    on_disk = (ROOT / "apps/opml/feeds.opml").read_text(encoding="utf-8")
    assert render_feeds_opml_groups() in on_disk, "feeds.opml CCIR groups drifted — run `make ccir-sync`"
```

- [ ] **Step 2: Run to verify it fails** — `ImportError: render_ccir_md`.

- [ ] **Step 3: Implement renderers + sync script + markers + Makefile target**

Add marker comments to `ccir.md` (around the per-requirement bullets + PMESII/TESSOC tables) and `feeds.opml` (around the `(SIR-n)` groups). Implement `render_ccir_md()` (reproduces the current marked regions from the registry) and `render_feeds_opml_groups()` (reproduces the marked OPML region). Write `scripts/ccir_sync.py` that rewrites the marked regions in place. Add:
```make
ccir-sync: ## Regenerate ccir.md + feeds.opml CCIR groups from the registry
	cd $(ROOT_DIR) && python scripts/ccir_sync.py
```

- [ ] **Step 4: Zero-diff gate** — run `make -f ops/Makefile ccir-sync`, then `git diff --stat ccir.md apps/opml/feeds.opml`. Expected: **no diff** (registry data is a faithful port). If diff appears, fix the registry data (not the files) until clean. Then `python -m pytest tests/test_ccir_registry_sync.py -q` PASS.

- [ ] **Step 5: Commit**

```bash
git add libs/contracts/src/contracts/ccir.py scripts/ccir_sync.py ops/Makefile ccir.md apps/opml/feeds.opml tests/test_ccir_registry_sync.py
git commit -m "feat(contracts): generate ccir.md + feeds.opml from registry with drift test"
```

---

### Task 5: Migrate count-based tests to registry-derived

**Files:**
- Modify: `tests/test_opml_check.py` (derive expected group count from registry)
- Modify: `tests/test_opml_roundtrip.py` (same)
- Modify: `tests/baselines/triage_sample_baseline.txt` (regenerate if the sample set is registry-driven)

**Interfaces:**
- Consumes: `active_specs()`, `render_feeds_opml_groups()`.

- [ ] **Step 1: Update the OPML tests** — replace the hardcoded `12` top-level-outline assertions with a count derived from the fixed thematic groups plus `len([c for c in active_specs() if c.feeds])`. Document the derivation inline.

- [ ] **Step 2: Run** — `python -m pytest tests/test_opml_check.py tests/test_opml_roundtrip.py -q`. Expected: PASS.

- [ ] **Step 3: Regenerate the triage baseline if needed** — if `triage_score.py` SAMPLE items are moved into the registry `examples`, regenerate `tests/baselines/triage_sample_baseline.txt` from the sample runner and confirm it only changed in expected ways. If SAMPLE stays inline, no change.

- [ ] **Step 4: Full suite** — `python -m pytest tests/ -q` (with `INFOTRIAGE_PG_DSN` set to a dummy DSN for the recall tests). Expected: all green, 0 regressions.

- [ ] **Step 5: Commit**

```bash
git add tests/test_opml_check.py tests/test_opml_roundtrip.py tests/baselines/triage_sample_baseline.txt
git commit -m "test: derive CCIR/OPML expectations from the registry"
```

---

### Task 6: Retire WC2026 (SIR-2) — first use of the new path

**Files:**
- Modify: `libs/contracts/src/contracts/ccir.py` (SIR-2 `active=False`)
- Modify (generated): `ccir.md`, `apps/opml/feeds.opml` (via `make ccir-sync`)
- Modify: `tests/test_opml_check.py` / `test_opml_roundtrip.py` (count drops by 1)

**Interfaces:**
- Consumes: everything from Tasks 1–5.

- [ ] **Step 1: Write the retirement test**

```python
def test_retired_sir2_absent_from_all_derivations():
    from contracts.ccir import CCIR_ORDER, COP_CCIR, build_scorer_block, active_ccir_enum
    assert "SIR-2" not in [cid for cid, _ in CCIR_ORDER]
    assert "SIR-2" not in COP_CCIR
    assert "SIR-2" not in active_ccir_enum()
    assert "VM 2026" not in build_scorer_block()
```

- [ ] **Step 2: Run to verify it fails** — SIR-2 still active.

- [ ] **Step 3: Flip the flag + regenerate** — set `active=False` on the SIR-2 `CCIRSpec`. Run `make -f ops/Makefile ccir-sync`. Update the OPML count assertions (12→11 groups). The SIR-2 entry stays in the registry (retired, re-activatable).

- [ ] **Step 4: Full verification** — `python -m pytest tests/ -q` (dummy `INFOTRIAGE_PG_DSN`). Expected: all green. Confirm `grep -rn "SIR-2\|VM 2026" ccir.md apps/opml/feeds.opml apps/triage apps/brief` returns nothing in active code/config (only the retired registry entry remains).

- [ ] **Step 5: Commit**

```bash
git add libs/contracts/src/contracts/ccir.py ccir.md apps/opml/feeds.opml tests/test_opml_check.py tests/test_opml_roundtrip.py
git commit -m "feat(ccir): retire SIR-2 (WC2026) — final played; active=False via registry"
```

## Self-Review

- **Spec coverage:** data model (T1), runtime derivations + rewire of all 4 code sites (T2, T3), generated files + drift test (T4), test migration (T5), retirement via `active=False` (T6). All spec sections covered.
- **Placeholder scan:** the 12-entry port (T1 step 3) and the marker-region renderers (T4 step 3) reference concrete source locations; the zero-diff gate (T4 step 4) is the objective completion check rather than reproducing ~300 lines of ported data in the plan.
- **Type consistency:** `CCIRSpec`, `active_specs()`, `CCIR_ORDER`, `COP_CCIR`, `build_scorer_block()`, `active_ccir_enum()`, `render_ccir_md()`, `render_feeds_opml_groups()` are named identically across all tasks.
