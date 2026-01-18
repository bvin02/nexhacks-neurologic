"""
Memory API

Endpoints for memory management.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.memory import MemoryAtom, MemoryVersion, MemoryType, MemoryStatus
from ..models.evidence import MemoryEvidenceLink, EvidenceChunk
from ..schemas.memory import (
    MemoryCreate,
    MemoryResponse,
    MemoryVersionResponse,
    MemoryLedgerResponse,
    ConflictResolution,
    IngestionConflictResolution,
    EvidenceLinkResponse,
    MemoryEdgeResponse,
)
from ..memory.conflict import ConflictDetector

router = APIRouter(prefix="/projects/{project_id}", tags=["memory"])


async def _memory_to_response(
    memory: MemoryAtom,
    db: AsyncSession,
) -> MemoryResponse:
    """Convert MemoryAtom to response schema with related data."""
    # Get versions
    version_stmt = (
        select(MemoryVersion)
        .where(MemoryVersion.memory_id == memory.id)
        .order_by(MemoryVersion.version_number)
    )
    version_result = await db.execute(version_stmt)
    versions = version_result.scalars().all()
    
    # Get evidence links
    link_stmt = (
        select(MemoryEvidenceLink)
        .where(MemoryEvidenceLink.memory_id == memory.id)
    )
    link_result = await db.execute(link_stmt)
    links = link_result.scalars().all()
    
    evidence_responses = []
    for link in links:
        # Get evidence chunk info
        chunk_stmt = select(EvidenceChunk).where(EvidenceChunk.id == link.evidence_id)
        chunk_result = await db.execute(chunk_stmt)
        chunk = chunk_result.scalar_one_or_none()
        
        if chunk:
            evidence_responses.append(EvidenceLinkResponse(
                id=link.id,
                evidence_id=link.evidence_id,
                quote=link.quote,
                confidence=link.confidence,
                source_type=chunk.source_type.value,
                source_ref=chunk.source_ref,
            ))
    
    return MemoryResponse(
        id=memory.id,
        project_id=memory.project_id,
        type=memory.type,
        canonical_statement=memory.canonical_statement,
        conflict_key=memory.conflict_key,
        importance=memory.importance,
        confidence=memory.confidence,
        durability=memory.durability,
        status=memory.status,
        timestamp_start=memory.timestamp_start,
        timestamp_end=memory.timestamp_end,
        entities=memory.entities,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        version_count=len(versions),
        versions=[
            MemoryVersionResponse(
                id=v.id,
                version_number=v.version_number,
                statement=v.statement,
                rationale=v.rationale,
                changed_by=v.changed_by,
                created_at=v.created_at,
            )
            for v in versions
        ],
        evidence_links=evidence_responses,
    )


@router.get("/ledger", response_model=MemoryLedgerResponse)
async def get_ledger(
    project_id: str,
    include_superseded: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the memory ledger for a project.
    
    Returns all memories grouped by type.
    """
    # Build query
    conditions = [MemoryAtom.project_id == project_id]
    if not include_superseded:
        conditions.append(MemoryAtom.status.in_([MemoryStatus.ACTIVE, MemoryStatus.DISPUTED]))
    
    stmt = (
        select(MemoryAtom)
        .where(*conditions)
        .order_by(MemoryAtom.created_at.desc())
    )
    
    result = await db.execute(stmt)
    memories = result.scalars().all()
    
    # Group by type
    ledger = MemoryLedgerResponse()
    type_map = {
        MemoryType.DECISION: "decisions",
        MemoryType.COMMITMENT: "commitments",
        MemoryType.CONSTRAINT: "constraints",
        MemoryType.GOAL: "goals",
        MemoryType.FAILURE: "failures",
        MemoryType.ASSUMPTION: "assumptions",
        MemoryType.EXCEPTION: "exceptions",
        MemoryType.PREFERENCE: "preferences",
        MemoryType.BELIEF: "beliefs",
    }
    
    disputed_count = 0
    active_count = 0
    
    for memory in memories:
        response = await _memory_to_response(memory, db)
        attr = type_map.get(memory.type)
        if attr:
            getattr(ledger, attr).append(response)
        
        if memory.status == MemoryStatus.ACTIVE:
            active_count += 1
        elif memory.status == MemoryStatus.DISPUTED:
            disputed_count += 1
    
    ledger.total_count = len(memories)
    ledger.active_count = active_count
    ledger.disputed_count = disputed_count
    
    return ledger


@router.get("/memory/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    project_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific memory by ID."""
    stmt = select(MemoryAtom).where(
        MemoryAtom.id == memory_id,
        MemoryAtom.project_id == project_id,
    )
    result = await db.execute(stmt)
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    return await _memory_to_response(memory, db)


@router.get("/memory/{memory_id}/versions", response_model=List[MemoryVersionResponse])
async def get_memory_versions(
    project_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all versions of a memory."""
    # Verify memory exists and belongs to project
    mem_stmt = select(MemoryAtom).where(
        MemoryAtom.id == memory_id,
        MemoryAtom.project_id == project_id,
    )
    mem_result = await db.execute(mem_stmt)
    if not mem_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Memory not found")
    
    stmt = (
        select(MemoryVersion)
        .where(MemoryVersion.memory_id == memory_id)
        .order_by(MemoryVersion.version_number)
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()
    
    return [
        MemoryVersionResponse(
            id=v.id,
            version_number=v.version_number,
            statement=v.statement,
            rationale=v.rationale,
            changed_by=v.changed_by,
            created_at=v.created_at,
        )
        for v in versions
    ]


@router.post("/memory/{memory_id}/resolve", response_model=MemoryResponse)
async def resolve_conflict(
    project_id: str,
    memory_id: str,
    data: ConflictResolution,
    db: AsyncSession = Depends(get_db),
):
    """Resolve a memory conflict."""
    # Verify memory exists and is disputed
    stmt = select(MemoryAtom).where(
        MemoryAtom.id == memory_id,
        MemoryAtom.project_id == project_id,
    )
    result = await db.execute(stmt)
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Resolve conflict
    detector = ConflictDetector(db)
    updated = await detector.resolve_conflict(
        memory_id=memory_id,
        action=data.action,
        merged_statement=data.merged_statement,
        rationale=data.rationale,
    )
    
    return await _memory_to_response(updated, db)


@router.post("/memory", response_model=MemoryResponse)
async def create_memory(
    project_id: str,
    data: MemoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Manually create a memory."""
    memory = MemoryAtom(
        project_id=project_id,
        type=data.type,
        canonical_statement=data.canonical_statement,
        conflict_key=data.conflict_key,
        importance=data.importance,
        confidence=data.confidence,
        durability=data.durability,
    )
    db.add(memory)
    await db.flush()
    
    # Create initial version
    version = MemoryVersion(
        memory_id=memory.id,
        version_number=1,
        statement=data.canonical_statement,
        rationale=data.rationale,
        changed_by="user",
    )
    db.add(version)
    
    await db.commit()
    await db.refresh(memory)
    
    return await _memory_to_response(memory, db)


@router.delete("/memory/{memory_id}")
async def delete_memory(
    project_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a memory (actually marks as superseded)."""
    stmt = select(MemoryAtom).where(
        MemoryAtom.id == memory_id,
        MemoryAtom.project_id == project_id,
    )
    result = await db.execute(stmt)
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    
    # Mark as superseded rather than deleting
    memory.status = MemoryStatus.SUPERSEDED
    await db.commit()
    
    return {"status": "superseded", "memory_id": memory_id}


@router.post("/resolve-conflict")
async def resolve_ingestion_conflict(
    project_id: str,
    data: IngestionConflictResolution,
    db: AsyncSession = Depends(get_db),
):
    """
    Resolve a conflict detected during memory ingestion.
    
    The new memory was NOT created yet - it was held pending conflict resolution.
    
    - 'keep': Keep the existing memory, discard the new one entirely
    - 'override': Create the new memory and mark the existing one as disputed
    """
    from ..events import EventPublisher, EventType
    from ..models.memory import MemoryVersion
    
    # Get existing memory
    existing_stmt = select(MemoryAtom).where(
        MemoryAtom.id == data.existing_memory_id,
        MemoryAtom.project_id == project_id,
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()
    
    if not existing:
        raise HTTPException(status_code=404, detail="Existing memory not found")
    
    publisher = EventPublisher()
    # Generate a turn_id for the resolution event
    import uuid
    turn_id = str(uuid.uuid4())[:8]
    
    if data.resolution == 'keep':
        # Keep existing, discard new (it was never created)
        await db.commit()
        
        await publisher.publish(
            project_id=project_id,
            event_type=EventType.CONFLICT_RESOLVED,
            message="Conflict resolved - kept existing",
            turn_id=turn_id,
            data={
                "resolution": "keep",
                "kept_memory_id": str(existing.id),
                "message": "Kept existing memory, new conflicting memory discarded"
            }
        )
        
        return {
            "status": "resolved",
            "resolution": "keep",
            "kept_memory": {
                "id": str(existing.id),
                "statement": existing.canonical_statement
            }
        }
    
    elif data.resolution == 'override':
        # Mark existing as disputed
        existing.status = MemoryStatus.DISPUTED
        
        # NOW create the new memory (it wasn't created before)
        new_memory = MemoryAtom(
            project_id=project_id,
            type=MemoryType(data.new_memory.type),
            canonical_statement=data.new_memory.statement,
            conflict_key=existing.conflict_key,  # Inherit conflict key
            importance=data.new_memory.importance,
            confidence=data.new_memory.confidence,
            status=MemoryStatus.ACTIVE,
        )
        db.add(new_memory)
        await db.flush()
        
        # Create initial version
        version = MemoryVersion(
            memory_id=new_memory.id,
            version_number=1,
            statement=data.new_memory.statement,
            rationale=f"Created via conflict resolution, overriding: {existing.canonical_statement[:100]}",
            changed_by="conflict_resolution",
        )
        db.add(version)
        
        await db.commit()
        await db.refresh(new_memory)
        
        await publisher.publish(
            project_id=project_id,
            event_type=EventType.CONFLICT_RESOLVED,
            message="Conflict resolved - overrode existing",
            turn_id=turn_id,
            data={
                "resolution": "override",
                "disputed_memory_id": str(existing.id),
                "new_memory_id": str(new_memory.id),
                "message": "Created new memory, existing marked as disputed"
            }
        )
        
        return {
            "status": "resolved",
            "resolution": "override",
            "disputed_memory": {
                "id": str(existing.id),
                "statement": existing.canonical_statement
            },
            "new_memory": {
                "id": str(new_memory.id),
                "statement": new_memory.canonical_statement
            }
        }
    
    else:
        raise HTTPException(status_code=400, detail="Invalid resolution. Use 'keep' or 'override'.")
