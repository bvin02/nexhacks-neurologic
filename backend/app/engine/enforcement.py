"""
Enforcement Engine

Checks for violations against commitments and constraints.
Challenges violations with citations and offers resolution paths.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ..models.memory import MemoryAtom, MemoryType, MemoryStatus
from ..models.ops_log import OpsLog, OpType
from ..llm import get_llm_provider, get_model_for_task
from ..prompts.enforcement import VIOLATION_CHECKER_SYSTEM, VIOLATION_CHECKER_PROMPT
from ..memory.retrieval import RetrievalPipeline

logger = logging.getLogger(__name__)


class ViolationCheckResult(BaseModel):
    """Result from violation checking."""
    violated: bool = False
    violated_memory_ids: List[str] = []
    explanation: str = ""
    severity: str = "low"  # high, medium, low
    suggested_response: str = "allow"  # challenge, warn, allow
    challenge_message: Optional[str] = None


class EnforcementEngine:
    """
    Enforcement engine for commitment and constraint checking.
    
    Before responding:
    1. Get active commitments and constraints
    2. Check if proposed action violates any
    3. If violation: challenge with citation
    4. Offer paths: revise, exception, or refuse
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
        self.retrieval = RetrievalPipeline(db)
    
    async def check_violation(
        self,
        project_id: str,
        message: str,
    ) -> ViolationCheckResult:
        """
        Check if a user message implies a violation.
        
        Args:
            project_id: Project to check against
            message: User's message
            
        Returns:
            ViolationCheckResult with violation details
        """
        # Get commitments, constraints, and decisions
        commitments = await self.retrieval.get_commitments_and_constraints(project_id)
        decisions = await self.retrieval.get_decisions(project_id)
        
        if not commitments and not decisions:
            return ViolationCheckResult(violated=False)
        
        # Format for prompt
        commitment_text = "\n".join([
            f"[{c.id}] {c.type.value.upper()}: {c.canonical_statement}"
            for c in commitments
        ]) or "No active commitments or constraints."
        
        constraint_text = "\n".join([
            f"[{c.id}] {c.canonical_statement}"
            for c in commitments if c.type == MemoryType.CONSTRAINT
        ]) or "No active constraints."
        
        decision_text = "\n".join([
            f"[{d.id}] {d.canonical_statement}"
            for d in decisions
        ]) or "No active decisions."
        
        prompt = VIOLATION_CHECKER_PROMPT.format(
            message=message,
            commitments=commitment_text,
            constraints=constraint_text,
            decisions=decision_text,
        )
        
        try:
            result = await self.llm.extract_json(
                prompt=prompt,
                schema=ViolationCheckResult,
                model=get_model_for_task("enforcement_reasoning"),
                system_prompt=VIOLATION_CHECKER_SYSTEM,
            )
            
            check_result = ViolationCheckResult(**result)
            
            # Log violation if detected
            if check_result.violated:
                self.db.add(OpsLog(
                    project_id=project_id,
                    op_type=OpType.VIOLATION_DETECTED,
                    entity_id=",".join(check_result.violated_memory_ids),
                    entity_type="memory",
                    message=check_result.explanation,
                    extra_data=json.dumps({
                        "severity": check_result.severity,
                        "response": check_result.suggested_response,
                    }),
                ))
                await self.db.flush()
            
            return check_result
            
        except Exception as e:
            logger.error(f"Violation check failed: {e}")
            return ViolationCheckResult(violated=False)
    
    async def create_exception(
        self,
        project_id: str,
        violated_memory_id: str,
        reason: str,
        scope: str = "this_instance",
        duration_days: Optional[int] = None,
    ) -> MemoryAtom:
        """
        Create an exception to a commitment or constraint.
        
        Exceptions are:
        - Scoped (this_instance, this_session, permanent)
        - Time-bounded (optional duration)
        - Linked to the original commitment
        
        Args:
            project_id: Project ID
            violated_memory_id: ID of the memory being excepted
            reason: Reason for the exception
            scope: Scope of exception
            duration_days: Optional duration in days
            
        Returns:
            Created exception MemoryAtom
        """
        from ..models.memory import MemoryEdge, MemoryRelation, MemoryVersion, MemoryDurability
        
        # Get the violated memory
        from sqlalchemy import select
        stmt = select(MemoryAtom).where(MemoryAtom.id == violated_memory_id)
        result = await self.db.execute(stmt)
        violated_memory = result.scalar_one()
        
        # Create exception memory
        exception = MemoryAtom(
            project_id=project_id,
            type=MemoryType.EXCEPTION,
            canonical_statement=f"Exception to '{violated_memory.canonical_statement[:100]}...': {reason}",
            conflict_key=violated_memory.conflict_key,
            importance=violated_memory.importance,
            confidence=0.9,
            durability=(
                MemoryDurability.EPHEMERAL if scope == "this_instance"
                else MemoryDurability.SESSION if scope == "this_session"
                else MemoryDurability.DURABLE
            ),
            ttl_days=duration_days,
        )
        self.db.add(exception)
        await self.db.flush()
        
        # Create version
        version = MemoryVersion(
            memory_id=exception.id,
            version_number=1,
            statement=exception.canonical_statement,
            rationale=reason,
            changed_by="user",
        )
        self.db.add(version)
        
        # Link to violated memory
        edge = MemoryEdge(
            from_memory_id=exception.id,
            to_memory_id=violated_memory_id,
            relation=MemoryRelation.DERIVED_FROM,
        )
        self.db.add(edge)
        
        # Log exception creation
        self.db.add(OpsLog(
            project_id=project_id,
            op_type=OpType.EXCEPTION_CREATE,
            entity_id=exception.id,
            entity_type="memory",
            message=f"Exception created: {reason}",
            extra_data=json.dumps({
                "violated_memory_id": violated_memory_id,
                "scope": scope,
                "duration_days": duration_days,
            }),
        ))
        
        await self.db.commit()
        return exception
    
    def format_challenge_message(
        self,
        violation: ViolationCheckResult,
        memories: List[MemoryAtom],
    ) -> str:
        """Format a challenge message with citations."""
        if not violation.violated:
            return ""
        
        memory_map = {m.id: m for m in memories}
        
        citations = []
        for mem_id in violation.violated_memory_ids:
            if mem_id in memory_map:
                mem = memory_map[mem_id]
                citations.append(
                    f"- **{mem.type.value.upper()}** (created {mem.created_at.strftime('%Y-%m-%d')}): "
                    f"\"{mem.canonical_statement}\""
                )
        
        challenge = f"""**This appears to conflict with existing commitments:**

{violation.explanation}

**Relevant memories:**
{chr(10).join(citations)}

**Options:**
1. **Revise** your request to align with existing commitments
2. **Create an exception** for this specific case
3. **Override** the commitment (this will supersede it)

How would you like to proceed?"""
        
        return challenge
