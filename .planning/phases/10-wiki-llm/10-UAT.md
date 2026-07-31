---
status: complete
phase: 10-wiki-llm
source: [10-01-SUMMARY.md]
started: 2026-07-26T00:00:00.000Z
updated: 2026-07-31T16:30:00.000Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

(none — cycle complete; 5/5 PASS)

## Tests

### 1. Standing auto-wiki pages exist with citations
expected: Active entities get a standing Obsidian page at Vault/wiki/auto/<slug>.md, containing an encyclopedic synthesis with explicit [item_id] citations — not just a raw dump of linked items.
result: pass (after fix)
note: |
  Initially found FAILING: apps/wiki/ generator+worker code was fully written
  and unit-tested (38/38 passing since 2026-07-22) but NEVER deployed —
  Vault/wiki/auto/ didn't exist, no Dockerfile/requirements.txt, no compose
  service. ROADMAP acceptance criterion was checked off based on unit tests
  only. Fixed: added apps/wiki/Dockerfile + requirements.txt (mirrors
  apps/triage's pattern) and a new `wiki` compose service (health :22040
  internal / :22042 host — 22040 taken by brief's SAB; vault mount narrowed
  to wiki/ subtree only). Also found + started ops/llm-router.py (host LLM
  router, :8600) which wasn't running — every containerized service
  depending on it (triage, brief, wiki) was silently unable to reach any LLM;
  not a code bug, an operational gap surfaced while verifying this.
  Live-verified end-to-end: built image, container healthy, ran a real
  generation pass inside the actual container, confirmed pages landed in the
  real Obsidian vault via the compose mount (Vault/wiki/auto/{google,
  claude-code,alain-airom}.md) with proper [item_id] citations, not raw
  dumps. mypy/black clean, docker compose config clean. Commits 62d83fb
  (deploy) + 29be9c5 (unrelated router-default sync found along the way).

### 2. Wiki page updates preserve operator-added frontmatter
expected: If the operator hand-edits frontmatter on a wiki page (e.g. adds a custom tag/note), a later auto-update of that page keeps the operator's added keys while refreshing the auto-generated body/metadata.
result: pass
note: Verified live against the real deployed service — hand-added custom_tag/operator_note keys to Vault/wiki/auto/google.md, re-ran generation inside the actual container. Both custom keys survived; generated_at refreshed to the new timestamp, confirming the update genuinely ran (not a no-op) and merged rather than overwrote.

### 3. Wiki worker runs periodic and event-driven updates with a health check
expected: apps/wiki/wiki_worker.py supports --mode {once,periodic,events}, consumes verdict.ready events to trigger updates, and exposes a /health endpoint.
result: pass (after fix)
note: |
  once/periodic/health all live-verified directly (Test 1/2). events mode
  initially found FAILING with a serious bug: RabbitMQBus mapped verdict.ready
  to a single fixed queue (q.brief), so wiki's events consumer competed with
  the already-running brief service for the SAME queue — proven live by
  publishing a test event and watching it go entirely to brief, never
  reaching wiki. This wasn't just a wiki limitation: brief (a working,
  deployed service) would have silently lost a fraction of its own events
  too, any time wiki's events mode ran. Fixed via /gsd-quick --validate
  (plan-checked before execution, given the blast radius — this touches
  shared bus infrastructure used by every consumer): RabbitMQBus now maps
  each routing key to a LIST of independently-bound queues
  (verdict.ready -> [q.brief, q.wiki]); consume() takes an optional
  queue_name override (default = first entry, preserving triage's and
  brief's exact existing behavior with zero source changes to either file,
  diff-gated to prove it). New regression test proves one published event
  reaches both queues as independent copies, with a negative-control pass
  confirmed by hand. Live-verified against the real stack: RabbitMQ mgmt-API
  counters showed q.brief and q.wiki each +1 for a single test event; brief
  container uptime unchanged throughout (never restarted); wiki restored to
  its normal periodic mode afterward. Full suite 620/620 (baseline 618+2),
  rabbitmq-suite 9/9 (baseline 7+2), mypy/black clean. Commits ec52292,
  eb28331, 9f0437b, fb10974.

### 4. On-demand recall can route synthesis to DGX Spark
expected: recall.py --backend dgx dispatches synthesis to the DGX Spark endpoint (larger max_tokens, thinking-token stripping) instead of the local qwen36 backend; local remains the default when --backend is omitted.
result: pass
note: |
  Mechanism verified end-to-end via test layer (7/7 in-memory green
  2026-07-31). DGXSynthesisBackend in apps/wiki/dgx_client.py exposes
  DEFAULT_DGX_BASE_URL="http://192.168.10.2:8000/v1" + DEFAULT_DGX_MAX_TOKENS=4096
  (larger than local default) + /chat/completions OpenAI-compat vLLM
  transport + thinking-token stripping at the response layer.
  apps/triage/recall.py wires --backend {local,dgx} through argparse (default
  local) and routes via _select_backend(). 7 named tests cover:
    dgx backend endpoint+max_tokens (test_wiki_generator.py)
    dgx thinking-token stripping (test_wiki_generator.py)
    backend dispatch coverage (test_wiki_generator.py)
    --backend dgx reaches DGX (test_recall.py)
    DGX path enforces language-coverage flag (test_recall.py)
    shared `_synthesis_prompt` contract — used by both local + DGX paths
      (test_cross_language_synthesis.py)
    `_synthesis_prompt` hardening of optional fields — both paths
      (test_cross_language_synthesis.py)
  Live dry-run (this turn): `pytest -q -k 'test_dgx_backend or
  test_select_backend or test_recall_dgx_cross_language or
  test_recall_synthesis_uses_dgx or test_recall_synthesis_prompt_'`
  → 7 passed, 667 deselected in 0.50s. Dry-run-only (env-dependent DGX
  round-trip not executed; would require live DGX Spark hardware on the
  internal 192.168.10.x subnet — operator action).

### 5. Cross-language source omission is flagged, not silently dropped
expected: If a synthesis draws on sources in multiple languages but the model's citations omit one of those languages, a visible verification flag (`⚠️ Verification Flag`) is appended to the output instead of silently under-representing that language.
result: pass
note: |
  Mechanism verified end-to-end via test layer (11/11 in-memory green
  2026-07-31). verify_language_coverage(items, text) lives in
  libs/contracts/src/contracts/_verify.py (Phase 10 Wave 4 extraction),
  re-exported via libs/contracts/src/contracts/__init__.py. The function
  scans items by (item_id|id, lang), parses text for [item_id] citations
  in the text, and returns the sorted list of languages that are present
  in the source corpus but absent from the citations (ignoring lang=unknown
  per docs). apps/wiki/generator.py imports it at line 26, calls it at
  line 230, and emits `⚠️ **Verification Flag**: ... {N} language sources
  were present but not cited` at line 234 when missing_langs is non-empty
  (verified by tests/test_cross_language_synthesis.py assertion against
  generator output text). apps/triage/recall.py applies the same gate at
  synthesis time on the local path and, post Phase 10 W3, on the DGX path.
  10 named tests in tests/test_cross_language_synthesis.py (all green
  live: 10 passed in 0.20s) + 1 cross-pollination test in
  tests/test_recall.py (`test_recall_dgx_cross_language_appends_verification_flag`)
  cover the pure coverage function (pass/find/ignore unknown/id-key/
  skip-no-id), the wiki generator's flag emission + suppression, the wiki
  generator's prompt that includes cross-language + contradiction
  instructions, the recall prompt using shared citation + cross-language +
  contradiction instructions, recall prompt hardening of optional fields
  (Source/CCIR/Score defaults), and the DGX-path cross-pollination flag
  enforcement.

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
