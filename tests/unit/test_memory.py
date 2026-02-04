"""
Unit tests for the InkArms memory system.
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from inkarms.memory import (
    CompactionStrategy,
    ContextTracker,
    ContextUsage,
    ConversationTurn,
    HandoffDocument,
    HandoffManager,
    MemoryEntry,
    MemoryStorage,
    MemoryType,
    Session,
    SessionMetadata,
    SessionManager,
    SlidingWindowCompactor,
    Snapshot,
    TokenCounter,
    TruncateCompactor,
    TurnRole,
    get_compactor,
)


# =============================================================================
# Model Tests
# =============================================================================


class TestConversationTurn:
    """Tests for ConversationTurn model."""

    def test_create_user_turn(self):
        """Test creating a user turn."""
        turn = ConversationTurn(
            role=TurnRole.USER,
            content="Hello, world!",
        )
        assert turn.role == TurnRole.USER
        assert turn.content == "Hello, world!"
        assert turn.token_count == 0
        assert turn.is_compacted is False

    def test_to_message_dict(self):
        """Test conversion to message dict."""
        turn = ConversationTurn(
            role=TurnRole.ASSISTANT,
            content="Hi there!",
        )
        msg = turn.to_message_dict()
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hi there!"


class TestSession:
    """Tests for Session model."""

    def test_create_empty_session(self):
        """Test creating an empty session."""
        session = Session()
        assert len(session.turns) == 0
        assert session.system_prompt is None
        assert session.metadata.turn_count == 0

    def test_add_user_message(self):
        """Test adding a user message."""
        session = Session()
        turn = session.add_user_message("Hello!", token_count=5)
        assert len(session.turns) == 1
        assert turn.role == TurnRole.USER
        assert turn.content == "Hello!"
        assert turn.token_count == 5

    def test_add_assistant_message(self):
        """Test adding an assistant message."""
        session = Session()
        turn = session.add_assistant_message(
            "Hi!",
            token_count=3,
            model="test-model",
            cost=0.001,
        )
        assert len(session.turns) == 1
        assert turn.role == TurnRole.ASSISTANT
        assert turn.model == "test-model"
        assert turn.cost == 0.001
        assert session.metadata.total_cost == 0.001

    def test_get_messages(self):
        """Test getting messages for LLM."""
        session = Session()
        session.system_prompt = "You are helpful."
        session.add_user_message("Hello!")
        session.add_assistant_message("Hi!")

        messages = session.get_messages(include_system=True)
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"

    def test_get_messages_without_system(self):
        """Test getting messages without system prompt."""
        session = Session()
        session.system_prompt = "You are helpful."
        session.add_user_message("Hello!")

        messages = session.get_messages(include_system=False)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_get_recent_turns(self):
        """Test getting recent turns."""
        session = Session()
        for i in range(10):
            session.add_user_message(f"Message {i}")

        recent = session.get_recent_turns(3)
        assert len(recent) == 3
        assert recent[0].content == "Message 7"
        assert recent[2].content == "Message 9"


class TestContextUsage:
    """Tests for ContextUsage model."""

    def test_usage_percent(self):
        """Test usage percentage calculation."""
        usage = ContextUsage(
            current_tokens=50000,
            max_tokens=100000,
        )
        assert usage.usage_percent == 0.5

    def test_should_compact(self):
        """Test compact threshold detection."""
        usage = ContextUsage(
            current_tokens=75000,
            max_tokens=100000,
            compact_threshold=0.70,
        )
        assert usage.should_compact is True

    def test_should_handoff(self):
        """Test handoff threshold detection."""
        usage = ContextUsage(
            current_tokens=90000,
            max_tokens=100000,
            handoff_threshold=0.85,
        )
        assert usage.should_handoff is True

    def test_tokens_remaining(self):
        """Test remaining tokens calculation."""
        usage = ContextUsage(
            current_tokens=30000,
            max_tokens=100000,
        )
        assert usage.tokens_remaining == 70000

    def test_format_status(self):
        """Test status formatting."""
        usage = ContextUsage(
            current_tokens=50000,
            max_tokens=100000,
        )
        status = usage.format_status()
        assert "50,000" in status
        assert "100,000" in status
        assert "50.0%" in status


# =============================================================================
# Context Tracker Tests
# =============================================================================


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_text(self):
        """Test counting tokens in text."""
        counter = TokenCounter()
        count = counter.count("Hello, world!")
        assert count > 0

    def test_count_empty_text(self):
        """Test counting empty text."""
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_count_messages(self):
        """Test counting tokens in messages."""
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        count = counter.count_messages(messages)
        assert count > 0


class TestContextTracker:
    """Tests for ContextTracker."""

    def test_count_text(self):
        """Test text token counting."""
        tracker = ContextTracker()
        count = tracker.count_text("Hello, world!")
        assert count > 0

    def test_set_system_prompt(self):
        """Test setting system prompt."""
        tracker = ContextTracker()
        tokens = tracker.set_system_prompt("You are a helpful assistant.")
        assert tokens > 0
        assert tracker.usage.current_tokens == tokens

    def test_track_session(self):
        """Test tracking a session."""
        tracker = ContextTracker()
        session = Session()
        session.system_prompt = "Be helpful."
        session.add_user_message("Hello!")
        session.add_assistant_message("Hi!")

        usage = tracker.track_session(session)
        assert usage.current_tokens > 0

    def test_can_fit(self):
        """Test checking if tokens can fit."""
        tracker = ContextTracker(model="default")
        assert tracker.can_fit(1000) is True
        assert tracker.can_fit(999999999) is False


# =============================================================================
# Compaction Tests
# =============================================================================


class TestTruncateCompactor:
    """Tests for TruncateCompactor."""

    @pytest.mark.asyncio
    async def test_compact_basic(self):
        """Test basic truncation."""
        compactor = TruncateCompactor(preserve_recent=2)

        session = Session()
        for i in range(10):
            session.add_user_message(f"Message {i}")

        compacted = await compactor.compact(session)
        assert len(compacted.turns) < len(session.turns)
        # Recent turns should be preserved
        assert compacted.turns[-1].content == "Message 9"

    @pytest.mark.asyncio
    async def test_compact_preserves_recent(self):
        """Test that recent turns are preserved."""
        compactor = TruncateCompactor(preserve_recent=5)

        session = Session()
        for i in range(10):
            session.add_user_message(f"Message {i}")

        compacted = await compactor.compact(session)
        # Last 5 should be preserved
        assert compacted.turns[-1].content == "Message 9"
        assert compacted.turns[-5].content == "Message 5"


class TestSlidingWindowCompactor:
    """Tests for SlidingWindowCompactor."""

    @pytest.mark.asyncio
    async def test_sliding_window(self):
        """Test sliding window compaction."""
        compactor = SlidingWindowCompactor(window_size=5, preserve_recent=2)

        session = Session()
        for i in range(20):
            session.add_user_message(f"Message {i}")

        compacted = await compactor.compact(session)
        assert len(compacted.turns) == 5
        assert compacted.turns[-1].content == "Message 19"


class TestGetCompactor:
    """Tests for compactor factory."""

    def test_get_truncate_compactor(self):
        """Test getting truncate compactor."""
        compactor = get_compactor(CompactionStrategy.TRUNCATE)
        assert isinstance(compactor, TruncateCompactor)

    def test_get_sliding_window_compactor(self):
        """Test getting sliding window compactor."""
        compactor = get_compactor(CompactionStrategy.SLIDING_WINDOW, window_size=10)
        assert isinstance(compactor, SlidingWindowCompactor)

    def test_get_compactor_by_string(self):
        """Test getting compactor by string name."""
        compactor = get_compactor("truncate")
        assert isinstance(compactor, TruncateCompactor)


# =============================================================================
# Storage Tests
# =============================================================================


class TestMemoryStorage:
    """Tests for MemoryStorage."""

    def test_save_and_load_daily_session(self):
        """Test saving and loading daily session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            session = Session()
            session.add_user_message("Hello!")
            session.add_assistant_message("Hi!")

            path = storage.save_daily_session(session)
            assert path.exists()

            loaded = storage.load_daily_session()
            assert loaded is not None
            assert len(loaded.turns) == 2

    def test_save_and_load_snapshot(self):
        """Test saving and loading snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            session = Session()
            session.add_user_message("Test message")

            snapshot = Snapshot(
                name="test-snapshot",
                description="A test snapshot",
                session=session,
            )

            path = storage.save_snapshot(snapshot)
            assert path.exists()

            loaded = storage.load_snapshot("test-snapshot")
            assert loaded is not None
            assert loaded.name == "test-snapshot"
            assert len(loaded.session.turns) == 1

    def test_delete_snapshot(self):
        """Test deleting snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            session = Session()
            snapshot = Snapshot(name="to-delete", session=session)
            storage.save_snapshot(snapshot)

            assert storage.delete_snapshot("to-delete") is True
            assert storage.delete_snapshot("to-delete") is False

    def test_save_and_load_handoff(self):
        """Test saving and loading handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            handoff = HandoffDocument(
                session_id="test-session",
                summary="Test summary",
                key_decisions=["Decision 1"],
                pending_tasks=["Task 1"],
            )

            path = storage.save_handoff(handoff)
            assert path.exists()

            loaded = storage.load_latest_handoff()
            assert loaded is not None
            assert loaded.summary == "Test summary"

    def test_list_all_memories(self):
        """Test listing all memory entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            # Create some entries
            session = Session()
            session.add_user_message("Test")
            storage.save_daily_session(session)

            snapshot = Snapshot(name="test-snap", session=session)
            storage.save_snapshot(snapshot)

            entries = storage.list_all()
            assert len(entries) >= 2

    def test_list_by_type(self):
        """Test listing by type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)

            session = Session()
            storage.save_daily_session(session)

            snapshot = Snapshot(name="test", session=session)
            storage.save_snapshot(snapshot)

            daily = storage.list_all(MemoryType.DAILY)
            assert all(e.memory_type == MemoryType.DAILY for e in daily)

            snapshots = storage.list_all(MemoryType.SNAPSHOT)
            assert all(e.memory_type == MemoryType.SNAPSHOT for e in snapshots)


# =============================================================================
# Handoff Tests
# =============================================================================


class TestHandoffManager:
    """Tests for HandoffManager."""

    @pytest.mark.asyncio
    async def test_create_handoff(self):
        """Test creating a handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)
            manager = HandoffManager(storage=storage)

            session = Session()
            session.add_user_message("Hello!")
            session.add_assistant_message("Hi!")

            handoff = await manager.create_handoff(session)
            assert handoff.session_id == session.id
            assert len(handoff.recent_turns) > 0

    def test_check_for_handoff(self):
        """Test checking for pending handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)
            manager = HandoffManager(storage=storage)

            # No handoff initially
            assert manager.check_for_handoff() is None

            # Create a handoff
            handoff = HandoffDocument(
                session_id="test",
                summary="Test",
            )
            storage.save_handoff(handoff)

            # Should find it
            found = manager.check_for_handoff()
            assert found is not None

    @pytest.mark.asyncio
    async def test_recover_from_handoff(self):
        """Test recovering from handoff."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = MemoryStorage(tmpdir)
            manager = HandoffManager(storage=storage)

            # Create handoff
            handoff = HandoffDocument(
                session_id="test",
                summary="Test summary",
                recent_turns=[
                    ConversationTurn(role=TurnRole.USER, content="Hello!"),
                ],
            )
            storage.save_handoff(handoff)

            # Recover
            session = await manager.recover_from_handoff(archive=False)
            assert len(session.turns) > 0


# =============================================================================
# Session Manager Tests
# =============================================================================


class TestSessionManager:
    """Tests for SessionManager."""

    def test_create_session(self):
        """Test creating a session manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock config
            import inkarms.memory.manager as manager_module

            original_config = manager_module.get_config

            def mock_get_config():
                from inkarms.config.schema import Config

                return Config()

            manager_module.get_config = mock_get_config

            # Mock storage path
            import inkarms.memory.storage as storage_module

            original_get_memory_dir = storage_module.get_memory_dir
            storage_module.get_memory_dir = lambda: Path(tmpdir)

            try:
                manager = SessionManager(storage_path=tmpdir)
                assert manager.session is not None

            finally:
                manager_module.get_config = original_config
                storage_module.get_memory_dir = original_get_memory_dir

    def test_add_messages(self):
        """Test adding messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.memory.manager as manager_module

            original_config = manager_module.get_config

            def mock_get_config():
                from inkarms.config.schema import Config

                return Config()

            manager_module.get_config = mock_get_config

            import inkarms.memory.storage as storage_module

            original_get_memory_dir = storage_module.get_memory_dir
            storage_module.get_memory_dir = lambda: Path(tmpdir)

            try:
                manager = SessionManager(storage_path=tmpdir)
                manager.add_user_message("Hello!")
                manager.add_assistant_message("Hi!", model="test", cost=0.001)

                assert len(manager.session.turns) == 2
                assert manager.session.metadata.total_cost == 0.001

            finally:
                manager_module.get_config = original_config
                storage_module.get_memory_dir = original_get_memory_dir

    def test_get_context_usage(self):
        """Test getting context usage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.memory.manager as manager_module

            original_config = manager_module.get_config

            def mock_get_config():
                from inkarms.config.schema import Config

                return Config()

            manager_module.get_config = mock_get_config

            import inkarms.memory.storage as storage_module

            original_get_memory_dir = storage_module.get_memory_dir
            storage_module.get_memory_dir = lambda: Path(tmpdir)

            try:
                manager = SessionManager(storage_path=tmpdir)
                manager.add_user_message("Hello!")

                usage = manager.get_context_usage()
                assert usage.current_tokens > 0

            finally:
                manager_module.get_config = original_config
                storage_module.get_memory_dir = original_get_memory_dir

    def test_save_and_load_snapshot(self):
        """Test saving and loading snapshots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.memory.manager as manager_module

            original_config = manager_module.get_config

            def mock_get_config():
                from inkarms.config.schema import Config

                return Config()

            manager_module.get_config = mock_get_config

            import inkarms.memory.storage as storage_module

            original_get_memory_dir = storage_module.get_memory_dir
            storage_module.get_memory_dir = lambda: Path(tmpdir)

            try:
                manager = SessionManager(storage_path=tmpdir)
                manager.add_user_message("Test message")

                path = manager.save_snapshot("test-snapshot", description="Test")
                assert path.exists()

                # Clear and reload
                manager.clear_session()
                assert len(manager.session.turns) == 0

                loaded = manager.load_snapshot("test-snapshot")
                assert loaded is not None
                assert len(loaded.turns) == 1

            finally:
                manager_module.get_config = original_config
                storage_module.get_memory_dir = original_get_memory_dir


# =============================================================================
# Integration Tests
# =============================================================================


class TestMemoryIntegration:
    """Integration tests for the memory system."""

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete memory workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import inkarms.memory.manager as manager_module

            original_config = manager_module.get_config

            def mock_get_config():
                from inkarms.config.schema import Config

                return Config()

            manager_module.get_config = mock_get_config

            import inkarms.memory.storage as storage_module

            original_get_memory_dir = storage_module.get_memory_dir
            storage_module.get_memory_dir = lambda: Path(tmpdir)

            try:
                # Create session manager
                manager = SessionManager(storage_path=tmpdir)

                # Add some messages
                manager.add_user_message("What is 2 + 2?")
                manager.add_assistant_message("2 + 2 = 4", model="test", cost=0.001)
                manager.add_user_message("What about 3 + 3?")
                manager.add_assistant_message("3 + 3 = 6", model="test", cost=0.001)

                # Check context
                usage = manager.get_context_usage()
                assert usage.current_tokens > 0

                # Save snapshot
                manager.save_snapshot("math-session", description="Math questions")

                # List memory
                entries = manager.list_memory()
                assert len(entries) > 0

                # Get session info
                info = manager.get_session_info()
                assert info["turn_count"] == 4
                assert info["total_cost"] == 0.002

            finally:
                manager_module.get_config = original_config
                storage_module.get_memory_dir = original_get_memory_dir
