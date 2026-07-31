# Codebase Structure

**Analysis Date:** 2026-07-24 *(refreshed for current containerized architecture)*

## Directory Layout

```
InfoTriage/
├── .planning/              # GSD orchestration state (phases, codebase maps, audits)
│   ├── phases/             # Per-phase plans, summaries, UATs, verifications, context
│   ├── codebase/           # Auto-generated codebase map (this file's family)
│   ├── PROJECT.md          # Living project identity (updated per session)
│   ├── STATE.md            # Pick-up-next-session memory + recent session log
│   ├── ROADMAP.md          # Phase list (v1.0 milestone; phases 00–12)
│   ├── HANDOFF.json        # Cross-phase decisions / pinned contexts
│   └── REQUIREMENTS.md     # Live / target / gated
├── apps/                   # Containerized services — one subdir per Docker Compose service
│   ├── brief/              # Phase 6: SAB + cluster + Obsidian vault projection
│   ├── dlq_consumer/       # Phase 7: RabbitMQ infotriage.dlq consumer + replay
│   ├── ingest-barentswatch/# Phase 11: MASINT/AIS adapter (MASINT discipline, admiralty reliability)
│   ├── ingest-gmail/       # Phase 4: OAuth2/MCP Gmail adapter (ADR-008)
│   ├── ingest-imap/        # Phase 4: multi-protocol mail adapter (IMAP/POP3, ADR-014)
│   ├── ingest-obsidian/    # Phase 4: vault `articles-inbox/` → Atom (READ-ONLY bind)
│   ├── ingest-telegram/    # Phase 11: SOCMINT public channels (Telethon)
│   ├── ingest-youtube/     # Phase 4: YouTube channels + Phase 11 W5 `faster-whisper`
│   ├── ingest/             # Legacy host-side bridge scripts — phased out (keep only RSS_BRIDGE_NOTES.md)
│   ├── ntfy/               # Phase 12 sub-wave (a): Dockerfile pre-bake (ADR-018)
│   ├── opml/               # OPML feed list + validator (`feeds.opml`, `working.opml`, `_check.py`); compose mounts `./apps/opml:/app/opml:ro` into `brief` for SAB rendering
│   ├── opml_health/        # Phase 7: cross-service health aggregator, `/admin/health`
│   ├── scheduler/          # APScheduler cron for ingest adapters
│   ├── triage/             # Phase 5: CCIR-driven event-driven LLM scorer
│   └── wiki/               # Phase 10: standup Obsidian wiki pages; DGX Spark backend
├── libs/                   # Shared Python libraries — published as egg-info packages
│   ├── contracts/          # Bus Protocol (aio-pika + InMemory), shared dataclasses, event types, CCIR registry, verification helpers, structured-logging helpers
│   ├── ingest_common/      # `make_trigger_app(...)` HTTP-trigger plumbing shared by every ingest adapter
│   └── store/              # Store Protocol + Postgres + InMemory implementations
├── ops/                    # Operator-facing tooling
│   ├── Makefile            # help/up/down/logs/status/restart/shell/seed/backfill/replay
│   │                       # test-safe/test-full/test-integration; ntfy-*/ccir-sync
│   └── llm-router.py       # Spark-primary / oMLX-fallback LLM router (ADR-004)
├── scripts/                # One-off scripts + UAT harnesses + regression suites
│   ├── build_ccir_vectors.py          # Offline CCIR pre-filter vectors
│   ├── ccir_sync.py                   # `make ccir-sync`; regenerate OPML CCIR groups
│   ├── check_test_dsn.sh              # Shell-layer DSN safety gate
│   ├── provision_gmail_oauth.py       # One-shot OAuth2 token bootstrap
│   ├── purge_noise_entities.py        # Entity-graph purge utility
│   ├── regression_pmesii_tessoc.py    # Phase 6 regression baseline
│   ├── seed_sample_data.py            # Sample articles for UAT
│   ├── set_newsapi_ttl.py             # FreshRSS per-feed TTL setter
│   ├── uat_test{4,5,6,7,8,9}_*.py     # Per-phase UAT scripts
│   └── validate_entity_threshold.py   # mE5-large cross-language T* sweep
├── tests/                  # 65 test files; pytest + db_live/rabbitmq/integration markers
├── docs/                   # Canonical design + ops docs
│   ├── adr/                # ADR-005..018 (Architectural Decision Records)
│   ├── ARCHITECTURE.md     # Older strategic design doc (Phase 0–4)
│   ├── RESEARCH-REPORT.md  # 2026-06-23 prior-art survey (23 sources → 25 verified claims)
│   ├── ops/logging.md      # JSON-log conventions for InfoTriage services
│   ├── planning/_archived/phase-12-sealed-bind-mount-attempt/  # retired substrate
│   └── superpowers/        # Specs + plans for phased builds
├── ccir.md                 # CANONICAL TAXONOMY — Commander's Critical Info Requirements
├── docker-compose.yml      # Local stack — 19 services on the `infotriage` network
├── docker-compose.test.yml # Throwaway test Postgres + RabbitMQ for `make test-full`
├── pyproject.toml          # Workspace pytest/pythonpath config
├── requirements.txt        # Top-level placeholder (canonical: libs/*/pyproject.toml)
├── CLAUDE.md               # Project instruction contract
├── USER-PROFILE.md         # Operator behavioral profile
└── README.md               # Top-level operator guide
```

## Directory Purposes

**apps/**

- Purpose: One subdirectory per Docker Compose service. Each is a thin Python app + `Dockerfile` + `requirements.txt`.
- Pattern: Adapters expose an HTTP `/health` endpoint; some also expose `/run` (manual trigger per Phase 4 contract).
- Wired by `docker-compose.yml`; names are the Compose service names.

**apps/triage/** (Phase 5)

- Purpose: Consumes `item.ingested`; dedups via mE5-large embeddings (`recall_items()` pre-filter); scores against `ccir.md` with qwen36/qwen80b; persists `InfoTriage.enrichment`; emits `verdict.ready`.
- Key files: `worker.py` (FastAPI trigger + bus consumer), `triage_score.py` (LLM scorer), `entities.py` (LLM NER), `recall.py` (`--topic --since --json` thematic recall CLI), `digest.py`, `sab_html.py` (SAB HTML form).
- Port: `:22030`.

**apps/brief/** (Phase 6)

- Purpose: Consumes `verdict.ready` from RabbitMQ; renders SAB + markdown digest + Obsidian vault projection (default/COP/CIP views).
- Key files: `consumer.py` (RabbitMQ consumer), `html_renderer.py`, `vault_writer.py` (Obsidian file writer), `clustering.py` (pgvector semantic clustering), `_i18n.py` (translation hooks), `renderer.py`, `views.py`.
- Port: `:22040`.

**apps/wiki/** (Phase 10)

- Purpose: Consumes `verdict.ready`; synthesizes Obsidian wiki pages (`Vault/wiki/auto/<slug>.md`); periodic (`--mode periodic`) + events (`--mode events`) modes; DGX Spark (`--backend dgx`) or local (`--backend local`) backend.
- Key files: `wiki_worker.py`, `generator.py` (LLM synthesis), `dgx_client.py` (`RecallBackend` protocol + DGX implementation).
- Port: `:22042`.

**apps/dlq_consumer/** (Phase 7)

- Purpose: RabbitMQ `infotriage.dlq` consumer; emits `feed.unhealthy` on consecutive messages; auto-replay (`--replay`) back to original routing keys; live RabbitMQ-mgmt queue-depth probe.
- Port: none (background worker).

**apps/opml_health/** (Phase 7)

- Purpose: Polls every service's `/health`; aggregates at `/admin/health`. Per-service probe + OPML feed-health classifier.
- Port: `:22032`.

**apps/ingest-*/**: Ingest adapters (one Compose service per directory). Each follows `make_trigger_app()` from `libs/ingest_common`.

- Pattern: `Dockerfile` (FROM `python:3.13-slim`) + `requirements.txt` + `<adapter>_ingest.py` + `main.py` (HTTP trigger wrapper).
- Ports: IMAP `:22010`, YouTube `:22011`, Gmail `:22012`, Obsidian `:22013`, Telegram `:22015`, BarentsWatch `:22016`.

**apps/ntfy/** (Phase 12 sub-wave a)

- Purpose: Local ntfy push channel. `Dockerfile` pre-bakes `auth.db` via BuildKit secrets (ADR-018). Compose binds `/var/cache/ntfy:rw` for runtime cache only — the credentials live in the image layer, not on disk.
- Port: `:22070`.

**apps/ingest/** (legacy)

- Purpose: `imap_to_atom.py`, `yt_to_atom.py` — the original host-side bridge scripts. Replaced by containerized adapters; kept only for the `apps/ingest/RSS_BRIDGE_NOTES.md` reference.

**libs/contracts/**

- Purpose: Shared Python contracts — bus Protocol, BusClient (aio-pika + InMemory implementations), event types, dataclasses (`Item`, `Enrichment`, `Entity`, etc.), CCIR registry (`contracts.ccir`), verification helpers (`contracts._verify`), structured-logging helpers (`contracts.setup_logging`).
- Exports: `BusClient`, `Item`, `Enrichment`, `Entity`, `ccir`, `setup_logging`, etc.

**libs/store/**

- Purpose: `Store` Protocol + Postgres + InMemory implementations. Postgres + pgvector for canonical state; InMemory for tests.
- Methods: `put_item`, `get_item`, `put_entity`, `link_entity`, `recall_items`, `get_active_entities`, etc.

**libs/ingest_common/**

- Purpose: `make_trigger_app()` — single FastAPI blueprint shared by every ingest adapter so each new adapter is `~150 LOC` of domain code (main + the ingest module).

**scripts/ + ops/Makefile**: See `ops/Makefile` help text for the operator surface. The 17 scripts are invocations of specific phases (`build_ccir_vectors.py`, `validate_entity_threshold.py`) plus UAT harnesses.

## Tests

- 65 test files under `tests/`. Pytest is the runner; configuration lives in `[tool.pytest.ini_options]` of the root `pyproject.toml`.
- Markers: `db_live` (requires `INFOTRIAGE_TEST_DSN`), `rabbitmq`, `integration` (requires both).
- `make test-safe` from `ops/Makefile` runs `scripts/check_test_dsn.sh` first, then `make test-full`.
- `make test-integration` runs the suite with both Postgres and RabbitMQ so no tests skip.
- Per-bug/per-feature regression tests: `make test-uvicorn-log`, `make test-dlq-depth`, `make test-dsn-smoke`.

## Naming Conventions

- Modules: `lower_snake_case.py`.
- Files: `_work.py` (e.g. `_atom.py`, `_verify.py`, `_events.py`, `_bus_rabbitmq.py`) for non-public helpers; `main.py` for the FastAPI trigger wrapper; `consumer.py` / `worker.py` for RabbitMQ consumers.
- Tests: `test_<feature>.py`. Test classes `Test<Behavior>`. Methods `test_<scenario>_<outcome>`.
- Env vars: `INFOTRIAGE_*` for our protocol; `LLM_*` for LLM endpoints; `RABBITMQ_*` for the broker; `NTFY_*` for the ntfy push channel; `TELEGRAM_*` / `BARENTSWATCH_*` for the Phase 11 adapters.
- Consts: `SCREAMING_SNAKE_CASE`. Pydantic models: `PascalCase`.

## Where to Add New Code

- New ingest adapter → new subdir under `apps/` + add a service block to `docker-compose.yml` (track the host-port band 22010+) + import `make_trigger_app` from `libs/ingest_common`. Aim for ~150 LOC of domain code.
- New event type → `libs/contracts/src/contracts/_events.py`; add to the `ROUTING_KEY_TO_QUEUE` dict (now a list due to the `verdict.ready` fan-out fix `ec52292`).
- New enrichment field → register the type in `libs/contracts/src/contracts/_verify.py`; produce it in `apps/triage/worker.py`.
- New CLI script → `scripts/<name>.py`; add a Makefile target in `ops/Makefile` if it deserves one (e.g. `make ccir-sync`, `make ntfy-build`).
- New CCIR tier → register in `libs/contracts/src/contracts/ccir.py`; run `make ccir-sync`; the rest of the chain (OPML groups, scorer prompt, sync tests) regenerates automatically.

---

*Structure analysis: 2026-07-24 (refresh)*
