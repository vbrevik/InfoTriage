# Testing Patterns

**Analysis Date:** 2026-06-24

## Test Framework

**Runner:**
- `unittest` (Python standard library, built-in)
- No test framework configuration file (no `pytest.ini`, `setup.cfg`, or similar)

**Run Commands:**
```bash
python3 tests/test_opml_check.py                # Run single test file
python3 tests/test_*.py                         # Run all test files (shell glob)
python3 -m unittest discover tests/ -p "test_*.py"  # Discover and run all tests
```

**Assertion Library:**
- Standard `unittest.TestCase` assertions: `assertEqual()`, `assertIn()`, `assertNotIn()`, `assertRaises()`

## Test File Organization

**Location:**
- All tests in `tests/` directory at project root
- Tests are sibling to source code modules (`bridge/`, `opml/`, `score/`)

**Naming:**
- Test files: `test_*.py` format (e.g., `test_opml_check.py`, `test_bridge_escape.py`)
- Test classes: `Test<FeatureName>` (e.g., `TestClassify`, `TestLoadOpml`, `TestEscape`)
- Test methods: `test_<scenario>` (e.g., `test_200_rss_xml_is_live`, `test_ampersand_escaped`)

**Directory Structure:**
```
tests/
├── test_opml_check.py       # opml/_check.py classifier + OPML loader
├── test_bridge_escape.py    # bridge/_util.py::escape() contract
├── test_ccir_sync.py        # CCIR markdown synchronization
├── test_opml_roundtrip.py   # OPML parsing round-trip
├── test_score_parse.py      # Triage scorer JSON extraction
└── test_write_bluf.py       # BLUF credential-leak guard
```

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
