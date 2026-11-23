from fastapi.testclient import TestClient

from app.agent import MeetingAgent
from app.api import routes
from app.retrieval import Retriever
from conftest import FakeReranker, ScriptedLLM, tool_call


class FakePipeline:
    def __init__(self, embedder, llm):
        self.llm, self.embedding_agent = llm, embedder
        self.retriever = Retriever(embedder, FakeReranker())


def client_with(llm, embedder):
    routes._Services.pipeline = FakePipeline(embedder, llm)
    routes._Services.agent = MeetingAgent(llm, routes._Services.pipeline.retriever, embedder)
    return TestClient(routes.app)


def test_agent_endpoint_and_memories(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("save_memory", {"fact": "User is Alice"})), "Noted, Alice.")
    c = client_with(llm, embedder)
    r = c.post("/agent/chat", json={"message": "I'm Alice", "user_id": "alice"})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["answer"] == "Noted, Alice." and data["steps"][0]["tool"] == "save_memory"

    mems = c.get("/agent/memories", params={"user_id": "alice"}).json()["data"]
    assert [m["fact"] for m in mems] == ["User is Alice"]
    assert c.delete(f"/agent/memories/{mems[0]['id']}", params={"user_id": "bob"}).status_code == 404
    assert c.delete(f"/agent/memories/{mems[0]['id']}", params={"user_id": "alice"}).status_code == 200


def test_agent_endpoint_validates_input(db, embedder):
    c = client_with(ScriptedLLM(), embedder)
    assert c.post("/agent/chat", json={"message": ""}).status_code == 422


def test_query_rejects_unknown_mode(db, embedder):
    c = client_with(ScriptedLLM(), embedder)
    assert c.post("/query", json={"question": "x", "mode": "magic"}).status_code == 422
