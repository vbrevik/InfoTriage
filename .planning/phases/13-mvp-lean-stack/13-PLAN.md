---
phase: 13-mvp-lean-stack
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - apps/mvp/poller.py
  - apps/mvp/Dockerfile
  - apps/mvp/requirements.txt
  - docker-compose.mvp.yml
  - ops/Makefile
  - .env.example
  - README.md
  - tests/test_mvp_poller.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "The MVP value chain is: FreshRSS (fetching) -> score against ccir.md -> persist to Postgres -> CAT I push to phone + SAB/digest. FreshRSS stays the fetching engine and reading surface."
    - "No RabbitMQ, no per-adapter containers, no scheduler, no DLQ consumer in the MVP runtime path. The event-driven middle is replaced by one synchronous asyncio loop."
    - "The alerting lane ships unchanged as a library: emitter.handle_verdict_ready with bus=None (verified — the whole claim->throttle->retry->DLX path works synchronously)."
    - "The existing 19-service docker-compose.yml stays intact; the MVP is a separate self-contained overlay (docker-compose.mvp.yml) — nothing is deleted."
  artifacts:
    - apps/mvp/poller.py
    - docker-compose.mvp.yml
    - tests/test_mvp_poller.py
  key_links:
    - "The poller imports existing tested modules (triage_score.score_item, emitter.handle_verdict_ready, outbox.NtfyClient, vault_writer, store) — it is a wiring job, not a rebuild."
    - "Gaps accepted for MVP and documented, not silent: email/Telegram/BarentsWatch not ingested (feeds only); no pgvector semantic dedup (id-dedupe via store.get_item); wiki/opml-health/DLQ replay out of scope."
---

<objective>
Collapse InfoTriage to a runnable, useful MVP: 19 containers -> 4 (postgres, freshrss, ntfy,
mvp poller). One synchronous asyncio loop replaces the entire event-driven middle — it polls
FreshRSS's Fever API for new items, scores them with the existing local-LLM scorer, persists
to Postgres, fires CAT I pushes through the shipped alerting lane (bus=None), and writes
Obsidian notes + SAB. FreshRSS keeps doing what it does best (fetching, TTL, rate limits);
nothing in the existing stack is deleted.

This is the operator-chosen direction from the 2026-08-02 simplification audit (Option 1:
Lean stack): keep Postgres + ntfy + alerting + FreshRSS; replace RabbitMQ + 6 adapter
containers + scheduler with one synchronous poller.
</objective>

<context>
@.planning/ROADMAP.md
@.planning/STATE.md
@apps/alerting/emitter.py
@apps/triage/triage_score.py
@apps/alerting/outbox.py
@apps/alerting/deep_link.py
@apps/brief/vault_writer.py
@README.md
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: The MVP poller — Fever poll -> score -> persist -> alert -> notes</name>
  <files>apps/mvp/poller.py, tests/test_mvp_poller.py</files>
  <read_first>
    - apps/triage/triage_score.py (score_item signature + llm() env vars)
    - apps/alerting/emitter.py (handle_verdict_ready with bus=None — the sync call path)
    - apps/alerting/outbox.py (NtfyClient constructor + deliver)
    - apps/alerting/deep_link.py (item_note_link / sab_note_link — env read at call time)
    - apps/brief/vault_writer.py (write_vault_digest signature)
    - libs/store/src/store/_postgres.py (PostgresStore constructor)
    - tests/conftest.py (fixture conventions)
  </read_first>
  <behavior>
    - Poll loop runs forever on MVP_POLL_INTERVAL (default 300s), driven by asyncio, with a stdlib /health server so the container passes liveness checks
    - Fetch: GET {FRESHRSS_URL}/api/fever.php?api&items&since_id=<last> (Fever protocol; api_key = md5(username:api_password) per Fever spec) — returns new items since last poll
    - Dedupe: skip items whose id is already in the store (store.get_item by Item.id); record the highest seen item id as since_id for the next poll (persisted so restarts don't refetch the whole feed)
    - Score: triage_score.score_item({"title", "source", "summary"}) — the exact same call the triage worker made
    - Persist: store.put_item(Item(...)) + store.put_enrichment(item_id, fields) — same store calls the old workers made
    - Alert: if cnr == "I", call emitter.handle_verdict_ready({"event": "verdict.ready", "item_id": ..., "cnr": "I"}, store, NtfyClient(...)) with bus=None — the shipped claim->throttle->retry->DLX lane
    - Notes: for kept items (score >= 8 or ccir != none), write Obsidian item note via vault_writer.write_item_obsidian + refresh the SAB via write_sab_obsidian (same filters brief used)
  </behavior>
  <action>
    Write apps/mvp/poller.py implementing the loop above, importing existing modules rather
    than reimplementing anything. Keep the Fever client minimal (urllib + json, mirroring
    triage_score.llm's style). Use INFOTRIAGE_PG_DSN/INFOTRIAGE_BLOB_ROOT for the store (same
    env vars as every other service), FRESHRSS_URL/FRESHRSS_FEVER_USER/FRESHRSS_FEVER_API_PASSWORD
    for the Fever poll, and the existing NTFY_URL/NTFY_TOKEN/NTFY_TOPIC_PREFIX + vault env vars
    for the alert/notes path. Write tests/test_mvp_poller.py with a stubbed Fever server and a
    monkeypatched score_item: a CAT I item fires exactly one push; a non-CAT-I item fires zero;
    a repeat item (same id) is skipped; the since_id advances; the health server responds 200.
  </action>
  <verify>
    <automated>python -m pytest tests/test_mvp_poller.py -q</automated>
  </verify>
  <acceptance_criteria>
    - `python -m pytest tests/test_mvp_poller.py -q` exits 0
    - Polling a stubbed Fever feed with one CAT I item produces exactly 1 POST to the stub ntfy server
    - Polling the same feed again (same item ids) produces 0 additional POSTs (id dedupe + since_id advance)
    - A non-CAT-I item (cnr != I) produces 0 POSTs
    - `handle_verdict_ready` is called with bus=None (no RabbitMQ in the runtime path)
    - Kept items land in the vault (write_item_obsidian called); the SAB is refreshed
    - The /health endpoint returns 200 without touching the bus or DB
    - Source: `apps/mvp/poller.py` imports `triage_score.score_item`, `emitter.handle_verdict_ready`, and `outbox.NtfyClient` (reuse, not reimplementation)
  </acceptance_criteria>
  <done>The MVP poller runs the whole value chain synchronously with zero broker dependencies and reuses every shipped module.</done>
</task>

<task type="auto">
  <name>Task 2: Container + compose overlay + Makefile targets</name>
  <files>apps/mvp/Dockerfile, apps/mvp/requirements.txt, docker-compose.mvp.yml, ops/Makefile, .env.example</files>
  <read_first>
    - apps/alerting/Dockerfile (container pattern — PYTHONPATH, entrypoint, healthcheck)
    - docker-compose.yml (postgres/freshrss/ntfy service blocks to reuse)
    - ops/Makefile (target conventions)
  </read_first>
  <behavior>
    - apps/mvp/Dockerfile + requirements.txt clone the alerting container pattern (multi-stage not needed; single python:3.12-slim with PYTHONPATH=/app)
    - docker-compose.mvp.yml is a SELF-CONTAINED 4-service overlay (postgres, freshrss, ntfy, mvp) — `docker compose -f docker-compose.mvp.yml up -d` is the entire MVP
    - Makefile gains mvp-up / mvp-down / mvp-status / mvp-test targets using the overlay file
    - .env.example documents the new FRESHRSS_URL / FRESHRSS_FEVER_USER / FRESHRSS_FEVER_API_PASSWORD vars (the Fever password already exists in the operator's .env per README)
  </behavior>
  <action>
    Clone the alerting Dockerfile pattern for the mvp app. Write docker-compose.mvp.yml by
    copying the postgres/freshrss/ntfy blocks from docker-compose.yml (they are stable and
    already tested) and adding the mvp service (health port 127.0.0.1:22017:22017, env for
    store/Fever/ntfy/vault, ccir.md mount, host.docker.internal LLM route like triage). Wire
    the Makefile targets.
  </action>
  <verify>
    <automated>docker compose -f docker-compose.mvp.yml config --quiet</automated>
  </verify>
  <acceptance_criteria>
    - `docker compose -f docker-compose.mvp.yml config --quiet` exits 0
    - The overlay defines exactly 4 services: postgres, freshrss, ntfy, mvp
    - The mvp service binds 127.0.0.1:22017 (loopback-only per ADR-016)
    - `make -f ops/Makefile mvp-status` prints the 4 containers' health without errors
    - `.env.example` documents the 3 new Fever env vars
  </acceptance_criteria>
  <done>The whole MVP is one command: `docker compose -f docker-compose.mvp.yml up -d`.</done>
</task>

<task type="auto">
  <name>Task 3: README MVP section + full-suite verification</name>
  <files>README.md</files>
  <read_first>
    - README.md (structure — "Run it" section is where MVP mode belongs)
  </read_first>
  <behavior>
    - README documents "MVP mode": what it runs (4 containers), what it drops (RabbitMQ + adapters + scheduler), the one command, and the documented gaps (email/Telegram/BarentsWatch not ingested; no pgvector dedup; wiki/opml-health out)
    - Full `make -f ops/Makefile test-safe` stays green (no regression to the 814-test baseline)
  </behavior>
  <action>
    Add an "MVP mode (lean stack)" section to README after the existing "Run it" section.
    Then run the full test-safe gate.
  </action>
  <verify>
    <automated>make -f ops/Makefile test-safe</automated>
  </verify>
  <acceptance_criteria>
    - README has an "MVP mode" section documenting the 4 containers, the one command, and the accepted gaps
    - `make -f ops/Makefile test-safe` exits 0 with 0 failures (baseline 814 + the new poller tests)
  </acceptance_criteria>
  <done>Any operator can read README and run the MVP in one command; the full suite stays green.</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/test_mvp_poller.py -q` — green
- `docker compose -f docker-compose.mvp.yml config --quiet` — exit 0
- `make -f ops/Makefile test-safe` — full suite green, no regression on the 814/0 baseline
- `black --check` + `mypy` clean on all new/modified Python files
</verification>

<success_criteria>
- The MVP value chain runs in 4 containers with zero broker dependencies
- Every shipped module is reused (score_item, emitter, NtfyClient, vault_writer, store) — no reimplementation
- The existing 19-service stack remains intact and fully tested; nothing deleted
- README documents MVP mode and its accepted gaps
</success_criteria>

<output>
Create `.planning/phases/13-mvp-lean-stack/13-01-SUMMARY.md` when done
</output>
