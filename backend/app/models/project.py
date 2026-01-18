"""
Project Model

Projects are the top-level container for all memory and context.
All tables are scoped by project_id to prevent cross-project leakage.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import uuid

from ..database import Base


class Project(Base):
    """
    A project is a container for related memory, decisions, and context.
    
    Projects are isolated - no memory leaks between projects.
    Each project has its own:
    - Memory atoms (decisions, commitments, constraints, etc.)
    - Evidence chunks (chat messages, documents)
    - Ops log (history of operations)
    """
    __tablename__ = "projects"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Profile memory (stable, small)
    user_preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    working_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    general_constraints: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Project state summary
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    architecture: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
    memory_atoms: Mapped[List["MemoryAtom"]] = relationship(
        "MemoryAtom",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    evidence_chunks: Mapped[List["EvidenceChunk"]] = relationship(
        "EvidenceChunk",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    ops_logs: Mapped[List["OpsLog"]] = relationship(
        "OpsLog",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    work_sessions: Mapped[List["WorkSession"]] = relationship(
        "WorkSession",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    reports: Mapped[List["Report"]] = relationship(
        "Report",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"
