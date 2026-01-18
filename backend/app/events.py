"""
Pipeline Event Publisher

Server-Sent Events (SSE) for real-time pipeline observability.
Publishes events for memory search, retrieval, extraction, deduplication, etc.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional, AsyncGenerator
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Pipeline event types."""
    INTENT_CLASSIFIED = "intent_classified"
    SEARCH_START = "search_start"
    MEMORIES_RETRIEVED = "memories_retrieved"
    GENERATING = "generating"
    EXTRACTING = "extracting"
    CANDIDATES_CREATED = "candidates_created"
    CLASSIFIED = "classified"
    DEDUP_RUNNING = "dedup_running"
    DEDUP_FOUND = "dedup_found"
    MEMORIES_SAVED = "memories_saved"
    COMPLETE = "complete"
    ERROR = "error"
    
    # Work session events
    SESSION_ENDING = "session_ending"
    SUMMARIZING = "summarizing"
    SUMMARY_GENERATED = "summary_generated"
    SESSION_COMPLETE = "session_complete"
    
    # Conflict events
    CONFLICT_DETECTED = "conflict_detected"
    CONFLICT_RESOLVED = "conflict_resolved"


@dataclass
class PipelineEvent:
    """A pipeline event to be streamed to client."""
    event_type: str
    message: str
    turn_id: str  # Groups events from same chat turn
    timestamp: str = None
    data: Optional[Dict] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
    
    def to_sse(self) -> str:
        """Format as SSE data line."""
        payload = asdict(self)
        return f"data: {json.dumps(payload)}\n\n"


class EventPublisher:
    """
    Manages SSE event queues for pipeline observability.
    
    Usage:
        publisher = EventPublisher()
        
        # In API endpoint - get stream for project
        async for event in publisher.subscribe(project_id):
            yield event
        
        # In pipeline - publish events
        await publisher.publish(project_id, EventType.SEARCH_START, "Searching memories...")
    """
    
    def __init__(self):
        # project_id -> list of subscriber queues
        self._subscribers: Dict[str, list] = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, project_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to events for a project. Yields SSE-formatted strings."""
        queue = asyncio.Queue()
        
        async with self._lock:
            if project_id not in self._subscribers:
                self._subscribers[project_id] = []
            self._subscribers[project_id].append(queue)
        
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'event_type': 'connected', 'message': 'Connected to event stream'})}\n\n"
            
            while True:
                event = await queue.get()
                if event is None:  # Shutdown signal
                    break
                yield event.to_sse()
        finally:
            async with self._lock:
                if project_id in self._subscribers:
                    self._subscribers[project_id].remove(queue)
                    if not self._subscribers[project_id]:
                        del self._subscribers[project_id]
    
    async def publish(
        self,
        project_id: str,
        event_type: EventType,
        message: str,
        turn_id: str,
        data: Optional[Dict] = None
    ):
        """Publish an event to all subscribers of a project."""
        event = PipelineEvent(
            event_type=event_type.value,
            message=message,
            turn_id=turn_id,
            data=data,
        )
        
        async with self._lock:
            subscribers = self._subscribers.get(project_id, [])
            for queue in subscribers:
                await queue.put(event)
        
        logger.debug(f"Published event to {len(subscribers)} subscribers: {message}")
    
    async def close_all(self, project_id: str):
        """Close all subscriber connections for a project."""
        async with self._lock:
            subscribers = self._subscribers.get(project_id, [])
            for queue in subscribers:
                await queue.put(None)


# Global publisher instance
_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """Get or create the global event publisher."""
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher
