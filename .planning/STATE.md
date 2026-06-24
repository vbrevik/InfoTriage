---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-06-24T18:57:01.318Z"
progress:
  total_phases: 13
  completed_phases: 0
  total_plans: 7
  completed_plans: 0
  percent: 0
---

# STATE — InfoTriage

> **Ephemeral.** Pick-up-next-session memory. Durable context lives in `docs/`, `PROJECT.md`,
> `REQUIREMENTS.md`, `ROADMAP.md`, `.planning/codebase/`. Trim aggressively.

## Session: 2026-06-24 — re-architecture design locked

### Just-completed

- **Combined re-architecture roadmap written** (`ROADMAP.md`) — replaces the old ingester-first
  phases. M1 Foundation (P0–P7), M2 Fusion (P8–P12), SP-COP parallel gated spike, M3 multi-user
  deferred. Old `phase-1` / `phase-1.5` dirs archived to `.planning/archive/`.

- **Design spec**: `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` (source of truth).
- **Codebase audit** (56 tests pass): ingest→score→brief + PMESII/TESSOC all WORK today on host
  Python → phases re-platform working code, not greenfield. Stale doc claims to fix in P1: imap/yt
  called "scaffolded" (complete), PMESII "planned" (done), `.env.example` "missing" (exists).

- **Bridges verified by execution**: imap/yt fully working (yt live-fetched). **Gmail blocked** —
  account 2SV ON, app passwords hard-blocked. Solved via **OAuth2/MCP**: live MCP pull produced a
  valid `data/feeds/gmail.xml` (20 entries), no app password. Runtime = self-hosted Gmail MCP server.

- **Assumptions reviewed + locked**: microservices (justified by solo→team growth), **RabbitMQ** bus,
  **Postgres** canonical (not SQLite), **MCP/OAuth2** ingestion, **split LLM** (embed + qwen36 + DGX),
  **email triage-only** (SAB+Obsidian, not FreshRSS), entity resolution in Postgres + Obsidian
  projection, COP demoted to gated spike, multi-user deferred to M3. See memory
  `infotriage-architecture-pivot`.

### Next session — first actions

1. **Plan P0** (narrowed concept spike) via `gsd-plan-phase` — gate the unproven bits (RabbitMQ
   topology, Norwegian pgvector dedup, entity resolution, COP/World Monitor, Wiki-LLM feasibility).

2. Write proposed ADRs: ADR-005 (COP/World Monitor), ADR-006 (microservice arch), ADR-007 (RabbitMQ),
   ADR-008 (self-hosted MCP/OAuth2 ingestion).

3. `config.json` still says `single_user: true` — correct for M1/M2; M3 flips it.

### Carried-over open questions (some now resolved)

- Q1 World Monitor CCIR/SAB coverage → **SP-COP spike** (still open).
- Q4 FreshRSS migration → moot (FreshRSS demoted to optional RSS/YouTube projection; Postgres is store).
- Q5 embedding model (bge-m3 vs mE5-large) → decided in **P0** spike.
