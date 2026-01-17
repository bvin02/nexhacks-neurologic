"""
Project Schemas

Pydantic models for project API requests and responses.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """Request to create a new project."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    goal: Optional[str] = None
    
    model_config = {"extra": "forbid"}


class ProjectUpdate(BaseModel):
    """Request to update a project."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    goal: Optional[str] = None
    architecture: Optional[str] = None
    stack: Optional[str] = None
    user_preferences: Optional[str] = None
    working_style: Optional[str] = None
    timezone: Optional[str] = None
    general_constraints: Optional[str] = None
    
    model_config = {"extra": "forbid"}


class ProjectResponse(BaseModel):
    """Project data returned from API."""
    id: str
    name: str
    description: Optional[str] = None
    goal: Optional[str] = None
    architecture: Optional[str] = None
    stack: Optional[str] = None
    user_preferences: Optional[str] = None
    working_style: Optional[str] = None
    timezone: Optional[str] = None
    general_constraints: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Stats
    memory_count: int = 0
    active_memory_count: int = 0
    
    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    """List of projects."""
    projects: list[ProjectResponse]
    total: int
