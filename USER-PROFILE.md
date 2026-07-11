# Developer Behavioral Profile — InfoTriage

Generated from session analysis on 2026-07-10.

## Communication Style

- **Direct and task-oriented.** Prefers concise, actionable requests. Examples:
  - "Run the Phase 6 UAT cold-start smoke test and update 06-UAT.md with results"
  - "Commit the recent planning file updates and code changes with a single milestone commit"
  - "run e2e tests for complete codebase, debug and fix all errors, old and new, related and unrelated"
- **Expects initiative.** Wants the assistant to act, orchestrate sub-agents, and make reasonable judgment calls.
- **No-surprises rule.** Files should not be modified unless explicitly or implicitly requested; transparency is expected.

## Technical Preferences

- **Testing-first mindset.** Routely asks for tests, validation, and verification before considering work done.
- **GSD framework native.** Uses `/gsd-progress`, `/gsd-profile-user`, and expects planning files (PROJECT.md, STATE.md, ROADMAP.md, HANDOFF.json) to stay in sync.
- **Milestone commits.** Likes bundling related work into single, well-described commits.
- **Docker/Python stack.** Works with Python 3.12, FastAPI, pgvector, RabbitMQ, Docker Compose, FreshRSS, RSS-Bridge.
- **Documentation-aware.** Values docs updates alongside code changes (e.g., RSS_BRIDGE_NOTES.md, 06-UAT.md).

## Decision-Making Style

- **Pragmatic.** Accepts that some services may be unhealthy due to missing runtime configuration and defers non-blocking issues.
- **Risk-aware.** Appreciates safety checks (e.g., confirming before `docker compose down -v`, excluding secrets/temp files from commits).
- **Follow-up oriented.** Uses suggested next steps to chain work.

## Collaboration Patterns

- Uses follow-up prompts to continue work sequentially.
- Provides API keys and credentials when needed (e.g., NewsAPI.org key).
- Expects concise final summaries and clear next-action suggestions.

## Preferred Artifacts

- Updated GSD planning files (STATE.md, ROADMAP.md, HANDOFF.json, PROJECT.md).
- Test files for new scripts.
- Markdown documentation for operational procedures.
- Milestone commits with descriptive messages.

## Anti-Patterns to Avoid

- Don't modify files without explicit or implicit request.
- Don't commit temporary debug files, session artifacts, or secrets.
- Don't skip verification/tests when they are relevant.
- Don't bury important decisions in long prose; be direct.
