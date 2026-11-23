import json
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import config
from app.agent import MeetingAgent
from app.api import routes
from app.db.models import ActionItem, Chunk, Meeting
from app.pipeline import MeetingPipeline
from fakes import FakeEmbedder, FakeReranker, ScriptedLLM, tool_call

SECRET = "test-secret-at-least-32-bytes-long!!"

EXTRACTION = {
    "participants": [{"name": "Alice"}, {"name": "Bob"}],
    "action_items": [{"description": "Send the revised budget", "owner": "Alice", "deadline": "2026-07-18"}],
    "decisions": [{"description": "Launch moves to August", "context": "QA behind"}],
    "summary": "Budget and launch.",
}
TRANSCRIPT = "Alice: Let's move the launch to August.\nBob: Agreed, QA is behind.\nAlice: I'll send the revised budget."


def token(sub, exp_in=3600, secret=SECRET, aud="authenticated"):
    return jwt.encode({"sub": sub, "email": f"{sub}@x.com", "aud": aud, "exp": int(time.time()) + exp_in},
                      secret, algorithm="HS256")


def auth(sub, **kw):
    return {"Authorization": f"Bearer {token(sub, **kw)}"}


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(config, "AUTH_DISABLED", False)
    emb = FakeEmbedder()

    def setup(*llm_replies):
        llm = ScriptedLLM(*llm_replies)
        p = MeetingPipeline(llm=llm, embedder=emb, reranker=FakeReranker())
        routes._Services.pipeline = p
        routes._Services.agent = MeetingAgent(llm, p.retriever, emb)
        return TestClient(routes.app), llm
    yield setup
    routes._Services.pipeline = routes._Services.agent = None


# ── auth ─────────────────────────────────────────────────────────

def test_health_is_public(client):
    c, _ = client()
    assert c.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer not-a-jwt"},
    {"Authorization": f"Bearer {token('alice', secret='wrong-secret-also-32-bytes-long!!!')}"},
    {"Authorization": f"Bearer {token('alice', exp_in=-10)}"},
    {"Authorization": f"Bearer {token('alice', aud='anon')}"},
])
def test_protected_routes_reject_missing_or_bad_tokens(client, headers):
    c, _ = client()
    for method, path in [("get", "/meetings"), ("get", "/action-items"), ("get", "/me"),
                         ("post", "/agent/chat"), ("get", "/agent/memories")]:
        r = getattr(c, method)(path, headers=headers, **({"json": {"message": "hi"}} if method == "post" else {}))
        assert r.status_code == 401, (path, r.text)


def test_me_returns_the_token_user(client):
    c, _ = client()
    assert c.get("/me", headers=auth("alice")).json()["data"] == {"id": "alice", "email": "alice@x.com"}


# ── ownership ────────────────────────────────────────────────────

def test_users_only_see_their_own_meetings(client, db):
    c, _ = client(json.dumps(EXTRACTION))
    r = c.post("/meetings/transcript", json={"title": "Launch sync", "transcript": TRANSCRIPT}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    mid = r.json()["data"]["meeting_id"]

    mine = c.get("/meetings", headers=auth("alice")).json()["data"]
    assert [(m["title"], m["open_items"]) for m in mine] == [("Launch sync", 1)]
    detail = c.get(f"/meetings/{mid}", headers=auth("alice")).json()["data"]
    assert detail["participants"] == ["Alice", "Bob"]
    assert detail["action_items"][0]["owner"] == "Alice"

    assert c.get("/meetings", headers=auth("bob")).json()["data"] == []
    assert c.get(f"/meetings/{mid}", headers=auth("bob")).status_code == 404
    assert c.get("/action-items", headers=auth("bob")).json()["data"] == []
    item_id = detail["action_items"][0]["id"]
    assert c.patch(f"/action-items/{item_id}/status", params={"status": "done"}, headers=auth("bob")).status_code == 404
    assert c.delete(f"/meetings/{mid}", headers=auth("bob")).status_code == 404
    assert c.post("/query", json={"question": "launch", "meeting_id": mid}, headers=auth("bob")).status_code == 404

    assert c.patch(f"/action-items/{item_id}/status", params={"status": "done"}, headers=auth("alice")).status_code == 200
    assert c.delete(f"/meetings/{mid}", headers=auth("alice")).status_code == 200
    assert db.query(Meeting).count() == 0 and db.query(Chunk).count() == 0 and db.query(ActionItem).count() == 0


def test_same_participant_name_is_separate_per_user(client, db):
    c, _ = client(json.dumps(EXTRACTION), json.dumps(EXTRACTION))
    c.post("/meetings/transcript", json={"title": "A", "transcript": TRANSCRIPT}, headers=auth("alice"))
    c.post("/meetings/transcript", json={"title": "B", "transcript": TRANSCRIPT}, headers=auth("bob"))
    from app.db.models import Participant
    assert sorted((p.user_id, p.name) for p in db.query(Participant)) == [
        ("alice", "Alice"), ("alice", "Bob"), ("bob", "Alice"), ("bob", "Bob")]


# ── live meetings (extension) ────────────────────────────────────

def test_live_captions_become_a_meeting_with_real_speakers(client, db):
    c, llm = client(json.dumps(EXTRACTION))
    captions = [{"speaker": "Alice", "text": "Let's move the launch"}, {"speaker": "Alice", "text": "to August."},
                {"speaker": "Bob", "text": "Agreed, QA is behind."}]
    r = c.post("/meetings/live", json={"title": "Meet call", "captions": captions}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    sent = llm.calls[0]["messages"][-1]["content"]
    assert "Alice: Let's move the launch to August.\nBob: Agreed, QA is behind." in sent
    chunks = db.query(Chunk).order_by(Chunk.id).all()
    assert [(ch.speaker, ch.chunk_text) for ch in chunks] == [
        ("Alice", "Let's move the launch to August."), ("Bob", "Agreed, QA is behind.")]


def test_live_requires_captions(client):
    c, _ = client()
    assert c.post("/meetings/live", json={"title": "x", "captions": []}, headers=auth("alice")).status_code == 422


def test_audio_too_large_is_rejected(client, monkeypatch):
    monkeypatch.setattr(routes, "MAX_AUDIO_MB", 0)
    c, _ = client()
    r = c.post("/meetings/audio", data={"title": "x"}, files={"file": ("a.m4a", b"123", "audio/m4a")},
               headers=auth("alice"))
    assert r.status_code == 413


# ── agent ────────────────────────────────────────────────────────

def test_agent_uses_the_token_user_and_memories(client):
    c, _ = client(tool_call(("save_memory", {"fact": "User is Alice"})), "Noted, Alice.")
    r = c.post("/agent/chat", json={"message": "I'm Alice"}, headers=auth("alice"))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["steps"][0]["tool"] == "save_memory"

    mems = c.get("/agent/memories", headers=auth("alice")).json()["data"]
    assert [m["fact"] for m in mems] == ["User is Alice"]
    assert c.get("/agent/memories", headers=auth("bob")).json()["data"] == []
    assert c.delete(f"/agent/memories/{mems[0]['id']}", headers=auth("bob")).status_code == 404
    assert c.delete(f"/agent/memories/{mems[0]['id']}", headers=auth("alice")).status_code == 200


def test_input_validation(client):
    c, _ = client()
    h = auth("alice")
    assert c.post("/agent/chat", json={"message": ""}, headers=h).status_code == 422
    assert c.post("/query", json={"question": "x", "mode": "magic"}, headers=h).status_code == 422
    assert c.post("/meetings/transcript", json={"title": "", "transcript": TRANSCRIPT}, headers=h).status_code == 422


def test_auth_disabled_mode_uses_local_user(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_DISABLED", True)
    c, _ = client()
    assert c.get("/me").json()["data"]["id"] == "local"
