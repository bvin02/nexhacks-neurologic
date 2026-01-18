"""
Work Session API

Endpoints for conversational work chat with session-based memory.
"""
import uuid
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models.project import Project
from ..models.work_session import WorkSession, WorkMessage, SessionStatus
from ..schemas.chat import (
    WorkSessionStartRequest,
    WorkSessionStartResponse,
    WorkSessionMessageRequest,
    WorkSessionMessageResponse,
    WorkSessionEndRequest,
    WorkSessionEndResponse,
    WorkSessionInfo,
    WorkMessageInfo,
    DebugMetadata,
    Citation,
)
from ..memory.retrieval import RetrievalPipeline
from ..memory.ingestion import IngestionPipeline
from ..engine.session_summarizer import SessionSummarizer
from ..llm import get_llm_provider, get_model_for_task
from ..prompts.response import RESPONSE_GENERATOR_SYSTEM
from ..tracer import trace_section, trace_input, trace_parse, trace_step, trace_pass, trace_output, trace_call, trace_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/work", tags=["work"])


# =============================================
# Work Session Endpoints
# =============================================

@router.post("/start", response_model=WorkSessionStartResponse)
async def start_work_session(
    project_id: str,
    data: WorkSessionStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a new work session.
    
    Work sessions have conversation memory within the session
    but do NOT write durable project memories until the session ends.
    """
    # ── TRACE: Start of work session request ──
    trace_section("Work Session Start")
    trace_input("api.work", "task_description", data.task_description)
    trace_input("api.work", "project_id", project_id)
    
    # Verify project exists
    trace_step("api.work", "Looking up project in database")
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    trace_parse("api.work", f"Found project: {project.name}")
    
    # Check for existing active session
    trace_step("api.work", "Checking for existing active session")
    active_stmt = select(WorkSession).where(
        and_(
            WorkSession.project_id == project_id,
            WorkSession.status == SessionStatus.ACTIVE
        )
    )
    active_result = await db.execute(active_stmt)
    active_session = active_result.scalar_one_or_none()
    
    if active_session:
        trace_parse("api.work", f"Active session already exists: {active_session.id}")
        raise HTTPException(
            status_code=400,
            detail=f"An active work session already exists: {active_session.id}"
        )
    
    # Create new session
    trace_step("api.work", "Creating new work session")
    session = WorkSession(
        project_id=project_id,
        task_description=data.task_description,
        status=SessionStatus.ACTIVE,
    )
    db.add(session)
    await db.flush()  # Flush to generate session.id
    
    # Add initial assistant message
    trace_step("api.work", "Adding welcome message to session")
    welcome_msg = WorkMessage(
        session_id=session.id,
        role="assistant",
        content=f"Started work session for: {data.task_description}\n\nI'll help you with this task. Feel free to ask questions, discuss approaches, or work through implementation. When you're done, click 'Task Completed' to save any important decisions or outcomes to project memory.",
    )
    db.add(welcome_msg)
    
    await db.commit()
    
    trace_output("api.work", "session_id", session.id)
    logger.info(f"Started work session {session.id} for project {project_id}")
    
    return WorkSessionStartResponse(
        session_id=session.id,
        task_description=data.task_description,
        message="Work session started. Memories will be saved when you end the session.",
    )


@router.get("/active", response_model=Optional[WorkSessionInfo])
async def get_active_session(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the currently active work session for a project, if any."""
    trace_step("api.work", "Fetching active session for project")
    stmt = (
        select(WorkSession)
        .options(selectinload(WorkSession.messages))
        .where(
            and_(
                WorkSession.project_id == project_id,
                WorkSession.status == SessionStatus.ACTIVE
            )
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        trace_parse("api.work", "No active session found")
        return None
    
    trace_output("api.work", "active_session", session.id)
    return WorkSessionInfo(
        session_id=session.id,
        project_id=session.project_id,
        task_description=session.task_description,
        status=session.status.value,
        created_at=session.created_at,
        ended_at=session.ended_at,
        message_count=len(session.messages),
    )


@router.get("/{session_id}/messages", response_model=List[WorkMessageInfo])
async def get_session_messages(
    project_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a work session."""
    trace_step("api.work", f"Fetching messages for session {session_id}")
    stmt = (
        select(WorkSession)
        .options(selectinload(WorkSession.messages))
        .where(
            and_(
                WorkSession.id == session_id,
                WorkSession.project_id == project_id,
            )
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Work session not found")
    
    trace_output("api.work", "message_count", len(session.messages))
    return [
        WorkMessageInfo(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg in session.messages
    ]


@router.post("/{session_id}/message", response_model=WorkSessionMessageResponse)
async def send_work_message(
    project_id: str,
    session_id: str,
    data: WorkSessionMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message in a work session.
    
    This endpoint:
    1. Stores the user message
    2. Builds conversation history
    3. Retrieves relevant project memories (read-only, for context)
    4. Generates response with full conversation + memory context
    5. Stores the assistant response
    6. Does NOT run ingestion pipeline (memories saved on session end)
    """
    # ── TRACE: Work session message ──
    trace_section("Work Session Message")
    trace_input("api.work", "session_id", session_id)
    trace_input("api.work", "message", data.message)
    trace_input("api.work", "mode", data.mode)
    
    # Get session with messages
    trace_step("api.work", "Loading session and message history")
    stmt = (
        select(WorkSession)
        .options(selectinload(WorkSession.messages))
        .where(
            and_(
                WorkSession.id == session_id,
                WorkSession.project_id == project_id,
                WorkSession.status == SessionStatus.ACTIVE,
            )
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Active work session not found. Start a session first."
        )
    
    trace_parse("api.work", f"Found session for task: {session.task_description}")
    
    # Get project for context
    project_stmt = select(Project).where(Project.id == project_id)
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()
    
    # Store user message
    trace_step("api.work", "Storing user message")
    user_msg = WorkMessage(
        session_id=session_id,
        role="user",
        content=data.message,
    )
    db.add(user_msg)
    await db.flush()
    
    # Build conversation history (last 20 turns or so)
    messages = list(session.messages) + [user_msg]
    recent_messages = messages[-40:]  # Last 20 turns = 40 messages
    trace_parse("api.work", f"Using {len(recent_messages)} messages for context")
    
    conversation_text = []
    for msg in recent_messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        conversation_text.append(f"{role_label}: {msg.content}")
    
    # Retrieve relevant project memories (read-only context)
    trace_section("Memory Retrieval (Read-Only)")
    trace_pass("api.work", "memory.retrieval", "query for context")
    
    retrieval = RetrievalPipeline(db)
    context_pack = await retrieval.build_context_pack(
        project_id=project_id,
        query=data.message,
        max_memories=10,
    )
    
    # Format memory context
    memory_lines = []
    memories_used = []
    for mem_type, mems in context_pack.get("memories_by_type", {}).items():
        for mem in mems:
            memory_lines.append(f"[{mem_type.upper()}] {mem['statement']}")
            memories_used.append(mem['id'])
    
    memory_context = "\n".join(memory_lines) if memory_lines else "No relevant project memories."
    trace_output("memory.retrieval", "memories_found", f"{len(memories_used)} memories")
    
    # Build the LLM prompt
    trace_section("Response Generation")
    trace_step("api.work", "Building LLM prompt with conversation + memory context")
    
    system_prompt = f"""{RESPONSE_GENERATOR_SYSTEM}

You are in a WORK SESSION helping with: {session.task_description}

This is a conversational work chat - you have full context of the conversation history.
Help the user complete their task. Be practical, code-focused, and helpful.
Refer to project memories when relevant but focus on the task at hand."""

    prompt = f"""Project: {project.name}
Goal: {project.goal or 'Not specified'}

Project Memories (for reference):
{memory_context}

Conversation History:
{chr(10).join(conversation_text)}

Respond helpfully to continue the work session. Be practical and focused on the task."""

    # Generate response
    trace_call("api.work", "llm.generate_text", f"mode={data.mode}")
    llm = get_llm_provider()
    assistant_text = await llm.generate_text(
        prompt=prompt,
        model=get_model_for_task("standard_response"),
        system_prompt=system_prompt,
        max_tokens=2000,
        temperature=0.7,
    )
    trace_result("api.work", "llm.generate_text", True, assistant_text[:100])
    
    # Store assistant response
    trace_step("api.work", "Storing assistant response (NO ingestion)")
    assistant_msg = WorkMessage(
        session_id=session_id,
        role="assistant",
        content=assistant_text,
    )
    db.add(assistant_msg)
    await db.commit()
    
    trace_output("api.work", "response", assistant_text[:100])
    logger.info(f"Work session {session_id}: processed message")
    
    return WorkSessionMessageResponse(
        assistant_text=assistant_text,
        session_id=session_id,
        debug=DebugMetadata(
            memory_used=memories_used,
            commitments_checked=[],
            violated=False,
            model_tier="mid",
        ),
    )


@router.post("/{session_id}/end", response_model=WorkSessionEndResponse)
async def end_work_session(
    project_id: str,
    session_id: str,
    data: WorkSessionEndRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    End a work session and ingest durable memories.
    
    This endpoint:
    1. Loads the full session transcript
    2. Generates a summary focused on durable items (decisions, constraints, etc.)
    3. Runs the ingestion pipeline on the summary
    4. Marks the session as completed
    """
    # ── TRACE: End work session ──
    trace_section("Work Session End")
    trace_input("api.work", "session_id", session_id)
    trace_input("api.work", "project_id", project_id)
    
    # Get session with messages
    trace_step("api.work", "Loading session and full transcript")
    stmt = (
        select(WorkSession)
        .options(selectinload(WorkSession.messages))
        .where(
            and_(
                WorkSession.id == session_id,
                WorkSession.project_id == project_id,
                WorkSession.status == SessionStatus.ACTIVE,
            )
        )
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Active work session not found"
        )
    
    trace_parse("api.work", f"Session has {len(session.messages)} messages")
    
    # Get project for context
    project_stmt = select(Project).where(Project.id == project_id)
    project_result = await db.execute(project_stmt)
    project = project_result.scalar_one()
    
    # Generate summary of durable memories
    trace_section("Session Summarization")
    summarizer = SessionSummarizer()
    
    if data.summary:
        trace_step("api.work", "Using provided summary (override)")
        summary = data.summary
    else:
        trace_call("api.work", "session_summarizer.summarize_session")
        summary = await summarizer.summarize_session(
            session=session,
            messages=list(session.messages),
        )
        trace_result("api.work", "session_summarizer.summarize_session", True, summary[:100])
    
    trace_output("api.work", "summary", summary[:100])
    
    # Run ingestion pipeline on the summary
    trace_section("Memory Ingestion")
    memories_created = []
    
    has_durable = summarizer.has_durable_content(summary) if not data.summary else True
    trace_parse("api.work", f"Has durable content: {has_durable}")
    
    if has_durable:
        trace_pass("api.work", "memory.ingestion", "session summary for extraction")
        pipeline = IngestionPipeline(db)
        project_context = f"Project: {project.name}\nGoal: {project.goal or 'Not set'}\nWork Session Task: {session.task_description}"
        
        created = await pipeline.ingest_message(
            project_id=project_id,
            message=summary,
            message_id=f"session-{session_id}",
            project_context=project_context,
        )
        memories_created = [m.id for m in created]
        
        trace_output("memory.ingestion", "memories_created", f"{len(memories_created)} memories")
        logger.info(f"Session {session_id} ended: created {len(memories_created)} memories")
    else:
        trace_step("api.work", "No durable content to ingest")
    
    # Mark session as completed
    trace_step("api.work", "Marking session as completed")
    session.status = SessionStatus.COMPLETED
    session.ended_at = datetime.utcnow()
    await db.commit()
    
    trace_section("Work Session Complete")
    trace_output("api.work", "result", f"Created {len(memories_created)} memories from session")
    
    return WorkSessionEndResponse(
        session_id=session_id,
        message=f"Work session completed. {len(memories_created)} memories created from session.",
        memories_created=len(memories_created),
        memory_ids=memories_created,
        summary=summary[:500] + "..." if len(summary) > 500 else summary,
    )


@router.get("/history", response_model=List[WorkSessionInfo])
async def get_session_history(
    project_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Get history of work sessions for a project."""
    trace_step("api.work", f"Fetching session history for project (limit={limit})")
    stmt = (
        select(WorkSession)
        .options(selectinload(WorkSession.messages))
        .where(WorkSession.project_id == project_id)
        .order_by(WorkSession.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    trace_output("api.work", "sessions_found", len(sessions))
    
    return [
        WorkSessionInfo(
            session_id=s.id,
            project_id=s.project_id,
            task_description=s.task_description,
            status=s.status.value,
            created_at=s.created_at,
            ended_at=s.ended_at,
            message_count=len(s.messages),
        )
        for s in sessions
    ]
