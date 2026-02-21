"""
Hub platforms API.

GET /api/platforms  — health status of all registered platform adapters
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/api/platforms")
async def get_platforms(request: Request) -> dict[str, Any]:
    """Return health status of all registered platform adapters."""
    app_state = getattr(request.app.state, "hub", None)
    router_obj = getattr(app_state, "router", None) if app_state else None

    if router_obj is None:
        return {
            "platforms": {},
            "is_running": False,
            "active_platforms": [],
        }

    try:
        health = await router_obj.health_check()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Health check failed: {exc}") from exc

    return {
        "platforms": health,
        "is_running": router_obj.is_running,
        "active_platforms": router_obj.active_platforms,
    }
