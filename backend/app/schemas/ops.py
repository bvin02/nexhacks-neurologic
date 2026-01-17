"""
Ops Log Schemas

Pydantic models for operations log API.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel

from ..models.ops_log import OpType


class OpsLogResponse(BaseModel):
    """Ops log entry."""
    id: str
    project_id: str
    op_type: OpType
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    message: str
    metadata: Optional[str] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


class OpsLogListResponse(BaseModel):
    """List of ops log entries."""
    logs: List[OpsLogResponse]
    total: int
