"""
Chat Schemas

Pydantic models for chat API requests and responses.
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


class ChatMode(BaseModel):
    """Chat mode selector."""
    mode: Literal["fast", "balanced", "thorough"] = "balanced"


class ChatRequest(BaseModel):
    """Request to chat with the project."""
    message: str = Field(..., min_length=1)
    mode: Literal["fast", "balanced", "thorough"] = "balanced"
    
    model_config = {"extra": "forbid"}


class IngestRequest(BaseModel):
    """Request to ingest text or file content."""
    text: Optional[str] = None
    filename: Optional[str] = None
    content: Optional[str] = None  # Base64 encoded file content
    
    model_config = {"extra": "forbid"}


class Citation(BaseModel):
    """Citation to memory or evidence."""
    memory_id: Optional[str] = None
    evidence_id: Optional[str] = None
    quote: str
    type: str  # decision, commitment, constraint, etc.
    timestamp: datetime


class DebugMetadata(BaseModel):
    """Debug metadata attached to responses."""
    memory_used: List[str] = []  # Memory IDs used
    commitments_checked: List[str] = []  # Commitment IDs checked
    violated: bool = False
    violation_details: Optional[str] = None
    citations: List[Citation] = []
    model_tier: str = "mid"
    latency_ms: int = 0
    token_count: int = 0
    
    model_config = {"protected_namespaces": ()}


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    assistant_text: str
    debug: DebugMetadata
    
    # If there was a violation
    violation_challenge: Optional[str] = None
    suggested_actions: List[str] = []  # "revise", "exception", "refuse"
    
    # Memory created from this message
    memories_created: List[str] = []


class TimelineEvent(BaseModel):
    """Event for timeline visualization."""
    id: str
    type: str  # memory_created, conflict_detected, violation, etc.
    timestamp: datetime
    title: str
    description: str
    memory_id: Optional[str] = None
    
    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    """Timeline of project events."""
    events: List[TimelineEvent]
    total: int


# =======================================
# Work Session Schemas
# =======================================

class WorkSessionStartRequest(BaseModel):
    """Request to start a new work session."""
    task_description: str = Field(..., min_length=1)
    
    model_config = {"extra": "forbid"}


class WorkSessionMessageRequest(BaseModel):
    """Request to send a message in a work session."""
    message: str = Field(..., min_length=1)
    mode: Literal["fast", "balanced", "thorough"] = "balanced"
    
    model_config = {"extra": "forbid"}


class WorkSessionEndRequest(BaseModel):
    """Request to end a work session."""
    # Optional summary override (if not provided, will be generated)
    summary: Optional[str] = None
    
    model_config = {"extra": "forbid"}


class WorkSessionInfo(BaseModel):
    """Information about a work session."""
    session_id: str
    project_id: str
    task_description: str
    status: str
    created_at: datetime
    ended_at: Optional[datetime] = None
    message_count: int = 0
    
    model_config = {"from_attributes": True}


class WorkMessageInfo(BaseModel):
    """A message in a work session."""
    id: str
    role: str
    content: str
    created_at: datetime
    
    model_config = {"from_attributes": True}


class WorkSessionStartResponse(BaseModel):
    """Response after starting a work session."""
    session_id: str
    task_description: str
    message: str


class WorkSessionMessageResponse(BaseModel):
    """Response from a work session message."""
    assistant_text: str
    session_id: str
    debug: DebugMetadata
    

class WorkSessionEndResponse(BaseModel):
    """Response after ending a work session."""
    session_id: str
    message: str
    memories_created: int
    memory_ids: List[str]
    summary: str

