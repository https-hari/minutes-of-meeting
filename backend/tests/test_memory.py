from app import memory
from app.agent import MeetingAgent
from app.retrieval import Retriever
from conftest import FakeReranker, ScriptedLLM, tool_call


def test_small_memory_is_recalled_in_full(db, embedder):
    memory.save_fact(db, embedder, "bob", "My name is Bob")
    memory.save_fact(db, embedder, "bob", "I prefer short answers")
    db.commit()
    # "my tasks" shares no words with "My name is Bob", but identity must still be known
    assert memory.recall(db, embedder, "bob", "what are my open tasks?") == [
        "My name is Bob", "I prefer short answers"]


def test_large_memory_recalls_only_relevant_facts(db, embedder, monkeypatch):
    monkeypatch.setattr(memory, "SMALL_MEMORY", 1)
    memory.save_fact(db, embedder, "bob", "My name is Bob and I own the launch timeline")
    memory.save_fact(db, embedder, "bob", "I prefer short answers")
    db.commit()
    facts = memory.recall(db, embedder, "bob", "what about the launch timeline", k=1)
    assert facts == ["My name is Bob and I own the launch timeline"]


def test_memories_are_per_user(db, embedder):
    memory.save_fact(db, embedder, "bob", "I own the launch timeline")
    db.commit()
    assert memory.recall(db, embedder, "alice", "launch timeline") == []


def test_near_duplicate_fact_updates_instead_of_inserting(db, embedder):
    memory.save_fact(db, embedder, "bob", "I own the launch timeline")
    r = memory.save_fact(db, embedder, "bob", "I own the launch timeline.")
    db.commit()
    assert r["updated"] is True and len(memory.list_facts(db, "bob")) == 1


def test_agent_saves_memory_and_uses_it_next_time(db, seeded, embedder):
    a = lambda llm: MeetingAgent(llm, Retriever(embedder, FakeReranker()), embedder)
    a(ScriptedLLM(tool_call(("save_memory", {"fact": "The user is Bob, owner of the launch timeline"})),
                  "Got it, Bob.")).chat(db, "u1", "I'm Bob, I own the launch timeline.")

    llm = ScriptedLLM("Your launch timeline update is in progress.")
    out = a(llm).chat(db, "u1", "How is my launch timeline task going?")   # new conversation
    assert out["memories_used"] == ["The user is Bob, owner of the launch timeline"]
    assert "owner of the launch timeline" in llm.calls[0]["messages"][0]["content"]
