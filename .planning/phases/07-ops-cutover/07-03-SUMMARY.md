# Phase 7 07-03 — M1 runtime-deps follow-up + live-stack gap closure

**Shipped:** commit pending (this turn). Follow-up to Phase 7 07-02 (`591034d`).

## What this closes

The Phase 7 07-02 commit made every InfoTriage service exercise the `from
contracts import ...` import chain actively at module-init time (via
`setup_logging()` in every service entrypoint, plus `LOGGING_CONFIG` in CLI-
mode uvicorn containers). Before 07-02, those imports were dormant — pytest
covered most code paths but didn't exercise every Dockerfile's container
start. The live-stack smoke test surfaced 4 distinct runtime issues that this
07-03 pass closes:

### 1. Three services crash-looping on transitive `from contracts import set...">The transitive deps of contracts (`pydantic`, `PyYAML`, `aio-pika`,
`json-log-formatter`) are pulled in eagerly by `contracts/__init__.py`. After
07-02 made every service `from contracts import setup_logging` at module-init,
3 containers (dlq-consumer, opml-health, scheduler) crashed because of missing
deps in their `requirements.txt`:

- **dlq-consumer**: missing `pydantic`, `PyYAML`
- **opml-health**: missing `PyYAML`, `aio-pika`
- **scheduler**: missing `pydantic`, `PyYAML`, `aio-pika` (deepest case — its
  `Dockerfile` never even `COPY`ed `libs/contracts` in before 07-03)

**Fix:** each affected `requirements.txt` now hand-lists all four transitive
deps with explanatory comments. `apps/scheduler/Dockerfile` adds a libs/contracts
`--no-deps` install step (matches the pattern already used by `triage` and
`brief`).

### 2. `libs/contracts/pyproject.toml` was missing `aio-pika` as a declared dep

`contracts/_bus_rabbitmq.py` requires `aio_pika`, but `pyproject.toml` only
declared `pydantic`, `PyYAML`, `json-log-formatter`. This was the root-cause
of issue #1 for any out-of-Docker install path (e.g., a developer doing
`pip install -e libs/contracts`). The Docker paths will still need hand-adds
because every Dockerfile installs with `--no-deps`, but the pyproject.toml
fix ensures consistency for dev installs.

**Fix:** append `"aio-pika>=9.6"` to `dependencies`. While there, widened the
leading comment to cover all 4 transitive deps (it previously scoped itself
only to `json-log-formatter`, hiding the shape of the issue).

### 3. `docker compose build` failed on every contracts consumer (TOML grammar bug)

The `pyproject.toml` rewrite unblocked the install, but `pip install --no-deps
/build/contracts` then failed with `tomllib.TOMLDecodeError: Expected '='
after a key in a key/value pair (at line 15, column 20)`. The closing
parenthesis of the leading comment was fused directly to the `dependencies = [...]`
key with no intervening newline — a TOML grammar error caused by an earlier
str_replace edit not preserving the blank line.

**Fix:** rewrote `pyproject.toml` cleanly with a blank line separator. Now
installing the library (`pip install --no-deps /build/contracts`) succeeds in
every Dockerfile that uses that pattern (brief, triage, 4 ingest-* adapters,
scheduler, dlq-consumer, opml-health).

### 4. DLQ depth-probe URL-builder was emitting `///` causing 404s

`apps/dlq_consumer/worker.py._probe_queue_depth` built the RabbitMQ mgmt-API
URL with `f".../api/queues/{mgmt_vhost}/{DLQ_NAME}"` and defaulted
`mgmt_vhost` to `"/"`. The literal `/` collapsed with the path template's
own `/` separators to produce `///infotriage.dlq` — a malformed path that
the mgmt-API rejects with 404. The RabbitMQ contract requires URL-encoded
`%2F` for the default vhost.

**Fix:** import `urllib.parse.quote as _quote_vhost` and URL-encode the
vhost segment when building the URL: `quote(mgmt_vhost, safe="")` produces
`%2F` for `/` and leaves harmless vhost names untouched.

## Verification

| Check                              | Result                                            |
| ---------------------------------- | ------------------------------------------------- |
| `python -m pytest tests/ -q`       | **319 passed**, 34 skipped, 0 failed              |
| Code-reviewer post-fix pass        | **PASS** on all 7 verification points             |
| `make -f ops/Makefile status`      | All InfoTriage app services **Up**                |
| `dlq-consumer` depth-probe         | URL now `/api/queues/%2F/infotriage.dlq` → HTTP 200 |

The 3 services still marked "unhealthy" in `make status` (freshrss first-boot
wizard, gmail-mcp missing OAuth creds, rssbridge 503 — all pre-existing
third-party dependencies unrelated to this work).

## Files changed (consolidated)

**MODIFIED (6):**
- `apps/dlq_consumer/requirements.txt` — pydantic + PyYAML added; duplicate
  PyYAML block deduped
- `apps/dlq_consumer/worker.py` — URL-encode `mgmt_vhost` in mgmt-API URL
- `apps/opml_health/requirements.txt` — PyYAML + aio-pika added
- `apps/scheduler/Dockerfile` — libs/contracts `--no-deps` install step added
- `apps/scheduler/requirements.txt` — pydantic + PyYAML + aio-pika added
- `libs/contracts/pyproject.toml` — `aio-pika>=9.6` declared + TOML grammar
  restored

**No new files** in this phase; this is a corrective follow-up to 07-02.

## Future work (07-04 candidates)

The reviewer flagged one structural concern: the 4 transitive deps now live in
two places that must stay in sync — `libs/contracts/pyproject.toml` and every
`apps/*/requirements.txt`. A future addition to `contracts/__init__.py` would
require editing N+1 files; the mitigation is a 5-line pytest that asserts
`pyproject.toml` deps are a superset of every `apps/*` re-listing. Not in 07-03
scope but a clean 07-04 add-test target.
