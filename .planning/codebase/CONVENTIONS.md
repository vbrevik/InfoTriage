# Coding Conventions

**Analysis Date:** 2026-06-24

## Naming Patterns

**Files:**
- Lowercase with underscores: `gmail_to_atom.py`, `_check.py`, `triage_score.py`
- Private modules prefixed with underscore: `_util.py`, `_check.py`
- Test files: `test_*.py` (e.g., `test_opml_check.py`)

**Functions:**
- Lowercase with underscores: `load_opml()`, `classify()`, `probe_and_classify()`, `escape()`, `emit_working_opml()`
- Helper functions may be private: `_collect_rss()`, `_make_verdicts()`
- Main entry point: `main()`

**Variables:**
- Lowercase with underscores: `tmpdir`, `body_clean`, `out_path`, `score_start`
- Module-level state: lowercase (e.g., `ccir = load_ccir()`)

**Constants:**
- UPPERCASE_WITH_UNDERSCORES: `DEFAULT_UA`, `DEFAULT_TIMEOUT`, `PROBE_BODY_BYTES`, `OPML_HERE`, `CCIR_PATH`, `OUT`

## Code Style

**Formatting:**
- No explicit linting tool configured (no `.eslintrc`, `.pylintrc`, `pyproject.toml`)
- PEP 8-style line length (no excessive wrapping observed)
- Indentation: 4 spaces (Python standard)
- Blank lines: 2 between module-level definitions, 1 between class methods

**Shebang & Module Header:**
- Every `.py` file starts: `#!/usr/bin/env python3`
- Followed by a comprehensive module docstring using triple quotes
- Module docstring includes: purpose, usage examples (with command-line options), and environment variables

**Example pattern** (`opml/_check.py` lines 1-37):
```python
#!/usr/bin/env python3
"""opml/_check.py — bulk health-check of every feed in opml/feeds.opml.

[Detailed description of purpose, behavior, output format]

Usage::

  python3 opml/_check.py                                  # report to stdout
  python3 opml/_check.py --out data/feed-health.md        # also write to file
  [more options...]

Stdlib only — urllib.request, xml.etree.ElementTree, ...
"""
```

## Import Organization

**Order:**
1. Standard library imports (`os`, `sys`, `unittest`, `urllib.request`, `xml.etree.ElementTree`, etc.)
2. Third-party imports (`feedgen`)
3. Local/project imports (relative imports from sibling modules)

**Style:**
- Multiple stdlib imports on one line separated by commas: `import os, sys, unittest`
- One import per line preferred for clarity in complex imports
- Relative imports within package: `from _util import escape`, `import _check`
- Path manipulation for imports: `sys.path.insert(0, os.path.join(...))`

**Example** (`tests/test_opml_check.py` lines 17-26):
```python
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opml"))
import _check  # noqa: E402
```

## Error Handling

**Pattern: Try-Except with Fallback:**
- Specific exception types caught
- Fallback to safe default or empty value
- Never silent failures without indication

**Example** (`opml/_check.py` lines 73-88):
```python
try:
    req = urllib.request.Request(url, headers={...})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(...)
except urllib.error.HTTPError as e:
    try:
        body = e.read(PROBE_BODY_BYTES) if hasattr(e, "read") else b""
    except Exception:
        body = b""
    return e.code, (e.headers.get("Content-Type", "") if e.headers else ""), body
except Exception as e:
    return "err", f"{type(e).__name__}: {e}", b""
```

**Pattern: None-Safety:**
- Functions handle `None` inputs gracefully
- Example: `escape()` in `bridge/_util.py` (lines 33-38) returns `""` for `None` input rather than raising

**Pattern: Type Validation:**
- Explicit type checking before processing
- Raise `TypeError` for incorrect input types
- Example: `escape()` raises `TypeError` for non-string inputs (except `None`)

## Logging

**Framework:** None. Uses standard output:
- `print()` statements for normal output
- Return values for structured data
- Exception messages embedded in tuples returned by functions

**Pattern: Return Structured Data:**
- Functions return tuples with status info: `(status, reason_string)`, `(emoji, explanation)`
- Example: `classify()` returns `("✅", "HTTP 200, RSS/Atom XML")`

**Pattern: Environment-Based Configuration:**
- No logging config; configuration via environment variables
- Example: `os.environ.get("LLM_BASE_URL", "http://127.0.0.1:8000/v1")`

## Comments

**When to Comment:**
- Explain WHY, not WHAT (the code shows WHAT)
- Clarify non-obvious design decisions
- Document edge cases and defensive patterns
- Explain why certain libraries are used (not stdlib vs. third-party)

**Example** (`opml/_check.py` lines 48-57):
```python
# FreshRSS-default UA-ish: a Chrome UA that FreshRSS can be configured to
# mimic. Adjusts past any common Cloudflare/JS-challenge layers that 403 pure
# bot UAs (curl, wget, Go-http-client). Override per-site via --ua as needed.
#
# Must be pure ASCII: urllib sends the User-Agent header as a latin-1-encoded
# byte string; any non-latin-1 codepoint (e.g. em-dash U+2014) raises
# UnicodeEncodeError on EVERY probe. Keep this string ASCII only.
```

**Docstrings:**
- Every function has a docstring
- Docstrings explain purpose, parameters (implicitly), return value, and behavior
- Example: `escape()` docstring explains None-safety and type validation

**Block Comments:**
- Use `#` for explanations of complex logic
- Example: Classification logic in `classify()` (lines 101-141) includes comments explaining each branch

## Function Design

**Size:** Functions typically 5-50 lines; longer functions well-commented

**Parameters:**
- Positional parameters for essential inputs
- Keyword parameters with defaults for optional config
- Example: `probe(url, ua=DEFAULT_UA, timeout=DEFAULT_TIMEOUT)`

**Return Values:**
- Return tuples for multiple related values: `(status, content_type, body)`
- Return structured dicts for complex data: `{"ccir": "PIR-1", "score": 7, ...}`
- Use `None` for missing data only when explicit about it

## Module Design

**Exports:**
- No explicit `__all__` declaration
- Public functions: not prefixed
- Private helpers: prefixed with underscore: `_collect_rss()`, `_make_verdicts()`

**Single-File Modules:**
- Self-contained logic with main entry point
- Helper functions defined before main entry point
- Example: `bridge/gmail_to_atom.py` has helpers (`load_dotenv`, `dec`, `gmail_search`, `body_text`) before `main()`

**Package Structure:**
- `opml/_check.py`: OPML validation and health checking
- `bridge/*.py`: Email/RSS to Atom bridge converters
- `score/*.py`: Item triage and scoring
- `tests/test_*.py`: Test suite

---

*Convention analysis: 2026-06-24*
