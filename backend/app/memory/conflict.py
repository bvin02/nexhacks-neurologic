"""
Conflict Detection Service

Detects contradictions between memories.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.memory import MemoryAtom, MemoryEdge, MemoryRelation, MemoryStatus
from ..schemas.memory import ConflictResult
from ..llm import get_llm_provider, get_model_for_task
from ..prompts.conflict import CONFLICT_CLASSIFIER_SYSTEM, CONFLICT_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)


class ConflictDetector:
    """
    Conflict detection for memory atoms.
    
    Detects contradictions by:
    1. Matching conflict_key
    2. LLM classification of relationship
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
    
    async def _classify_conflict(
        self,
        memory_a: MemoryAtom,
        memory_b: MemoryAtom,
        conflict_key: str,
    ) -> ConflictResult:
        """Use LLM to classify the relationship between memories."""
        prompt = CONFLICT_CLASSIFIER_PROMPT.format(
            type_a=memory_a.type.value,
            statement_a=memory_a.canonical_statement,
            confidence_a=memory_a.confidence,
            created_a=memory_a.created_at.isoformat(),
            type_b=memory_b.type.value,
            statement_b=memory_b.canonical_statement,
            confidence_b=memory_b.confidence,
            created_b=memory_b.created_at.isoformat(),
            conflict_key=conflict_key,
        )
        
        try:
            result = await self.llm.extract_json(
                prompt=prompt,
                schema=ConflictResult,
                model=get_model_for_task("conflict_classification"),
                system_prompt=CONFLICT_CLASSIFIER_SYSTEM,
            )
            return ConflictResult(**result)
        except Exception as e:
            logger.error(f"Conflict classifier failed: {e}")
            return ConflictResult(
                relation="consistent",
                recommended_action="none",
                explanation="Classification failed"
            )
    
    async def detect_conflicts(
        self,
        project_id: str,
        memory: MemoryAtom,
    ) -> List[dict]:
        """
        Detect conflicts between a new memory and existing memories.
        
        Args:
            project_id: Project ID
            memory: The new memory to check
            
        Returns:
            List of conflict records
        """
        if not memory.conflict_key:
            return []
        
        # Find other memories with the same conflict key
        stmt = select(MemoryAtom).where(
            and_(
                MemoryAtom.project_id == project_id,
                MemoryAtom.conflict_key == memory.conflict_key,
                MemoryAtom.id != memory.id,
                MemoryAtom.status == MemoryStatus.ACTIVE,
            )
        )
        
        result = await self.db.execute(stmt)
        existing_memories = result.scalars().all()
        
        conflicts = []
        
        for existing in existing_memories:
            # Classify the relationship
            classification = await self._classify_conflict(
                memory_a=existing,
                memory_b=memory,
                conflict_key=memory.conflict_key,
            )
            
            if classification.relation == "contradiction":
                # Create conflict edge
                edge = MemoryEdge(
                    from_memory_id=memory.id,
                    to_memory_id=existing.id,
                    relation=MemoryRelation.CONTRADICTS,
                    confidence=0.9,
                )
                self.db.add(edge)
                
                # Mark both as disputed based on action
                if classification.recommended_action == "mark_disputed":
                    memory.status = MemoryStatus.DISPUTED
                    existing.status = MemoryStatus.DISPUTED
                elif classification.recommended_action == "prefer_newer":
                    existing.status = MemoryStatus.SUPERSEDED
                    # Add supersedes edge
                    supersede_edge = MemoryEdge(
                        from_memory_id=memory.id,
                        to_memory_id=existing.id,
                        relation=MemoryRelation.SUPERSEDES,
                    )
                    self.db.add(supersede_edge)
                elif classification.recommended_action == "prefer_higher_confidence":
                    if memory.confidence > existing.confidence:
                        existing.status = MemoryStatus.SUPERSEDED
                    else:
                        memory.status = MemoryStatus.SUPERSEDED
                
                conflicts.append({
                    "other_id": existing.id,
                    "other_statement": existing.canonical_statement,
                    "relation": classification.relation,
                    "action": classification.recommended_action,
                    "explanation": classification.explanation,
                })
            
            elif classification.relation == "refinement":
                # Create derived_from edge
                edge = MemoryEdge(
                    from_memory_id=memory.id,
                    to_memory_id=existing.id,
                    relation=MemoryRelation.DERIVED_FROM,
                )
                self.db.add(edge)
        
        await self.db.flush()
        return conflicts
    
    async def resolve_conflict(
        self,
        memory_id: str,
        action: str,
        merged_statement: Optional[str] = None,
        rationale: str = "",
    ) -> MemoryAtom:
        """
        Resolve a memory conflict.
        
        Args:
            memory_id: ID of the memory to update
            action: Resolution action (keep_new, keep_old, keep_both, merge)
            merged_statement: New statement if merging
            rationale: Reason for resolution
            
        Returns:
            Updated MemoryAtom
        """
        stmt = select(MemoryAtom).where(MemoryAtom.id == memory_id)
        result = await self.db.execute(stmt)
        memory = result.scalar_one()
        
        if action == "keep_new":
            # Keep this one active, supersede others
            edge_stmt = select(MemoryEdge).where(
                and_(
                    MemoryEdge.from_memory_id == memory_id,
                    MemoryEdge.relation == MemoryRelation.CONTRADICTS,
                )
            )
            edge_result = await self.db.execute(edge_stmt)
            edges = edge_result.scalars().all()
            
            for edge in edges:
                other_stmt = select(MemoryAtom).where(
                    MemoryAtom.id == edge.to_memory_id
                )
                other_result = await self.db.execute(other_stmt)
                other = other_result.scalar_one()
                other.status = MemoryStatus.SUPERSEDED
            
            memory.status = MemoryStatus.ACTIVE
            
        elif action == "keep_old":
            # Supersede this one
            memory.status = MemoryStatus.SUPERSEDED
            
        elif action == "keep_both":
            # Mark both as active (agree to disagree)
            memory.status = MemoryStatus.ACTIVE
            
        elif action == "merge" and merged_statement:
            # Update statement and mark as active
            from ..models.memory import MemoryVersion
            
            version = MemoryVersion(
                memory_id=memory_id,
                version_number=(len(memory.versions) + 1) if hasattr(memory, 'versions') else 1,
                statement=merged_statement,
                rationale=rationale,
                changed_by="user",
            )
            self.db.add(version)
            
            memory.canonical_statement = merged_statement
            memory.status = MemoryStatus.ACTIVE
        
        memory.updated_at = datetime.utcnow()
        await self.db.commit()
        return memory
