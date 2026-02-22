"""Tests for hub lifecycle bootstrap helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMakeProcessor:
    def test_make_processor_returns_processor(self) -> None:
        from inkarms.hub.lifecycle import _make_processor
        from inkarms.platforms.sessions import PlatformSessionStore

        mock_cfg = MagicMock()
        mock_cfg.hub.tool_approval_mode = "auto"
        mock_cfg.providers.default = "test-model"
        session_store = MagicMock(spec=PlatformSessionStore)

        with (
            patch("inkarms.hub.lifecycle.MessageProcessor") as MockProcessor,
        ):
            MockProcessor.return_value = MagicMock()
            proc = _make_processor(mock_cfg, session_store)
            MockProcessor.assert_called_once()
            assert proc is MockProcessor.return_value

    def test_tool_approval_callback_auto(self) -> None:
        """tool_approval_callback returns True when mode is 'auto'."""
        from inkarms.hub.lifecycle import _make_processor

        mock_cfg = MagicMock()
        mock_cfg.hub.tool_approval_mode = "auto"

        captured_callback = None

        def capture_processor(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("tool_approval_callback")
            return MagicMock()

        with patch("inkarms.hub.lifecycle.MessageProcessor", side_effect=capture_processor):
            _make_processor(mock_cfg, MagicMock())

        assert captured_callback is not None
        assert captured_callback(MagicMock(), MagicMock()) is True

    def test_tool_approval_callback_disabled(self) -> None:
        """tool_approval_callback returns False when mode is 'disabled'."""
        from inkarms.hub.lifecycle import _make_processor

        mock_cfg = MagicMock()
        mock_cfg.hub.tool_approval_mode = "disabled"

        captured_callback = None

        def capture_processor(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("tool_approval_callback")
            return MagicMock()

        with patch("inkarms.hub.lifecycle.MessageProcessor", side_effect=capture_processor):
            _make_processor(mock_cfg, MagicMock())

        assert captured_callback(MagicMock(), MagicMock()) is False


class TestSupervisedListen:
    @pytest.mark.asyncio
    async def test_supervised_listen_clean_exit(self) -> None:
        """Supervised listen exits cleanly when router.listen_to_adapter returns normally."""
        from inkarms.hub.lifecycle import _supervised_listen

        mock_router = MagicMock()
        mock_router.listen_to_adapter = AsyncMock(return_value=None)
        mock_adapter = MagicMock()
        mock_adapter.platform_type.value = "test"

        # Should not raise; returns after listen_to_adapter completes
        await _supervised_listen(mock_router, mock_adapter)
        mock_router.listen_to_adapter.assert_called_once_with(mock_adapter)

    @pytest.mark.asyncio
    async def test_supervised_listen_cancelled(self) -> None:
        """CancelledError causes immediate exit without retry."""
        import asyncio
        from inkarms.hub.lifecycle import _supervised_listen

        mock_router = MagicMock()
        mock_router.listen_to_adapter = AsyncMock(side_effect=asyncio.CancelledError())
        mock_adapter = MagicMock()
        mock_adapter.platform_type.value = "test"

        # Should not raise CancelledError outward; just return
        await _supervised_listen(mock_router, mock_adapter)
        mock_router.listen_to_adapter.assert_called_once()

    @pytest.mark.asyncio
    async def test_supervised_listen_retries_on_crash(self) -> None:
        """Adapter crash triggers retries with back-off."""
        from inkarms.hub.lifecycle import _supervised_listen, _MAX_RETRIES

        call_count = 0

        async def crashing(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("crash")

        mock_router = MagicMock()
        mock_router.listen_to_adapter = crashing
        mock_adapter = MagicMock()
        mock_adapter.platform_type.value = "test"

        with patch("inkarms.hub.lifecycle.asyncio.sleep", new_callable=AsyncMock):
            await _supervised_listen(mock_router, mock_adapter)

        assert call_count == _MAX_RETRIES


class TestSessionIndexBridge:
    """Tests that MessageRouter writes platform sessions into hub.db session_index."""

    def _make_router_and_message(self):
        """Return a minimal (router, adapter, message) triple for _process_message tests."""
        from inkarms.platforms.router import MessageRouter
        from inkarms.models.platforms import IncomingMessage, PlatformType, PlatformUser

        mock_processor = MagicMock()
        mock_processor.process = AsyncMock(
            return_value=MagicMock(content="hi", error=None)
        )
        mock_session_mapper = MagicMock()
        mock_session_mapper.get_session_id.return_value = "tg_abc123"

        router = MessageRouter(
            processor=mock_processor,
            session_mapper=mock_session_mapper,
        )

        adapter = MagicMock()
        adapter.platform_type = PlatformType.TELEGRAM
        adapter.capabilities.supports_streaming = False
        adapter.capabilities.supports_typing_indicator = False
        adapter.send_message = AsyncMock()

        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="99",
            username="alice",
        )
        message = IncomingMessage(
            message_id="m1",
            content="hello",
            platform=PlatformType.TELEGRAM,
            user=user,
            metadata={"channel_id": "99"},
        )
        return router, adapter, message

    @pytest.mark.asyncio
    async def test_upsert_called_after_message_processed(self) -> None:
        """hub_db.upsert_session is called with correct args after a platform message."""
        router, adapter, message = self._make_router_and_message()

        with (
            patch("inkarms.hub.db.is_connected", return_value=True),
            patch("inkarms.hub.db.upsert_session", new_callable=AsyncMock) as mock_upsert,
        ):
            await router._process_message(adapter, message)

        mock_upsert.assert_called_once_with(
            session_id="tg_abc123",
            platform="telegram",
            platform_user_id="99",
            channel_id="99",
            display_name="alice",
            turn_count_delta=1,
        )

    @pytest.mark.asyncio
    async def test_upsert_skipped_when_hub_db_not_connected(self) -> None:
        """upsert_session is NOT called when hub.db is not open (CLI mode)."""
        router, adapter, message = self._make_router_and_message()

        with (
            patch("inkarms.hub.db.is_connected", return_value=False),
            patch("inkarms.hub.db.upsert_session", new_callable=AsyncMock) as mock_upsert,
        ):
            await router._process_message(adapter, message)

        mock_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_exception_does_not_abort_message_processing(self) -> None:
        """A failing upsert does not prevent the response being sent to the user."""
        router, adapter, message = self._make_router_and_message()

        with (
            patch("inkarms.hub.db.is_connected", return_value=True),
            patch("inkarms.hub.db.upsert_session", side_effect=RuntimeError("disk full")),
        ):
            await router._process_message(adapter, message)

        # Adapter.send_message must still have been called (response delivered)
        adapter.send_message.assert_called_once()


class TestCreateAdapters:
    def test_create_adapters_no_platforms_enabled(self) -> None:
        """Returns empty list when no platforms are enabled."""
        from inkarms.platforms.adapters import create_adapters

        cfg = MagicMock()
        cfg.platforms.telegram.enable = False
        cfg.platforms.slack.enable = False
        cfg.platforms.discord.enable = False

        adapters = create_adapters(cfg)
        assert adapters == []

    def test_create_adapters_uses_warn_callback(self) -> None:
        """Warning is passed to warn_callback, not logged internally."""
        from inkarms.platforms.adapters import create_adapters

        cfg = MagicMock()
        cfg.platforms.telegram.enable = True
        cfg.platforms.telegram.model_dump.return_value = {"bot_token": ""}
        cfg.platforms.slack.enable = False
        cfg.platforms.discord.enable = False

        warnings = []
        create_adapters(cfg, warn_callback=warnings.append)
        assert any("bot_token" in w or "Telegram" in w for w in warnings)
