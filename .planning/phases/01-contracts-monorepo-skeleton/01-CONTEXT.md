# Phase 1: Contracts + monorepo skeleton - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the shared `libs/contracts` package (pydantic v2 `Item`, 4 event schemas, lossless
frontmatter⇆JSONB codec, bus-client interface + in-memory impl) and re-root the repo into
`apps/` + `libs/`, with the existing pipeline behavior preserved. No Postgres, no real RabbitMQ,
no app splitting, no Docker changes this phase.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**6 requirements are locked.** See `01-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `01-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- `libs/contracts` package: `Item`, 4 event schemas, frontmatter⇆payload codec, bus-client interface + in-memory implementation
- Monorepo re-root into `apps/` + `libs/` (re-home existing scripts; one importing `Item`)
- Fixing the three stale doc claims
- Tests for Item id, event validation, codec round-trip, bus dedup/ordering/empty
- Import-boundary check proving no `apps/*` package imports another

**Out of scope (from SPEC.md):**
- Postgres / store implementation, DB schema, live DB wiring — Phase 2 (codec targets the JSONB *shape* only)
- Real RabbitMQ / AMQP transport — Phase 3 (in-memory bus only)
- Splitting `bridge`/`score` into separate containerized apps — Phase 4+ (scripts only re-homed)
- Any `docker-compose.yml` / infra changes
- Any change to pipeline behavior

</spec_lock>

<decisions>
## Implementation Decisions

### Packaging & import mechanism
- **D-01:** `libs/contracts` is a real installable package with its own `pyproject.toml`; the
  **pydantic v2** dependency is declared there. Apps and tests import it via **editable install**
  (`pip install -e libs/contracts`). Rationale: matches the containerized future (each image
  pip-installs contracts) and removes the current `sys.path.insert` hacks. A root
  `requirements-dev.txt` (or equivalent) wires the editable install + pytest for local dev.
- **D-02:** Endpoints/secrets are NOT baked into the package (SPEC prohibition P2) — config comes
  from `.env` at runtime, never from `libs/contracts`.

### Test runner
- **D-03:** **Migrate the 6 test files from `unittest` → pytest style** (functions/fixtures).
  This is a **test-code-only refactor** — it does NOT touch pipeline code, so it stays within the
  "no behavior change to the pipeline" boundary.
- **D-04:** Migration is **assertion-preserving**: no test dropped or weakened, zero coverage lost.
  The literal "56" in SPEC R5 is refined to **"all migrated tests green, zero coverage lost"** —
  the reported pytest count may differ from the unittest method count (parametrization etc.). This
  is an intentional refinement of SPEC R5's acceptance wording; planner/verifier should use the
  coverage-preserving check, not a hard count of 56.
- **D-05:** **pytest is the single canonical runner** after migration. Drop the script-style
  `if __name__ == '__main__': unittest.main()` entrypoints and the `sys.path.insert` sibling hacks
  (the editable install replaces them). No dual-run compatibility kept.

### Repo layout
- **D-06:** Re-home scripts under **stage-named app dirs** per the design doc's app table:
  `apps/ingest/` (from `bridge/*`), `apps/triage/` (from `score/*`), `apps/opml/` (from `opml/*`).
  `libs/contracts/` holds the shared package.
- **D-07:** Rewrite the tests' `sys.path.insert` targets to the new module locations — or drop them
  entirely once `contracts` (and the re-homed app modules) resolve via the editable install.
- **D-08:** At least one re-homed script imports `Item` from `libs/contracts` to satisfy SPEC R5
  (proves the shared contract is wired, not just present).

### Codec + bus API (Claude's Discretion — see below)
- **D-09:** Codec uses **PyYAML** for the YAML⇆markdown-frontmatter split with explicit
  datetime handling (ISO-8601, tz-aware, no precision loss per SPEC R3). Public API:
  `to_frontmatter(payload: dict) -> str` / `from_frontmatter(text: str) -> dict` (names to be
  finalized by planner).
- **D-10:** Bus-client interface is a **`typing.Protocol`** (structural, no inheritance coupling —
  fits "swappable broker"); in-memory impl satisfies it. Methods cover `publish` / `subscribe`
  with idempotency keyed on `Item.id`, FIFO per routing key, empty-subscribe no-op (per SPEC R4).

### Claude's Discretion
- Codec library (PyYAML) and bus interface style (`typing.Protocol`) were delegated by the user
  ("You decide"). D-09/D-10 record the chosen defaults; the planner/researcher may refine exact
  function/method signatures and whether `python-frontmatter` is cleaner with pydantic
  `model_dump()`, as long as the SPEC R3/R4 acceptance criteria hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked requirements
- `.planning/phases/01-contracts-monorepo-skeleton/01-SPEC.md` — Locked requirements, boundaries,
  acceptance criteria, edge coverage, prohibitions. MUST read before planning.

### Architecture / design
- `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` §"The glue — `libs/contracts`"
  — canonical Item schema fields, event schemas, bus client, frontmatter⇆payload codec. §"Apps
  (containers)" — the stage-named app table (ingest/triage/...) that drives D-06.
- `.planning/ROADMAP.md` — Phase 1 entry: goal, 5 success criteria, refs (ADR-006, spec §The glue).
- `.planning/REQUIREMENTS.md` — NF-2 (no paid/cloud/SaaS), NF-1 (all-local LLM) constraints.

### Current-state codebase maps
- `.planning/codebase/STRUCTURE.md` — current flat layout (`bridge/`, `score/`, `opml/`, `tests/`).
- `.planning/codebase/CONVENTIONS.md` §"Import Organization" — current relative-sibling +
  `sys.path.insert` import style being replaced by the editable install.
- `.planning/codebase/TESTING.md` §"Test Imports Pattern" / §"Running Tests" — the 56 tests are
  `unittest` run as scripts with `sys.path.insert(0, "../opml")`; basis for D-03/D-05/D-07.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `score/_util.py` — shared helper already imported by `digest.py` + `fever_triage.py`; the
  re-home must keep this intra-app import working under `apps/triage/`.
- `feedgen` (only third-party dep today) — stays; pydantic v2 + PyYAML + pytest are the new
  dev/runtime additions.

### Established Patterns
- Private modules prefixed `_` (`_util.py`, `_check.py`); SCREAMING_SNAKE_CASE module constants
  (`CCIR_ORDER`, `CCIR_PATH`). New contracts code should match house style.
- Tests currently: `import pytest`-free `unittest.TestCase` subclasses run as `__main__` scripts
  with manual `sys.path` injection — all three patterns are being removed (D-05).

### Integration Points
- Re-homed scripts must import `Item` from `libs/contracts` (D-08) — the first place app code
  depends on the shared contract instead of ad-hoc dicts.
- Editable install is the seam every future container build reuses (`pip install -e libs/contracts`).

</code_context>

<specifics>
## Specific Ideas

- `Item.id = sha256(normalized(source_type + url + title))` — content-stable id is the bus
  idempotency/dedup key (SPEC R1/R4). Normalization rules to be specified by planner.
- Codec round-trip fixture must include nested dicts/lists, `None`, unicode, and a tz-aware
  datetime (SPEC R3 acceptance).

</specifics>

<deferred>
## Deferred Ideas

- Real RabbitMQ/aio-pika bus transport → Phase 3 (in-memory impl only now).
- Live Postgres store + JSONB persistence → Phase 2 (codec targets the shape only).
- Splitting `bridge`/`score` into independent containerized apps with their own images → Phase 4+.
- Re-validating mE5-large dedup threshold on held-out corpus → Phase 5 (carried from Phase 0).

None of these are in Phase 1 scope — discussion stayed within the contracts/restructure boundary.

</deferred>

---

*Phase: 1-contracts-monorepo-skeleton*
*Context gathered: 2026-06-27*
