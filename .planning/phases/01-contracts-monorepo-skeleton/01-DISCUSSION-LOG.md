# Phase 1: Contracts + monorepo skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 1-contracts-monorepo-skeleton
**Areas discussed:** Packaging/import mechanism, Test runner reconciliation, Repo layout, Codec + bus API, pytest migration guardrail

---

## Packaging / import mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Editable install via pyproject | libs/contracts gets pyproject.toml (pydantic dep); `pip install -e libs/contracts` | ✓ |
| conftest.py sys.path injection | tests/conftest.py inserts libs/ on sys.path — zero packaging | |
| PYTHONPATH / .pth | Set PYTHONPATH=libs at runtime | |

**User's choice:** Editable install via pyproject
**Notes:** Matches the containerized future (each image pip-installs contracts); removes sys.path hacks.

---

## Test runner reconciliation

| Option | Description | Selected |
|--------|-------------|----------|
| Keep unittest, run via pytest | Leave 56 unittest TestCases; pytest collects them natively | |
| Migrate to pytest style | Rewrite 6 files to pytest functions/fixtures | ✓ |
| Keep unittest invocation | Verify via `python3 -m unittest discover` | |

**User's choice:** Migrate to pytest style
**Notes:** Chosen despite the larger diff. Constrained in follow-up to be test-code-only and assertion-preserving (see guardrail below).

---

## Repo layout

| Option | Description | Selected |
|--------|-------------|----------|
| Stage-named apps + fix import shims | apps/ingest (bridge/*), apps/triage (score/*), apps/opml (opml/*); rewrite sys.path targets | ✓ |
| Keep current names under apps/ | apps/bridge, apps/score, apps/opml — literal move | |
| Minimal: only libs/, defer apps/ | Create libs/contracts now, leave scripts in place | |

**User's choice:** Stage-named apps + fix import shims
**Notes:** Aligns with the design doc's app table (named by pipeline stage).

---

## Codec + bus API shape

| Option | Description | Selected |
|--------|-------------|----------|
| PyYAML codec + Protocol bus | PyYAML with explicit datetime; bus = typing.Protocol | (Claude's discretion) |
| python-frontmatter + ABC bus | python-frontmatter lib; bus = abc.ABC | |
| You decide | Let planner/researcher pick | ✓ |

**User's choice:** You decide
**Notes:** Claude recorded PyYAML + typing.Protocol as the default (D-09/D-10); planner may refine.

---

## pytest migration guardrail

| Option | Description | Selected |
|--------|-------------|----------|
| Assertion-preserving, count may differ | 1:1 on assertions; reported count may change; acceptance = all green, zero coverage lost | ✓ |
| Hold count at exactly 56 | Strict 1:1 method→function, exactly 56 collected | |
| Snapshot old run first | Baseline the unittest run, diff after | |

**User's choice:** Assertion-preserving, count may differ
**Notes:** Refines SPEC R5's literal "56" to "all migrated tests green, zero coverage lost."

## Dual-run

| Option | Description | Selected |
|--------|-------------|----------|
| pytest-only | Single canonical runner; drop `__main__` + sys.path hacks | ✓ |
| Keep both runnable | Works under pytest and `python3 tests/test_x.py` | |

**User's choice:** pytest-only

---

## Claude's Discretion

- Codec library (PyYAML) and bus interface style (typing.Protocol) — user said "You decide"; recorded as D-09/D-10. Exact signatures and a possible python-frontmatter alternative left to planner.

## Deferred Ideas

- Real RabbitMQ/aio-pika transport → Phase 3
- Live Postgres store + JSONB persistence → Phase 2
- Containerized app splitting with per-app images → Phase 4+
- mE5-large dedup threshold re-validation → Phase 5
