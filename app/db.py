"""PostgreSQL + pgvector data layer.

We use the mandated PostgreSQL with the pgvector extension as the single
datastore: it holds the chunk text, its embedding, and rich metadata, and lets
us combine vector similarity with full-text keyword search in plain SQL. No
separate vector database is needed.
"""

from __future__ import annotations

from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from .config import get_settings

_settings = get_settings()


@contextmanager
def connect():
    conn = psycopg.connect(_settings.database_url)
    try:
        _ensure_vector(conn)
        yield conn
    finally:
        conn.close()


def _ensure_vector(conn) -> None:
    """Register the pgvector type, creating the extension first if needed.

    The pgvector image ships the extension *available* but not *created* in a
    fresh database, so the very first connection must create it before
    register_vector() can find the `vector` type.
    """
    try:
        register_vector(conn)
    except psycopg.ProgrammingError:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
        register_vector(conn)


def init_schema() -> None:
    dim = _settings.embedding_dim
    with connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS guideline_chunks (
                id            BIGSERIAL PRIMARY KEY,
                guideline_set TEXT NOT NULL,
                source_document TEXT NOT NULL,
                location      TEXT NOT NULL,
                chunk_index   INT  NOT NULL,
                content       TEXT NOT NULL,
                embedding     vector({dim}),
                tsv           tsvector
                              GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON guideline_chunks USING GIN (tsv);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_set ON guideline_chunks (guideline_set);"
        )
        # HNSW index for cosine distance. HNSW gives correct recall regardless
        # of corpus size (IVFFlat can return zero rows on small corpora because
        # it probes a single, often-empty list). Good fit for this dataset.
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_vec ON guideline_chunks "
            "USING hnsw (embedding vector_cosine_ops);"
        )
        conn.commit()


def clear_chunks() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE guideline_chunks RESTART IDENTITY;")
        conn.commit()


def insert_chunks(rows: list[dict]) -> None:
    """rows: dicts with keys guideline_set, source_document, location,
    chunk_index, content, embedding (list[float])."""
    with connect() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO guideline_chunks
                (guideline_set, source_document, location, chunk_index, content, embedding)
            VALUES (%(guideline_set)s, %(source_document)s, %(location)s,
                    %(chunk_index)s, %(content)s, %(embedding)s);
            """,
            rows,
        )
        conn.commit()


def count_chunks() -> int:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM guideline_chunks;")
        return cur.fetchone()[0]


def vector_search(embedding: list[float], k: int, exclude_sets: list[str]) -> list[dict]:
    where = ""
    params: list = [embedding]
    if exclude_sets:
        where = "WHERE guideline_set <> ALL(%s)"
        params.append(exclude_sets)
    params.append(k)
    sql = f"""
        SELECT id, guideline_set, source_document, location, content,
               1 - (embedding <=> %s::vector) AS score
        FROM guideline_chunks
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """
    # embedding appears twice in the SQL (score + ORDER BY); duplicate it.
    final_params = [embedding] + ([exclude_sets] if exclude_sets else []) + [embedding, k]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, final_params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def keyword_search(query: str, k: int, exclude_sets: list[str]) -> list[dict]:
    where = "WHERE tsv @@ plainto_tsquery('english', %s)"
    params: list = [query]
    if exclude_sets:
        where += " AND guideline_set <> ALL(%s)"
        params.append(exclude_sets)
    params.append(query)
    params.append(k)
    sql = f"""
        SELECT id, guideline_set, source_document, location, content,
               ts_rank(tsv, plainto_tsquery('english', %s)) AS score
        FROM guideline_chunks
        {where}
        ORDER BY score DESC
        LIMIT %s;
    """
    # reorder params to match placeholder order: ts_rank query, where query,
    # (exclude), limit
    final_params = [query, query] + ([exclude_sets] if exclude_sets else []) + [k]
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, final_params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]