# Phase 7 07-04 — dep-list-superset guard closes the structural-fragility nit

**Committed:** `f17e644 — test(07-04): dep-list-superset guard + opml_health pydantic fix`
**Local-only:** yes (2 commits ahead of `origin/main` at merge-time).
**Status:** M1 ship-gate fully closed at the planning layer.

## What this closes

The transitive deps that `contracts/__init__.py` eagerly imports live in
**two places** that must stay in sync:

1. `libs/contracts/pyproject.toml` — authoritative for `pip install -e libs/contracts`
   and any out-of-Docker install path.
2. Every `apps/*/requirements.txt` that ships a service consuming contracts —
   authoritative for Docker images (which install contracts with `--no-deps`).

Phase 7 07-03 came about because three services (`dlq-consumer`, `opml-health`,
`scheduler`) crash-looped when these drifted out of sync. The class of bug is
prevented now by **a single pytest** that fails CI the moment a new transitive
dep is added to `contracts/__init__.py` and missing from even one consumer
`requirements.txt`.

## Files in the diff

**NEW:** `tests/test_dep_list_superset.py` — 157 lines, one parametrized test
across 9 apps (brief, triage, dlq_consumer, opml_health, scheduler,
ingest-{imap,youtube,gmail,obsidian}).

**MODIFIED:** `apps/opml_health/requirements.txt` — added the missing
`pydantic>=2.0` (Phase 7 07-03 oversight that the test caught on its very
first run; a real defect, not a false positive).

## Detection logic (the heart of the test)

A service's `apps/*/requirements.txt` is cross-checked when the service
"consumes" `contracts`. Consumption is the union of three paths:

- **(A)** — the app's own `*.py` directly imports `contracts`
  (`import contracts` / `from contracts import …`).
- **(B)** — the app's Dockerfile mentions `libs/contracts` or `build/contracts`
  (catches apps that install contracts transitively via the IMAGE even though
  their own source never names it — e.g. `ingest-imap` uses `libs/ingest_common`
  which itself imports `contracts`; the Dockerfile installs contracts).
- **(C)** — *future-proofing*: any sibling `libs/<X>` the app's `*.py` imports
  declares `contracts` as a dep in `libs/<X>/pyproject.toml`. Covers any
  future indirect-only service.

## Parse strategy (chosen for minimalism)

- **pyproject.toml** — stdlib `tomllib.load()` on the `[project].dependencies`
  array.
- **pip reqs.txt** — one shared `_PACKAGE_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.+-]*)")`
  extracts the leading package name from each line (after stripping inline
  `# …` comments).
- **Comparison** — case-folded lower; version specifiers are dropped (a
  stricter pin in reqs.txt doesn't trigger a false negative).

No third-party deps. No `pip._internal` reach-throughs. No `packaging.requirements`
imports. Pure stdlib + pytest.

## Verification

- `python -m pytest tests/test_dep_list_superset.py -v` → **9/9 apps pass**
  (brief, triage, dlq_consumer, opml_health, scheduler, ingest-{imap,youtube,
  gmail,obsidian}).
- `python -m pytest tests/ -q` → **328 passed, 34 skipped, 0 failed** (baseline
  preserved; +1 vs. the 07-03 baseline counting this new test).
- Two-pass code review returned **PASS** on both the initial design and the
  post-cleanup refinements (try/except removal + `_PACKAGE_RE` harmonization).

## Files / commits

- `f17e644 — test(07-04): dep-list-superset guard + opml_health pydantic fix` —
  the add-test + the bug-fix it uncovered, in one atomic commit per the
  "milestone commits" guideline.

## Decisions recorded

1. **Detection union (A ∪ B ∪ C).** Choosing A alone misses the 4 ingest-*
   adapters (their source imports `libs.ingest_common` not `contracts`); choosing
   A ∪ B alone misses any future indirect-only service that doesn't name
   `libs/contracts` in its own Dockerfile. C closes that gap without static
   hard-coding.

2. **Version specifiers ignored at comparison.** The test asserts "every
   package name is present in every consumer's reqs.txt". A stricter version
   pin (e.g. `aio-pika==9.6.1` vs pyproject's `aio-pika>=9.6`) is a
   documentation-quality issue (call it out in code review) but **not** a
   hard correctness issue — Python's resolver will install whatever the
   consumer's req says.

3. **`tomllib.load` raises loudly.** The reviewer's second pass pushed back on
   the initial `try/except Exception` around the per-lib `tomllib.load` —
   a malformed `libs/<X>/pyproject.toml` is a real repo bug that should
   crash with a meaningful error rather than be silently treated as "this
   lib doesn't consume contracts". Removed per the "prefer to remove
   unnecessary try/except" guideline.

## Connection to 07-02 / 07-03

This 07-04 closes the loop on the reviewer-flagged fragility from 07-02 and
07-03:
- **07-02** (feat, `591034d`) closed the 3 M1 known gaps; uvicorn JSON access
  logs, live DLQ depth probe, DSN smoke gate.
- **07-03** (fix, `3da4932` + docs `428f8a9`) closed the live-stack follow-up
  crashes for `apps/opml_health`, `apps/dlq_consumer`, and `apps/scheduler`
  + the `worker.py` vhost URL-encoding bug.
- **07-04** (test, `f17e644`) prevents the 07-03 class of bug from ever shipping
  silently again.

Together these three commits finish **the M1 ship-gate**.
