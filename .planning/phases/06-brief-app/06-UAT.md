---
status: diagnosed
phase: 06-brief-app
source: 06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md, 06-05-SUMMARY.md, 06-06-SUMMARY.md
started: 2026-07-11T21:00:00Z
updated: 2026-07-11T21:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running services (docker compose down -v). Start the stack from scratch (docker compose up -d). All services boot without errors, schema/migration completes, GET http://localhost:22040/health returns ok.
result: pass
evidence: |
  Deviation: ran `docker compose down` + `up -d` WITHOUT -v (volumes preserved) — full
  volume-wipe + reseed already validated in round 1 (2026-07-10); wiping now would destroy
  live enrichment data needed by tests 3-8. All 14 services restarted; brief healthy in 20s;
  /health returned {"status":"ok","service":"brief"}; 0 errors in brief logs.

### 2. View SAB via /sab endpoint with query params
expected: GET /sab returns staleness-gated HTML page (CNR alerts top, CCIR sections, "siden" timestamp). ?window=Nh narrows the time window; ?mode=list renders list view sorted by score.
result: pass
evidence: |
  /sab → HTTP 200, 74KB HTML, title "InfoTriage · SAB — siden 2026-07-10 18:13", 4 CNR +
  FFIR/CCIR sections. ?window=48h → 200, 81KB (window respected). ?mode=list → 200, compact
  list "7 viktigste" sorted 9,9,8,8,8,8,8 with 🚩 flags.

### 3. Semantic clustering groups related items per CCIR
expected: Items with similar content within the same CCIR section merge into multi-source clusters ("N kilder"); items from different CCIR sections never merge into one cluster.
result: pass
evidence: |
  Live /sab shows 6 multi-source clusters ("2 kilder", "3 kilder"). 169 embeddings in
  infotriage.embeddings. CCIR-boundary: zebra decoy items (near-identical content, seeded
  in PIR-1 vs PIR-2) rendered as separate items — never merged across sections.

### 4. CLUSTER_THRESHOLD env var validated and wired
expected: Setting CLUSTER_THRESHOLD outside 0.0-1.0 fails startup with a clear error. A valid value changes clustering behavior — the value reaches the actual clustering call.
result: pass
evidence: |
  CLUSTER_THRESHOLD=1.5 → ValueError("CLUSTER_THRESHOLD must be 0.0–1.0, got 1.5") at import.
  Live 42-row corpus clustered in-container: threshold=0.95 → 35 clusters (5 multi);
  0.75 → 8 clusters (6 multi). Value demonstrably reaches cluster_items_in_memory().
  Note: ad-hoc DB reads need pgvector register_vector(); production PostgresStore registers
  it in __enter__ (embedding arrives as str otherwise — harness artifact, not a product bug).

### 5. Vault writer emits Obsidian .md files
expected: After a render cycle, /vault/brief-outbox contains obsidian-sab.md plus per-item .md files for high-value items, with YAML front-matter and [[entity]] wikilinks.
result: pass
evidence: |
  /vault/brief-outbox (host: ~/Vault/brief-outbox) holds obsidian-sab.md (22 saker,
  22 wikilinks, SIR/PIR sections) + per-item .md files keyed by item_id with YAML
  front-matter (bucket, ccir, cnr, score, source, title, url).

### 6. VAULT_INCLUDE_EMAIL toggle
expected: Default (1): email-sourced items appear in vault output. Set to 0 and re-render: email-sourced items excluded from vault files.
result: issue
reported: "VAULT_INCLUDE_EMAIL=0 does not exclude production email items. Synthetic proof in-container: row with source='gmail' (exactly what production enrichment rows carry) is still written to vault + obsidian-sab.md under VAULT_INCLUDE_EMAIL=0; control row with source='imap://…' is correctly excluded. Default-include half works (gmail item present in live vault)."
severity: major

### 7. Markdown digest rendering correctness
expected: brief.md shows CNR alerts first; list mode sorted score-descending (score >= 8 flagged); BLUF section has [N] citations and a visible placeholder (not silence) on LLM failure.
result: pass
evidence: |
  FINDING (resolved during UAT): running container image (built 12:27) predated renderer
  fix 07df0d9 (committed 18:18) — live brief.md showed the pre-fix "- Why:" regression.
  md5 of /app/apps/brief/renderer.py != host. Rebuilt + restarted brief during UAT.
  Post-rebuild fresh render: CNR section first; CCIR lines = flag + **[score] title** · why
  + (N kilder) + [les](url); bluf.md has [N] citations per CCIR section; list.md sorted
  9,9,9,8,8,8,8,8. Ops takeaway (Phase 7 scope): no guard that running images match HEAD.

### 8. Event-driven rendering end-to-end
expected: Publishing a verdict.ready event triggers the consumer: all four digest files (incl. bluf.md) atomically rewritten, and a sab.published event is emitted on the bus.
result: pass
evidence: |
  scripts/uat_test7_event.py against live stack: q.brief has 1 consumer; republished
  verdict.ready → 4/4 digests atomically rewritten (brief.md, cluster.md, list.md, bluf.md);
  sab.published landed on q.notify (depth 0 → 1). All checks passed.

## Summary

total: 8
passed: 7
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "VAULT_INCLUDE_EMAIL=0 excludes email-sourced items from vault output"
  status: failed
  reason: "User-run live test: production email rows carry source='gmail' with the imap URI in the url field, but the exclusion filter matches source.startswith('imap://') — it can never fire on real data. Exclusion currently works only for the synthetic source='imap://…' shape."
  severity: major
  test: 6
  artifacts:
    - path: "apps/brief/vault_writer.py"
      issue: "write_vault_digest() line ~254: `kept = [r for r in kept if not (r.get('source') or '').startswith('imap://')]` — wrong field; enrichment rows have source='gmail', the imap:// scheme lives in r['url']"
  missing:
    - "Exclusion predicate that matches production email rows, e.g. source == 'gmail' OR url.startswith('imap://')"
    - "Regression test with a production-shaped row (source='gmail', url='imap://…') asserting exclusion under VAULT_INCLUDE_EMAIL=0"
  root_cause: "Filter tests the wrong column: written against the url scheme but applied to the source field, which holds the adapter name ('gmail'), never an imap:// URI. Verified by synthetic-row experiment in the live container (gmail row leaked; imap:// row excluded)."

## Notes

- Round 2 (2026-07-11), executed by Claude on user request. Round 1 (9/9 pass) preserved at commit 235b3d2.
- Test 1 deviation: volumes preserved deliberately (full -v wipe validated in round 1).
- Test 7 surfaced a deployment-freshness gap (stale image vs HEAD) — resolved by rebuild during UAT; systemic guard belongs to Phase 7 (ops Makefile).
