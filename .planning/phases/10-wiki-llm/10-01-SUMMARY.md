---
phase: 10-wiki-llm
plan: 01
status: complete
goal: Standing per-entity wiki pages + on-demand synthesis with DGX backend and cross-language verification
verified: 2026-07-22
verified_by: "pytest tests/test_wiki_generator.py tests/test_cross_language_synthesis.py → 38 passed, 0 failed; mypy clean"
---

# 10-01-SUMMARY.md — Wiki-LLM (complete)

Phase 10 delivered an auto-maintained intelligence wiki synthesized from the corpus and on-demand synthesized articles, fulfilling the M2 Fusion vision.

1. **Auto-maintained Wiki**: A service that writes and updates standing Obsidian `.md` pages for key entities and topics, providing an updated synthesized overview with citations.
2. **On-Demand Synthesis & DGX**: Enhanced thematic recall (`recall.py`) with a pluggable `--backend {local,dgx}` argument and heavy synthesis support via DGX Spark.
3. **Cross-Language Verification** (folded from Phase 999.4 backlog): `verify_language_coverage()` enforces that all languages present in the corpus context are cited, flagging silent omissions.

## What shipped

### Wave 1: Data Foundation & Store Protocol

- `libs/store/src/store/_protocol.py` gained `get_active_entities(since=None, limit=100) -> list[dict]`.
- Postgres implementation: queries `entity_links` joined to `articles` and `enrichment`, returning `entity_id`, `name`, `name_norm`, `type`, `lang`, `first_seen`, `last_seen`, `link_count`, and `ccir`.
- InMemory implementation: aggregates the in-memory entity and link tables.
- `apps/wiki/generator.py` scaffolded with `WikiGenerator` class — prompt templates request encyclopedic summary, explicit `[item_id]` citations, cross-language synthesis, and contradiction flagging.
- `tests/test_wiki_generator.py` — prompt instruction presence and markdown structure tests.

### Wave 2: Auto-Wiki File Writer & Worker

- `write_wiki_page()` in `generator.py` writes to `Vault/wiki/auto/<slug>.md`. Existing files merge frontmatter via `from_frontmatter`/`to_frontmatter`, preserving operator-added keys.
- `apps/wiki/wiki_worker.py` — `--mode {once,periodic,events}`; periodic passes a `since` window to `get_active_entities`; consumes `verdict.ready` events; `/health` endpoint; structured logging.

### Wave 3: DGX Backend Integration

- `apps/wiki/dgx_client.py` — `DGXSynthesisBackend` implements the `RecallBackend` protocol; routes to DGX Spark endpoint with larger `max_tokens` and thinking-token stripping.
- `apps/triage/recall.py` — `--backend {local,dgx}` argument (default `local`); `_select_backend()` dispatches correctly.
- Mock test proves correct endpoint and payload.

### Wave 4: Cross-Language Verification (Phase 999.4)

- `libs/contracts/src/contracts/_verify.py` — `verify_language_coverage(items, text)` extracts languages from items, parses `[item_id]` citations via regex, maps citations to language, returns missing languages.
- Verification flag appended to synthesis output: `> ⚠️ **Verification Flag**: <lang> language sources were present but not cited.`
- Applied to both `generator.py` standing pages and `recall.py` on-demand synthesis.
- `tests/test_cross_language_synthesis.py` — consolidated tests: mock LLM omitting Russian sources triggers flag; citing all languages passes.

### Intra-Page Contradiction Prompting

- Both `generator.py` and `recall.py` include: `"If sources disagree, highlight the contradiction explicitly."`
- Test asserts the instruction is present in all synthesis prompts.

## Deviations from 10-PLAN.md

| Plan | Actual | Rationale |
|------|--------|-----------|
| Wave 4 was "queued" in planning docs (`67dceab`). | Executed and completed in the same session as Waves 2-3. | Scope was small; sequential execution was efficient. |
| `test_cross_language_synthesis.py` was the original plan filename. | Consolidated into a single test file. | Avoids duplication with wiki generator tests. |

## Decisions recorded

- **Synthesis backend default**: `local` (oMLX/qwen36). DGX is opt-in (`--backend dgx`). Keeps the common case fast and cheap.
- **Wiki page isolation**: `write_wiki_page` merges frontmatter via the contracts codec, preserving operator-added keys. Body is replaced; frontmatter operator keys are retained.
- **Cross-language verification**: Only items with non-empty `lang` (excluding `"unknown"`) are checked. False positives avoided.
- **Contradiction handling**: Prompt-only in Phase 10. A dedicated LLM call for contradiction detection is a Phase 11+ improvement.

## Tests / verification

- `pytest tests/test_wiki_generator.py tests/test_cross_language_synthesis.py -q` — 38 passed, 0 failed
- `mypy` clean on all modified Phase 10 files
- Black formatting clean across project

## Files touched

### New
- `apps/wiki/generator.py` — WikiGenerator with prompt construction and Obsidian file writer
- `apps/wiki/wiki_worker.py` — scheduled + event-driven wiki update worker
- `apps/wiki/dgx_client.py` — DGX SynthesisBackend
- `libs/contracts/src/contracts/_verify.py` — verify_language_coverage()

### Modified
- `libs/store/src/store/_protocol.py` — added `get_active_entities()`
- `libs/store/src/store/_postgres.py` — `get_active_entities()` implementation
- `libs/store/src/store/_inmemory.py` — `get_active_entities()` implementation
- `apps/triage/recall.py` — `--backend {local,dgx}`, `--include-body`, cross-language verification
- `tests/test_wiki_generator.py` — WikiGenerator unit tests
- `tests/test_cross_language_synthesis.py` — cross-language verification tests

## Acceptance criteria

From ROADMAP.md §Phase 10:

- [x] A standing, auto-updated wiki exists as cross-linked Obsidian `.md` files.
- [x] On-demand synthesis functions via `recall.py` with DGX support.
- [x] Cross-language synthesis verification is complete and tested, preventing silent omission of non-English sources.
