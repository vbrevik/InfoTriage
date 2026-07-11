---
phase: 4
slug: ingest-adapters-gmail-mcp
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-29
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pyproject.toml `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` — `testpaths = ["tests"]`, `pythonpath = [...]` |
| **Quick run command** | `pytest tests/ -m "not db_live and not rabbitmq" -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~30 seconds (quick) / ~120 seconds (full, requires Postgres + RabbitMQ) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -m "not db_live and not rabbitmq" -x`
- **After every plan wave:** Run `pytest tests/ -x` (requires Postgres and RabbitMQ running)
- **Before `/gsd-verify-work`:** Full suite must be green + docker compose up smoke test
- **Max feedback latency:** 30 seconds (quick), 120 seconds (full)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-R1 | imap | 1 | ADR-004 (read-only) | IMAP write ops | No STORE/EXPUNGE in adapter | integration | `pytest tests/test_ingest_imap.py -x -m db_live` | ❌ Wave 0 | ⬜ pending |
| 04-R2 | youtube | 1 | ADR-003 | — | N/A | integration | `pytest tests/test_ingest_youtube.py -x -m db_live` | ❌ Wave 0 | ⬜ pending |
| 04-R3 | gmail | 2 | ADR-008 (MCP/OAuth2) | OAuth2 token exposure | Token in env_file only, not image | integration | `pytest tests/test_ingest_gmail.py -x -m db_live` | ❌ Wave 0 | ⬜ pending |
| 04-R4 | obsidian | 1 | ADR-003 | YAML injection | `yaml.safe_load` only | unit | `pytest tests/test_ingest_obsidian.py -x` | ❌ Wave 0 | ⬜ pending |
| 04-R5 | scheduler | 1 | ADR-003 | — | N/A | unit | `pytest tests/test_scheduler.py -x` | ❌ Wave 0 | ⬜ pending |
| 04-R6 | idempotency | 1 | ADR-003 | — | N/A | unit | `pytest tests/test_ingest_idempotency.py -x` | ❌ Wave 0 | ⬜ pending |
| 04-R7 | gmail | 2 | ADR-008 | — | Legacy gmail_to_atom.py deleted | static | `git ls-files apps/ingest/gmail_to_atom.py \| grep -c .` → 0 | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ingest_imap.py` — covers R1 (unit: mock IMAP via imaplib mock; integration: real mailbox with `db_live` marker)
- [ ] `tests/test_ingest_youtube.py` — covers R2 (unit: mock yt-dlp subprocess; check Atom file created + Item constructed)
- [ ] `tests/test_ingest_gmail.py` — covers R3 (unit: mock MCP server via httpx_mock; integration: real MCP server with `db_live`)
- [ ] `tests/test_ingest_obsidian.py` — covers R4 (unit: write temp .md file, run adapter, check Item fields)
- [ ] `tests/test_scheduler.py` — covers R5 (unit: mock HTTP responses; first=200, second=409; verify log)
- [ ] `tests/test_ingest_idempotency.py` — covers R6 (unit: InMemoryStore + InMemoryBus; run twice same Item; verify 1 row + 1 event)
