"""
Hub sessions API.

GET    /api/sessions           list sessions from hub.db session_index
GET    /api/sessions/{id}      session metadata + recent turns from JSON daily files
DELETE /api/sessions/{id}      remove from session_index; clear JSON daily files

session_index in hub.db is the authoritative store for hub session metadata.
Platform adapter sessions (Telegram, Slack, Discord) are registered here via
lifecycle.py hooks. Hub WS sessions (/ws/chat/{session_id}) use platform="hub".

Full conversation turns live in JSON daily files under
~/.inkarms/memory/platform/<session_id>/daily/.  They are only loaded when
a specific session's detail is requested (never on listing).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from inkarms.hub import db as hub_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# List sessions
# ---------------------------------------------------------------------------


@router.get("/api/sessions")
async def list_sessions(
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List sessions from hub.db session_index (fast, indexed, no file scanning)."""
    params: list[Any] = []
    where = ""
    if platform:
        where = "WHERE platform = ?"
        params.append(platform)

    query = f"""
        SELECT session_id, platform, platform_user_id, channel_id, display_name,
               created_at, last_active, turn_count, total_tokens, total_cost, primary_model
        FROM session_index
        {where}
        ORDER BY last_active DESC
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]

    rows = await hub_db.execute_fetchall(query, tuple(params))

    total_row = await hub_db.execute_fetchone(
        f"SELECT COUNT(*) FROM session_index {where}",
        tuple(params[: len(params) - 2]),  # exclude limit/offset
    )
    total = total_row[0] if total_row else 0

    return {
        "sessions": [_row_to_summary(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Get session detail
# ---------------------------------------------------------------------------


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    """Return session metadata from hub.db plus recent turns from JSON daily files."""
    row = await hub_db.execute_fetchone(
        "SELECT * FROM session_index WHERE session_id = ?", (session_id,)
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    summary = _row_to_summary(row)

    # Load turn history from JSON daily files (only when a specific session is requested)
    summary["turns"] = _load_recent_turns(session_id, max_turns=20)

    return summary


# ---------------------------------------------------------------------------
# Delete session
# ---------------------------------------------------------------------------


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Remove session from session_index and clear its JSON daily files."""
    deleted = await hub_db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    # Best-effort: remove JSON daily files
    _delete_session_files(session_id)

    return {"status": "deleted", "session_id": session_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_summary(row: Any) -> dict[str, Any]:
    """Convert a hub.db session_index row to a dict."""
    return {
        "session_id": row["session_id"],
        "platform": row["platform"],
        "platform_user_id": row["platform_user_id"],
        "channel_id": row["channel_id"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
        "last_active": row["last_active"],
        "turn_count": row["turn_count"],
        "total_tokens": row["total_tokens"],
        "total_cost": row["total_cost"],
        "primary_model": row["primary_model"],
    }


def _load_recent_turns(session_id: str, max_turns: int = 20) -> list[dict[str, Any]]:
    """Load the most recent turns from JSON daily files for a session."""
    import json
    from pathlib import Path

    from inkarms.storage.paths import get_inkarms_home

    daily_dir = get_inkarms_home() / "memory" / "platform" / session_id / "daily"
    if not daily_dir.exists():
        return []

    turns: list[dict[str, Any]] = []
    # Walk daily files newest-first
    for daily_file in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(daily_file.read_text())
            file_turns = data.get("turns", data.get("messages", []))
            turns = file_turns + turns  # prepend older turns
            if len(turns) >= max_turns:
                break
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not load daily file %s: %s", daily_file, exc)

    return turns[-max_turns:]


def _delete_session_files(session_id: str) -> None:
    """Remove JSON daily files for a session (best-effort)."""
    import shutil
    from pathlib import Path

    from inkarms.storage.paths import get_inkarms_home

    session_dir = get_inkarms_home() / "memory" / "platform" / session_id
    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
            logger.info("Deleted session files: %s", session_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not delete session files %s: %s", session_dir, exc)
