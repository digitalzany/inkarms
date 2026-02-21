"""
Hub budget tracker.

Maintains daily cost in memory for zero-latency hot-path checks.
Reads from hub.db once on startup; syncs back every budget_sync_interval
seconds (default 60s) or immediately on budget violation / hub shutdown.

Only ``budgets.daily`` is enforced. weekly/monthly emit a config warning
(see configure() below) and have no enforcement effect.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level tracker instance
# ---------------------------------------------------------------------------

_tracker: BudgetTracker | None = None


def get_budget_tracker() -> BudgetTracker:
    """Return the module-level BudgetTracker. Must call init() first."""
    if _tracker is None:
        raise RuntimeError("BudgetTracker not initialised — call hub.budget.init() first")
    return _tracker


# ---------------------------------------------------------------------------
# BudgetTracker
# ---------------------------------------------------------------------------


class BudgetTracker:
    """In-memory daily cost tracker with periodic DB sync.

    Usage (in hub lifespan):
        await budget.init(config, db)         # startup
        budget.get_budget_tracker().check()   # before each AI call (sync, zero DB hits)
        budget.get_budget_tracker().record(delta)  # after each AI call
        await budget.get_budget_tracker().sync_now()  # on shutdown
    """

    def __init__(self, daily_limit: float | None, sync_interval: int) -> None:
        self._daily_limit = daily_limit
        self._sync_interval = sync_interval
        self._today_cost: float = 0.0
        self._today_date: str = ""
        self._dirty: bool = False
        self._sync_task: asyncio.Task[None] | None = None

    @classmethod
    async def create(cls, daily_limit: float | None, sync_interval: int) -> BudgetTracker:
        """Create and initialise a BudgetTracker, reading today's cost from DB."""
        tracker = cls(daily_limit, sync_interval)
        await tracker._load_from_db()
        return tracker

    async def _load_from_db(self) -> None:
        """Load today's cost from hub.db. Called once at startup."""
        from inkarms.hub import db

        today = datetime.now().strftime("%Y-%m-%d")
        self._today_date = today
        self._today_cost = await db.read_daily_cost(today)
        logger.debug("BudgetTracker loaded today=%s cost=%.4f", today, self._today_cost)

    def _refresh_date(self) -> None:
        """Reset cost tracking if the calendar date has rolled over."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_cost = 0.0
            self._dirty = False

    def check(self, delta: float = 0.0, block_on_exceed: bool = False) -> None:
        """Synchronous hot-path budget check — zero DB queries.

        Args:
            delta: Estimated cost of the upcoming call (for pre-flight check).
            block_on_exceed: Raise HTTP 429 if budget would be exceeded.

        Raises:
            HTTPException(429) if block_on_exceed is True and budget is exceeded.
        """
        self._refresh_date()
        if self._daily_limit is None:
            return
        projected = self._today_cost + delta
        if projected >= self._daily_limit:
            logger.warning(
                "Daily budget exceeded: %.4f / %.4f", projected, self._daily_limit
            )
            if block_on_exceed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "budget_exceeded",
                        "today_cost": self._today_cost,
                        "daily_limit": self._daily_limit,
                    },
                )

    def record(self, delta: float) -> None:
        """Record cost delta after a completed AI call."""
        self._refresh_date()
        self._today_cost += delta
        self._dirty = True

    async def periodic_sync(self) -> None:
        """Background task: flush to DB every sync_interval seconds."""
        while True:
            try:
                await asyncio.sleep(self._sync_interval)
                if self._dirty:
                    await self.sync_now()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("BudgetTracker periodic_sync error: %s", exc)

    async def sync_now(self) -> None:
        """Force an immediate DB flush. Call on budget violation or shutdown."""
        from inkarms.hub import db

        self._refresh_date()
        await db.upsert_daily_cost(self._today_date, self._today_cost)
        self._dirty = False
        logger.debug("BudgetTracker synced cost=%.4f for %s", self._today_cost, self._today_date)

    def start_background_sync(self) -> asyncio.Task[None]:
        """Start the periodic sync task and store a reference to it."""
        self._sync_task = asyncio.create_task(self.periodic_sync())
        return self._sync_task

    def stop_background_sync(self) -> None:
        """Cancel the periodic sync task."""
        if self._sync_task is not None:
            self._sync_task.cancel()
            self._sync_task = None

    @property
    def today_cost(self) -> float:
        """Today's accumulated cost (in-memory, may be slightly ahead of DB)."""
        self._refresh_date()
        return self._today_cost

    @property
    def daily_limit(self) -> float | None:
        """Configured daily limit, or None if unset."""
        return self._daily_limit


# ---------------------------------------------------------------------------
# Module-level init / teardown
# ---------------------------------------------------------------------------


async def init(daily_limit: float | None, sync_interval: int) -> None:
    """Initialise the module-level BudgetTracker. Call during hub lifespan startup."""
    global _tracker
    _tracker = await BudgetTracker.create(daily_limit, sync_interval)
    _tracker.start_background_sync()
    logger.info(
        "BudgetTracker initialised (daily_limit=%s, sync_interval=%ds)",
        daily_limit,
        sync_interval,
    )


async def shutdown() -> None:
    """Flush and stop the module-level BudgetTracker. Call during hub lifespan shutdown."""
    global _tracker
    if _tracker is not None:
        _tracker.stop_background_sync()
        await _tracker.sync_now()
        _tracker = None
