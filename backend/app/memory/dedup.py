"""
Deduplication Service

Identifies and merges duplicate memories.
"""
import json
import logging
from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from ..models.memory import MemoryAtom, MemoryVersion, MemoryStatus
from ..models.evidence import EvidenceChunk
from ..schemas.memory import MemoryCandidate, DedupResult, MergeResult
from ..llm import get_llm_provider, get_model_for_task, get_embedding_model
from ..prompts.dedup import DEDUP_CLASSIFIER_SYSTEM, DEDUP_CLASSIFIER_PROMPT

logger = logging.getLogger(__name__)


class DeduplicationService:
    """
    Deduplication service for memory atoms.
    
    Duplicate detection:
    1. Cosine similarity >= 0.85
    2. LLM merge classifier confirmation
    """
    
    SIMILARITY_THRESHOLD = 0.85
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
    
    def _cosine_similarity(
        self,
        vec_a: Optional[list[float]],
        vec_b: Optional[list[float]]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        if vec_a is None or vec_b is None:
            return 0.0
        
        a = np.array(vec_a)
        b = np.array(vec_b)
        
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(dot / (norm_a * norm_b))
    
    async def _get_text_embedding(self, text: str) -> Optional[list[float]]:
        """Generate embedding for text."""
        try:
            embeddings = await self.llm.embed_text(
                [text],
                get_embedding_model()
            )
            return embeddings[0] if embeddings else None
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")
            return None
    
    async def _llm_check_duplicate(
        self,
        existing: MemoryAtom,
        candidate: MemoryCandidate,
    ) -> DedupResult:
        """Use LLM to check if memories are duplicates."""
        prompt = DEDUP_CLASSIFIER_PROMPT.format(
            type_a=existing.type.value,
            statement_a=existing.canonical_statement,
            created_a=existing.created_at.isoformat(),
            type_b=candidate.type.value,
            statement_b=candidate.canonical_statement,
        )
        
        try:
            result = await self.llm.extract_json(
                prompt=prompt,
                schema=DedupResult,
                model=get_model_for_task("deduplication"),
                system_prompt=DEDUP_CLASSIFIER_SYSTEM,
            )
            return DedupResult(**result)
        except Exception as e:
            logger.error(f"Dedup classifier failed: {e}")
            return DedupResult(is_duplicate=False, confidence=0.5)
    
    async def check_duplicate(
        self,
        project_id: str,
        candidate: MemoryCandidate,
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Check if a candidate memory is a duplicate of an existing one.
        
        Returns:
            Tuple of (is_duplicate, existing_memory_id, merged_statement, new_details)
        """
        # Get existing memories of the same type
        stmt = select(MemoryAtom).where(
            and_(
                MemoryAtom.project_id == project_id,
                MemoryAtom.type == candidate.type,
                MemoryAtom.status.in_([MemoryStatus.ACTIVE, MemoryStatus.DISPUTED])
            )
        )
        
        result = await self.db.execute(stmt)
        existing_memories = result.scalars().all()
        
        if not existing_memories:
            return False, None, None, None
        
        # Get embedding for candidate
        candidate_embedding = await self._get_text_embedding(
            candidate.canonical_statement
        )
        
        # Check each existing memory
        for existing in existing_memories:
            # Get embedding for existing
            existing_embedding = await self._get_text_embedding(
                existing.canonical_statement
            )
            
            # Check cosine similarity
            similarity = self._cosine_similarity(
                candidate_embedding,
                existing_embedding
            )
            
            if similarity >= self.SIMILARITY_THRESHOLD:
                # High similarity - do LLM merge to get merged statement
                dedup_result = await self._llm_check_duplicate(
                    existing=existing,
                    candidate=candidate,
                )
                return True, existing.id, dedup_result.merged_statement, dedup_result.new_details_found
            
            # If similarity is close, use LLM classifier
            if similarity >= 0.7:
                dedup_result = await self._llm_check_duplicate(
                    existing=existing,
                    candidate=candidate,
                )
                if dedup_result.is_duplicate:
                    return True, existing.id, dedup_result.merged_statement, dedup_result.new_details_found
        
        return False, None, None, None
    
    async def merge_into_existing(
        self,
        memory_id: str,
        candidate: MemoryCandidate,
        merged_statement: Optional[str] = None,
        new_details: Optional[str] = None,
    ) -> MemoryVersion:
        """
        Merge a candidate into an existing memory by creating a new version.
        
        Uses LLM to intelligently merge statements, preserving new details
        from the candidate while keeping the existing memory's core meaning.
        
        Args:
            memory_id: ID of existing memory to update
            candidate: The new candidate to merge
            merged_statement: Pre-computed merged statement (from dedup check)
            new_details: Description of what new details were found
            
        Returns:
            The new MemoryVersion created
        """
        from ..prompts.dedup import MERGE_MEMORIES_SYSTEM, MERGE_MEMORIES_PROMPT
        
        # Get existing memory
        stmt = select(MemoryAtom).where(MemoryAtom.id == memory_id)
        result = await self.db.execute(stmt)
        memory = result.scalar_one()
        
        # Get current version count
        version_stmt = select(MemoryVersion).where(
            MemoryVersion.memory_id == memory_id
        ).order_by(MemoryVersion.version_number.desc())
        version_result = await self.db.execute(version_stmt)
        latest_version = version_result.scalars().first()
        
        new_version_number = (latest_version.version_number + 1) if latest_version else 1
        
        # Determine final statement - use provided merged or do LLM merge
        final_statement = merged_statement
        rationale = "Merged duplicate"
        
        if not final_statement:
            # No pre-computed merge, do LLM merge now
            try:
                merge_prompt = MERGE_MEMORIES_PROMPT.format(
                    existing_statement=memory.canonical_statement,
                    new_statement=candidate.canonical_statement,
                )
                
                merge_result = await self.llm.extract_json(
                    prompt=merge_prompt,
                    schema=MergeResult,
                    model=get_model_for_task("deduplication"),
                    system_prompt=MERGE_MEMORIES_SYSTEM,
                )
                
                final_statement = merge_result.get("merged_statement", candidate.canonical_statement)
                changes = merge_result.get("changes_made", "merged duplicate")
                rationale = f"Merged duplicate: {changes}"
                logger.info(f"LLM merged memories: {changes}")
                
            except Exception as e:
                logger.warning(f"LLM merge failed, using candidate statement: {e}")
                final_statement = candidate.canonical_statement
                rationale = "Merged duplicate (fallback)"
        else:
            if new_details and new_details != "none":
                rationale = f"Merged duplicate: added {new_details}"
        
        # Create new version with merged statement
        version = MemoryVersion(
            memory_id=memory_id,
            version_number=new_version_number,
            statement=final_statement,
            rationale=rationale,
            changed_by="system",
        )
        self.db.add(version)
        
        # Always update the canonical statement with the merged version
        memory.canonical_statement = final_statement
        memory.updated_at = datetime.utcnow()
        
        # Update confidence to max of both
        if candidate.confidence > memory.confidence:
            memory.confidence = candidate.confidence
        
        # Update importance to max of both
        if candidate.importance > memory.importance:
            memory.importance = candidate.importance
        
        await self.db.flush()
        logger.info(f"Merged memory {memory_id}: {final_statement[:50]}...")
        return version

