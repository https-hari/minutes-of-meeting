import json

from app.agent import TOOLS, MeetingAgent
from app.db.models import ActionItem, Message
from app.retrieval import Retriever
from conftest import FakeReranker, ScriptedLLM, tool_call


def agent(llm, embedder, steps=6):
    return MeetingAgent(llm, Retriever(embedder, FakeReranker()), embedder, max_steps=steps)


def test_tool_schemas_are_valid_function_specs():
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"search_meetings", "list_meetings", "get_action_items", "get_decisions",
                     "update_action_item", "save_memory"}
    for t in TOOLS:
        assert t["function"]["parameters"]["type"] == "object"


def test_agent_calls_tool_then_answers(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("get_action_items", {"owner": "alice", "status": "open"})),
                      "Alice still owes the revised budget proposal.")
    out = agent(llm, embedder).chat(db, "u1", "What does Alice still have open?")
    assert out["answer"].startswith("Alice still owes")
    assert out["steps"][0]["tool"] == "get_action_items" and out["steps"][0]["ok"]
    tool_msg = llm.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool"
    items = json.loads(tool_msg["content"])["action_items"]
    assert [i["description"] for i in items] == ["Prepare revised budget proposal"]


def test_invalid_arguments_go_back_to_the_model(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("get_action_items", {"status": "finished"})),      # not a valid status
                      tool_call(("get_action_items", {"status": "done"})),
                      "Renew TLS certificate is done.")
    out = agent(llm, embedder).chat(db, "u1", "What's done?")
    assert [s["ok"] for s in out["steps"]] == [False, True]
    assert "invalid arguments" in json.loads(llm.calls[1]["messages"][-1]["content"])["error"]


def test_unknown_tool_is_reported_not_crashed(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("delete_everything", {})), "I can't do that.")
    out = agent(llm, embedder).chat(db, "u1", "wipe it")
    assert out["steps"][0]["ok"] is False and "unknown tool" in out["steps"][0]["summary"]


def test_update_action_item_writes_status(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("update_action_item", {"item_id": 1, "status": "done"})), "Marked done.")
    agent(llm, embedder).chat(db, "u1", "Mark the budget proposal done")
    db.expire_all()
    assert db.get(ActionItem, 1).status == "done"


def test_search_tool_uses_hybrid_retrieval(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("search_meetings", {"query": "JIRA-482 outage"})), "An expired TLS cert.")
    out = agent(llm, embedder).chat(db, "u1", "What caused the login outage?")
    results = json.loads(llm.calls[1]["messages"][-1]["content"])["results"]
    assert "JIRA-482" in results[0]["text"]
    assert out["steps"][0]["ok"] and out["steps"][0]["summary"].endswith("results")


def test_step_limit_forces_an_answer_without_tools(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("list_meetings", {})), tool_call(("list_meetings", {})), "Two meetings.")
    out = agent(llm, embedder, steps=3).chat(db, "u1", "list")
    assert out["answer"] == "Two meetings."
    assert llm.calls[-1]["tools"] is None                 # last step: tools withheld


def test_conversation_history_is_replayed(db, seeded, embedder):
    a = agent(ScriptedLLM("First answer."), embedder)
    first = a.chat(db, "u1", "Hello")
    llm2 = ScriptedLLM("Second answer.")
    agent(llm2, embedder).chat(db, "u1", "And again?", conversation_id=first["conversation_id"])
    roles = [m["role"] for m in llm2.calls[0]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert db.query(Message).count() == 4


def test_other_users_cannot_continue_a_conversation(db, seeded, embedder):
    first = agent(ScriptedLLM("Hi."), embedder).chat(db, "alice", "Hello")
    second = agent(ScriptedLLM("Hi."), embedder).chat(db, "mallory", "Hello", conversation_id=first["conversation_id"])
    assert second["conversation_id"] != first["conversation_id"]


def test_tools_only_see_the_callers_meetings(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("get_action_items", {}), ("get_decisions", {}), ("list_meetings", {}),
                                ("search_meetings", {"query": "marketing budget"})), "Nothing.")
    agent(llm, embedder).chat(db, "intruder", "show me everything")
    results = [json.loads(m["content"]) for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert results == [{"action_items": []}, {"decisions": []}, {"meetings": []}, {"results": []}]


def test_cannot_update_another_users_item(db, seeded, embedder):
    llm = ScriptedLLM(tool_call(("update_action_item", {"item_id": 1, "status": "done"})), "Can't.")
    out = agent(llm, embedder).chat(db, "intruder", "mark item 1 done")
    assert out["steps"][0]["ok"] is False
    db.expire_all()
    assert db.get(ActionItem, 1).status == "open"
