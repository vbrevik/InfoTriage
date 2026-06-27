# Phase 1: Contracts + Monorepo Skeleton — Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 20 (new + modified)
**Analogs found:** 14 / 20 (6 new contracts files have no codebase analog — use RESEARCH.md patterns)

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `libs/contracts/pyproject.toml` | config | — | none (new packaging) | none |
| `libs/contracts/src/contracts/__init__.py` | config/export | — | `bridge/_util.py` (module entry style) | partial |
| `libs/contracts/src/contracts/_item.py` | model | transform | none in codebase | none — use RESEARCH.md Pattern 1 |
| `libs/contracts/src/contracts/_events.py` | model | transform | none in codebase | none — use RESEARCH.md Pattern 2 |
| `libs/contracts/src/contracts/_codec.py` | utility | transform | none in codebase | none — use RESEARCH.md Pattern 3 |
| `libs/contracts/src/contracts/_bus.py` | utility/interface | event-driven | none in codebase | none — use RESEARCH.md Pattern 4 |
| `apps/ingest/gmail_to_atom.py` | utility/script | file-I/O | `bridge/gmail_to_atom.py` (identity move) | exact |
| `apps/ingest/imap_to_atom.py` | utility/script | file-I/O | `bridge/imap_to_atom.py` (identity move) | exact |
| `apps/ingest/yt_to_atom.py` | utility/script | file-I/O | `bridge/yt_to_atom.py` (identity move) | exact |
| `apps/ingest/_util.py` | utility | transform | `bridge/_util.py` (identity move) | exact |
| `apps/triage/triage_score.py` | service/script | request-response | `score/triage_score.py` | exact (path-depth fix) |
| `apps/triage/digest.py` | service/script | batch | `score/digest.py` | exact (path-depth fix) |
| `apps/triage/fever_triage.py` | service/script | request-response | `score/fever_triage.py` | exact (path-depth fix) |
| `apps/triage/sab_html.py` | utility | transform | `score/sab_html.py` (identity move) | exact |
| `apps/opml/_check.py` | utility/script | request-response | `opml/_check.py` (identity move) | exact |
| `apps/opml/feeds.opml` | config/data | — | `opml/feeds.opml` (identity move) | exact |
| `pyproject.toml` (root) | config | — | none (new) | none — use RESEARCH.md Pattern 5 |
| `tests/conftest.py` | config/test | — | none (new) | none — use RESEARCH.md Pattern 5 |
| `tests/test_contracts.py` | test | — | `tests/test_bridge_escape.py` (style) | role-match |
| `tests/test_*.py` (6 migrated) | test | — | current `tests/test_*.py` files | exact (style migration only) |

---

## Pattern Assignments

### `apps/triage/triage_score.py` — path-depth fix (CCIR_PATH + .env load)

**Analog:** `score/triage_score.py`

**Current import + constants block** (`score/triage_score.py` lines 1–19):
```python
#!/usr/bin/env python3
"""InfoTriage scorer — the noise-killer. ..."""
import json, os, sys, argparse, urllib.request, urllib.error

# The triage brain lives in ccir.md (Commander's Critical Information Requirements).
CCIR_PATH = os.path.join(os.path.dirname(__file__), "..", "ccir.md")
```

**Fixed expressions** (two depth changes, both in `triage_score.py`):

| Constant | Current (line) | Fixed |
|----------|---------------|-------|
| `CCIR_PATH` | line 19: `os.path.join(os.path.dirname(__file__), "..", "ccir.md")` | `os.path.join(os.path.dirname(__file__), "..", "..", "ccir.md")` |
| `.env` in `load_dotenv` call | line 43: `os.path.join(os.path.dirname(__file__), "..", ".env")` | `os.path.join(os.path.dirname(__file__), "..", "..", ".env")` |

**No other changes.** All other code in `triage_score.py` moves verbatim.

---

### `apps/triage/digest.py` — path-depth fix (ROOT constant)

**Analog:** `score/digest.py`

**Current import + constants block** (`score/digest.py` lines 17–30):
```python
import os, sys, re, json, time, argparse, datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(__file__))
from triage_score import score_item, load_dotenv                 # noqa: E402
from fever_triage import fever_key, fever, strip_html             # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT  = os.path.join(ROOT, "data", "digests")
STORE = os.path.join(ROOT, "data", "verdicts.jsonl")
```

**Fixed expression** (single change cascades to 4 downstream uses):

| Constant | Current (line) | Fixed |
|----------|---------------|-------|
| `ROOT` | line 24: `os.path.join(os.path.dirname(__file__), "..")` | `os.path.join(os.path.dirname(__file__), "..", "..")` |

**Downstream paths fixed automatically by ROOT change** (no further edits needed):
- line 25: `OUT = os.path.join(ROOT, "data", "digests")` — correct after ROOT fix
- line 26: `STORE = os.path.join(ROOT, "data", "verdicts.jsonl")` — correct after ROOT fix
- line 46: `open(os.path.join(ROOT, "ccir.md"), ...)` — correct after ROOT fix
- line 279: `load_dotenv(os.path.join(ROOT, ".env"))` — correct after ROOT fix

**`sys.path.insert` on line 20** (`sys.path.insert(0, os.path.dirname(__file__))`) — this resolves to `apps/triage/` after re-home, which is correct for intra-app imports. It is redundant when pytest `pythonpath` is configured but is harmless at runtime; leave in place.

---

### `apps/triage/fever_triage.py` — path-depth fix (ENV constant)

**Analog:** `score/fever_triage.py`

**Current import + constants block** (`score/fever_triage.py` lines 15–20):
```python
import os, sys, re, json, time, hashlib, argparse, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from triage_score import llm, score_item, load_dotenv  # noqa: E402

ENV = os.path.join(os.path.dirname(__file__), "..", ".env")
```

**Fixed expression:**

| Constant | Current (line) | Fixed |
|----------|---------------|-------|
| `ENV` | line 20: `os.path.join(os.path.dirname(__file__), "..", ".env")` | `os.path.join(os.path.dirname(__file__), "..", "..", ".env")` |

**`sys.path.insert` on line 17** resolves to `apps/triage/` after re-home — correct for sibling imports. Leave in place.

---

### `apps/ingest/*` and `apps/triage/sab_html.py` and `apps/opml/_check.py` — identity moves

No code changes. Copy files verbatim to new locations. The only changes are in the three `apps/triage/` files above.

**Files moved without change:**
- `bridge/gmail_to_atom.py` → `apps/ingest/gmail_to_atom.py`
- `bridge/imap_to_atom.py` → `apps/ingest/imap_to_atom.py`
- `bridge/yt_to_atom.py` → `apps/ingest/yt_to_atom.py`
- `bridge/_util.py` → `apps/ingest/_util.py`
- `score/sab_html.py` → `apps/triage/sab_html.py`
- `opml/_check.py` → `apps/opml/_check.py`
- `opml/feeds.opml` → `apps/opml/feeds.opml`
- `opml/working.opml` → `apps/opml/working.opml` (if committed; check `.gitignore`)
- `opml/RSS_BRIDGE_NOTES.md` → `apps/opml/RSS_BRIDGE_NOTES.md` (or `docs/`; planner judgment)

---

### `tests/test_opml_check.py` and `tests/test_opml_roundtrip.py` — OPML path fix + pytest migration

**Analog:** `tests/test_opml_check.py` (current)

**Current import + path constant** (`tests/test_opml_check.py` lines 17–28):
```python
import os, shutil, sys, tempfile, unittest, xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opml"))
import _check  # noqa: E402

OPML = os.path.join(os.path.dirname(__file__), "..", "opml", "feeds.opml")
```

**After migration:**
```python
# sys.path.insert removed — resolved via pytest pythonpath config
import _check

OPML = os.path.join(os.path.dirname(__file__), "..", "apps", "opml", "feeds.opml")
```

**OPML path fix** (applies to both test files):

| File | Current expression | Fixed expression |
|------|--------------------|-----------------|
| `tests/test_opml_check.py` line 28 | `os.path.join(..., "..", "opml", "feeds.opml")` | `os.path.join(..., "..", "apps", "opml", "feeds.opml")` |
| `tests/test_opml_roundtrip.py` | `os.path.join(..., "..", "opml", "feeds.opml")` | `os.path.join(..., "..", "apps", "opml", "feeds.opml")` |

**`tests/test_ccir_sync.py`** — OPML path UNCHANGED: `ccir.md` stays at repo root, so `os.path.join(..., "..", "ccir.md")` is still correct.

---

### `tests/test_*.py` (6 files) — pytest migration pattern

**Analog:** All 6 current `tests/test_*.py` files (current `unittest.TestCase` style)

**Before** (current pattern in all 6 test files — exemplified by `tests/test_bridge_escape.py` lines 10–13):
```python
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bridge"))
from _util import escape  # noqa: E402

class TestEscape(unittest.TestCase):
    def test_ascii_alphanumeric_passthrough(self):
        """Plain printable ASCII is unchanged."""
        self.assertEqual(escape("Hello world 123"), "Hello world 123")

if __name__ == "__main__":
    unittest.main()
```

**After** (pytest function style — D-03/D-05):
```python
# No sys.path.insert — resolved via pytest pythonpath in root pyproject.toml
from _util import escape

def test_ascii_alphanumeric_passthrough():
    """Plain printable ASCII is unchanged."""
    assert escape("Hello world 123") == "Hello world 123"
```

**setUp/tearDown → fixture** (from `test_opml_check.py` pattern):
```python
# Before:
class TestEmitWorkingOPML(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

# After — use pytest built-in tmp_path (auto-cleaned):
def test_emit_working_opml_keeps_only_live(tmp_path):
    out_path = tmp_path / "working.opml"
    ...
```

**Manual monkey-patch with try/finally → `monkeypatch` fixture** (from `test_write_bluf.py` lines 24–39):
```python
# Before:
original = triage_score.llm
triage_score.llm = failing_llm
try:
    _, text = write_bluf(...)
finally:
    triage_score.llm = original

# After:
def test_credential_not_in_markdown(monkeypatch):
    monkeypatch.setattr(triage_score, "llm", failing_llm)
    _, text = write_bluf(...)
```

**`assertRaises` → `pytest.raises`:**
```python
# Before:
with self.assertRaises(TypeError):
    escape(bad)

# After:
import pytest
with pytest.raises(TypeError):
    escape(bad)
```

**Drop these from every migrated test file:**
- `if __name__ == "__main__": unittest.main()`
- `sys.path.insert(0, ...)` lines
- `import unittest` (unless still needed for `unittest.mock`)
- `class Test*(unittest.TestCase):` wrapper

---

### `tests/test_contracts.py` — new contracts test file

**Analog:** `tests/test_bridge_escape.py` (function style, after migration)

**House style for new test file** (from `bridge/_util.py` module docstring pattern):
```python
#!/usr/bin/env python3
"""test_contracts.py — tests for libs/contracts: Item, events, codec, bus."""
import hashlib, datetime, zoneinfo
import pytest
from contracts import Item, ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from contracts import to_frontmatter, from_frontmatter
from contracts import InMemoryBus
from pydantic import ValidationError
```

Full test patterns are in RESEARCH.md §"Code Examples" (SHA-256 ID test, codec round-trip, bus tests) — all verified against the live system.

---

### `libs/contracts/src/contracts/_item.py` — new pydantic v2 model

**No codebase analog.** Closest style reference: module-level constants + private module prefix from `score/triage_score.py` and `bridge/_util.py`.

**Use RESEARCH.md Pattern 1 verbatim.** Key house style to apply:
- Private module prefix `_` (matches `_util.py`, `_check.py`)
- Module docstring (matches all existing scripts)
- SCREAMING_SNAKE_CASE for any module constants (not needed here; `id` computation is inline)

---

### `libs/contracts/src/contracts/_events.py` — new pydantic v2 event models

**No codebase analog.** Use RESEARCH.md Pattern 2 verbatim.

---

### `libs/contracts/src/contracts/_codec.py` — new PyYAML codec

**No codebase analog.** Use RESEARCH.md Pattern 3 verbatim.

Security constraint: always `yaml.safe_load`, never `yaml.load` (RESEARCH.md §Security Domain).

---

### `libs/contracts/src/contracts/_bus.py` — new Protocol + InMemoryBus

**No codebase analog.** Use RESEARCH.md Pattern 4 verbatim.

---

### `libs/contracts/src/contracts/__init__.py` — package exports

**Partial analog:** `bridge/_util.py` (single public function exported from a private `_`-prefixed impl).

**House style for `__init__.py`:**
```python
"""contracts — InfoTriage shared schemas, codec, and bus interface."""
from ._item import Item
from ._events import ItemIngested, VerdictReady, SabPublished, FeedUnhealthy
from ._codec import to_frontmatter, from_frontmatter
from ._bus import BusClient, InMemoryBus

__all__ = [
    "Item",
    "ItemIngested", "VerdictReady", "SabPublished", "FeedUnhealthy",
    "to_frontmatter", "from_frontmatter",
    "BusClient", "InMemoryBus",
]
```

---

### `libs/contracts/pyproject.toml` — package definition

**No codebase analog.** Use RESEARCH.md Pattern 6 verbatim.

---

### `pyproject.toml` (root) — pytest config

**No codebase analog.** Use RESEARCH.md Pattern 5 verbatim:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]
```

This replaces all `sys.path.insert` calls in the 6 migrated test files.

---

## Shared Patterns

### Module docstring style
**Source:** `bridge/_util.py` lines 1–18, `score/triage_score.py` lines 1–14, `score/digest.py` lines 1–16
**Apply to:** All new `libs/contracts/src/contracts/` modules
**Pattern:** `#!/usr/bin/env python3` shebang + `"""<module-name> — <one-line description>.\n\n<usage block>."""`

### Private module naming with `_` prefix
**Source:** `bridge/_util.py`, `opml/_check.py`
**Apply to:** `_item.py`, `_events.py`, `_codec.py`, `_bus.py` in `libs/contracts/src/contracts/`
**Pattern:** Implementation modules prefixed `_`; public API exported from `__init__.py`

### SCREAMING_SNAKE_CASE module constants
**Source:** `score/triage_score.py` line 19 (`CCIR_PATH`), `score/digest.py` lines 24–32 (`ROOT`, `OUT`, `STORE`, `OSLO`, `STOP`, `CCIR_ORDER`), `score/fever_triage.py` line 20 (`ENV`)
**Apply to:** Any module-level path or config constants in re-homed scripts (after depth fix), and in new contracts modules if any constants are needed

### `sys.path.insert(0, os.path.dirname(__file__))` for intra-app sibling imports
**Source:** `score/digest.py` line 20, `score/fever_triage.py` line 17
**Apply to:** `apps/triage/digest.py`, `apps/triage/fever_triage.py` — leave these in place (they resolve to `apps/triage/` after re-home and work correctly for runtime; redundant but harmless when pytest `pythonpath` is set)

### `yaml.safe_load` (never `yaml.load`)
**Source:** RESEARCH.md §Security Domain
**Apply to:** `libs/contracts/src/contracts/_codec.py`
**Pattern:** `yaml.safe_load(parts[1])` only — never `yaml.load(text, Loader=yaml.FullLoader)` or any Unsafe loader

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `libs/contracts/src/contracts/_item.py` | model | transform | No pydantic v2 models in codebase today |
| `libs/contracts/src/contracts/_events.py` | model | transform | No pydantic v2 models in codebase today |
| `libs/contracts/src/contracts/_codec.py` | utility | transform | No YAML frontmatter handling in codebase today |
| `libs/contracts/src/contracts/_bus.py` | utility/interface | event-driven | No event bus or Protocol interfaces in codebase today |
| `libs/contracts/pyproject.toml` | config | — | No installable packages in codebase today |
| `pyproject.toml` (root) | config | — | No root pyproject.toml exists today (only `requirements.txt`) |

**For these 6 files, use RESEARCH.md Patterns 1–6 as the implementation template.** All patterns were verified against the live system (PyYAML round-trip, pydantic version, pytest config).

---

## Metadata

**Analog search scope:** `bridge/`, `score/`, `opml/`, `tests/`
**Files scanned:** 15 Python files + directory listings
**Pattern extraction date:** 2026-06-27
