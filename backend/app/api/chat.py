"""
Chat API

Endpoints for chat and ingestion.
"""
import uuid
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.project import Project
from ..models.memory import MemoryAtom
from ..models.ops_log import OpsLog
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
    IngestRequest,
    TimelineEvent,
    TimelineResponse,
)
from ..memory.ingestion import IngestionPipeline
from ..engine.reasoning import ReasoningEngine
from ..events import get_event_publisher, EventType
from ..tracer import trace_section, trace_input, trace_parse, trace_step, trace_pass, trace_output

router = APIRouter(prefix="/projects/{project_id}", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    project_id: str,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Chat with a project.
    
    This endpoint:
    1. Classifies intent
    2. Retrieves relevant memory
    3. Checks for violations
    4. Generates response
    5. Ingests new memories from the message
    """
    # Generate turn ID for grouping events
    turn_id = str(uuid.uuid4())[:8]
    publisher = get_event_publisher()
    
    # -- TRACE: Start of chat request --
    trace_section("Chat Request")
    trace_input("api.chat", "message", data.message)
    trace_input("api.chat", "mode", data.mode)
    trace_input("api.chat", "project_id", project_id)
    
    # Verify project exists
    trace_step("api.chat", "Looking up project in database")
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    trace_parse("api.chat", f"Found project: {project.name}")
    
    # Generate response (events are published inside reasoning engine)
    trace_section("Response Generation")
    trace_pass("api.chat", "engine.reasoning", "message + mode")
    
    engine = ReasoningEngine(db)
    response = await engine.generate_response(
        project_id=project_id,
        message=data.message,
        mode=data.mode,
        turn_id=turn_id,  # Pass turn_id for event publishing
    )
    
    trace_output("engine.reasoning", "response", response.assistant_text)
    
    # Ingest message for memory extraction (events are published inside ingestion pipeline)
    trace_section("Memory Ingestion")
    trace_pass("api.chat", "memory.ingestion", "message for extraction")
    
    pipeline = IngestionPipeline(db)
    message_id = str(uuid.uuid4())
    
    project_context = f"Project: {project.name}\nGoal: {project.goal or 'Not set'}"
    
    created_memories = await pipeline.ingest_message(
        project_id=project_id,
        message=data.message,
        message_id=message_id,
        project_context=project_context,
        turn_id=turn_id,  # Pass turn_id for event publishing
    )
    
    trace_output("memory.ingestion", "memories_created", f"{len(created_memories)} memories")
    
    # Update response with created memories
    response.memories_created = [m.id for m in created_memories]
    
    # Publish: complete with memory IDs for citation pills
    await publisher.publish(
        project_id, EventType.COMPLETE, "Complete", turn_id,
        data={"memory_ids": [m.id for m in created_memories]}
    )
    
    trace_section("Chat Complete")
    trace_output("api.chat", "final_response", response.assistant_text)
    
    return response


@router.post("/ingest")
async def ingest(
    project_id: str,
    data: IngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest text or file content into project memory.
    """
    # Verify project exists
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    pipeline = IngestionPipeline(db)
    project_context = f"Project: {project.name}\nGoal: {project.goal or 'Not set'}"
    
    if data.text:
        # Ingest raw text
        message_id = str(uuid.uuid4())
        memories = await pipeline.ingest_message(
            project_id=project_id,
            message=data.text,
            message_id=message_id,
            project_context=project_context,
        )
        return {
            "status": "success",
            "memories_created": len(memories),
            "memory_ids": [m.id for m in memories],
        }
    
    elif data.filename and data.content:
        # Ingest file content
        import base64
        try:
            content = base64.b64decode(data.content).decode("utf-8")
        except Exception:
            content = data.content  # Assume plain text if not base64
        
        memories = await pipeline.ingest_document(
            project_id=project_id,
            content=content,
            filename=data.filename,
            project_context=project_context,
        )
        return {
            "status": "success",
            "memories_created": len(memories),
            "memory_ids": [m.id for m in memories],
        }
    
    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'text' or both 'filename' and 'content' must be provided"
        )


@router.get("/timeline", response_model=TimelineResponse)
async def get_timeline(
    project_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """
    Get timeline of project events.
    
    Events include memory creation, conflicts, violations, etc.
    """
    # Get ops logs
    stmt = (
        select(OpsLog)
        .where(OpsLog.project_id == project_id)
        .order_by(OpsLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()
    
    events = []
    for log in logs:
        event_type = log.op_type.value
        
        # Format title based on type
        title_map = {
            "memory_create": "Memory Created",
            "ingest": "Content Ingested",
            "dedup": "Duplicate Merged",
            "conflict": "Conflict Detected",
            "violation_detected": "Violation Detected",
            "exception_create": "Exception Created",
            "enforcement": "Enforcement Check",
            "compaction": "Memory Compacted",
        }
        
        events.append(TimelineEvent(
            id=log.id,
            type=event_type,
            timestamp=log.created_at,
            title=title_map.get(event_type, event_type.replace("_", " ").title()),
            description=log.message,
            memory_id=log.entity_id if log.entity_type == "memory" else None,
        ))
    
    return TimelineResponse(
        events=events,
        total=len(events),
    )
