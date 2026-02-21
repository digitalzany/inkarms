"""Tests for hub scheduler — schedule parsing and job management."""

from __future__ import annotations

import pytest


class TestParseSchedule:
    """Tests for _parse_schedule helper."""

    def _parse(self, schedule: str):
        from inkarms.hub.scheduler import _parse_schedule
        return _parse_schedule(schedule)

    def test_interval_minutes(self) -> None:
        result = self._parse("every 5m")
        assert result["trigger"] == "interval"
        assert result["trigger_args"] == {"minutes": 5}

    def test_interval_hours(self) -> None:
        result = self._parse("every 2h")
        assert result["trigger"] == "interval"
        assert result["trigger_args"] == {"hours": 2}

    def test_interval_seconds(self) -> None:
        result = self._parse("every 30s")
        assert result["trigger"] == "interval"
        assert result["trigger_args"] == {"seconds": 30}

    def test_interval_days(self) -> None:
        result = self._parse("every 1d")
        assert result["trigger"] == "interval"
        assert result["trigger_args"] == {"days": 1}

    def test_interval_case_insensitive(self) -> None:
        result = self._parse("every 10M")
        assert result["trigger"] == "interval"
        assert result["trigger_args"] == {"minutes": 10}

    def test_cron_five_fields(self) -> None:
        result = self._parse("0 * * * *")
        assert result["trigger"] == "cron"
        assert result["trigger_args"]["minute"] == "0"
        assert result["trigger_args"]["hour"] == "*"

    def test_cron_with_step(self) -> None:
        result = self._parse("*/5 * * * *")
        assert result["trigger"] == "cron"
        assert result["trigger_args"]["minute"] == "*/5"

    def test_cron_six_fields(self) -> None:
        result = self._parse("0 0 * * * *")
        assert result["trigger"] == "cron"
        assert "second" in result["trigger_args"]

    def test_invalid_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unrecognised"):
            self._parse("not_a_schedule")

    def test_invalid_every_no_unit(self) -> None:
        with pytest.raises(ValueError):
            self._parse("every 5")


class TestAddJob:
    """Tests for add_job / remove_job behaviour."""

    def test_add_job_disabled_does_not_register(self) -> None:
        """Disabled jobs are not added to the scheduler."""
        from unittest.mock import MagicMock, patch

        from inkarms.hub import scheduler

        mock_sched = MagicMock()
        with patch.object(scheduler, "_scheduler", mock_sched):
            scheduler.add_job({
                "id": "test-job",
                "schedule": "every 5m",
                "type": "bash",
                "command": "echo hi",
                "session_id": "default",
                "enabled": False,
            })
            mock_sched.add_job.assert_not_called()

    def test_add_job_bash_registers(self) -> None:
        """Enabled bash job calls scheduler.add_job."""
        from unittest.mock import MagicMock, patch

        from inkarms.hub import scheduler

        mock_sched = MagicMock()
        with patch.object(scheduler, "_scheduler", mock_sched):
            scheduler.add_job({
                "id": "bash-job",
                "schedule": "every 1m",
                "type": "bash",
                "command": "ls",
                "session_id": "default",
                "enabled": True,
            })
            mock_sched.add_job.assert_called_once()
            kwargs = mock_sched.add_job.call_args
            assert kwargs[1]["id"] == "bash-job"

    def test_remove_job_silent_on_missing(self) -> None:
        """remove_job is silent when job does not exist in scheduler."""
        from inkarms.hub import scheduler

        # No scheduler running — should not raise
        with pytest.raises(RuntimeError, match="not started"):
            scheduler.get_scheduler()
        # remove_job should swallow the error gracefully
        scheduler.remove_job("nonexistent-job")  # must not raise


class TestGetScheduler:
    def test_raises_before_start(self) -> None:
        from inkarms.hub import scheduler

        original = scheduler._scheduler
        scheduler._scheduler = None
        try:
            with pytest.raises(RuntimeError, match="not started"):
                scheduler.get_scheduler()
        finally:
            scheduler._scheduler = original
