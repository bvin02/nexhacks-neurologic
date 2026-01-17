"""
Reasoning Engine

Generates responses with memory context and debug metadata.
"""
import json
import time
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from ..models.project import Project
from ..models.memory import MemoryAtom
from ..schemas.chat import ChatResponse, DebugMetadata, Citation
from ..llm import get_llm_provider, get_model_for_task, ModelTier
from ..prompts.response import RESPONSE_GENERATOR_SYSTEM, RESPONSE_GENERATOR_PROMPT
from ..memory.retrieval import RetrievalPipeline
from .enforcement import EnforcementEngine, ViolationCheckResult
from .intent_router import IntentRouter, IntentClassification
from ..tracer import trace_step, trace_call, trace_result, trace_pass, trace_parse

logger = logging.getLogger(__name__)


class ResponseResult(BaseModel):
    """Result from response generation."""
    assistant_text: str = ""
    memories_referenced: List[str] = []
    suggested_new_memories: List[dict] = []
    concerns: List[str] = []


class ReasoningEngine:
    """
    Reasoning engine for generating responses.
    
    Process:
    1. Classify intent
    2. Retrieve relevant memory
    3. Check for violations (if needed)
    4. Generate response with context
    5. Attach debug metadata
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
        self.retrieval = RetrievalPipeline(db)
        self.enforcement = EnforcementEngine(db)
        self.intent_router = IntentRouter()
    
    async def _get_project(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        stmt = select(Project).where(Project.id == project_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _format_memory_context(
        self,
        memories_by_type: dict,
    ) -> str:
        """Format memories for prompt injection."""
        lines = []
        
        for type_name, memories in memories_by_type.items():
            if memories:
                lines.append(f"\n## {type_name.upper()}S:")
                for mem in memories[:5]:  # Limit per type
                    lines.append(
                        f"- [{mem['id'][:8]}] {mem['statement']} "
                        f"(importance: {mem['importance']:.1f}, "
                        f"created: {mem['created_at'][:10]})"
                    )
        
        return "\n".join(lines) if lines else "No memories in context."
    
    async def generate_response(
        self,
        project_id: str,
        message: str,
        mode: str = "balanced",
        recent_messages: List[str] = None,
    ) -> ChatResponse:
        """
        Generate a response to a user message.
        
        Args:
            project_id: Project ID
            message: User's message
            mode: Response mode (fast, balanced, thorough)
            recent_messages: Recent conversation for context
            
        Returns:
            ChatResponse with text and debug metadata
        """
        start_time = time.time()
        
        # Get project
        project = await self._get_project(project_id)
        if not project:
            return ChatResponse(
                assistant_text="Project not found.",
                debug=DebugMetadata(),
            )
        
        # Classify intent
        trace_call("engine.reasoning", "IntentRouter.classify")
        intent = await self.intent_router.classify(message)
        trace_result("engine.reasoning", "IntentRouter.classify", True, f"intent={intent.intent}, enforcement={intent.requires_enforcement}")
        
        # Determine tier based on mode
        tier_map = {
            "fast": ModelTier.CHEAP,
            "balanced": ModelTier.MID,
            "thorough": ModelTier.HEAVY,
        }
        tier = tier_map.get(mode, ModelTier.MID)
        trace_parse("engine.reasoning", f"Mode '{mode}' -> tier '{tier.value}'")
        
        # Check for violations if needed
        violation: Optional[ViolationCheckResult] = None
        if intent.requires_enforcement:
            trace_call("engine.reasoning", "EnforcementEngine.check_violation")
            violation = await self.enforcement.check_violation(
                project_id=project_id,
                message=message,
            )
            trace_result("engine.reasoning", "EnforcementEngine.check_violation", True, f"violated={violation.violated}")
            
            if violation.violated and violation.suggested_response == "challenge":
                # Get violated memories for challenge message
                violated_memories = []
                for mem_id in violation.violated_memory_ids:
                    stmt = select(MemoryAtom).where(MemoryAtom.id == mem_id)
                    result = await self.db.execute(stmt)
                    mem = result.scalar_one_or_none()
                    if mem:
                        violated_memories.append(mem)
                
                challenge_message = self.enforcement.format_challenge_message(
                    violation=violation,
                    memories=violated_memories,
                )
                
                latency = int((time.time() - start_time) * 1000)
                
                return ChatResponse(
                    assistant_text=challenge_message,
                    debug=DebugMetadata(
                        memory_used=violation.violated_memory_ids,
                        commitments_checked=violation.violated_memory_ids,
                        violated=True,
                        violation_details=violation.explanation,
                        model_tier=tier.value,
                        latency_ms=latency,
                    ),
                    violation_challenge=violation.explanation,
                    suggested_actions=["revise", "exception", "override"],
                )
        
        # Build context pack
        trace_call("engine.reasoning", "RetrievalPipeline.build_context_pack")
        context_pack = await self.retrieval.build_context_pack(
            project_id=project_id,
            query=message,
        )
        trace_result("engine.reasoning", "RetrievalPipeline.build_context_pack", True, f"{len(context_pack['memory_ids'])} memories retrieved")
        
        memory_context = await self._format_memory_context(
            context_pack["memories_by_type"]
        )
        trace_step("engine.reasoning", f"Formatted memory context ({len(memory_context)} chars)")
        
        # Format recent messages
        recent_text = ""
        if recent_messages:
            recent_text = "\n".join(recent_messages[-5:])
        
        # Generate response
        prompt = RESPONSE_GENERATOR_PROMPT.format(
            project_name=project.name,
            project_goal=project.goal or "Not defined",
            memory_context=memory_context,
            recent_messages=recent_text or "No recent messages.",
            message=message,
        )
        
        try:
            trace_call("engine.reasoning", "LLM.extract_json", f"model={get_model_for_task('standard_response')}")
            result = await self.llm.extract_json(
                prompt=prompt,
                schema=ResponseResult,
                model=get_model_for_task("standard_response"),
                system_prompt=RESPONSE_GENERATOR_SYSTEM,
            )
            response_result = ResponseResult(**result)
            trace_result("engine.reasoning", "LLM.extract_json", True, response_result.assistant_text)
            
        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            # Fallback to simple generation
            try:
                text = await self.llm.generate_text(
                    prompt=f"""Project: {project.name}
Context: {memory_context}
User: {message}

Provide a helpful response:""",
                    model=get_model_for_task("standard_response"),
                    system_prompt=RESPONSE_GENERATOR_SYSTEM,
                )
                response_result = ResponseResult(assistant_text=text)
            except Exception as e2:
                logger.error(f"Fallback generation also failed: {e2}")
                response_result = ResponseResult(
                    assistant_text="I apologize, but I encountered an error generating a response. Please try again."
                )
        
        # Build citations
        citations = []
        for mem_id in response_result.memories_referenced:
            if mem_id in context_pack["memory_ids"]:
                # Find the memory info
                for type_memories in context_pack["memories_by_type"].values():
                    for mem_info in type_memories:
                        if mem_info["id"] == mem_id:
                            citations.append(Citation(
                                memory_id=mem_id,
                                quote=mem_info["statement"][:100],
                                type=list(context_pack["memories_by_type"].keys())[0],
                                timestamp=datetime.fromisoformat(mem_info["created_at"]),
                            ))
                            break
        
        latency = int((time.time() - start_time) * 1000)
        
        return ChatResponse(
            assistant_text=response_result.assistant_text,
            debug=DebugMetadata(
                memory_used=context_pack["memory_ids"],
                commitments_checked=[c["id"] for c in context_pack["commitments"]],
                violated=violation.violated if violation else False,
                citations=citations,
                model_tier=tier.value,
                latency_ms=latency,
            ),
            memories_created=[],  # Will be populated after ingestion
        )
