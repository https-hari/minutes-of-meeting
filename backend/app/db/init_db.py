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


# v3: data is owned by a user. Older databases get the column, and existing rows
# are assigned to "local" (the user when AUTH_DISABLED=1), so nothing is lost.
MIGRATIONS = [
    "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS user_id TEXT",
    "UPDATE meetings SET user_id = 'local' WHERE user_id IS NULL",
    "ALTER TABLE meetings ALTER COLUMN user_id SET NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_meetings_user_id ON meetings (user_id)",
    "ALTER TABLE participants ADD COLUMN IF NOT EXISTS user_id TEXT",
    "UPDATE participants SET user_id = 'local' WHERE user_id IS NULL",
    "ALTER TABLE participants ALTER COLUMN user_id SET NOT NULL",
    "ALTER TABLE participants DROP CONSTRAINT IF EXISTS participants_email_key",
    "CREATE INDEX IF NOT EXISTS ix_participants_user_id ON participants (user_id)",
    "ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS user_id TEXT",
]


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for sql in MIGRATIONS + INDEXES:
            conn.execute(text(sql))


if __name__ == "__main__":
    init_db()
    print("Database ready.")
