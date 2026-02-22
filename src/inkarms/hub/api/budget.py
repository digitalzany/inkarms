"""
Hub budget API endpoint.

GET /api/budget — current budget status (today's cost, limits, alerts)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/budget")
async def get_budget() -> dict[str, Any]:
    """Return current budget status."""
    from inkarms.config.loader import get_config
    from inkarms.hub import budget as hub_budget

    cfg = get_config()
    budget_cfg = cfg.cost.budgets
    alerts_cfg = cfg.cost.alerts

    result: dict[str, Any] = {
        "limits": {
            "daily": budget_cfg.daily,
            "weekly": budget_cfg.weekly,
            "monthly": budget_cfg.monthly,
        },
        "alerts": {
            "warning_threshold": alerts_cfg.warning_threshold,
            "block_on_exceed": alerts_cfg.block_on_exceed,
        },
        "enforcement": {
            "daily_enforced": budget_cfg.daily is not None,
            "weekly_enforced": False,   # not implemented — see Known Limitations
            "monthly_enforced": False,  # not implemented — see Known Limitations
        },
    }

    try:
        tracker = hub_budget.get_budget_tracker()
        result["today"] = {
            "cost": tracker.today_cost,
            "limit": tracker.daily_limit,
            "remaining": (
                max(0.0, tracker.daily_limit - tracker.today_cost)
                if tracker.daily_limit is not None
                else None
            ),
            "exceeded": (
                tracker.today_cost >= tracker.daily_limit
                if tracker.daily_limit is not None
                else False
            ),
        }
    except RuntimeError:
        result["today"] = {"cost": None, "error": "tracker not initialised"}

    return result
