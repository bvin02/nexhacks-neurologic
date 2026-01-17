"""
Memory Retrieval Pipeline

Two-stage retrieval with scoring and diversity constraints.
"""
import json
import math
import logging
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import numpy as np

from ..models.memory import MemoryAtom, MemoryType, MemoryStatus
from ..models.evidence import EvidenceChunk
from ..llm import get_llm_provider, get_embedding_model

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """
    Two-stage retrieval for memory context.
    
    Stage A: Candidate generation (vector + keyword)
    Stage B: Rerank and select with scoring
    
    Scoring function:
    score = 0.40 * semantic_similarity +
            0.20 * importance +
            0.20 * recency_weight +
            0.10 * confidence +
            0.10 * type_boost
    """
    
    # Type boost values
    TYPE_BOOSTS = {
        MemoryType.COMMITMENT: 1.0,
        MemoryType.CONSTRAINT: 1.0,
        MemoryType.DECISION: 0.9,
        MemoryType.GOAL: 0.8,
        MemoryType.FAILURE: 0.7,
        MemoryType.ASSUMPTION: 0.6,
        MemoryType.PREFERENCE: 0.5,
        MemoryType.BELIEF: 0.4,
        MemoryType.EXCEPTION: 0.3,
    }
    
    # Recency half-life in days
    RECENCY_HALF_LIFE = 30
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
    
    async def _get_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding for query."""
        try:
            embeddings = await self.llm.embed_text(
                [query],
                get_embedding_model()
            )
            return embeddings[0] if embeddings else None
        except Exception as e:
            logger.warning(f"Failed to generate query embedding: {e}")
            return None
    
    def _cosine_similarity(
        self,
        vec_a: List[float],
        vec_b: List[float]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(vec_a)
        b = np.array(vec_b)
        
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(dot / (norm_a * norm_b))
    
    def _recency_weight(self, created_at: datetime) -> float:
        """Calculate recency weight with exponential decay."""
        age_days = (datetime.utcnow() - created_at).days
        return math.exp(-age_days / self.RECENCY_HALF_LIFE)
    
    def _calculate_score(
        self,
        memory: MemoryAtom,
        semantic_similarity: float,
    ) -> float:
        """Calculate final score for a memory."""
        type_boost = self.TYPE_BOOSTS.get(memory.type, 0.5)
        recency = self._recency_weight(memory.created_at)
        
        score = (
            0.40 * semantic_similarity +
            0.20 * memory.importance +
            0.20 * recency +
            0.10 * memory.confidence +
            0.10 * type_boost
        )
        
        # Penalty for disputed memories
        if memory.status == MemoryStatus.DISPUTED:
            score *= 0.7
        
        return score
    
    async def retrieve(
        self,
        project_id: str,
        query: str,
        max_results: int = 20,
        include_disputed: bool = False,
        memory_types: Optional[List[MemoryType]] = None,
    ) -> List[Tuple[MemoryAtom, float]]:
        """
        Retrieve relevant memories for a query.
        
        Args:
            project_id: Project to search in
            query: The query text
            max_results: Maximum memories to return
            include_disputed: Whether to include disputed memories
            memory_types: Filter by memory types
            
        Returns:
            List of (MemoryAtom, score) tuples, sorted by score descending
        """
        # Get query embedding
        query_embedding = await self._get_query_embedding(query)
        
        # Build base query
        stmt = (
            select(MemoryAtom)
            .where(MemoryAtom.project_id == project_id)
            .options(
                selectinload(MemoryAtom.versions),
                selectinload(MemoryAtom.evidence_links),
            )
        )
        
        # Filter by status
        if include_disputed:
            stmt = stmt.where(
                MemoryAtom.status.in_([MemoryStatus.ACTIVE, MemoryStatus.DISPUTED])
            )
        else:
            stmt = stmt.where(MemoryAtom.status == MemoryStatus.ACTIVE)
        
        # Filter by types
        if memory_types:
            stmt = stmt.where(MemoryAtom.type.in_(memory_types))
        
        # Get all candidate memories
        result = await self.db.execute(stmt)
        memories = result.scalars().all()
        
        if not memories:
            return []
        
        # If we have embeddings, score by similarity
        scored_memories: List[Tuple[MemoryAtom, float]] = []
        
        if query_embedding:
            # Get evidence chunks with embeddings for each memory
            for memory in memories:
                # Get linked evidence embeddings
                max_similarity = 0.0
                
                for link in memory.evidence_links:
                    chunk_stmt = select(EvidenceChunk).where(
                        EvidenceChunk.id == link.evidence_id
                    )
                    chunk_result = await self.db.execute(chunk_stmt)
                    chunk = chunk_result.scalar_one_or_none()
                    
                    if chunk and chunk.embedding_vector:
                        try:
                            chunk_embedding = json.loads(chunk.embedding_vector)
                            similarity = self._cosine_similarity(
                                query_embedding,
                                chunk_embedding
                            )
                            max_similarity = max(max_similarity, similarity)
                        except (json.JSONDecodeError, TypeError):
                            pass
                
                # If no evidence embedding, use text similarity heuristic
                if max_similarity == 0.0:
                    # Simple keyword overlap
                    query_words = set(query.lower().split())
                    memory_words = set(memory.canonical_statement.lower().split())
                    overlap = len(query_words & memory_words)
                    max_similarity = min(overlap / max(len(query_words), 1), 1.0)
                
                score = self._calculate_score(memory, max_similarity)
                scored_memories.append((memory, score))
        else:
            # No embedding, use keyword-based scoring
            query_words = set(query.lower().split())
            
            for memory in memories:
                memory_words = set(memory.canonical_statement.lower().split())
                overlap = len(query_words & memory_words)
                similarity = min(overlap / max(len(query_words), 1), 1.0)
                
                score = self._calculate_score(memory, similarity)
                scored_memories.append((memory, score))
        
        # Sort by score descending
        scored_memories.sort(key=lambda x: x[1], reverse=True)
        
        # Apply diversity constraints
        selected = []
        source_counts: dict = {}
        day_counts: dict = {}
        
        for memory, score in scored_memories:
            if len(selected) >= max_results:
                break
            
            # Max 3 per source
            source = None
            if memory.evidence_links:
                source = memory.evidence_links[0].evidence_id
            if source and source_counts.get(source, 0) >= 3:
                continue
            
            # Max 3 per day
            day = memory.created_at.date().isoformat()
            if day_counts.get(day, 0) >= 3:
                continue
            
            selected.append((memory, score))
            if source:
                source_counts[source] = source_counts.get(source, 0) + 1
            day_counts[day] = day_counts.get(day, 0) + 1
        
        return selected
    
    async def build_context_pack(
        self,
        project_id: str,
        query: str,
        max_memories: int = 15,
    ) -> dict:
        """
        Build a context pack for LLM response generation.
        
        Returns a structured context with:
        - Active memories by type
        - Recent episodic events
        - Key citations
        """
        # Get relevant memories
        memories_with_scores = await self.retrieve(
            project_id=project_id,
            query=query,
            max_results=max_memories,
        )
        
        # Group by type
        by_type: dict = {}
        for memory, score in memories_with_scores:
            type_name = memory.type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append({
                "id": memory.id,
                "statement": memory.canonical_statement,
                "importance": memory.importance,
                "confidence": memory.confidence,
                "score": score,
                "created_at": memory.created_at.isoformat(),
            })
        
        # Get commitments and constraints specifically
        commitments = await self.retrieve(
            project_id=project_id,
            query=query,
            max_results=10,
            memory_types=[MemoryType.COMMITMENT, MemoryType.CONSTRAINT],
        )
        
        return {
            "memories_by_type": by_type,
            "commitments": [
                {
                    "id": m.id,
                    "type": m.type.value,
                    "statement": m.canonical_statement,
                }
                for m, _ in commitments
            ],
            "memory_ids": [m.id for m, _ in memories_with_scores],
        }
    
    async def get_commitments_and_constraints(
        self,
        project_id: str,
    ) -> List[MemoryAtom]:
        """Get all active commitments and constraints for enforcement."""
        stmt = (
            select(MemoryAtom)
            .where(
                and_(
                    MemoryAtom.project_id == project_id,
                    MemoryAtom.status == MemoryStatus.ACTIVE,
                    MemoryAtom.type.in_([
                        MemoryType.COMMITMENT,
                        MemoryType.CONSTRAINT,
                    ])
                )
            )
            .options(selectinload(MemoryAtom.versions))
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_decisions(
        self,
        project_id: str,
    ) -> List[MemoryAtom]:
        """Get all active decisions."""
        stmt = (
            select(MemoryAtom)
            .where(
                and_(
                    MemoryAtom.project_id == project_id,
                    MemoryAtom.status == MemoryStatus.ACTIVE,
                    MemoryAtom.type == MemoryType.DECISION,
                )
            )
            .options(selectinload(MemoryAtom.versions))
        )
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
