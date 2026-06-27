---
phase: 01-contracts-monorepo-skeleton
reviewed: 2026-06-27T20:43:39Z
depth: standard
files_reviewed: 28
files_reviewed_list:
  - README.md
  - .gitignore
  - pyproject.toml
  - requirements-dev.txt
  - libs/contracts/pyproject.toml
  - libs/contracts/src/contracts/__init__.py
  - libs/contracts/src/contracts/_bus.py
  - libs/contracts/src/contracts/_codec.py
  - libs/contracts/src/contracts/_events.py
  - libs/contracts/src/contracts/_item.py
  - apps/ingest/_util.py
  - apps/ingest/gmail_to_atom.py
  - apps/ingest/imap_to_atom.py
  - apps/ingest/yt_to_atom.py
  - apps/ingest/RSS_BRIDGE_NOTES.md
  - apps/opml/_check.py
  - apps/opml/feeds.opml
  - apps/opml/working.opml
  - apps/triage/digest.py
  - apps/triage/fever_triage.py
  - apps/triage/sab_html.py
  - apps/triage/triage_score.py
  - tests/test_bridge_escape.py
  - tests/test_ccir_sync.py
  - tests/test_contracts.py
  - tests/test_opml_check.py
  - tests/test_opml_roundtrip.py
  - tests/test_score_parse.py
  - tests/test_write_bluf.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-06-27T20:43:39Z
**Depth:** standard
**Files Reviewed:** 28
**Status:** issues_found

## Summary

Phase goal was a behavior-preserving restructure (flat `bridge/`, `score/`, `opml/` →
`apps/ingest`, `apps/triage`, `apps/opml`) plus a new `libs/contracts` package. The
contracts package is the focus and is largely sound — pydantic v2 models, `yaml.safe_*`
codec (T-01-01 XXE concern correctly handled), `computed_field` SHA-256 id, and a
`runtime_checkable` Protocol bus. Two genuine correctness defects exist in the new
contracts code (codec round-trip and bus dedup semantics).

The headline problem is **not** in contracts: the restructure was supposed to be
behavior-preserving, but the path-depth fix that accompanied the move was applied to
`gmail_to_atom.py` and all `apps/triage/*` files yet **missed on `imap_to_atom.py` and
`yt_to_atom.py`**. Both now resolve their project root one directory too shallow
(`.../InfoTriage/apps` instead of `.../InfoTriage`), so they read `.env` / config and
write Atom feeds into `apps/data/feeds/` — a location the `feeds` Docker container does
not serve. This is verified below and is a behavior-breaking regression introduced by
this phase.

Several pre-existing defects carried in verbatim by the `git mv` are also reported
(they were unchanged by the move, so behavior is technically "preserved", but they are
in review scope and worth surfacing): an always-non-zero exit gate in `_check.py` and
incomplete attribute escaping in `sab_html.py`.

No `<structural_findings>` block was provided, so this report is narrative-only.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `imap_to_atom.py` and `yt_to_atom.py` resolve project root one level too shallow — feeds + config land in the wrong directory

**File:** `apps/ingest/imap_to_atom.py:41`, `apps/ingest/yt_to_atom.py:40`

**Issue:** Both files compute:
```python
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
```
In the **original flat layout** (`bridge/imap_to_atom.py`, depth 1 under repo root)
this idiom yielded the repo root. After the `git mv` to `apps/ingest/` (depth 2), the
same two `dirname()` calls now stop at `.../InfoTriage/apps`, not the repo root.
Verified directly:
```
imap/yt ROOT  = /Users/vidarbrevik/projects/InfoTriage/apps      # wrong
gmail   root  = /Users/vidarbrevik/projects/InfoTriage           # correct
```
`gmail_to_atom.py:18` was correctly updated for the new depth (`"..", ".."`, two
levels up from `apps/ingest`), and every `apps/triage/*` file uses the same corrected
`"..", ".."` idiom. Only `imap` and `yt` were missed.

Consequences (all silent):
- `OUT_DIR = ROOT/data/feeds` → feeds written to `apps/data/feeds/*.xml`, which the
  `feeds` container does **not** serve. `README.md:92` and both files' own docstrings
  (e.g. `imap_to_atom.py:27`) promise `data/feeds/<name>.xml` at repo root.
- `load_dotenv(ROOT/.env)` reads `apps/.env` — the real `.env` at repo root is never
  loaded, so IMAP/Gmail credentials silently go missing.
- `.mailboxes.json` / `.yt_channels.json` fallbacks (`imap:56`, `yt:58`) are looked up
  under `apps/`, not repo root where `.gitignore` expects them.

No test exercises either `main()`, so the regression is not caught by CI. This breaks
the phase's behavior-preservation contract.

**Fix:** Add the missing level (match the `gmail`/`triage` convention):
```python
# apps/ingest/imap_to_atom.py:41 and apps/ingest/yt_to_atom.py:40
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# or, equivalently and consistent with the other modules:
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
```

## Warnings

### WR-01: `InMemoryBus` dedup is global across routing keys — same `item_id` can only ever be published once to the entire bus

**File:** `libs/contracts/src/contracts/_bus.py:50,53-57`

**Issue:** `_seen` is a single `set[str]` keyed solely on `item_id`, ignoring
`routing_key`:
```python
def publish(self, routing_key, item_id, payload):
    if item_id in self._seen:
        return
    self._seen.add(item_id)
    self._queues.setdefault(routing_key, []).append(payload)
```
The documented event lifecycle reuses the same `item_id` across stages —
`ItemIngested(item_id=...)` then `VerdictReady(item_id=...)` (`_events.py:19,28`). With
global dedup, once an item is published to `item.ingested`, any later `verdict.ready`
(or `sab.published`) publish for that same `item_id` is **silently dropped**, even
though it is a different routing key. The intended idempotency key is almost certainly
`(routing_key, item_id)`. The existing tests do not catch this: `test_bus_dedup` uses
one routing key, and `test_bus_cross_routing_key_isolation`
(`test_contracts.py:314`) uses two *different* ids (`id1`, `id2`), so the cross-key
collision path is never exercised.

**Fix:** Key dedup per routing key:
```python
def __init__(self):
    self._queues: dict[str, list[dict]] = {}
    self._seen: set[tuple[str, str]] = set()

def publish(self, routing_key, item_id, payload):
    key = (routing_key, item_id)
    if key in self._seen:
        return
    self._seen.add(key)
    self._queues.setdefault(routing_key, []).append(payload)
```
Add a test that publishes the same `item_id` to two routing keys and asserts both are
delivered.

### WR-02: `from_frontmatter` splits on `---` anywhere — a frontmatter value containing `---` corrupts the round-trip

**File:** `libs/contracts/src/contracts/_codec.py:40-43`

**Issue:** `text.split("---", 2)` treats the first two occurrences of `---` anywhere in
the text as delimiters. When a frontmatter **value** contains `---`, the split lands
inside that value. Example that violates the SPEC R3 "no precision loss" round-trip
guarantee:
```python
to_frontmatter({"sep": "---"})        # -> "---\nsep: '---'\n---\n"
from_frontmatter("---\nsep: '---'\n---\n")
# parts[1] == "\nsep: '"  -> yaml.safe_load raises (unterminated quote)
```
Plausible real inputs: a `why`/`bluf` string or any Obsidian field containing a literal
`---`. The body-content case is safe (`maxsplit=2` discards the body), so this is
narrower than total breakage — but it is still silent data corruption / an exception on
otherwise-valid payloads.

**Fix:** Require the frontmatter fence at the start and split only the leading block,
e.g.:
```python
def from_frontmatter(text):
    if not text.startswith("---"):
        raise ValueError(f"No YAML frontmatter found in text: {text[:80]!r}")
    rest = text[3:]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError(f"Unterminated frontmatter: {text[:80]!r}")
    return yaml.safe_load(rest[:end]) or {}
```
Add a round-trip test for a value containing `---`.

### WR-03: `sab_html.escape()` does not escape quotes — feed-supplied `url` is injected into an `href` attribute (HTML attribute injection / XSS)

**File:** `apps/triage/sab_html.py:106-107,124`

**Issue:** The local `escape()` only handles `&`, `<`, `>`:
```python
def escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```
`render_item` then places the (escaped-but-not-quote-escaped) `url` directly inside a
double-quoted attribute:
```python
url = escape(v.get("url", ""))
...
f'<a class="item" href="{url}">'
```
`url` originates from `verdicts.jsonl`, which is populated from Fever/RSS item URLs —
attacker-influenceable via a malicious feed entry. A URL such as
`x" onmouseover="alert(1)` breaks out of the attribute and injects arbitrary handlers
into the generated SAB HTML when opened in a browser. Title/source text is fine (text
context, where only `&<>` matter); the defect is specific to attribute context.

This is pre-existing (the file is a verbatim `git mv` from `score/sab_html.py`) and the
artifact is a local single-user/FOUO page, which lowers exploitability — but it is a
real injection vector and would be a BLOCKER if the page were ever shared/served.

**Fix:** Escape quotes too, and use it for attribute values:
```python
def escape(text):
    return ((text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;"))
```
(`apps/ingest/_util.py:escape` already does the right thing with `html.escape(s,
quote=True)` — consider reusing it.)

### WR-04: `_check.py` default exit gate is always non-zero — `"❌" in md` is always true

**File:** `apps/opml/_check.py:426-431`

**Issue:** The exit gate keys off substring presence in the full markdown report:
```python
bad = "❌" in md
warn = "⚠️" in md
transient = "🟡" in md
if bad:
    sys.exit(1)
```
But `run()` unconditionally emits a summary line (`:235-237`) and a status legend
(`:239-242`) that *always* contain `✅ 🟡 ⚠️ ❌` — e.g. `"❌ 0 unreachable"` and
`"❌ 5xx / network error"`. So `bad`/`warn`/`transient` are `True` even when every feed
is healthy, and the default (non-`--allow-broken`) run **always exits 1**, defeating any
CI/health gate. Note the author already knew the correct technique: `n_attention`
(`:432`) counts table rows via `md.count("| ⚠️ ")`, but the gate uses the bare
substring.

Pre-existing: the file is byte-identical to `opml/_check.py` at the diff base (the move
introduced no change), so behavior is "preserved" — but it is a live bug in scope.

**Fix:** Gate on the computed counts, not substring presence:
```python
n_bad = sum(1 for r in results if r[4] == "❌")
n_warn = sum(1 for r in results if r[4] == "⚠️")
n_transient = sum(1 for r in results if r[4] == "🟡")
# (results is already returned from run(); thread the counts out or recompute)
if n_bad:
    sys.exit(1)
if (n_warn or n_transient) and not args.exit_on_error_only:
    sys.exit(1)
```

### WR-05: `yt_to_atom.py` interpolates `vid` into XML without escaping

**File:** `apps/ingest/yt_to_atom.py:143-144`

**Issue:** Every other field flows through `escape()`, but the video id does not:
```python
f'<id>urn:youtube:{vid}</id>',
f'<link href="https://youtu.be/{vid}"/>',
```
`vid` comes from `yt-dlp --print "%(id)s|||%(title)s"` split on `"|||"`. YouTube ids are
normally `[A-Za-z0-9_-]`, so exploitation is unlikely, but a malformed/spoofed id
containing `"`, `<`, or `&` would produce invalid Atom XML (and `href` is an attribute
context, so a `"` breaks the tag). Inconsistent with the file's own defense-in-depth
escape contract.

**Fix:** Wrap both interpolations: `escape(vid)` (use a quote-escaping helper for the
`href` attribute).

### WR-06: `digest.py` performs file I/O and can raise `AssertionError` at import time

**File:** `apps/triage/digest.py:50-60`

**Issue:** The CCIR drift guard runs at module top level: it `open()`s `ROOT/ccir.md`
(no context manager — leaked handle, `:50`) and `raise AssertionError(...)` on drift
(`:60`). Because `test_ccir_sync.py:17` and `test_write_bluf.py:12` `import digest`, any
missing/desynced `ccir.md` makes the module unimportable and fails test *collection*
(not just one test), and breaks any tooling that imports `digest` for unrelated reasons.
This phase added the `from contracts import Item` wiring (`:20`) into the same import
path, increasing the blast radius of an import-time failure.

**Fix:** Move the guard into a function invoked from `main()` (and called explicitly by
`test_ccir_sync`), and use `with open(...) as f:` for the read. Keep the strict raise,
just don't run it as an import side effect.

## Info

### IN-01: `Item.id` docstring claims normalization that does not happen

**File:** `libs/contracts/src/contracts/_item.py:43,47`

**Issue:** Docstring says "SHA-256 of **normalized** source_type + NUL + url + NUL +
title", but the implementation hashes the raw fields with no normalization
(casefold/strip/etc.). Misleading for future callers reasoning about dedup stability.

**Fix:** Either drop "normalized" from the docstring or implement the normalization the
contract implies.

### IN-02: Stale `bridge/` references in moved docs/docstrings

**File:** `apps/ingest/_util.py:2-7`, `apps/ingest/RSS_BRIDGE_NOTES.md:8,72-74`

**Issue:** `_util.py`'s header still reads `bridge/_util.py` and lists `bridge/*` call
sites; `RSS_BRIDGE_NOTES.md` links `bridge/imap_to_atom.py`, `bridge/yt_to_atom.py`,
`opml/feeds.opml`, etc. After the restructure these paths are `apps/ingest/*` /
`apps/opml/*`. Cosmetic but will mislead.

**Fix:** Update the moved files' self-references to the `apps/...` paths.

### IN-03: README references Ollama, contradicting the documented stack

**File:** `README.md:11,84-86`

**Issue:** The diagram says `qwen36 via oMLX/Ollama`. Project memory explicitly states
the stack is oMLX (Mac) + vLLM (Spark) with **no Ollama** (port `:11434` unused).
Documentation drift only.

**Fix:** Replace `oMLX/Ollama` with `oMLX/vLLM` (or just oMLX).

### IN-04: Unread-id ordering assumption differs between `digest.py` and `fever_triage.py`

**File:** `apps/triage/digest.py:87`, `apps/triage/fever_triage.py:57`

**Issue:** `digest.py` explicitly `sorted(..., key=int, reverse=True)[:hardcap]` to get
newest-first; `fever_triage.py` relies on Fever's native return order and takes
`unread[-args.max:]` with a comment claiming "newest first (highest ids)". The two
disagree on whether the raw `unread_item_ids` order is ascending or descending; only one
can be right for "newest." Pre-existing (unchanged by the move), but worth aligning so
both code paths cap on the same end of the window.

**Fix:** Have `fever_triage.py` sort explicitly (`sorted(unread, key=int,
reverse=True)[:args.max]`) to match `digest.py` and make the intent unambiguous.

---

_Reviewed: 2026-06-27T20:43:39Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
