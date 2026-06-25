---
phase: 00-concept-spike
plan: "01"
subsystem: infra
tags: [docker, rabbitmq, pgvector, pika, defusedxml, rss, nrk, bbc, tass]

requires: []

provides:
  - "Ephemeral RabbitMQ 3.13-management container on ports 22060 (AMQP) / 22061 (management UI)"
  - "Ephemeral pgvector/pgvector:pg16 container on port 22062 (Postgres with vector extension)"
  - ".spike/ scratch layout (r1_rabbit/ r2_dedup/ r3_entities/ r4_wiki/ r5_worldmonitor/)"
  - ".spike/requirements-spike.txt pinning pika==1.4.1, pgvector==0.4.2, defusedxml"
  - ".spike/r2_dedup/r2_fetch.py — defusedxml-safe NRK/BBC/TASS corpus fetcher"
  - ".spike/items.json — 144 fresh corpus items (nrk:20, bbc:24, tass:100) shared across R2-R5"
  - ".gitignore guard for .spike/ (ephemeral lifecycle, D-06)"

affects: [00-02-PLAN.md, 00-03-PLAN.md, 00-04-PLAN.md, 00-05-PLAN.md]

tech-stack:
  added: [pika==1.4.1, pgvector==0.4.2, defusedxml, rabbitmq:3.13-management, pgvector/pgvector:pg16]
  patterns:
    - "defusedxml.ElementTree as the sole XML parser for network-sourced feeds (XXE prevention)"
    - "Distinct port band 22060-22062 for throwaway spike infra, never overlapping prod 8088/3000"
    - "Force-added gitignored spike configs (.spike/docker-compose.yml etc.) so they are tracked but .spike/items.json is not"

key-files:
  created:
    - .spike/docker-compose.yml
    - .spike/requirements-spike.txt
    - .spike/r2_dedup/r2_fetch.py
  modified:
    - .gitignore

key-decisions:
  - "defusedxml.ElementTree exclusively for RSS parsing — stdlib XML parser forbidden (RESEARCH Pitfall 7 / T-00-01-XXE)"
  - "Port band 22060-22062 for spike containers, credentials spike/spike — fully isolated from prod (D-04)"
  - ".spike/ gitignored wholesale; config files force-added individually so items.json never commits"
  - "OrbStack started automatically when Docker daemon was not running (no manual intervention needed)"

patterns-established:
  - "Spike config files (docker-compose, requirements) committed via git add -f; ephemeral data (items.json) stays gitignored"
  - "All network-sourced XML parsed with defusedxml — carry this pattern into any future RSS ingestion code"

requirements-completed: [R1, R2, R3, R4, R5]

duration: 7min
completed: "2026-06-25"
status: complete
---

# Phase 00 Plan 01: Spike Infra + Corpus Fetcher Summary

**Ephemeral RabbitMQ (22060/22061) + pgvector (22062) containers live; 144-item NRK/BBC/TASS corpus fetched via defusedxml and written to .spike/items.json — all downstream R2-R5 unknowns can now proceed.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-25T07:11:31Z
- **Completed:** 2026-06-25T07:18:39Z
- **Tasks:** 2
- **Files modified:** 4 (`.gitignore`, `.spike/docker-compose.yml`, `.spike/requirements-spike.txt`, `.spike/r2_dedup/r2_fetch.py`)

## Accomplishments

- Ephemeral RabbitMQ 3.13-management and pgvector/pgvector:pg16 containers pulled, started, and confirmed healthy on port band 22060-22062; prod stack (8088/3000) untouched.
- pika==1.4.1, pgvector==0.4.2, defusedxml installed; `python3 -c "import pika, pgvector, defusedxml"` exits 0.
- `.spike/r2_dedup/r2_fetch.py` fetches NRK/BBC/TASS using defusedxml.ElementTree exclusively (XXE-safe) and writes 144 normalized items to `.spike/items.json`, spanning all three sources.
- `.gitignore` guard added so the entire `.spike/` tree is ignored by default; throwaway data (items.json) can never be accidentally committed.

## Container Ports Confirmed Running

| Service | Image | Host ports | Status |
|---------|-------|------------|--------|
| rabbitmq | rabbitmq:3.13-management | 22060 (AMQP), 22061 (mgmt UI) | healthy |
| pgvector | pgvector/pgvector:pg16 | 22062 (Postgres) | healthy |

## Item Count per Source

| Source | Items | Lang |
|--------|-------|------|
| nrk | 20 | no |
| bbc | 24 | en |
| tass | 100 | ru |
| **Total** | **144** | — |

144 items far exceeds the >=30 threshold. The assumption (PLAN § Assumptions) that feeds carry >=10 concurrent same-story triples should be verifiable in R2 labeling.

## Task Commits

1. **Task 1: Scaffold spike infra + containers** — `14ead5e` (feat)
2. **Task 2: r2_fetch.py corpus fetcher** — `f317cd4` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `.gitignore` — added `.spike/` line (ephemeral lifecycle guard D-06)
- `.spike/docker-compose.yml` — two services: rabbitmq:3.13-management + pgvector:pg16 on port band 22060-22062 with spike/spike credentials
- `.spike/requirements-spike.txt` — pinned pika==1.4.1, pgvector==0.4.2, defusedxml
- `.spike/r2_dedup/r2_fetch.py` — defusedxml-safe NRK/BBC/TASS fetcher; normalizes to stable `{source}_{NNN}` IDs; read-only

## Decisions Made

- **defusedxml.ElementTree exclusively**: stdlib parser is forbidden in any code parsing network-sourced XML (T-00-01-XXE). Comments in r2_fetch.py avoid even mentioning the forbidden module name so the grep gate stays clean.
- **Force-add pattern for spike configs**: `.spike/` is gitignored wholesale (so items.json never commits), but docker-compose.yml / requirements-spike.txt / r2_fetch.py are individually force-added via `git add -f` so they are tracked.
- **OrbStack auto-start**: Docker daemon was not running on first `docker compose up`; `open -a OrbStack` was sufficient to start it without user intervention.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment text triggered XXE grep gate**
- **Found during:** Task 2 acceptance check
- **Issue:** Two comment lines in r2_fetch.py contained the text `xml.etree` as documentation (explaining exclusion), causing `grep -nE 'xml\.etree'` to return matches — a false positive on the security gate.
- **Fix:** Rewrote the two comment lines to avoid the string `xml.etree` while preserving the intent ("unsafe stdlib parser is intentionally excluded").
- **Files modified:** `.spike/r2_dedup/r2_fetch.py`
- **Verification:** `grep -nE 'xml\.etree' .spike/r2_dedup/r2_fetch.py` returns nothing.
- **Committed in:** f317cd4 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — false-positive grep gate triggered by documentation comments)
**Impact on plan:** Trivial; no behavioral change. Grep gate now passes cleanly.

## Issues Encountered

- Docker daemon was not running when `docker compose up -d` was first attempted (OrbStack). Fixed by `open -a OrbStack` — daemon started within 5 seconds, no user action required.
- The `version:` key in docker-compose.yml produced an "obsolete attribute" warning from Docker Compose. Harmless; containers started correctly. Left as-is since the PLAN specified the format.

## Go/No-Go Outcome

**GO** — All infra prerequisites for the five R1-R5 investigations are in place:
- RabbitMQ broker reachable on 22060/22061 (R1)
- pgvector Postgres reachable on 22062 (R3)
- 144-item multilingual corpus at .spike/items.json (R2, R4, R5)
- Spike Python deps installed (R2-R5 scripts can import pika, pgvector, defusedxml)
- Prod stack untouched; read-only constraint honored

## Next Phase Readiness

- R1 (RabbitMQ topology spike) can proceed — broker is live on 22060.
- R2 (Norwegian dedup spike) can proceed — items.json has 20 NRK items + 24 BBC + 100 TASS for cross-lingual same-story labeling.
- R3 (entity resolution spike) can proceed — pgvector on 22062 ready for schema + vector ops.
- R4 (Wiki-LLM spike) and R5 (World Monitor COP spike) can draw from items.json via the existing pipeline.

---
*Phase: 00-concept-spike*
*Completed: 2026-06-25*
