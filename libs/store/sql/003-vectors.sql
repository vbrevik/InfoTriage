-- 003-vectors.sql
-- Vector tables for entity resolution and article embeddings.
-- Dimension 1024 is the locked embedder contract (D-05a, mE5-large).
-- HNSW indexes with cosine ops (D-05b, ADR-006).
-- NOTE: CREATE INDEX IF NOT EXISTS only — no parallel build option (cannot run inside a transaction).

CREATE TABLE IF NOT EXISTS infotriage.entities (
    id          SERIAL      PRIMARY KEY,
    name        TEXT        NOT NULL,               -- canonical entity name
    name_norm   TEXT        NOT NULL,               -- lowercased/normalized for matching
    lang        TEXT        NOT NULL,               -- language of canonical name
    type        TEXT,                               -- e.g. "ORG", "PER", "LOC"
    embedding   vector(1024)                        -- mE5-large 1024-dim embedding
);

CREATE TABLE IF NOT EXISTS infotriage.entity_links (
    id          SERIAL      PRIMARY KEY,
    entity_id   INT         NOT NULL REFERENCES infotriage.entities(id),
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    mention     TEXT        NOT NULL,               -- surface form in source text
    lang        TEXT        NOT NULL                -- language of the mention
);

CREATE TABLE IF NOT EXISTS infotriage.embeddings (
    id          SERIAL      PRIMARY KEY,
    item_id     TEXT        NOT NULL REFERENCES infotriage.articles(id),
    embedding   vector(1024) NOT NULL,              -- article-level embedding
    model       TEXT        NOT NULL,               -- embedder model id
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique indexes for idempotent entity upserts (Phase 8).
-- Using CREATE UNIQUE INDEX IF NOT EXISTS keeps init_schema() idempotent;
-- PostgreSQL does not support ALTER TABLE ADD CONSTRAINT IF NOT EXISTS.
CREATE UNIQUE INDEX IF NOT EXISTS uk_entities_name_lang
    ON infotriage.entities (name_norm, lang);

CREATE UNIQUE INDEX IF NOT EXISTS uk_entity_links_entity_item_mention
    ON infotriage.entity_links (entity_id, item_id, mention);

-- HNSW cosine indexes (m=16, ef_construction=64 per D-05b)
CREATE INDEX IF NOT EXISTS idx_entities_embedding_hnsw
    ON infotriage.entities USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_embeddings_embedding_hnsw
    ON infotriage.embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
