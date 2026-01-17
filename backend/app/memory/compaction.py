"""
Memory Compaction Service

Compresses old episodic memories while preserving causal links.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.memory import MemoryAtom, MemoryVersion, MemoryEdge, MemoryType, MemoryStatus
from ..models.ops_log import OpsLog, OpType
from ..llm import get_llm_provider, get_model_for_task

logger = logging.getLogger(__name__)


class CompactionService:
    """
    Memory compaction service.
    
    Triggers:
    - Episodic memory older than 30 days
    - More than 5 versions of the same memory
    
    Process:
    - Summarize episodic memories into milestone memories
    - Preserve temporal ordering
    - Preserve causal links
    - Mark old memories as superseded, not deleted
    """
    
    EPISODIC_AGE_THRESHOLD_DAYS = 30
    VERSION_COUNT_THRESHOLD = 5
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
    
    async def compact_project(self, project_id: str) -> dict:
        """
        Run compaction on a project.
        
        Returns:
            Summary of compaction operations
        """
        stats = {
            "memories_compacted": 0,
            "versions_preserved": 0,
            "milestones_created": 0,
        }
        
        # Find old episodic memories
        cutoff = datetime.utcnow() - timedelta(days=self.EPISODIC_AGE_THRESHOLD_DAYS)
        
        stmt = select(MemoryAtom).where(
            and_(
                MemoryAtom.project_id == project_id,
                MemoryAtom.status == MemoryStatus.ACTIVE,
                MemoryAtom.type.in_([
                    MemoryType.FAILURE,
                    MemoryType.ASSUMPTION,
                ]),
                MemoryAtom.created_at < cutoff,
            )
        )
        
        result = await self.db.execute(stmt)
        old_memories = result.scalars().all()
        
        # Group by conflict key or type
        grouped: dict = {}
        for memory in old_memories:
            key = memory.conflict_key or memory.type.value
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(memory)
        
        # Summarize each group into milestone
        for key, memories in grouped.items():
            if len(memories) < 2:
                continue
            
            # Create summary
            statements = [m.canonical_statement for m in memories]
            summary = await self._summarize_memories(statements)
            
            if not summary:
                continue
            
            # Create milestone memory
            milestone = MemoryAtom(
                project_id=project_id,
                type=memories[0].type,
                canonical_statement=summary,
                conflict_key=key,
                importance=max(m.importance for m in memories),
                confidence=sum(m.confidence for m in memories) / len(memories),
                timestamp_start=min(m.created_at for m in memories),
                timestamp_end=max(m.created_at for m in memories),
            )
            self.db.add(milestone)
            await self.db.flush()
            
            # Create version
            version = MemoryVersion(
                memory_id=milestone.id,
                version_number=1,
                statement=summary,
                rationale=f"Compacted from {len(memories)} memories",
                changed_by="system",
            )
            self.db.add(version)
            
            # Mark old memories as superseded
            for memory in memories:
                memory.status = MemoryStatus.SUPERSEDED
                
                # Create supersedes edge
                edge = MemoryEdge(
                    from_memory_id=milestone.id,
                    to_memory_id=memory.id,
                    relation="supersedes",
                )
                self.db.add(edge)
            
            stats["memories_compacted"] += len(memories)
            stats["milestones_created"] += 1
        
        # Log compaction
        self.db.add(OpsLog(
            project_id=project_id,
            op_type=OpType.COMPACTION,
            message=f"Compacted {stats['memories_compacted']} memories into {stats['milestones_created']} milestones",
            extra_data=json.dumps(stats),
        ))
        
        await self.db.commit()
        return stats
    
    async def _summarize_memories(self, statements: List[str]) -> str:
        """Summarize multiple memory statements into one."""
        prompt = f"""Summarize these related memories into a single concise statement that preserves the key information:

{chr(10).join(f'- {s}' for s in statements)}

Provide a single summary statement."""

        try:
            response = await self.llm.generate_text(
                prompt=prompt,
                model=get_model_for_task("summarization"),
                max_tokens=200,
                temperature=0.3,
            )
            return response.strip()
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            return ""
