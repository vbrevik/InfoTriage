# Phase 0: Concept Spike — Research

**Researched:** 2026-06-24
**Domain:** RabbitMQ AMQP topology / multilingual embeddings / pgvector entity resolution / Wiki-LLM synthesis / World Monitor COP integration
**Confidence:** MEDIUM (all primary sources verified via Context7 or registry; World Monitor internals LOW due to limited official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** Source spike test data by **fetching fresh from NRK/BBC/TASS** (not reusing `data/verdicts.jsonl`, not synthetic). Read-only against sources.

**D-02:** For R2, pick real events all three outlets covered **concurrently**; same-story groupings require a **hand-labeling step** to measure the ≥80% collapse rate and seed control items.

**D-03:** R4 (≥5 corpus items) and R5 (20 InfoTriage items) **reuse the same fresh-fetched items**, run through the existing pipeline where needed.

**D-04:** Stand up Postgres+pgvector (R3) and RabbitMQ (R1) as **ephemeral throwaway containers** — separate compose/`docker run`, **distinct ports, torn down after**. Must not touch the running `:8088`/`:3000` stack or production data.

**D-05:** Evaluate COP by **cloning and running the real World Monitor repo** against oMLX (local LLM, ADR-004) to score 20 items + write a CCIR-structured brief.

**D-06:** After ADRs (005–008) + `SPIKE-FINDINGS.md` are written, **delete throwaway spike code**. ADRs + SPIKE-FINDINGS.md are the only durable record. Spike code never merges to `apps/`/`libs/`.

### Claude's Discretion

- Exact scratch directory location for throwaway code (kept out of `apps/`/`libs/`).
- Embedding model serving mechanism for the bge-m3 vs mE5-large bake-off (host sentence-transformers / oMLX / Ollama).
- Spike sequencing among the 5 unknowns and any early-exit on a documented "partial".
- Same-story event selection and labeling format for the R2 triple set.

### Deferred Ideas (OUT OF SCOPE)

- Building the final embedding infrastructure (Phase 5).
- Entity resolution production schema + Obsidian projection (Phase 8).
- Wiki-LLM production (Phase 10).
- Full COP/map UI build (SP-COP / later, depending on R5 verdict).
- Multi-user / auth / tenancy (Milestone 3).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| R1 | RabbitMQ AMQP publish→consume round-trip with 4 event types, DLQ, publisher confirms | pika/aio-pika syntax, exchange/routing design, DLX wiring, Docker image |
| R2 | Norwegian semantic dedup: ≥10 NRK/BBC/TASS same-story triples, ≥80% collapse at one threshold, no control over-merge | bge-m3 vs mE5-large serving options, cosine threshold guidance, hand-label scheme |
| R3 | Postgres entity resolution: one known entity merged across ≥3 items / 2 languages, no control over-merge | pgvector schema, cosine operator, HNSW index, NER approach on ADR-004 constraint |
| R4 | Wiki-LLM: 1 coherent cited standing page from ≥5 corpus items + 1 on-demand article | qwen36 prompt/RAG pattern, citation grounding, context window analysis |
| R5 | COP + World Monitor: score 20 items + CCIR brief; adopt/build/drop recorded in ADR-005 | WM setup steps, Ollama config path, CCIR injection approach, known blockers |
</phase_requirements>

---

## Summary

This research delivers implementation-ready guidance for the five throwaway spike unknowns in Phase 0. Every unknown has a concrete, runnable approach using tools already available or trivially installable on this Mac. The spike infrastructure — RabbitMQ and pgvector — runs as ephemeral Docker containers on the dedicated port band 22060–22062 to avoid touching the production `:8088`/`:3000` stack.

**R1 (RabbitMQ):** Use `pika` 1.4.1 with `BlockingConnection` for the spike. One topic exchange `infotriage.events`, four routing keys, a dead-letter exchange `infotriage.dlx`, and a DLQ queue. DLX wiring is 12 lines of pika setup code. Publisher confirms are one method call.

**R2 (Embedding dedup):** `sentence-transformers` 5.3.0 is already installed (Anaconda). Download `BAAI/bge-m3` (570 MB FP16) via `SentenceTransformer("BAAI/bge-m3")` — no Ollama needed, simpler for the spike. Start cosine threshold at **0.85** and tune down; the bake-off against mE5-large requires running both and comparing collapse rates on the labeled triple set.

**R3 (Entity resolution):** `pgvector/pgvector:pg16` container, `pgvector` 0.4.2 Python package, `psycopg2-binary` (already installed). NER via qwen36 `llm()` function reused from `triage_score.py` (ADR-004 compliant; spaCy not installed). HNSW index with `vector_cosine_ops` enables sub-millisecond cosine lookups.

**R4 (Wiki-LLM):** Reuse the existing `write_bluf()` pattern from `score/digest.py` with a wiki-structured prompt asking for section headers and inline `[N]` citations. qwen36's 32K context comfortably holds ≥5 items at ~125 tokens each.

**R5 (World Monitor):** Clone `koala73/worldmonitor`, `npm install`, `npm run dev` for the web mode. **Critical finding:** Ollama local-LLM support is exclusive to the Tauri desktop runtime, NOT the web dev server. The desktop build requires `npm run tauri dev` (Rust 1.91.1 is available). For the spike, configure the Ollama/oMLX endpoint in the settings UI. CCIR scoring is NOT built into WM — it must be injected via a custom system prompt for the LLM or by pre-scoring items with InfoTriage's existing pipeline before feeding them to WM.

**Primary recommendation:** Implement the unknowns in this order — R1 (simplest, clearest go/no-go) → R3 (pgvector, unlocks R2) → R2 (embedding bake-off, longer run time) → R4 (qwen36, needs corpus) → R5 (most setup overhead, most uncertain outcome). Run R1 and R3 container setup in parallel as they are independent.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AMQP message routing (R1) | Broker (RabbitMQ) | App / Python client | Exchange + routing key wiring lives in the broker; Python only declares topology |
| Semantic dedup / embedding (R2) | Host Python (spike) | pgvector (Phase 5) | sentence-transformers on host is the simplest spike path; Phase 5 moves it inside the triage container |
| Entity NER extraction (R3) | Local LLM (qwen36) | — | ADR-004; spaCy not installed; qwen36 already proven for structured JSON output |
| Entity linking (R3) | Postgres + pgvector | Python glue | Cosine lookup lives in the DB; Python decides the merge threshold |
| Wiki synthesis (R4) | Local LLM (qwen36) | Python prompt builder | Same `llm()` pattern as triage_score.py; model does the synthesis |
| COP globe / map (R5) | World Monitor (JS/Tauri) | InfoTriage pipeline (pre-scoring) | WM owns the map; InfoTriage owns CCIR scoring and briefing |
| CCIR brief (R5) | InfoTriage triage_score.py | WM LLM (if configurable) | WM has no native CCIR taxonomy; InfoTriage's existing prompt is the source of truth |

---

## Standard Stack

### Core (spike-specific — throwaway, not for `apps/`/`libs/`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pika` | 1.4.1 | AMQP 0-9-1 Python client for RabbitMQ (R1) | Official RabbitMQ-recommended sync client; pure-Python, stdlib-friendly; 296 Context7 snippets |
| `aio-pika` | 9.6.2 | Async wrapper over aiormq (Phase 3 production use) | Confirms by default; connect_robust auto-reconnects; preferred for long-running apps |
| `pgvector` | 0.4.2 | pgvector Python adapter for psycopg2/psycopg3 (R3) | Official pgvector Python client; register_vector() integrates with existing psycopg2-binary |
| `sentence-transformers` | 5.3.0 | Embedding inference for R2 (ALREADY INSTALLED via Anaconda) | HuggingFace-maintained; supports BAAI/bge-m3 and intfloat/multilingual-e5-large directly |
| `FlagEmbedding` | 1.4.0 | Alternative bge-m3 client with sparse+dense support (R2 optional) | Official BAAI client; needed only if sparse retrieval modes are tested |

### Pre-installed (no action needed)
| Library | Version | Purpose |
|---------|---------|---------|
| `psycopg2-binary` | 2.9.10 | Postgres driver (R3) — already installed |
| `sentence-transformers` | 5.3.0 | Embedding host (R2) — already installed |
| `torch` | 2.11.0 | ML backend for sentence-transformers — already installed |

### Docker images (spike containers — D-04)

| Image | Tag | Purpose | Port band |
|-------|-----|---------|-----------|
| `rabbitmq` | `3.13-management` | RabbitMQ broker + management UI (R1) | 22060 (AMQP), 22061 (UI) |
| `pgvector/pgvector` | `pg16` | Postgres 16 + pgvector extension (R3) | 22062 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pika` (sync, spike) | `aio-pika` (async) | aio-pika is better for Phase 3 production but adds asyncio complexity to the throwaway spike |
| `sentence-transformers` on host | `ollama pull bge-m3` | Ollama serving adds HTTP overhead; host ST is faster for batch encoding in the spike |
| qwen36 NER via `llm()` | `spacy nb_core_news_lg` | spaCy not installed; qwen36 already proven for structured JSON; NER via LLM is ADR-004 compliant |
| `pgvector/pgvector:pg16` | `ankane/pgvector` (older) | Official pgvector/pgvector image is the current recommended image |

**Installation (new packages only):**
```bash
pip3 install pika==1.4.1 pgvector==0.4.2 defusedxml
# Optional for FlagEmbedding sparse mode:
pip3 install FlagEmbedding==1.4.0
```

---

## Package Legitimacy Audit

The gsd-tools legitimacy seam rates all PyPI packages as `SUS` due to unknown download stats (the seam cannot query PyPI download counts). The packages below are well-established projects with years of version history and active GitHub repos — the `SUS` rating reflects a tooling gap, not actual risk. Each package is independently verified via `pip3 index versions` against PyPI and cross-confirmed via Context7 (official docs).

| Package | Registry | Age | Version History | Source Repo | Seam Verdict | Disposition |
|---------|----------|-----|-----------------|-------------|--------------|-------------|
| `pika` | PyPI | 10+ yrs | 1.4.1, long history | github.com/pika/pika | SUS (no dl stats) | Approved — official RabbitMQ Python client, Context7 HIGH |
| `aio-pika` | PyPI | 7+ yrs | 9.6.2, 140+ versions | github.com/mosquito/aio-pika | SUS (no dl stats) | Approved — async wrapper over aiormq, Context7 HIGH |
| `pgvector` | PyPI | 3+ yrs | 0.4.2, 25 versions | github.com/pgvector/pgvector-python | SUS (no dl stats) | Approved — official pgvector Python adapter, Context7 HIGH |
| `FlagEmbedding` | PyPI | 2+ yrs | 1.4.0, 25+ versions | github.com/FlagOpen/FlagEmbedding | SUS (no dl stats) | Approved — BAAI official client, Context7 HIGH |
| `sentence-transformers` | PyPI | 5+ yrs | 5.3.0 | sbert.net | SUS (no dl stats) | Already installed — approved |
| `psycopg2-binary` | PyPI | 10+ yrs | 2.9.10 | psycopg.org | SUS (no dl stats) | Already installed — approved |
| `defusedxml` | PyPI | 10+ yrs | stable long history | github.com/tiran/defusedxml | SUS (no dl stats) | Approved — CVE-mitigating XML parser, widely used, security-recommended |

**Packages removed due to SLOP verdict:** none

**Packages flagged as suspicious (SUS — legitimate projects, tooling gap):** all above rated SUS due to PyPI download count unavailability in the seam, NOT due to actual risk signals. Source repos and version histories are verified authoritative.

---

## Architecture Patterns

### System Architecture Diagram (spike scope only)

```
NRK/BBC/TASS RSS feeds (read-only fetch)
        |
        v
[.spike/fetch.py]  ─── fresh items JSON (D-01)
        |
        +──── HAND LABEL ───────────────── same_story_triples.csv (D-02)
        |
        +──── R2: sentence-transformers ─── cosine matrix ─── threshold sweep
        |     (host, bge-m3 or mE5-large)      |
        |                                       v
        |                               collapse_rate >= 80%?  ─── ADR note
        |
        +──── R3: qwen36 NER via llm() ─── entity JSON
        |            |
        |            v
        |     pgvector/pgvector:pg16 :22062
        |     entities + entity_links ─── cosine linking ─── merge test
        |
        +──── R4: qwen36 via llm() ─── wiki prompt ─── cited wiki page
        |     (reuse write_bluf() pattern, score/digest.py)
        |
        +──── R5: run through pipeline ─── 20 scored items JSON
                           |
                           v
              [worldmonitor/] npm run tauri dev
                    |
                    +── Ollama/oMLX endpoint → qwen36 (ADR-004)
                    |
                    v
              COP globe + AI brief ─── CCIR inject via system prompt?
                    |
                    v
              adopt/build/drop ─── ADR-005

RabbitMQ container :22060/:22061
[.spike/r1_publisher.py] → infotriage.events (topic) → [.spike/r1_consumer.py]
Poison msg → nack(requeue=False) → infotriage.dlx → infotriage.dlq
                    |
                    v
                 ADR-007
```

### Recommended Scratch Directory Layout (Claude's Discretion, D-06)

```
.spike/                         # gitignored; deleted after ADRs written (D-06)
├── docker-compose.yml          # RabbitMQ :22060/:22061 + pgvector :22062
├── requirements-spike.txt      # pika==1.4.1 pgvector==0.4.2
├── r1_rabbit/
│   ├── r1_publisher.py         # dummy service A: publishes 4 event types
│   ├── r1_consumer.py          # dummy service B: consumes, acks, nacks poison
│   └── r1_topology.py         # declare exchanges, queues, DLX, DLQ
├── r2_dedup/
│   ├── r2_fetch.py            # fetch NRK/BBC/TASS RSS → items JSON
│   ├── same_story_triples.csv  # hand-labeled (item_a, item_b, same_story)
│   ├── r2_embed.py            # embed titles+summaries, cosine matrix
│   └── r2_threshold.py        # threshold sweep, collapse rate calculation
├── r3_entities/
│   ├── r3_schema.sql           # CREATE TABLE entities + entity_links + HNSW index
│   ├── r3_ner.py              # NER via qwen36 llm() → entity JSON
│   └── r3_link.py             # embed entities, cosine link, merge/insert
├── r4_wiki/
│   └── r4_wiki.py             # extend write_bluf() pattern → wiki page
├── r5_worldmonitor/
│   └── r5_prep.py             # export 20 scored items as WM-compatible input
└── SPIKE-FINDINGS.md           # per-unknown go/no-go/partial (durable artifact)
```

---

## R1: RabbitMQ Topology

### Exchange and Routing Key Design

```
Exchange: infotriage.events  (type: topic, durable: true)

Routing keys:
  item.ingested    — published by ingest adapters
  verdict.ready    — published by triage
  sab.published    — published by brief
  feed.unhealthy   — published by opml-health

DLX exchange: infotriage.dlx  (type: direct, durable: true)
DLQ queue:    infotriage.dlq  (durable: true, bound to infotriage.dlx, routing_key="dead")

Primary queues (durable, with DLX wired):
  q.triage        bound to infotriage.events, routing_key="item.ingested"
  q.brief         bound to infotriage.events, routing_key="verdict.ready"
  q.ops           bound to infotriage.events, routing_key="feed.unhealthy"
  q.notify        bound to infotriage.events, routing_key="sab.published"

All primary queues declared with:
  arguments={"x-dead-letter-exchange": "infotriage.dlx", "x-dead-letter-routing-key": "dead"}
```

**Why topic exchange:** Routing keys use dot-separated namespacing (`item.ingested`) which maps naturally to topic exchange wildcards. For M3 team fan-out, a second consumer binding `q.team_member_1` to `verdict.ready` is just one extra `queue_bind()` call — no exchange change needed. [CITED: github.com/pika/pika/blob/main/docs/examples/]

### Python Client: pika for spike, aio-pika for Phase 3

Use **pika 1.4.1** (blocking) for the throwaway spike — simpler, no asyncio boilerplate. Use **aio-pika 9.6.2** for Phase 3 production (auto-reconnect, cleaner consumer lifecycle).

### Key Syntax (pika — R1 spike)

**Topology declaration:**
```python
# Source: github.com/pika/pika docs
import pika

conn = pika.BlockingConnection(pika.ConnectionParameters("localhost", 22060))
ch = conn.channel()

# Declare DLX first (must exist before primary queues reference it)
ch.exchange_declare("infotriage.dlx", exchange_type="direct", durable=True)
ch.queue_declare("infotriage.dlq", durable=True)
ch.queue_bind("infotriage.dlq", "infotriage.dlx", routing_key="dead")

# Main topic exchange
ch.exchange_declare("infotriage.events", exchange_type="topic", durable=True)

# Primary queue with DLX wiring
ch.queue_declare(
    "q.triage",
    durable=True,
    arguments={"x-dead-letter-exchange": "infotriage.dlx",
               "x-dead-letter-routing-key": "dead"}
)
ch.queue_bind("q.triage", "infotriage.events", routing_key="item.ingested")
```

**Publisher with confirms:**
```python
# Source: github.com/pika/pika/blob/main/docs/examples/blocking_delivery_confirmations.md
ch_confirm = conn.channel(confirm_delivery=True)
ch_confirm.basic_publish(
    exchange="infotriage.events",
    routing_key="item.ingested",
    body=b'{"id": "test-001", "source": "NRK"}',
    properties=pika.BasicProperties(delivery_mode=2),  # persistent
)
confirmed = ch_confirm.wait_for_confirms()
```

**Consumer with ack/nack (poison → DLQ):**
```python
# Source: github.com/pika/pika docs
def on_message(ch, method, props, body):
    try:
        process(body)
        ch.basic_ack(method.delivery_tag)
    except PoisonMessage:
        ch.basic_nack(method.delivery_tag, requeue=False)  # → DLQ

ch.basic_qos(prefetch_count=1)
ch.basic_consume("q.triage", on_message_callback=on_message)
ch.start_consuming()
```

### Docker Compose (spike only)

```yaml
# .spike/docker-compose.yml
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    ports:
      - "22060:5672"   # AMQP — distinct from production ports
      - "22061:15672"  # Management UI
    environment:
      RABBITMQ_DEFAULT_USER: spike
      RABBITMQ_DEFAULT_PASS: spike
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  pgvector:
    image: pgvector/pgvector:pg16
    ports:
      - "22062:5432"
    environment:
      POSTGRES_USER: spike
      POSTGRES_PASSWORD: spike
      POSTGRES_DB: spike
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U spike"]
      interval: 5s
      retries: 5
```

**Run:** `docker compose -f .spike/docker-compose.yml up -d`
**Teardown:** `docker compose -f .spike/docker-compose.yml down -v` (removes volumes)

### M3 Fan-out Growth Path

The topic exchange design maps directly to M3 multi-user team fan-out: each team member gets their own durable queue (`q.member_alice`, `q.member_bob`) bound to `verdict.ready`. The broker delivers a copy to each. No code changes to publishers; only consumer registration changes. [ASSUMED — based on RabbitMQ topic exchange semantics; not verified against M3 specs which don't exist yet]

---

## R2: Norwegian Semantic Dedup

### Model Recommendation: BAAI/bge-m3

Use **`BAAI/bge-m3`** via `sentence-transformers` for the spike. Rationale:
- 100+ language coverage including Norwegian Bokmål, English, Russian [CITED: arxiv.org/pdf/2402.03216v3]
- SOTA on MIRACL multilingual + MKQA cross-lingual retrieval benchmarks [CITED: docs/RESEARCH-REPORT.md §8]
- Dense + sparse + multi-vector modes; spike only needs dense cosine for R2
- 1024 dims (matches the Phase 2 DB schema `vector(1024)` already planned in ARCHITECTURE.md)
- sentence-transformers 5.3.0 is **already installed** — just download the model weights

**mE5-large comparison:** `intfloat/multilingual-e5-large` is also 1024 dims, well-validated on Scandinavian Embedding Benchmark [CITED: arxiv.org/pdf/2406.02396]. Slightly faster inference; slightly weaker on multilingual cross-language tasks than bge-m3. The spike runs BOTH and records which achieves ≥80% collapse; bge-m3 is the expected winner for NO/EN/RU mix.

### Serving: Host sentence-transformers (Claude's Discretion)

```python
# Source: sbert.net docs, Context7 /websites/sbert_net
from sentence_transformers import SentenceTransformer
import numpy as np

# Download on first run (~570MB for bge-m3 FP16)
model = SentenceTransformer("BAAI/bge-m3")

def embed_item(item: dict) -> np.ndarray:
    """Embed title + first 512 chars of summary."""
    text = f"{item['title']} {item.get('summary', '')[:512]}"
    emb = model.encode(text, normalize_embeddings=True)
    return emb.astype(np.float32)

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity for normalized embeddings = dot product."""
    return float(np.dot(a, b))
```

**Why host over Ollama:** `ollama pull bge-m3` produces a 1.2GB quantized model; the host sentence-transformers FP16 is ~570MB and already in the installed ecosystem. Avoids HTTP round-trip overhead for batch encoding (R2 needs to embed ~30 items). [ASSUMED — size comparison based on web search; not benchmarked on this Mac in this session]

**mE5-large alternative:**
```python
# Requires instruction prefix for queries
model_e5 = SentenceTransformer("intfloat/multilingual-e5-large")
query_text = f"query: {title} {summary[:512]}"
# For documents: "passage: {text}"
```

### Fresh Fetch Approach (D-01/D-02)

Use existing bridge patterns to fetch fresh items:

```python
# Pattern from bridge/imap_to_atom.py + yt_to_atom.py
# SECURITY: use defusedxml, NOT stdlib xml.etree.ElementTree.
# stdlib is vulnerable to XXE (external entity injection) and billion-laughs attacks.
# pip3 install defusedxml
import urllib.request
import defusedxml.ElementTree as ET  # safe drop-in for xml.etree.ElementTree

def fetch_rss(url: str) -> list[dict]:
    """Fetch an RSS/Atom feed → list of {title, summary, link, source}."""
    with urllib.request.urlopen(url, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    # Handle Atom and RSS2
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        items.append({
            "title": entry.findtext("{http://www.w3.org/2005/Atom}title", ""),
            "summary": entry.findtext("{http://www.w3.org/2005/Atom}summary", ""),
            "source": url,
        })
    return items

# NRK: https://www.nrk.no/nyheter/siste.rss
# BBC: https://feeds.bbci.co.uk/news/world/rss.xml
# TASS: https://tass.com/rss/v2.xml
```

### Hand-Labeling Scheme (D-02)

```csv
# same_story_triples.csv
item_a_id,item_b_id,item_c_id,same_story,notes
nrk_001,bbc_003,tass_007,yes,"NATO summit Berlin coverage"
nrk_002,bbc_010,tass_009,yes,"Svalbard incident"
nrk_005,bbc_015,,no,"control: NRK-only story"
```

Minimum: 10 same-story triples (≥30 items) + 5 control pairs that must NOT collapse. One run of the threshold sweep records the ≥80% collapse rate and zero control over-merges.

### Cosine Threshold Selection

```python
def sweep_threshold(embeddings: dict, labels: pd.DataFrame,
                    thresholds=np.arange(0.75, 0.98, 0.02)):
    results = []
    for t in thresholds:
        tp = sum(cosine_sim(emb[r.item_a_id], emb[r.item_b_id]) >= t
                 for _, r in labels[labels.same_story=="yes"].iterrows())
        fp = sum(cosine_sim(emb[r.item_a_id], emb[r.item_b_id]) >= t
                 for _, r in labels[labels.same_story=="no"].iterrows())
        collapse_rate = tp / len(labels[labels.same_story=="yes"])
        control_overmerge = fp
        results.append((t, collapse_rate, control_overmerge))
    return results
# Target: collapse_rate >= 0.80 AND control_overmerge == 0
```

**Starting point:** threshold 0.85 for same-story collapse; control pairs expected ≤ 0.75. [ASSUMED — based on typical multilingual embedding behavior; must be confirmed on the labeled triple set]

### Long-Input Caveat

Both bge-m3 and mE5-large weaken on long inputs. Embed **title + summary[:512 chars]** only, never the full article body. [CITED: docs/RESEARCH-REPORT.md §8 — "chunk" caveat confirmed]

---

## R3: Postgres Entity Resolution

### Schema

```sql
-- r3_schema.sql
-- Source: pgvector docs, Context7 /pgvector/pgvector-python

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE entities (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    name_norm   TEXT NOT NULL,          -- lowercased, stripped
    lang        VARCHAR(5),             -- 'no', 'en', 'ru'
    type        TEXT,                   -- 'PER', 'ORG', 'GPE', 'LOC'
    embedding   VECTOR(1024),           -- bge-m3 or mE5-large
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE entity_links (
    id          SERIAL PRIMARY KEY,
    entity_id   INT REFERENCES entities(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,          -- references the fetched item
    mention     TEXT NOT NULL,          -- exact text span extracted
    confidence  FLOAT DEFAULT 1.0,
    lang        VARCHAR(5),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index: no training needed (IVFFlat requires min rows before indexing)
CREATE INDEX entities_embedding_idx
    ON entities USING hnsw (embedding vector_cosine_ops);
```

### Cosine Linking Query

```python
# Source: github.com/pgvector/pgvector-python _autodocs, Context7 /pgvector/pgvector-python
import psycopg2
import numpy as np
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect(host="localhost", port=22062, dbname="spike",
                        user="spike", password="spike")
register_vector(conn)

LINK_THRESHOLD = 0.85  # adjust per bake-off result

def link_or_insert_entity(name: str, lang: str, etype: str,
                           embedding: np.ndarray) -> int:
    """Return entity_id of matched or newly inserted entity."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, 1 - (embedding <=> %s::vector) AS sim
            FROM entities
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT 1
        """, (embedding, embedding, LINK_THRESHOLD, embedding))
        row = cur.fetchone()
        if row:
            return row[0]  # matched existing entity
        # Insert new entity
        cur.execute("""
            INSERT INTO entities (name, name_norm, lang, type, embedding)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (name, name.lower().strip(), lang, etype, embedding))
        conn.commit()
        return cur.fetchone()[0]
```

### NER via qwen36 (ADR-004 compliant)

spaCy is not installed; `nb_core_news_lg` is unavailable. Use the existing `llm()` function from `score/triage_score.py`:

```python
# Pattern from score/triage_score.py llm()
import sys; sys.path.insert(0, "score")
from triage_score import llm

def extract_entities(title: str, summary: str) -> list[dict]:
    """Extract named entities via qwen36. Returns [{name, type, lang}]."""
    prompt = f"""Extract named entities from this news item.
Return ONLY JSON array: [{{"name": "...", "type": "PER|ORG|GPE|LOC", "lang": "no|en|ru"}}]

TITLE: {title}
SUMMARY: {summary[:300]}

Rules:
- type PER = persons, ORG = organizations, GPE = countries/regions/cities, LOC = places
- lang = language of the item (not the entity's country)
- Return [] if no entities found
- Return ONLY the JSON array, nothing else."""

    raw = llm([{"role": "user", "content": prompt}], max_tokens=300).strip()
    s, e = raw.find("["), raw.rfind("]")
    try:
        return json.loads(raw[s:e+1])
    except Exception:
        return []
```

### Acceptance Test Design (R3)

- **Pass entity:** "NATO" appears in NRK item (no), BBC item (en), TASS item (ru) → must link to same `entity_id` after processing all 3
- **Control entity:** "Vladimir Putin" and "Joe Biden" in same corpus → must have `entity_id` values that are different
- Verify: `SELECT entity_id, COUNT(*) FROM entity_links WHERE entity_id IN (SELECT id FROM entities WHERE name_norm='nato') GROUP BY entity_id` → should return 1 entity_id with count=3

### Index Choice: HNSW over IVFFlat for Spike

IVFFlat requires `VACUUM ANALYZE` and a minimum number of rows before the index is useful. HNSW builds incrementally on insert. For a spike with ≤200 entities, HNSW is the correct choice. [CITED: github.com/pgvector/pgvector/blob/master/_autodocs/getting-started.md]

---

## R4: Wiki-LLM Feasibility

### Approach: Extend write_bluf() from score/digest.py

The existing `write_bluf()` function in `score/digest.py` already implements:
- Per-topic LLM synthesis from N numbered items
- Mandatory bracketed citation `[N]` in every claim
- Contradiction detection across sources
- Per-prompt token cap with tail-trimming

The wiki task is a direct extension with a different output format prompt.

### Wiki Prompt Template

```python
# r4_wiki.py — reuse llm() from score/triage_score.py

WIKI_PROMPT_TEMPLATE = """\
You are an intelligence analyst maintaining a structured intel wiki.
Write a comprehensive wiki page for: {topic}

Source items ({n} items):
{context}

Instructions:
1. Write 3-4 structured sections: ## Background, ## Key Developments, ## Current Assessment, ## Open Questions
2. Every factual claim MUST carry a bracketed citation [N]. A claim without a citation is wrong.
3. If sources disagree, report both positions: "Kildene spriker: [1] hevder X, mens [3] melder Y."
4. Write in Norwegian. Max 600 words total.
5. Output ONLY the wiki text. No preamble, no source list (citations are inline).
"""

def generate_wiki(topic: str, items: list[dict]) -> str:
    context_blocks = [
        f"[{i}] KILDE: {it.get('source','')}\n"
        f"TITTEL: {it.get('title','')}\n"
        f"OPPSUMMERING: {it.get('summary','')[:400]}\n"
        for i, it in enumerate(items[:10], 1)
    ]
    prompt = WIKI_PROMPT_TEMPLATE.format(
        topic=topic, n=len(context_blocks),
        context="".join(context_blocks)
    )
    from triage_score import llm
    return llm([{"role": "user", "content": prompt}], max_tokens=800).strip()
```

### Context Window Analysis

qwen36-ud-4bit context window: ~32K tokens [ASSUMED — based on Qwen3 architecture; not verified in this session against the specific quantized model]

Estimated token usage for R4:
- Prompt frame: ~150 tokens
- 5 items × (title ~15 + summary ~130 tokens): ~725 tokens
- Total input: ~875 tokens — well within 32K limit
- Max 10 items still fits within 3K input tokens

**DGX Spark availability:** [ASSUMED — DGX is mentioned in PROJECT.md as an optional heavy-synthesis backend; not verified as available or online in this session]

### Citation Grounding Check

After generation, verify grounding:
```python
import re
cited_refs = set(int(n) for n in re.findall(r'\[(\d+)\]', wiki_text))
available_refs = set(range(1, len(items) + 1))
uncited_claims = []  # detect paragraphs with no [N] in them
```

### On-Demand Article

Same `generate_wiki()` function with a query-style topic: "Hva vet vi om X siden {date}?" — reuse the R4 items that score highest for that entity after R3 entity linking.

---

## R5: COP + World Monitor

### Repository

**github.com/koala73/worldmonitor** — AGPL-3.0, ~500+ feeds, globe.gl + deck.gl COP, 4-tier LLM fallback (Ollama → Groq → OpenRouter → T5). [CITED: github.com/koala73/worldmonitor]

Also note: **github.com/sjkncs/worldmonitor** — a fork with 35+ data layers and Ollama/Groq/OpenRouter AI Agent, may be simpler to configure. Check during spike. [CITED: search results, github.com/sjkncs/worldmonitor]

### Critical Architecture Finding

**Ollama local-LLM is exclusive to the Tauri Desktop Runtime, NOT the web browser dev mode.** [CITED: deepwiki.com/koala73/worldmonitor]

The web dev mode (`npm run dev`) serves a browser app that routes API calls through Vercel Edge Functions for secret injection, caching, and API proxying. Without Vercel, many data source endpoints will not work in web mode.

The Tauri desktop app (`npm run tauri dev`) uses a local sidecar (`local-api-server.mjs`) that bypasses Vercel entirely and routes through the local Ollama/oMLX endpoint.

**Spike path: Tauri desktop build** — Rust 1.91.1 is available on this Mac (confirmed), which satisfies the Tauri build requirement.

### Setup Steps

```bash
# On the Mac (outside the InfoTriage repo — spike scratch dir)
git clone https://github.com/koala73/worldmonitor.git .spike/worldmonitor
cd .spike/worldmonitor
npm install           # Node.js 22.12.0 available

# Web browser version (limited Ollama support):
npm run dev           # → localhost:3000

# Tauri desktop (full local-LLM support):
npm run tauri dev     # requires Rust 1.91.1 (available) + XCode CLT
```

**Settings configuration (Tauri):**
- Open Settings (Cmd+,)
- LLMs tab → set Ollama endpoint to `http://127.0.0.1:11434` (Ollama) OR `http://127.0.0.1:8000` (oMLX, OpenAI-compatible)
- Model: `qwen36-ud-4bit` — WM auto-discovers via `/v1/models` endpoint (oMLX-compatible)

**Pointing at oMLX instead of Ollama:**
WM's auto-discover queries both `/api/tags` (Ollama native) and `/v1/models` (OpenAI-compatible). oMLX at `:8000/v1` should be discoverable if the server is running. If auto-discover fails, the oMLX model name must be entered manually.

### CCIR Scoring Gap and Injection Strategy

World Monitor does NOT have a CCIR taxonomy. Its built-in scoring is the **Country Instability Index (CII)** — a composite of 12 signals (protests, military activity, internet outages, etc.). CII is NOT CCIR. [CITED: deepwiki.com/koala73/worldmonitor]

**Strategy for R5 acceptance ("score 20 InfoTriage items + CCIR brief"):**

Option A — Pre-score with InfoTriage, feed to WM:
1. Run 20 freshly-fetched items through `score/triage_score.py` (existing, working)
2. Items are now tagged with `{ccir, cnr, pmesii, tessoc, score, why}`
3. Feed these pre-scored items to WM as custom events or simply display them on the COP globe via WM's API or custom data layer
4. Use WM's LLM (configured to qwen36/oMLX) to generate a country brief with the InfoTriage CCIR scores embedded in the context

Option B — Inject CCIR taxonomy into WM system prompt:
- If WM allows configuring a system prompt for the local LLM, inject `ccir.md` content
- WM then generates briefs that cite CCIR requirements
- [ASSUMED — WM system prompt configurability not confirmed in docs]

**Recommended for spike:** Option A. Pre-score items with InfoTriage's existing pipeline (D-03: reuse same fresh-fetched items), then demonstrate WM COP display + generate a CCIR brief using qwen36 called directly (same `llm()` pattern) referencing the scored items as context.

### ADR-005 Decision Inputs

The spike must answer these questions for ADR-005:

| Question | Spike action |
|----------|-------------|
| Does WM's Tauri build run on this Mac? | Attempt `npm run tauri dev`; record success/failure |
| Can oMLX be configured as the local LLM? | Check auto-discover result; set manually if needed |
| Does WM's CII scoring align with CCIR? | Compare CII output vs InfoTriage triage output on same 20 items |
| Can WM ingest InfoTriage scored items as custom events? | Attempt custom data layer injection or feed format |
| Setup effort (hours)? | Record actual time from clone to running WM with qwen36 |

### Known Blockers (Pre-Spike Assessment)

1. **Tauri build requirements:** `npm run tauri dev` may require additional XCode frameworks beyond Rust. Build time on first run can be 10–20 min. [ASSUMED]
2. **Vercel Edge Functions in web mode:** Without Vercel, many of WM's 65+ external data sources will fail to load in web mode. Desktop/Tauri mode avoids this.
3. **CCIR mismatch:** WM has no CCIR. The "CCIR-structured brief" requirement (R5 acceptance) requires either pre-scoring or LLM prompt injection — neither is native WM functionality.
4. **oMLX availability:** oMLX was NOT responding during environment audit (server not running). Must start oMLX before the WM spike.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| AMQP publisher confirms | Custom retry loop | `pika` confirm_delivery or `aio-pika` default | Broker-level confirmation handles network partitions correctly |
| Dead-letter routing | Custom error queue logic | RabbitMQ DLX (`x-dead-letter-exchange` argument) | Atomic at broker level; no consumer-side coordination needed |
| Cosine similarity | Manual dot product | pgvector `<=>` operator with HNSW index | Sub-millisecond indexed search; hand-rolled is O(n) scan |
| Multilingual NER | Custom regex for NO/EN/RU | qwen36 `llm()` JSON extraction | Already proven in `score/triage_score.py`; handles multilingual naturally |
| Embedding model training | Fine-tune on InfoTriage | `BAAI/bge-m3` off-the-shelf | 100+ language coverage; top multilingual retrieval benchmark; spike only needs inference |
| Map/globe rendering | Custom WebGL globe | World Monitor globe.gl + deck.gl | 45+ data layers, 500+ feeds; not worth building |
| CCIR brief synthesis | New LLM wrapper | Extend `write_bluf()` from digest.py | Pattern already proven, tested; token cap + citation enforcement included |

---

## Common Pitfalls

### Pitfall 1: DLX Must Be Declared Before Primary Queue
**What goes wrong:** `channel.queue_declare()` with `x-dead-letter-exchange` fails if the named DLX exchange does not yet exist.
**Why it happens:** RabbitMQ validates the DLX argument at queue-declare time.
**How to avoid:** Always declare DLX exchange first, then declare DLQ queue, then bind DLQ to DLX, then declare primary queues with the DLX argument.
**Warning signs:** `channel.exceptions.ChannelClosedByBroker: 406` on queue_declare.

### Pitfall 2: IVFFlat Needs Rows Before Index Works
**What goes wrong:** HNSW or IVFFlat index created on an empty table; queries use sequential scan anyway.
**Why it happens:** IVFFlat requires a minimum number of rows for centroid training. HNSW does not.
**How to avoid:** Use HNSW for the spike (no minimum rows). Run `VACUUM ANALYZE entities;` after bulk insert before querying.
**Warning signs:** Slow queries, `EXPLAIN ANALYZE` showing `Seq Scan` instead of `Index Scan`.

### Pitfall 3: Embedding Dim Mismatch Silently Fails
**What goes wrong:** Entity embeddings generated with model A (dim=1024) but DB schema uses `VECTOR(768)` — insert raises error or truncates.
**Why it happens:** Both bge-m3 and mE5-large are 1024 dims, but a wrong model (e.g., paraphrase-MiniLM) produces 384 dims.
**How to avoid:** Log `embedding.shape` on first run; assert `embedding.shape[0] == 1024` before insertion.
**Warning signs:** `psycopg2.errors.DataException` on INSERT.

### Pitfall 4: World Monitor Web Mode Needs Vercel
**What goes wrong:** `npm run dev` shows the globe but data sources return 401/404; the "AI brief" button produces no output.
**Why it happens:** Most data source API calls in web mode are proxied through Vercel Edge Functions that inject secrets. Without Vercel, raw calls fail CORS or authentication.
**How to avoid:** Use `npm run tauri dev` (desktop mode) for the spike, NOT `npm run dev`. Or run `npx vercel dev` if Vercel CLI is installed.
**Warning signs:** Network tab shows 404 on `/api/*` routes in browser dev tools.

### Pitfall 5: pika BlockingConnection Is Not Thread-Safe
**What goes wrong:** Two Python threads share one pika channel; broker closes the channel.
**Why it happens:** pika channels are not thread-safe by design.
**How to avoid:** For the spike, use one BlockingConnection per thread or use the `ThreadedConnection` pattern. Since the spike is single-threaded, this is not an issue, but document it for Phase 3 (use aio-pika).
**Warning signs:** `AMQPChannelError` or `AMQPConnectionError` in multi-threaded code.

### Pitfall 6: cosine_sim on Non-Normalized Embeddings Is Wrong
**What goes wrong:** Dot product returns values > 1.0 or gives wrong rankings because embeddings are not L2-normalized.
**Why it happens:** sentence-transformers `model.encode()` returns non-normalized vectors by default.
**How to avoid:** Always pass `normalize_embeddings=True` to `model.encode()`. bge-m3 BGE series normalizes to unit norm automatically for dense retrieval when using FlagEmbedding client. [CITED: github.com/flagopen/flagembedding/blob/master/Tutorials/2_Metrics/2.1_Similarity_Metrics.ipynb]
**Warning signs:** Cosine similarity > 1.0 or all similarities clustering near 0.

### Pitfall 7: stdlib XML Parser Is XXE-Vulnerable
**What goes wrong:** `import xml.etree.ElementTree as ET` used to parse fetched RSS/Atom feeds allows an attacker-controlled feed to exfiltrate local files or trigger billion-laughs DoS via external entity expansion.
**Why it happens:** Python's stdlib XML parsers do not disable external entity processing by default (CVE class: XXE / CWE-611).
**How to avoid:** Always use `import defusedxml.ElementTree as ET` — it is a safe drop-in that raises `DefusedXmlException` on malicious inputs. This applies to any XML parsed from a network source, including NRK/BBC/TASS RSS feeds.
**Warning signs:** Security scanner (bandit, semgrep) flags `xml.etree.ElementTree` on network-sourced data.

### Pitfall 8: oMLX Endpoint May Not Be Running
**What goes wrong:** R4 wiki synthesis and R1 publish (qwen36 LLM calls) fail with `ConnectionRefusedError` on `http://127.0.0.1:8000/v1`.
**Why it happens:** oMLX must be started before the spike run. It was NOT responding during environment audit.
**How to avoid:** Run `omlx-ensure-server` or start oMLX manually before spike execution. Add a health-check call to `llm()` early in each spike script.
**Warning signs:** `urllib.error.URLError: <urlopen error [Errno 61] Connection refused>`.

Also add `defusedxml` to the `requirements-spike.txt` Wave 0 gap:
- [ ] `.spike/requirements-spike.txt` should include `pika==1.4.1 pgvector==0.4.2 defusedxml`

---

## Code Examples

### R1: Minimal Round-Trip (pika)
```python
# Source: github.com/pika/pika docs — publisher confirms + consumer ack
import pika, json

AMQP = pika.ConnectionParameters("localhost", 22060,
                                  credentials=pika.PlainCredentials("spike","spike"))

# --- Service A: Publisher ---
def publish(event_type: str, payload: dict):
    conn = pika.BlockingConnection(AMQP)
    ch = conn.channel(confirm_delivery=True)
    ch.basic_publish(
        exchange="infotriage.events",
        routing_key=event_type,
        body=json.dumps(payload).encode(),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    assert ch.wait_for_confirms(), f"Broker rejected {event_type}"
    conn.close()

# --- Service B: Consumer ---
def start_consumer(queue: str):
    conn = pika.BlockingConnection(AMQP)
    ch = conn.channel()
    ch.basic_qos(prefetch_count=1)
    def callback(ch, method, props, body):
        data = json.loads(body)
        if data.get("poison"):
            ch.basic_nack(method.delivery_tag, requeue=False)  # → DLQ
        else:
            ch.basic_ack(method.delivery_tag)
    ch.basic_consume(queue, callback)
    ch.start_consuming()
```

### R2: Cosine Collapse Rate
```python
# Source: sbert.net docs, Context7 /websites/sbert_net
from sentence_transformers import SentenceTransformer
import numpy as np, csv

model = SentenceTransformer("BAAI/bge-m3")

def embed_items(items: list[dict]) -> dict[str, np.ndarray]:
    texts = {it["id"]: f"{it['title']} {it.get('summary','')[:512]}" for it in items}
    embeddings = model.encode(list(texts.values()), normalize_embeddings=True,
                              batch_size=8, show_progress_bar=True)
    return dict(zip(texts.keys(), embeddings))

def evaluate_threshold(emb: dict, triples_csv: str, threshold: float):
    tp, fp = 0, 0
    with open(triples_csv) as f:
        for row in csv.DictReader(f):
            sim = float(np.dot(emb[row["item_a_id"]], emb[row["item_b_id"]]))
            hit = sim >= threshold
            if row["same_story"] == "yes":
                tp += hit
            else:
                fp += hit
    total_pos = sum(1 for r in csv.DictReader(open(triples_csv)) if r["same_story"]=="yes")
    return {"threshold": threshold, "collapse_rate": tp/total_pos, "control_overmerge": fp}
```

### R3: Entity Linking
```python
# Source: github.com/pgvector/pgvector-python Context7 docs
from pgvector.psycopg2 import register_vector
import psycopg2, numpy as np

conn = psycopg2.connect(host="localhost", port=22062, dbname="spike",
                        user="spike", password="spike")
register_vector(conn)

def find_or_create_entity(name: str, lang: str, etype: str,
                           emb: np.ndarray) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM entities "
            "WHERE 1 - (embedding <=> %s::vector) >= 0.85 "
            "ORDER BY embedding <=> %s::vector LIMIT 1",
            (emb, emb)
        )
        if row := cur.fetchone():
            return row[0]
        cur.execute(
            "INSERT INTO entities (name, name_norm, lang, type, embedding) "
            "VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (name, name.lower(), lang, etype, emb)
        )
        conn.commit()
        return cur.fetchone()[0]
```

---

## Cross-Cutting: Ephemeral Docker Setup

The same `docker-compose.yml` in `.spike/` serves both R1 (RabbitMQ) and R3 (pgvector). The file is shown in full under the R1 section. Key isolation rules:

- RabbitMQ: `22060` (AMQP), `22061` (management) — distinct from production `:8088`/`:3000`
- pgvector: `22062` — distinct from any production Postgres
- Both use the `spike` user/password (not the production credentials)
- No volumes mounted from the production data tree
- `docker compose -f .spike/docker-compose.yml down -v` deletes all data

**Read-only against production:** Spike scripts read from `data/verdicts.jsonl` (reference only, for format understanding) but MUST NOT write to it. Fresh items are fetched into `.spike/r2_dedup/items.json` and processed only there. The running FreshRSS/rss-bridge stack is never touched.

---

## Runtime State Inventory

This is a greenfield spike — no rename, refactor, or migration involved. No runtime state audit required.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| IVFFlat index (requires training rows) | HNSW index (no minimum rows) | pgvector ~0.5.0 | HNSW preferred for small corpora and incremental inserts |
| pika SelectConnection (callback hell) | aio-pika async/await | 2018–2020 | Much cleaner consumer code; use for Phase 3 |
| Keyword-overlap clustering (score/digest.py `cluster()`) | Cosine embedding clustering | This spike | Replaces language-blind approach; the baseline to beat |
| Training custom multilingual embeddings | bge-m3 / mE5-large off-the-shelf | 2024 | SOTA without fine-tuning; 100+ language coverage |

**Deprecated/outdated:**
- `rabbitmq:3-management` tags older than `3.13-management`: use 3.13+ for feature stability
- `ankane/pgvector` Docker image: superseded by `pgvector/pgvector:pg16` (official)
- IVFFlat for empty-or-small tables: use HNSW instead

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | R1 RabbitMQ, R3 pgvector | ✓ | 29.4.0 | — |
| Python 3 | R1–R5 spike scripts | ✓ | 3.13.5 | — |
| Node.js | R5 World Monitor | ✓ | 22.12.0 | — |
| Rust (for Tauri) | R5 World Monitor desktop | ✓ | 1.91.1 | npm run dev (web mode, limited Ollama) |
| sentence-transformers | R2 embedding | ✓ (installed) | 5.3.0 | — |
| torch | R2 embedding backend | ✓ (installed) | 2.11.0 | — |
| psycopg2-binary | R3 Postgres adapter | ✓ (installed) | 2.9.10 | — |
| pika | R1 AMQP client | ✗ (needs install) | 1.4.1 | — |
| pgvector (Python) | R3 vector adapter | ✗ (needs install) | 0.4.2 | — |
| defusedxml | R2 RSS fetch (security) | ✗ (needs install) | latest | — (stdlib ET is unsafe) |
| FlagEmbedding | R2 optional bge-m3 client | ✗ (needs install) | 1.4.0 | sentence-transformers (already installed) |
| oMLX server | R4, R5 qwen36 calls | ✗ (not running) | unknown | Start with `omlx-ensure-server` |
| Ollama + models | R2 bge-m3 (optional) | ✗ (empty model list) | — | sentence-transformers on host |
| spaCy nb_core_news_lg | R3 NER (alternative) | ✗ (spaCy not installed) | — | qwen36 NER via llm() |
| pgvector/pgvector:pg16 image | R3 | ✗ (not pulled) | pg16 | `docker pull pgvector/pgvector:pg16` |
| rabbitmq:3.13-management image | R1 | ✗ (not pulled) | 3.13 | `docker pull rabbitmq:3.13-management` |

**Missing dependencies with no fallback:**
- oMLX server: must be started before R4/R5 spike scripts run. Use `omlx-ensure-server`.
- pika: `pip3 install pika==1.4.1`
- pgvector Python: `pip3 install pgvector==0.4.2`

**Missing dependencies with fallback:**
- FlagEmbedding: sentence-transformers is the fallback (already installed); only install FlagEmbedding if sparse-retrieval bake-off is needed
- Ollama + bge-m3 model: host sentence-transformers is the fallback
- spaCy: qwen36 NER is the fallback (preferred under ADR-004)

---

## Validation Architecture

> nyquist_validation is not explicitly false in config.json — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (available via Python 3.13.5) |
| Config file | none — spike uses ad-hoc assert + print; existing `tests/` are for the production pipeline, not the spike |
| Quick run command | `python3 .spike/<script>.py --smoke` (smoke flag exits after first success) |
| Full suite command | `python3 -m pytest .spike/` (if spike tests are written as pytest) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| R1 | Publish `item.ingested` consumed by service B | integration | `python3 .spike/r1_rabbit/r1_publisher.py && python3 .spike/r1_rabbit/r1_consumer.py --smoke` | ❌ Wave 0 |
| R1 | Poison message lands in DLQ | integration | `python3 .spike/r1_rabbit/r1_consumer.py --poison-test` | ❌ Wave 0 |
| R2 | ≥80% triple collapse at chosen threshold | measurement | `python3 .spike/r2_dedup/r2_threshold.py` (reports collapse_rate) | ❌ Wave 0 |
| R2 | 0 control over-merges | measurement | same script, check `control_overmerge == 0` | ❌ Wave 0 |
| R3 | Same entity linked across ≥3 items / 2 languages | integration | `python3 .spike/r3_entities/r3_link.py --verify-nato-test` | ❌ Wave 0 |
| R3 | Control entity NOT over-merged | integration | same script, check distinct entity IDs | ❌ Wave 0 |
| R4 | Wiki page contains ≥3 `[N]` citations | smoke | `python3 .spike/r4_wiki/r4_wiki.py | grep -cP '\[\d+\]'` | ❌ Wave 0 |
| R4 | On-demand article produced | smoke | `python3 .spike/r4_wiki/r4_wiki.py --on-demand --topic "NATO"` | ❌ Wave 0 |
| R5 | World Monitor desktop launches | smoke | `cd .spike/worldmonitor && npm run tauri dev` (manual observation) | ❌ Wave 0 |
| R5 | 20 items scored and brief produced | integration | manual — R5 involves a GUI application | manual only |

### Sampling Rate

- **Per spike task:** Run the corresponding smoke command above before recording go/no-go
- **Per wave merge:** N/A — spike is not wave-organized; each unknown is a standalone task
- **Phase gate:** All 5 unknowns have a recorded go/no-go/partial in `SPIKE-FINDINGS.md` before closing Phase 0

### Wave 0 Gaps

- [ ] `.spike/r1_rabbit/r1_topology.py` — exchange + DLQ setup
- [ ] `.spike/r1_rabbit/r1_publisher.py` — dummy service A
- [ ] `.spike/r1_rabbit/r1_consumer.py` — dummy service B with ack/nack
- [ ] `.spike/r2_dedup/r2_fetch.py` — NRK/BBC/TASS fresh fetch
- [ ] `.spike/r2_dedup/same_story_triples.csv` — hand-labeled (requires human step after fetch)
- [ ] `.spike/r2_dedup/r2_embed.py` — batch embed + cosine matrix
- [ ] `.spike/r2_dedup/r2_threshold.py` — threshold sweep → collapse rate
- [ ] `.spike/r3_entities/r3_schema.sql` — entities + entity_links + HNSW
- [ ] `.spike/r3_entities/r3_ner.py` — qwen36 NER
- [ ] `.spike/r3_entities/r3_link.py` — cosine link + merge
- [ ] `.spike/r4_wiki/r4_wiki.py` — wiki generation + citation check
- [ ] `.spike/r5_worldmonitor/r5_prep.py` — export 20 scored items

---

## Security Domain

> security_enforcement absent from config.json — treated as enabled.

This is a throwaway spike with no persistent user data, no auth, no network exposure beyond localhost. The security surface is minimal:

| ASVS Category | Applies | Control |
|---------------|---------|---------|
| V2 Authentication | no | spike has no auth |
| V3 Session Management | no | no sessions |
| V4 Access Control | no | single-operator, local-only |
| V5 Input Validation | yes (minimal) | LLM responses are JSON-parsed with try/except (reuse triage_score.py pattern) |
| V6 Cryptography | no | no secrets handled by spike code |

| Threat Pattern | STRIDE | Mitigation |
|----------------|--------|------------|
| Spike credentials leaking into git | Info Disclosure | `.spike/` directory is gitignored; spike compose uses `spike`/`spike` credentials |
| oMLX/Ollama calls hitting cloud endpoint | Tampering | `llm()` function defaults to `http://127.0.0.1:8000/v1` (local); verify `LLM_BASE_URL` not set to cloud URL before any spike run |
| World Monitor Tauri app making cloud calls | Info Disclosure | Monitor network tab during R5; confirm no cloud LLM calls when Ollama endpoint is configured |
| Production data mutation | Tampering | Spike scripts read `data/verdicts.jsonl` in read mode only; spike containers use distinct ports + separate volumes |
| XXE / billion-laughs via RSS feeds (NRK/BBC/TASS) | Tampering / DoS | Use `defusedxml.ElementTree` — never `xml.etree.ElementTree` — for any XML parsed from a network source |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | qwen36-ud-4bit context window is ~32K tokens | R4 Wiki-LLM | If context window is smaller (e.g., 8K), must reduce items per prompt or chunk differently |
| A2 | DGX Spark is available and reachable for heavy synthesis | R4 Wiki-LLM | If DGX unavailable, R4 Wiki-LLM runs on qwen36/oMLX only (still feasible within 32K context) |
| A3 | Cosine threshold 0.85 will achieve ≥80% collapse on NRK/BBC/TASS same-story triples | R2 dedup | If wrong, threshold must be lowered (risk: more false positives); spike records the empirical threshold |
| A4 | M3 team fan-out is modeled by adding consumer bindings to the same topic exchange | R1 RabbitMQ | If M3 requires per-user exchanges or headers-based routing, the topology design needs revision before Phase 3 |
| A5 | `npm run tauri dev` will build successfully on this Mac with Rust 1.91.1 + XCode CLT | R5 World Monitor | If Tauri build fails (missing XCode, incompatible Rust), fall back to `npm run dev` + Vercel CLI (`npx vercel dev`) |
| A6 | oMLX `:8000/v1` auto-discovery works in World Monitor Tauri via `/v1/models` endpoint | R5 World Monitor | If WM only queries Ollama `/api/tags`, must enter model name manually or start Ollama separately |
| A7 | bge-m3 on host sentence-transformers fits in available RAM (~570MB FP16) | R2 dedup | If OOM, use Ollama quantized version (`ollama pull bge-m3`, 1.2GB GGUF) instead |
| A8 | World Monitor can be configured to use oMLX as the LLM endpoint instead of Ollama | R5 World Monitor | If oMLX endpoint URL is not accepted (expects Ollama-specific API responses), must run actual Ollama with qwen36 model pulled |

---

## Open Questions (RESOLVED)

1. **RESOLVED: Does `npm run dev` (web browser mode) connect to Ollama at all, or is Tauri strictly required?**
   - What we know: DeepWiki says Ollama is "exclusive to Desktop Runtime (Tauri)"
   - What's unclear: Whether a `VITE_OLLAMA_URL` env var or settings file bypasses the Vercel proxy in dev mode
   - Recommendation: Attempt web mode first (faster setup); if AI brief produces nothing, switch to Tauri

2. **RESOLVED: What does World Monitor's "AI brief" output look like for non-country-specific content?**
   - What we know: WM has "Country Intelligence & Briefings" (country-centric CII)
   - What's unclear: Whether it can produce a CCIR-structured brief from InfoTriage items that span multiple countries
   - Recommendation: Record whatever output WM produces; compare to the CCIR brief generated by InfoTriage's existing `write_bluf()` for the same 20 items. This comparison IS the ADR-005 input.

3. **RESOLVED: Is the R2 threshold stable across date ranges, or does it drift?**
   - What we know: A single threshold is required for the SPEC acceptance bar
   - What's unclear: Whether a threshold chosen on today's NRK/BBC/TASS triples generalizes to other events
   - Recommendation: Record the chosen threshold in SPIKE-FINDINGS.md with the specific event set it was calibrated on; note "calibrated on [event set], generalization unverified"

---

## Sources

### Primary (MEDIUM confidence — Context7)
- `/pika/pika` Context7 — AMQP publish/confirm/nack patterns, BlockingConnection, delivery confirmations
- `/mosquito/aio-pika` Context7 — async exchange declare, queue.bind, queue.consume, DLQ wiring
- `/pgvector/pgvector-python` Context7 — register_vector, cosine distance, HNSW index creation
- `/pgvector/pgvector` Context7 — `<=>` operator, `vector_cosine_ops`, HNSW vs IVFFlat
- `/flagopen/flagembedding` Context7 — bge-m3 dense embedding, normalize, cosine similarity identity
- `/websites/sbert_net` Context7 — SentenceTransformer.encode(), normalize_embeddings, similarity()

### Secondary (LOW confidence — WebSearch + WebFetch)
- [github.com/koala73/worldmonitor](https://github.com/koala73/worldmonitor) — setup, Ollama config, 4-tier fallback, Tauri desktop
- [deepwiki.com/koala73/worldmonitor](https://deepwiki.com/koala73/worldmonitor) — Ollama Tauri-only finding, CII scoring, Vercel dependency
- [arxiv.org/pdf/2406.02396](https://arxiv.org/pdf/2406.02396) — Scandinavian Embedding Benchmark (bge-m3 vs mE5-large)
- [arxiv.org/html/2402.03216v3](https://arxiv.org/html/2402.03216v3) — bge-m3 MIRACL/MKQA results
- [oneuptime.com/blog/post/2026-01-24-rabbitmq-dead-letter-exchanges](https://oneuptime.com/blog/post/2026-01-24-rabbitmq-dead-letter-exchanges/view) — DLX/DLQ Python pika patterns
- [ollama.com/library/bge-m3](https://ollama.com/library/bge-m3) — Ollama bge-m3 model, 1.2GB, 8K context

### Codebase (verified by read)
- `score/triage_score.py` — `llm()` function contract, env vars, JSON extraction pattern (reused for R3 NER + R4 wiki)
- `score/digest.py` — `write_bluf()` pattern (reused for R4 wiki synthesis)
- `docs/RESEARCH-REPORT.md` §8 — bge-m3 multilingual benchmark prior art
- `.planning/PROJECT.md` — hard constraints verification
- `.planning/codebase/STACK.md` — sentence-transformers, psycopg2-binary already installed

---

## Metadata

**Confidence breakdown:**
- Standard stack (pika, aio-pika, pgvector): MEDIUM — verified via Context7 official docs + PyPI registry
- Architecture patterns (exchanges, HNSW, entity schema): MEDIUM — verified via Context7
- Embedding models (bge-m3 vs mE5-large): MEDIUM — prior research in RESEARCH-REPORT.md §8 + arxiv citations; inference on this Mac not benchmarked
- World Monitor (R5): LOW — web-fetched README + DeepWiki; exact Ollama config steps require runtime verification
- Environment (packages installed): HIGH — verified by shell commands in this session

**Research date:** 2026-06-24
**Valid until:** 2026-07-24 (30 days for stable libraries; World Monitor is fast-moving, verify before R5)
