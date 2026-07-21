---
phase: 10-wiki-llm
plan: 01
type: execute
wave: 1
depends_on:
  - 09-rag-recall
files_modified:
  - libs/store/src/store/_protocol.py
  - libs/store/src/store/_postgres.py
  - libs/store/src/store/_inmemory.py
  - apps/wiki/wiki_worker.py
  - apps/wiki/generator.py
  - apps/wiki/dgx_client.py
  - apps/triage/recall.py
  - tests/test_wiki_generator.py
  - tests/test_cross_language_synthesis.py
autonomous: true
requirements: [ADR-006, spec §Obsidian]

must_haves:
  truths:
    - "Standing per-entity and per-topic wiki pages are continuously updated in the Obsidian vault"
    - "Wiki pages include cross-linked Obsidian .md formatting and cite source items by item_id"
    - "On-demand synthesis answers ad-hoc queries from the corpus"
    - "DGX is integrated for heavy synthesis tasks"
    - "Cross-language synthesis verification enforces that all languages present in the corpus context are cited (Phase 999.4 backlog folded into this phase)"
    - "Intra-page contradictions are avoided or explicitly flagged in the generated text"
  artifacts:
    - libs/store/src/store/_protocol.py + backends (new `get_active_entities` query)
    - apps/wiki/generator.py (prompting + Obsidian file create/update)
    - apps/wiki/wiki_worker.py (event-driven or scheduled wiki update worker)
    - apps/wiki/dgx_client.py (DGX `RecallBackend` implementation)
    - apps/triage/recall.py (`--backend dgx` + verification hooks)
    - tests/test_wiki_generator.py
    - tests/test_cross_language_synthesis.py
  key_links:
    - "Follows Obsidian formatting constraints (frontmatter codec, wikilinks) developed in Phase 6"
    - "Integrates with entity resolution from Phase 8 for entity pages"
    - "Reuses Phase 9 `RecallBackend` protocol for on-demand recall/synthesis"
  prohibitions:
    - statement: "MUST NOT omit source items from non-English/Norwegian languages in synthesis"
      status: resolved
      verification: "Cross-language coverage check enforces at least one citation per present language"

---

<objective>
Phase 10 delivers an auto-maintained intelligence wiki synthesized from the corpus and on-demand synthesized articles, fulfilling the M2 Fusion vision.

1. **Auto-maintained Wiki**: A service that writes and updates standing Obsidian `.md` pages for key entities and topics, providing an updated synthesized overview with citations.
2. **On-Demand Synthesis & DGX**: Enhances the Phase 9 thematic recall with heavy synthesis powered by DGX, and addresses the Phase 999.4 backlog item by strictly verifying cross-language context coverage so no language sources (e.g., Russian) are silently dropped.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/phases/09-rag-recall/09-PLAN.md
@docs/adr/ADR-006-microservice-architecture-entity-resolution.md
@docs/superpowers/specs/2026-06-24-app-split-architecture-design.md
</context>

<downstream_consumer>
Plans consume:
- Frontmatter (wave, depends_on, files_modified, autonomous)
- Tasks in XML format with read_first and acceptance_criteria
- Verification criteria
</downstream_consumer>

## Artifacts this plan produces

| Artifact | Purpose |
|----------|---------|
| `libs/store/src/store/_protocol.py` (+ backends) | `get_active_entities(since)` read path for wiki targets |
| `apps/wiki/generator.py` | Prompt construction + Obsidian file create/update |
| `apps/wiki/wiki_worker.py` | Periodic/event-driven trigger for generator |
| `apps/wiki/dgx_client.py` | DGX-backed `RecallBackend` implementation |
| `apps/triage/recall.py` | `--backend dgx` + cross-language verification |
| `tests/test_wiki_generator.py` | Unit tests for auto-wiki page generation |
| `tests/test_cross_language_synthesis.py` | Tests Phase 999.4 language omission rules |

<tasks>

## Wave 1: Data Foundation & Store Protocol

### Task 1: Add `get_active_entities()` to the Store Protocol

**Files:** `libs/store/src/store/_protocol.py`, `libs/store/src/store/_postgres.py`, `libs/store/src/store/_inmemory.py`

**Read first:**
- `libs/store/src/store/_protocol.py` (existing read patterns like `get_all_entities`, `recall_items`)
- `libs/store/src/store/_postgres.py` (aggregation SQL patterns)

**Action:**
1. Add `get_active_entities(self, since: datetime.datetime | None = None, limit: int = 100) -> list[dict]` to the `Store` Protocol.
2. Postgres implementation: query `infotriage.entity_links` joined to `infotriage.articles` and `infotriage.enrichment`, returning `entity_id`, `name`, `name_norm`, `type`, `lang`, `first_seen`, `last_seen`, `link_count`, and `ccir` for entities that have appeared since `since`.
3. InMemory implementation: aggregate the in-memory entity and link tables.
4. Add db_live + inmemory tests in `tests/test_store_entities.py`.

**Acceptance Criteria:**
- Protocol + both backends return a stable, ordered list of active entities.
- Empty store returns `[]`.

### Task 2: Scaffold `apps/wiki/generator.py` prompt templates

**Files:** `apps/wiki/generator.py`, `tests/test_wiki_generator.py`

**Read first:**
- `apps/triage/recall.py` (synthesis prompt patterns and `RecallBackend` abstraction)
- `apps/brief/vault_writer.py` (Obsidian note + frontmatter codec usage)
- `libs/contracts/src/contracts/__init__.py` (`to_frontmatter`, `from_frontmatter`)

**Action:**
1. Create `generator.py` with a `WikiGenerator` class.
2. Define prompt templates that request an encyclopedic summary, explicit `[item_id]` citations, cross-language synthesis, and contradiction flagging.
3. Add unit tests that assert the prompt contains required instructions and that output markdown is structurally valid.

**Acceptance Criteria:**
- `WikiGenerator.build_prompt(subject, context_items)` returns a string with the required instructions.
- Tests verify the prompt mentions cross-language and contradiction checks.

## Wave 2: Auto-Wiki File Writer & Worker

### Task 3: Implement create/update Obsidian file writer

**Files:** `apps/wiki/generator.py`

**Read first:**
- `apps/brief/vault_writer.py` (Obsidian frontmatter codec)
- `libs/contracts/src/contracts/__init__.py` (frontmatter helpers)

**Action:**
1. Implement `write_wiki_page(subject, content, metadata, vault_path)` that writes to `Vault/wiki/auto/<slug>.md`.
2. If the file already exists, read it with `from_frontmatter`, merge metadata (preserving operator edits), and rewrite only the auto-generated body.
3. Use the contracts codec to ensure frontmatter round-trips cleanly.

**Acceptance Criteria:**
- New file is created with valid YAML frontmatter, body, and wikilinks.
- Updating an existing file preserves operator-added frontmatter keys.

### Task 4: Implement `apps/wiki/wiki_worker.py`

**Files:** `apps/wiki/wiki_worker.py`, `tests/test_wiki_generator.py`

**Read first:**
- `apps/triage/worker.py` (aio-pika consumer + health server pattern)
- `apps/scheduler/scheduler_main.py` (scheduling pattern)

**Action:**
1. Create `wiki_worker.py` that calls `store.get_active_entities(since=...)` and passes each target to `WikiGenerator`.
2. Support either a periodic schedule (configurable interval, default 1 hour) or consumption of `verdict.ready` events.
3. Include a `/health` endpoint and structured logging.

**Acceptance Criteria:**
- Worker runs end-to-end against a mock store and writes at least one wiki page.
- Health endpoint returns 200.

## Wave 3: DGX Backend Integration

### Task 5: Implement `apps/wiki/dgx_client.py` as a `RecallBackend`

**Files:** `apps/wiki/dgx_client.py`, `tests/test_wiki_generator.py`

**Read first:**
- `apps/triage/recall.py` (the `RecallBackend` Protocol / `_llm` abstraction)
- `ops/llm-router.py` or documented DGX endpoint details

**Action:**
1. Define a `DGXSynthesisBackend` class implementing the same interface as the local synthesis backend.
2. Route requests to the DGX endpoint with larger `max_tokens` and timeout handling.
3. Add a test using a mocked HTTP transport.

**Acceptance Criteria:**
- `DGXSynthesisBackend.synthesize(prompt)` returns a string.
- Mock test proves the correct endpoint and payload are used.

### Task 6: Wire `--backend dgx` into `apps/triage/recall.py`

**Files:** `apps/triage/recall.py`

**Read first:**
- `apps/triage/recall.py` (argparse + `_llm` / `_synthesis_prompt`)

**Action:**
1. Add `--backend {local,dgx}` argument (default `local`).
2. Select the appropriate backend in `_llm()`.
3. Ensure the DGX backend respects local-only ADR-004 for non-heavy tasks (default local).

**Acceptance Criteria:**
- `recall.py --topic ... --synthesize --backend dgx` routes to the DGX backend.
- Default remains local.

## Wave 4: Cross-Language Verification (Former Phase 999.4)

### Task 7: Enforce Language Coverage in Synthesis

**Files:** `apps/wiki/generator.py`, `apps/triage/recall.py`, `tests/test_cross_language_synthesis.py`

**Read first:**
- `apps/triage/recall.py` (synthesis result handling)
- `apps/wiki/generator.py` (wiki result handling)

**Action:**
1. Implement `verify_language_coverage(context_items, text)` that:
   - Extracts the set of `lang` values present in `context_items`.
   - Parses all `[item_id]` citations in `text`.
   - Maps each citation back to its item's `lang`.
   - Returns missing languages.
2. If any language is missing, append a verification flag block to the output (Markdown callout):
   `> ⚠️ **Verification Flag**: <lang> language sources were present but not cited.`
3. Apply the check to both `generator.py` standing pages and `recall.py` on-demand synthesis.

**Acceptance Criteria:**
- Test proves that a mock LLM output omitting Russian sources is flagged.
- Test proves an output citing all present languages passes.

### Task 8: Intra-Page Contradiction Prompting

**Files:** `apps/wiki/generator.py`, `apps/triage/recall.py`

**Action:**
1. Add an explicit system/user prompt instruction: "Highlight any contradictions between the provided sources. If sources disagree, state the disagreement explicitly."
2. Add a test asserting the instruction is present in the prompt.

**Acceptance Criteria:**
- Contradiction instruction is present in all synthesis prompts.

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| DGX API | Outbound synthesis payload must only contain authorized corpus data; no SOCMINT/ACLED data sent to DGX without license checks. |
| Obsidian Vault | Wiki builder writes to the vault. Must not overwrite operator notes outside of the designated auto-wiki folders. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-10-01 | Tampering | Obsidian vault writes | Medium | Mitigate | Restrict wiki generator to `Vault/wiki/auto/` paths only. |
| T-10-02 | Info Disclosure | DGX API | High | Mitigate | Ensure only sanitized chunks are sent; respect license tags. |
| T-10-03 | Information Quality | Cross-language omission | Medium | Mitigate | `verify_language_coverage` flags silent drops. |
</threat_model>

<verification>
- `pytest tests/test_store_entities.py -k get_active_entities -x` green
- `pytest tests/test_wiki_generator.py -x` green
- `pytest tests/test_cross_language_synthesis.py -x` green
- End-to-end: run `python apps/triage/recall.py --topic "NATO" --synthesize --backend dgx` (with mock DGX) and verify Markdown output + language coverage flag behavior
- Check the Obsidian vault `wiki/auto/` directory for generated/updated pages
</verification>

<success_criteria>
From `.planning/ROADMAP.md` §Phase 10:

1. A standing, auto-updated wiki exists as cross-linked Obsidian `.md` files.
2. On-demand synthesis functions via `recall.py` with DGX support.
3. Cross-language synthesis verification (Phase 999.4) is complete and tested, preventing silent omission of non-English sources.
</success_criteria>

<output>
Create `.planning/phases/10-wiki-llm/10-01-SUMMARY.md` when done
</output>
