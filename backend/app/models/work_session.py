"""
Work Session Models

Session-based work chat with conversation history.
Memories are only ingested when session ends.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum
import uuid

from ..database import Base


class SessionStatus(str, enum.Enum):
    """Status of a work session."""
    ACTIVE = "active"
    COMPLETED = "completed"


class WorkSession(Base):
    """
    A work chat session with conversation memory.
    
    Work sessions:
    - Have multi-turn conversation history
    - Do NOT ingest memories on each message
    - Ingest memories only when session ends
    """
    __tablename__ = "work_sessions"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Task description provided when session started
    task_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Session status
    status: Mapped[SessionStatus] = mapped_column(
        SQLEnum(SessionStatus),
        default=SessionStatus.ACTIVE,
        nullable=False,
        index=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="work_sessions"
    )
    messages: Mapped[List["WorkMessage"]] = relationship(
        "WorkMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="WorkMessage.created_at"
    )
    
    def __repr__(self) -> str:
        return f"<WorkSession(id={self.id}, status={self.status})>"


class WorkMessage(Base):
    """
    A message in a work session.
    
    Stores both user and assistant messages for conversation history.
    """
    __tablename__ = "work_messages"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("work_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False
    )  # "user" or "assistant"
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationship
    session: Mapped["WorkSession"] = relationship(
        "WorkSession",
        back_populates="messages"
    )
    
    def __repr__(self) -> str:
        return f"<WorkMessage(id={self.id}, role={self.role})>"
