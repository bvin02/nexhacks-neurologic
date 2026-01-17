"""
Projects API

Endpoints for project management.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.project import Project
from ..models.memory import MemoryAtom, MemoryStatus
from ..schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_response(project: Project, memory_count: int = 0, active_count: int = 0) -> ProjectResponse:
    """Convert Project model to response schema."""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        goal=project.goal,
        architecture=project.architecture,
        stack=project.stack,
        user_preferences=project.user_preferences,
        working_style=project.working_style,
        timezone=project.timezone,
        general_constraints=project.general_constraints,
        created_at=project.created_at,
        updated_at=project.updated_at,
        memory_count=memory_count,
        active_memory_count=active_count,
    )


@router.post("", response_model=ProjectResponse)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new project."""
    project = Project(
        name=data.name,
        description=data.description,
        goal=data.goal,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    
    return _project_to_response(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    db: AsyncSession = Depends(get_db),
):
    """List all projects."""
    stmt = select(Project).order_by(Project.updated_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()
    
    # Get memory counts for each project
    responses = []
    for project in projects:
        count_stmt = select(func.count()).where(MemoryAtom.project_id == project.id)
        count_result = await db.execute(count_stmt)
        memory_count = count_result.scalar() or 0
        
        active_stmt = select(func.count()).where(
            MemoryAtom.project_id == project.id,
            MemoryAtom.status == MemoryStatus.ACTIVE,
        )
        active_result = await db.execute(active_stmt)
        active_count = active_result.scalar() or 0
        
        responses.append(_project_to_response(project, memory_count, active_count))
    
    return ProjectListResponse(
        projects=responses,
        total=len(responses),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a project by ID."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get memory counts
    count_stmt = select(func.count()).where(MemoryAtom.project_id == project_id)
    count_result = await db.execute(count_stmt)
    memory_count = count_result.scalar() or 0
    
    active_stmt = select(func.count()).where(
        MemoryAtom.project_id == project_id,
        MemoryAtom.status == MemoryStatus.ACTIVE,
    )
    active_result = await db.execute(active_stmt)
    active_count = active_result.scalar() or 0
    
    return _project_to_response(project, memory_count, active_count)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a project."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    
    await db.commit()
    await db.refresh(project)
    
    return _project_to_response(project)


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a project and all its data."""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    await db.delete(project)
    await db.commit()
    
    return {"status": "deleted", "project_id": project_id}
