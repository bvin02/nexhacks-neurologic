"""
Memory Schemas

Pydantic models for memory API requests and responses.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

from ..models.memory import MemoryType, MemoryDurability, MemoryStatus, MemoryRelation


class MemoryCandidate(BaseModel):
    """Memory candidate extracted by LLM."""
    type: MemoryType
    canonical_statement: str
    conflict_key: Optional[str] = None
    importance: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    rationale: Optional[str] = None
    evidence_quote: Optional[str] = None
    entities: List[str] = []


class MemoryCandidateList(BaseModel):
    """List of memory candidates from extraction."""
    candidates: List[MemoryCandidate] = []


class MemoryCreate(BaseModel):
    """Request to manually create a memory."""
    type: MemoryType
    canonical_statement: str = Field(..., min_length=1)
    conflict_key: Optional[str] = None
    importance: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    durability: MemoryDurability = MemoryDurability.DURABLE
    rationale: Optional[str] = None
    
    model_config = {"extra": "forbid"}


class MemoryVersionResponse(BaseModel):
    """Memory version data."""
    id: str
    version_number: int
    statement: str
    rationale: Optional[str] = None
    changed_by: str
    created_at: datetime
    
    model_config = {"from_attributes": True}


class MemoryEdgeResponse(BaseModel):
    """Memory edge data."""
    id: str
    from_memory_id: str
    to_memory_id: str
    relation: MemoryRelation
    confidence: float
    created_at: datetime
    
    model_config = {"from_attributes": True}


class EvidenceLinkResponse(BaseModel):
    """Evidence link data."""
    id: str
    evidence_id: str
    quote: Optional[str] = None
    confidence: float
    source_type: str
    source_ref: str
    
    model_config = {"from_attributes": True}


class MemoryResponse(BaseModel):
    """Memory data returned from API."""
    id: str
    project_id: str
    type: MemoryType
    canonical_statement: str
    conflict_key: Optional[str] = None
    importance: float
    confidence: float
    durability: MemoryDurability
    status: MemoryStatus
    timestamp_start: datetime
    timestamp_end: Optional[datetime] = None
    entities: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Related data
    version_count: int = 0
    versions: List[MemoryVersionResponse] = []
    evidence_links: List[EvidenceLinkResponse] = []
    outgoing_edges: List[MemoryEdgeResponse] = []
    incoming_edges: List[MemoryEdgeResponse] = []
    
    model_config = {"from_attributes": True}


class MemoryLedgerResponse(BaseModel):
    """Memory ledger with grouped memories."""
    decisions: List[MemoryResponse] = []
    commitments: List[MemoryResponse] = []
    constraints: List[MemoryResponse] = []
    goals: List[MemoryResponse] = []
    failures: List[MemoryResponse] = []
    assumptions: List[MemoryResponse] = []
    exceptions: List[MemoryResponse] = []
    preferences: List[MemoryResponse] = []
    beliefs: List[MemoryResponse] = []
    
    total_count: int = 0
    active_count: int = 0
    disputed_count: int = 0


class ConflictResolution(BaseModel):
    """Request to resolve a memory conflict."""
    action: str = Field(..., pattern="^(keep_new|keep_old|keep_both|merge)$")
    merged_statement: Optional[str] = None
    rationale: str
    
    model_config = {"extra": "forbid"}


class NewMemoryData(BaseModel):
    """New memory data for ingestion conflict resolution."""
    type: str = "belief"
    statement: str
    importance: float = 0.5
    confidence: float = 0.8
    durability: str = "session"


class IngestionConflictResolution(BaseModel):
    """Request to resolve a conflict detected during memory ingestion."""
    existing_memory_id: str
    new_memory: NewMemoryData
    resolution: str = Field(..., pattern="^(keep|override)$")
    
    model_config = {"extra": "forbid"}


class DedupResult(BaseModel):
    """Result from deduplication classifier."""
    is_duplicate: bool
    is_contradiction: bool = False  # True if memories contradict (user changed mind)
    merged_statement: Optional[str] = None
    new_details_found: Optional[str] = None  # What new details were integrated
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class ConflictResult(BaseModel):
    """Result from conflict classifier."""
    relation: str = Field(..., pattern="^(consistent|contradiction|refinement)$")
    recommended_action: str
    explanation: str


class MergeResult(BaseModel):
    """Result from memory merge LLM call."""
    merged_statement: str
    changes_made: str
    kept_meaning: bool = True
