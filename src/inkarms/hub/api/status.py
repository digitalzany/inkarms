"""
Hub status API endpoints.

GET /health   — unauthenticated liveness probe (systemd/launchd)
GET /api/status — authenticated summary: uptime, cost, sessions, model
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

router = APIRouter()

# Set by app.py lifespan at startup
_start_time: float = 0.0


def set_start_time(t: float) -> None:
    """Record hub start timestamp. Called from lifespan."""
    global _start_time
    _start_time = t


@router.get("/health")
async def health() -> dict[str, str]:
    """Unauthenticated liveness probe for systemd/launchd health checks."""
    from inkarms import __version__

    return {"status": "ok", "version": __version__}


@router.get("/api/status")
async def status() -> dict[str, Any]:
    """Authenticated hub status summary."""
    from inkarms import __version__
    from inkarms.config.loader import get_config
    from inkarms.hub import budget as hub_budget

    cfg = get_config()
    uptime = time.monotonic() - _start_time if _start_time else 0.0

    cost_info: dict[str, Any] = {}
    try:
        tracker = hub_budget.get_budget_tracker()
        cost_info = {
            "today_cost": tracker.today_cost,
            "daily_limit": tracker.daily_limit,
        }
    except RuntimeError:
        pass

    return {
        "status": "running",
        "version": __version__,
        "uptime_seconds": round(uptime, 1),
        "host": cfg.hub.host,
        "port": cfg.hub.port,
        "model": cfg.providers.default,
        "budget": cost_info,
    }
