-- 008-translation-cache.sql
-- Idempotent translation cache schema (Phase 11 Wave 4).
-- Caches local-LLM translations keyed by (text_hash, target_lang) to avoid
-- repeated LLM calls for identical source text.

CREATE TABLE IF NOT EXISTS infotriage.translation_cache (
    text_hash    TEXT        NOT NULL,
    target_lang  TEXT        NOT NULL,
    translation  TEXT        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (text_hash, target_lang)
);

-- The PRIMARY KEY on (text_hash, target_lang) already provides the lookup
-- index; no additional index is needed.
