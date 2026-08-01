-- 010-backfill-discipline.sql
-- Phase 11 closed-debt backfill: populate `discipline` for the 499
-- NULL-discipline rows that were ingested before migration 007+
-- adapters tagged `discipline` at model-build time.
--
-- The mapping below MUST stay in lock-step with
-- `libs/contracts/src/contracts/_phase11_gates.py::SOURCE_TYPE_TO_INT_DISCIPLINE`.
-- The per-ingest contract test
-- `tests/test_phase11_gates.py::test_all_source_types_mapped_to_valid_int_discipline`
-- enforces conformance at the Python side. A follow-up commit will add a
-- `tests/test_phase11_parity.py` test that parses this SQL file's CASE
-- branches and asserts byte-level parity with the Python dict.
--
-- Taxonomy = INT (Open Source / HUMan / SIGint / MASint / GEOint / SOCmint
-- intelligence taxonomy per NATO JP 2-00 framing). NOT to be confused
-- with PMESII analytical enrichment, which lives in ccir.md and
-- drives SCORING, not the `discipline` metadata column.
--
-- Idempotent: `WHERE discipline IS NULL` guards against re-runs.
-- Implicitly atomic: a single UPDATE on `infotriage.articles` is one
-- transaction at the SQL level — no explicit BEGIN/COMMIT needed
-- (matches existing migrations 001-009 style; BEGIN/COMMIT was
-- deliberately removed after operator + code-reviewer verdict
-- flagged the project convention).
--
-- `ELSE NULL` (no fallback): unmapped source_types stay NULL so the
-- per-ingest contract test surfaces drift loudly. A future adapter
-- that introduces a new source_type without updating the dict will
-- fail `test_all_source_types_mapped_to_valid_int_discipline` rather
-- than silently being labeled OSINT.

UPDATE infotriage.articles
SET discipline = CASE source_type
    -- OSINT family (open-source / public-data)
    WHEN 'rss'              THEN 'OSINT'
    WHEN 'obsidian'         THEN 'OSINT'
    WHEN 'yt'               THEN 'OSINT'
    WHEN 'youtube'          THEN 'OSINT'
    WHEN 'acled'            THEN 'OSINT'
    -- HUMINT family (human-mediated; e.g., email sources)
    WHEN 'imap'             THEN 'HUMINT'
    WHEN 'gmail'            THEN 'HUMINT'
    WHEN 'pop3'             THEN 'HUMINT'
    -- SOCMINT (social-media intelligence; Phase 11 Telegram adapter)
    WHEN 'telegram'         THEN 'SOCMINT'
    -- MASINT family (measurement-and-signature; Phase 11 BarentsWatch AIS)
    WHEN 'barentswatch'     THEN 'MASINT/AIS'
    WHEN 'ais'              THEN 'MASINT/AIS'
    ELSE NULL
END
WHERE discipline IS NULL;
