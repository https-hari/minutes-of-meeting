"""REST API. Every route except /health needs a signed-in user, and every query
is scoped to that user's meetings: another user's ids return 404, never data."""
import os
import tempfile
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, text

from app import memory
from app.agent import MeetingAgent
from app.auth import User, current_user
from app.config import CORS_ORIGINS, MAX_AUDIO_MB, RETRIEVAL_MODE
from app.db.connection import SessionLocal
from app.db.init_db import init_db
from app.db.models import ActionItem, Decision, Meeting, MeetingParticipant, Participant
from app.pipeline import MeetingPipeline

app = FastAPI(title="Minutes of Meeting API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",   # the browser extension
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class _Services:
    """Built on first request, so importing the app (e.g. in tests) loads no models."""
    pipeline: MeetingPipeline = None
    agent: MeetingAgent = None


def services() -> _Services:
    if _Services.pipeline is None:
        _Services.pipeline = MeetingPipeline()
    if _Services.agent is None:
        p = _Services.pipeline
        _Services.agent = MeetingAgent(p.llm, p.retriever, p.embedding_agent)
    return _Services


@app.on_event("startup")
def _startup():
    if os.getenv("SKIP_DB_INIT") != "1":
        init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def owned_meeting(db, meeting_id: int, user: User) -> Meeting:
    m = db.query(Meeting).filter(Meeting.id == meeting_id, Meeting.user_id == user.id).first()
    if not m:
        raise HTTPException(404, "Meeting not found")
    return m


# ── request models ───────────────────────────────────────────────

class TranscriptRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=10, max_length=500_000)


class CaptionLine(BaseModel):
    speaker: str = Field("Unknown", max_length=100)
    text: str = Field(min_length=1, max_length=5000)


class LiveMeetingRequest(BaseModel):
    """Sent by the Chrome extension when a live meeting ends."""
    title: str = Field(min_length=1, max_length=200)
    captions: List[CaptionLine] = Field(min_length=1, max_length=20_000)
    source: str = Field("google-meet", max_length=50)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    meeting_id: Optional[int] = None
    mode: Literal["vector", "keyword", "hybrid", "hybrid_rerank"] = RETRIEVAL_MODE


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[int] = None


# ── misc ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "minutes-of-meeting"}


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"success": True, "data": {"id": user.id, "email": user.email}}


# ── ingest ───────────────────────────────────────────────────────

def _run(fn, *args):
    try:
        return {"success": True, "data": fn(*args)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Processing failed: {e}")


@app.post("/meetings/transcript")
def ingest_transcript(req: TranscriptRequest, user: User = Depends(current_user)):
    """A pasted or uploaded text transcript ("Name: what they said" per line works best)."""
    return _run(services().pipeline.process_transcript, req.transcript, req.title, user.id)


@app.post("/meetings/live")
def ingest_live(req: LiveMeetingRequest, user: User = Depends(current_user)):
    """Captions captured by the extension during a live meeting, with real speaker names."""
    lines, last = [], None
    for c in req.captions:                         # merge consecutive lines from one speaker
        speaker = c.speaker.strip() or "Unknown"
        if lines and speaker == last:
            lines[-1] += " " + c.text.strip()
        else:
            lines.append(f"{speaker}: {c.text.strip()}")
            last = speaker
    return _run(services().pipeline.process_transcript, "\n".join(lines), req.title, user.id)


@app.post("/meetings/audio")
async def ingest_audio(title: str = Form(..., min_length=1, max_length=200),
                       file: UploadFile = File(...), user: User = Depends(current_user)):
    """An audio file (mp3, m4a, wav, webm...). Transcribed with Whisper."""
    data = await file.read()
    if len(data) > MAX_AUDIO_MB * 1024 * 1024:
        raise HTTPException(413, f"Audio is larger than {MAX_AUDIO_MB} MB. Compress it or split it.")
    suffix = os.path.splitext(file.filename or "")[1] or ".m4a"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
    try:
        return _run(services().pipeline.process_audio, tmp.name, title, user.id)
    finally:
        os.remove(tmp.name)


# ── read / update ────────────────────────────────────────────────

@app.get("/meetings")
def list_meetings(user: User = Depends(current_user), db=Depends(get_db)):
    rows = db.query(Meeting).filter(Meeting.user_id == user.id).order_by(Meeting.date.desc()).all()
    counts = dict(db.query(ActionItem.meeting_id, func.count(ActionItem.id))
                  .join(Meeting, ActionItem.meeting_id == Meeting.id)
                  .filter(Meeting.user_id == user.id, ActionItem.status != "done")
                  .group_by(ActionItem.meeting_id).all())
    return {"success": True, "data": [
        {"id": m.id, "title": m.title, "date": str(m.date), "summary": m.summary,
         "duration": m.duration, "open_items": counts.get(m.id, 0)} for m in rows]}


@app.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int, user: User = Depends(current_user), db=Depends(get_db)):
    m = owned_meeting(db, meeting_id, user)
    items = (db.query(ActionItem, Participant.name)
             .outerjoin(Participant, ActionItem.owner_id == Participant.id)
             .filter(ActionItem.meeting_id == m.id).order_by(ActionItem.id).all())
    decisions = db.query(Decision).filter(Decision.meeting_id == m.id).order_by(Decision.id).all()
    people = (db.query(Participant.name).join(MeetingParticipant)
              .filter(MeetingParticipant.meeting_id == m.id).order_by(Participant.name).all())
    return {"success": True, "data": {
        "id": m.id, "title": m.title, "date": str(m.date), "summary": m.summary,
        "duration": m.duration, "transcript": m.transcript,
        "participants": [p.name for p in people],
        "action_items": [{"id": a.id, "description": a.description, "status": a.status,
                          "deadline": str(a.deadline) if a.deadline else None, "owner": owner}
                         for a, owner in items],
        "decisions": [{"id": d.id, "description": d.description, "context": d.context} for d in decisions],
    }}


@app.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: int, user: User = Depends(current_user), db=Depends(get_db)):
    m = owned_meeting(db, meeting_id, user)
    # query logs keep the question but lose the link; everything else cascades in the database
    db.execute(text("UPDATE query_logs SET meeting_id = NULL WHERE meeting_id = :id"), {"id": m.id})
    db.query(Meeting).filter(Meeting.id == m.id).delete(synchronize_session=False)
    db.commit()
    return {"success": True, "data": {"id": meeting_id}}


@app.get("/action-items")
def list_action_items(status: Optional[Literal["open", "in_progress", "done"]] = None,
                      user: User = Depends(current_user), db=Depends(get_db)):
    q = (db.query(ActionItem, Participant.name, Meeting.title)
         .join(Meeting, ActionItem.meeting_id == Meeting.id)
         .outerjoin(Participant, ActionItem.owner_id == Participant.id)
         .filter(Meeting.user_id == user.id))
    if status:
        q = q.filter(ActionItem.status == status)
    rows = q.order_by(ActionItem.deadline.nulls_last(), ActionItem.id).all()
    return {"success": True, "data": [
        {"id": a.id, "description": a.description, "status": a.status,
         "deadline": str(a.deadline) if a.deadline else None, "owner": owner,
         "meeting_id": a.meeting_id, "meeting": title} for a, owner, title in rows]}


@app.patch("/action-items/{item_id}/status")
def update_action_item_status(item_id: int, status: Literal["open", "in_progress", "done"],
                              user: User = Depends(current_user), db=Depends(get_db)):
    item = (db.query(ActionItem).join(Meeting, ActionItem.meeting_id == Meeting.id)
            .filter(ActionItem.id == item_id, Meeting.user_id == user.id).first())
    if not item:
        raise HTTPException(404, "Action item not found")
    item.status = status
    db.commit()
    return {"success": True, "data": {"id": item_id, "status": status}}


# ── search and agent ─────────────────────────────────────────────

@app.post("/query")
def query_meetings(req: QueryRequest, user: User = Depends(current_user), db=Depends(get_db)):
    if req.meeting_id:
        owned_meeting(db, req.meeting_id, user)
    return _run(lambda: services().pipeline.query(req.question, req.meeting_id, mode=req.mode,
                                                  user_id=user.id))


@app.post("/agent/chat")
def agent_chat(req: AgentRequest, user: User = Depends(current_user), db=Depends(get_db)):
    """The agent picks tools (search, action items, decisions, update status, remember)
    and returns its answer plus the steps it took."""
    try:
        return {"success": True, "data": services().agent.chat(db, user.id, req.message, req.conversation_id)}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Agent failed: {e}")


@app.get("/agent/memories")
def list_memories(user: User = Depends(current_user), db=Depends(get_db)):
    return {"success": True, "data": memory.list_facts(db, user.id)}


@app.delete("/agent/memories/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(current_user), db=Depends(get_db)):
    if not memory.delete_fact(db, user.id, memory_id):
        raise HTTPException(404, "Memory not found")
    db.commit()
    return {"success": True, "data": {"id": memory_id}}
