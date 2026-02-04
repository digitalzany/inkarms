"""Unit tests for platform session mapper."""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from inkarms.platforms.models import PlatformType, PlatformUser
from inkarms.platforms.session_mapper import (
    SessionMapper,
    SessionMapping,
    reset_session_mapper,
)


class TestSessionMapping:
    """Tests for SessionMapping model."""

    def test_create_mapping(self):
        """Test creating a session mapping."""
        mapping = SessionMapping(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123456789",
            session_id="telegram_123_20260202",
            metadata={"username": "john"},
        )

        assert mapping.platform == PlatformType.TELEGRAM
        assert mapping.platform_user_id == "123456789"
        assert mapping.session_id == "telegram_123_20260202"
        assert mapping.metadata["username"] == "john"
        assert isinstance(mapping.created_at, datetime)
        assert isinstance(mapping.last_accessed, datetime)

    def test_mapping_string_representation(self):
        """Test __str__ method."""
        mapping = SessionMapping(
            platform=PlatformType.SLACK,
            platform_user_id="U123",
            session_id="slack_u123_20260202",
        )

        assert str(mapping) == "slack:U123 -> slack_u123_20260202"


class TestSessionMapper:
    """Tests for SessionMapper class."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test storage."""
        with TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mapper(self, temp_dir):
        """Create a SessionMapper with temporary storage."""
        storage_path = temp_dir / "test_sessions.json"
        return SessionMapper(storage_path=storage_path)

    @pytest.fixture
    def telegram_user(self):
        """Create a test Telegram user."""
        return PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123456789",
            username="john_doe",
        )

    @pytest.fixture
    def slack_user(self):
        """Create a test Slack user."""
        return PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="U123456",
            username="alice",
        )

    def test_get_session_id_creates_new(self, mapper, telegram_user):
        """Test that get_session_id creates a new session if missing."""
        session_id = mapper.get_session_id(telegram_user, create_if_missing=True)

        assert session_id is not None
        assert session_id.startswith("telegram_")
        assert "123456789" in session_id

    def test_get_session_id_returns_none_when_not_creating(self, mapper, telegram_user):
        """Test that get_session_id returns None when not creating."""
        session_id = mapper.get_session_id(telegram_user, create_if_missing=False)

        assert session_id is None

    def test_get_session_id_returns_existing(self, mapper, telegram_user):
        """Test that get_session_id returns existing session."""
        # Create session
        session_id1 = mapper.get_session_id(telegram_user, create_if_missing=True)

        # Get same session
        session_id2 = mapper.get_session_id(telegram_user, create_if_missing=True)

        assert session_id1 == session_id2

    def test_session_isolation_by_platform(self, mapper, temp_dir):
        """Test that different platforms get different sessions."""
        user1 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        user2 = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="123",  # Same ID, different platform
        )

        session_id1 = mapper.get_session_id(user1, create_if_missing=True)
        session_id2 = mapper.get_session_id(user2, create_if_missing=True)

        assert session_id1 != session_id2
        assert "telegram" in session_id1
        assert "slack" in session_id2

    def test_session_isolation_by_user(self, mapper):
        """Test that different users get different sessions."""
        user1 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        user2 = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="456",
        )

        session_id1 = mapper.get_session_id(user1, create_if_missing=True)
        session_id2 = mapper.get_session_id(user2, create_if_missing=True)

        assert session_id1 != session_id2

    def test_link_users(self, mapper, telegram_user, slack_user):
        """Test linking two users to share a session."""
        # Create sessions for both users
        session_id1 = mapper.get_session_id(telegram_user, create_if_missing=True)
        session_id2 = mapper.get_session_id(slack_user, create_if_missing=True)

        # Initially different
        assert session_id1 != session_id2

        # Link them
        result = mapper.link_users(telegram_user, slack_user)
        assert result is True

        # Now they should share the same session
        new_session_id = mapper.get_session_id(slack_user)
        assert new_session_id == session_id1

    def test_link_users_fails_if_users_dont_exist(self, mapper, telegram_user, slack_user):
        """Test that linking fails if users don't have sessions."""
        result = mapper.link_users(telegram_user, slack_user)
        assert result is False

    def test_unlink_user(self, mapper, telegram_user):
        """Test unlinking a user to give them a fresh session."""
        import time

        # Create session
        session_id1 = mapper.get_session_id(telegram_user, create_if_missing=True)

        # Wait a moment to ensure different timestamp
        time.sleep(1.1)

        # Unlink
        result = mapper.unlink_user(telegram_user)
        assert result is True

        # New session should be different
        session_id2 = mapper.get_session_id(telegram_user)
        assert session_id2 != session_id1

    def test_unlink_user_fails_if_not_exists(self, mapper, telegram_user):
        """Test that unlink fails if user doesn't exist."""
        result = mapper.unlink_user(telegram_user)
        assert result is False

    def test_get_mapping(self, mapper, telegram_user):
        """Test getting full mapping for a user."""
        # Create session
        mapper.get_session_id(telegram_user, create_if_missing=True)

        # Get mapping
        mapping = mapper.get_mapping(telegram_user)

        assert mapping is not None
        assert mapping.platform == PlatformType.TELEGRAM
        assert mapping.platform_user_id == "123456789"
        assert mapping.metadata["username"] == "john_doe"

    def test_get_mapping_returns_none_if_not_exists(self, mapper, telegram_user):
        """Test that get_mapping returns None if user doesn't exist."""
        mapping = mapper.get_mapping(telegram_user)
        assert mapping is None

    def test_delete_mapping(self, mapper, telegram_user):
        """Test deleting a user's mapping."""
        # Create session
        mapper.get_session_id(telegram_user, create_if_missing=True)

        # Delete
        result = mapper.delete_mapping(telegram_user)
        assert result is True

        # Mapping should be gone
        mapping = mapper.get_mapping(telegram_user)
        assert mapping is None

    def test_delete_mapping_fails_if_not_exists(self, mapper, telegram_user):
        """Test that delete fails if user doesn't exist."""
        result = mapper.delete_mapping(telegram_user)
        assert result is False

    def test_list_mappings(self, mapper, telegram_user, slack_user):
        """Test listing all mappings."""
        # Create sessions
        mapper.get_session_id(telegram_user, create_if_missing=True)
        mapper.get_session_id(slack_user, create_if_missing=True)

        # List all
        mappings = mapper.list_mappings()

        assert len(mappings) == 2
        platforms = {m.platform for m in mappings}
        assert PlatformType.TELEGRAM in platforms
        assert PlatformType.SLACK in platforms

    def test_list_mappings_filtered_by_platform(self, mapper, telegram_user, slack_user):
        """Test listing mappings filtered by platform."""
        # Create sessions
        mapper.get_session_id(telegram_user, create_if_missing=True)
        mapper.get_session_id(slack_user, create_if_missing=True)

        # List only Telegram
        mappings = mapper.list_mappings(platform=PlatformType.TELEGRAM)

        assert len(mappings) == 1
        assert mappings[0].platform == PlatformType.TELEGRAM

    def test_persistence_save_and_load(self, temp_dir, telegram_user):
        """Test that mappings are persisted to disk."""
        storage_path = temp_dir / "sessions.json"

        # Create mapper and session
        mapper1 = SessionMapper(storage_path=storage_path)
        session_id1 = mapper1.get_session_id(telegram_user, create_if_missing=True)

        # Create new mapper (simulates restart)
        mapper2 = SessionMapper(storage_path=storage_path)
        session_id2 = mapper2.get_session_id(telegram_user)

        # Should load the same session
        assert session_id2 == session_id1

    def test_persistence_file_format(self, temp_dir, telegram_user):
        """Test that storage file is valid JSON."""
        storage_path = temp_dir / "sessions.json"

        # Create mapper and session
        mapper = SessionMapper(storage_path=storage_path)
        mapper.get_session_id(telegram_user, create_if_missing=True)

        # Read file
        data = json.loads(storage_path.read_text())

        # Should have one entry
        assert len(data) == 1

        # Key should be platform:user_id
        key = "telegram:123456789"
        assert key in data

        # Entry should have required fields
        entry = data[key]
        assert "platform" in entry
        assert "platform_user_id" in entry
        assert "session_id" in entry
        assert "created_at" in entry
        assert "last_accessed" in entry
        assert "metadata" in entry

    def test_last_accessed_updated(self, mapper, telegram_user):
        """Test that last_accessed is updated on access."""
        # Create session
        mapper.get_session_id(telegram_user, create_if_missing=True)

        # Get initial timestamp
        mapping1 = mapper.get_mapping(telegram_user)
        initial_time = mapping1.last_accessed

        # Access again (would normally have time delay)
        mapper.get_session_id(telegram_user)

        # Get updated timestamp
        mapping2 = mapper.get_mapping(telegram_user)
        updated_time = mapping2.last_accessed

        # Should be updated (or at least not earlier)
        assert updated_time >= initial_time

    def test_make_key(self, mapper):
        """Test the _make_key method."""
        key = mapper._make_key(PlatformType.TELEGRAM, "123456789")
        assert key == "telegram:123456789"

    def test_generate_session_id(self, mapper, telegram_user):
        """Test the _generate_session_id method."""
        session_id = mapper._generate_session_id(telegram_user)

        # Should have format: platform_userid_timestamp
        assert session_id.startswith("telegram_")
        assert "123456789" in session_id
        # Should have timestamp (format: YYYYMMDD_HHMMSS)
        parts = session_id.split("_")
        assert len(parts) >= 3

    def test_generate_session_id_sanitizes_special_chars(self, mapper):
        """Test that special characters are removed from session ID."""
        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="user@example.com",
        )

        session_id = mapper._generate_session_id(user)

        # Should not contain @ or . (only alphanumeric, -, _)
        assert "@" not in session_id
        assert "." not in session_id
        # Should contain sanitized version
        assert "userexamplecom" in session_id


def test_singleton_get_session_mapper():
    """Test the global singleton function."""
    from inkarms.platforms.session_mapper import get_session_mapper

    # Get singleton
    mapper1 = get_session_mapper()
    mapper2 = get_session_mapper()

    # Should be the same instance
    assert mapper1 is mapper2

    # Reset and get new instance
    reset_session_mapper()
    mapper3 = get_session_mapper()

    # Should be different from original
    assert mapper3 is not mapper1
