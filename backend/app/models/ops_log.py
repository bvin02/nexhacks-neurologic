"""
Operations Log Model

Audit log for all memory operations.
Every ingest, dedup, conflict, enforcement, and compaction is logged.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
import enum
import uuid

from ..database import Base


class OpType(str, enum.Enum):
    """Types of operations logged."""
    INGEST = "ingest"
    DEDUP = "dedup"
    CONFLICT = "conflict"
    ENFORCEMENT = "enforcement"
    COMPACTION = "compaction"
    MEMORY_CREATE = "memory_create"
    MEMORY_UPDATE = "memory_update"
    MEMORY_SUPERSEDE = "memory_supersede"
    EXCEPTION_CREATE = "exception_create"
    VIOLATION_DETECTED = "violation_detected"


class OpsLog(Base):
    """
    Audit log for memory operations.
    
    Enables full transparency into what the system is doing.
    Users can see exactly how memory was created, modified, or resolved.
    """
    __tablename__ = "ops_logs"
    
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
    
    op_type: Mapped[OpType] = mapped_column(
        SQLEnum(OpType),
        nullable=False,
        index=True
    )
    
    # Reference to affected entity (memory_id, evidence_id, etc.)
    entity_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        index=True
    )
    entity_type: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True
    )
    
    # Human-readable message
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Additional data as JSON string (can't use 'metadata' - reserved by SQLAlchemy)
    extra_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    
    # Relationship
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="ops_logs"
    )
    
    __table_args__ = (
        Index("idx_ops_project_type", "project_id", "op_type"),
        Index("idx_ops_project_time", "project_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<OpsLog(id={self.id}, type={self.op_type})>"
