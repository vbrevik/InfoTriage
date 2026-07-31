# Testing Patterns

**Analysis Date:** 2026-06-24

## Test Framework

**Runner:**
- `pytest` (configured under `[tool.pytest.ini_options]` in the root `pyproject.toml`)
  - `pythonpath` points at `libs/{contracts,store,ingest_common}/src` and every `apps/<service>` so tests run from the repo root without `pip install -e` (though `pip install -e libs/contracts libs/store libs/ingest_common` makes type-checking happier).
  - Markers registered in the same block: `db_live`, `rabbitmq`, `integration` — and ad-hoc `slow` / `asyncio` where used.
  - 65 test files (counted 2026-07-23); recent baseline **572 passed / 7 skipped / 58 deselected / 0 failed**.

**Run Commands:**
```bash
# Quick subset (no integration markers) — runs without rabbitmq/Postgres env:
pytest tests/ -q

# Project defaults — use ops/Makefile targets:
make test-safe          # DSN smoke (check_test_dsn.sh) → full pytest chain
make test-full          # full pytest against throwaway Postgres (port 22062)
make test-integration   # adds RabbitMQ so db_live/rabbitmq/integration don't skip

# Convenience regression targets (operator-facing per bug-fix):
make test-uvicorn-log   # tests/test_uvicorn_log_config.py
make test-dlq-depth     # tests/test_dlq_depth_probe.py
make test-dsn-smoke     # tests/test_check_test_dsn.py
```

**Assertion Library:**
- pytest's `assert` statement with rich introspection (rewritten at collection time).
- Existing `unittest.TestCase` subclasses are still discoverable and runnable — pytest supports both. New tests should use plain `assert` + pytest fixtures.

## Test File Organization

**Location:**
- All tests in `tests/` directory at the project root.
- **65 test files** (counted 2026-07-23). Coverage spans `libs/{contracts,store,ingest_common}` + `apps/{triage,brief,wiki,opml_health,dlq_consumer,ingest-*}` + cross-cutting concerns (bus topology, CCIR sync, dedup thresholds).

**Naming:**
- Test files: `test_<feature>.py` (e.g. `test_triage_worker.py`, `test_recall.py`, `test_wiki_generator.py`, `test_ccir_registry.py`, `test_cross_language_synthesis.py`).
- Test classes: `Test<Behavior>` uppercase prefix (pytest discovery-friendly); not required for plain-`def test_` style.
- Test methods: `test_<scenario>_<outcome>` (behavior-driven; e.g. `test_atomic_rename_does_not_leave_tmp`).

**Markers (registered in `pyproject.toml` `[tool.pytest.ini_options]`):**
- `db_live: requires INFOTRIAGE_TEST_DSN pointing at a reachable isolated test Postgres`
- `rabbitmq: requires RabbitMQ :22001 to be running`
- `integration: used by the superclaude pytest plugin for integration tests`
- Plus ad-hoc `@pytest.mark.skipif(...)` for opt-in feature tests (e.g. YouTube transcription gated on `INFOTRIAGE_YOUTUBE_TRANSCRIBE`, DGX Spark routing gated on backend argument).

`poolimport`/`pythonpath` includes `libs/{contracts,store,ingest_common}/src` + every `apps/<service>`, so tests run from the repo root once `libs/*` are installed (`pip install -e libs/contracts libs/store libs/ingest_common`).

## Test Structure

**Suite Organization:**
```python
class TestClassify(unittest.TestCase):
    """``classify(probe_result)`` → (emoji, reason). Pure logic, no network."""

    def test_200_rss_xml_is_live(self):
        """200 OK with <?xml + <rss = ✅."""
        self.assertEqual(
            _check.classify((200, "application/rss+xml",
                             b'<?xml version="1.0"?><rss version="2.0">')),
            ("✅", "HTTP 200, RSS/Atom XML"))

    def test_200_html_body_keeps_warning(self):
        """200 OK but body is HTML (Pravda / The National Interest) = ⚠️."""
        self.assertEqual(
            _check.classify((200, "text/html",
                             b"<!DOCTYPE html><html><head><title>Pravda</title>")),
            ("⚠️", "HTTP 200, HTML body"))
```

**Patterns:**
- One docstring per test method explaining the scenario and expected outcome
- Assertion on result immediately after action
- Each test is self-contained (no test order dependencies)
- Multiple related tests in one test class

**Setup and Teardown:**
```python
class TestEmitWorkingOPML(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Build synthetic test data
        def outline(title, url):
            return ET.Element("outline", {...})
        self.results = [...]

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_emit_working_opml_keeps_only_live_and_transient(self):
        out_path = os.path.join(self.tmpdir, "working.opml")
        _check.emit_working_opml(self.results, out_path, "2026-06-24")
        tree = ET.parse(out_path)
        # assertions...
```

## Mocking

**Framework:** Manual mocking without a dedicated mocking library

**Patterns:**
```python
def test_credential_not_in_markdown(self):
    """Exception carrying GMAIL_APP_PASSWORD=… must NOT appear in bluf.md."""
    secret = "GMAIL_APP_PASSWORD=abcd1234efgh5678"
    original = triage_score.llm

    def failing_llm(msgs, max_tokens=400):
        raise RuntimeError(f"auth failed: {secret}")

    triage_score.llm = failing_llm
    try:
        _, text = write_bluf(self._make_verdicts("PIR-1"), "test period")
    finally:
        triage_score.llm = original

    self.assertNotIn("abcd1234", text)
```

**What to Mock:**
- External function calls that have side effects
- LLM API calls (replace with lambda returning test data)
- I/O operations that are expensive or have state

**What NOT to Mock:**
- Pure functions (no side effects)
- XML parsing (safe and fast)
- Data structure operations

## Fixtures and Factories

**Test Data Creation:**
```python
def _make_verdicts(self, ccir="PIR-1"):
    """Minimal verdict list hitting one CCIR."""
    return [{"title": "t", "source": "s", "summary": "sum",
             "ccir": ccir, "cnr": "II", "score": 8, "bucket": "read",
             "why": "test", "url": "http://x", "id": 1, "t": 0}]

def _make_verdicts_n(self, ccir, n, score_start=9):
    """N items in CCIR `ccir` with descending scores."""
    return [
        {"title": f"item_{i}", "source": f"s_{i}",
         "summary": "x " * 50,
         "ccir": ccir, "cnr": "II", "score": score_start - i,
         "bucket": "read", "why": "test",
         "url": f"http://x/{i}", "id": i, "t": 0}
        for i in range(n)
    ]
```

**Location:**
- Helper methods in the test class, prefixed with `_`
- Not extracted to separate files (kept inline for clarity)

## Coverage

**Requirements:** None enforced (no coverage tool configured)

**View Coverage:**
- No built-in command; would require adding pytest-cov or coverage.py

## Test Types

**Unit Tests:**
- Pure function testing with controlled inputs
- Examples: `TestClassify`, `TestEscape`, `TestScoreParse`
- No network access required; all probes mocked
- Scope: Single function or class behavior

**Integration Tests:**
- Multi-component testing (e.g., OPML loading + filtering)
- Examples: `TestLoadOpml`, `TestEmitWorkingOPML`
- File I/O tested using `tempfile.mkdtemp()`
- Scope: Entire workflow with real files

**E2E Tests:**
- Not used in this codebase
- Tests run locally without external services

## Common Patterns

**Assertion for Exception Type:**
```python
def test_non_str_input_fails_loud(self):
    """Defense-in-depth: silent ``str()`` coercion was over-broad."""
    for bad in (123, 4.5, ["a"], {"k": "v"}, b"bytes"):
        with self.assertRaises(TypeError,
                               msg=f"expected TypeError for input {bad!r}"):
            escape(bad)
```

**Multiple Assertions per Test:**
```python
def test_emit_working_opml_keeps_only_live_and_transient(self):
    """✅ + 🟡 survive; ⚠️ + ❌ are dropped."""
    out_path = os.path.join(self.tmpdir, "working.opml")
    _check.emit_working_opml(self.results, out_path, "2026-06-24")
    tree = ET.parse(out_path)
    cats = tree.getroot().find("body").findall("outline")
    texts_in_file = []
    for c in cats:
        cat_text = c.get("text")
        for sub in c.findall("outline"):
            texts_in_file.append((cat_text, sub.get("text")))
    self.assertIn(("CatA", "A1-live"), texts_in_file)
    self.assertIn(("CatA", "A2-transient"), texts_in_file)
    self.assertNotIn(("CatA", "A3-broken"), texts_in_file)
```

**Defense-in-Depth Testing:**
```python
def test_double_escape_stays_well_formed(self):
    """Defense-in-depth: html.escape is not idempotent by design.
    Even if a bridge accidentally double-escapes, the output still
    contains no raw XML metachars — FreshRSS keeps parsing."""
    for raw in ["<a>", "a&b", '"x"', "mix & < > '\"", "AT&T"]:
        once = escape(raw)
        twice = escape(once)
        for c in ("<", ">"):
            self.assertNotIn(c, twice,
                             f"raw {c!r} leaked through double-escape of {raw!r}")
```

**Behavior-Driven Test Names:**
Test names describe the scenario and expected outcome, not just the operation:
- `test_200_rss_xml_is_live` — describes scenario AND result
- `test_html_body_keeps_warning` — describes state AND outcome
- `test_credential_not_in_markdown` — describes contract being tested
- `test_none_returns_empty_string` — describes input AND output

## Test Imports Pattern

```python
#!/usr/bin/env python3
"""tests/test_opml_check.py — opml/_check.py classifier + OPML loader.

[Docstring with test purpose and usage]
"""
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

# Set up path to import from sibling package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opml"))
import _check  # noqa: E402

# Define module-level constants
OPML = os.path.join(os.path.dirname(__file__), "..", "opml", "feeds.opml")

# Define test classes
class TestClassify(unittest.TestCase):
    ...

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

## Running Tests

**Example Test Run Output:**
```bash
$ python3 tests/test_opml_check.py
test_200_rss_xml_is_live (test_opml_check.TestClassify) ... ok
test_200_html_body_keeps_warning (test_opml_check.TestClassify) ... ok
test_403_cloudflare_is_warning (test_opml_check.TestClassify) ... ok
...
Ran 24 tests in 0.123s

OK
```

**Verbosity:**
- Default: minimal output (just `.` or `F` per test)
- `unittest.main(verbosity=2)`: show test name + result for each test

---

*Testing analysis: 2026-06-24*
