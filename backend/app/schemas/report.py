"""
Report Schemas

Pydantic models for report API requests and responses.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class GenerateReportRequest(BaseModel):
    """Request to generate a report from conversation."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    session_id: str  # Work session to generate report from


class ReportResponse(BaseModel):
    """Report details response."""
    id: str
    name: str
    description: Optional[str]
    content: str
    session_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    """Report item in list view (without full content)."""
    id: str
    name: str
    description: Optional[str]
    created_at: datetime
    
    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    """List of reports."""
    reports: List[ReportListItem]
    total: int


class UpdateReportRequest(BaseModel):
    """Request to update report name/description."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
