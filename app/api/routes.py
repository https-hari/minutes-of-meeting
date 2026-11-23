from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal, Optional
from app import memory
from app.agent import MeetingAgent
from app.config import RETRIEVAL_MODE
from app.pipeline import MeetingPipeline
from app.db.connection import SessionLocal
from app.db.init_db import init_db
from app.db.models import Meeting, ActionItem, Participant, Decision
import shutil
import os

app = FastAPI(title="Meeting Intelligence Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
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


# ── request/response models ──────────────────────────────────────

class TranscriptRequest(BaseModel):
    title: str
    transcript: str

class QueryRequest(BaseModel):
    question: str
    meeting_id: Optional[int] = None
    mode: Literal["vector", "keyword", "hybrid", "hybrid_rerank"] = RETRIEVAL_MODE

class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str = Field("default", min_length=1, max_length=100)
    conversation_id: Optional[int] = None


# ── routes ───────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "running", "service": "Meeting Intelligence Agent"}


@app.post("/meetings/transcript")
def ingest_transcript(req: TranscriptRequest):
    """
    Ingest a raw transcript string.
    Used for testing without audio files.
    """
    try:
        result = services().pipeline.process_transcript(req.transcript, req.title)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/meetings/audio")
async def ingest_audio(title: str, file: UploadFile = File(...)):
    """
    Ingest an audio file.
    Saves temporarily, runs pipeline, deletes temp file.
    """
    temp_path = f"/tmp/{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = services().pipeline.process_audio(temp_path, title)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.post("/query")
def query_meetings(req: QueryRequest):
    """
    Ask a natural language question across all meetings
    or a specific meeting.
    """
    try:
        result = services().pipeline.query(req.question, req.meeting_id, mode=req.mode)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meetings")
def list_meetings():
    """Returns all meetings with summary info."""
    db = SessionLocal()
    try:
        meetings = db.query(Meeting).order_by(Meeting.date.desc()).all()
        return {
            "success": True,
            "data": [
                {
                    "id":         m.id,
                    "title":      m.title,
                    "date":       str(m.date),
                    "summary":    m.summary,
                    "duration":   m.duration
                }
                for m in meetings
            ]
        }
    finally:
        db.close()


@app.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int):
    """Returns full detail for one meeting."""
    db = SessionLocal()
    try:
        m = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not m:
            raise HTTPException(status_code=404, detail="Meeting not found")

        action_items = db.query(ActionItem).filter(
            ActionItem.meeting_id == meeting_id
        ).all()

        decisions = db.query(Decision).filter(
            Decision.meeting_id == meeting_id
        ).all()

        return {
            "success": True,
            "data": {
                "id":          m.id,
                "title":       m.title,
                "date":        str(m.date),
                "summary":     m.summary,
                "transcript":  m.transcript,
                "action_items": [
                    {
                        "id":          a.id,
                        "description": a.description,
                        "status":      a.status,
                        "deadline":    str(a.deadline) if a.deadline else None,
                        "owner_id":    a.owner_id
                    }
                    for a in action_items
                ],
                "decisions": [
                    {
                        "id":          d.id,
                        "description": d.description,
                        "context":     d.context
                    }
                    for d in decisions
                ]
            }
        }
    finally:
        db.close()


@app.get("/action-items")
def list_action_items(status: str = None):
    """
    Returns action items, optionally filtered by status.
    Example: GET /action-items?status=open
    """
    db = SessionLocal()
    try:
        query = db.query(ActionItem)
        if status:
            query = query.filter(ActionItem.status == status)

        items = query.order_by(ActionItem.deadline).all()

        return {
            "success": True,
            "data": [
                {
                    "id":          a.id,
                    "description": a.description,
                    "status":      a.status,
                    "deadline":    str(a.deadline) if a.deadline else None,
                    "meeting_id":  a.meeting_id,
                    "owner_id":    a.owner_id
                }
                for a in items
            ]
        }
    finally:
        db.close()


@app.patch("/action-items/{item_id}/status")
def update_action_item_status(item_id: int, status: str):
    """
    Updates the status of an action item.
    Valid values: open, in_progress, done
    """
    valid = ["open", "in_progress", "done"]
    if status not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid}"
        )

    db = SessionLocal()
    try:
        item = db.query(ActionItem).filter(ActionItem.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Action item not found")

        item.status = status
        db.commit()
        return {"success": True, "data": {"id": item_id, "status": status}}
    finally:
        db.close()


# ── agent (v2) ───────────────────────────────────────────────────

@app.post("/agent/chat")
def agent_chat(req: AgentRequest):
    """
    Ask the meeting agent. It decides which tools to call (search transcripts,
    action items, decisions, update a status, remember a fact) and returns its
    answer plus the steps it took.
    """
    db = SessionLocal()
    try:
        result = services().agent.chat(db, req.user_id, req.message, req.conversation_id)
        return {"success": True, "data": result}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@app.get("/agent/memories")
def list_memories(user_id: str = "default"):
    db = SessionLocal()
    try:
        return {"success": True, "data": memory.list_facts(db, user_id)}
    finally:
        db.close()


@app.delete("/agent/memories/{memory_id}")
def delete_memory(memory_id: int, user_id: str = "default"):
    db = SessionLocal()
    try:
        if not memory.delete_fact(db, user_id, memory_id):
            raise HTTPException(status_code=404, detail="Memory not found")
        db.commit()
        return {"success": True, "data": {"id": memory_id}}
    finally:
        db.close()
