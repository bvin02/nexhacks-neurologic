"""
Report Model

Stores generated reports from work sessions.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
import uuid

from ..database import Base


class Report(Base):
    """
    A generated report from a work session conversation.
    
    Reports are:
    - Generated via LLM from conversation history
    - Stored as markdown content
    - Project-specific
    """
    __tablename__ = "reports"
    
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
    
    # File name provided by user
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Optional description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Generated markdown content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Source session (optional, for reference)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("work_sessions.id", ondelete="SET NULL"),
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="reports"
    )
    
    def __repr__(self) -> str:
        return f"<Report(id={self.id}, name={self.name})>"
