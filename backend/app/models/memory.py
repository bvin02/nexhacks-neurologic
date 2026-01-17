"""
Memory Models

Core memory system with typed atoms, versioning, and graph edges.
Memory is the heart of DecisionOS - it governs all future responses.
"""
from datetime import datetime
from sqlalchemy import (
    String, Text, Float, DateTime, Integer, 
    ForeignKey, Enum as SQLEnum, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List
import enum
import uuid

from ..database import Base


class MemoryType(str, enum.Enum):
    """Types of memory atoms."""
    DECISION = "decision"
    COMMITMENT = "commitment"
    CONSTRAINT = "constraint"
    PREFERENCE = "preference"
    GOAL = "goal"
    BELIEF = "belief"
    FAILURE = "failure"
    ASSUMPTION = "assumption"
    EXCEPTION = "exception"


class MemoryDurability(str, enum.Enum):
    """How long memory should persist."""
    EPHEMERAL = "ephemeral"  # Session only
    SESSION = "session"      # Current session
    DURABLE = "durable"      # Permanent


class MemoryStatus(str, enum.Enum):
    """Current status of a memory atom."""
    ACTIVE = "active"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class MemoryRelation(str, enum.Enum):
    """Types of relationships between memories."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    CAUSES = "causes"
    DEPENDS_ON = "depends_on"


class MemoryAtom(Base):
    """
    A single unit of project memory.
    
    Memory atoms are typed (decision, commitment, constraint, etc.)
    and governed (importance, durability, status).
    
    Each atom can have multiple versions as understanding evolves.
    """
    __tablename__ = "memory_atoms"
    
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
    
    # Memory type classification
    type: Mapped[MemoryType] = mapped_column(
        SQLEnum(MemoryType),
        nullable=False,
        index=True
    )
    
    # The core statement
    canonical_statement: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Conflict detection key - memories with same key are checked for conflicts
    conflict_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True
    )
    
    # Governance attributes
    importance: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        nullable=False
    )  # 0.0 to 1.0
    
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.8,
        nullable=False
    )  # 0.0 to 1.0
    
    durability: Mapped[MemoryDurability] = mapped_column(
        SQLEnum(MemoryDurability),
        default=MemoryDurability.DURABLE,
        nullable=False
    )
    
    status: Mapped[MemoryStatus] = mapped_column(
        SQLEnum(MemoryStatus),
        default=MemoryStatus.ACTIVE,
        nullable=False,
        index=True
    )
    
    # Temporal bounds
    timestamp_start: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    timestamp_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    
    # TTL / decay
    ttl_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Entities mentioned (JSON array as string for SQLite)
    entities: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
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
        back_populates="memory_atoms"
    )
    versions: Mapped[List["MemoryVersion"]] = relationship(
        "MemoryVersion",
        back_populates="memory",
        cascade="all, delete-orphan",
        order_by="MemoryVersion.version_number"
    )
    evidence_links: Mapped[List["MemoryEvidenceLink"]] = relationship(
        "MemoryEvidenceLink",
        back_populates="memory",
        cascade="all, delete-orphan"
    )
    
    # Graph edges (outgoing)
    outgoing_edges: Mapped[List["MemoryEdge"]] = relationship(
        "MemoryEdge",
        foreign_keys="MemoryEdge.from_memory_id",
        back_populates="from_memory",
        cascade="all, delete-orphan"
    )
    incoming_edges: Mapped[List["MemoryEdge"]] = relationship(
        "MemoryEdge",
        foreign_keys="MemoryEdge.to_memory_id",
        back_populates="to_memory",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("idx_memory_project_type", "project_id", "type"),
        Index("idx_memory_project_status", "project_id", "status"),
        Index("idx_memory_conflict", "project_id", "conflict_key"),
    )
    
    def __repr__(self) -> str:
        return f"<MemoryAtom(id={self.id}, type={self.type}, status={self.status})>"


class MemoryVersion(Base):
    """
    Version history for memory atoms.
    
    As understanding evolves, memories get new versions.
    This preserves the full history of how decisions changed.
    """
    __tablename__ = "memory_versions"
    
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
    
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    changed_by: Mapped[str] = mapped_column(
        String(50),
        default="user",
        nullable=False
    )  # "user" or "system"
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationship
    memory: Mapped["MemoryAtom"] = relationship(
        "MemoryAtom",
        back_populates="versions"
    )
    
    __table_args__ = (
        Index("idx_version_memory", "memory_id", "version_number"),
    )
    
    def __repr__(self) -> str:
        return f"<MemoryVersion(memory_id={self.memory_id}, version={self.version_number})>"


class MemoryEdge(Base):
    """
    Graph edges between memory atoms.
    
    Edges capture causal and logical relationships:
    - supports: one memory supports another
    - contradicts: memories are in conflict
    - derived_from: memory was inferred from another
    - supersedes: newer memory replaces older
    - causes: causal relationship
    - depends_on: dependency relationship
    """
    __tablename__ = "memory_edges"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    
    from_memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_atoms.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    to_memory_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("memory_atoms.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    relation: Mapped[MemoryRelation] = mapped_column(
        SQLEnum(MemoryRelation),
        nullable=False
    )
    
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    from_memory: Mapped["MemoryAtom"] = relationship(
        "MemoryAtom",
        foreign_keys=[from_memory_id],
        back_populates="outgoing_edges"
    )
    to_memory: Mapped["MemoryAtom"] = relationship(
        "MemoryAtom",
        foreign_keys=[to_memory_id],
        back_populates="incoming_edges"
    )
    
    __table_args__ = (
        Index("idx_edge_relation", "from_memory_id", "to_memory_id", "relation"),
    )
    
    def __repr__(self) -> str:
        return f"<MemoryEdge({self.from_memory_id} -{self.relation}-> {self.to_memory_id})>"
