"""
Session Summarizer

Extracts durable project memories from work session transcripts.
Used when a work session ends to summarize decisions, constraints, etc.
"""
import logging
from typing import List, Dict, Any

from pydantic import BaseModel

from ..llm import get_llm_provider, get_model_for_task
from ..models.work_session import WorkSession, WorkMessage
from ..tracer import trace_section, trace_input, trace_step, trace_call, trace_result, trace_output

logger = logging.getLogger(__name__)


SUMMARIZER_SYSTEM = """You are a session summarizer for DecisionOS.

Your job is to extract DURABLE project information from a work session transcript.
Focus ONLY on items that should be remembered for the long-term project context.

Types of durable information to extract:
- DECISIONS: Explicit choices made between alternatives (e.g., "We chose React over Vue")
- COMMITMENTS: Promises or binding statements about future behavior (e.g., "We will always use TypeScript")
- CONSTRAINTS: Limitations or requirements that must be respected (e.g., "Database must be PostgreSQL")
- GOALS: Objectives or targets established (e.g., "Launch MVP by Q2")
- FAILURES: Things that were tried and didn't work (e.g., "Redis caching caused race conditions")
- ASSUMPTIONS: Unstated assumptions made explicit (e.g., "Assuming all users have modern browsers")
- ARCHITECTURE: Structural decisions about the system (e.g., "Using microservices for authentication")
- OUTCOMES: What was actually implemented or completed (e.g., "Completed user login module")

DO NOT extract:
- Small talk or greetings
- Temporary debugging steps
- Implementation details that don't affect future decisions
- Speculative ideas that weren't confirmed

Format your output as a structured summary that can be ingested by the memory system."""


SUMMARIZER_PROMPT = """Summarize the following work session transcript to extract durable project information.

Task Description: {task_description}

Session Transcript:
{transcript}

Extract and format durable information as a clear summary document.
Focus on:
1. Key decisions made and their rationale
2. Constraints agreed upon
3. Architecture or design choices
4. Completed outcomes
5. Failures or things to avoid
6. Any commitments for future work

Format as a structured document with clear statements that can be individually tracked.
Each durable statement should be on its own line, prefixed with its type.

Example format:
DECISION: We will use PostgreSQL for the primary database because of better transaction support.
COMMITMENT: All API endpoints will be versioned from v1.
CONSTRAINT: The system must support 1000 concurrent users.
OUTCOME: Completed user authentication module with JWT tokens.
FAILURE: Tried using NoSQL but hit consistency issues; reverted to SQL.

If no durable information was established in this session, return:
NO_DURABLE_MEMORIES: This session contained only implementation work without establishing new decisions or constraints."""


class SessionSummary(BaseModel):
    """Result of summarizing a session."""
    summary: str
    has_durable_memories: bool = True


class SessionSummarizer:
    """
    Summarizes work session transcripts to extract durable memories.
    
    Used when a work session ends to identify what should be
    permanently stored in project memory.
    """
    
    def __init__(self):
        self.llm = get_llm_provider()
    
    def _format_transcript(self, messages: List[WorkMessage]) -> str:
        """Format messages into a readable transcript."""
        trace_step("engine.summarizer", f"Formatting {len(messages)} messages into transcript")
        lines = []
        for msg in messages:
            role_label = "USER" if msg.role == "user" else "ASSISTANT"
            lines.append(f"[{role_label}]: {msg.content}")
        transcript = "\n\n".join(lines)
        trace_output("engine.summarizer", "transcript_length", f"{len(transcript)} chars")
        return transcript
    
    async def summarize_session(
        self,
        session: WorkSession,
        messages: List[WorkMessage],
    ) -> str:
        """
        Generate a summary of durable memories from a session transcript.
        
        Args:
            session: The work session
            messages: List of messages in the session
            
        Returns:
            Summary text suitable for ingestion
        """
        trace_section("Session Summarization")
        trace_input("engine.summarizer", "session_id", session.id)
        trace_input("engine.summarizer", "task", session.task_description)
        trace_input("engine.summarizer", "message_count", len(messages))
        
        if not messages:
            trace_step("engine.summarizer", "Empty session - returning no durable memories")
            return "NO_DURABLE_MEMORIES: Empty session with no messages."
        
        transcript = self._format_transcript(messages)
        
        prompt = SUMMARIZER_PROMPT.format(
            task_description=session.task_description,
            transcript=transcript,
        )
        
        try:
            trace_call("engine.summarizer", "llm.generate_text", "summarization model")
            summary = await self.llm.generate_text(
                prompt=prompt,
                model=get_model_for_task("summarization"),
                system_prompt=SUMMARIZER_SYSTEM,
                max_tokens=2000,
                temperature=0.3,
            )
            trace_result("engine.summarizer", "llm.generate_text", True, summary[:100])
            
            logger.info(f"Generated session summary: {len(summary)} chars")
            trace_output("engine.summarizer", "summary", summary[:100])
            return summary.strip()
            
        except Exception as e:
            trace_result("engine.summarizer", "llm.generate_text", False, str(e))
            logger.error(f"Failed to summarize session: {e}")
            # Fallback: create a simple summary from the task description
            fallback = f"OUTCOME: Work session completed for task: {session.task_description}"
            trace_output("engine.summarizer", "fallback_summary", fallback)
            return fallback
    
    def has_durable_content(self, summary: str) -> bool:
        """Check if summary contains durable memories to ingest."""
        has_durable = "NO_DURABLE_MEMORIES" not in summary
        trace_step("engine.summarizer", f"Has durable content: {has_durable}")
        return has_durable
