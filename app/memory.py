"""Agent memory.

Short-term: the conversation's last few messages are replayed to the model.
Long-term:  facts about the user ("I'm Bob", "only show my open items") are
            saved with an embedding; for each new question only the few most
            relevant facts are recalled, so memory can grow without filling the
            prompt.
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.models import Conversation, Memory, Message

HISTORY_MESSAGES = 10      # short-term window replayed to the model
RECALL_K = 3               # long-term facts injected per question (when there are many)
SMALL_MEMORY = 8           # up to this many facts, include them all: identity facts like
                           # "I'm Bob" matter for "what are MY tasks?" but are not
                           # semantically similar to it, so similarity search would miss them
RECALL_MAX_DISTANCE = 0.75  # cosine distance; MiniLM puts unrelated sentences around 0.85-1.0
DUPLICATE_DISTANCE = 0.08  # closer than this = same fact, update instead of insert


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def get_or_create_conversation(db, user_id: str, conversation_id: int | None) -> Conversation:
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv and conv.user_id == user_id:
            return conv
    conv = Conversation(user_id=user_id)
    db.add(conv)
    db.flush()
    return conv


def history(db, conversation_id: int, limit: int = HISTORY_MESSAGES) -> list[dict]:
    rows = (db.query(Message).filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc()).limit(limit).all())
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def add_message(db, conversation_id: int, role: str, content: str) -> None:
    db.add(Message(conversation_id=conversation_id, role=role, content=content))


def save_fact(db, embedder, user_id: str, fact: str) -> dict:
    """Store a fact; if a near-identical one exists, replace its wording instead."""
    fact = fact.strip()
    if not fact:
        raise ValueError("fact is empty")
    vec = embedder.embed_text(fact)
    row = db.execute(text(
        "SELECT id, embedding <=> CAST(:v AS vector) AS d FROM memories "
        "WHERE user_id = :u ORDER BY d LIMIT 1"), {"v": _vec(vec), "u": user_id}).first()
    if row and row.d < DUPLICATE_DISTANCE:
        mem = db.get(Memory, row.id)
        mem.fact, mem.embedding = fact, vec
        db.flush()
        return {"id": mem.id, "fact": fact, "updated": True}
    mem = Memory(user_id=user_id, fact=fact, embedding=vec)
    db.add(mem)
    db.flush()
    return {"id": mem.id, "fact": fact, "updated": False}


def recall(db, embedder, user_id: str, query: str, k: int = RECALL_K) -> list[str]:
    total = db.query(Memory).filter(Memory.user_id == user_id).count()
    if total == 0:
        return []
    if total <= SMALL_MEMORY:
        return [m.fact for m in db.query(Memory).filter(Memory.user_id == user_id).order_by(Memory.id)]
    rows = db.execute(text(
        "SELECT fact, embedding <=> CAST(:v AS vector) AS d FROM memories "
        "WHERE user_id = :u ORDER BY d LIMIT :k"),
        {"v": _vec(embedder.embed_query(query)), "u": user_id, "k": k}).fetchall()
    return [r.fact for r in rows if r.d <= RECALL_MAX_DISTANCE]


def list_facts(db, user_id: str) -> list[dict]:
    rows = db.query(Memory).filter(Memory.user_id == user_id).order_by(Memory.id).all()
    return [{"id": m.id, "fact": m.fact, "created_at": str(m.created_at)} for m in rows]


def delete_fact(db, user_id: str, memory_id: int) -> bool:
    n = db.query(Memory).filter(Memory.id == memory_id, Memory.user_id == user_id).delete()
    return n > 0
