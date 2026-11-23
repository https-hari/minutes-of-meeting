from sqlalchemy import (
    Column, Integer, Text, DateTime, Date,
    ForeignKey, CheckConstraint, ARRAY
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from app.db.connection import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Text, nullable=False, index=True)   # owner (Supabase user id)
    title       = Column(Text, nullable=False)
    date        = Column(DateTime, server_default=func.now())
    duration    = Column(Integer)
    transcript  = Column(Text)
    summary     = Column(Text)
    created_at  = Column(DateTime, server_default=func.now())

    action_items    = relationship("ActionItem", back_populates="meeting")
    decisions       = relationship("Decision",   back_populates="meeting")
    chunks          = relationship("Chunk",       back_populates="meeting")
    participants    = relationship("MeetingParticipant", back_populates="meeting")


class Participant(Base):
    __tablename__ = "participants"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Text, nullable=False, index=True)   # people are per account
    name        = Column(Text, nullable=False)
    email       = Column(Text)
    created_at  = Column(DateTime, server_default=func.now())

    meetings        = relationship("MeetingParticipant", back_populates="participant")
    action_items    = relationship("ActionItem", back_populates="owner")


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"

    meeting_id      = Column(Integer, ForeignKey("meetings.id",     ondelete="CASCADE"), primary_key=True)
    participant_id  = Column(Integer, ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True)

    meeting     = relationship("Meeting",     back_populates="participants")
    participant = relationship("Participant", back_populates="meetings")


class ActionItem(Base):
    __tablename__ = "action_items"

    id          = Column(Integer, primary_key=True, index=True)
    meeting_id  = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"))
    owner_id    = Column(Integer, ForeignKey("participants.id"))
    description = Column(Text, nullable=False)
    deadline    = Column(Date)
    status      = Column(Text, nullable=False, default="open")
    created_at  = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'done')",
            name="valid_status"
        ),
    )

    meeting = relationship("Meeting",     back_populates="action_items")
    owner   = relationship("Participant", back_populates="action_items")


class Decision(Base):
    __tablename__ = "decisions"

    id          = Column(Integer, primary_key=True, index=True)
    meeting_id  = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"))
    description = Column(Text, nullable=False)
    context     = Column(Text)
    created_at  = Column(DateTime, server_default=func.now())

    meeting = relationship("Meeting", back_populates="decisions")


class Chunk(Base):
    __tablename__ = "chunks"

    id          = Column(Integer, primary_key=True, index=True)
    meeting_id  = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"))
    chunk_text  = Column(Text, nullable=False)
    speaker     = Column(Text)
    embedding   = Column(Vector(384))
    created_at  = Column(DateTime, server_default=func.now())

    meeting = relationship("Meeting", back_populates="chunks")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id              = Column(Integer, primary_key=True, index=True)
    user_id         = Column(Text, index=True)
    question        = Column(Text, nullable=False)
    answer          = Column(Text)
    chunk_ids_used  = Column(ARRAY(Integer))
    meeting_id      = Column(Integer, ForeignKey("meetings.id"))
    created_at      = Column(DateTime, server_default=func.now())


# ── agent memory (v2) ─────────────────────────────────────────────
# Short-term memory = the conversation (messages). Long-term memory =
# facts about a user that should survive across conversations, stored
# with an embedding so only the relevant ones are recalled per question.

class Conversation(Base):
    __tablename__ = "conversations"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Text, nullable=False, index=True)
    created_at  = Column(DateTime, server_default=func.now())

    messages = relationship("Message", back_populates="conversation",
                            order_by="Message.id", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(Text, nullable=False)
    content         = Column(Text, nullable=False)
    created_at      = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="valid_role"),
    )

    conversation = relationship("Conversation", back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Text, nullable=False, index=True)
    fact        = Column(Text, nullable=False)
    embedding   = Column(Vector(384), nullable=False)
    created_at  = Column(DateTime, server_default=func.now())
