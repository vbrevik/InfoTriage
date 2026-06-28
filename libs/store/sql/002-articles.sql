-- 002-articles.sql
-- Hybrid mapping of contracts.Item.
-- Real columns for queryable/indexed fields + JSONB payload for open dict.
-- D-02: hybrid (not all-JSONB). D-02a: FTS/GIN deferred to search/RAG phase.
CREATE TABLE IF NOT EXISTS infotriage.articles (
    id          TEXT        PRIMARY KEY,            -- sha256(source_type + NUL + url + NUL + title)
    source      TEXT        NOT NULL,               -- "NRK Nyheter"
    source_type TEXT        NOT NULL,               -- "rss", "imap", "yt"
    url         TEXT        NOT NULL DEFAULT '',    -- empty string when absent
    title       TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    lang        TEXT        NOT NULL,
    summary     TEXT,
    body_ref    TEXT,                               -- sha256 hash → data/blobs/ shard path
    payload     JSONB       NOT NULL DEFAULT '{}',  -- open dict (ccir, cnr, score, etc.)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_source_type ON infotriage.articles (source_type);
CREATE INDEX IF NOT EXISTS idx_articles_ts          ON infotriage.articles (ts DESC);
CREATE INDEX IF NOT EXISTS idx_articles_lang        ON infotriage.articles (lang);
