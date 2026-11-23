"""Meeting assistant agent: the model chooses tools, our code runs them.

Loop (ReAct-style, using the provider's native tool calling):

    user question + recalled memories + recent history
        -> model: answer, or call one or more tools
        -> run each tool (arguments validated with Pydantic)
        -> tool results go back to the model
        -> repeat until it answers, or AGENT_MAX_STEPS is hit

Safety and robustness:
- Every tool's arguments are validated; a bad call returns an error message
  to the model (so it can correct itself) instead of crashing the request.
- Unknown tools are reported back the same way.
- Only one tool writes data (update_action_item), and only to a whitelisted status.
- A hard step limit stops loops; on the last step the model must answer.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from app import memory
from app.config import AGENT_MAX_STEPS, RETRIEVAL_MODE
from app.db.models import ActionItem, Decision, Meeting, Participant

# ---------------------------------------------------------------- tool args


class SearchArgs(BaseModel):
    query: str = Field(min_length=2)
    meeting_id: Optional[int] = None


class ListMeetingsArgs(BaseModel):
    limit: int = Field(10, ge=1, le=50)


class ActionItemsArgs(BaseModel):
    meeting_id: Optional[int] = None
    owner: Optional[str] = None
    status: Optional[Literal["open", "in_progress", "done"]] = None


class DecisionsArgs(BaseModel):
    meeting_id: Optional[int] = None


class UpdateItemArgs(BaseModel):
    item_id: int
    status: Literal["open", "in_progress", "done"]


class SaveMemoryArgs(BaseModel):
    fact: str = Field(min_length=3, max_length=300)


def _schema(name: str, description: str, model: type[BaseModel]) -> dict:
    params = model.model_json_schema()
    params.pop("title", None)
    for p in params.get("properties", {}).values():
        p.pop("title", None)
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


TOOL_SPECS = [
    ("search_meetings", "Search meeting transcripts for what was said about a topic. Use for questions "
                        "about discussions, reasons, opinions or anything not in the structured data.",
     SearchArgs),
    ("list_meetings", "List recent meetings with id, title, date and summary.", ListMeetingsArgs),
    ("get_action_items", "Get action items (tasks), filtered by meeting, owner name and/or status.",
     ActionItemsArgs),
    ("get_decisions", "Get decisions recorded in meetings, optionally for one meeting.", DecisionsArgs),
    ("update_action_item", "Change the status of one action item. Only when the user asks to.",
     UpdateItemArgs),
    ("save_memory", "Remember a lasting fact or preference about the user for future conversations, "
                    "e.g. their name or which items they own. Not for one-off questions.", SaveMemoryArgs),
]
TOOLS = [_schema(n, d, m) for n, d, m in TOOL_SPECS]
ARG_MODELS = {n: m for n, _, m in TOOL_SPECS}

SYSTEM = """You are the assistant for a team's meeting records. Today is {today}.
Use the tools to look things up; never invent meetings, people, tasks or decisions.
Prefer get_action_items / get_decisions for tasks and decisions, search_meetings for what was said.
When you use transcript excerpts, mention which meeting they came from.
If the user tells you something lasting about themselves, call save_memory.
Answer briefly and directly.{memories}"""


# ---------------------------------------------------------------- tools


class ToolBox:
    def __init__(self, db, retriever, embedder, user_id: str, retrieval_mode: str = RETRIEVAL_MODE):
        self.db, self.retriever, self.embedder = db, retriever, embedder
        self.user_id, self.mode = user_id, retrieval_mode

    def run(self, name: str, raw_args: str) -> tuple[bool, dict]:
        if name not in ARG_MODELS:
            return False, {"error": f"unknown tool '{name}'. Available: {sorted(ARG_MODELS)}"}
        try:
            args = ARG_MODELS[name].model_validate(json.loads(raw_args or "{}"))
        except (json.JSONDecodeError, ValidationError) as e:
            return False, {"error": f"invalid arguments for {name}: {e}"}
        try:
            return True, getattr(self, name)(args)
        except ValueError as e:                 # expected problems, e.g. item not found
            return False, {"error": str(e)}

    def search_meetings(self, a: SearchArgs) -> dict:
        hits = self.retriever.search(self.db, a.query, k=5, mode=self.mode, meeting_id=a.meeting_id)
        return {"results": [{"meeting_id": h.meeting_id, "meeting": h.meeting_title,
                             "speaker": h.speaker, "text": h.text} for h in hits]}

    def list_meetings(self, a: ListMeetingsArgs) -> dict:
        rows = self.db.query(Meeting).order_by(Meeting.date.desc()).limit(a.limit).all()
        return {"meetings": [{"id": m.id, "title": m.title, "date": str(m.date)[:10], "summary": m.summary}
                             for m in rows]}

    def get_action_items(self, a: ActionItemsArgs) -> dict:
        q = (self.db.query(ActionItem, Participant.name, Meeting.title)
             .outerjoin(Participant, ActionItem.owner_id == Participant.id)
             .join(Meeting, ActionItem.meeting_id == Meeting.id))
        if a.meeting_id:
            q = q.filter(ActionItem.meeting_id == a.meeting_id)
        if a.owner:
            q = q.filter(Participant.name.ilike(f"%{a.owner}%"))
        if a.status:
            q = q.filter(ActionItem.status == a.status)
        rows = q.order_by(ActionItem.deadline.nulls_last(), ActionItem.id).limit(50).all()
        return {"action_items": [{"id": i.id, "description": i.description, "owner": owner,
                                  "status": i.status, "deadline": str(i.deadline) if i.deadline else None,
                                  "meeting": title} for i, owner, title in rows]}

    def get_decisions(self, a: DecisionsArgs) -> dict:
        q = self.db.query(Decision, Meeting.title).join(Meeting, Decision.meeting_id == Meeting.id)
        if a.meeting_id:
            q = q.filter(Decision.meeting_id == a.meeting_id)
        rows = q.order_by(Decision.id).limit(50).all()
        return {"decisions": [{"id": d.id, "description": d.description, "context": d.context,
                               "meeting": title} for d, title in rows]}

    def update_action_item(self, a: UpdateItemArgs) -> dict:
        item = self.db.get(ActionItem, a.item_id)
        if not item:
            raise ValueError(f"no action item with id {a.item_id}")
        old, item.status = item.status, a.status
        self.db.flush()
        return {"id": item.id, "description": item.description, "old_status": old, "new_status": a.status}

    def save_memory(self, a: SaveMemoryArgs) -> dict:
        return memory.save_fact(self.db, self.embedder, self.user_id, a.fact)


# ---------------------------------------------------------------- agent


def _summarize(result: dict) -> str:
    if "error" in result:
        return result["error"][:200]
    for key, val in result.items():
        if isinstance(val, list):
            return f"{len(val)} {key.replace('_', ' ')}"
    return json.dumps(result)[:200]


class MeetingAgent:
    def __init__(self, llm, retriever, embedder, max_steps: int = AGENT_MAX_STEPS):
        self.llm, self.retriever, self.embedder, self.max_steps = llm, retriever, embedder, max_steps

    def chat(self, db, user_id: str, message: str, conversation_id: int | None = None) -> dict:
        conv = memory.get_or_create_conversation(db, user_id, conversation_id)
        facts = memory.recall(db, self.embedder, user_id, message)
        mem_text = ("\n\nWhat you remember about this user:\n" + "\n".join(f"- {f}" for f in facts)) if facts else ""

        messages = [{"role": "system", "content": SYSTEM.format(today=date.today().isoformat(), memories=mem_text)},
                    *memory.history(db, conv.id),
                    {"role": "user", "content": message}]
        tools = ToolBox(db, self.retriever, self.embedder, user_id)
        steps: list[dict] = []
        answer = None

        for step in range(self.max_steps):
            last = step == self.max_steps - 1
            out = self.llm.chat(messages, tools=None if last else TOOLS)
            if not out["tool_calls"]:
                answer = (out["content"] or "").strip()
                break
            messages.append({"role": "assistant", "content": out["content"] or "",
                             "tool_calls": [{"id": c["id"], "type": "function",
                                             "function": {"name": c["name"], "arguments": c["arguments"]}}
                                            for c in out["tool_calls"]]})
            for call in out["tool_calls"]:
                ok, result = tools.run(call["name"], call["arguments"])
                steps.append({"tool": call["name"], "arguments": call["arguments"], "ok": ok,
                              "summary": _summarize(result)})
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(result, default=str)[:6000]})

        if not answer:
            answer = "I couldn't finish that within the step limit. Try asking more specifically."

        memory.add_message(db, conv.id, "user", message)
        memory.add_message(db, conv.id, "assistant", answer)
        db.commit()
        return {"answer": answer, "conversation_id": conv.id, "steps": steps, "memories_used": facts}
