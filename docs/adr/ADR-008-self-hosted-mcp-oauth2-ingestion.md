# ADR-008 — Self-hosted MCP / OAuth2 ingestion

**Status.** Accepted (2026-06-27). Decision **carried from the already-proven Gmail OAuth2/MCP pull**
(STATE.md / PROJECT.md / `docs/superpowers/specs/2026-06-24-app-split-architecture-design.md` →
"Ingestion auth & self-hosted MCP layer"); not re-spiked in Phase 0 (it is outside the five unknowns
R1–R5 but is a required ADR deliverable). Continues the ADR lineage in `docs/ARCHITECTURE.md`
(ADR-001..004).

---

**Context.** InfoTriage ingests from many sources. Some rich sources require **OAuth2** rather than a
static credential. The target account (Gmail) has **2-Step Verification ON and app passwords
hard-blocked** (Advanced Protection / policy), so the legacy IMAP + app-password path
(`bridge/gmail_to_atom.py`) is a dead end and is **retired** for this account. A headless-safe,
durable ingestion path is needed that does not depend on an interactive session.

---

**Decision.** Ingest OAuth2 sources (Gmail, and later others) through **self-hosted, OAuth2-backed
MCP servers** running as containers in the stack. The ingest adapter is a thin **MCP client**; the
**MCP server owns the OAuth token + the source API**. "Use an MCP server" becomes the ingestion
*pattern*, not a one-off.

- **Proven path (verified 2026-06-24):** Gmail read via OAuth2 MCP works live — a one-time pull
  through the claude.ai Gmail connector produced a valid `data/feeds/gmail.xml` (**20 entries**) with
  **no app password**.
- **Runtime path (Phase 4):** `ingest-gmail` adapter → **self-hosted Gmail MCP server** (its own
  OAuth2 refresh token, headless-safe, on :22025). The claude.ai connector is **interactive-only**
  (token bound to the Claude session, dies in cron/headless) — it is a dev/verify aid, **NOT** the
  runtime.
- IMAP (non-Gmail) and YouTube bridges stay as-is — verified working, need no OAuth.

---

**Consequences.**

- **Auth boundary is the MCP server.** Refresh tokens / OAuth credentials live in the MCP server
  container, not in the adapter or the app — adapters hold no long-lived secrets. (Aligns with the
  codebase security guidance: OAuth2 + refresh tokens over stored passwords.)
- **Pattern, not a special case.** New OAuth2 sources are added by standing up another self-hosted
  MCP server + a thin client adapter — uniform across sources.
- **Phase 4 scope:** containerize the bridges + the self-hosted Gmail MCP server; retire the legacy
  IMAP `gmail_to_atom.py` for the Gmail account; emit ingested items onto the bus as `item.ingested`
  (ADR-007).
- The interactive claude.ai connector remains a useful verification/dev tool but is explicitly **not**
  part of the production runtime.
