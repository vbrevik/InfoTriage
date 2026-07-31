---
created: 2026-07-31
kind: cross-session concept-spike learnings
status: active
---
# InfoTriage — Cross-Session Learnings

> Project-level retention for patterns, pitfalls, preferences, and open
> questions surfaced across sessions. Each dated session below is a *layer*;
> staleness gets pruned via `/learn prune` (gstack skill) or via individual
> revisit. New sessions are pre-pended above older ones so most-recent
> context stays at the top.

## How to add a new session

1. Surface patterns manually, OR at session close reflect and run `learn`.
2. Add a new `### YYYY-MM-DD — <title>` section below `## Sessions`
   in reverse-chronological order.
3. Tag each entry with a type: **pattern** / **pitfall** / **preference** /
   **open-question** / **arch**.
4. Cross-link to the artifact the entry came from (commit SHA, file path,
   test name) so future readers can reproduce.
5. Skip one-time transient errors (network blips, rate limits). Only log
   genuine operational or domain discoveries that would save 5+ minutes in
   a future session.

---

## Sessions

### 2026-07-31 — Phase 8 Nyquist audit + Phase 11 sibling debt flag

Scope: `/gsd-validate-phase 8` (State A: existing `08-VALIDATION.md`,
`status: validated`, `nyquist_compliant: true`). Audit closed cleanly after
three amend iterations. Phase 8 UAT continuation paused mid-flight at
Test 2 of 5 awaiting verdict. Phase 11 sibling debt (`articles.discipline
= 0 across 499 rows despite column existing`) flagged out-of-band.

#### Patterns

- **State-A re-audit amend ceiling = 2-3 iterations.** Pattern: append
  audit block (iter 1) → surface API drift / map-row omission (iter 2) →
  polish + add in-session verification qualifier (iter 3). Plan for
  multi-amend; landmark commit message carries metric snapshot + "no
  gaps" for traceability. Source: Phase 8 commit chain
  `ab40b5d` → `887fe7f` → `69c27d0` on
  `.planning/phases/08-entity-resolution/08-VALIDATION.md`.

- **`Store.get_active_entities` vs `Store.get_all_entities` are siblings,
  not a rename.** Both methods coexist on the protocol
  (`libs/store/src/store/_protocol.py`) plus Postgres + InMemory
  implementations. Production callers (`apps/brief/vault_writer.py:368` +
  `apps/wiki/wiki_worker.py`) use the active-entities view; full-aggregation
  `get_all_entities` remains the canonical sibling. Audit-maps need BOTH
  rows. Detection: when suspecting rename, grep for both names in protocol
  + tests + callers; if both exist, they're siblings. Phase 8 map gained
  row 08-02-06 to capture the active-entities view alongside row 08-02-03.

- **Nyquist closeout signal is unambiguous.** Three amend iterations on
  the same `docs(phase-XX)` milestone commit, with explicit reviewer
  verdict "PHASE N IS NYQUIST-COMPLIANT (State A satisfied)". Closing
  reviewer pass issues the declaration; that's the green light to flip
  `*-UAT.md` frontmatter `status: testing → complete` on the final UAT
  test verdict.

- **`State A Step 6` map updates can ADD rows, not just flip checkboxes.**
  When re-auditing, `Step 6: Update Per-Task Map statuses` is permissive
  about *new* rows — protocol surfaces that evolve post-closeout
  (e.g., `get_active_entities` landing alongside `get_all_entities`)
  should be captured with their own map row + tests + callers, not
  retroactively folded into the original row. Source: this session's
  row 08-02-06 addition.

- **Mechanism-pass + live-data-caveat is a valid close posture when
  audit history documents the same observation.** Phase 8 close pattern:
  mechanism fully validated on injected data (`test_entity_links_cross_language`
  passes, HNSW index live, `LINK_THRESHOLD=0.92` verified); live corpus
  doesn't exercise the path because of an *upstream* weakness (language
  detector returning `und` for 98% of entities). Cross-check the audit
  history before deciding escalate-or-close; if a prior audit block
  already documents the matching observation, mechanism-pass + flag is
  the right close posture, not a parallel-debug invocation.

- **Live-verify any figure I'm citing in audit work.** State-A audit
  blocks tend to inherit historical numbers from prior audit blocks;
  those are file-readable but the *current session's* claim needs
  verification in-session. Pattern: include "(verified in-session
  YYYY-MM-DD via `docker exec infotriage-postgres psql …`)" qualifier
  next to figures the audit asserts.

#### Pitfalls

- **Don't trigger debug agents when audit history already names the
  limitation.** Cross-language linking — mechanism tested green
  (`tests/test_store_entities.py::test_entity_links_cross_language`
  passes, HNSW index live on `infotriage.entities.embedding` with
  `vector_cosine_ops m=16 ef_construction=64`, `LINK_THRESHOLD=0.92`
  confirmed at `apps/triage/entities.py:33`). Live corpus shows
  0 cross-language merges attributable to upstream language detector
  returning `und` for 98% of entities. Same observation documented in
  `08-VALIDATION.md` "Validation Audit 2026-07-24" audit-block
  "Separately observed" paragraph. Cost of gratuitous parallel-debug
  spawn: 5+ min agent time per case. The user's discriminator on
  similar issues going forward: "if you consider this a real issue
  (not a known limitation), I'll spawn parallel debug agents." Use it.

- **Cross-phase verification cycles don't cross-contaminate.** Phase 11
  `articles.discipline = 0 across 499 rows despite the column existing`
  surfaced out-of-band during Phase 8 verification; held for Phase 11's
  own verification cycle rather than folded into Phase 8. Discipline:
  acknowledge in conversation, park debt for the owning phase's verify
  step (most likely `/gsd-validate-phase 11` given Phase 11's existing
  VERIFICATION.md-missing debt per cross-phase audit).

#### Preferences

- **One-test-per-response pacing for conversational UAT.** Subjective
  verdicts want evidence-rich per-test presentation: header → expected →
  mechanism table → data table → reading → verdict options (pass / issue
  / skip / blocked). Don't bundle tests; user drives the cadence. Bundle
  evidence collection but not verdict adjudications.

#### Open questions

- **Test 5 scope for Phase 8 UAT.** Default: vault note `[[Name]]`
  wikilinks + cosmetic dup-name deferred. Two cleaner paths: Path A
  (narrow — wikilinks only; clean close with cosmetic staying deferred)
  vs Path B (wider — bug-fix `_entity_names()` dedup in
  `apps/brief/vault_writer.py` first, then Test 5 covers both; closes
  latent cosmetic surface). Pre-decide at Test 4 verdict time, not
  under pressure at Test 5.

---

## Cross-references

- **Phase 8 validation (closed, Nyquist-compliant, awaiting UAT test
  continuations):** `.planning/phases/08-entity-resolution/08-VALIDATION.md`
- **Phase 8 UAT (in flight, paused at Test 2 of 5 awaiting verdict):**
  `.planning/phases/08-entity-resolution/08-UAT.md`
- **Phase 11 sibling debt (held for Phase 11's verification cycle):**
  `articles.discipline` column-population gap — 499 of 499 articles
  have `discipline = 0` despite the column existing. Suspected ingest
  path: `apps/ingest-acled/` or whichever ingest surface is responsible
  for discipline-mapping. Needs root-cause + backfill + per-ingest
  contract test when Phase 11 opens.

## Versioning

This file was created 2026-07-31. Future sessions pre-pend their dated
section above the current top entry. Stale entries should be pruned via
`/learn prune` when the underlying code changes (e.g., LINK_THRESHOLD
moves off 0.92, oracle re-validation reaches a different conclusion,
the `apps/ingest-acled/` discipline pipeline gets fixed or split).
