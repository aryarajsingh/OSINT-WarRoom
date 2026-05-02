import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from app.database import get_events

router = APIRouter()

# Global event queue for broadcasting new events to SSE clients
_subscribers: list[asyncio.Queue] = []


def broadcast_event(event_html: str, event_type: str = "new_event"):
    """Push an HTML fragment to all connected SSE clients."""
    for q in _subscribers:
        q.put_nowait({"event": event_type, "data": event_html})


def broadcast_alert(alert_html: str):
    """Push a critical alert to all SSE clients."""
    for q in _subscribers:
        q.put_nowait({"event": "alert", "data": alert_html})


@router.get("/sse/feed")
async def sse_feed():
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    async def event_stream():
        try:
            # Send keepalive comment every 30s to prevent timeout
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield msg
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.remove(queue)

    return EventSourceResponse(event_stream())


@router.get("/sse/alerts")
async def sse_alerts():
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.append(queue)

    async def alert_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if msg.get("event") == "alert":
                        yield msg
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.remove(queue)

    return EventSourceResponse(alert_stream())
