---
phase: 05-triage-app
plan: 04
subsystem: triage-container
tags: [docker, docker-compose, healthcheck, non-root, rabbitmq-reconnect]

requires:
  - phase: 05-03
    provides: apps/triage/worker.py (D-01 event-driven entry point, /health liveness server)
provides:
  - "apps/triage/Dockerfile — python:3.12-slim image, local-lib install pattern mirrored from apps/ingest-imap, non-root USER triage, CMD python worker.py"
  - "apps/triage/requirements.txt — aio-pika, psycopg[binary], pgvector + 3 already-vetted transitive deps (feedgen, pydantic, PyYAML) pulled in by libs/store and libs/contracts module-level imports"
  - "docker-compose.yml triage service — container_name infotriage-triage, 127.0.0.1:22030, python-urllib healthcheck, host.docker.internal extra_hosts for host oMLX, depends_on postgres+rabbitmq service_healthy"
  - "Live-verified: /health 200, RabbitMQ stop/start auto-reconnect via connect_robust, no DSN in logs, non-root container user"
affects: [05-05]

tech-stack:
  added: []
  patterns:
    - "Dockerfile mirrors apps/ingest-imap exactly: COPY libs/contracts + libs/store, pip install --no-deps, then app requirements.txt, then app source, then drop to non-root USER before CMD"
    - "compose healthcheck via python urllib one-liner (python:3.12-slim has no curl) — same pattern as other app containers in this compose file"

key-files:
  created:
    - apps/triage/Dockerfile
    - apps/triage/requirements.txt
  modified:
    - docker-compose.yml

key-decisions:
  - "requirements.txt expanded beyond the plan's literal 3 packages (aio-pika, psycopg[binary], pgvector) to include feedgen, pydantic, PyYAML — see Deviations. All three are already-vetted deps used elsewhere in the monorepo (apps/ingest-imap), pulled in transitively because libs/store and libs/contracts are installed with --no-deps and their own module-level imports require them at runtime."
  - "Operator approved the Task 3 checkpoint based on independent re-verification of /health 200, non-root user, and clean logs."

requirements-completed: [R7]

coverage:
  - id: D1
    description: "docker compose build triage produces an image whose CMD runs python worker.py"
    requirement: "R7"
    verification:
      - kind: manual
        ref: "docker build -f apps/triage/Dockerfile -t infotriage-triage:plancheck . (Task 1); docker compose up -d --build triage (Task 3)"
        status: pass
    human_judgment: false
  - id: D2
    description: "docker compose up -d triage reaches running state; GET http://localhost:22030/health returns 200"
    requirement: "R7"
    verification:
      - kind: manual
        ref: "docker compose ps triage -> running (healthy); curl -s -o /dev/null -w '%{http_code}' http://localhost:22030/health -> 200 (re-confirmed independently in this continuation session)"
        status: pass
    human_judgment: true
    rationale: "Live container health is an operator-observed fact, not unit-testable; re-verified directly via curl + docker compose ps in this session in addition to the prior session's run and the operator's own independent check."
  - id: D3
    description: "The container survives a temporary RabbitMQ outage and reconnects via connect_robust — /health stays 200 and the process does not crash"
    requirement: "R7"
    verification:
      - kind: manual
        ref: "Prior session: docker compose stop rabbitmq -> wait 10s -> curl /health still 200 -> docker compose start rabbitmq -> aio_pika.robust_connection reconnect log lines + rabbitmqctl list_connections confirms a live `infotriage` connection"
        status: pass
    human_judgment: true
    rationale: "Re-confirmed in this continuation session: rabbitmqctl list_connections on infotriage-rabbitmq shows the triage worker's connection in `running` state and `rabbitmqctl list_queues` shows q.triage with an active consumer, days after the original stop/start test — proving connect_robust's auto-reconnect held without manual intervention."
  - id: D4
    description: "The container runs as a non-root user (least privilege, T-05-04)"
    requirement: "R7"
    verification:
      - kind: manual
        ref: "docker exec infotriage-triage whoami -> triage (not root)"
        status: pass
    human_judgment: false
  - id: D5
    description: "No DSN appears in plaintext in container logs (T-05-02)"
    requirement: "R7"
    verification:
      - kind: manual
        ref: "docker compose logs triage | grep -iE DSN/amqp/postgresql patterns -> all aio-pika log lines show amqp://infotriage:******@rabbitmq:5672 (password masked by aio-pika itself, not by app code)"
        status: pass
    human_judgment: false

duration: continuation session (Tasks 1-2 in prior session; Task 3 re-verification + closeout in this session)
completed: 2026-07-01
status: complete
---

# Phase 5 Plan 04: Triage Container Summary

**Dockerized apps/triage/worker.py as the `infotriage-triage` service on 127.0.0.1:22030 — non-root image, python-urllib healthcheck, host-oMLX reachable via host.docker.internal, live-verified RabbitMQ-outage auto-reconnect via connect_robust**

## Performance

- **Tasks:** 3 completed (2 in a prior session, Task 3's live verification re-confirmed and closed out in this continuation session)
- **Files modified:** 3 (apps/triage/Dockerfile, apps/triage/requirements.txt created; docker-compose.yml modified)

## Accomplishments

- `apps/triage/Dockerfile` — `python:3.12-slim`, mirrors `apps/ingest-imap/Dockerfile`'s local-lib install pattern (`COPY libs/contracts`/`libs/store` -> `pip install --no-deps` -> `COPY requirements.txt` -> `pip install -r requirements.txt` -> `COPY apps/triage/` -> non-root `USER triage` -> `CMD ["python", "worker.py"]`). No credential ARG/ENV baked in — secrets arrive at runtime via `env_file` only (NF-6).
- `apps/triage/requirements.txt` — `aio-pika`, `psycopg[binary]`, `pgvector` per the plan, plus three already-vetted transitive deps required because `libs/contracts`/`libs/store` are installed `--no-deps` (see Deviations).
- `docker-compose.yml` triage service — `container_name infotriage-triage`, `127.0.0.1:22030:22030`, `extra_hosts host.docker.internal:host-gateway` (host oMLX reachable on non-Docker-Desktop engines too), `depends_on` postgres+rabbitmq with `condition: service_healthy`, a python-urllib healthcheck (no curl in the slim image), and `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` env defaults pointing at the host oMLX endpoint (ADR-004 — local only, never cloud).
- Task 3 (blocking human-verify checkpoint): live container brought up, `/health` confirmed 200, RabbitMQ stopped/restarted with confirmed `connect_robust` auto-reconnect, non-root user confirmed, no DSN leak in logs confirmed. Operator approved. This continuation session independently re-verified all of the above against the still-running container rather than assuming the prior session's results still held:
  - `docker compose ps triage` -> `Up ... (healthy)`
  - `curl -s -o /dev/null -w "%{http_code}" http://localhost:22030/health` -> `200`
  - `docker exec infotriage-triage whoami` -> `triage`
  - `docker compose logs triage` -> only masked DSNs (`amqp://infotriage:******@rabbitmq:5672`), no plaintext credentials
  - `rabbitmqctl list_connections` on `infotriage-rabbitmq` -> one `infotriage` connection in `running` state; `rabbitmqctl list_queues` -> `q.triage` present with an active consumer — confirming the RabbitMQ connection survived/reconnected after the prior session's stop/start test with no manual intervention needed since

## Task Commits

1. **Task 1: requirements.txt + Dockerfile for the triage container** - `aff9373` (feat) — built and verified `docker build -f apps/triage/Dockerfile -t infotriage-triage:plancheck .` exits 0
2. **Task 2: Add triage service to docker-compose.yml** - `9910278` (feat) — verified `docker compose config` parses the triage stanza
3. **Task 3: [BLOCKING] Live /health + RabbitMQ-reconnect verification (R7)** - no separate commit (pure live-verification checkpoint, no code artifact); operator approved; closed out via this SUMMARY + tracking commit

## Files Created/Modified

- `apps/triage/Dockerfile` - non-root, no-curl, local-lib install pattern mirroring `apps/ingest-imap`
- `apps/triage/requirements.txt` - 3 plan packages + 3 vetted transitive deps (see Deviations)
- `docker-compose.yml` - new `triage` service stanza (port 22030, healthcheck, host-oMLX wiring, postgres+rabbitmq healthy deps)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] requirements.txt needed 3 additional packages beyond the plan's literal list**
- **Found during:** Task 1 (Dockerfile build verification)
- **Issue:** The plan specified exactly `aio-pika`, `psycopg[binary]`, `pgvector` for `apps/triage/requirements.txt` ("no new packages — RESEARCH Package Legitimacy Audit"). Because the Dockerfile installs `libs/contracts` and `libs/store` with `pip install --no-deps`, any package those libraries import at module level must be supplied by the app's own `requirements.txt`. `libs/store/__init__.py` imports `_atom.render_atom` at module level, which imports `feedgen.feed.FeedGenerator` (even though `worker.py` never calls `render_atom` itself); `libs/contracts` (pydantic models) and `libs/store`'s yaml-based config also import `pydantic` and `PyYAML` at module level. Without these three, `docker build` would succeed but the container would crash on import at `python worker.py` startup.
- **Fix:** Added `feedgen>=0.3.1`, `pydantic>=2.0`, `PyYAML>=6.0` to `apps/triage/requirements.txt`, each with an inline comment explaining why it's needed despite not being directly imported by `worker.py`. All three are already-vetted dependencies used identically in `apps/ingest-imap` — no new/unaudited package was introduced, preserving the spirit of the RESEARCH Package Legitimacy Audit (T-05-SC).
- **Files modified:** `apps/triage/requirements.txt`
- **Verification:** `docker build -f apps/triage/Dockerfile -t infotriage-triage:plancheck .` exits 0; `docker compose up -d --build triage` reaches healthy state and `worker.py` imports cleanly (no `ModuleNotFoundError` in logs).
- **Committed in:** `aff9373` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking issue, dependency completeness). No architectural changes, no scope creep. All Task 1/2/3 acceptance criteria met.

## Known Gaps

- **Embedding model `intfloat/multilingual-e5-large` is not yet registered on the local oMLX instance.** `apps/triage/worker.py`'s `get_embedding()` calls the oMLX `/embeddings` endpoint with `"model": "intfloat/multilingual-e5-large"` by name (D-06). As of this plan's verification, no MLX-format build of that model exists on disk for oMLX to load on demand. This does **not** block 05-04: none of Task 3's live checks (`/health`, RabbitMQ stop/start reconnect, non-root user, log-leak check) push a real `item.ingested` message through the dedup/embedding path, so the gap was never exercised here. A real end-to-end run (publishing an `item.ingested` event and letting the worker process it) **will 404 on the embeddings call** until the model is set up on the host oMLX instance. Tracked as a follow-up — not attempted in this plan per scope; likely a prerequisite for Phase 5 Plan 05 (shadow-run parity), which will need real scoring/embedding calls to succeed end-to-end.

## Issues Encountered

None beyond the requirements.txt completeness gap documented above (Rule 3) and the oMLX embedding-model gap documented above (Known Gaps, non-blocking for this plan).

## User Setup Required

- Host oMLX must be running on port 8000 with `qwen36-ud-4bit` loadable on demand for live scoring (already required by 05-02/05-03; confirmed reachable during this plan's verification).
- Before any real end-to-end run (publishing `item.ingested` and observing `verdict.ready`), `intfloat/multilingual-e5-large` must be registered/built on the host oMLX instance — see Known Gaps above.

## Next Phase Readiness

- The `triage` service is live in `docker-compose.yml`, builds, runs as non-root, exposes `/health` on `127.0.0.1:22030`, and has been proven to survive a RabbitMQ outage via `connect_robust` auto-reconnect without crashing.
- Container left running (not torn down) per resume instructions, since Phase 5 Plan 05 (shadow-run) will likely need the same infra (postgres, rabbitmq, oMLX, triage) already up.
- Plan 05-05 (shadow-run parity script + Fever cutover gate) can now run real `item.ingested` events through the live triage container — but should account for the oMLX embedding-model gap above before relying on real dedup/embedding behavior.

---
*Phase: 05-triage-app*
*Completed: 2026-07-01*

## Self-Check: PASSED

All created/modified files (apps/triage/Dockerfile, apps/triage/requirements.txt,
docker-compose.yml triage stanza, this SUMMARY.md) and both Task 1/2 commit hashes
(aff9373, 9910278) verified present in working tree / git log. Live container
re-verified healthy in this session (curl /health -> 200, whoami -> triage,
rabbitmqctl list_connections shows an active infotriage connection).
