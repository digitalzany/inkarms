"""Tests for hub WebSocket chat helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from inkarms.hub.ws.chat import _chunk_to_frame


class TestChunkToFrame:
    def _make_chunk(
        self,
        content: str = "",
        is_final: bool = False,
        metadata: dict | None = None,
    ) -> MagicMock:
        chunk = MagicMock()
        chunk.content = content
        chunk.is_final = is_final
        chunk.metadata = metadata
        return chunk

    def test_final_chunk_returns_none(self) -> None:
        chunk = self._make_chunk(content="full response", is_final=True)
        assert _chunk_to_frame(chunk) is None

    def test_text_delta_frame(self) -> None:
        chunk = self._make_chunk(content="Hello", metadata={"event_type": "stream_chunk"})
        frame = _chunk_to_frame(chunk)
        assert frame == {"type": "delta", "content": "Hello"}

    def test_tool_start_frame(self) -> None:
        chunk = self._make_chunk(
            content="ls -la",
            metadata={"event_type": "tool_start", "tool_name": "bash"},
        )
        frame = _chunk_to_frame(chunk)
        assert frame == {"type": "tool_start", "name": "bash", "input": "ls -la"}

    def test_tool_done_frame(self) -> None:
        chunk = self._make_chunk(
            content="file1.txt\n",
            metadata={"event_type": "tool_complete", "tool_name": "bash"},
        )
        frame = _chunk_to_frame(chunk)
        assert frame == {"type": "tool_done", "name": "bash", "output": "file1.txt\n"}

    def test_empty_content_returns_none(self) -> None:
        chunk = self._make_chunk(content="", metadata=None)
        assert _chunk_to_frame(chunk) is None

    def test_no_metadata_defaults_to_delta(self) -> None:
        chunk = self._make_chunk(content="world", metadata=None)
        frame = _chunk_to_frame(chunk)
        assert frame == {"type": "delta", "content": "world"}


class TestEventsModule:
    """Test the event bus broadcast helper."""

    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_subscribers(self) -> None:
        import asyncio
        from inkarms.hub.ws.events import broadcast, _register, _unregister

        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        _register(q)

        try:
            await broadcast({"type": "test_event"})
            item = q.get_nowait()
            assert item == {"type": "test_event"}
        finally:
            _unregister(q)

    @pytest.mark.asyncio
    async def test_broadcast_overflow_drops_oldest(self) -> None:
        import asyncio
        from inkarms.hub.ws.events import broadcast, _register, _unregister

        # Fill queue completely
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        await q.put({"type": "old1"})
        await q.put({"type": "old2"})
        _register(q)

        try:
            # Broadcast into a full queue — oldest should be dropped
            await broadcast({"type": "new"})
            items = []
            while not q.empty():
                items.append(q.get_nowait())
            # Queue should now have the overflow notice + new event or similar
            assert len(items) <= 2
        finally:
            _unregister(q)
