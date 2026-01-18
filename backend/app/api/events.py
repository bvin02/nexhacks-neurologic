"""
Events API

Server-Sent Events endpoint for real-time pipeline observability.
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..events import get_event_publisher

router = APIRouter(prefix="/projects/{project_id}", tags=["events"])


@router.get("/events")
async def stream_events(project_id: str, request: Request):
    """
    Stream pipeline events for a project using Server-Sent Events.
    
    Connect to this endpoint to receive real-time updates about:
    - Memory search and retrieval
    - Memory candidate extraction
    - Deduplication and merging
    - Response generation
    """
    publisher = get_event_publisher()
    
    async def event_generator():
        async for event in publisher.subscribe(project_id):
            # Check if client disconnected
            if await request.is_disconnected():
                break
            yield event
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
