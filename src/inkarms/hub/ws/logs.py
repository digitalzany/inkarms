"""
Hub WebSocket log tail endpoint.

WS /ws/logs

Streams new lines from hub.log to connected clients.  Handles log rotation
by detecting inode changes — when the file is renamed and a new one created,
the stream transparently reopens the new file.

Requires: pip install aiofiles  (part of inkarms[hub])
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from inkarms.hub import auth as hub_auth
from inkarms.storage.paths import get_hub_log_path

router = APIRouter()
logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.2   # seconds between readline attempts
_INODE_CHECK_INTERVAL = 10  # seconds between inode checks for rotation detection


@router.websocket("/ws/logs")
async def logs_ws(websocket: WebSocket) -> None:
    """Stream hub.log lines to the connected client."""
    from inkarms.config.loader import get_config

    cfg = get_config()
    await websocket.accept()

    authenticated = await hub_auth.ws_authenticate(websocket, cfg.hub.trust_localhost)
    if not authenticated:
        return

    log_path = get_hub_log_path()

    try:
        import aiofiles
    except ImportError:
        await websocket.send_json(
            {"type": "error", "message": "aiofiles not installed — pip install inkarms[hub]"}
        )
        await websocket.close(code=1011)
        return

    try:
        await _stream_log(websocket, log_path, aiofiles)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("ws/logs error: %s", exc)


async def _stream_log(websocket: WebSocket, log_path: Path, aiofiles: object) -> None:
    """Tail log_path, detect rotation, stream lines as {"type":"log","line":"..."}."""
    # If file doesn't exist yet, wait for it
    wait_count = 0
    while not log_path.exists():
        await asyncio.sleep(1.0)
        wait_count += 1
        if wait_count > 30:
            await websocket.send_json({"type": "error", "message": "log file not found"})
            return

    current_inode = _get_inode(log_path)
    last_inode_check = asyncio.get_event_loop().time()

    async with aiofiles.open(str(log_path)) as f:  # type: ignore[attr-defined]
        # Seek to end — only stream new lines
        await f.seek(0, 2)

        while True:
            line = await f.readline()
            if line:
                await websocket.send_json({"type": "log", "line": line.rstrip()})
            else:
                await asyncio.sleep(_POLL_INTERVAL)

            # Periodically check for log rotation (inode change)
            now = asyncio.get_event_loop().time()
            if now - last_inode_check >= _INODE_CHECK_INTERVAL:
                last_inode_check = now
                new_inode = _get_inode(log_path)
                if new_inode and new_inode != current_inode:
                    logger.debug("Log rotation detected — reopening %s", log_path)
                    current_inode = new_inode
                    # Reopen file from beginning of new log
                    break  # exit inner loop; caller will re-enter

    # Re-enter to tail the rotated file (recursion avoided by iteration)
    await _stream_log(websocket, log_path, aiofiles)


def _get_inode(path: Path) -> int | None:
    """Return the inode number of path, or None if unavailable."""
    try:
        return path.stat().st_ino
    except OSError:
        return None
