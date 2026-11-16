-- pgvector + Postgres full-text search. {dim} is replaced at startup.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT '',
    symbol TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    search_text TEXT NOT NULL,
    embedding vector({dim}) NOT NULL
);

CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING gin (to_tsvector('simple', search_text));
