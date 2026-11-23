"""Create the extension, tables and search indexes. Safe to run on every start."""
from sqlalchemy import text

from app.db.connection import Base, engine
from app.db import models  # noqa: F401  (registers the tables on Base)

INDEXES = [
    # keyword search: full-text index over chunk text
    "CREATE INDEX IF NOT EXISTS chunks_fts_idx ON chunks USING GIN (to_tsvector('english', chunk_text))",
    # vector search: HNSW keeps nearest-neighbour search fast as chunks grow
    "CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)",
    "CREATE INDEX IF NOT EXISTS memories_embedding_hnsw ON memories USING hnsw (embedding vector_cosine_ops)",
]


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for sql in INDEXES:
            conn.execute(text(sql))


if __name__ == "__main__":
    init_db()
    print("Database ready.")
