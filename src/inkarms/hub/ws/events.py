"""
Hub WebSocket event bus.

WS /ws/events

Each subscriber gets a bounded asyncio.Queue (maxsize=1000).  When full, the
oldest event is dropped and the client receives {"type":"overflow","dropped":N}.
After 3 consecutive overflows the client is disconnected to prevent back-pressure.

Concurrent subscriber count is capped by ``hub.max_event_subscribers``.

Usage (from other hub modules):
    from inkarms.hub.ws.events import broadcast
    await broadcast({"type": "tool_start", "name": "bash"})
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from inkarms.hub import auth as hub_auth

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process event bus
# ---------------------------------------------------------------------------

_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
_QUEUE_MAXSIZE = 1000
_MAX_OVERFLOW = 3


def _register(q: asyncio.Queue[dict[str, Any]]) -> None:
    _subscribers.add(q)


def _unregister(q: asyncio.Queue[dict[str, Any]]) -> None:
    _subscribers.discard(q)


async def broadcast(event: dict[str, Any]) -> None:
    """Send an event to all connected /ws/events subscribers.

    Called by lifecycle, cron, triggers, and other hub components.
    Each subscriber's queue is non-blocking: overflow is handled per-queue.
    """
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest item and enqueue an overflow notification
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait({"type": "overflow", "dropped": 1})
            except asyncio.QueueFull:
                pass


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    """Stream hub events to connected clients."""
    from inkarms.config.loader import get_config

    cfg = get_config()
    await websocket.accept()

    # Auth
    authenticated = await hub_auth.ws_authenticate(websocket, cfg.hub.trust_localhost)
    if not authenticated:
        return

    # Cap concurrent subscribers
    if len(_subscribers) >= cfg.hub.max_event_subscribers:
        await websocket.send_json({"type": "error", "message": "max_subscribers_reached"})
        await websocket.close(code=1008)
        return

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _register(queue)

    ping_task = asyncio.create_task(
        _ping_loop(websocket, interval=cfg.hub.ws_ping_interval)
    )

    overflow_count = 0

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=60.0)
            except asyncio.TimeoutError:
                continue  # keep alive

            await websocket.send_json(event)

            if event.get("type") == "overflow":
                overflow_count += 1
                if overflow_count >= _MAX_OVERFLOW:
                    logger.warning("WS /ws/events client disconnected after %d overflows", overflow_count)
                    break
            else:
                overflow_count = 0

            # Disconnect clients on hub shutdown signal
            if event.get("type") == "shutdown":
                break

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("ws/events error: %s", exc)
    finally:
        ping_task.cancel()
        _unregister(queue)


async def _ping_loop(websocket: WebSocket, interval: int) -> None:
    while True:
        try:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            break
