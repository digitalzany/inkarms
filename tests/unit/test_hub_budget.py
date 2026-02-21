"""Tests for hub BudgetTracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from inkarms.hub.budget import BudgetTracker


class TestBudgetTracker:
    def _make_tracker(
        self, daily_limit: float | None = 10.0, sync_interval: int = 60
    ) -> BudgetTracker:
        tracker = BudgetTracker(daily_limit=daily_limit, sync_interval=sync_interval)
        tracker._today_cost = 0.0
        tracker._today_date = "2026-02-20"
        return tracker

    def test_check_under_limit_no_raise(self) -> None:
        tracker = self._make_tracker(daily_limit=10.0)
        tracker._today_cost = 5.0
        tracker.check(delta=1.0, block_on_exceed=True)  # 6.0 < 10.0 — no raise

    def test_check_over_limit_raises_when_blocking(self) -> None:
        tracker = self._make_tracker(daily_limit=5.0)
        tracker._today_cost = 4.9
        with pytest.raises(HTTPException) as exc_info:
            tracker.check(delta=0.5, block_on_exceed=True)
        assert exc_info.value.status_code == 429

    def test_check_over_limit_no_raise_when_not_blocking(self) -> None:
        tracker = self._make_tracker(daily_limit=5.0)
        tracker._today_cost = 10.0
        # Should not raise when block_on_exceed=False
        tracker.check(block_on_exceed=False)

    def test_check_no_limit_never_raises(self) -> None:
        tracker = self._make_tracker(daily_limit=None)
        tracker._today_cost = 999.0
        tracker.check(delta=999.0, block_on_exceed=True)  # No limit — no raise

    def test_record_accumulates_cost(self) -> None:
        tracker = self._make_tracker()
        tracker.record(1.23)
        tracker.record(0.77)
        assert abs(tracker.today_cost - 2.00) < 1e-9

    def test_record_marks_dirty(self) -> None:
        tracker = self._make_tracker()
        assert tracker._dirty is False
        tracker.record(0.01)
        assert tracker._dirty is True

    def test_today_cost_property(self) -> None:
        tracker = self._make_tracker()
        tracker._today_cost = 3.14
        assert tracker.today_cost == 3.14

    def test_daily_limit_property(self) -> None:
        tracker = self._make_tracker(daily_limit=7.5)
        assert tracker.daily_limit == 7.5

    @pytest.mark.asyncio
    async def test_sync_now_calls_db(self) -> None:
        tracker = self._make_tracker()
        tracker._today_cost = 1.50
        tracker._dirty = True

        with patch("inkarms.hub.db.upsert_daily_cost", new_callable=AsyncMock) as mock_upsert:
            await tracker.sync_now()
            mock_upsert.assert_called_once_with("2026-02-20", 1.50)

        assert tracker._dirty is False

    def test_date_rollover_resets_cost(self) -> None:
        tracker = self._make_tracker()
        tracker._today_cost = 5.0
        tracker._today_date = "2020-01-01"  # Old date
        # _refresh_date() should reset cost when date changes
        tracker._refresh_date()
        assert tracker._today_cost == 0.0
