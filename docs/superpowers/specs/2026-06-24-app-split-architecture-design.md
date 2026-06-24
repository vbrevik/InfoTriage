# InfoTriage — App-Split Architecture Design

> Date: 2026-06-24 · Status: approved (brainstorming session) · Supersedes the deferred
> architecture cut of `docs/ARCHITECTURE.md` Phases 2–7 with an explicit, event-driven,
> multi-container target. Roadmap reconciliation in the final section.

## Goal

Split the InfoTriage monolith (host-run `bridge/`, `score/`, `opml/` scripts + 3 off-shelf
containers) into **independent, single-purpose apps** that communicate through a **message
bus** and a **robust canonical store**, all in **Docker**, on one Mac, all-local, all-free.
RSS/Atom is demoted from the spine to one projection among several, because much source
content (full email MIME, transcripts, PDFs, structured rows) does not fit RSS.

## Principles

1. **Canonical `Item` is the truth.** RSS/Atom, FreshRSS, Obsidian are downstream *projections*.
2. **Split by pipeline stage**, not by source: ingest → aggregate → triage → brief.
3. **Apps never import each other.** They share only `libs/contracts` (schemas + bus client)
   and talk over the bus + canonical store.
4. **Bus = transport. Postgres = durable truth. Projections = views.** Three distinct roles.
5. **Everything in Docker.** No host services. The only host dependency is the external local
   LLM (oMLX), reached via `host.docker.internal:8000` — it is not a service this stack owns.
6. **Dedicated port band 22000–22099**, assigned from the first commit, to avoid collision
   with other stacks on this Mac.

## Final decisions — assumption review (2026-06-24)

These override any earlier inline mentions in this doc (notably: transport is **RabbitMQ**, not
Redis Streams).

- **Architecture style:** full **microservices** kept — justified by the growth path below, not
  over-engineering.
- **Growth trajectory:** single operator on one Mac **now**, but containerized so the solution can
  grow into a **multi-user team server for information-sharing**. Design honors this: containers +
  message broker now; auth/tenancy deferred.
- **Multi-user:** **deferred to its own future milestone.** Build pure single-user now — NO
  owner/tenant fields, NO auth. Refactor for multi-user when a team actually adopts it.
- **Message bus:** **RabbitMQ (AMQP) from the start** — routing keys, fan-out, per-consumer queues,
  acks, DLQ. Models team information-sharing topologies directly and avoids a later migration. The
  bus client still lives behind a `libs/contracts` interface so the broker stays swappable.
- **COP / map UI:** **gated spike, NOT a built phase.** Validate need + World Monitor adopt-vs-build
  in a non-blocking spike before committing any UI build.
- **Entity graph:** truth = **Postgres entities table + pgvector linking/resolution**; Obsidian
  wikilinks are a **projection** of it, not the entity system. Neo4j only if graph queries are later needed.
- **LLM model strategy:** **split roles** — dedicated multilingual (Norwegian-capable) **embedding
  model** for dedup/RAG, **qwen36** for chat/synthesis (triage, BLUF), **DGX Spark** as optional
  heavy-synthesis backend (RAG, Wiki-LLM). Not one model for everything.
- **Concept spike scope:** narrowed to **unproven bits only** — RabbitMQ topology, COP need,
  Wiki-LLM feasibility, Norwegian semantic dedup quality, entity resolution. The already-working,
  tested ingest→score→brief pipeline is NOT re-spiked.

## Apps (containers)

| App | Job | In → Out |
|-----|-----|----------|
| `ingest-{gmail,imap,youtube,web,obsidian}` | fetch source, normalize to canonical `Item` | source → `item.ingested` + canonical store + Atom projection |
| `freshrss` (off-shelf) | human feed-reader UI + browse dedup | Atom files → web UI |
| `rssbridge` (off-shelf) | sites → RSS | site → RSS |
| `triage` | LLM CCIR/PMESII/TESSOC scoring | `item.ingested` → `verdict.ready` + verdicts in store |
| `brief` | cluster + render SAB/digest + vault-writer | `verdict.ready` → `sab.published` + sab.html + vault `.md` |
| `opml-health` | scheduled feed health check | cron → `feed.unhealthy` |
| `postgres` | canonical store | — |
| `redis` | transport (Streams) | — |

## The glue — `libs/contracts`

Single source of truth, installed into every Python image. Apps depend on it, never on each other.

- **Canonical `Item` schema**
  - core: `id, source, source_type, url, title, ts, lang`
  - content: `summary` (short, RSS-safe) + `body_ref` → blob
  - rich: `payload {}` (source-specific structured JSON — email headers, transcript segments,
    GDELT fields, geo, entities)
  - refs: `attachments[]` → blob refs (PDF, image, raw HTML, audio)
- **Event schemas**: `item.ingested`, `verdict.ready`, `sab.published`, `feed.unhealthy`
- **Bus client**: publish/subscribe, consumer groups, idempotency keys (dedup by item id)
- **`frontmatter ⇆ payload` codec**: lossless map between Obsidian YAML front-matter and
  Postgres JSONB. The one place that bridges JSON-native and markdown-native worlds.

## Storage — polyglot, by data kind

| Store | Holds | Native for |
|-------|-------|-----------|
| **Postgres** (JSONB + FTS + **pgvector** + optional PostGIS) | Item rows, `payload`, verdicts, embeddings | structured JSON, full-text, semantic vectors, geo |
| **Blob store** (`data/blobs/<hash>`, on disk) | MIME, PDF, transcripts, raw HTML, images | large binary payloads (never in DB) |
| **Redis Streams** | events in flight | transport only — not durable truth |
| **FreshRSS** | Atom projection (RSS/YouTube only) | optional feed-river browsing — NOT a store, NOT for email |
| **Obsidian vault** | markdown notes + graph | markdown-native UX + entity graph via `[[wikilinks]]` |

**Reading-surface routing (decided 2026-06-24):**
- **Email → triage-only.** Email items land in Postgres, go straight to triage; only items that
  score surface in the **SAB** and as **Obsidian** notes. No raw newsletter river anywhere —
  matches the noise-killer goal. Email is NOT projected to FreshRSS.
- **RSS/YouTube → FreshRSS** (Atom projection) for optional river browsing, plus triage.
- **FreshRSS is no longer load-bearing** — Postgres is the store and triage reads events, not the
  Fever API. FreshRSS is a convenience reader; droppable later if unused.

- **Postgres over SQLite** because the architecture has *concurrent writers* (N ingest
  adapters + triage); SQLite's single-writer lock would bottleneck. JSONB gives document
  flexibility; `pgvector` gives cross-source semantic dedup + SAB clustering (replacing
  keyword overlap); PostGIS optional for PMESII geolocation.
- **JSON is native in Postgres** (JSONB, GIN-indexed, JSONPath). **Markdown is native in
  Obsidian** (graph, backlinks, render). The codec maps between them losslessly.

## Obsidian — bidirectional

- **As source**: an `ingest-obsidian` adapter reads `Vault/articles-inbox/` clips →
  canonical `Item` (markdown body → blob, front-matter → `payload`).
- **As projection**: `brief`'s vault-writer emits high-value items + the SAB as `.md` notes —
  front-matter = structured slice (`ccir_cat`, scores, entities), body = summary, `[[entity]]`
  wikilinks. **Obsidian's graph view is the PMESII/TESSOC entity graph for free**, deferring
  (likely replacing) a dedicated Neo4j store.

## Ingestion auth & self-hosted MCP layer

Rich sources that need OAuth2 (Gmail, and later others) are ingested through **self-hosted,
OAuth2-backed MCP servers** running as containers in the stack. The ingest adapter is a thin
**MCP client**; the MCP server owns the OAuth token + source API. This makes "use an MCP server"
the ingestion *pattern*, not a one-off.

- **Gmail reality (verified 2026-06-24):** the account has 2-Step Verification ON and app
  passwords are hard-blocked (Advanced Protection / policy) — IMAP+app-password is a dead end.
  The legacy `bridge/gmail_to_atom.py` IMAP path is therefore **retired** for this account.
- **Proven path:** Gmail read via OAuth2 MCP works live — a one-time pull through the claude.ai
  Gmail connector produced a valid `data/feeds/gmail.xml` (20 entries) with no app password.
- **Runtime path (planned):** `ingest-gmail` adapter → **self-hosted Gmail MCP server** (its own
  OAuth2 refresh token, headless-safe). The claude.ai connector is interactive-only (token bound
  to the Claude session, dies in cron/headless) so it is a dev/verify aid, NOT the runtime.
- IMAP (non-Gmail) and YouTube bridges stay as-is — they're verified working and need no OAuth.

## Data flow

```
articles-inbox/ ─┐
feeds/email/yt ──┼─→ canonical (Postgres + blobs) ─→ [item.ingested] ─→ triage
                 ┘            │                                            │
                             Atom projection ─→ FreshRSS            [verdict.ready]
                                                                          │
                                       brief ─→ sab.html ─────────────────┤
                                       vault-writer ─→ sources/*.md  ◄─────┘
                                                       (front-matter + [[entities]])
```

## Repo layout (monorepo, multi-container)

```
apps/ingest/{gmail,imap,youtube,web,obsidian}/  + Dockerfile each
apps/triage/      + Dockerfile
apps/brief/       + Dockerfile   (SAB renderer + vault-writer)
apps/opml-health/ + Dockerfile
libs/contracts/   (Item, events, bus client, frontmatter⇆payload codec)
docker-compose.yml   (all apps + postgres + redis + freshrss + rssbridge)
ops/Makefile         (up / logs / replay / backfill)
.env                 (port map + LLM endpoint + secrets)
```

## Port map — 22000–22099 (assigned from first commit)

Bands: `2200x` datastores · `2201x` off-shelf UIs/ops · `2202x` ingest · `2203x` processing · `2204x` outputs.

| Port | Service | Exposed |
|------|---------|---------|
| 22000 | postgres | host (db tools) |
| 22001 | redis | host (debug) |
| 22002 | adminer/pgweb *(opt)* | host |
| 22010 | freshrss | host |
| 22011 | rss-bridge | host |
| 22012 | dozzle *(opt logs)* | host |
| 22020 | ingest-gmail | health only |
| 22021 | ingest-imap | health only |
| 22022 | ingest-youtube | health only |
| 22023 | ingest-web | health only |
| 22024 | ingest-obsidian | health only |
| 22030 | triage | health only |
| 22031 | brief | health only |
| 22032 | opml-health | health only |
| 22040 | sab-server | host |
| 22041 | feeds (Atom projection) | compose-net |

Internal traffic (worker→postgres/redis) uses the `infotriage` compose network by service
name and consumes no host port. External LLM: `host.docker.internal:8000` via `.env`.

## Phases (target + non-breaking migration)

Migration stays alive throughout via **dual-write** then **shadow + cut over**.

- **P0 — Canonical model + contracts.** `Item` schema, event schemas, `frontmatter⇆payload`
  codec, `libs/contracts`. Monorepo skeleton (`apps/`, `libs/`). No behavior change.
- **P1 — Storage layer.** Postgres (JSONB + FTS + pgvector) + disk blob store + Atom-projection
  writer behind one `store` interface, in Docker on port 22000. Existing scripts read/write through it.
- **P2 — Bus foundation.** Redis Streams (22001) + bus client (consumer groups, idempotency).
  Smoke-test round-trip.
- **P3 — Ingest adapters.** Containerize bridges as light + rich adapters (incl. `ingest-obsidian`).
  Write canonical store + Atom projection + publish `item.ingested`. Dual-write; nothing breaks.
- **P4 — Triage app.** Subscribe `item.ingested`, drop Fever-poll, read full payload from store,
  write verdicts, publish `verdict.ready`. Shadow vs old path, then cut over. pgvector dedup.
- **P5 — Brief app.** Worker on `verdict.ready` → SAB/digest renderer + vault-writer →
  `sab.published`. pgvector semantic clustering.
- **P6 — Ops layer.** `opml-health` worker, compose healthchecks + restart, structured logging,
  `ops/Makefile`, replay/backfill runbook. Delete dead host-script path.
- **P7 (opt) — Hardening + graph.** DLQ for poison items, stream retention, metrics, PostGIS geo.
  Dedicated entity graph only if Obsidian graph is outgrown.

## Reconciliation with existing ROADMAP

The current roadmap (Phases 0–7, "ingester-first, defer architecture") deferred Postgres/
embeddings/RAG until ingest proved value. This design commits to that architecture now and
adds the app-split + event bus + Obsidian + Docker-all + port-band dimensions. Mapping:

- Existing **Phase 1 (stabilize + ingesters)** → feeds this design's P3 adapter work.
- Existing **Phase 3 (Postgres + pgvector)** → this design's **P1**.
- Existing **Phase 4 (embeddings + dedup)** → folded into **P4** (pgvector dedup).
- Existing **Phase 5 (RAG SAB)** → folded into **P5**.
- **New** here: P0 contracts/canonical-model, P2 event bus, Obsidian dual-role, Docker-all +
  22000 port band, frontmatter⇆payload codec, ops layer (P6).

Treat this as a **new milestone** (architecture re-sequencing) layered on the proven ingest spike.
```

## Open / deferred

- World Monitor COP gate (existing Phase 2) is orthogonal — it picks the *reading/COP UI*, not
  the ingest/store/triage spine this design covers. Keep as a parallel spike.
- Neo4j entity graph deferred behind Obsidian graph (revisit at P7).
