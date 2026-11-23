"""Shared setup for the evals: a separate database so your real meetings are untouched.

By default the eval uses a database named after yours with "_eval" appended
(e.g. meetings -> meetings_eval), created on first run on the same server.
Override with EVAL_DATABASE_URL.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / ".env")


EVAL_USER = "eval"   # all eval meetings belong to this user


def use_eval_database() -> str:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = os.getenv("EVAL_DATABASE_URL")
    if not url:
        base = make_url(os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg2://", 1))
        target = base.set(database=f"{base.database}_eval")
        admin = create_engine(base, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"),
                             {"d": target.database}).scalar():
                c.execute(text(f'CREATE DATABASE "{target.database}"'))
        admin.dispose()
        url = target.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url        # must be set before app.db.connection is imported
    return url


def load(name: str):
    return json.loads((ROOT / name).read_text())


def reset_and_load_chunks(embedder) -> int:
    """Wipe the eval database and insert the eval meetings as chunks (no LLM needed)."""
    from sqlalchemy import text

    from app.db.connection import SessionLocal, engine
    from app.db.init_db import init_db
    from app.db.models import Chunk, Meeting
    from app.pipeline import MeetingPipeline

    init_db()
    with engine.begin() as c:
        c.execute(text("TRUNCATE meetings, chunks, action_items, decisions, meeting_participants, "
                       "participants, query_logs, conversations, messages, memories RESTART IDENTITY CASCADE"))
    db = SessionLocal()
    n = 0
    for m in load("meetings.json"):
        transcript = "\n".join(m["transcript"])
        meeting = Meeting(user_id=EVAL_USER, title=m["title"], transcript=transcript)
        db.add(meeting)
        db.flush()
        chunks = embedder.embed_chunks(MeetingPipeline._text_to_chunks(transcript))
        for ch in chunks:
            db.add(Chunk(meeting_id=meeting.id, speaker=ch["speaker"], chunk_text=ch["text"],
                         embedding=ch["embedding"]))
            n += 1
    db.commit()
    db.close()
    return n


def update_readme(marker: str, content: str) -> None:
    """Replace the block between <!-- MARKER --> and <!-- /MARKER --> in README.md."""
    readme = ROOT.parent.parent / "README.md"   # repo root
    s = readme.read_text()
    start, end = f"<!-- {marker} -->", f"<!-- /{marker} -->"
    if start in s and end in s:
        a, b = s.index(start) + len(start), s.index(end)
        readme.write_text(s[:a] + "\n" + content.strip() + "\n" + s[b:])
