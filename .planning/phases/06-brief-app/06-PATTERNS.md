# Phase 6: Brief app (gap-closure round) - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 5 (4 modify — clustering wiring bug; 1 new — Obsidian vault-writer)
**Analogs found:** 5/5 have at least a partial analog; one sub-piece (wikilink extraction) has **no** analog — flagged explicitly rather than forced

**Note on source:** No `06-RESEARCH.md` exists for this phase (`--gaps` mode skipped research). `06-VERIFICATION.md`'s `gaps:` YAML block and Data-Flow Trace table were used as the primary technical-context source, cross-checked against direct reads of every file named below. All line numbers in this document were verified against the live files as of 2026-07-06 (a first pass via local-model delegation produced different line numbers for `consumer.py`/`main.py`/`renderer.py`; those were discarded and replaced with direct-read ground truth).

## File Classification

| File | Action | Role | Data Flow | Closest Analog | Match Quality |
|------|--------|------|-----------|-----------------|---------------|
| `apps/brief/consumer.py` | modify (`_SELECT`) | event consumer | request-response (DB fetch on event) | `apps/brief/clustering.py`'s `cluster_items()` query shape | role-match |
| `apps/brief/main.py` | modify (`_ENRICHMENT_SQL`, wire `CLUSTER_THRESHOLD`) | HTTP controller | request-response | `apps/brief/clustering.py`'s `cluster_items()` query shape | role-match |
| `apps/brief/renderer.py` | modify (`_rows_to_enriched_items`, `_cluster_rows`) | transform/service | transform (rows → markdown) | `apps/brief/clustering.py` (embedding-attach logic) | role-match |
| `apps/brief/clustering.py` | modify (wire threshold; resolve orphaned `cluster_items()`) | service | CRUD-read + transform | `libs/store/src/store/_postgres.py` `find_near_duplicate()` | exact |
| `apps/brief/vault_writer.py` | **NEW** | service / file-writer | file-I/O | `apps/ingest-obsidian/obsidian_ingest.py` (inverse direction) + `libs/contracts/src/contracts/_codec.py` | role-match (inverse direction) |

---

## Pattern Assignments

### Gap 1 — Clustering wiring bug (`consumer.py`, `main.py`, `renderer.py`, `clustering.py`)

#### Current state (verified directly, exact line numbers)

**`apps/brief/consumer.py`** — `_SELECT` (lines 57-62):
```python
_SELECT = (
    "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, e.pmesii, e.tessoc, "
    "a.title, a.summary, a.source, a.url, a.ts "
    "FROM infotriage.enrichment e "
    "JOIN infotriage.articles a ON a.id = e.item_id "
)
```
No `embedding` column, no join to `infotriage.embeddings`. Used at line 67 (`_SELECT + "WHERE e.item_id = %s"`) and line 86 (`_SELECT + "ORDER BY e.score DESC"`).

**`apps/brief/main.py`** — `_ENRICHMENT_SQL` (lines 48-54):
```python
_ENRICHMENT_SQL = (
    "SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why, e.pmesii, e.tessoc, "
    "a.title, a.summary, a.source, a.url "
    "FROM infotriage.enrichment e "
    "JOIN infotriage.articles a ON a.id = e.item_id "
    "WHERE e.created_at >= %s ORDER BY e.score DESC"
)
```
Same gap — no `embeddings` join. Also **`CLUSTER_THRESHOLD`** (lines 43-46):
```python
# Clustering threshold (0.0–1.0, default 0.75)
CLUSTER_THRESHOLD = float(os.getenv("CLUSTER_THRESHOLD", "0.75"))
if not (0.0 <= CLUSTER_THRESHOLD <= 1.0):
    raise ValueError(f"CLUSTER_THRESHOLD must be 0.0–1.0, got {CLUSTER_THRESHOLD}")
```
Defined and range-validated, but never imported/read by `renderer.py` or `clustering.py` (verification must-have #9).

**`apps/brief/renderer.py`** — `_rows_to_enriched_items()` (lines 103-122), embedding default at **line 119**:
```python
embedding=r.get("embedding", [0.0] * 4),
```
`_cluster_rows()` (lines 144-151), hardcoded threshold at **line 150**:
```python
def _cluster_rows(rows: list[dict]) -> list[dict]:
    items = _rows_to_enriched_items(rows)
    clusters_raw = cluster_items_in_memory(items, threshold=0.75)
    return [{"items": _enriched_to_dicts(cl)} for cl in clusters_raw]
```
Calls `cluster_items_in_memory()` (pure-Python fallback) — never `clustering.cluster_items()` (the real DB-backed path).

**`apps/brief/clustering.py`** — two functions exist side by side:
- `cluster_items_in_memory()` (lines 233-309) — pure-Python fallback, correctly implemented, called by `renderer.py`, but only as good as the embeddings it's handed.
- `cluster_items()` (lines 80-230) — the real pgvector-backed path, 0 call sites outside its own module + one signature-only test. **This function is itself the closest analog** for "how to attach embeddings to enrichment rows," since it already solves the exact problem:

```python
# lines 118-127 — enrichment+articles JOIN, filtered by CCIR + window
query = """
    SELECT e.item_id, e.ccir, e.cnr, e.score, e.bucket, e.why,
           e.pmesii, e.tessoc,
           a.title, a.summary, a.source, a.url
    FROM infotriage.enrichment e
    JOIN infotriage.articles a ON a.id = e.item_id
    WHERE e.ccir = ANY(%s)
      AND e.created_at >= NOW() - CAST(%s AS interval)
    ORDER BY e.score DESC
"""
...
# lines 143-147 — SEPARATE batch embeddings fetch (NOT a SQL JOIN — a second
# query, merged in Python). item_ids collected from the first result set.
emb_query = """
    SELECT item_id, embedding
    FROM infotriage.embeddings
    WHERE item_id = ANY(%s)
"""
...
# lines 154-157 — merge in Python
embedding_map: dict[str, list[float]] = {
    row["item_id"]: row["embedding"] for row in emb_rows
}
```
Lines 161-181 then build `EnrichedItem` objects: `emb = embedding_map.get(row["item_id"]); if emb is None: continue` — items lacking an embedding are skipped, not dropped from clustering entirely (satisfies the SPEC.md "Partial cluster" edge case).

**Diagnostic note for the planner — two viable fix shapes exist; this document maps patterns, it does not choose between them:**

1. **Single SQL-level `LEFT JOIN`.** `infotriage.embeddings` has a UNIQUE index on `item_id` (`006-enrichment.sql` → `embeddings_item_id_unique`; schema at `libs/store/sql/003-vectors.sql` lines 24-30), so adding `LEFT JOIN infotriage.embeddings em ON em.item_id = e.item_id` (must be **LEFT**, not inner `JOIN` — an inner join would silently drop any item lacking an embedding, breaking the "Partial cluster" edge case) directly to `consumer.py`'s `_SELECT` / `main.py`'s `_ENRICHMENT_SQL` gives exactly one row per enrichment row with a real `em.embedding` column. `_rows_to_enriched_items()`'s existing `.get("embedding", ...)` line then starts receiving real data with no further code change needed there. This is the smaller, more surgical diff (2 SQL strings + threshold plumbing) but has no exact 3-way-JOIN precedent elsewhere in the codebase — it is a direct, minimal extension of the 2-way JOIN both files already contain.
2. **Reuse `clustering.cluster_items()` directly**, replacing the `cluster_items_in_memory()` call in `renderer.py::_cluster_rows()`. This requires threading a `store: PostgresStore` handle into `renderer.py`'s render functions (currently they only take `enrichment_rows: list[dict]`), and duplicates the enrichment+articles fetch `consumer.py`/`main.py` already performed (an extra Postgres round-trip per render). More invasive, but reuses tested, existing code verbatim with zero new SQL to write.

Either path, `main.py`'s `CLUSTER_THRESHOLD` (lines 44-46) must reach the clustering call — nothing currently imports it into `renderer.py`/`clustering.py`. This is parameter-passing, not new parameter surface: `render_brief()`/`render_cluster()`/`_cluster_rows()` in `renderer.py` and `cluster_items()`/`cluster_items_in_memory()` in `clustering.py` **already accept a `threshold` parameter** — the value from `main.py` just needs to flow through the existing call chain instead of the hardcoded `0.75` literal at `renderer.py:150`.

#### Shared pattern: pgvector query idiom (applies regardless of which fix shape is chosen)

**Analog:** `libs/store/src/store/_postgres.py` `find_near_duplicate()` (lines 392-424):
```python
def find_near_duplicate(
    self,
    vector: list[float],
    window_days: int = 7,
    threshold: float = 0.84,
) -> "str | None":
    ...
    row = self._conn.execute(
        """
        SELECT item_id, (embedding <=> %s::vector) AS dist
        FROM infotriage.embeddings
        WHERE created_at >= NOW() - CAST(%s AS interval)
        ORDER BY embedding <=> %s::vector
        LIMIT 1
        """,
        (vector, f"{window_days} days", vector),
    ).fetchone()
    if row is not None and row["dist"] < (1.0 - threshold):
        return row["item_id"]
    return None
```
Establishes the codebase convention: `<=>` cosine operator (never `<->` L2), `%s` bind params throughout, `CAST(%s AS interval)` (not the invalid `INTERVAL %s` form), similarity→distance conversion via `1.0 - threshold`. `register_vector()` is called once in `PostgresStore.__enter__()` (line 73) and again after DDL in `init_schema()` (line 123) — already active for any query run through an open `PostgresStore`, so **no new registration code is needed** regardless of which fix shape is picked.

Imports needed for the direct-JOIN route: none new — both `consumer.py` and `main.py` already build plain parameterized SQL strings with `%s`; adding a `LEFT JOIN` clause requires no new import.

---

### Gap 2 — Obsidian vault-writer (net-new: `apps/brief/vault_writer.py`)

No existing "vault writer" exists in the codebase (confirmed: only `apps/ingest-obsidian/` matches `*vault*`/`*obsidian*`, and it is read-only, opposite direction). Compose the new module from these existing pieces:

**(a) Front-matter codec — exact analog, import and use directly, do not reimplement**

`libs/contracts/src/contracts/_codec.py` (49 lines total, quoted in full):
```python
import yaml


def to_frontmatter(payload: dict) -> str:
    """Serialize payload dict to YAML frontmatter block (with --- delimiters).

    Preserves: tz-aware datetime (as YAML timestamp with UTC offset),
    Norwegian unicode, None→null, nested dicts/lists, [N] citation strings.
    Uses allow_unicode=True so Norwegian characters are not escaped.
    """
    body = yaml.safe_dump(payload, allow_unicode=True, default_flow_style=False)
    return f"---\n{body}---\n"


def from_frontmatter(text: str) -> dict:
    """Extract and parse YAML frontmatter from text, returning payload dict.
    ...
    Raises ValueError if text contains no frontmatter delimiters (---).
    Returns {} if the frontmatter block is empty (valid YAML null).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"No YAML frontmatter found in text: {text[:80]!r}")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":            # closing delimiter on its own line
            return yaml.safe_load("\n".join(lines[1:i])) or {}
    raise ValueError(f"Unterminated YAML frontmatter in text: {text[:80]!r}")
```
`vault_writer.py` should `from contracts import to_frontmatter` (same import site pattern as `obsidian_ingest.py:28`) and call `to_frontmatter({...})` to build each `.md` file's header, then append the body summary text below the returned `---\n...\n---\n` block.

**(b) Reverse-direction structural analog — `obsidian_ingest.py`**

`apps/ingest-obsidian/obsidian_ingest.py` reads the opposite direction (vault → `Item`) but is the closest shape match for "map one domain object to/from one Obsidian `.md` with front-matter," because it already establishes this project's Obsidian field-mapping convention:

- Import shape (line 28): `from contracts import Item, from_frontmatter` → `vault_writer.py`'s mirror: `from contracts import to_frontmatter`.
- Field-mapping function `item_from_obsidian_clip()` (lines 59-122) is structured as: read/parse → extract fields with `.get(...) or <default>` fallback + `log.warning(...)` (never raise on a missing field) → construct the domain object. `vault_writer.py`'s inverse function should mirror this shape: take one enrichment-row dict → build a front-matter payload dict with the same defensive `.get(key, default)` style → `to_frontmatter(payload) + body`.
- Batch-processing shape `fetch_items()` (lines 130-152): iterates paths, wraps each item in `try/except Exception as exc: log.error("Failed to parse Obsidian clip %r: %s", path, exc)` so **one bad item never aborts the batch**. The same per-item isolation should apply to `vault_writer.py`'s per-item file-write loop — one failing item's write must not stop the rest of that render's vault emission.
- **Explicit read-only constraint on the existing adapter** (module docstring lines 17-20, tag `T-04-09`): *"Vault files opened read-only only (no write/append modes)... No write, unlink, rename, or rmtree calls against the vault path."* **This is the opposite of what `vault_writer.py` must do** — flagging prominently: the new module is deliberately the first code in this repo permitted to WRITE into the vault. Do not reuse the read-only assumption or any of its guard comments; this needs its own writable mount (see Docker note below).

**(c) Atomic file write — reuse directly, exact analog already inside `apps/brief/`**

No need to invent a new atomic-write helper — `consumer.py` (lines 114-118) and `main.py`'s `_write_atomic()` (lines 81-86) already implement `.tmp` + `os.replace()` for this exact service:
```python
tmp = fpath.with_suffix(".tmp")
tmp.write_text(content, encoding="utf-8")
os.replace(tmp, fpath)
```
`vault_writer.py` should reuse this identical idiom for every emitted `.md` file (per-item files and the SAB projection file alike).

**(d) "High-value item" threshold — reuse the existing constant, don't invent a new one**

SPEC R6 says "emits one Obsidian `.md` file per high-value item" without redefining "high-value." The codebase already has exactly this concept, used in 3 call sites:
- `renderer.py:247` (`render_list()`): `[r for r in enrichment_rows if r.get("score", 0) >= 8]`
- `consumer.py:132` and `consumer.py:157`: BLUF-topic gating and `total_keep` counting, both `r.get("score", 0) >= 8`

`vault_writer.py` should filter on the same `score >= 8` threshold rather than introducing a new one, so "high-value" means the same thing in `list.md`, the BLUF, and the vault projection.

**(e) Integration point — where to call `vault_writer` from**

`consumer.py`'s `process_verdict()` already runs all 4 renderers in one `asyncio.gather()` (lines 99-104) against the same `enrichment_rows` fetched at lines 83-94, then writes files in a loop (lines 107-119). `vault_writer.py`'s emit function is the natural 5th participant in that same gather/write cycle — no new consumer subscription or separate Postgres round-trip is needed; it consumes the already-fetched `enrichment_rows` list.

---

### No analog found — `[[entity]]` wikilink generation

**Confirmed no existing analog anywhere in the codebase.** Grepped for `wikilink`, `[[...]]`, `extract_entit*`, `proper.noun`, `entity_link` across all `.py` files (excluding the SQL table name `infotriage.entity_links` and its test fixtures): zero hits. `infotriage.entities` / `infotriage.entity_links` (`libs/store/sql/003-vectors.sql` lines 7-22) are Phase 8's future system-of-record tables — schema exists, but no Python code anywhere reads or writes them yet.

**Closest partial (not sufficient) precedent:** `apps/triage/digest.py` `keywords()` (lines 148-149) and `STOP` (lines 31-32):
```python
STOP = set("the a an of to in on for and or at by with from is are as it its this that "
           "i og å en et er på til av for som med det den de har om mot ved".split())

def keywords(title):
    return {w for w in re.findall(r"[a-zA-ZæøåÆØÅ0-9]{4,}", (title or "").lower()) if w not in STOP}
```
This tokenizes into a **lowercased** bag of 4+ char words for keyword-overlap **clustering**, not entity extraction — lowercasing destroys the capitalization signal (`NATO`, `Ukraina`) that a proper-noun heuristic needs, and it returns an unordered `set` (no positions, no phrase grouping), so it cannot directly produce `[[Multi Word Entity]]` wikilinks. Reusable pieces: the Norwegian-aware regex charset (`[a-zA-ZæøåÆØÅ0-9]`) and the bilingual `STOP` list, if the interim heuristic needs stopword filtering. The case-preserving, phrase-grouping extraction logic itself must be written new — there is nothing to copy for that part.

**Observation, not a mandate:** no NLP dependency (spaCy, NLTK, etc.) appears in any `requirements*.txt` in this repo — a lightweight stdlib `re`-based heuristic (e.g., runs of consecutive capitalized words) would match the project's existing stdlib-first pattern rather than introducing a new dependency, but the planner should decide the exact approach.

---

### Docker / infra note (cross-cutting, relevant to whichever plan handles Compose wiring)

`docker-compose.yml`'s only existing Obsidian mount (lines 288-289) is explicitly **read-only** and scoped to `articles-inbox`, owned by `ingest-obsidian`:
```yaml
OBSIDIAN_VAULT_PATH: /vault
...
- ${OBSIDIAN_VAULT_PATH}/articles-inbox:/vault/articles-inbox:ro
```
The `brief` service's current volumes (docker-compose.yml lines 182-183) mount only `./data:/data` — **no vault mount exists on `brief` today**. `vault_writer.py` will need a new, separate, **writable** mount added to the `brief` service block (e.g., a distinct subpath such as `${OBSIDIAN_VAULT_PATH}/brief-outbox:/vault/brief-outbox:rw` — not reusing `articles-inbox`'s path or its `:ro` flag). No `Dockerfile` change is needed: `COPY apps/brief/ apps/brief/` (`apps/brief/Dockerfile` line 19) already copies the whole directory, so any new `.py` file placed under `apps/brief/` ships automatically.

---

## Shared Patterns

### Atomic write (`.tmp` + `os.replace`)
**Source:** `apps/brief/main.py` `_write_atomic()` (lines 81-86); `apps/brief/consumer.py` (lines 114-118)
**Apply to:** `vault_writer.py` (every emitted `.md` file)

### `%s` bind params — never f-string SQL
**Source:** `libs/store/src/store/_postgres.py` `find_near_duplicate()` (line 403 docstring: "vector and interval bound as parameters — never f-string SQL"); `apps/brief/clustering.py`'s `cluster_items()` query
**Apply to:** any SQL touched while fixing the clustering wiring bug (Gap 1)

### Cursor error handling: commit-on-read / rollback-on-exception
**Source:** `consumer.py` `_fetch()` (lines 64-73) and `_fetch_all()` (lines 83-92); `main.py` `_fetch_rows()` (lines 59-74) — every read wraps `cur.execute(...)`, then `cur.connection.commit()` to end the read transaction, with `except Exception: cur.connection.rollback(); raise` to avoid poisoning the shared connection for the next message/request.
**Apply to:** any modified `_fetch()`/`_fetch_rows()` in Gap 1 (e.g. if a `LEFT JOIN` is added, keep this exact try/commit/except-rollback shape around it)

### "High-value" == `score >= 8`
**Source:** `apps/brief/renderer.py:247`; `apps/brief/consumer.py:132,157`
**Apply to:** `vault_writer.py`'s item-selection filter (Gap 2)

## No Analog Found

| File/Feature | Role | Data Flow | Reason |
|---|---|---|---|
| `[[entity]]` wikilink generation (part of `vault_writer.py`) | transform (text → wikilink markup) | transform | No entity/wikilink extraction code exists anywhere in the repo; Phase 8's `infotriage.entities`/`entity_links` tables exist in schema only, unread by any app. Nearest precedent (`digest.py`'s `keywords()`) solves a different problem (lowercased keyword-overlap clustering) and is not directly reusable for phrase-level, case-preserving entity extraction. Planner should treat this as new code, optionally borrowing `digest.py`'s regex charset/`STOP` list only. |

## Metadata

**Files read directly (ground truth):** `apps/brief/consumer.py`, `apps/brief/main.py`, `apps/brief/renderer.py`, `apps/brief/clustering.py`, `apps/brief/Dockerfile`, `libs/store/src/store/_postgres.py` (targeted sections + signature grep), `libs/contracts/src/contracts/_codec.py`, `apps/ingest-obsidian/obsidian_ingest.py`, `apps/triage/digest.py` (targeted section), `libs/store/sql/003-vectors.sql`, `libs/store/sql/006-enrichment.sql`, `docker-compose.yml` (brief + ingest-obsidian service blocks), `06-CONTEXT.md`, `06-SPEC.md`, `06-VERIFICATION.md`
**Search scope:** `apps/`, `libs/`, `docker-compose.yml`, `tests/` (grep only, for confirming absence of wikilink/entity-extraction/NLP-dependency code)
**Analog search stopped at:** 5 strong analogs (pgvector query idiom, front-matter codec, reverse-direction Obsidian adapter, atomic-write idiom, shared score-threshold constant) plus one explicit no-analog finding
**Pattern extraction date:** 2026-07-06
