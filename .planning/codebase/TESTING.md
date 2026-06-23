# TESTING — trimail

Source of truth: absence of a formal test suite + observed smoke patterns.
Generated: 2026-06-23.

## TL;DR

**No formal test suite.** No `test/`, no `pytest`, no `unittest`, no `conftest.py`. The codebase ships with smoke evals at every code change but no regression test harness. The runtime itself is the integration test (Fever loop on live FreshRSS + live qwen36).

This is consistent with a spike-stage project: cost-of-test-harness exceeds cost-of-smoke-run while the codebase is small and the bugs that matter are end-to-end ones (Cloudflare-blocked feed; credential issue; LLM inviability; staleness).

## What validation exists today

### Smoke at file level

| Layer | Smoke check | Where |
|---|---|---|
| Python syntax | `python3 -m py_compile <file>` | every code change |
| OPML well-formedness | `xml.etree.ElementTree.fromstring()` parses the file cleanly | after every OPML edit |
| Markdown structure | grep `^## ` for section hierarchy | after every ccir.md edit |
| ccir.md × CCIR_ORDER sync | spot-check that tuple count matches expected | after every ccir.md or CCIR_ORDER edit |

### Smoke at module level

| Module | Smoke pattern |
|---|---|
| `score/digest.py` | Build a hand-crafted list of `verdicts` → call `write_bluf(verdicts, period, top_n=K)` → assert the output markdown contains exactly the expected number of `## …` headers and `[N]` references. |
| `score/triage_score.py` | `python3 triage_score.py --sample` against the in-file  `SAMPLE` list; eyeball the markdown digest icons. |
| `score/fever_triage.py` | `python3 fever_triage.py --dry-run --max 20` exercises the full Fever pull without mutating state. |

### Smoke at integration level

Verified live per README's "Status" table:

| Piece | Verified by |
|---|---|
| FreshRSS + rss-bridge + feeds up | `docker compose ps` |
| qwen36 scorer roundtrip | `python3 score/triage_score.py --sample` returns sensible buckets |
| Fever API auth + mark-read roundtrip | `python3 score/fever_triage.py` from the cron |
| Bridge writes to `data/feeds/*.xml` | handshake after the bridge runs |
| FreshRSS subscribes a bridge feed | manual UI / curl on `:8088` |
| `http://feeds/gmail.xml` from inside the `trimail` compose network | container-side curl |

### Smoke at directory level / external services

| Probe | Pattern |
|---|---|
| LLM reachability | `curl -m 3 http://127.0.0.1:8000/v1/models` expecting HTTP 200/401 (auth header). |
| FreshRSS web | `curl -m 3 http://localhost:8088/` expecting 302 (FreshRSS's expected redirect). |
| IMAP probe (Gmail) | low-level `imaplib.IMAP4_SSL('imap.gmail.com'); imap.login(user, pw)` with `.env` loaded. Length-and-shape-only diagnostics for the password (never the password itself). |
| OPML feed health | `curl` each URL, assert `content-type=xml` and HTTP 200; flag ⚠️ empirically. |

## What is missing

These are gaps; ranked by blast-radius × cost to close.

### High priority

- **No regression tests for `score_item`.** The bucket derivation (`skip`/`read`/`maybe`) is the most-branched logic in the codebase. A ccir.md edit + scorer prompt change could silently invert the routing. Cheap to add: `tests/test_triage_score.py` with 8–10 fixtures covering: `ccir=none` ⇒ `skip`; `ccir=PIR-1, cnr=I` ⇒ `read`; `ccir=PIR-1, cnr=II, score=8` ⇒ `read`; etc.
- **No fix for `write_bluf` redaction regression.** Verified once (password-leak guard). No automated regression check that the markdown output never contains `GMAIL_APP_PASSWORD` or other env-var names. Cheap: a fixture where `llm()` raises `Exception("GMAIL_APP_PASSWORD=abcd1234")`, then assert the output BLUF markdown doesn't contain `"abcd1234"` or `"GMAIL_APP_PASSWORD"`. This is the highest-value test for security.
- **No tests for OPML parser roundtrip.** Editing opml by hand with str_replace is fragile (multi-byte em-dash anchors have failed multiple times). A roundtrip test "edit → write → re-parse → feed count == expected" would catch the same bug class instantly.

### Medium priority

- **No `pytest` config.** Setup = `pyproject.toml` or `pytest.ini` at project root. Cost: trivial.
- **No `CI`.** A GitHub-Actions workflow that runs `py_compile` + the bridge IMAP-probes + a sample scoring run would catch 80% of regressions overnight.
- **No fixtures for the bridges.** Each bridge requires live creds to test end-to-end. A `tests/fixtures/{mailboxes,channels}/*.json.example` would let new contributors dry-run bridges without their own creds.
- **No tests for `cluster()` in `score/digest.py`.** Greedy keyword-overlap clustering is replaceable (Phase 2: cosine on embeddings) but currently has no testbench for the existing greedy behavior.

### Low priority (defer)

- **Property-based tests** (Hypothesis) on the LLM prompt parser.
- **Mutation testing** for the scorer.
- **Coverage targets.** Spike-stage: not yet.

## What we've explicitly not done

- **No mocks for the LLM.** Score-time tests against a real local qwen36 (the stack's normal boot path) — that's how the user verifies "the brain works" in practice. A mock would test the parser, not the truck.
- **No load testing.** Digest generation runs in seconds at the current article volume (max 400 per window).
- **No per-bridge integration test against FreshRSS.** Verified manually per README.

## How to run the existing smoke

```bash
# Syntax
python3 -m py_compile score/digest.py score/triage_score.py score/fever_triage.py \
                    bridge/gmail_to_atom.py bridge/imap_to_atom.py bridge/yt_to_atom.py

# OPML well-formedness + feed-count
python3 -c "from xml.etree import ElementTree as ET; r=ET.parse('opml/feeds.opml'); \
            print(sum(1 for o in r.iter('outline') if o.get('type')=='rss'))"

# Scorer self-test
python3 score/triage_score.py --sample

# Fever dry-run (read unread, score, mark nothing)
python3 score/fever_triage.py --dry-run --max 20

# Liveness
docker compose ps
curl -m 3 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:8088/
curl -m 3 -o /dev/null -w 'HTTP %{http_code}\n' http://localhost:3000/
curl -m 3 -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/v1/models
```

## TL;DR for the reviewer

If you only have time to add three tests:

1. `score_item` enum-table test (ccir + cnr + score → bucket).
2. `write_bluf` credential-leak guard test.
3. OPML roundtrip test (write → re-parse → `len(feeds) == expected`).
