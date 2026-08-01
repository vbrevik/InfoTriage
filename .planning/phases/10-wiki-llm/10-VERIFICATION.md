---
phase: 10-wiki-llm
verified: 2026-08-01T00:00:00Z
status: gaps_found
score: 2/6 must-haves verified
behavior_unverified: 2
overrides_applied: 0
re_verification: false  # retroactive backfill — Phase 10 shipped without a VERIFICATION.md; this closes that closure-doc gap
gaps:
  - truth: "Wiki pages include cross-linked Obsidian .md formatting and cite source items by item_id"
    status: partial
    reason: >-
      The item_id citation half is met; the cross-linking half is not implemented at all.
      Zero of the 46 live pages in Vault/wiki/auto/ contain a single Obsidian [[wikilink]],
      and the generator has no code path that emits one. The Phase 6 helper that does this
      (render_wikilinked) exists but is never imported by the wiki generator. This is the
      "cross-linked" clause of ROADMAP SC-1, which is checked off in ROADMAP.md.
    artifacts:
      - path: "apps/wiki/generator.py"
        issue: >-
          _write_page (line 200-212) emits only `# {subject}`, the synthesis body, and a
          `## Sources` list of external markdown links `[title](url)`. No [[Entity]] wikilinks.
          Imports at line 20-27 pull from_frontmatter/to_frontmatter/verify_language_coverage
          but not render_wikilinked.
      - path: "apps/brief/vault_writer.py"
        issue: >-
          render_wikilinked(text, entities) at line 76 already implements Phase 6 entity
          wikilink-ification (with URL-corruption guard at line 91) — available but unused
          by Phase 10.
    missing:
      - "Call render_wikilinked (or an equivalent) on the synthesis body in generator._write_page, using the entity names from get_active_entities."
      - "Cross-link sibling wiki pages: entities co-occurring in a page's source items should render as [[slug]] links to their own Vault/wiki/auto/ page."
      - "Add a test asserting generated page bodies contain [[...]] wikilinks for known entities."
  - truth: "Cross-language synthesis verification enforces that all languages present in the corpus context are cited (Phase 999.4 backlog folded into this phase)"
    status: failed
    reason: >-
      Two compounding defects make the guard a no-op on the live path, empirically proven
      (see Behavioral Spot-Checks). (1) recall_items never selects `lang`, so items reaching
      verify_language_coverage in production carry no lang key, required_langs is empty, and
      the function returns [] unconditionally — which is why 0 of 46 live vault pages carry a
      Verification Flag. (2) The citation regex only matches a bare `[item_id]`, but the
      production prompt renders sources as `[item_id: <hash>]` and the LLM mirrors that exact
      format in real output — so a fully-cited synthesis is scored as citing nothing. The two
      defects mask each other: fixing (1) alone would flag every multi-language page falsely.
      The unit tests pass only because their mock LLM output uses the bare `[i1]` form that
      real output never takes. Phase 999.4 was closed against this implementation.
    artifacts:
      - path: "libs/store/src/store/_postgres.py"
        issue: >-
          recall_items SELECT at line 780 returns item_id, title, source, url, ccir, score, dist
          — no `lang`. The returned dict (line 794-804) therefore has no lang key.
          infotriage.articles.lang exists and is NOT NULL and indexed
          (libs/store/sql/002-articles.sql:12,21), so the column is available.
      - path: "libs/contracts/src/contracts/_verify.py"
        issue: >-
          Regex `\\[([^\\]]+)\\]` at line 52 captures the full "item_id: <hash>" string, then
          tests `cited in lang_by_item` at line 54 against bare-hash keys — never matches
          real output. Docstring at line 26 asserts the citation format is `[item_id]`, but
          the prompt that produces the text (apps/wiki/generator.py:100) emits
          `[item_id: {hash}]`.
      - path: "tests/test_cross_language_synthesis.py"
        issue: >-
          All coverage tests (lines 11-46) and the generator flag tests (lines 48-90) use the
          bare `[i1]` citation form and hand-supply a `lang` key that the live store never
          returns. Green tests over a shape production never produces.
    missing:
      - "Add `a.lang` to the recall_items SELECT and to the returned dict in _postgres.py (and the matching _inmemory.py path)."
      - "Make the citation regex accept the `[item_id: <hash>]` form the prompt actually elicits (or change the prompt to emit bare `[<hash>]` and pin it with a test)."
      - "Add a test that feeds verify_language_coverage the exact dict shape recall_items returns and the exact citation format the prompt elicits."
      - "Re-open Phase 999.4 or open a follow-up: it was closed 2026-07-22 against a non-functional live path."
prohibitions_flagged:
  - statement: "MUST NOT omit source items from non-English/Norwegian languages in synthesis"
    plan_status: resolved
    verification: test
    disposition: unverified
    flagged: true
    reason: >-
      Declared test-tier and marked resolved, but the enforcement mechanism it relies on
      (verify_language_coverage) is proven inert on the live path. Fail-closed: a well-formed
      test-tier prohibition with no working enforcement is UNVERIFIED, never green.
behavior_unverified_items:
  - truth: "DGX is integrated for heavy synthesis tasks"
    test: >-
      With DGX Spark reachable on the internal subnet, run
      `python apps/triage/recall.py --topic "NATO" --synthesize --backend dgx` from the host.
    expected: >-
      The request reaches http://192.168.10.2:8000/v1/chat/completions, returns a synthesis
      longer than the local backend's default budget (max_tokens boosted to 4096), and any
      reasoning/thinking tokens are stripped from the rendered markdown.
    why_human: >-
      Requires live DGX Spark hardware on the internal 192.168.10.x subnet. The 7 named tests
      cover endpoint, payload, max_tokens boost and thinking-token stripping against a mocked
      transport only. 10-UAT.md Test 4 records this explicitly as "Dry-run-only ... would
      require live DGX Spark hardware ... operator action". No test exercises a real round-trip,
      so the transport and the strip regex (_THINK_RE, dgx_client.py:28 — which the code's own
      comment warns is delimiter-specific) are unproven against the deployed model.
  - truth: "Intra-page contradictions are avoided or explicitly flagged in the generated text"
    test: >-
      Generate a wiki page for a subject whose recalled source items genuinely disagree
      (e.g. two sources reporting different casualty figures for the same event).
    expected: >-
      The generated body states the disagreement explicitly rather than silently picking one
      figure or averaging them.
    why_human: >-
      Enforcement is prompt-only. CONTRADICTION_INSTRUCTION (_verify.py:17-19) is wired into
      both synthesis prompts, and tests assert the instruction is present in the prompt string
      — but nothing verifies the model's output actually flags a contradiction. 10-01-SUMMARY.md
      is honest about this ("Prompt-only in Phase 10. A dedicated LLM call for contradiction
      detection is a Phase 11+ improvement"). Judging whether a synthesis surfaced a real
      disagreement is a human reading task.
---

# Phase 10: Wiki-LLM Verification Report

**Phase Goal:** An auto-maintained intel wiki synthesized from the corpus, plus on-demand synthesized articles.

**Verified:** 2026-08-01 (retroactive backfill — Phase 10 shipped 2026-07-22..2026-07-31 without a VERIFICATION.md)
**Status:** GAPS_FOUND (2/6 must-haves verified, 2 failed, 2 present-but-behavior-unverified)
**Re-verification:** No — initial verification, produced retroactively to close the Phase 10 closure-doc gap.

Evidence base: `10-PLAN.md` (must_haves), `10-01-SUMMARY.md`, `10-VALIDATION.md` (status: validated), `10-UAT.md` (5/5 pass), plus direct codebase and live-vault inspection. **SUMMARY/UAT claims were not accepted as evidence** — every row below is re-derived from the code or the real Obsidian vault.

---

## Goal Achievement

### Observable Truths

Merged from ROADMAP §Phase 10 success criteria (the contract) and `10-PLAN.md` `must_haves.truths` (plan-specific detail).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| T1 | Standing per-entity and per-topic wiki pages are continuously updated in the Obsidian vault | ✓ VERIFIED | 46 live pages in `/Users/vidarbrevik/Vault/wiki/auto/`, most recent write `2026-08-01 12:51` (`android.md`, `alain-airom.md`). Worker deployed as a real compose service (`docker-compose.yml:254-296`), `restart: unless-stopped`, default `INFOTRIAGE_WIKI_MODE=periodic` / `INFOTRIAGE_WIKI_INTERVAL=3600`. Target selection wired: `apps/wiki/wiki_worker.py:46` `store.get_active_entities(**kwargs)`. Writer is atomic (`generator.py:157-159` tmp + `os.replace`). Frontmatter merge preserves operator keys (`generator.py:144-152`), live-confirmed in 10-UAT.md Test 2. |
| T2 | Wiki pages include cross-linked Obsidian `.md` formatting and cite source items by `item_id` | ✗ FAILED | **Citations: met.** Body carries inline `[item_id: <hash>]` (see `claude-code.md`) and frontmatter carries a `sources:` list of item_ids (`generator.py:206`). **Cross-linking: absent.** `grep -E '\[\[[^]]+\]\]'` over all 46 pages returns **0 pages**. `generator.py` has no `[[...]]` emission; `render_wikilinked` (`apps/brief/vault_writer.py:76`) is never imported. See Gaps. |
| T3 | On-demand synthesis answers ad-hoc queries from the corpus | ✓ VERIFIED | `apps/triage/recall.py:202` `store.recall_items(...)` → `:229-230` `backend.synthesize(...)` behind `--synthesize` (`:178`). Body hydration via `--include-body` (`:211-216`), and `safe_results` strips body before synthesis (`:223`). Covered by `tests/test_recall.py` (10 named tests). |
| T4 | DGX is integrated for heavy synthesis tasks | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Present and wired: `apps/wiki/dgx_client.py:30-32` (`DEFAULT_DGX_BASE_URL=http://192.168.10.2:8000/v1`, `DEFAULT_DGX_MAX_TOKENS=4096`), `:62` max_tokens boost, `:70` `/chat/completions`, `:28` thinking-token strip; `recall.py:181-184` `--backend {local,dgx}` default `local`; `:229` `_select_backend(args.backend)` (`:82-84`). No live DGX round-trip has ever run — 10-UAT.md Test 4 records it as dry-run-only pending operator hardware. Routed to human verification. |
| T5 | Cross-language synthesis verification enforces that all languages present in the corpus context are cited (Phase 999.4 folded in) | ✗ FAILED | Proven inert on the live path by direct execution (see Behavioral Spot-Checks): `recall_items` never returns `lang` (`_postgres.py:780`, `:794-804`), so the check short-circuits to `[]` at `_verify.py:47-49`; and the citation regex (`_verify.py:52`) cannot match the `[item_id: <hash>]` form the prompt elicits (`generator.py:100`). Consistent with the live vault: **0 of 46 pages** carry a Verification Flag. See Gaps. |
| T6 | Intra-page contradictions are avoided or explicitly flagged in the generated text | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | `CONTRADICTION_INSTRUCTION` (`_verify.py:17-19`) is wired into the wiki prompt (`generator.py:93`) and imported by `recall.py:24`. Tests assert only that the instruction appears in the prompt string; nothing exercises whether output actually flags a disagreement. Enforcement is prompt-only by design (10-01-SUMMARY.md "Decisions recorded"). Routed to human verification. |

**Score:** 2/6 truths verified (2 failed, 2 present but behavior-unverified).

### ROADMAP Success Criteria (the contract)

| # | Criterion | Status | Verdict |
|---|-----------|--------|---------|
| SC-1 | A standing, auto-updated per-entity/per-topic wiki is written as **cross-linked** Obsidian `.md` | **PARTIAL — NOT MET** | Standing + auto-updated + Obsidian `.md`: met (T1). **Cross-linked: not met** (T2) — zero wikilinks across 46 live pages. ROADMAP currently shows this criterion as ✅; that checkmark is not supported by the vault. |
| SC-2 | On-demand synthesized articles answer ad-hoc queries from the corpus; DGX used for heavy synthesis | **PARTIAL** | On-demand synthesis: met (T3). DGX: code present and wired but never exercised against real hardware (T4) — human verification. |

**Note on ROADMAP drift:** the Phase 10 `**Status**:` line still reads "Waves 1-3 complete ... Wave 4 (cross-language verification) queued", while `10-01-SUMMARY.md` and `10-UAT.md` record Wave 4 as complete. The line is stale in one direction; the SC-1 ✅ is optimistic in the other.

### Deferred Items

None. Phase 999.4 (cross-language synthesis verification) is marked **CLOSED 2026-07-22 — shipped as Phase 10 Wave 4** in ROADMAP.md, so the T5 failure cannot be deferred to it — it was closed against this implementation. No Phase 11/12 success criterion covers wiki cross-linking or the language-coverage defect. Both gaps are actionable now.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `libs/store/src/store/_protocol.py` | `get_active_entities` on the Store Protocol | ✓ VERIFIED | Declared at `:224`. |
| `libs/store/src/store/_postgres.py` | Postgres `get_active_entities` | ✓ VERIFIED | `:642`; joins `entity_links` → satisfies the Phase 8 key link. |
| `libs/store/src/store/_inmemory.py` | InMemory `get_active_entities` | ✓ VERIFIED | `:328`. |
| `apps/wiki/generator.py` | Prompting + Obsidian create/update writer | ⚠️ HOLLOW (partial) | 238 lines, substantive, wired, real data flows (live pages prove it). **But** no wikilink emission (T2) and it feeds `verify_language_coverage` a dict shape that has no `lang` key (T5). |
| `apps/wiki/wiki_worker.py` | Periodic/event-driven worker + `/health` | ✓ VERIFIED | 328 lines. `--mode {once,periodic,events}` (`:203-209`, default from `INFOTRIAGE_WIKI_MODE`), `run_once` (`:55`), `run_periodic` (`:86`), `run_consumer` (`:149`) with `bus.consume("verdict.ready", ..., queue_name="q.wiki")` (`:166`), `/health` server (`:178`, `:192`). |
| `apps/wiki/dgx_client.py` | DGX `RecallBackend` implementation | ✓ VERIFIED (artifact) | 82 lines; `RecallBackend` protocol at `:20`, `DGXSynthesisBackend` at `:38`. Behavior unproven against real hardware (T4). |
| `apps/wiki/Dockerfile` + `requirements.txt` | Deployable service | ✓ VERIFIED | Both present; compose service builds from them. Added mid-UAT (`62d83fb`) after UAT Test 1 found the code was unit-tested but never deployed. |
| `libs/contracts/src/contracts/_verify.py` | `verify_language_coverage` + shared prompt constants | ✗ DEFECTIVE | 57 lines. Constants (`:15-19`) are correct and shared. The coverage function is non-functional on the live path (T5). |
| `libs/contracts/src/contracts/_bus_rabbitmq.py` | Fan-out routing table | ✓ VERIFIED | `ROUTING_KEY_TO_QUEUE` widened to lists at `:50-55` with `"verdict.ready": ["q.brief", "q.wiki"]`; `consume(..., queue_name=None)` at `:247-252` with the default-preservation contract documented at `:261-267`. |
| `apps/triage/recall.py` | `--backend dgx` + verification hooks | ⚠️ VERIFIED with caveat | `--backend` at `:181-184`, dispatch at `:229`, coverage hook at `:240-244`. Caveat: reaches `dgx_client` via `sys.path.insert(.../apps/wiki)` at `:21` — host-only (see Anti-Patterns). |
| `tests/test_wiki_generator.py` | Wiki generator unit tests | ⚠️ PRESENT, WEAK | 13 named tests. Green, but exercise mocked stores whose dict shape does not match `recall_items` output. |
| `tests/test_cross_language_synthesis.py` | Phase 999.4 language omission tests | ⚠️ PRESENT, WEAK | 10 named tests. Green over a citation format and item shape production never produces (T5). |
| `tests/test_bus_consume.py` | Fan-out regression test | ✓ VERIFIED | `test_verdict_ready_fans_out_to_both_queues` at `:208` (`@pytest.mark.rabbitmq`, skips without a broker) plus `test_consume_rejects_queue_not_bound_to_routing_key` at `:281`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `apps/wiki/generator.py` | Phase 6 Obsidian conventions | frontmatter codec + wikilinks | ⚠️ PARTIAL | Frontmatter codec reused (`from_frontmatter`/`to_frontmatter`, `generator.py:24-25`, used at `:147`/`:154`). Wikilink convention **not** reused — `render_wikilinked` (`apps/brief/vault_writer.py:76`) is never imported. This partial link is the direct cause of the T2 failure. |
| `apps/wiki/wiki_worker.py` | Phase 8 entity resolution | `store.get_active_entities` | ✓ WIRED | `wiki_worker.py:46` → `_postgres.py:642`, which joins `infotriage.entity_links`. |
| `apps/triage/recall.py` | Phase 9 `RecallBackend` protocol | `dgx_client.RecallBackend` | ✓ WIRED | `recall.py:30` imports both `DGXSynthesisBackend` and `RecallBackend`; `_select_backend` (`:82-84`) returns the protocol type. |
| `apps/wiki/wiki_worker.py` | RabbitMQ `verdict.ready` | `bus.consume(queue_name="q.wiki")` | ✓ WIRED | `wiki_worker.py:166` + `_bus_rabbitmq.py:52`. Independent queue — no longer competes with brief. |
| `apps/wiki/generator.py` | Obsidian vault | compose bind mount | ✓ WIRED | `docker-compose.yml:284` mounts `${OBSIDIAN_VAULT_PATH}/wiki:/vault/wiki:rw`; `.env:39` sets `OBSIDIAN_VAULT_PATH=/Users/vidarbrevik/Vault`. Narrow mount satisfies threat T-10-01 (writer confined to the wiki subtree). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `generator.generate_page` | `items` | `store.recall_items(vec, limit)` via `_recall_for_subject` (`:186-188`) | Yes — real corpus rows, proven by 46 populated live pages | ✓ FLOWING |
| `generator._write_page` | `synthesis` | `self.llm(...)` → host LLM router `:8600` (`docker-compose.yml:275`) | Yes — real LLM prose in live pages | ✓ FLOWING |
| `generator.generate_page` | `missing_langs` | `verify_language_coverage(items, synthesis)` (`:230`) | **No** — `items` carry no `lang` key, so the value is always `[]` | ✗ DISCONNECTED |
| `wiki_worker` | `entities` | `store.get_active_entities(**kwargs)` (`:46`) | Yes — real entity slugs became real page filenames | ✓ FLOWING |

The third row is the Level-4 finding that presence and wiring checks miss: the call site is correct, the function is imported and invoked, and the flag-emission branch below it is correct — but the data reaching it can never trigger that branch.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Language coverage accepts the citation format the prompt actually elicits | `verify_language_coverage([{item_id:'abc123',lang:'en'},{item_id:'def456',lang:'ru'}], "Claim [item_id: abc123] and [item_id: def456].")` | `['en', 'ru']` — a fully-cited synthesis reported as citing **nothing** | ✗ FAIL |
| Language coverage accepts the format the tests use | same items, text `"Claim [abc123] and [def456]."` | `[]` | ✓ PASS (test-only shape) |
| Language coverage against the live `recall_items` dict shape (no `lang` key) | same call with `[{item_id:'abc123'},{item_id:'def456'}]`, text with no citations at all | `[]` — guard is a no-op | ✗ FAIL |
| Live vault carries Verification Flags | `grep -l 'Verification Flag' /Users/vidarbrevik/Vault/wiki/auto/*.md` | 0 of 46 pages | ✗ FAIL (corroborates the two above) |
| Live vault carries Obsidian wikilinks | `grep -lE '\[\[[^]]+\]\]' /Users/vidarbrevik/Vault/wiki/auto/*.md` | 0 of 46 pages | ✗ FAIL |
| Live vault carries inline `item_id` citations | inspect `claude-code.md` body | 7 inline `[item_id: <hash>]` citations across the synthesis | ✓ PASS |
| Standing pages exist and are current | `ls -la /Users/vidarbrevik/Vault/wiki/auto/` | 46 pages, newest `2026-08-01 12:51` | ✓ PASS |
| Fan-out regression test exists | `grep 'def test_' tests/test_bus_consume.py` | `test_verdict_ready_fans_out_to_both_queues:208` present | ✓ PASS |
| DGX live round-trip | — | not run: requires DGX Spark on 192.168.10.x | ? SKIP → human |

An earlier `grep -c '\[\['` appeared to show wikilinks on 38 of 46 pages. Those were false positives — markdown links whose **titles** start with `[`, e.g. `[[ngrok news] certified 100% slop-free](imap://...)`. The anchored `\[\[[^]]+\]\]` match returns zero. Worth recording because the naive grep is exactly what would have let this pass.

Full test suite was **not** run for this backfill, per instruction. Recorded baseline: `make -f ops/Makefile test-safe` = **677 passed / 0 failed** in 43.97s at `63b8da2` (`.planning/STATE.md:12`, `:55`). Two commits have landed since (`bb5420e` adds a per-ingest contract test, `7082f54`/`510dade` test isolation fixes), consistent with the 678-passing figure reported this session; STATE.md has not yet been bumped past 677.

### Probe Execution

Not applicable — Phase 10 declares no `scripts/*/tests/probe-*.sh` probes, and none exist for the wiki surface. Verification criteria in `10-PLAN.md` are pytest- and vault-inspection-based, both exercised above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ADR-006 | 10-PLAN.md | Microservice architecture + entity resolution | ✓ SATISFIED | Wiki ships as an independent compose service with its own Dockerfile, health check, restart policy and narrow vault mount; consumes entity resolution via `get_active_entities` → `entity_links`. |
| spec §Obsidian | 10-PLAN.md | Obsidian output conventions | ✗ BLOCKED | Frontmatter codec conventions honored; the wikilink convention (Phase 6 `render_wikilinked`) is not. Same root cause as T2. |
| ADR-004 (all-local-LLM) | inherited | No cloud LLM endpoints | ✓ SATISFIED | Wiki routes to `http://host.docker.internal:8600/v1` (host router, Spark/oMLX) per `docker-compose.yml:275`; DGX default target is the internal `192.168.10.2` subnet; `--backend` defaults to `local`. |
| Phase 999.4 | folded into 10 | Cross-language synthesis verification | ✗ BLOCKED | Closed 2026-07-22 against an implementation that is inert on the live path (T5). |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | `TODO`/`FIXME`/`XXX`/`HACK`/`PLACEHOLDER` debt markers | — | **None found** across all Phase 10 files. No debt-marker gate violations. |
| `libs/contracts/src/contracts/_verify.py` | 26 | Docstring asserts a citation format (`[item_id]`) that the paired prompt does not produce (`[item_id: <hash>]`) | 🛑 BLOCKER | Root cause of half of T5. The docstring made the mismatch look intentional. |
| `tests/test_cross_language_synthesis.py` | 11-90 | Tests assert over a mock item shape (`lang` present) and citation format (bare `[i1]`) that production never produces | 🛑 BLOCKER | Green tests concealed a fully inert guard through UAT, VALIDATION and 999.4 closure. |
| `apps/triage/recall.py` | 21 | `sys.path.insert(.../apps/wiki)` to import a sibling app's module | ⚠️ WARNING | `apps/triage/Dockerfile` copies only `apps/triage/`, so `apps/wiki/dgx_client.py` is absent from the triage image — `recall.py` would `ImportError` at module load inside the container. It is a host-only CLI by construction; that constraint is undocumented and sits beside `worker.py`, which *is* the container entrypoint. |
| `apps/wiki/generator.py` | 186-188, 219-226 | `_recall_for_subject` applies no relevance threshold — `recall_items(vec, limit=max_items)` always returns `max_items` rows | ⚠️ WARNING | Pages are generated and published for subjects with no relevant corpus coverage. Live examples: `android.md`, `google.md`, `alain-airom.md` all read "The provided articles do not cover the topic" while still listing 20 unrelated Sources and 20 item_ids in frontmatter. The empty-corpus stub branch at `:220-224` only fires on a literally empty result, which vector recall never returns. |
| `apps/wiki/dgx_client.py` | 26-28 | `_THINK_RE` delimiter is model-specific, flagged as such by its own comment | ℹ️ INFO | Unproven against the deployed DGX model; part of the T4 human-verification item. |
| `.planning/ROADMAP.md` | §Phase 10 | Status line says Wave 4 "queued"; SC-1 checked ✅ despite the missing cross-linking | ℹ️ INFO | Doc drift in both directions. |

### Human Verification Required

Both items are `PRESENT_BEHAVIOR_UNVERIFIED` truths — code present and wired, runtime behavior never exercised.

#### 1. DGX Spark heavy synthesis round-trip

**Test:** With DGX Spark reachable, run `python apps/triage/recall.py --topic "NATO" --synthesize --backend dgx` from the host.
**Expected:** Request reaches `http://192.168.10.2:8000/v1/chat/completions`; output exceeds the local backend's budget (max_tokens boosted to 4096); reasoning/thinking tokens are stripped from the rendered markdown.
**Why human:** Requires live hardware on the internal 192.168.10.x subnet. All 7 DGX tests use a mocked transport. `10-UAT.md` Test 4 records this as dry-run-only, operator action. The `_THINK_RE` strip pattern is delimiter-specific and unproven against the deployed model.

#### 2. Contradiction flagging in generated prose

**Test:** Generate a wiki page for a subject whose recalled sources genuinely disagree (e.g. conflicting casualty figures for one event).
**Expected:** The body states the disagreement explicitly rather than silently picking one figure.
**Why human:** Enforcement is prompt-only; tests assert only that the instruction string is in the prompt. Judging whether a synthesis surfaced a real disagreement is a reading task.

### Prohibitions

| Statement | Plan Status | Tier | Disposition |
|-----------|-------------|------|-------------|
| MUST NOT omit source items from non-English/Norwegian languages in synthesis | resolved | test | **UNVERIFIED — flagged.** Fail-closed: the declared enforcement (`verify_language_coverage`) is proven inert on the live path, so the prohibition has no working guard. Not green. Closing T5 resolves this. |

### Gaps Summary

Phase 10 shipped a genuinely working auto-wiki. The worker is deployed as a real service, 46 standing pages sit in the operator's actual Obsidian vault refreshed as recently as today, operator frontmatter edits survive regeneration, and the `verdict.ready` fan-out bug found during UAT was fixed properly — `ROUTING_KEY_TO_QUEUE` now maps to independently-bound queue lists with the existing-caller default explicitly preserved and regression-tested. That work is solid and the UAT that surfaced the never-deployed code and the competing-consumer bug did its job well.

Two must-haves nonetheless fail, and both were masked by tests that pass over shapes production never produces.

**Gap 1 — no cross-linking (T2 / ROADMAP SC-1).** The word "cross-linked" is in the roadmap criterion and the criterion is checked off, but zero of 46 live pages contain an Obsidian `[[wikilink]]` and the generator has no code that emits one. The Phase 6 helper `render_wikilinked` already exists in `apps/brief/vault_writer.py:76` and was named in the plan's own key_links; the wiki generator simply reuses the frontmatter half of that Phase 6 contract and not the linking half. Without it the wiki is 46 disconnected pages, not a wiki — the graph view that motivates an Obsidian target is empty.

**Gap 2 — cross-language verification is inert (T5 / Phase 999.4).** Two defects that mask each other. `recall_items` never selects `lang` even though `infotriage.articles.lang` is `NOT NULL` and indexed, so every item reaching `verify_language_coverage` in production lacks the key the function keys on and the function returns `[]` unconditionally. Independently, the citation regex matches only a bare `[item_id]` while the production prompt renders sources as `[item_id: <hash>]` and the model mirrors that format — so a *fully cited* synthesis scores as citing nothing. Direct execution confirms both. Fixing only the missing `lang` column would turn a silent no-op into a false-positive flag on every multi-language page, so both must be fixed together, with a test built from the real `recall_items` dict shape and the real citation format. Phase 999.4 was closed against this, so the backlog item needs reopening.

Neither gap is deferrable: no later milestone phase covers wiki cross-linking, and 999.4 is already marked closed as "shipped as Phase 10 Wave 4".

Two further truths (DGX round-trip, contradiction flagging) are present and wired but behaviorally unexercised, and route to the human checkpoint above rather than counting as verified. Two lower-severity warnings are worth queuing: `recall.py` is host-only by construction because it reaches into `apps/wiki` via `sys.path` while the triage image does not ship that module, and the generator's threshold-free recall publishes confident-looking pages for subjects the corpus does not cover.

---

_Verified: 2026-08-01 (retroactive backfill)_
_Verifier: Claude (gsd-verifier) — goal-backward against ROADMAP §Phase 10 success criteria and `10-PLAN.md` must_haves; all rows re-derived from code and the live vault, not from SUMMARY/UAT claims._
