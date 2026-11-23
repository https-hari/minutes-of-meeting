"""Tests run against a real Postgres + pgvector (set TEST_DATABASE_URL), with
fake embedder / re-ranker / LLM so no model downloads or API calls happen.

    createdb mom_test
    TEST_DATABASE_URL=postgresql://localhost/mom_test pytest -q
"""
import os

import pytest

TEST_DB = os.getenv("TEST_DATABASE_URL")
if not TEST_DB:
    pytest.skip("set TEST_DATABASE_URL to a throwaway Postgres database with pgvector",
                allow_module_level=True)
os.environ["DATABASE_URL"] = TEST_DB          # must happen before app.db.connection is imported
os.environ["SKIP_DB_INIT"] = "1"
os.environ["AUTH_DISABLED"] = "0"

from sqlalchemy import text  # noqa: E402

from app.db.connection import SessionLocal, engine  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import ActionItem, Chunk, Decision, Meeting, Participant  # noqa: E402

from fakes import FakeEmbedder, FakeReranker, ScriptedLLM, tool_call  # noqa: E402,F401


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db()


@pytest.fixture
def db():
    with engine.begin() as c:
        c.execute(text("TRUNCATE meetings, participants, meeting_participants, action_items, decisions, "
                       "chunks, query_logs, conversations, messages, memories RESTART IDENTITY CASCADE"))
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def seeded(db, embedder):
    """Two meetings with overlapping topics, people, tasks and decisions."""
    m1 = Meeting(user_id="u1", title="Q3 Budget Review", summary="Budget and launch planning")
    m2 = Meeting(user_id="u1", title="Infra Sync", summary="Database and deploy issues")
    db.add_all([m1, m2]); db.flush()
    alice, bob = Participant(user_id="u1", name="Alice"), Participant(user_id="u1", name="Bob")
    db.add_all([alice, bob]); db.flush()
    chunks = [
        (m1, "Bob", "We need to increase the marketing budget by fifteen percent for Q3."),
        (m1, "Alice", "Agreed, the marketing spend goes up fifteen percent."),
        (m1, "Bob", "We decided to move the product launch to August because QA is behind."),
        (m2, "Carol", "The login outage was caused by ticket JIRA-482, an expired TLS certificate."),
        (m2, "Bob", "Postgres replication lag hit thirty seconds during the deploy."),
        (m2, "Alice", "Let's upgrade the connection pooler to version 2.3 next sprint."),
    ]
    for m, sp, t in chunks:
        db.add(Chunk(meeting_id=m.id, speaker=sp, chunk_text=t, embedding=embedder.embed_text(t)))
    db.add_all([
        ActionItem(meeting_id=m1.id, owner_id=alice.id, description="Prepare revised budget proposal", status="open"),
        ActionItem(meeting_id=m1.id, owner_id=bob.id, description="Update launch timeline", status="in_progress"),
        ActionItem(meeting_id=m2.id, owner_id=alice.id, description="Renew TLS certificate", status="done"),
        Decision(meeting_id=m1.id, description="Marketing budget +15% for Q3", context="growth push"),
        Decision(meeting_id=m1.id, description="Product launch moved to August", context="QA behind"),
    ])
    db.commit()
    return {"m1": m1.id, "m2": m2.id}
