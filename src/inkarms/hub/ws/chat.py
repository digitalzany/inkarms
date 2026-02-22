"""
Hub WebSocket chat endpoint.

WS /ws/chat/{session_id}

Authentication (first message, within 5s):
    Client → Server: {"type": "auth", "token": "<key>"}
    Server → Client: {"type": "ready"}

Message protocol (after auth):
    Client → Server: {"type": "message", "content": "...", "skills": [...]}
    Server → Client: {"type": "delta", "content": "..."}
    Server → Client: {"type": "tool_start", "name": "bash", "input": "..."}
    Server → Client: {"type": "tool_done",  "name": "bash", "output": "..."}
    Server → Client: {"type": "ping"}           ← heartbeat every ws_ping_interval seconds
    Server → Client: {"type": "done", "tokens": N, "cost": 0.0}
    Server → Client: {"type": "shutdown"}       ← on hub SIGTERM

Hub WS sessions are registered in hub.db session_index with platform="hub".
session_index is updated on connect and after each completed turn.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from inkarms.hub import auth as hub_auth
from inkarms.hub import db as hub_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/chat/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    """WebSocket chat endpoint — wraps MessageProcessor.process_streaming()."""
    from inkarms.config.loader import get_config

    cfg = get_config()
    await websocket.accept()

    # Authenticate via first-message protocol
    authenticated = await hub_auth.ws_authenticate(websocket, cfg.hub.trust_localhost)
    if not authenticated:
        return

    # Register/touch session_index (platform="hub")
    await hub_db.upsert_session(session_id=session_id, platform="hub")

    # Get MessageProcessor from app state
    app_state = getattr(websocket.app.state, "hub", None)
    processor = getattr(app_state, "processor", None) if app_state else None
    session_store = getattr(app_state, "session_store", None) if app_state else None

    if processor is None:
        await websocket.send_json({"type": "error", "message": "hub not fully started"})
        await websocket.close(code=1011)
        return

    # Start server-side heartbeat
    ping_task = asyncio.create_task(
        _ping_loop(websocket, interval=cfg.hub.ws_ping_interval)
    )

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            if msg.get("type") != "message":
                continue

            content = msg.get("content", "").strip()
            if not content:
                continue

            # Stream the response
            tokens = 0
            cost = 0.0

            try:
                async for chunk in processor.process_streaming(
                    query=content,
                    session_id=session_id,
                    platform="hub",
                    platform_user_id=None,
                    platform_username=None,
                ):
                    frame = _chunk_to_frame(chunk)
                    if frame:
                        await websocket.send_json(frame)

                    # Capture final cost/token data
                    if chunk.is_final and chunk.metadata:
                        tokens = chunk.metadata.get("total_tokens", tokens)
                        cost = chunk.metadata.get("cost", cost)

            except Exception as exc:  # noqa: BLE001
                logger.error("hub ws/chat processing error: %s", exc, exc_info=True)
                await websocket.send_json({"type": "error", "message": str(exc)})

            # Send completion frame
            await websocket.send_json({"type": "done", "tokens": tokens, "cost": cost})

            # Update session_index with turn metrics
            await hub_db.upsert_session(
                session_id=session_id,
                platform="hub",
                turn_count_delta=1,
                tokens_delta=tokens,
                cost_delta=cost,
            )

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("hub ws/chat error: %s", exc, exc_info=True)
    finally:
        ping_task.cancel()
        logger.debug("WS chat session %s disconnected", session_id)


def _chunk_to_frame(chunk: Any) -> dict[str, Any] | None:
    """Convert a StreamChunk to a WS frame dict."""
    if chunk.is_final:
        return None  # done frame is sent separately

    meta = chunk.metadata or {}
    event_type = meta.get("event_type", "stream_chunk")

    if event_type == "tool_start":
        return {
            "type": "tool_start",
            "name": meta.get("tool_name", ""),
            "input": chunk.content,
        }
    if event_type == "tool_complete":
        return {
            "type": "tool_done",
            "name": meta.get("tool_name", ""),
            "output": chunk.content,
        }
    if chunk.content:
        return {"type": "delta", "content": chunk.content}
    return None


async def _ping_loop(websocket: WebSocket, interval: int) -> None:
    """Send server-side ping frames every ``interval`` seconds."""
    while True:
        try:
            await asyncio.sleep(interval)
            await websocket.send_json({"type": "ping"})
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            break
