#!/usr/bin/env python3
"""_postgres.py — PostgresStore: psycopg3 + pgvector Store implementation.

Production Store implementation backed by PostgreSQL 16 + pgvector.
Satisfies the Store Protocol defined in _protocol.py.

Usage:
    import os
    from pathlib import Path
    from store import PostgresStore

    dsn = os.environ["INFOTRIAGE_PG_DSN"]
    with PostgresStore(dsn=dsn, blob_root=Path("data/blobs")) as store:
        store.init_schema()
        store.put_item(item)

Design decisions (from CONTEXT.md / RESEARCH.md):
- D-03:  single DSN from caller; caller reads INFOTRIAGE_PG_DSN; class never reads env
- D-03a: one connection opened in __enter__, closed in __exit__; no pool (deferred P3+)
- D-01a: blob operations delegate to _blob helpers (same code path as InMemoryStore)
- DD-5:  audit row written in same transaction as put_item
- V5/T-02-01: ALL SQL uses %s bind params; no f-string or string concatenation ever
- Pitfall 1: register_vector from pgvector.psycopg (NOT pgvector.psycopg2)
- Pitfall 2: JSONB columns wrapped with Jsonb() (NOT passed as raw dict)
- Pitfall 4: init_schema uses autocommit connection (so HNSW INDEX works without CONCURRENTLY)
- Pitfall 5: all table names fully-qualified infotriage.* (no search_path reliance)
"""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector  # Pitfall 1: NOT pgvector.psycopg2

from contracts import Item

from ._blob import get_blob as _get_blob
from ._blob import put_blob as _put_blob


class PostgresStore:
    """Postgres-backed Store implementation using psycopg3 + pgvector.

    Opens a single psycopg3 connection in __enter__ and closes it in __exit__.
    No connection pool (deferred to P3+ per D-03a). NOT thread-safe.

    Usage:
        dsn = os.environ["INFOTRIAGE_PG_DSN"]
        with PostgresStore(dsn=dsn, blob_root=Path("data/blobs")) as store:
            store.init_schema()
            store.put_item(item)
    """

    def __init__(self, dsn: str, blob_root: Path) -> None:
        """Initialise with DSN and blob root directory.

        Args:
            dsn: libpq connection string. The caller reads INFOTRIAGE_PG_DSN and
                 passes it here — PostgresStore never reads env vars itself (D-03).
            blob_root: filesystem root for content-addressed blob storage (D-01a).
        """
        self._dsn = dsn
        self._blob_root = blob_root
        self._conn: psycopg.Connection | None = None  # opened in __enter__

    # -------------------------------------------------------------------------
    # Context manager — one connection per "with" block (D-03)
    # -------------------------------------------------------------------------

    def __enter__(self) -> "PostgresStore":
        """Open one psycopg3 connection and register the pgvector type adapter."""
        self._conn = psycopg.connect(self._dsn, row_factory=dict_row)
        register_vector(self._conn)  # Pitfall 1: must be called before any vector query
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit on clean exit, rollback on exception, always close connection."""
        if self._conn is not None:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
            self._conn.close()
            self._conn = None

    # -------------------------------------------------------------------------
    # Raw read cursor (Phase 6: brief consumer/server ad-hoc SELECTs)
    # -------------------------------------------------------------------------

    def cursor(self, row_factory=None):
        """Return a cursor on the open connection for ad-hoc SELECTs.

        row_factory=None inherits the connection's dict_row. psycopg3
        connections serialize access internally, so cursors from multiple
        threads (asyncio.to_thread callers) are safe.
        """
        assert self._conn is not None, (
            "PostgresStore used outside 'with' block — connection not open"
        )
        if row_factory is None:
            return self._conn.cursor()
        return self._conn.cursor(row_factory=row_factory)

    # -------------------------------------------------------------------------
    # Schema bootstrap (R1, DD-2)
    # -------------------------------------------------------------------------

    def init_schema(self) -> None:
        """Apply all DDL files under libs/store/sql/ in sorted order.

        Uses a SEPARATE autocommit connection so CREATE EXTENSION vector and
        CREATE INDEX USING hnsw run outside a wrapping transaction (Pitfall 4).
        Idempotent: all DDL uses IF NOT EXISTS throughout (R1).
        """
        sql_dir = Path(__file__).parent.parent.parent / "sql"
        # Autocommit DDL connection — separate from the main transaction connection.
        # register_vector is called AFTER the SQL files so that the vector extension
        # exists when we register its type adapter (fails on fresh DB if called before
        # CREATE EXTENSION runs — Rule 1 fix from PATTERNS.md ordering).
        with psycopg.connect(self._dsn, autocommit=True) as ddl_conn:
            for sql_file in sorted(sql_dir.glob("*.sql")):
                ddl_conn.execute(sql_file.read_text())
            register_vector(ddl_conn)  # after extension is created/confirmed

    # -------------------------------------------------------------------------
    # Item CRUD (R5)
    # -------------------------------------------------------------------------

    def put_item(self, item: Item) -> None:
        """Upsert item by item.id (ON CONFLICT DO UPDATE). Last-write-wins.

        Writes an audit row in the SAME transaction as the article row (DD-5).
        Both are committed together — a failed audit write rolls back the article.

        Raises psycopg.Error on any DB failure — never silently swallowed
        (no-silent-loss prohibition).

        Security (V5, T-02-01): all values via %s bind params; no f-string SQL.
        """
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager: "
            "'with PostgresStore(...) as store:'"
        )
        # Upsert the article row. Pitfall 2: Jsonb() is REQUIRED for JSONB columns.
        self._conn.execute(
            """
            INSERT INTO infotriage.articles
                (id, source, source_type, url, title, ts, lang, summary, body_ref, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                source      = EXCLUDED.source,
                source_type = EXCLUDED.source_type,
                url         = EXCLUDED.url,
                title       = EXCLUDED.title,
                ts          = EXCLUDED.ts,
                lang        = EXCLUDED.lang,
                summary     = EXCLUDED.summary,
                body_ref    = EXCLUDED.body_ref,
                payload     = EXCLUDED.payload
            """,
            (
                item.id,
                item.source,
                item.source_type,
                item.url,
                item.title,
                item.ts,
                item.lang,
                item.summary,
                item.body_ref,
                Jsonb(item.payload),  # REQUIRED — Pitfall 2: raw dict fails for JSONB
            ),
        )
        # Audit row in the SAME transaction (DD-5) — commit both together.
        self._conn.execute(
            """
            INSERT INTO infotriage.audit (op, table_name, item_id)
            VALUES (%s, %s, %s)
            """,
            ("put_item", "articles", item.id),
        )
        self._conn.commit()

    def get_item(self, item_id: str) -> Item | None:
        """Return the Item for item_id, or None on miss. Never raises on absence."""
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager"
        )
        row = self._conn.execute(
            """
            SELECT source, source_type, url, title, ts, lang, summary, body_ref, payload
            FROM infotriage.articles
            WHERE id = %s
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return Item(
            source=row["source"],
            source_type=row["source_type"],
            url=row["url"],
            title=row["title"],
            ts=row["ts"],
            lang=row["lang"],
            summary=row["summary"],
            body_ref=row["body_ref"],
            payload=row["payload"] if row["payload"] is not None else {},
        )

    def list_items(
        self,
        source_type_in: list[str] | None = None,
        limit: int = 200,
    ) -> list[Item]:
        """Return items ordered by (ts DESC, id DESC). Empty list on no match.

        Args:
            source_type_in: filter to items whose source_type is in this list.
                            Uses psycopg3 ANY(%s) for safe list params (Open Q3).
            limit: max items returned (T-02-05 DoS mitigation).
        """
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager"
        )
        if source_type_in is not None:
            rows = self._conn.execute(
                """
                SELECT source, source_type, url, title, ts, lang, summary, body_ref, payload
                FROM infotriage.articles
                WHERE source_type = ANY(%s)
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (source_type_in, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT source, source_type, url, title, ts, lang, summary, body_ref, payload
                FROM infotriage.articles
                ORDER BY ts DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            Item(
                source=r["source"],
                source_type=r["source_type"],
                url=r["url"],
                title=r["title"],
                ts=r["ts"],
                lang=r["lang"],
                summary=r["summary"],
                body_ref=r["body_ref"],
                payload=r["payload"] if r["payload"] is not None else {},
            )
            for r in rows
        ]

    # -------------------------------------------------------------------------
    # Blob operations — delegate to _blob helpers (D-01a)
    # -------------------------------------------------------------------------

    def put_blob(self, data: bytes) -> str:
        """Store bytes at a content-addressed sharded path. Returns sha256 hex.

        Delegates filesystem I/O to _blob.put_blob (D-01a: same code path as
        InMemoryStore). Also writes an audit row if inside a context manager
        (DD-5). The blob is written first; audit follows — if audit fails the
        blob stays (idempotent dedup on next call), but the exception propagates.

        Raises on any write failure — never silently returns success on error.
        """
        h = _put_blob(self._blob_root, data)
        # Audit row (DD-5) — conditional on connection being open
        if self._conn is not None:
            self._conn.execute(
                """
                INSERT INTO infotriage.audit (op, table_name, item_id)
                VALUES (%s, %s, %s)
                """,
                ("put_blob", "blobs", h),
            )
            self._conn.commit()
        return h

    def get_blob(self, blob_hash: str) -> bytes:
        """Return bytes for the blob identified by blob_hash.

        Raises:
            ValueError: if blob_hash is not a 64-char lowercase hex string (T-02-02).
            FileNotFoundError: if no blob with that hash has been stored.
        """
        return _get_blob(self._blob_root, blob_hash)

    # -------------------------------------------------------------------------
    # Enrichment persistence — D-05, R1
    # -------------------------------------------------------------------------

    def put_enrichment(self, item_id: str, fields: dict) -> None:
        """Upsert enrichment row for item_id. ON CONFLICT DO UPDATE all 7 columns.

        Idempotent: ON CONFLICT (item_id) backed by enrichment_item_id_unique index
        (006-enrichment.sql). Second write updates the same row in place.
        Security (V5/T-05-01): all values via %s bind params — never f-string SQL.
        """
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager: "
            "'with PostgresStore(...) as store:'"
        )
        self._conn.execute(
            """
            INSERT INTO infotriage.enrichment
                (item_id, ccir, cnr, score, bucket, why, pmesii, tessoc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (item_id) DO UPDATE SET
                ccir   = EXCLUDED.ccir,
                cnr    = EXCLUDED.cnr,
                score  = EXCLUDED.score,
                bucket = EXCLUDED.bucket,
                why    = EXCLUDED.why,
                pmesii = EXCLUDED.pmesii,
                tessoc = EXCLUDED.tessoc
            """,
            (
                item_id,
                fields.get("ccir"),
                fields.get("cnr"),
                fields.get("score"),
                fields.get("bucket"),
                fields.get("why"),
                fields.get("pmesii"),
                fields.get("tessoc"),
            ),
        )
        self._conn.commit()

    def get_enrichment(self, item_id: str) -> "dict | None":
        """Return enrichment dict for item_id, or None if absent."""
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager"
        )
        row = self._conn.execute(
            """
            SELECT ccir, cnr, score, bucket, why, pmesii, tessoc
            FROM infotriage.enrichment
            WHERE item_id = %s
            """,
            (item_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "ccir": row["ccir"],
            "cnr": row["cnr"],
            "score": row["score"],
            "bucket": row["bucket"],
            "why": row["why"],
            "pmesii": row["pmesii"],
            "tessoc": row["tessoc"],
        }

    # -------------------------------------------------------------------------
    # Embedding dedup — D-05, D-06, R4
    # -------------------------------------------------------------------------

    def put_embedding(self, item_id: str, vector: list[float]) -> None:
        """Upsert embedding vector for item_id into infotriage.embeddings.

        Idempotent: ON CONFLICT (item_id) backed by embeddings_item_id_unique index
        (006-enrichment.sql). Second write updates the stored vector in place.
        Security (V5/T-05-01): all values via %s bind params; vector never interpolated.
        """
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager"
        )
        model = "intfloat/multilingual-e5-large"
        self._conn.execute(
            """
            INSERT INTO infotriage.embeddings (item_id, embedding, model)
            VALUES (%s, %s, %s)
            ON CONFLICT (item_id) DO UPDATE SET
                embedding = EXCLUDED.embedding,
                model     = EXCLUDED.model
            """,
            (item_id, vector, model),
        )
        self._conn.commit()

    def find_near_duplicate(
        self,
        vector: list[float],
        window_days: int = 7,
        threshold: float = 0.84,
    ) -> "str | None":
        """Return item_id of nearest embedding within cosine threshold and time window.

        Uses the pgvector <=> cosine distance operator (NOT <-> which is L2) against
        the HNSW cosine index on infotriage.embeddings (003-vectors.sql, ADR-006).
        register_vector() is already called in __enter__ so the type adapter is ready.
        Security (V5/T-05-01): vector and interval bound as parameters — never f-string SQL.

        cosine_distance = 1 - cosine_similarity, so threshold 0.84 → distance < 0.16.
        """
        assert self._conn is not None, (
            "PostgresStore must be used as a context manager"
        )
        # INTERVAL %s is invalid Postgres syntax; CAST(%s AS interval) is the correct
        # parameterized form. The string "7 days" is a valid interval literal.
        row = self._conn.execute(
            """
            SELECT item_id, (embedding <=> %s::vector) AS dist
            FROM infotriage.embeddings
            WHERE created_at >= NOW() - CAST(%s AS interval)
            ORDER BY embedding <=> %s::vector
            LIMIT 1
            """,
            (vector, f"{window_days} days", vector),
        ).fetchone()
        if row is not None and row["dist"] < (1.0 - threshold):
            return row["item_id"]
        return None
