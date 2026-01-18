"""
Memory Ingestion Pipeline

Processes messages and documents to extract and store memories.
Runs on every chat turn and file upload.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List
import tiktoken

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.memory import MemoryAtom, MemoryVersion, MemoryType, MemoryStatus
from ..models.evidence import EvidenceChunk, MemoryEvidenceLink, SourceType
from ..models.ops_log import OpsLog, OpType
from ..schemas.memory import MemoryCandidate, MemoryCandidateList
from ..llm import get_llm_provider, get_model_for_task, get_embedding_model
from ..prompts.extractor import MEMORY_EXTRACTOR_SYSTEM, MEMORY_EXTRACTOR_PROMPT
from .dedup import DeduplicationService
from .conflict import ConflictDetector
from ..tracer import trace_step, trace_call, trace_result, trace_parse

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Ingestion pipeline for processing messages into memories.
    
    Steps:
    1. Chunk text (500 tokens, 50 overlap)
    2. Generate embeddings
    3. Extract memory candidates (LLM)
    4. Apply write gate (filter)
    5. Deduplicate
    6. Detect conflicts
    7. Persist
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = get_llm_provider()
        self.dedup = DeduplicationService(db)
        self.conflict = ConflictDetector(db)
        
        # Token counter - DISABLED: tiktoken causes blocking on first use
        # TODO: Re-enable after fixing the async issue
        self.encoder = None  # Disabled for now
        # try:
        #     self.encoder = tiktoken.get_encoding("cl100k_base")
        # except Exception:
        #     self.encoder = None
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoder:
            return len(self.encoder.encode(text))
        return len(text) // 4  # Rough estimate
    
    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50
    ) -> List[str]:
        """Split text into overlapping chunks."""
        if self.encoder:
            tokens = self.encoder.encode(text)
            chunks = []
            start = 0
            while start < len(tokens):
                end = min(start + chunk_size, len(tokens))
                chunk_tokens = tokens[start:end]
                chunks.append(self.encoder.decode(chunk_tokens))
                if end >= len(tokens):
                    break
                start = end - overlap
            return chunks
        else:
            # Fallback: character-based chunking
            char_size = chunk_size * 4  # ~2000 chars
            char_overlap = overlap * 4   # ~200 chars
            chunks = []
            start = 0
            while start < len(text):
                end = min(start + char_size, len(text))
                chunks.append(text[start:end])
                if end >= len(text):
                    break  # We've reached the end
                start = end - char_overlap
                if start <= 0:
                    break  # Prevent infinite loop for small texts
            return chunks if chunks else [text]  # Return at least the original text
    
    async def _create_evidence_chunks(
        self,
        project_id: str,
        text: str,
        source_type: SourceType,
        source_ref: str,
    ) -> List[EvidenceChunk]:
        """Create and store evidence chunks with embeddings."""
        
        # Use print for immediate output (no buffering)
        print(f"[TRACE] _create_evidence_chunks: Starting with {len(text)} chars", flush=True)
        
        trace_step("memory.ingestion", f"Chunking text ({len(text)} chars)")
        
        # Call directly - no async needed since tiktoken is disabled
        print("[TRACE] About to call _chunk_text...", flush=True)
        chunks_text = self._chunk_text(text)  # Direct call, no asyncio.to_thread
        print(f"[TRACE] _chunk_text returned {len(chunks_text)} chunks", flush=True)
        
        chunks = []
        
        trace_step("memory.ingestion", f"Created {len(chunks_text)} text chunks")
        
        # Generate embeddings for all chunks
        if chunks_text:
            try:
                print(f"[TRACE] About to call embed_text for {len(chunks_text)} chunks...", flush=True)
                trace_step("memory.ingestion", f"Calling embed_text for {len(chunks_text)} chunks...")
                embeddings = await self.llm.embed_text(
                    chunks_text,
                    get_embedding_model()
                )
                print(f"[TRACE] embed_text returned {len(embeddings)} embeddings", flush=True)
                trace_step("memory.ingestion", f"Embeddings received: {len(embeddings)}")
            except Exception as e:
                print(f"[TRACE] embed_text FAILED: {e}", flush=True)
                logger.warning(f"Failed to generate embeddings: {e}")
                trace_step("memory.ingestion", f"Embedding failed: {e}")
                embeddings = [None] * len(chunks_text)
        else:
            embeddings = []
        
        trace_step("memory.ingestion", "Creating EvidenceChunk records")
        for i, (chunk_text, embedding) in enumerate(zip(chunks_text, embeddings)):
            chunk = EvidenceChunk(
                project_id=project_id,
                source_type=source_type,
                source_ref=source_ref,
                text=chunk_text,
                embedding_vector=json.dumps(embedding) if embedding else None,
                chunk_index=i,
                token_count=self._count_tokens(chunk_text),
            )
            self.db.add(chunk)
            chunks.append(chunk)
        
        trace_step("memory.ingestion", "Flushing to database")
        await self.db.flush()
        print(f"[TRACE] _create_evidence_chunks: Done, returning {len(chunks)} chunks", flush=True)
        trace_result("memory.ingestion", "_create_evidence_chunks", True, f"{len(chunks)} chunks")
        return chunks
    
    async def _extract_memory_candidates(
        self,
        message: str,
        project_context: str,
    ) -> List[MemoryCandidate]:
        """Use LLM to extract memory candidates from message."""
        prompt = MEMORY_EXTRACTOR_PROMPT.format(
            project_context=project_context,
            message=message,
        )
        
        try:
            result = await self.llm.extract_json(
                prompt=prompt,
                schema=MemoryCandidateList,
                model=get_model_for_task("memory_extraction"),
                system_prompt=MEMORY_EXTRACTOR_SYSTEM,
            )
            return [MemoryCandidate(**c) for c in result.get("candidates", [])]
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return []
    
    def _apply_write_gate(
        self,
        candidates: List[MemoryCandidate]
    ) -> List[MemoryCandidate]:
        """Filter candidates through write gate."""
        passed = []
        for candidate in candidates:
            # Importance threshold
            if candidate.importance < 0.4:
                continue
            
            # Statement length check (not too short)
            if len(candidate.canonical_statement) < 10:
                continue
            
            # Statement length check (not too long)
            if len(candidate.canonical_statement) > 500:
                continue
            
            passed.append(candidate)
        
        return passed
    
    async def ingest_message(
        self,
        project_id: str,
        message: str,
        message_id: str,
        project_context: str = "",
        turn_id: str = None,
    ) -> List[MemoryAtom]:
        """
        Ingest a chat message.
        
        Args:
            project_id: Project to ingest into
            message: The message text
            message_id: Unique ID for this message
            project_context: Optional project context for extraction
            turn_id: Optional turn ID for event publishing
            
        Returns:
            List of created MemoryAtom objects
        """
        from ..events import get_event_publisher, EventType
        publisher = get_event_publisher()
        
        created_memories = []
        
        # Step 1: Create evidence chunks
        trace_call("memory.ingestion", "_create_evidence_chunks")
        chunks = await self._create_evidence_chunks(
            project_id=project_id,
            text=message,
            source_type=SourceType.CHAT,
            source_ref=message_id,
        )
        trace_result("memory.ingestion", "_create_evidence_chunks", True, f"{len(chunks)} chunks")
        
        # Log ingestion op
        self.db.add(OpsLog(
            project_id=project_id,
            op_type=OpType.INGEST,
            entity_id=message_id,
            entity_type="message",
            message=f"Ingested message with {len(chunks)} chunks",
        ))
        
        # Step 2: Extract memory candidates
        # Publish: extracting (before LLM call)
        if turn_id:
            await publisher.publish(
                project_id, EventType.EXTRACTING,
                "Extracting memory candidates...", turn_id
            )
        
        trace_call("memory.ingestion", "_extract_memory_candidates (LLM)")
        candidates = await self._extract_memory_candidates(
            message=message,
            project_context=project_context,
        )
        trace_result("memory.ingestion", "_extract_memory_candidates", True, f"{len(candidates)} candidates")
        
        # Publish: candidates created with previews
        if turn_id and candidates:
            candidate_previews = [
                {
                    "type": c.type.value,
                    "preview": c.canonical_statement[:50] + "..." if len(c.canonical_statement) > 50 else c.canonical_statement,
                    "importance": c.importance
                }
                for c in candidates[:3]  # Top 3 previews
            ]
            await publisher.publish(
                project_id, EventType.CANDIDATES_CREATED,
                f"{len(candidates)} memory candidates extracted", turn_id,
                data={"count": len(candidates), "previews": candidate_previews}
            )
        
        # Step 3: Apply write gate
        trace_call("memory.ingestion", "_apply_write_gate")
        candidates = self._apply_write_gate(candidates)
        trace_result("memory.ingestion", "_apply_write_gate", True, f"{len(candidates)} passed")
        
        if not candidates:
            trace_step("memory.ingestion", "No candidates passed write gate - done")
            await self.db.commit()
            return []
        
        # Publish: classified with type breakdown
        if turn_id:
            types = list(set(c.type.value for c in candidates))
            type_counts = {}
            for c in candidates:
                type_counts[c.type.value] = type_counts.get(c.type.value, 0) + 1
            await publisher.publish(
                project_id, EventType.CLASSIFIED,
                f"Classified as {', '.join(types)}", turn_id,
                data={"types": types, "type_counts": type_counts}
            )
        
        # Step 4-6: Process each candidate
        merged_count = 0
        
        # Publish: running deduplication (before first dedup check)
        if turn_id and len(candidates) > 0:
            await publisher.publish(
                project_id, EventType.DEDUP_RUNNING,
                "Running deduplication...", turn_id
            )
        
        for i, candidate in enumerate(candidates):
            trace_step("memory.ingestion", f"Processing candidate {i+1}/{len(candidates)}: {candidate.type.value}")
            
            # Check for duplicates and contradictions
            trace_call("memory.ingestion", "DeduplicationService.check_duplicate")
            is_dup, is_contradiction, existing_id, merged_stmt, new_details = await self.dedup.check_duplicate(
                project_id=project_id,
                candidate=candidate,
            )
            trace_result("memory.ingestion", "check_duplicate", True, f"duplicate={is_dup}, contradiction={is_contradiction}")
            
            # Handle contradiction - DON'T create memory, trigger conflict UI
            if is_contradiction and existing_id:
                trace_step("memory.ingestion", f"Contradiction detected with memory {existing_id[:8]} - triggering conflict resolution")
                
                # Get the existing memory details for the UI
                existing_stmt = select(MemoryAtom).where(MemoryAtom.id == existing_id)
                existing_result = await self.db.execute(existing_stmt)
                existing_memory = existing_result.scalar_one_or_none()
                
                # Publish CONFLICT_DETECTED event for the UI
                if turn_id and existing_memory:
                    await publisher.publish(
                        project_id, EventType.CONFLICT_DETECTED,
                        f"Conflict detected!", turn_id,
                        data={
                            "new_memory": {
                                "id": None,  # Not created yet
                                "type": candidate.type.value,
                                "statement": candidate.canonical_statement,
                                "importance": candidate.importance,
                                "confidence": candidate.confidence,
                            },
                            "existing_memory": {
                                "id": str(existing_memory.id),
                                "type": existing_memory.type.value,
                                "statement": existing_memory.canonical_statement,
                                "importance": existing_memory.importance,
                                "confidence": existing_memory.confidence,
                                "created_at": existing_memory.created_at.isoformat(),
                            },
                            "explanation": f"New statement contradicts existing {existing_memory.type.value}",
                            "recommended_action": "resolve",
                        }
                    )
                
                # Log the conflict
                self.db.add(OpsLog(
                    project_id=project_id,
                    op_type=OpType.CONFLICT,
                    entity_id=existing_id,
                    entity_type="memory",
                    message=f"Contradiction detected: '{candidate.canonical_statement[:50]}...' conflicts with existing memory",
                ))
                
                # Skip creating this memory - user must resolve conflict first
                continue
                
            elif is_dup and existing_id:
                # Update existing memory with new version - use merged statement
                if new_details and new_details != "none" and new_details is not None:
                    trace_step("memory.ingestion", f"Merging into existing memory (new details: {new_details})")
                else:
                    trace_step("memory.ingestion", "Merging into existing memory (no new details)")
                    
                await self.dedup.merge_into_existing(
                    memory_id=existing_id,
                    candidate=candidate,
                    merged_statement=merged_stmt,
                    new_details=new_details,
                )
                self.db.add(OpsLog(
                    project_id=project_id,
                    op_type=OpType.DEDUP,
                    entity_id=existing_id,
                    entity_type="memory",
                    message=f"Merged duplicate: {new_details or 'no new details added'}",
                ))
                
                # Publish: dedup found with memory ID for navigation
                if turn_id:
                    await publisher.publish(
                        project_id, EventType.DEDUP_FOUND,
                        f"Merged into existing memory", turn_id,
                        data={
                            "memory_id": existing_id,
                            "type": candidate.type.value,
                            "preview": merged_stmt[:50] + "..." if merged_stmt and len(merged_stmt) > 50 else (merged_stmt or candidate.canonical_statement[:50])
                        }
                    )
                
                merged_count += 1
                continue
            
            # Create new memory
            memory = MemoryAtom(
                project_id=project_id,
                type=candidate.type,
                canonical_statement=candidate.canonical_statement,
                conflict_key=candidate.conflict_key,
                importance=candidate.importance,
                confidence=candidate.confidence,
                entities=json.dumps(candidate.entities) if candidate.entities else None,
            )
            self.db.add(memory)
            await self.db.flush()
            
            # Create initial version
            version = MemoryVersion(
                memory_id=memory.id,
                version_number=1,
                statement=candidate.canonical_statement,
                rationale=candidate.rationale,
                changed_by="user",
            )
            self.db.add(version)
            
            # Link to evidence
            if chunks and candidate.evidence_quote:
                # Find the chunk that contains the quote
                best_chunk = chunks[0]  # Default to first
                for chunk in chunks:
                    if candidate.evidence_quote in chunk.text:
                        best_chunk = chunk
                        break
                
                link = MemoryEvidenceLink(
                    memory_id=memory.id,
                    evidence_id=best_chunk.id,
                    quote=candidate.evidence_quote,
                    confidence=candidate.confidence,
                )
                self.db.add(link)
            
            # Log creation
            self.db.add(OpsLog(
                project_id=project_id,
                op_type=OpType.MEMORY_CREATE,
                entity_id=memory.id,
                entity_type="memory",
                message=f"Created {candidate.type.value}: {candidate.canonical_statement[:100]}",
            ))
            
            created_memories.append(memory)
            trace_step("memory.ingestion", f"Created memory: {memory.id[:8]}")
            
            # Check for conflicts
            conflicts = await self.conflict.detect_conflicts(
                project_id=project_id,
                memory=memory,
            )
            
            for conflict in conflicts:
                self.db.add(OpsLog(
                    project_id=project_id,
                    op_type=OpType.CONFLICT,
                    entity_id=memory.id,
                    entity_type="memory",
                    message=f"Conflict detected with memory {conflict['other_id']}: {conflict['explanation']}",
                    extra_data=json.dumps(conflict),
                ))
                
                # Publish conflict event with full details for UI
                if turn_id:
                    # Get the conflicting memory details
                    other_stmt = select(MemoryAtom).where(MemoryAtom.id == conflict['other_id'])
                    other_result = await self.db.execute(other_stmt)
                    other_memory = other_result.scalar_one_or_none()
                    
                    await publisher.publish(
                        project_id, EventType.CONFLICT_DETECTED,
                        f"Conflict detected!", turn_id,
                        data={
                            "new_memory": {
                                "id": memory.id,
                                "type": memory.type.value,
                                "statement": memory.canonical_statement,
                                "importance": memory.importance,
                                "confidence": memory.confidence,
                                "created_at": memory.created_at.isoformat(),
                            },
                            "existing_memory": {
                                "id": other_memory.id if other_memory else conflict['other_id'],
                                "type": other_memory.type.value if other_memory else "unknown",
                                "statement": conflict['other_statement'],
                                "importance": other_memory.importance if other_memory else 0.5,
                                "confidence": other_memory.confidence if other_memory else 0.5,
                                "created_at": other_memory.created_at.isoformat() if other_memory else None,
                            },
                            "explanation": conflict['explanation'],
                            "recommended_action": conflict['action'],
                        }
                    )
        
        # Publish: duplicates merged
        if turn_id and merged_count > 0:
            await publisher.publish(
                project_id, EventType.DEDUP_FOUND,
                f"{merged_count} duplicate(s) merged", turn_id
            )
        
        # Publish: memories saved
        if turn_id and created_memories:
            await publisher.publish(
                project_id, EventType.MEMORIES_SAVED,
                f"{len(created_memories)} memories saved", turn_id
            )
        
        await self.db.commit()
        return created_memories
    
    async def ingest_document(
        self,
        project_id: str,
        content: str,
        filename: str,
        project_context: str = "",
    ) -> List[MemoryAtom]:
        """
        Ingest a document file.
        
        Similar to message ingestion but with file source type.
        """
        # Create evidence chunks
        chunks = await self._create_evidence_chunks(
            project_id=project_id,
            text=content,
            source_type=SourceType.FILE,
            source_ref=filename,
        )
        
        # Log ingestion
        self.db.add(OpsLog(
            project_id=project_id,
            op_type=OpType.INGEST,
            entity_id=filename,
            entity_type="file",
            message=f"Ingested file with {len(chunks)} chunks",
        ))
        
        # For documents, we might want to extract from each chunk
        all_memories = []
        for chunk in chunks[:5]:  # Limit to first 5 chunks for performance
            candidates = await self._extract_memory_candidates(
                message=chunk.text,
                project_context=project_context,
            )
            candidates = self._apply_write_gate(candidates)
            
            for candidate in candidates:
                is_dup, is_contradiction, _, _, _ = await self.dedup.check_duplicate(
                    project_id=project_id,
                    candidate=candidate,
                )
                # Skip duplicates but allow contradictions through for conflict detection
                if is_dup and not is_contradiction:
                    continue
                
                memory = MemoryAtom(
                    project_id=project_id,
                    type=candidate.type,
                    canonical_statement=candidate.canonical_statement,
                    conflict_key=candidate.conflict_key,
                    importance=candidate.importance,
                    confidence=candidate.confidence,
                )
                self.db.add(memory)
                await self.db.flush()
                
                version = MemoryVersion(
                    memory_id=memory.id,
                    version_number=1,
                    statement=candidate.canonical_statement,
                    rationale=candidate.rationale,
                    changed_by="system",
                )
                self.db.add(version)
                
                link = MemoryEvidenceLink(
                    memory_id=memory.id,
                    evidence_id=chunk.id,
                    quote=candidate.evidence_quote,
                    confidence=candidate.confidence,
                )
                self.db.add(link)
                
                all_memories.append(memory)
        
        await self.db.commit()
        return all_memories
