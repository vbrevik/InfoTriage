---
phase: 01-contracts-monorepo-skeleton
verified: 2026-06-27T21:30:00Z
status: passed
score: 5/5
behavior_unverified: 0
overrides_applied: 0
re_verification: false
---

# Phase 01: Contracts + Monorepo Skeleton — Verification Report

**Phase Goal:** One shared contract package all apps depend on; no app imports another. No behavior change to the running pipeline.
**Verified:** 2026-06-27T21:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `libs/contracts` defines canonical Item schema (core + summary + body_ref + payload JSON + attachments[]) | VERIFIED | `_item.py` has all required fields; live import + construction confirmed |
| 2 | Event schemas exist for item.ingested, verdict.ready, sab.published, feed.unhealthy | VERIFIED | `_events.py` with Literal `event` routing-key fields; all 4 models validated live |
| 3 | frontmatter JSONB codec and transport-swappable bus-client interface exist | VERIFIED | `_codec.py` (to_frontmatter/from_frontmatter), `_bus.py` (BusClient Protocol + InMemoryBus); round-trip tested live |
| 4 | Repo restructured into apps/ + libs/; existing scripts import from contracts; tests pass | VERIFIED | apps/{ingest,triage,opml} present; bridge/score/opml absent; digest.py imports Item; 87 tests pass |
| 5 | Three stale doc claims fixed (imap/yt not "scaffolded"; PMESII/TESSOC done; .env.example exists) | VERIFIED | REQUIREMENTS.md C-9/C-13 say "implemented"; A-5 is [LIVE]; .env.example in PROJECT.md + README |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `libs/contracts/pyproject.toml` | VERIFIED | `build-backend = "setuptools.build_meta"`, pydantic>=2.0, PyYAML>=6.0 |
| `libs/contracts/src/contracts/__init__.py` | VERIFIED | Exports all 9 public symbols with `__all__` |
| `libs/contracts/src/contracts/_item.py` | VERIFIED | Item with computed_field sha256 id, AwareDatetime, open payload, attachments |
| `libs/contracts/src/contracts/_events.py` | VERIFIED | All 4 event models; FeedUnhealthy.reason max_length=120; VerdictReady Literal cnr/bucket |
| `libs/contracts/src/contracts/_codec.py` | VERIFIED | yaml.safe_dump/safe_load only; line-wise delimiter split (WR-02 fix) |
| `libs/contracts/src/contracts/_bus.py` | VERIFIED | BusClient @runtime_checkable Protocol; InMemoryBus dedup on (routing_key, item_id) (WR-01 fix) |
| `tests/test_contracts.py` | VERIFIED | 29 pytest functions (27 initial + 2 CR regression for WR-01, WR-02) |
| `requirements-dev.txt` | VERIFIED | `-e ./libs/contracts` + `pytest>=8.0` |
| `pyproject.toml` | VERIFIED | `[tool.pytest.ini_options]` testpaths=["tests"] pythonpath=["apps/triage","apps/opml","apps/ingest"] |
| `apps/ingest/gmail_to_atom.py` | VERIFIED | OUT and .env load each carry `"..", ".."` (2-level depth fix) |
| `apps/ingest/imap_to_atom.py` | VERIFIED | ROOT uses triple dirname (CR-01 fix); verified resolves to repo root |
| `apps/ingest/yt_to_atom.py` | VERIFIED | ROOT uses triple dirname (CR-01 fix); verified resolves to repo root |
| `apps/ingest/_util.py` | VERIFIED | Identity move |
| `apps/ingest/RSS_BRIDGE_NOTES.md` | VERIFIED | Moved from bridge/ (not opml/ as RESEARCH claimed) |
| `apps/triage/triage_score.py` | VERIFIED | CCIR_PATH and .env load each carry `"..", ".."` |
| `apps/triage/digest.py` | VERIFIED | ROOT `"..", ".."` fix; `from contracts import Item` (D-08); `__contract__ = Item` |
| `apps/triage/fever_triage.py` | VERIFIED | ENV carries `"..", ".."` before .env |
| `apps/triage/sab_html.py` | VERIFIED | ROOT `"..", ".."` fix; co-located with triage_score.py for sibling import |
| `apps/opml/_check.py` | VERIFIED | Identity move |
| `apps/opml/feeds.opml` | VERIFIED | Present at apps/opml/ |
| `apps/opml/working.opml` | VERIFIED | Present at apps/opml/ (git-tracked, moved per Q2 resolution) |
| `tests/test_bridge_escape.py` | VERIFIED | Pytest function style, no sys.path.insert |
| `tests/test_ccir_sync.py` | VERIFIED | ccir.md path unchanged (`"..", "ccir.md"` from tests/) |
| `tests/test_opml_check.py` | VERIFIED | OPML path references `apps/opml/feeds.opml` |
| `tests/test_opml_roundtrip.py` | VERIFIED | OPML path references `apps/opml/feeds.opml` |
| `tests/test_score_parse.py` | VERIFIED | Pytest function style, no sys.path.insert |
| `tests/test_write_bluf.py` | VERIFIED | monkeypatch fixture; credential-leak guard preserved |
| `tests/test_ingest_paths.py` | VERIFIED | 2 CR-01 regression tests for imap/yt ROOT depth |
| `.planning/REQUIREMENTS.md` | VERIFIED | C-9/C-13 "implemented" + apps/ingest/ paths; A-5 [LIVE] |
| `README.md` | VERIFIED | No `python3 score/` or `python3 bridge/` commands; apps/ paths throughout |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| any app | `contracts.Item` et al | editable install `-e ./libs/contracts` | VERIFIED | `from contracts import Item` resolves; 29 tests exercise it |
| `apps/triage/digest.py` | `contracts.Item` | `from contracts import Item` at top of import block | VERIFIED | line 20; `__contract__ = Item` marker at line 34 |
| `apps/triage/triage_score.py` | repo-root `ccir.md` + `.env` | `os.path.join(__file__, "..", "..", ...)` | VERIFIED | CCIR_PATH line 19; .env load line 180 |
| `apps/triage/digest.py` | repo-root `data/` + `.env` + `ccir.md` | ROOT = `join(__file__, "..", "..")` | VERIFIED | ROOT line 26; cascades to OUT, STORE, load_dotenv |
| `apps/triage/fever_triage.py` | repo-root `.env` | ENV = `join(__file__, "..", "..", ".env")` | VERIFIED | line 20 |
| `apps/triage/sab_html.py` | repo-root `data/` + `.env` | ROOT = `join(__file__, "..", "..")` | VERIFIED | line 23; cascades to STORE, OUT, load_dotenv |
| `apps/ingest/gmail_to_atom.py` | repo-root `data/feeds/` + `.env` | OUT line 18, .env load line 57 | VERIFIED | both carry `"..", ".."` |
| `apps/ingest/imap_to_atom.py` | repo-root `data/` + `.env` | ROOT = triple dirname (CR-01 fix) | VERIFIED | resolves to `/Users/vidarbrevik/projects/InfoTriage` |
| `apps/ingest/yt_to_atom.py` | repo-root `data/` + `.env` | ROOT = triple dirname (CR-01 fix) | VERIFIED | resolves to `/Users/vidarbrevik/projects/InfoTriage` |
| `tests/test_opml_*.py` | `apps/opml/feeds.opml` | `os.path.join(__file__, "..", "apps", "opml", "feeds.opml")` | VERIFIED | both test files carry the corrected path |
| `tests/test_ccir_sync.py` | repo-root `ccir.md` | `os.path.join(__file__, "..", "ccir.md")` | VERIFIED | unchanged — ccir.md did not move |
| `pyproject.toml` | `apps/{triage,opml,ingest}` | `pythonpath = [...]` | VERIFIED | replaces all removed sys.path.insert calls |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Item id determinism (same inputs → same sha256) | `python3 -c "from contracts import Item; ..."` | `a.id == b.id` | PASS |
| Empty url produces expected hash | `python3 -c "..."` | matches `sha256('rss\x00\x00T')` | PASS |
| Naive datetime rejected | `from pydantic import ValidationError; try: Item(..., ts=naive_dt)` | ValidationError raised | PASS |
| VerdictReady rejects invalid cnr / bucket literals | live test | ValidationError on "bogus" | PASS |
| FeedUnhealthy rejects 121-char reason | live test | ValidationError; 120-char accepted | PASS |
| Codec round-trips (nested/unicode/datetime/[N] markers) | `to_frontmatter` → `from_frontmatter` | deep equality on all fields | PASS |
| Codec handles `---` in values (WR-02) | `from_frontmatter(to_frontmatter({"sep":"---"}))` | `sep == "---"` | PASS |
| InMemoryBus dedup per routing_key (WR-01) | same item_id on two keys | both delivered | PASS |
| InMemoryBus FIFO | publish 1,2,3 with dedup on middle | [1,3] in order | PASS |
| Bus subscribe on empty key returns [] | `bus.subscribe("unused")` | `[]` | PASS |
| imap_to_atom.ROOT resolves to repo root (CR-01) | `os.path.abspath(imap_to_atom.ROOT) == repo_root` | True | PASS |
| yt_to_atom.ROOT resolves to repo root (CR-01) | `os.path.abspath(yt_to_atom.ROOT) == repo_root` | True | PASS |
| Full test suite green | `pytest tests/ -q` | 87 passed, 0 failed | PASS |
| BusClient Protocol isinstance | `isinstance(InMemoryBus(), BusClient)` | True | PASS |

---

### Anti-Patterns Found

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `apps/triage/sab_html.py` | XSS via `url` in `href` attribute (WR-03) | INFO | Pre-existing; byte-identical git mv; explicitly out of scope per phase contract |
| `apps/opml/_check.py` | Exit gate always non-zero (WR-04) | INFO | Pre-existing; byte-identical git mv; explicitly out of scope |
| `apps/ingest/yt_to_atom.py` | `vid` interpolated without escape in XML (WR-05) | INFO | Pre-existing; byte-identical git mv; explicitly out of scope |
| `apps/triage/digest.py` | File I/O + potential AssertionError at import time (WR-06) | INFO | Pre-existing; explicitly out of scope |

No TBD/FIXME/XXX markers in any phase-introduced file. No secrets or hardcoded host:port endpoints in `libs/contracts/src`. No unittest class wrappers or `sys.path.insert` calls in the test suite.

---

### Requirements Coverage

| Plan Requirement | Description | Status | Evidence |
|-----------------|-------------|--------|----------|
| R1 (01-01) | Item schema: id determinism, open payload, validation | SATISFIED | `_item.py` + 7 tests in test_contracts.py |
| R2 (01-01) | 4 event schemas with Literal routing keys + field constraints | SATISFIED | `_events.py` + 8 tests (validate + reject per event) |
| R3 (01-01) | PyYAML frontmatter codec; safe_load only; round-trip fidelity | SATISFIED | `_codec.py` + 3 codec tests + WR-02 regression test |
| R4 (01-01) | BusClient Protocol + InMemoryBus dedup/FIFO | SATISFIED | `_bus.py` + 5 bus tests + WR-01 regression test |
| R5 (01-02) | Monorepo restructure; path-depth fixes; pytest config; coverage preserved | SATISFIED | Directory structure verified; 7+2 path fixes confirmed; 87 tests |
| R6 (01-03) | Three stale doc claims corrected in REQUIREMENTS.md + README | SATISFIED | C-9/C-13 "implemented"; A-5 [LIVE]; README apps/ paths |
| ADR-006 | Architecture: shared contract package; no app imports another | SATISFIED | Import-boundary grep returns NONE in all directions |

---

### Human Verification Required

None. All observable truths are verifiable programmatically and have been verified against the live codebase.

---

## Gaps Summary

No gaps. All 5 ROADMAP success criteria verified against the actual codebase. The phase goal is fully achieved:
- `libs/contracts` is pip-installable and exports all 9 public symbols
- All 4 event schemas and both codec functions are implemented and proven by 29 tests
- apps/ restructure is complete with all path-depth fixes applied (7 original + 2 CR-01)
- Test suite expanded from 56 (baseline) to 87 (56 migrated + 27 new contracts + 4 CR regression)
- Documentation stale claims corrected in REQUIREMENTS.md and README.md
- No app imports another; no cross-subdir dependencies

Pre-existing bugs in moved files (WR-03 through WR-06) are documented in 01-REVIEW.md and are explicitly out of scope for this behavior-preserving phase.

---

_Verified: 2026-06-27T21:30:00Z_
_Verifier: Claude (gsd-verifier)_
