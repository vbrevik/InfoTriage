# Plan 06-04 Summary: Obsidian Vault Writer Gap Closure

**Status:** code patched; focused tests pass; live compose verification pending  
**Date:** 2026-07-07

## Delivered

- Added `apps/brief/vault_writer.py` for high-value item files plus `obsidian-sab.md`.
- Vault writer uses `contracts.to_frontmatter()` so YAML is parseable by the existing codec.
- Email-sourced `imap://` rows are included by default unless `VAULT_INCLUDE_EMAIL=0`.
- `consumer.py` writes the vault projection after digest rendering.
- `docker-compose.yml` gives `brief` a writable `/vault/brief-outbox` mount and exposes vault/threshold env toggles.
- `.env.example` documents `CLUSTER_THRESHOLD` and `VAULT_INCLUDE_EMAIL`.

## Tests

- `python -m pytest tests/test_vault_writer.py -q` — 8 passed.
- Codec round-trip test covers punctuation and multiline front-matter fields.
- Email default-inclusion test covers the ROADMAP SC3 Obsidian half at unit level.

## Pending Verification

- Run the compose `brief` service with a real host `OBSIDIAN_VAULT_PATH` and confirm `.md` files appear in `${OBSIDIAN_VAULT_PATH}/brief-outbox`.
