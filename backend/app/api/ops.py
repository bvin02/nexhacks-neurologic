"""
Ops Log API

Endpoints for operations log.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.ops_log import OpsLog, OpType
from ..schemas.ops import OpsLogResponse, OpsLogListResponse

router = APIRouter(prefix="/projects/{project_id}", tags=["ops"])


@router.get("/ops", response_model=OpsLogListResponse)
async def get_ops_log(
    project_id: str,
    op_type: Optional[str] = Query(None, description="Filter by operation type"),
    limit: int = Query(100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Get operations log for a project.
    
    Returns a history of all memory operations.
    """
    conditions = [OpsLog.project_id == project_id]
    
    if op_type:
        try:
            conditions.append(OpsLog.op_type == OpType(op_type))
        except ValueError:
            pass  # Invalid op_type, ignore filter
    
    stmt = (
        select(OpsLog)
        .where(*conditions)
        .order_by(OpsLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    return OpsLogListResponse(
        logs=[
            OpsLogResponse(
                id=log.id,
                project_id=log.project_id,
                op_type=log.op_type,
                entity_id=log.entity_id,
                entity_type=log.entity_type,
                message=log.message,
                metadata=log.extra_data,
                created_at=log.created_at,
            )
            for log in logs
        ],
        total=len(logs),
    )
