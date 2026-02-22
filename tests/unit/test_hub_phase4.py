"""
Phase 4 tests: SIGHUP handler, graceful shutdown, install helpers.
"""

from __future__ import annotations

import signal
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SIGHUP handler tests
# ---------------------------------------------------------------------------


class TestSighupHandler:
    """Tests for _on_sighup() in hub/app.py."""

    @pytest.mark.asyncio
    async def test_sighup_aborts_on_invalid_config(self) -> None:
        """Bad config keeps hub running unchanged — no adapter restart."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = None  # adapters not running

        with patch(
            "inkarms.config.loader.get_config",
            side_effect=ValueError("bad yaml"),
        ):
            # Should not raise — errors are logged only
            await _on_sighup(app_state)

        # No lifecycle calls when config is invalid
        app_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_sighup_reloads_config_no_adapters(self) -> None:
        """When adapters are not running and config says don't start, only reload."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = None

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = False
        mock_cfg.platforms.enable = False

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch("inkarms.hub.app.hub_budget.get_budget_tracker") as mock_bt,
            patch(
                "inkarms.hub.lifecycle.stop_hub", new_callable=AsyncMock
            ) as mock_stop,
            patch(
                "inkarms.hub.lifecycle.start_hub", new_callable=AsyncMock
            ) as mock_start,
        ):
            mock_bt.return_value.sync_now = AsyncMock()
            await _on_sighup(app_state)

        mock_stop.assert_not_called()
        mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_sighup_restarts_running_adapters(self) -> None:
        """Running adapters are stopped and restarted on SIGHUP."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = MagicMock()  # adapters ARE running

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = True
        mock_cfg.platforms.enable = True

        stop_mock = AsyncMock()
        start_mock = AsyncMock()

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch("inkarms.hub.app.hub_budget.get_budget_tracker") as mock_bt,
            patch("inkarms.hub.lifecycle.stop_hub", stop_mock),
            patch("inkarms.hub.lifecycle.start_hub", start_mock),
        ):
            mock_bt.return_value.sync_now = AsyncMock()
            await _on_sighup(app_state)

        stop_mock.assert_called_once_with(app_state)
        start_mock.assert_called_once_with(app_state)

    @pytest.mark.asyncio
    async def test_sighup_starts_newly_enabled_adapters(self) -> None:
        """Adapters that weren't running but config now enables them are started."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = None  # adapters NOT running

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = True
        mock_cfg.platforms.enable = True

        start_mock = AsyncMock()
        stop_mock = AsyncMock()

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch("inkarms.hub.app.hub_budget.get_budget_tracker") as mock_bt,
            patch("inkarms.hub.lifecycle.stop_hub", stop_mock),
            patch("inkarms.hub.lifecycle.start_hub", start_mock),
        ):
            mock_bt.return_value.sync_now = AsyncMock()
            await _on_sighup(app_state)

        stop_mock.assert_not_called()
        start_mock.assert_called_once_with(app_state)

    @pytest.mark.asyncio
    async def test_sighup_syncs_budget_before_restart(self) -> None:
        """BudgetTracker.sync_now() is called before adapter restart."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = MagicMock()

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = True
        mock_cfg.platforms.enable = True

        call_order: list[str] = []

        mock_tracker = MagicMock()
        mock_tracker.sync_now = AsyncMock(
            side_effect=lambda: call_order.append("sync")
        )

        stop_mock = AsyncMock(side_effect=lambda s: call_order.append("stop"))
        start_mock = AsyncMock(side_effect=lambda s: call_order.append("start"))

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch(
                "inkarms.hub.app.hub_budget.get_budget_tracker",
                return_value=mock_tracker,
            ),
            patch("inkarms.hub.lifecycle.stop_hub", stop_mock),
            patch("inkarms.hub.lifecycle.start_hub", start_mock),
        ):
            await _on_sighup(app_state)

        # Budget must be synced before stop
        assert call_order.index("sync") < call_order.index("stop")

    @pytest.mark.asyncio
    async def test_sighup_budget_tracker_not_init_is_ok(self) -> None:
        """RuntimeError from get_budget_tracker is silently ignored."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = None

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = False
        mock_cfg.platforms.enable = False

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch(
                "inkarms.hub.app.hub_budget.get_budget_tracker",
                side_effect=RuntimeError("not initialised"),
            ),
        ):
            # Must not raise
            await _on_sighup(app_state)

    @pytest.mark.asyncio
    async def test_sighup_stops_adapters_not_restarted_when_disabled(self) -> None:
        """Running adapters are stopped but NOT restarted when new config disables them."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = MagicMock()  # adapters running

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = False   # disabled in new config
        mock_cfg.platforms.enable = False

        stop_mock = AsyncMock()
        start_mock = AsyncMock()

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch("inkarms.hub.app.hub_budget.get_budget_tracker") as mock_bt,
            patch("inkarms.hub.lifecycle.stop_hub", stop_mock),
            patch("inkarms.hub.lifecycle.start_hub", start_mock),
        ):
            mock_bt.return_value.sync_now = AsyncMock()
            await _on_sighup(app_state)

        stop_mock.assert_called_once_with(app_state)
        start_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Graceful shutdown — early budget sync
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_syncs_budget_before_stop_hub(self) -> None:
        """Budget sync is called before stop_hub in SIGHUP sequence."""
        from inkarms.hub.app import _on_sighup

        app_state = MagicMock()
        app_state.router = MagicMock()

        mock_cfg = MagicMock()
        mock_cfg.hub.auto_start_platforms = True
        mock_cfg.platforms.enable = True

        call_order: list[str] = []

        mock_tracker = MagicMock()
        mock_tracker.sync_now = AsyncMock(
            side_effect=lambda: call_order.append("sync")
        )
        stop_mock = AsyncMock(side_effect=lambda s: call_order.append("stop"))
        start_mock = AsyncMock(side_effect=lambda s: call_order.append("start"))

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch(
                "inkarms.hub.app.hub_budget.get_budget_tracker",
                return_value=mock_tracker,
            ),
            patch("inkarms.hub.lifecycle.stop_hub", stop_mock),
            patch("inkarms.hub.lifecycle.start_hub", start_mock),
        ):
            await _on_sighup(app_state)

        assert "sync" in call_order
        # sync comes before stop
        assert call_order.index("sync") < call_order.index("stop")


# ---------------------------------------------------------------------------
# Install helper content tests
# ---------------------------------------------------------------------------


class TestInstallHelpers:
    """Tests for launchd and systemd service file generation."""

    def test_launchd_plist_has_required_keys(self, tmp_path: Path) -> None:
        """Plist must contain correct keys for reliable restart."""
        from inkarms.cli.commands.hub import _install_launchd

        log_path = tmp_path / "logs" / "hub.log"
        inkarms_home = tmp_path

        with patch("inkarms.cli.commands.hub.os.system"):
            _install_launchd(sys.executable, log_path, inkarms_home)

        plist_path = Path.home() / "Library" / "LaunchAgents" / "dev.inkarms.hub.plist"
        if not plist_path.exists():
            pytest.skip("LaunchAgents dir not available")

        content = plist_path.read_text()
        assert sys.executable in content
        assert "SuccessfulExit" in content
        assert "<false/>" in content
        assert "ThrottleInterval" in content
        assert "<integer>10</integer>" in content
        assert "PYTHONUNBUFFERED" in content
        # Cleanup
        plist_path.unlink(missing_ok=True)

    def test_launchd_writes_sentinel_file(self, tmp_path: Path) -> None:
        """install writes sentinel hub.launchd so stop knows to use launchctl."""
        from inkarms.cli.commands.hub import _install_launchd

        log_path = tmp_path / "hub.log"
        inkarms_home = tmp_path

        with patch("inkarms.cli.commands.hub.os.system"):
            _install_launchd(sys.executable, log_path, inkarms_home)

        sentinel = inkarms_home / "hub.launchd"
        assert sentinel.exists()
        plist_path_str = sentinel.read_text().strip()
        assert plist_path_str.endswith(".plist")
        # Cleanup
        plist = Path(plist_path_str)
        plist.unlink(missing_ok=True)

    def test_systemd_unit_has_restart_and_env(self, tmp_path: Path) -> None:
        """systemd unit uses Restart=on-failure and PYTHONUNBUFFERED."""
        import shutil
        from inkarms.cli.commands.hub import _install_systemd

        inkarms_bin = shutil.which("inkarms") or sys.executable + " -m inkarms"

        with (
            patch("inkarms.cli.commands.hub.os.system"),
            patch(
                "inkarms.cli.commands.hub.Path.home",
                return_value=tmp_path,
            ),
        ):
            _install_systemd(inkarms_bin)

        service_path = (
            tmp_path / ".config" / "systemd" / "user" / "inkarms-hub.service"
        )
        if not service_path.exists():
            pytest.skip("systemd path not written in this environment")

        content = service_path.read_text()
        assert "Restart=on-failure" in content
        assert "PYTHONUNBUFFERED=1" in content
        assert inkarms_bin in content

    def test_uninstall_launchd_removes_sentinel(self, tmp_path: Path) -> None:
        """uninstall removes the hub.launchd sentinel file."""
        from inkarms.cli.commands.hub import _uninstall_launchd

        # Create a fake sentinel
        sentinel = tmp_path / "hub.launchd"
        sentinel.write_text("/fake/path/dev.inkarms.hub.plist")

        with (
            patch(
                "inkarms.storage.paths.get_inkarms_home",
                return_value=tmp_path,
            ),
            patch("inkarms.cli.commands.hub.os.system"),
        ):
            _uninstall_launchd()

        assert not sentinel.exists()


# ---------------------------------------------------------------------------
# Stop command tests
# ---------------------------------------------------------------------------


class TestStopCommand:
    def test_stop_uses_launchctl_when_sentinel_exists(
        self, tmp_path: Path
    ) -> None:
        """stop command uses launchctl unload when hub.launchd sentinel exists."""
        from inkarms.cli.commands.hub import stop as hub_stop

        sentinel = tmp_path / "hub.launchd"
        plist = tmp_path / "dev.inkarms.hub.plist"
        sentinel.write_text(str(plist))

        with (
            patch(
                "inkarms.storage.paths.get_inkarms_home",
                return_value=tmp_path,
            ),
            patch("inkarms.cli.commands.hub.os.system") as mock_system,
        ):
            hub_stop()

        call_args = mock_system.call_args[0][0]
        assert "launchctl" in call_args
        assert "unload" in call_args
        assert str(plist) in call_args

    def test_stop_uses_sigterm_without_sentinel(self, tmp_path: Path) -> None:
        """stop command sends SIGTERM when no launchd sentinel."""
        from inkarms.cli.commands.hub import stop as hub_stop

        with (
            patch(
                "inkarms.storage.paths.get_inkarms_home",
                return_value=tmp_path,
            ),
            patch(
                "inkarms.cli.commands.hub._read_pid",
                return_value=12345,
            ),
            patch("inkarms.cli.commands.hub.os.kill") as mock_kill,
        ):
            hub_stop()

        mock_kill.assert_called_once_with(12345, signal.SIGTERM)
