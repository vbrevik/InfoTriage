# Phase 1: Contracts + Monorepo Skeleton — Research

**Researched:** 2026-06-27
**Domain:** Python packaging, pydantic v2 schema design, PyYAML codec, pytest migration, monorepo restructure
**Confidence:** HIGH (codebase-grounded; all critical claims verified against live system)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01** `libs/contracts` is a real installable package with its own `pyproject.toml`; the pydantic v2 dependency is declared there. Apps and tests import it via editable install (`pip install -e libs/contracts`). A root `requirements-dev.txt` (or equivalent) wires the editable install + pytest for local dev.

**D-02** Endpoints/secrets are NOT baked into the package (SPEC prohibition P2) — config comes from `.env` at runtime, never from `libs/contracts`.

**D-03** Migrate the 6 test files from `unittest` → pytest style (functions/fixtures). This is a test-code-only refactor — it does NOT touch pipeline code.

**D-04** Migration is assertion-preserving: no test dropped or weakened, zero coverage lost. The literal "56" is refined to "all migrated tests green, zero coverage lost" — the reported pytest count may differ from the unittest method count (parametrization etc.). Use the coverage-preserving check, not a hard count of 56.

**D-05** pytest is the single canonical runner after migration. Drop `if __name__ == '__main__': unittest.main()` entrypoints and `sys.path.insert` sibling hacks. No dual-run compatibility kept.

**D-06** Re-home scripts under stage-named app dirs: `apps/ingest/` (from `bridge/*`), `apps/triage/` (from `score/*`), `apps/opml/` (from `opml/*`). `libs/contracts/` holds the shared package.

**D-07** Rewrite the tests' `sys.path.insert` targets to the new module locations — or drop them entirely once `contracts` (and the re-homed app modules) resolve via the editable install.

**D-08** At least one re-homed script imports `Item` from `libs/contracts` to satisfy SPEC R5.

**D-09** Codec uses PyYAML for the YAML⇆markdown-frontmatter split with explicit datetime handling (ISO-8601, tz-aware, no precision loss per SPEC R3). Public API: `to_frontmatter(payload: dict) -> str` / `from_frontmatter(text: str) -> dict` (names to be finalized by planner).

**D-10** Bus-client interface is a `typing.Protocol` (structural, no inheritance coupling); in-memory impl satisfies it. Methods cover `publish` / `subscribe` with idempotency keyed on `Item.id`, FIFO per routing key, empty-subscribe no-op (per SPEC R4).

### Claude's Discretion

- Codec library (PyYAML) and bus interface style (`typing.Protocol`) were delegated by the user. D-09/D-10 record the chosen defaults; the planner/researcher may refine exact function/method signatures and whether `python-frontmatter` is cleaner with pydantic `model_dump()`, as long as the SPEC R3/R4 acceptance criteria hold.

### Deferred Ideas (OUT OF SCOPE)

- Real RabbitMQ/aio-pika bus transport → Phase 3 (in-memory impl only now).
- Live Postgres store + JSONB persistence → Phase 2 (codec targets the shape only).
- Splitting `bridge`/`score` into independent containerized apps with their own images → Phase 4+.
- Re-validating mE5-large dedup threshold on held-out corpus → Phase 5.
</user_constraints>

---

## Summary

Phase 1 creates `libs/contracts` — a pip-installable Python package containing an `Item` pydantic v2 model, four event schemas, a PyYAML-based frontmatter↔payload codec, and a `typing.Protocol` bus-client interface with an in-memory implementation. Simultaneously, the flat `bridge/`, `score/`, `opml/` directories are re-homed to `apps/ingest/`, `apps/triage/`, `apps/opml/` and all 6 test files are migrated from `unittest.TestCase` to pytest function style.

The most dangerous part is the re-home: every script that uses `os.path.join(os.path.dirname(__file__), "..", ...)` to reference the repo root will silently reach the wrong location after gaining one extra directory level. There are exactly four places that need a depth fix: `CCIR_PATH` in `triage_score.py`, `ROOT` in `digest.py`, `ENV` in `fever_triage.py`, and two test files' OPML path references. Missing any one of these breaks a test.

The codec and schema design are low-risk: PyYAML 6.0 is already installed and has been verified to round-trip all required data types (Norwegian unicode, tz-aware datetimes, None, nested dicts/lists, `[N]` citation strings) against the live system. Pydantic v2 is already installed. No new runtime packages need to be downloaded.

**Primary recommendation:** Enumerate all `"..", "filename"` path constructions in scripts before touching any file; fix all depth references as a single atomic wave. Then create contracts, then restructure, then migrate tests.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Canonical Item schema | `libs/contracts` | — | Shared across all future apps; single source of truth |
| Event schema validation | `libs/contracts` | — | Bus events are cross-app contracts |
| Frontmatter↔JSONB codec | `libs/contracts` | — | One codec bridges vault-writer (Phase 6) and Postgres (Phase 2) |
| Bus-client interface + in-memory impl | `libs/contracts` | — | Interface lives in contracts; concrete broker impl deferred to Phase 3 |
| Ingest scripts | `apps/ingest/` | `libs/contracts` (Item import) | Re-homed; not yet containerized |
| Triage/scoring scripts | `apps/triage/` | `libs/contracts` (Item import) | Re-homed; not yet event-driven |
| OPML/health scripts | `apps/opml/` | — | Re-homed; feeds.opml moves with _check.py |
| Tests | `tests/` | pytest + conftest | Tests dir stays at root; conftest adds app dirs to sys.path |

---

## Standard Stack

### Core (already installed — no downloads needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.9.2 | Item + event schema validation | Already installed; v2 is the locked choice (D-01, SPEC R1) |
| PyYAML | 6.0.2 | Frontmatter YAML serialization/deserialization | Already installed; safe_load/safe_dump handle all required data types |
| pytest | 8.3.3 | Test runner | Already installed; the locked choice (D-03–D-05) |

[VERIFIED: live system — `python3 -c "import pydantic; print(pydantic.__version__)"` → 2.9.2]
[VERIFIED: live system — `python3 -c "import yaml; print(yaml.__version__)"` → 6.0.2]
[VERIFIED: live system — `python3 -c "import pytest; print(pytest.__version__)"` → 8.3.3]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| setuptools | ≥68 | `pyproject.toml` build backend for editable install | `pip install -e libs/contracts` requires this; already installed via Python 3.13 toolchain |
| hashlib | stdlib | SHA-256 for `Item.id` | Stdlib; no install needed |
| zoneinfo | stdlib | Tz-aware datetime in tests | Stdlib (Python 3.9+); already used in `score/digest.py` |
| typing | stdlib | `Protocol`, `Literal`, `Optional`, `Annotated` | All needed for contracts; stdlib |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@computed_field @property` for Item.id | `@model_validator(mode='after')` setting `self.id` | computed_field is cleaner (read-only, always consistent); model_validator requires mutable model and risks being bypassed on deserialization |
| PyYAML native datetime round-trip | Serialize datetime as ISO-8601 string | Native round-trip verified to work and preserves datetime equality; string approach loses the type after round-trip, requiring callers to re-parse |
| `typing.Protocol` for bus interface | `abc.ABC` / `abc.abstractmethod` | Protocol enables structural subtyping — any class with the right methods satisfies it; ABC requires explicit inheritance, tighter coupling |
| pytest.ini / pyproject.toml `pythonpath` | Root `conftest.py` with `sys.path` inserts | pyproject.toml approach is cleaner (declarative, avoids import-time side effects); both work |

**Installation (no new downloads required — all packages already present):**
```bash
pip install -e libs/contracts   # installs the new contracts package
```

**For a clean dev setup file (requirements-dev.txt or root pyproject.toml dev dependencies):**
```
pydantic>=2.0
PyYAML>=6.0
pytest>=8.0
```

---

## Package Legitimacy Audit

All three packages are established Python ecosystem libraries confirmed installed on the developer's system. The legitimacy seam returns `SUS` due to PyPI download statistics being unavailable (seam is npm-optimized), not due to any real concern.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pydantic | PyPI | 10+ yrs | >200M/mo (industry standard) | github.com/pydantic/pydantic | SUS (download stats unavailable to seam) | Approved — confirmed installed 2.9.2, official repo verified |
| PyYAML | PyPI | 15+ yrs | >200M/mo (ecosystem staple) | github.com/yaml/pyyaml | SUS (download stats unavailable to seam) | Approved — confirmed installed 6.0.2 |
| pytest | PyPI | 15+ yrs | >100M/mo (universal test runner) | github.com/pytest-dev/pytest | SUS (download stats unavailable to seam; "too-new" flag for latest release date, not the package) | Approved — confirmed installed 8.3.3 |

**Packages removed due to [SLOP] verdict:** none

**Note:** The seam's `SUS` verdict for these packages is a false positive arising from PyPI download-count unavailability, not from legitimacy concerns. All three packages are confirmed via Context7 (High reputation source) and are physically installed on the target system.

[VERIFIED: live system — all three packages confirmed installed and functional]

---

## Architecture Patterns

### System Architecture Diagram

```
libs/contracts/
    Item (pydantic v2 BaseModel)
      ├── core: source, source_type, url, title, ts, lang
      ├── content: summary, body_ref
      ├── rich: payload: dict (open — Phase 5 writes scoring keys)
      ├── refs: attachments: list
      └── computed: id = sha256(source_type + "\x00" + url + "\x00" + title)
    
    Events (4 pydantic v2 models)
      ├── ItemIngested: event=Literal["item.ingested"], item_id, source, ts
      ├── VerdictReady: event=Literal["verdict.ready"], item_id, ccir, cnr, score, bucket, why, ts
      ├── SabPublished: event=Literal["sab.published"], pub_ts, snapshot_day, ccir_topics,
      │                 bluf_by_topic, item_refs, total_keep, since_ts
      └── FeedUnhealthy: event=Literal["feed.unhealthy"], feed_url, feed_name, reason, last_ok_at, ts
    
    Codec (PyYAML-based)
      to_frontmatter(payload: dict) → str  (---\n<YAML>\n---\n)
      from_frontmatter(text: str) → dict
    
    Bus Interface (typing.Protocol)
      BusClient.publish(routing_key, item_id, payload) → None
      BusClient.subscribe(routing_key) → list[dict]
      InMemoryBus (concrete impl, satisfies BusClient)
        _queues: dict[str, list[dict]]   # FIFO per routing_key
        _seen: set[str]                  # dedup by item_id

apps/ingest/    ← bridge/* re-homed
apps/triage/    ← score/* re-homed; digest.py imports Item from contracts (D-08)
apps/opml/      ← opml/* re-homed; feeds.opml moves here

tests/          ← stays at root; 6 files migrated to pytest function style
    conftest.py (new) or pyproject.toml pythonpath  ← replaces sys.path.insert hacks
```

### Recommended Project Structure

```
libs/
└── contracts/
    ├── pyproject.toml        # name="contracts", deps: pydantic>=2.0, PyYAML>=6.0
    └── src/
        └── contracts/
            ├── __init__.py   # exports: Item, ItemIngested, VerdictReady, SabPublished, FeedUnhealthy, BusClient, InMemoryBus, to_frontmatter, from_frontmatter
            ├── _item.py      # Item BaseModel
            ├── _events.py    # 4 event models
            ├── _codec.py     # to_frontmatter / from_frontmatter
            └── _bus.py       # BusClient Protocol + InMemoryBus

apps/
├── ingest/                   # bridge/* re-homed (no __init__.py — not a package)
│   ├── gmail_to_atom.py
│   ├── imap_to_atom.py
│   ├── yt_to_atom.py
│   └── _util.py
├── triage/                   # score/* re-homed
│   ├── triage_score.py       # CCIR_PATH depth fix: "..", "..", "ccir.md"
│   ├── digest.py             # ROOT depth fix: "..", ".."
│   ├── fever_triage.py       # ENV depth fix: "..", "..", ".env"
│   └── sab_html.py
└── opml/                     # opml/* re-homed
    ├── _check.py             # OPML_HERE path unchanged (sibling feeds.opml moves with it)
    ├── feeds.opml
    └── working.opml

tests/
├── conftest.py               # NEW: pytest sys.path setup + shared fixtures
├── test_bridge_escape.py     # migrated to pytest functions
├── test_ccir_sync.py         # migrated
├── test_opml_check.py        # migrated + OPML path fix → "apps", "opml"
├── test_opml_roundtrip.py    # migrated + OPML path fix → "apps", "opml"
├── test_score_parse.py       # migrated
├── test_write_bluf.py        # migrated
└── test_contracts.py         # NEW: Item, events, codec, bus tests

pyproject.toml (root)         # [tool.pytest.ini_options] pythonpath, testpaths
```

**Note on src-layout vs flat layout:** The `src/contracts/` layout is recommended because it prevents accidental imports from the repo root during tests (forces the installed package to be on sys.path). A flat layout (`libs/contracts/contracts/__init__.py`) also works and is simpler if the team prefers it.

### Pattern 1: Item Model with Computed SHA-256 ID

```python
# Source: pydantic/pydantic docs — computed_field + AwareDatetime
# libs/contracts/src/contracts/_item.py
import hashlib
from typing import Optional
from pydantic import AwareDatetime, BaseModel, computed_field


class Item(BaseModel):
    """Canonical information item — single source of truth across all apps."""

    # Core
    source: str           # human-readable source name ("NRK Nyheter")
    source_type: str      # machine-readable type ("rss", "imap", "yt")
    url: str = ""         # empty string when absent (per SPEC R1)
    title: str
    ts: AwareDatetime     # requires tz-aware — naive datetime raises ValidationError
    lang: str

    # Content
    summary: Optional[str] = None
    body_ref: Optional[str] = None

    # Rich / open
    payload: dict = {}    # open dict — Phase 5 writes ccir, cnr, score, bucket, why
    attachments: list = []

    @computed_field
    @property
    def id(self) -> str:
        """SHA-256 of normalized source_type + url + title. Content-stable dedup key."""
        raw = f"{self.source_type}\x00{self.url}\x00{self.title}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

[CITED: https://github.com/pydantic/pydantic/blob/main/docs/concepts/fields.md — computed_field with property]

### Pattern 2: Event Schemas with Literal Discriminators

```python
# Source: pydantic/pydantic docs — Literal types for routing discriminator
# libs/contracts/src/contracts/_events.py
from typing import Literal, Optional
from pydantic import AwareDatetime, BaseModel


class ItemIngested(BaseModel):
    event: Literal["item.ingested"]
    item_id: str          # sha256 hex — FK to Item
    source: str
    ts: AwareDatetime


class VerdictReady(BaseModel):
    event: Literal["verdict.ready"]
    item_id: str
    ccir: Optional[str]                           # None = not CCIR-relevant
    cnr: Literal["I", "II", "Routine"]
    score: int                                    # 0–10
    bucket: Literal["keep", "maybe", "skip"]
    why: str
    ts: AwareDatetime


class SabPublished(BaseModel):
    event: Literal["sab.published"]
    pub_ts: AwareDatetime
    snapshot_day: str                             # ISO-8601 date string, e.g. "2026-06-27"
    ccir_topics: list[str]
    bluf_by_topic: dict[str, str]                 # topic_key → BLUF paragraph with [N] refs
    item_refs: list[dict]                         # {item_id, ccir, cnr, n, title, source, url, ts}
    total_keep: int
    since_ts: Optional[AwareDatetime]             # None = full-corpus SAB


class FeedUnhealthy(BaseModel):
    event: Literal["feed.unhealthy"]
    feed_url: str
    feed_name: str
    reason: str            # human-readable, ≤ 120 chars (UI-SPEC requirement)
    last_ok_at: Optional[AwareDatetime]           # None = never seen healthy
    ts: AwareDatetime
```

[CITED: https://github.com/pydantic/pydantic/blob/main/docs/api/standard_library_types.md — AwareDatetime]

### Pattern 3: Frontmatter Codec (PyYAML round-trip)

```python
# Source: PyYAML docs — safe_dump/safe_load with allow_unicode
# libs/contracts/src/contracts/_codec.py
import yaml


def to_frontmatter(payload: dict) -> str:
    """Serialize payload dict to YAML frontmatter block (with --- delimiters).

    Preserves: tz-aware datetime (as YAML timestamp with UTC offset),
    Norwegian unicode, None→null, nested dicts/lists, [N] citation strings.
    """
    body = yaml.safe_dump(payload, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def from_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from text, returning payload dict.

    Inverse of to_frontmatter. Datetime values are restored as datetime objects
    with UTC-offset tzinfo (ZoneInfo name is not preserved — this is acceptable
    per SPEC R3 which requires no precision loss, not tzinfo type preservation).
    """
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"No YAML frontmatter found in text: {text[:80]!r}")
    return yaml.safe_load(parts[1]) or {}
```

**Verified behavior (live system test):**
- Norwegian unicode (`Ø`, `æ`, `å`) → preserved byte-for-byte [VERIFIED: live test]
- `datetime(2026, 6, 27, 10, 30, 45, 123456, tzinfo=ZoneInfo("Europe/Oslo"))` → YAML: `2026-06-27 10:30:45.123456+02:00` → back to `datetime(..., tzinfo=UTC+02:00)`, `ts == original` is `True` [VERIFIED: live test]
- `None` → `null` → `None` [VERIFIED: live test]
- Nested dicts and lists → structurally identical [VERIFIED: live test]
- `[N]` citation strings → preserved verbatim in string values; quoted in list values but load correctly [VERIFIED: live test]

### Pattern 4: Bus-Client Interface (typing.Protocol)

```python
# Source: PEP 544 / typing.python.org protocols reference
# libs/contracts/src/contracts/_bus.py
from typing import Protocol, runtime_checkable


@runtime_checkable
class BusClient(Protocol):
    """Transport-swappable bus interface. In-memory now; AMQP (Phase 3) later."""

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        """Publish payload to routing_key. Idempotent: re-publishing same item_id is a no-op."""
        ...

    def subscribe(self, routing_key: str) -> list[dict]:
        """Return all payloads for routing_key in FIFO order. Returns [] if queue empty."""
        ...


class InMemoryBus:
    """Concrete BusClient impl for in-process use. Not thread-safe (Phase 1 scope)."""

    def __init__(self) -> None:
        self._queues: dict[str, list[dict]] = {}
        self._seen: set[str] = set()

    def publish(self, routing_key: str, item_id: str, payload: dict) -> None:
        if item_id in self._seen:
            return                                # dedup: same item_id → no-op
        self._seen.add(item_id)
        self._queues.setdefault(routing_key, []).append(payload)

    def subscribe(self, routing_key: str) -> list[dict]:
        return list(self._queues.get(routing_key, []))  # empty queue → [] (no-op)
```

[CITED: https://typing.python.org/en/latest/reference/protocols.html — Protocol structural subtyping]

### Pattern 5: pytest Config (replaces sys.path.insert hacks)

```toml
# Root pyproject.toml — replaces per-test sys.path.insert
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]
```

With this config, `import digest`, `import _check`, `from _util import escape` work in test files without any `sys.path.insert`. The `contracts` package is importable via the editable install.

[CITED: https://docs.pytest.org/en/stable/ — pythonpath configuration option]

### Pattern 6: pyproject.toml for libs/contracts

```toml
# libs/contracts/pyproject.toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "contracts"
version = "0.1.0"
description = "InfoTriage shared schemas, codec, and bus interface"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "PyYAML>=6.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

Install: `pip install -e libs/contracts`

[CITED: https://setuptools.pypa.io/en/latest/userguide/development_mode.html — editable installs with pyproject.toml]

### Pattern 7: pytest Migration (unittest → function-based)

Before (current pattern in 6 test files):
```python
import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opml"))
import _check

class TestClassify(unittest.TestCase):
    def test_200_rss_xml_is_live(self):
        self.assertEqual(
            _check.classify((200, "application/rss+xml", b'<?xml ...')),
            ("✅", "HTTP 200, RSS/Atom XML"))

if __name__ == "__main__":
    unittest.main()
```

After (pytest function style — D-03/D-05):
```python
import _check  # resolved via pytest pythonpath config

def test_200_rss_xml_is_live():
    assert _check.classify((200, "application/rss+xml", b'<?xml ...')) == ("✅", "HTTP 200, RSS/Atom XML")
```

**setUp/tearDown → fixture pattern:**
```python
# Before:
class TestEmitWorkingOPML(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

# After:
import pytest

@pytest.fixture
def tmpdir(tmp_path):  # tmp_path is a built-in pytest fixture — auto-cleaned
    return tmp_path

def test_emit_working_opml_keeps_only_live(tmpdir):
    out_path = tmpdir / "working.opml"
    _check.emit_working_opml(results, str(out_path), "2026-06-27")
    ...
```

**Monkey-patch pattern for LLM mock (test_write_bluf.py):**
```python
# Before (manual restore with try/finally):
def test_credential_not_in_markdown(self):
    original = triage_score.llm
    def failing_llm(msgs, max_tokens=400):
        raise RuntimeError("auth failed: GMAIL_APP_PASSWORD=abcd1234")
    triage_score.llm = failing_llm
    try:
        _, text = write_bluf(...)
    finally:
        triage_score.llm = original

# After (monkeypatch fixture — auto-restored after test):
def test_credential_not_in_markdown(monkeypatch):
    def failing_llm(msgs, max_tokens=400):
        raise RuntimeError("auth failed: GMAIL_APP_PASSWORD=abcd1234")
    monkeypatch.setattr(triage_score, "llm", failing_llm)
    _, text = write_bluf(...)
    assert "abcd1234" not in text
```

**assertRaises → pytest.raises:**
```python
# Before:
with self.assertRaises(TypeError, msg=f"expected TypeError for {bad!r}"):
    escape(bad)

# After:
import pytest
with pytest.raises(TypeError):
    escape(bad)
```

[CITED: https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/unittest.rst]

### Anti-Patterns to Avoid

- **Hard-coding test count 56:** D-04 explicitly says coverage-preserving, not "56 passed". Parametrized tests expand the count; consolidated setup tests might reduce it. Gate on coverage, not arithmetic.
- **Putting `id` as a regular settable field with no computation:** This allows callers to construct an Item with an arbitrary (wrong) id, breaking dedup. Use `@computed_field @property`.
- **Serializing datetime as ISO-8601 string in the codec:** While technically round-trippable, PyYAML's native datetime handling is more correct (loads back as actual datetime, not string). Verified to work correctly.
- **Using `python-frontmatter` library:** Not installed; PyYAML is already available and tested. The `python-frontmatter` library is an alternative but not needed.
- **Making app dirs (`apps/ingest/`, `apps/triage/`, `apps/opml/`) into installable packages:** Premature. They're plain script directories until Phase 4 containerization. A `pyproject.toml pythonpath` config handles test imports without packaging.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema validation with helpful errors | Custom `__init__` type checks | pydantic v2 `BaseModel` | pydantic gives ValidationError with field-level details, coercion, JSON Schema — hand-rolled checks give cryptic AttributeErrors |
| Datetime serialization | Custom strftime/strptime logic | PyYAML native datetime handling + `AwareDatetime` | PyYAML handles UTC offsets, microseconds; pydantic AwareDatetime enforces tz-awareness at validation time |
| Structural interfaces without inheritance | ABC base classes | `typing.Protocol` | Protocol requires no registration or inheritance — any conforming class works. ABC adds coupling that breaks the swap pattern |
| Test environment path setup | `sys.path.insert` in every test file | `[tool.pytest.ini_options] pythonpath` | Declarative, centralized, invisible to test code |

**Key insight:** pydantic v2's `@computed_field @property` is the canonical way to derive a field from other fields without storing it separately. It appears in `model_dump()` output, is included in JSON Schema, and is always consistent.

---

## Critical File Change Inventory

> This section documents every path-depth fix required when scripts move from flat dirs to `apps/<subdir>/`. Missing one causes a silent wrong-path failure.

### Path Depth Changes in Re-Homed Scripts

Scripts currently use `os.path.join(os.path.dirname(__file__), "..", ...)` to reach the repo root. After gaining one extra directory level (from `score/` to `apps/triage/`), **every `".."` that was reaching the repo root must become `"..",".."`**.

| File (before → after) | Line | Current path expression | Fixed path expression |
|----------------------|------|------------------------|----------------------|
| `score/triage_score.py` → `apps/triage/triage_score.py` | CCIR_PATH | `os.path.join(os.path.dirname(__file__), "..", "ccir.md")` | `os.path.join(os.path.dirname(__file__), "..", "..", "ccir.md")` |
| `score/triage_score.py` → `apps/triage/triage_score.py` | load_dotenv call | `os.path.join(os.path.dirname(__file__), "..", ".env")` | `os.path.join(os.path.dirname(__file__), "..", "..", ".env")` |
| `score/digest.py` → `apps/triage/digest.py` | ROOT | `os.path.join(os.path.dirname(__file__), "..")` | `os.path.join(os.path.dirname(__file__), "..", "..")` |
| `score/fever_triage.py` → `apps/triage/fever_triage.py` | ENV | `os.path.join(os.path.dirname(__file__), "..", ".env")` | `os.path.join(os.path.dirname(__file__), "..", "..", ".env")` |

**What ROOT affects in digest.py** (single fix, multiple downstream paths):
- `OUT = os.path.join(ROOT, "data", "digests")`
- `STORE = os.path.join(ROOT, "data", "verdicts.jsonl")`
- `open(os.path.join(ROOT, "ccir.md"), ...)` (the CCIR drift guard)
- `load_dotenv(os.path.join(ROOT, ".env"))` in `main()`

### Path Changes in Test Files

| Test file | Current path expression | Fixed path expression |
|-----------|------------------------|----------------------|
| `tests/test_opml_check.py` | `os.path.join(..., "..", "opml", "feeds.opml")` | `os.path.join(..., "..", "apps", "opml", "feeds.opml")` |
| `tests/test_opml_roundtrip.py` | `os.path.join(..., "..", "opml", "feeds.opml")` | `os.path.join(..., "..", "apps", "opml", "feeds.opml")` |
| `tests/test_ccir_sync.py` | `os.path.join(..., "..", "ccir.md")` | **UNCHANGED** — `ccir.md` stays at repo root |

### Imports in Re-Homed Scripts (bridge/ → apps/ingest/)

The three bridge scripts use `from _util import escape` with no sys.path manipulation. This works because Python adds the script's own directory to sys.path when the script is run directly. After re-home to `apps/ingest/`, this behavior is unchanged (scripts still run from their own directory at runtime). For test imports, `pythonpath = ["apps/ingest"]` in pytest config handles it.

### Intra-App Imports in score/ → apps/triage/

`digest.py` uses:
```python
sys.path.insert(0, os.path.dirname(__file__))
from triage_score import score_item, load_dotenv
from fever_triage import fever_key, fever, strip_html
```

After re-home: `os.path.dirname(__file__)` resolves to `apps/triage/` — correct. The `sys.path.insert` remains valid and functional. With `pythonpath = ["apps/triage"]` in pytest config, these imports also work during testing (the sys.path.insert in digest.py is redundant but harmless when pytest adds the same path).

---

## Common Pitfalls

### Pitfall 1: Path Depth Bug (Highest Risk)

**What goes wrong:** Script at `apps/triage/triage_score.py` constructs `os.path.join(os.path.dirname(__file__), "..", "ccir.md")` → resolves to `apps/ccir.md` (doesn't exist). Script runs but loads fallback CCIR text instead of the actual taxonomy. Tests pass (CCIR sync test imports digest which has its own path), but the live pipeline silently uses wrong data.

**Why it happens:** The move from `score/triage_score.py` (depth=1 below root) to `apps/triage/triage_score.py` (depth=2 below root) adds one directory level. Every `".."` that was reaching root now reaches `apps/`.

**How to avoid:** Fix all four path expressions in the first wave, before anything else. See the Critical File Change Inventory table above.

**Warning signs:** `load_ccir()` returns the fallback string "(no ccir.md found — ...)" instead of the actual taxonomy; CCIR sync test fails if ccir.md path in digest.py is wrong.

### Pitfall 2: pytest `pythonpath` Not Configured

**What goes wrong:** After removing `sys.path.insert` from test files (D-05, D-07), all imports of `digest`, `_check`, `triage_score`, `_util` fail with `ModuleNotFoundError`.

**Why it happens:** Without `sys.path.insert` and without `pythonpath` in pytest config, Python cannot find modules in `apps/triage/`, `apps/opml/`, `apps/ingest/`.

**How to avoid:** Add to root `pyproject.toml` (or `pytest.ini`):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["apps/triage", "apps/opml", "apps/ingest"]
```

**Warning signs:** `ModuleNotFoundError: No module named 'digest'` or similar on first `pytest tests/` run.

### Pitfall 3: Editable Install Not Active

**What goes wrong:** `from contracts import Item` raises `ModuleNotFoundError` because the editable install was not run in the active environment.

**Why it happens:** `pip install -e libs/contracts` installs into the current Python environment. If the developer uses multiple envs/conda envs, they may run tests in an environment where the install hasn't been done.

**How to avoid:** Document the setup step in requirements-dev.txt or in a `make install-dev` target. Verify with `python3 -c "from contracts import Item; print(Item.__module__)"` before running tests.

**Warning signs:** `ModuleNotFoundError: No module named 'contracts'` on test run.

### Pitfall 4: pytest Count vs "56 Tests"

**What goes wrong:** Someone writes `assert "56 passed" in pytest_output` as the acceptance criterion and fails because parametrized tests expand the count.

**Why it happens:** D-04 explicitly refined the acceptance from "56 tests" to "all tests green, zero coverage lost". unittest methods and pytest tests are not 1:1.

**How to avoid:** The acceptance check for R5 should be `pytest tests/ --tb=short` exits 0 (no failures), not that exactly 56 tests ran. If parametrization expands tests, more than 56 may run — that's fine.

**Warning signs:** Plan task says "verify 56 tests pass" rather than "verify pytest exits 0 with zero failures".

### Pitfall 5: Item.id in model_dump() Round-Trip

**What goes wrong:** Code does `Item.model_validate(item.model_dump())` and passes the serialized `id` field back as input, then checks `new_item.id == original_item.id`. This works (both are computed from the same source fields) but the intent could be misread as "id is stored and re-validated".

**Why it doesn't matter:** `@computed_field @property` for `id` means it is always recomputed from `source_type + url + title`. The id in `model_dump()` output is correct, but it is ignored during `model_validate()` (treated as an extra field). The reconstructed item will have the same id because the source fields are the same.

**How to avoid:** In tests, verify that `Item.model_validate({"source_type": "rss", "url": "http://x", "title": "t", ...}).id == expected_sha256` — do not pass `id` explicitly.

### Pitfall 6: AwareDatetime Rejects Naive Datetimes

**What goes wrong:** Constructing `Item(ts=datetime.datetime(2026, 6, 27, 10, 0, 0))` (naive datetime) raises `ValidationError`.

**Why it happens:** pydantic v2's `AwareDatetime` type enforces timezone awareness at validation time. This is intentional — the SPEC requires all datetimes to be tz-aware.

**How to avoid:** All Item construction must use tz-aware datetimes: `datetime.datetime.now(tz=datetime.timezone.utc)` or `datetime.datetime(2026, 6, 27, 10, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Oslo"))`. All test fixtures must use tz-aware datetimes.

**Warning signs:** `ValidationError: ts: Value error, Input should have timezone info` during construction.

### Pitfall 7: score/ Has No _util.py (CONTEXT.md Inaccuracy)

**What goes wrong:** Plan assumes `score/_util.py` exists and needs to be moved to `apps/triage/_util.py`. It does not exist.

**Why it happens:** CONTEXT.md §"Reusable Assets" says "`score/_util.py` — shared helper already imported by `digest.py` + `fever_triage.py`". This is incorrect. `ls score/` shows no `_util.py`. The only `_util.py` is in `bridge/` (HTML escape for Atom XML).

**How to avoid:** Plan the re-home based on actual file listings, not CONTEXT.md assertions. The re-home inventory is:
- `bridge/*` (4 files: gmail_to_atom.py, imap_to_atom.py, yt_to_atom.py, _util.py) → `apps/ingest/`
- `score/*` (4 files: triage_score.py, digest.py, fever_triage.py, sab_html.py) → `apps/triage/`
- `opml/*` (3 files: _check.py, feeds.opml, working.opml, plus RSS_BRIDGE_NOTES.md) → `apps/opml/`

[VERIFIED: live system — `ls bridge/ score/ opml/`]

---

## Code Examples

### SHA-256 ID Verification Test

```python
# tests/test_contracts.py
import hashlib, datetime, zoneinfo, pytest
from contracts import Item
from pydantic import ValidationError

TS = datetime.datetime(2026, 6, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)


def test_item_id_deterministic():
    """Same source_type+url+title → same id (idempotent)."""
    a = Item(source="NRK", source_type="rss", url="https://nrk.no/1", title="Test", ts=TS, lang="no")
    b = Item(source="NRK", source_type="rss", url="https://nrk.no/1", title="Test", ts=TS, lang="no")
    assert a.id == b.id


def test_item_no_url_constructs():
    """url is optional — empty string in hash when absent."""
    item = Item(source="NRK", source_type="rss", url="", title="Test", ts=TS, lang="no")
    expected = hashlib.sha256("rss\x00\x00Test".encode()).hexdigest()
    assert item.id == expected


def test_item_missing_required_field_raises():
    """Omitting a required field raises ValidationError."""
    with pytest.raises(ValidationError):
        Item(source="NRK", source_type="rss", url="", ts=TS, lang="no")  # missing title
```

### Codec Round-Trip Test

```python
# tests/test_contracts.py (continued)
import datetime, zoneinfo
from contracts import to_frontmatter, from_frontmatter

def test_codec_round_trip():
    """Full round-trip: nested dict/list, None, Norwegian unicode, tz-aware datetime, [N] marker."""
    oslo = zoneinfo.ZoneInfo("Europe/Oslo")
    payload = {
        "ts": datetime.datetime(2026, 6, 27, 10, 30, 45, tzinfo=oslo),
        "bluf": "Russland angrep [1] kritisk infrastruktur [2].",
        "nested": {"ccir": "PIR-1", "cnr": "I"},
        "refs": ["[1] NRK Nyheter", "[2] BBC News"],
        "nothing": None,
        "name": "Åse Æriksen Ø-test",
    }
    text = to_frontmatter(payload)
    assert text.startswith("---\n")
    result = from_frontmatter(text)

    assert result["ts"] == payload["ts"]       # datetime VALUE preserved (UTC offset matches)
    assert result["bluf"] == payload["bluf"]   # [N] citation markers preserved
    assert result["nested"] == payload["nested"]
    assert result["refs"] == payload["refs"]
    assert result["nothing"] is None
    assert result["name"] == payload["name"]   # Norwegian unicode
```

### Bus Tests

```python
# tests/test_contracts.py (continued)
from contracts import InMemoryBus

def test_bus_dedup():
    """Re-publishing same item_id is a no-op."""
    bus = InMemoryBus()
    bus.publish("item.ingested", item_id="abc123", payload={"n": 1})
    bus.publish("item.ingested", item_id="abc123", payload={"n": 2})  # ignored
    msgs = bus.subscribe("item.ingested")
    assert len(msgs) == 1
    assert msgs[0]["n"] == 1


def test_bus_fifo():
    """Messages delivered in publish order (FIFO per routing_key)."""
    bus = InMemoryBus()
    bus.publish("item.ingested", item_id="id1", payload={"n": 1})
    bus.publish("item.ingested", item_id="id2", payload={"n": 2})
    msgs = bus.subscribe("item.ingested")
    assert [m["n"] for m in msgs] == [1, 2]


def test_bus_empty_subscribe_no_op():
    """Subscribe on empty queue returns [] (non-blocking no-op)."""
    bus = InMemoryBus()
    assert bus.subscribe("item.ingested") == []
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sys.path.insert(0, "../sibling")` in test files | `pythonpath` in pyproject.toml / conftest.py | pytest ~3.0 (2017) | No path manipulation in test source |
| `abc.ABC` for interfaces | `typing.Protocol` | Python 3.8 (2019) | Structural subtyping; no inheritance coupling |
| Pydantic v1 `@validator` / `class Config` | pydantic v2 `@field_validator` / `model_config = ConfigDict(...)` | pydantic v2 (2023) | ~50x faster; cleaner API; `@computed_field` for derived properties |
| `unittest.TestCase` class-based tests | `def test_foo():` function-based | pytest has supported this since v1 | Simpler, no class boilerplate, better error messages |

**Deprecated/outdated:**
- `unittest.TestCase.setUp/tearDown`: Replaced by `@pytest.fixture` with `yield` and the built-in `tmp_path` fixture.
- `if __name__ == '__main__': unittest.main()`: Removed per D-05; pytest is the only runner.
- `sys.path.insert(0, ...)` in test files: Replaced by pytest's `pythonpath` configuration.
- pydantic v1 `Optional[str]` = required (can be None): In v2, `Optional[str]` without default is still required. Use `Optional[str] = None` for optional fields.

---

## Runtime State Inventory

> This phase is not a rename/refactor phase in the sense of string replacement across runtime state. It is a file-system restructure + package creation. Runtime state inventory is SKIPPED.
>
> **Why not applicable:** No stored data uses the directory names `bridge/`, `score/`, or `opml/` as keys or identifiers. No external services are configured with these paths. The scripts are run ad-hoc via cron — cron entries reference full absolute paths or scripts from the repo root, which should be updated independently when the scripts move.
>
> **Operator note:** If any cron jobs or launchd plists reference the old paths (`bridge/`, `score/`, `opml/`), those will need updating. This is out of scope for Phase 1 but should be called out in the cutover notes.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `score/_util.py` does NOT exist — only `bridge/_util.py` exists | Critical File Change Inventory | Planner adds a non-existent file to the move list; low risk (would just skip a missing file) |
| A2 | `opml/working.opml` should move with `opml/feeds.opml` to `apps/opml/` | Standard Stack - project structure | If working.opml is a generated artifact that shouldn't be committed, it stays where it is (gitignored) |
| A3 | `opml/RSS_BRIDGE_NOTES.md` should move to `apps/opml/` | Standard Stack - project structure | It might belong in `docs/` instead; planner judgment call |
| A4 | `sab_html.py` in `score/` re-homes to `apps/triage/` | Standard Stack - project structure | It might belong in `apps/brief/` (it generates SAB HTML); but it's just a re-home, not a restructure, so `apps/triage/` is defensible |
| A5 | The PyPI legitimacy seam's "SUS" verdict for pydantic/PyYAML/pytest is a false positive | Package Legitimacy Audit | If somehow wrong, all three packages are physically installed on the system — actual risk is zero |

---

## Open Questions

1. **`sab_html.py` destination in apps/**
   - What we know: It generates SAB HTML, logically belongs more to the "brief" app than "triage".
   - What's unclear: Phase 4+ splits apps into their own containers. The re-home here is temporary. Does it matter which app dir it goes to?
   - Recommendation: Re-home to `apps/triage/` (current score/ peer) for consistency; note it will move again in Phase 4+.

2. **conftest.py vs pyproject.toml pythonpath**
   - What we know: Both approaches work; pyproject.toml is cleaner.
   - What's unclear: Does the project already have a root `pyproject.toml`? (Currently no — only a `requirements.txt`.)
   - Recommendation: Create a root `pyproject.toml` with `[tool.pytest.ini_options]` for pytest config. This is also the place to declare dev dependencies.

3. **`working.opml` gitignore status**
   - What we know: `working.opml` exists in `opml/` and appears to be a generated output (the result of running `_check.py --emit-working`).
   - What's unclear: Is it committed and should move, or is it gitignored and will be regenerated?
   - Recommendation: Check `.gitignore`; if gitignored, it stays where it is. If committed, move to `apps/opml/`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.13.5 | — |
| pydantic | contracts Item/events | ✓ | 2.9.2 | — |
| PyYAML | contracts codec | ✓ | 6.0.2 | — |
| pytest | test runner | ✓ | 8.3.3 | — |
| setuptools | editable install | ✓ | bundled with Python 3.13 | — |
| pip | editable install | ✓ | system pip | — |

[VERIFIED: live system — all dependencies confirmed installed]

**Missing dependencies with no fallback:** none

**Missing dependencies with fallback:** none

**Key note:** `python-frontmatter` is NOT installed (`pip show python-frontmatter` → not found). PyYAML is used instead per D-09. No action needed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.3 |
| Config file | `pyproject.toml` (to be created at repo root) — `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ --tb=short` |

### Phase Requirements → Test Map

| ID | Behavior | Test Type | Automated Command | File |
|----|----------|-----------|-------------------|------|
| R1 | Same source_type+url+title → same id | unit | `pytest tests/test_contracts.py::test_item_id_deterministic -x` | ❌ Wave 0 |
| R1 | No-url item constructs successfully | unit | `pytest tests/test_contracts.py::test_item_no_url_constructs -x` | ❌ Wave 0 |
| R1 | Missing required field → ValidationError | unit | `pytest tests/test_contracts.py::test_item_missing_required_field_raises -x` | ❌ Wave 0 |
| R2 | Each event model validates well-formed payload | unit | `pytest tests/test_contracts.py -k "event" -x` | ❌ Wave 0 |
| R2 | Missing required event field → ValidationError | unit | `pytest tests/test_contracts.py -k "event_missing" -x` | ❌ Wave 0 |
| R3 | Codec round-trip (nested/None/unicode/datetime/[N]) | unit | `pytest tests/test_contracts.py::test_codec_round_trip -x` | ❌ Wave 0 |
| R4 | Bus dedup by item_id | unit | `pytest tests/test_contracts.py::test_bus_dedup -x` | ❌ Wave 0 |
| R4 | Bus FIFO per routing_key | unit | `pytest tests/test_contracts.py::test_bus_fifo -x` | ❌ Wave 0 |
| R4 | Empty subscribe is no-op | unit | `pytest tests/test_contracts.py::test_bus_empty_subscribe_no_op -x` | ❌ Wave 0 |
| R5 | All existing 56 tests remain green after restructure | regression | `pytest tests/ --tb=short` | ✓ (migrated) |
| R5 | No apps/* package imports another apps/* package | boundary check | `grep -r "from apps\." apps/ | grep -v contracts` exits non-zero | ❌ Wave 0 |
| R6 | Three stale doc claims corrected | smoke | `grep -L "imap_to_atom.py" docs/ARCHITECTURE.md` etc. | manual |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q` (fast — all tests are unit-level, < 1s total)
- **Per wave merge:** `pytest tests/ --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps (files that must be created before implementation begins)

- [ ] `tests/test_contracts.py` — covers R1 Item tests, R2 event tests, R3 codec tests, R4 bus tests
- [ ] `tests/conftest.py` — shared fixtures (or replace by `pyproject.toml pythonpath`)
- [ ] `pyproject.toml` at repo root — `[tool.pytest.ini_options]` with `pythonpath` and `testpaths`
- [ ] `libs/contracts/pyproject.toml` — package definition
- [ ] `libs/contracts/src/contracts/__init__.py` — package exports

---

## Security Domain

`security_enforcement` is not explicitly set in `.planning/config.json`; treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth in contracts package |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | No access control |
| V5 Input Validation | yes | pydantic v2 validates all Item/event fields at construction; ValidationError on invalid input |
| V6 Cryptography | partial | SHA-256 used for id computation (hashlib stdlib — not hand-rolled) |
| V13 API | no | No API surface in this phase |

### Known Threat Patterns for Python Schema / Codec Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Injection via YAML payload (YAML bombs, unsafe load) | Tampering | Use `yaml.safe_load` exclusively — never `yaml.load(text, Loader=yaml.UnsafeLoader)` |
| Secret leakage via contracts package | Information Disclosure | D-02/SPEC P2 enforced: no hardcoded endpoints or credentials in `libs/contracts`; all config from `.env` at runtime |
| Arbitrary payload in `payload: dict` | Tampering | `payload` is an open dict by design (extensible for Phase 5); validation of payload contents is Phase 5's responsibility, not the contract |
| sha256 collision for item dedup | Spoofing | SHA-256 collision resistance is industry-standard; acceptable for dedup use case |

**Critical:** The codec uses `yaml.safe_load` (not `yaml.load`). This must be enforced in code review. `yaml.safe_load` disables Python object construction from YAML, preventing arbitrary code execution via crafted frontmatter.

---

## Sources

### Primary (MEDIUM confidence — Context7, High-reputation sources)

- `/pydantic/pydantic` (Context7) — computed_field, AwareDatetime, model_validator, Optional fields, ValidationError patterns
- `/yaml/pyyaml` (Context7) — custom datetime handling, yaml.safe_dump/safe_load
- `/pytest-dev/pytest` (Context7) — unittest migration, pythonpath config, monkeypatch fixture

### Secondary (MEDIUM confidence — live system verification)

- Live system tests: PyYAML round-trip with Norwegian unicode, tz-aware datetime, None, [N] markers — all VERIFIED in this session
- Live system: `pip show pydantic/PyYAML/pytest` — exact versions confirmed
- Live codebase: `ls score/ bridge/ opml/` — file inventory confirmed (no score/_util.py)
- Live codebase: grep of imports in digest.py, triage_score.py, fever_triage.py — path expressions confirmed
- Live tests: `python3 -m unittest discover tests/ -v` — 56 tests, exact test method names listed

### Tertiary (LOW confidence — web search)

- [Python typing.Protocol reference](https://typing.python.org/en/latest/reference/protocols.html) — Protocol structural subtyping
- [setuptools editable installs](https://setuptools.pypa.io/en/latest/userguide/development_mode.html) — pyproject.toml editable install mechanics

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all packages physically installed and verified on target system
- Architecture / restructure patterns: HIGH — grounded in actual file contents and import graphs from live codebase
- PyYAML codec behavior: HIGH — round-trip verified with live Python test against all required data types
- pydantic v2 patterns: MEDIUM — from Context7 official docs; exact computed_field behavior confirmed via docs
- Pitfalls: HIGH — path depth bugs discovered from actual codebase inspection, not assumed

**Research date:** 2026-06-27

**Valid until:** 2026-07-27 (30 days — stable libraries, no fast-moving dependencies)
