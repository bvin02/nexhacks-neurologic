"""
Evidence Models

Evidence chunks are the source material that backs memory.
Every memory should have evidence - this enables "receipts".
"""
from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum
import uuid

from ..database import Base


class SourceType(str, enum.Enum):
    """Types of evidence sources."""
    CHAT = "chat"
    FILE = "file"
    URL = "url"
    MANUAL = "manual"


class EvidenceChunk(Base):
    """
    A chunk of source material that can back memories.
    
    Evidence chunks are created during ingestion (chat or file upload).
    They are embedded for vector similarity search.
    """
    __tablename__ = "evidence_chunks"
    
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
    
    source_type: Mapped[SourceType] = mapped_column(
        SQLEnum(SourceType),
        nullable=False
    )
    source_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )  # message_id, filename, URL
    
    text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Embedding vector stored as JSON string (for SQLite)
    # In production, use pgvector or similar
    embedding_vector: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    
    # Chunk metadata
    chunk_index: Mapped[int] = mapped_column(
        default=0,
        nullable=False
    )
    token_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="evidence_chunks"
    )
    memory_links: Mapped[List["MemoryEvidenceLink"]] = relationship(
        "MemoryEvidenceLink",
        back_populates="evidence",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_evidence_project_source", "project_id", "source_type"),
    )
    
    def __repr__(self) -> str:
        return f"<EvidenceChunk(id={self.id}, source={self.source_type})>"


class MemoryEvidenceLink(Base):
    """
    Links memory atoms to supporting evidence.
    
    Each link includes the specific quote that supports the memory
    and a confidence score for how well it supports.
    """
    __tablename__ = "memory_evidence_links"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_atoms.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    evidence_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evidence_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # The specific quote from evidence that supports memory
    quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # How strongly this evidence supports the memory
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.8,
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    memory: Mapped["MemoryAtom"] = relationship(
        "MemoryAtom",
        back_populates="evidence_links"
    )
    evidence: Mapped["EvidenceChunk"] = relationship(
        "EvidenceChunk",
        back_populates="memory_links"
    )
    
    __table_args__ = (
        Index("idx_link_memory_evidence", "memory_id", "evidence_id"),
    )
    
    def __repr__(self) -> str:
        return f"<MemoryEvidenceLink(memory={self.memory_id}, evidence={self.evidence_id})>"
