---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: M1 ship-gate met (Phase 7 07-01..07-04 closed); M1 ship or Phase 8 next
stopped_at: Phase 7 07-02..07-04 closed and verified live; planning sweep complete (this commit)
last_updated: "2026-07-12T00:00:00.000Z"
progress:
  total_phases: 13
  completed_phases: 8
  total_plans: 34
  completed_plans: 34
  percent: 62
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-07-12 — Phase 7 07-02..07-04 closure (M1 ship-gate docs)

### Just-completed

- **07-02** (committed `591034d`): closed the 3 M1 known gaps from the 07-01 review — uvicorn JSON access logs via shared `LOGGING_CONFIG` (`libs/contracts/src/contracts/uvicorn-log-config.json` + `uvicorn_log_config.py` wrapper); live RabbitMQ-mgmt queue-depth probe (`apps/dlq_consumer/worker.py`, periodic GET, `feed.unhealthy` on `messages >= DLQ_DEPTH_CRITICAL_N`); `INFOTRIAGE_TEST_DSN` shell-smoke gate (`scripts/check_test_dsn.sh` + `make test-safe`). Pytest 319/0/34. See `.planning/phases/07-ops-cutover/07-02-SUMMARY.md`.

- **07-03** (committed `3da4932` + docs `428f8a9`): live-stack follow-up. After 07-02 made every InfoTriage service actively execute `from contracts import setup_logging` at module-init, three services (`dlq-consumer`, `opml-health`, `scheduler`) crash-looped on missing transitive contracts deps (`pydantic` / `PyYAML` / `aio-pika`). Closed via per-`requirements.txt` hand-listing + `libs/contracts/pyproject.toml` `aio-pika` addition + TOML-grammar fix + `apps/dlq_consumer/worker.py` vhost URL-encoding fix (the `///` → `%2F` mgmt-API correction). Pytest 0 failures. 2-pass code review PASS. See `.planning/phases/07-ops-cutover/07-03-SUMMARY.md`.

- **`b4ee46a` Makefile recursion fix**: detected when running `make -f ops/Makefile test-safe` end-to-end — `$(MAKE) test-full` sub-call failed because Make does NOT propagate `-f` via MAKEFLAGS. Captured the resolved path at parse time via `OPS_MAKEFILE := $(abspath $(lastword $(MAKEFILE_LIST)))` and forwarded `-f $(OPS_MAKEFILE)` explicitly. Full test-safe chain now exits 0 (DSN smoke + 351 pytest pass + teardown).

- **07-04** (committed `f17e644`): `tests/test_dep_list_superset.py` cross-check — every dep declared in `libs/contracts/pyproject.toml` MUST be re-listed in every `apps/*/requirements.txt` that consumes contracts. Detection = union of direct Python import ∪ Dockerfile `libs/contracts`-install ∪ transitive sibling-lib walk. Caught a real defect on first run: `apps/opml_health/requirements.txt` was missing `pydantic>=2.0` since the 07-03 partial patch; bug fixed in the same commit. 2-pass code review PASS. Pytest 328/0/34 (baseline preserved). See `.planning/phases/07-ops-cutover/07-04-SUMMARY.md`.

### M1 ship-gate status

All Phase 7 sub-plans (`07-01` through `07-04`) shipped. Full pytest suite green on the way out (328 pass, 34 skip, 0 fail). `make -f ops/Makefile test-safe` runs the full chain (DSN smoke + pytest container + teardown) and exits 0. **Phase 7 → M1 ship-gate satisfied.**

Local-main sync state:
- `afab4d9` + `023d9b2` (07-01 ship) → ON `origin/main`
- `591034d` (07-02 feat), `3da4932` (07-03 fix), `428f8a9` (07-03 docs), `b4ee46a` (Makefile fix), `f17e644` (07-04) → AWAITING PUSH (next-session decision: push, OR begin Phase 8 first).
- This planning-file sweep commit closes the planning portion of that bundle.

### Next

- **M1 ship or Phase 8 decision** (defensible either way): push the 5 unpushed commits + finalize milestone, OR begin Phase 8 (Entity Resolution) immediately. If going to Phase 8 first, address backlog 999.3 (cross-language entity linking revalidation on mE5-large) per the spike PARTIAL finding.

## Session: 2026-07-11 — 06-07 gap closure: VAULT_INCLUDE_EMAIL url-scheme fix

### Just-completed

- **06-07-PLAN.md COMPLETE** (commits `d7dba4a` test, `8ef54ee` fix): fixed the
  UAT round-2 Test 6 gap. `write_vault_digest()`'s `VAULT_INCLUDE_EMAIL=0`
  exclusion predicate tested `source.startswith("imap://")` — production gmail
  rows carry `source="gmail"` and production imap rows carry `source=<mailbox
  name>`, so neither adapter's rows were ever caught and email content leaked
  into the Obsidian vault even with the operator's opt-out set.

- **Fix**: added `_EMAIL_URL_SCHEMES = ("imap://", "gmail://")` and rekeyed the
  exclusion on `r["url"]` instead of `r["source"]` — `url` reliably carries the
  mail transport URI for both adapters
  (`gmail://message/...`, `imap://<host>/<id>`); `source_type` isn't in scope
  (consumer.py's SELECT omits it from the row dict).

- **TDD**: RED confirmed first (both `*_row_excluded_when_email_disabled`
  tests failed against the pre-fix predicate), then GREEN (all 14 tests in
  `tests/test_vault_writer.py` pass, plus `tests/test_brief_consumer.py`
  unaffected). Full-suite `pytest tests/ -q`: 296 passed, 1 pre-existing
  unrelated failure (`test_bus_consume.py::test_consume_delivers_message`,
  RabbitMQ live-consumer contention — logged to deferred-items.md, out of
  scope).

- ROADMAP SC3 (email opt-out) is now fully closed. Phase 06 has all 7 plans
  complete (`06-01`..`06-07`).

### Next

- See Session: 2026-07-12 (the new top-of-file entry) for the current Phase-7-closed state. The "07-01 in progress" stale-pointer is now resolved.

## Session: 2026-07-11 — Phase 7 07-01: M1 ship-gate ops

### Just-completed

- **Task 1 (retire host scripts):** Removed stale references to `fever_triage.py` and
  `gmail_to_atom.py` from `README.md`, `apps/ingest/_util.py`,
  `apps/ingest/RSS_BRIDGE_NOTES.md`, `apps/ingest/imap_to_atom.py`,
  `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md`, and
  `docs/adr/ADR-008-self-hosted-mcp-oauth2-ingestion.md`.

- **Task 2 (structured logging):** Added `contracts.setup_logging()` helper
  (`libs/contracts/src/contracts/_logging.py`) that emits JSON to stdout and a daily-
  rotating file under `/data/logs/<service>.log`, with a writable fallback to a temp
  dir. Wired it into all 8 services (ingest adapters via `make_trigger_app`, triage,
  brief, opml-health, scheduler). Added `LOG_LEVEL` env var to every compose service.
  Added `docs/ops/logging.md` with `jq` query examples.

- **Task 3 (ops/Makefile):** Expanded `ops/Makefile` with `help`, `up`, `down`,
  `logs`, `status`, `restart`, `shell-<service>`, `seed`, `backfill`, `replay`,
  `test-full`, and `clean`. Added host port `22041` for the `feeds` service so
  `make status` can probe it.

- **Task 4 (DLQ consumer):** Created `apps/dlq_consumer/` worker that consumes
  `infotriage.dlq`, logs at ERROR, emits `feed.unhealthy`, alerts at CRITICAL after
  10 consecutive messages, and supports `--replay` to republish to original routing
  keys. Added `dlq-consumer` service to `docker-compose.yml` and wired `make replay`.

- **Tests:** Added `tests/test_dlq_consumer.py` and `tests/test_ops_makefile.py`.
  Full pytest suite: 302 passed, 34 skipped, 0 failed.

### Post-review gap-closure (this session)

After the broad reviewer pass the working tree had 3 BLOCKING + 5 advisory items.
All BLOCKINGs resolved; all advisories resolved:

- **B1 — `LOG_LEVEL` anti-pattern**: kept `${LOG_LEVEL:-INFO}` (intentional
  operator knob; not the HANDOFF-flagged collision case). Top-of-file comment
  in `docker-compose.yml` documents the distinction explicitly.
- **B2 — README removed the "do not delete fever_triage" warning**: B2's
  premise (`digest.py` imports `fever_key`/`fever`/`strip_html`) turned out
  to be stale — fresh grep confirms `digest.py` has ZERO `fever_triage`
  references. The file is genuinely gone and the warning-removal is correct.
- **B3 — Plan-vs-execution gap on retire-host-scripts**: `apps/ingest/
  gmail_to_atom.py` was already deleted in commit `66477b8` (Phase 4 retire);
  `docs/ARCHITECTURE.md` / `ccir.md` were already clean. The only surviving
  cleanup was `.env.example`'s orphan `FRESHRSS_FEVER_*` vars (no Python
  callers post Phase 5 cutover) — removed with a 9-line comment block citing
  the cutover rationale and commit `1849f2a`.
- **Advisory — `json-log-formatter` not propagated**: 8 of 9 service
  `requirements.txt` files were missing it (the `--no-deps` install in each
  Dockerfile strips the contracts dep). Added `json-log-formatter>=1.1` to
  all 8 files with a 2-line comment per file; documented the propagation
  policy in `libs/contracts/pyproject.toml`'s new `# NOTE:` block; removed
  the now-redundant trailing `json-log-formatter` argument from
  `apps/ingest-gmail/Dockerfile`'s `pip install` line.
- **Advisory — `apps/dlq_consumer/requirements.txt` "symmetry" comment**:
  the "kept for symmetry with the dependency-declaration pattern in other
  services" rationale was factually wrong (no other service lists
  `contracts`). Dropped the redundant `contracts` line entirely; the file
  now matches the structural pattern of the other 7 service files.

Re-verification after gap-closure: `pytest tests/ -q` → 302 passed / 34
skipped / 0 failed. Tight reviewer pass on the final fix returned PASS with
no blockers. 07-01-SUMMARY.md written
(`.planning/phases/07-ops-cutover/07-01-SUMMARY.md`).

### Still pending / known gaps (M1)

- Uvicorn access logs remain plain text; application logs are JSON. Documented
  as a known gap in `docs/ops/logging.md`. (Triage via log-formatter middleware
  when needed.)
- DLQ "bounded depth" is implemented as a consecutive-message threshold, not
  a live queue-depth probe. Documented in the worker docstring.
- Bare `pytest` skips `db_live` tests unless `INFOTRIAGE_TEST_DSN` is set
  (06-05's safety gate, intentional; remember to set the env var before
  exhaustive regression runs).

### Next

- Stage explicit file paths for the milestone commits (do NOT use `git add .`):
  - commit 1 (code) — apps/{dlq_consumer/*,triage/worker.py,...} +
    docker-compose.yml + libs/{contracts/_logging.py,contracts/__init__.py,...}
    + libs/ingest_common/trigger.py + ops/Makefile + 8 requirements.txt +
    .env.example cleaner + Dockerfile ingest-gmail cleanup + README.md + 4
    spec/ADR refs + docs/superpowers/spec/... + docs/adr/ADR-008 + 4 new
    tests + tests/baselines/triage_sample_baseline.txt
  - commit 2 (planning files) — 07-01-SUMMARY.md (new) + ROADMAP.md checkbox
    flip (already in working tree) + STATE.md close-out (this update).
- DO NOT push (`main` is 17 commits ahead of origin/main already; a push is an
  explicit operator action).
- M1 ship decision: ship M1 foundation now, OR continue straight into Phase 8
  (Entity resolution) per the original ROADMAP pipeline. Either is defensible;
  if going to Phase 8, address backlog 999.3 (cross-language entity linking
  recalibration) first.

## Session: 2026-07-11 — Phase 6 UAT bug fix: `digest.line()` `or` short-circuit

### Just-completed

- **Root-caught renderer regression in `apps/brief/renderer.py`.** The
  `render_brief()` CCIR-iteration path called `digest.line()`
  (`f"- {v.get('why') or v['title']}..."` from `apps/triage/digest.py`),
  which short-circuits `title` (and silently drops `score`) whenever
  `why` is truthy. Visible in the brief app as `- <why>  [les](<url>)`
  under any CAT_II/ROUTINE section.

- **Trigger:** re-running the test suite after the COP/CIP view-filter
  work landed. `tests/test_brief_consumer.py::test_process_verdict_renders_default_cop_cip_files`
  failed with `AssertionError: assert 'COP Item' in '# InfoTriage · SAB\n_1 saker · ~10 min_\n\n## FFIR-1 · Norsk forsvar & sikkerhetspolitikk\n- Test why  [les](http://example.com)\n'`
  — note the missing `**[9] COP Item**` prefix.

- **Fix:** replaced the single `lines.append(_digest_line(lead, extra))`
  call with inline formatting (matches the existing CAT_I section's
  style: flag + score + title + why + extra + url). Also deleted
  pre-existing dead code `_group_by_ccir()` (defined but never called;
  return shape was broken — it returned a `dict` over a concatenated
  key seq).

- **Regression test added:** `tests/test_brief_renderer.py::TestRenderBriefIncludesAllItemFields`
  — two test methods asserting title/score/why all appear for CAT_II
  items, and title+score for `Routine` (no-CCIR) items.

- **Live proof confirmed:** rendered a CAT_II item with
  `why="Krigsøkonomi under press"`, `title="Russland varsler nye
  sanksjoner"`, `score=7` through the live `render_brief()` path.
  Output: `## PIR-1 · Russland / Ukraina\n- **[7] Russland varsler nye
  sanksjoner** · Krigsøkonomi under press  [les](http://example.com)` —
  all three fields present.

- **Full pytest suite:** 280 passed, 34 skipped.
- **Live UAT re-confirmed:** `uat_test6_cluster_threshold.py` and
  `uat_test8_semantic.py` both pass after the fix.

### Next

- Continue **Phase 6 UAT** (Tests 4, 5, 7, 9 still pending live
  verification — the renderer fix unblocks them, but the live
  republish-to-q.brief / vault-mount / email-in-vault checks still
  need to be run end-to-end).

- Commit the uncommitted view-filter pipeline (consumer.py / main.py
  / vault_writer.py / html_renderer.py) + TESSOC taxonomy work
  (sab_html.py / triage_score.py / ccir.md per ADR-010) + UAT scripts
  (uat_test6, uat_test8, seed_sample_data) as a separate focused
  milestone commit.

## Session: 2026-07-10 — SAB UI polish + FreshRSS/NewsAPI ops

### Just-completed

- **SAB UI refinements**: source status card added (upper-right, OPML-based, green/red per source)
  and empty CCIR slides hidden while the Alle BLUF slide remains visible.

- **FreshRSS ops**: imported `apps/opml/feeds.opml` into the `admin` account via the FreshRSS CLI.
- **NewsAPI rate-limiting**: created and ran `scripts/set_newsapi_ttl.py`; all 6 NewsAPI feeds now
  have a 3-hour TTL (10,800 s), keeping the free-tier request count under the 100/day cap.

- **Documentation**: manual FreshRSS TTL steps documented in `apps/ingest/RSS_BRIDGE_NOTES.md`
  (including the automated helper script).

- **CI coverage**: added `tests/test_set_newsapi_ttl.py` to validate the script's syntax and
  basic structure.

### Next

- Resume **Phase 6 UAT** (cold-start smoke test and remaining UAT items from `.planning/phases/06-brief-app/06-UAT.md`).

## Session: 2026-07-08 — 06-05 executed (test-DSN safety, gap closure)

### Just-completed

- **06-05 COMPLETE** (commits `2d6c255`, `6fecb46`, `f92f8ed`): db_live tests now resolve their
  DSN exclusively from **INFOTRIAGE_TEST_DSN** (no INFOTRIAGE_PG_DSN fallback, no prod literal);
  unset ⇒ all 26 db_live tests skip. Always-run guard `tests/test_dsn_safety.py` fails on any
  prod-port (22000) DSN/probe under tests/. `docker-compose.test.yml` = tmpfs pgvector on :22062.
  **Bare `pytest` is now safe** — verified: no prod connection attempted with DSN unset;
  26/26 db_live green against a pristine compose test DB.

- Deviations (Rule 3, both in `f92f8ed`): `001-schema.sql` now uses `CREATE EXTENSION vector
  WITH SCHEMA public` (was landing in infotriage schema on fresh DBs → register_vector failed);
  db_live fixtures bootstrap `init_schema()` before TRUNCATE/`__enter__` (fresh-DB safe).

- Deferred (pre-existing, `deferred-items.md`): `tests/integration/test_clustering_integration.py`
  hardcodes 127.0.0.1:5432 (not prod) with no skip guard; 4 rabbitmq test failures (contention).

### Decisions recorded

- db_live DSN source = INFOTRIAGE_TEST_DSN only; reachability parsed from the DSN, never hardcoded.
- `CREATE EXTENSION vector` must specify `WITH SCHEMA public` — search_path-relative install
  breaks pgvector adapter registration on default-search_path connections.

- db_live fixtures must run init_schema() before TRUNCATE and before entering the store context.

### Next

- Execute **06-06** (store read-path rollback + idle_in_transaction_session_timeout backstop).

## Session: 2026-07-08 — Phase 6 UAT run + SIR-3 live add + new gap plans

### Just-completed

- **06-UAT complete (agent-run, live): 4 pass / 1 issue (root-caused).** Clustering
  (5-source FFIR-3 merge), vault writer (7 item files + obsidian-sab.md), email-in-vault,
  CLUSTER_THRESHOLD validation — all verified against real containers.

- **Root cause of "empty SAB" found forensically**: db_live test fixtures TRUNCATE the
  PRODUCTION Postgres :22000 (DEV_DSN in test_store_integration/test_triage_enrichment/
  test_store_contract) — every pytest run wipes live data. Plus triage worker's
  PostgresStore read paths leave connections idle-in-transaction (observed 8.5h; a queued
  fixture TRUNCATE then blocked all reads). Unblocked via pg_cancel_backend + triage restart.

- **DB repopulated live**: POST /run to ingest-imap/:22010 + ingest-youtube/:22011 →
  108 articles → 108 enrichments → 108 embeddings → SAB rendering 108 items.

- **Found + fixed: triage container had NO ccir.md** (CCIR_PATH → /ccir.md not in image;
  scorer used 76-char fallback stub). Added `./ccir.md:/ccir.md:ro` mount (committed e6fab90).

- **SIR-3 (NATO-toppmøtet i Ankara) added to ccir.md** + both CCIR_ORDER copies
  (digest.py, sab_html.py — DRIFT-1 duplication is real; seeds SEED-001/SEED-002 planted).
  Live-verified: synthetic summit article scored `SIR-3|II|8|read`, renders in SAB SIR-3
  section. Commit ef2ae38.

- **Committed stranded 06-03/06-04 patchset** (e6fab90) — was uncommitted from 07-07 session.
- **Gap-closure plans written + checker-verified**: 06-05 (test-DSN safety: require
  INFOTRIAGE_TEST_DSN, dsn-safety guard test, ephemeral test Postgres on 22062) →
  06-06 (store read-path rollback + idle_in_transaction_session_timeout backstop). Ready:
  `/gsd-execute-phase 06 --gaps-only`.

### Watch out for

- ~~NEVER run bare `pytest` until 06-05 lands~~ **RESOLVED 2026-07-08**: 06-05 landed — db_live
  tests skip unless INFOTRIAGE_TEST_DSN is set; guard test blocks prod-port reintroduction.

- /sab default path caches sab.html for 24h (D-01) — `rm data/digests/sab.html` or
  `?window=24h` to see fresh data.

## Session: 2026-07-07 — Phase 6 gap-closure patchset (06-03, 06-04)

### Just-completed

- Addressed code-review findings from Phase 6 gap closure:
  - `vault_writer.py` now uses `contracts.to_frontmatter()` instead of hand-rolled YAML.
  - `brief` compose service now has `INFOTRIAGE_VAULT_PATH=/vault/brief-outbox`, `CLUSTER_THRESHOLD`, `VAULT_INCLUDE_EMAIL`, and a writable Obsidian brief-outbox mount.
  - `CLUSTER_THRESHOLD` is validated in `main.py` and passed into `run_consumer()` → `process_verdict()` → `render_brief()`/`render_cluster()`.
  - Missing embeddings now pass through as singleton clusters instead of silently disappearing from clustered sections.
- Added regression tests:
  - codec-parseable Obsidian front matter, including punctuation/multiline fields.
  - default inclusion of `imap://` email-sourced items in the vault projection.
  - no-embedding singleton pass-through in in-memory clustering.
- Focused validation passed: `python -m pytest tests/test_brief_clustering.py tests/test_brief_renderer.py tests/test_vault_writer.py -q` → 43 passed; `python -m pytest tests/test_vault_writer.py -q` → 8 passed.

### Still pending

- Live Postgres/container verification for 06-03: prove at least one real enrichment cluster merges through the production fetch → render path.
- Live compose verification for 06-04: run `brief` with a real `OBSIDIAN_VAULT_PATH` and confirm files land in the host vault brief-outbox.
- No commit created in this Codex session; user did not request committing.

## Session: 2026-07-06 — Integrity fix: stranded 06-02 work committed

### Just-completed

- **Committed stranded 06-02 implementation.** Commit `3047116` ("plan 06-02 complete")
  contained only PLAN.md — the actual code (apps/brief/clustering.py, main.py/renderer.py
  wiring, tests/test_brief_clustering.py) plus 06-02-SUMMARY.md and 00-07-SUMMARY.md sat
  uncommitted in the working tree after a session death. Verified tests green before
  committing.

- Left untracked on purpose: `.env.bak-channels` (env backup — never commit),
  `apps/opml-health/` (orphan side work, no plan/summary claims it — needs triage),
  `.planning/research/` (only a .cache dir).

- Phase 6 has no VERIFICATION.md — running verification next (Route V.missing).
- **Verification result: gaps_found (1/3 success criteria).** 06-VERIFICATION.md written.
  Gap 1 (real bug): production path never joins `infotriage.embeddings` — renderer.py
  defaults embedding to `[0.0]*4`, cosine distance always 1.0, clustering never merges;
  pgvector `cluster_items()` is dead code; `CLUSTER_THRESHOLD` validated in main.py but
  hardcoded 0.75 used in renderer.py. Gap 2: Obsidian vault-writer does not exist —
  06-SPEC.md descoped it without amending ROADMAP success criteria (commit d0ab4ac's
  "Obsidian vault-writer" claim is false). Gap 3: SC3 Obsidian half blocked by gap 2.
  Known test-infra issue: rabbitmq-marker tests need triage/brief containers stopped
  (live consumers on q.triage/q.brief eat test messages) — contention, not code defect.

## Session: 2026-07-05 (resume) — Phase 6 recovery: false SUMMARY fixed, Wave 2 delivered

### Just-completed

- Resumed from HANDOFF.json + .continue-here.md (phase 6 paused at task 3/3 after a
  prior run wrote a SUMMARY with false Wave 2 completion claims — stalled bg executor).

- **Corrected 06-01-SUMMARY.md** to verified disk state; committed Wave 1 (renderer,
  consumer, tests) which was sitting untracked (`eec345d`).

- **Added SabPublished YAML-codec roundtrip test** (plan Task 1 residual; note: repo
  convention is `tests/test_contracts.py`, plan's `libs/contracts/tests/` never existed).

- **Wave 2 delivered + live-verified** (`316a20f`, `01ed73c`, `af9dcac`): main.py FastAPI
  (:22040, staleness gate D-01, ?window D-10, ?mode=list), html_renderer.py (delegates to
  sab_html.build_html — template imported not copied, D-12), Dockerfile (ships ccir.md for
  digest.py's import-time sync guard), compose service `brief` (127.0.0.1:22040, D-14).

- **Found + fixed 4 latent Wave 1 consumer bugs during live verify** (consumer had never
  run against real infra): enrichment SQL missing JOIN to articles (title/summary/source/
  url live there — UndefinedColumn crash); `_fetch`/`_render_bluf_all_sections` were
  `async def` run via `to_thread` → returned coroutines (bluf.md write TypeError); no
  rollback after failed statements (poisoned the shared psycopg conn); digests dir
  split-brain (consumer wrote $BLOB_ROOT/digests, server served $DIGESTS_DIR).

- **Added `PostgresStore.cursor()`** — store had no read-cursor API at all.
- **E2E verified**: republished verdict.ready via rabbitmqadmin → all 4 digests
  atomically rewritten (incl. bluf.md) → sab.published event landed in q.notify.
  Container healthy, /sab 200, cached serve <2ms.

### Decisions recorded

- **Never write SUMMARY.md before verifying claimed artifacts exist on disk** — run
  `git status` + `ls` first. The false 06-01-SUMMARY came from a run that trusted plan
  frontmatter over reality.

- **`asyncio.to_thread(fn)` requires plain `def`** — an `async def` passed to to_thread
  returns an un-awaited coroutine that silently flows into downstream code.

- **Phase 6 remaining scope → plan 06-02**: pgvector clustering.py + window.py
  incremental BLUF (D-05/D-06/D-08/D-11). Do NOT mark phase 6 complete.

## Session: 2026-07-02 (resume) — youtube ingest fixes (max_n + tab over-fetch)

### Just-completed

- Resumed from HANDOFF.json (between-phases pause, Phase 5 closed). User AFK at the
  pending question, so proceeded with the recommended small fix.

- **Fixed `youtube_ingest.py` max_n key mismatch** (HANDOFF task 11): `ingest()` read
  `c.get("max_per_run", 3)` but `YT_CHANNELS` uses `"max_n"` — per-channel limits were
  silently ignored. Added regression test (verified it fails on pre-fix code via stash).

- **Root-caused + fixed the yt-dlp over-fetch** (HANDOFF task 12): bare channel-root URLs
  expand to up to 3 tab playlists (Videos/Shorts/Live) and `-I 1:N` applies PER TAB —
  NATO returned 15 for max_n=5 (3 per tab × 3 tabs, confirmed via `%(playlist_title)s`).
  Fixed by pinning URLs to `/videos` unless a tab is already named. Also surfaced yt-dlp
  non-zero exits to stderr (were swallowed as "empty channel"). Commit `0c6d75e`,
  redeployed, verified live: NATO now returns exactly 5.

- **Found 3 dead/broken channels in `.env` `YT_CHANNELS`** (not fixed — editorial/user
  decision): `@bellingcat` → 404 (real channel now at `@BellingcatOfficial`, verified),
  `@NRKnyheter` → 404 (`@NRK` exists but is general NRK, not Nyheter), `@theisw` → 200
  on curl but yt-dlp lists NO tabs/videos at all (channel appears contentless via API).

- Legacy `apps/ingest/yt_to_atom.py` still uses `max_per_run` internally — left alone
  (not deployed in docker-compose, internally consistent).

## Session: 2026-07-02 — Phase 5 COMPLETE (05-05 Task 3 closed out)

### Just-completed

- **05-05-PLAN.md Task 3 (Shadow-run parity gate + Fever cutover, R6)**: Redeployed the
  05-03 `on_message` header fix (`89d6496`, committed but not yet deployed at session start —
  the prior session's HANDOFF.json/.continue-here.md were stale on this point). Found and fixed
  a second real bug: `docker-compose.yml`'s `LLM_BASE_URL` was silently reading the host `.env`'s
  `127.0.0.1:8000` value via Compose's automatic `.env` substitution instead of the intended
  `host.docker.internal` container default — every embed call failed with `Connection refused`.
  Hardcoded the container-only URL (commit `d9714fc`). Populated enrichment rows by republishing
  `item.ingested` via `rabbitmqadmin` for existing `infotriage.articles` rows (43 total, 0 DLQ
  failures). First `shadow_run.py` run showed 6/15 matching — diagnosed as a methodology bug, not
  a scoring bug: 9-29 of the rows were dedup short-circuits (D-01, `bucket=skip`, `why="duplicate
  of <id>"`, no LLM call) that a naive rescore always disagrees with. Fixed `shadow_run.py` to
  exclude dedup rows from the parity count (commit `f7430ef`). Corrected run: **14/14 genuinely-
  scored buckets matched (100%)** — parity verdict MET. Verified the host crontab fever entry was
  already absent (`crontab -l` → "no crontab for vidarbrevik") — R6's cutover end-state already
  satisfied, no removal action needed. **Phase 5 (Triage app) now 5/5 plans complete.**
  Commits: `d9714fc`, `f7430ef`, `1849f2a` (SUMMARY + ROADMAP + HANDOFF/continue-here cleanup).

### Decisions recorded

- **docker-compose.yml container env vars must never use `${VAR:-default}` for a var name that
  also exists in host `.env`** — Compose auto-loads the project `.env` for substitution, so a
  host-scoped value (e.g. `LLM_BASE_URL=127.0.0.1` for host scripts) silently overrides the
  container-appropriate default. Hardcode container-only values instead of relying on the
  fallback pattern when the var name collides with a host-side config need.

- **shadow_run.py / any future parity-style comparison must account for dedup short-circuits** —
  comparing a dedup-skip (no LLM call) against an independent rescore (which has no dedup
  awareness) measures dedup coverage, not scoring agreement. Exclude those rows from parity
  counts and report them separately.

## Session: 2026-06-27 — Phase 1 COMPLETE (01-03 stale doc fixes, SPEC R6)

### Just-completed

- **01-03-PLAN.md (Stale doc fixes, SPEC R6)**: Corrected three stale claims in REQUIREMENTS.md (C-9 yt_to_atom: "scaffolded" → "implemented" + apps/ingest/ path; C-13 imap_to_atom: same; A-5 PMESII: [PLANNED] → [LIVE] with Phase 1.5 archive ref) and updated README.md run-commands + Bridges section to use apps/triage/, apps/ingest/, apps/opml/ paths from plan 01-02 restructure. Commits b9a1606 (REQUIREMENTS.md), 70e5a25 (README.md).
  - Decision: A-5 set to [LIVE] — PMESII/TESSOC enrichment confirmed shipped in Phase 1.5
  - Decision: C-9/C-13 kept [SPIKE] — runtime blockers (yt-dlp + transcribe; IMAP creds) still pending
  - Planner-script bug noted: `grep 'opml/feeds.opml'` matches apps/opml/feeds.opml substring; spirit of check confirmed satisfied

## Session: 2026-06-27 — Phase 1 01-02 COMPLETE (monorepo restructure)

### Just-completed

- **01-02-PLAN.md (Monorepo restructure + test migration)**: Re-homed bridge/score/opml into apps/{ingest,triage,opml}. Applied exhaustive 7-expression path-depth fix table (3 expressions RESEARCH/PATTERNS missed: sab_html.py ROOT, gmail_to_atom.py OUT + .env). D-08 wiring: digest.py imports Item from contracts. Root pyproject.toml pytest config (pythonpath replaces all sys.path.insert). Migrated 6 unittest files to pytest functions. **83 tests green** (27 contracts + 56 migrated). Commits c22d10c (pyproject), 9035fe5 (re-home), 8d9ca9d (test migration).
  - Q1 resolved: sab_html.py in apps/triage/ (sibling import forces co-location)
  - Q2 resolved: working.opml moved (git-tracked)
  - Q3 resolved: pyproject.toml chosen over pytest.ini / conftest.py

## Session: 2026-06-27 — Phase 0 COMPLETE (00-07 closeout + teardown)

### Just-completed

- **00-07-PLAN.md (Spike closeout)**: SPIKE-FINDINGS.md consolidated (R1-R5 per-unknown verdicts +
  raw numbers, R4 samples pasted inline, R3/R2 divergence note) + ADR-005..008 written. Then full
  D-06 teardown: `.spike/` deleted (3.1G incl. World Monitor clone/build), pgvector + rabbitmq
  containers/volumes removed. **Phase 0 done** (1/13 phases). Commits 5b5ab32 (artifacts), 379bb7a (teardown).

  - ADR-005: DROP World Monitor (+ Aegis) as engine; BUILD native SP-COP interactive-SAB canvas.
  - ADR-006: entity resolution (pgvector HNSW cosine, threshold 0.85); Phase-8 risk = re-validate on mE5-large.
  - ADR-007: RabbitMQ topology (infotriage.events + 4 keys + DLX/DLQ); Phase 3 use aio-pika.
  - ADR-008: self-hosted Gmail MCP/OAuth2 ingestion.
- **SP-COP design work** (parallel, captured): R5-VERDICT holds the full vision (LOOK/HEADLINES/FOCUS
  modes, known↔unknown + ambient↔focused axes, prior-art incl. Palantir/i2/InfraNodus/Aegis). Sketch
  001 built (winner = HEADLINES: BLUF-first, delta-default, time-aware; LOOK geo half has OSINT layers

  + heatmap wired to timeline). Wrapped into skill `sketch-findings-infotriage`.

### Just-completed (prior — Phase 0 R1-R5)

- **00-06-PLAN.md (R5 COP / World Monitor)**: cloned + built + launched the real WM desktop app
  (oMLX-pinned, cloud keys blank). Operator judged the globe hands-on. **Verdict: DROP WM as
  product/engine; BUILD own interactive-SAB canvas/COP (SP-COP).** WM is an online aggregator with a
  local shell (api.worldmonitor.app backend, own RSS feeds, Convex/Clerk/Vercel); its globe is 100%
  open libs (globe.gl/three-globe MIT, maplibre BSD). WM HAS a CCIR-like concept (SOURCE_REGION_MAP
  AOIs→feeds + source tiers + instability score) — at personal scale InfoTriage's CCIR/CNR = "what I'm
  interested in" + "how urgent," scored vs own ccir.md. **Product vision:** SAB → interactive canvas
  (topics/news/info, globe + panels), NOT a static brief. SP-COP feature wishlist: keep floating
  pickers; add timeline/time-scrubber; add views beyond geo (timeline/topic/entity/list). Build trap
  found: `tauri build` ships broken app — must use `desktop:build:full`. Commit da77120 (Task 1) + verdict.

### Just-completed

- **00-05-PLAN.md (R4 Wiki-LLM)**: local qwen36 (oMLX, DGX Spark unavailable) synthesizes coherent
  4-section citation-grounded intel-wiki pages. Standing NATO page (5 items, 5 grounded cites) +
  on-demand Venezuela article (17 items gathered across en/no/ru via R3 entity_links, 8 cited).
  Grounding PASS both (hard-exit on ungrounded ref). **Verdict PARTIAL** — synthesis mechanism GO,
  but cross-language synthesis **drops Russian sources** (all 7 TASS items gathered, none cited).
  This directly motivates backlog 999.1 (on-demand translation). Commit 232929e + verdict.
  Deviation: max_tokens 800→1100 (800 truncated section 4).

### Just-completed (R2, this session)

- **00-03-PLAN.md (R2 Norwegian Dedup Bake-off)**: mE5-large vs bge-m3 threshold sweep on 24-row
  hand-labeled corpus (13 yes / 11 no). bge-m3 disqualified (collapse_rate < 0.05 all thresholds).
  **mE5-large chosen @ threshold 0.84** (collapse_rate 0.783, control_overmerge 1). No pair cleared
  both bars — control set too topically narrow. Verdict: PARTIAL — mechanism + model GO; threshold
  needs held-out corpus in Phase 5. Commit: d5aacee. Input `title + summary[:512]`; `passage:`/`query:` prefixes.

### Just-completed (prior session)

- **00-04-PLAN.md (R3 Entity Resolution)**: pgvector cosine entity resolution proven via bge-m3
  1024-dim embeddings + HNSW index. 285 entities, 599 entity_links from 144-item corpus.
  NATO → 1 entity_id across 5 TASS items (all lang=ru). Control test PASS (Trump≠Putin).
  Verdict: PARTIAL — mechanism GO, cross-language coverage limited by corpus date (no NATO
  in NRK/BBC on 2026-06-25). Commit: 5c17666 (R3-VERDICT.md).

- **00-02-PLAN.md (R1 RabbitMQ Topology)**: InfoTriage AMQP topology proven on RabbitMQ 3.13 /
  pika 1.4.1. DLX-first declaration (infotriage.dlx → infotriage.dlq → infotriage.events → 4 primary
  queues). Publish→consume round-trip passed. All 4 event-type publisher confirms passed. Poison
  nack (requeue=False) dead-lettered to infotriage.dlq (depth=1). Verdict: GO.
  Commit: 39711a0 (R1-VERDICT.md).

- **00-01-PLAN.md (Spike Infra + Corpus)**: Ephemeral RabbitMQ (22060/22061) + pgvector (22062)
  containers running and healthy. 144-item NRK/BBC/TASS corpus fetched via defusedxml into
  `.spike/items.json`. `.spike/` gitignored. All infra prerequisites for R1-R5 now in place.
  Commits: 14ead5e (infra), f317cd4 (fetcher).

### Decisions recorded

- **R2 → mE5-large @ 0.84**: bge-m3 disqualified for Norwegian dedup (collapse_rate < 0.05).
  mE5-large locked as Q5 embedding model for ADR / Phase 5. Threshold 0.84 is a starting point —
  PARTIAL because no (model,threshold) cleared both bars on this narrow single-day corpus; Phase 5
  must recalibrate on a held-out corpus with genuinely off-topic controls.

- **R3 PARTIAL**: pgvector HNSW cosine entity resolution mechanism GO; cross-language NATO coverage
  limited by corpus date. Schema (entities+entity_links+HNSW), threshold 0.85, bge-m3 1024-dim
  validated for ADR-006 / Phase 8.

- **HNSW over IVFFlat**: No minimum rows needed; correct for small corpora and incremental inserts.

- **LINK_THRESHOLD=0.85**: Separates distinct persons (Trump/Putin sim ~0.72) while merging entity
  variants (NATO/НАТО sim ~0.92). Confirmed empirically on R3 corpus.

- **bge-m3 1024-dim CLS-pool vectors**: Validated for multilingual entity resolution; primary
  candidate for Phase 5/8. R2-VERDICT.md needed to confirm bake-off result.

- **torchvision nightly incompatibility (0.24.0.dev vs torch 2.11.0)**: Phase 5 env must resolve
  torch/torchvision version mismatch; spike used XLMRobertaModel direct import with mock.

- **R1 GO**: InfoTriage AMQP topology (topic exchange infotriage.events, 4 routing keys, DLX
  infotriage.dlx, DLQ infotriage.dlq) proven on RabbitMQ 3.13 — proceed to ADR-007.

- **pika 1.4.1 confirm API**: `channel.confirm_delivery()` method call; `basic_publish()` raises
  `NackError`/`UnroutableError` on rejection (no `wait_for_confirms()` method). Phase 3 must use
  `aio-pika` with `connect_robust()`.

- `defusedxml.ElementTree` exclusively for any network-sourced RSS/XML (stdlib parser forbidden — XXE, T-00-01-XXE).
- Spike port band: 22060 (RabbitMQ AMQP), 22061 (RabbitMQ mgmt), 22062 (pgvector Postgres); credentials `spike`/`spike`.
- `.spike/` gitignored wholesale; spike config files committed via `git add -f`; ephemeral data (items.json) not committed.

### Pending — Phase 00 plans

- 00-07-PLAN.md: Spike closeout (ADRs + SPIKE-FINDINGS.md + teardown) — all of R1-R5 now done; ready to run

### Infrastructure corrections (2026-06-25)

- **No Ollama** — removed from all docs and configs. Stack is oMLX (Mac) + vLLM (Spark) only.
- **DGX Spark now active** — vLLM serving qwen 80B at `http://192.168.10.2:8000/v1`, key=EMPTY. Spark has no internet; models must be transferred from Mac.
- **Embedder**:
  - Mac: `intfloat/multilingual-e5-large` (1024-dim) via oMLX
  - Spark: `Alibaba-NLP/gte-Qwen2-7B-instruct` (7B) via vLLM
- **New source — The Telegraph (UK)**: Added for Ukraine coverage. RSS blocked (bot detection). Recommended path: subscribe to Telegraph Ukraine newsletter → ingest via IMAP bridge (`bridge/imap_to_atom.py`). No new code needed until Phase 4.

### Carried-over open questions

- Q1 World Monitor CCIR/SAB coverage → **R5 spike** (still open).
- Q5 embedding model (bge-m3 vs mE5-large) → **DECIDED: mE5-large @ 0.84** (R2, PARTIAL — recalibrate Phase 5).

## Session: 2026-06-30 — Phase 5 Wave 1 in progress (05-01 closed out)

### Just-completed

- **05-01-PLAN.md (Store extension)**: Commits (`0837fb0` test, `a98a5e0` migration, `eafc031`
  implement) landed in a prior session that ended before SUMMARY.md was written — execute-phase
  safe-resume gate caught the gap on resume. Verified green (12/12 tests, inmemory+db_live
  postgres; grep clean for forbidden `ADD CONSTRAINT IF NOT EXISTS`/f-string SQL) and closed out
  manually: wrote 05-01-SUMMARY.md, flipped ROADMAP.md checkbox via `roadmap.update-plan-progress`.
  006-enrichment.sql + put_enrichment/get_enrichment/put_embedding/find_near_duplicate now live on
  Protocol+Postgres+InMemory.

## Session: 2026-06-30 — Phase 5 Wave 1 complete (05-02 closed out)

### Just-completed

- **05-02-PLAN.md (Worker prerequisites)**: Added `RabbitMQBus.consume(routing_key, handler,
  prefetch_count=1)` — a persistent callback consumer (sibling to drain-only `subscribe()`,
  reuses `self._queues` keyed by routing_key and the existing topology; raises `ValueError` on
  an unknown routing key). Verified end-to-end against live RabbitMQ `:22001`
  (`tests/test_bus_consume.py -m rabbitmq`, 2/2 passed; existing `test_bus_rabbitmq.py` 5/5
  still green). Also applied D-02: `apps/triage/triage_score.py` no longer caches `ccir.md` at
  import time — `score_item()` now calls `load_ccir()` as its first statement and the prompt
  f-string reads the local `{ccir}`, so operator edits to `ccir.md` take effect on the very
  next scoring call (D-5). Regression test `tests/test_triage_score_hotread.py` proves this via
  monkeypatched `CCIR_PATH` + a prompt-capturing `llm` stub. TDD throughout (RED commits
  `e049a71`, `1d3b2db`; GREEN commits `a1e05e1`, `260d7b5`). 210+7 tests green project-wide, no
  regressions. Both Wave-1 worker prerequisites (05-03 depends on) now in place.

## Session: 2026-06-30 — Phase 5 Wave 2 complete (05-03 closed out)

### Just-completed

- **05-03-PLAN.md (Triage worker)**: Built `apps/triage/worker.py`, the D-01 event-driven
  entry point. `process_item(item_id, store, bus, *, embed, score)` is the async testable
  core: `get_item` → mE5-large embed + `find_near_duplicate` dedup check (LLM call skipped
  entirely on a hit, `bucket=skip`/`why="duplicate of <id>"`) → `score_item()` against
  `ccir.md` (non-dup path) → `clamp_score` to `[0,10]` → `put_enrichment` (raw vocabulary)
  → `put_embedding` (always, dup or not) → `VerdictReady` (mapped vocabulary via
  `map_cnr`/`map_bucket`) → `bus.publish("verdict.ready", ...)`. Enrichment write commits
  before publish in every path; a `put_enrichment` failure propagates so `on_message`'s
  `message.process()` nacks instead of acking (R2/R5 prohibition). Each blocking call runs
  via `asyncio.to_thread` individually (not the whole pipeline as one block) so
  `bus.publish` always executes on the consumer's own event loop — avoids an aio-pika
  cross-event-loop bug that a naive "wrap process_item in one to_thread" reading of the
  plan would have introduced. `_handle_health`/`run_health_server` (D-04) serve a
  liveness-only `/health` alongside the consumer under `asyncio.gather` (D-03). TDD
  throughout (RED commit `519ea87`; GREEN commit `30d1baa`; health test `db3d714`). 9/9 new
  tests green, 219 project-wide, no regressions.

## Session: 2026-07-01 — Phase 5 Wave 3 complete (05-04 closed out)

### Just-completed

- **05-04-PLAN.md (Triage container)**: Containerized `apps/triage/worker.py` as the
  `infotriage-triage` service on `127.0.0.1:22030`. `apps/triage/Dockerfile` mirrors
  `apps/ingest-imap`'s local-lib install pattern (`COPY libs/contracts`/`libs/store` →
  `pip install --no-deps` → app `requirements.txt` → app source → non-root `USER triage`
  → `CMD ["python", "worker.py"]`), no credential ARG/ENV baked in. `docker-compose.yml`
  triage stanza adds a python-urllib healthcheck (no curl in `python:3.12-slim`),
  `extra_hosts host.docker.internal:host-gateway` for the host oMLX endpoint (ADR-004 —
  local only), and `depends_on` postgres+rabbitmq with `condition: service_healthy`.
  Task 3's blocking live-verify checkpoint confirmed `/health` → 200, non-root user,
  no DSN leak in logs, and `connect_robust` auto-reconnect surviving a RabbitMQ
  stop/start (re-confirmed independently in this continuation session via
  `rabbitmqctl list_connections`/`list_queues` showing the worker's connection still
  `running` and `q.triage` with an active consumer, days after the original test).
  Operator approved. Commits `aff9373` (Dockerfile/requirements.txt), `9910278`
  (docker-compose.yml).

  - Deviation (Rule 3): `requirements.txt` needed `feedgen`/`pydantic`/`PyYAML` beyond
    the plan's literal `aio-pika`/`psycopg[binary]`/`pgvector` — `libs/store` and
    `libs/contracts` are installed `--no-deps` and import these at module level.

  - Known gap (non-blocking): `intfloat/multilingual-e5-large` is not yet registered
    on the host oMLX instance — `worker.py`'s `get_embedding()` will 404 on a real
    end-to-end run until that model is set up. Tracked as a Phase 5 follow-up.

## Session: 2026-07-01 — Phase 5 Wave 4 (05-05) BLOCKED on Task 3

### Just-completed

- **05-05-PLAN.md Tasks 1-2**: `scripts/shadow_run.py` built (reads `infotriage.enrichment`
  joined to `infotriage.articles`, re-runs `score_item()` standalone, prints side-by-side
  bucket parity table + `>= 10` verdict — commit `49f1822`). README.md updated to document
  the triage container (`docker compose up -d triage`, port 22030) as the scoring path;
  fever_triage.py run-commands/crontab line marked retired, file itself preserved for
  `digest.py` imports (commit `e846d94`).

### Blocked — Task 3 (shadow-run parity checkpoint + Fever cutover)

Two independent, pre-existing blockers, confirmed live (not guessed):

1. **Embedder gap (already known, from 05-04)**: `intfloat/multilingual-e5-large` is not
   registered on the host oMLX instance. Reproduced directly: `POST host.docker.internal:8000/v1/embeddings`
   from inside the `infotriage-triage` container → clean `404`. Docker networking itself is
   fine (`host.docker.internal` resolves and `/health` returns 200) — this is purely a
   missing-model-registration issue on the host, not a bug in 05-04's compose config.

2. **New finding — `infotriage.articles` has 0 rows.** This contradicts this STATE.md's
   earlier note about "111 existing articles" (stale — likely referred to the old `.spike/`
   corpus from Phase 0, torn down before Phase 5). `infotriage-postgres` has a persistent
   volume (`./data/postgres`) and has been up ~14h; `ingest-youtube`/`ingest-imap` have been
   up ~41-42h and `ingest-youtube` shows multiple successful `POST /run` (200 OK) calls from
   the scheduler in that window, yet zero rows landed in `infotriage.articles`. Root cause
   NOT diagnosed — could be no-new-content-found each run, a silent `persist_and_publish`
   failure, or a Postgres data reset independent of Phase 5. Needs separate investigation
   (not attempted this session — operator chose to defer and investigate later).

Even if the embedder were fixed today, Task 3 still can't proceed with zero source articles.
Both must be resolved before `/gsd-execute-phase 5` can complete Task 3 (or `--gaps-only`/manual
close-out once resolved). Task 3 is NOT committed, no SUMMARY.md was written, ROADMAP.md still
shows 05-05 incomplete — this is intentional, do not mark it done.

### Follow-up — embedder gap RESOLVED (host-only change, no repo commit)

Registered `intfloat/multilingual-e5-large` on the local oMLX instance (standard HF safetensors —
oMLX's `mlx-embeddings` backend natively supports the `XLMRobertaModel` architecture, no MLX
conversion needed). Steps: `hf download intfloat/multilingual-e5-large --local-dir
~/.omlx/models/multilingual-e5-large`, stripped the redundant `onnx/`/`openvino/`/`pytorch_model.bin`
export formats oMLX doesn't use (8.9GB → 2.1GB), killed the running server (PID tracked in
`~/.omlx/claude-mlx.serve.pid`; `omlx-cli restart` doesn't recognize servers it didn't launch
itself, so used the same kill+`omlx-ensure-server` path the Mac already relies on), let it come
back and rescan `~/.omlx/models`.

**Model-id resolution note:** the directory is named `multilingual-e5-large` (no `intfloat/`
prefix — oMLX's model-dir discovery uses the bare leaf directory name as the model_id). This
still works with `worker.py`'s literal `"model": "intfloat/multilingual-e5-large"` request
because oMLX's `resolve_model_id()` strips an `org/` prefix and matches the remainder against
registered entries (`engine_pool.py` line ~343) — confirmed working, not just directory-inferred.

Verified live: `POST /v1/embeddings` with the exact body `worker.py`'s `get_embedding()` sends
returns `200`, 1024-dim vector — reproduced both from the host (4.7s cold) and from inside
`infotriage-triage` via `host.docker.internal:8000` (0.5s warm). Existing models
(`qwen36-ud-4bit`, `gpt-oss-20b`, etc.) confirmed still registered post-restart — no regression.

**Remaining blocker for 05-05 Task 3:** `infotriage.articles` still has 0 rows (see above) —
untouched this session, still needs separate investigation.

## Session

**Last session:** 2026-07-11T20:23:29.221Z
**Stopped at:** Phase 06 complete incl. gap-closure 06-07 (VAULT_INCLUDE_EMAIL url-scheme fix); clean stop
**Resume file:** .planning/phases/07-ops-cutover/07-01-PLAN.md

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 02 P01 | 10 | 3 tasks | 10 files |
| Phase 02 P03 | 732 | 3 tasks | 4 files |
| Phase 03 P01 | 21 | 7 tasks | 5 files |
| Phase 05 P02 | 12min | 2 tasks | 4 files |
| Phase 05 P03 | 22min | 3 tasks | 3 files |
| Phase 05 P04 | continuation | 3 tasks | 3 files |
| Phase 06 P05 | 15min | 2 tasks | 7 files |
| Phase 06-brief-app P07 | 3min | 2 tasks | 2 files |

## Decisions

- [Phase ?]: register_vector in init_schema must run AFTER DDL
- [Phase ?]: postgres fixture requires TRUNCATE before each test for isolation
- [Phase ?]: DLX infotriage.dlx declared before primary queues (prevents 406 PRECONDITION_FAILED)
- [Phase ?]: x-dead-letter-routing-key=dead for all primary queues routes nacked messages to infotriage.dlq
- [Phase ?]: aio-pika async transport for RabbitMQ bus with connect_robust auto-reconnect and topology migration handler
- [Phase ?]: consume() added as a sibling method on RabbitMQBus only (not BusClient Protocol) per RESEARCH Open Q2; subscribe() untouched
- [Phase 05]: 05-03: process_item runs async with per-call asyncio.to_thread (not a sync function run as a whole via asyncio.to_thread) so bus.publish always executes on the consumer's event loop, avoiding aio-pika cross-event-loop bugs
- [Phase 05]: 05-04: requirements.txt needs feedgen/pydantic/PyYAML beyond aio-pika/psycopg/pgvector — libs/store and libs/contracts are installed --no-deps and import these at module level
- [Phase 05]: 05-04: intfloat/multilingual-e5-large not yet registered on host oMLX — worker.py's get_embedding() will 404 until set up; tracked as a Phase 5 follow-up, non-blocking for 05-04. **RESOLVED 2026-07-01**: registered at ~/.omlx/models/multilingual-e5-large (standard HF safetensors via mlx-embeddings' native XLMRobertaModel support), verified 200/1024-dim from host and from inside infotriage-triage.
- [Phase ?]: 06-07: excluded email by matching r['url'] against _EMAIL_URL_SCHEMES (imap://, gmail://) instead of r['source'] -- source_type isn't available to vault_writer.py's row shape, url-scheme is the reliable in-scope signal
