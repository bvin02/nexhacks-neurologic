"""
Report API Endpoints

Generate, list, view, rename, and delete reports.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from ..database import get_db
from ..models import Report, WorkSession, WorkMessage
from ..schemas.report import (
    GenerateReportRequest,
    ReportResponse,
    ReportListItem,
    ReportListResponse,
    UpdateReportRequest,
)
from ..llm import get_llm_provider
from ..llm.router import get_model_for_tier, ModelTier
from ..prompts.report import REPORT_GENERATOR_SYSTEM, get_report_generation_prompt
from ..tracer import (
    trace_section, trace_input, trace_parse, trace_step, 
    trace_pass, trace_output, trace_call, trace_result
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/reports/generate", response_model=ReportResponse)
async def generate_report(
    project_id: str,
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a report from a work session conversation."""
    # ── TRACE: Start of report generation ──
    trace_section("Report Generation")
    trace_input("api.reports", "project_id", project_id)
    trace_input("api.reports", "session_id", request.session_id)
    trace_input("api.reports", "name", request.name)
    trace_input("api.reports", "description", request.description)
    
    # Get the work session
    trace_step("api.reports", "Looking up work session in database")
    stmt = select(WorkSession).where(
        WorkSession.id == request.session_id,
        WorkSession.project_id == project_id,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        trace_result("api.reports", "lookup_session", False, "Session not found")
        raise HTTPException(status_code=404, detail="Work session not found")
    
    trace_parse("api.reports", f"Found session: {session.task_description[:50]}...")
    
    # Get conversation messages
    trace_step("api.reports", "Fetching conversation messages")
    msg_stmt = select(WorkMessage).where(
        WorkMessage.session_id == request.session_id
    ).order_by(WorkMessage.created_at)
    msg_result = await db.execute(msg_stmt)
    messages = msg_result.scalars().all()
    
    if not messages:
        trace_result("api.reports", "fetch_messages", False, "No messages found")
        raise HTTPException(status_code=400, detail="No messages in session to generate report from")
    
    trace_parse("api.reports", f"Found {len(messages)} messages in conversation")
    
    # Build conversation history string
    trace_step("api.reports", "Building conversation history")
    conversation_parts = []
    for msg in messages:
        role = "User" if msg.role == "user" else "Assistant"
        conversation_parts.append(f"{role}: {msg.content}")
    
    conversation_history = "\n\n".join(conversation_parts)
    trace_parse("api.reports", f"Conversation history: {len(conversation_history)} chars")
    
    # Generate report via LLM
    trace_step("api.reports", "Preparing LLM call for report generation")
    try:
        llm = get_llm_provider()
        model = get_model_for_tier(ModelTier.MID)
        trace_parse("api.reports", f"Using model: {model}")
        
        user_prompt = get_report_generation_prompt(
            conversation_history=conversation_history,
            file_description=request.description
        )
        trace_parse("api.reports", f"User prompt: {len(user_prompt)} chars")
        
        trace_call("api.reports", "llm.generate_text", f"model={model}, temp=0.3")
        report_content = await llm.generate_text(
            prompt=user_prompt,
            system_prompt=REPORT_GENERATOR_SYSTEM,
            model=model,
            temperature=0.3,  # Lower temperature for consistent output
        )
        trace_result("api.reports", "llm.generate_text", True, f"{len(report_content)} chars generated")
        
    except Exception as e:
        trace_result("api.reports", "llm.complete_text", False, str(e))
        logger.error(f"Failed to generate report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate report")
    
    # Create report record
    trace_step("api.reports", "Creating report record in database")
    report = Report(
        project_id=project_id,
        name=request.name,
        description=request.description,
        content=report_content,
        session_id=request.session_id,
    )
    
    db.add(report)
    await db.commit()
    await db.refresh(report)
    
    trace_output("api.reports", "report_id", report.id)
    trace_output("api.reports", "report_name", report.name)
    trace_result("api.reports", "generate_report", True, f"Report '{report.name}' created")
    
    return ReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        content=report.content,
        session_id=report.session_id,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all reports for a project."""
    trace_section("List Reports")
    trace_input("api.reports", "project_id", project_id)
    
    trace_step("api.reports", "Querying reports from database")
    stmt = select(Report).where(
        Report.project_id == project_id
    ).order_by(Report.created_at.desc())
    
    result = await db.execute(stmt)
    reports = result.scalars().all()
    
    trace_output("api.reports", "report_count", len(reports))
    trace_result("api.reports", "list_reports", True, f"Found {len(reports)} reports")
    
    return ReportListResponse(
        reports=[
            ReportListItem(
                id=r.id,
                name=r.name,
                description=r.description,
                created_at=r.created_at,
            )
            for r in reports
        ],
        total=len(reports),
    )


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific report with content."""
    trace_section("Get Report")
    trace_input("api.reports", "project_id", project_id)
    trace_input("api.reports", "report_id", report_id)
    
    trace_step("api.reports", "Looking up report in database")
    stmt = select(Report).where(
        Report.id == report_id,
        Report.project_id == project_id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        trace_result("api.reports", "get_report", False, "Report not found")
        raise HTTPException(status_code=404, detail="Report not found")
    
    trace_output("api.reports", "report_name", report.name)
    trace_output("api.reports", "content_length", len(report.content))
    trace_result("api.reports", "get_report", True, f"Retrieved '{report.name}'")
    
    return ReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        content=report.content,
        session_id=report.session_id,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.put("/reports/{report_id}", response_model=ReportResponse)
async def update_report(
    project_id: str,
    report_id: str,
    request: UpdateReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update report name or description."""
    trace_section("Update Report")
    trace_input("api.reports", "project_id", project_id)
    trace_input("api.reports", "report_id", report_id)
    trace_input("api.reports", "new_name", request.name)
    trace_input("api.reports", "new_description", request.description)
    
    trace_step("api.reports", "Looking up report in database")
    stmt = select(Report).where(
        Report.id == report_id,
        Report.project_id == project_id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        trace_result("api.reports", "update_report", False, "Report not found")
        raise HTTPException(status_code=404, detail="Report not found")
    
    old_name = report.name
    trace_step("api.reports", f"Updating report '{old_name}'")
    
    if request.name is not None:
        report.name = request.name
        trace_parse("api.reports", f"Name: {old_name} => {request.name}")
    if request.description is not None:
        report.description = request.description
        trace_parse("api.reports", f"Description updated")
    
    await db.commit()
    await db.refresh(report)
    
    trace_result("api.reports", "update_report", True, f"Updated '{report.name}'")
    
    return ReportResponse(
        id=report.id,
        name=report.name,
        description=report.description,
        content=report.content,
        session_id=report.session_id,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.delete("/reports/{report_id}")
async def delete_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a report."""
    trace_section("Delete Report")
    trace_input("api.reports", "project_id", project_id)
    trace_input("api.reports", "report_id", report_id)
    
    trace_step("api.reports", "Looking up report in database")
    stmt = select(Report).where(
        Report.id == report_id,
        Report.project_id == project_id,
    )
    result = await db.execute(stmt)
    report = result.scalar_one_or_none()
    
    if not report:
        trace_result("api.reports", "delete_report", False, "Report not found")
        raise HTTPException(status_code=404, detail="Report not found")
    
    report_name = report.name
    trace_step("api.reports", f"Deleting report '{report_name}'")
    
    await db.delete(report)
    await db.commit()
    
    trace_result("api.reports", "delete_report", True, f"Deleted '{report_name}'")
    
    return {"status": "deleted", "id": report_id}
