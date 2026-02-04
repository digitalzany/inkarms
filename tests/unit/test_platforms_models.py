"""Unit tests for platform models and protocol."""

import pytest
from datetime import datetime

from inkarms.platforms.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
    StreamChunk,
)


class TestPlatformType:
    """Tests for PlatformType enum."""

    def test_platform_types(self):
        """Test all platform type values."""
        assert PlatformType.CLI.value == "cli"
        assert PlatformType.TELEGRAM.value == "telegram"
        assert PlatformType.SLACK.value == "slack"
        assert PlatformType.DISCORD.value == "discord"
        assert PlatformType.WHATSAPP.value == "whatsapp"
        assert PlatformType.IMESSAGE.value == "imessage"
        assert PlatformType.SIGNAL.value == "signal"
        assert PlatformType.TEAMS.value == "teams"
        assert PlatformType.WECHAT.value == "wechat"

    def test_platform_type_creation(self):
        """Test creating PlatformType from string."""
        platform = PlatformType("telegram")
        assert platform == PlatformType.TELEGRAM


class TestPlatformUser:
    """Tests for PlatformUser model."""

    def test_create_user(self):
        """Test creating a platform user."""
        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123456789",
            username="john_doe",
            display_name="John Doe",
        )

        assert user.platform == PlatformType.TELEGRAM
        assert user.platform_user_id == "123456789"
        assert user.username == "john_doe"
        assert user.display_name == "John Doe"

    def test_user_without_optional_fields(self):
        """Test creating user without optional fields."""
        user = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="U123456",
        )

        assert user.platform == PlatformType.SLACK
        assert user.platform_user_id == "U123456"
        assert user.username is None
        assert user.display_name is None

    def test_user_string_representation(self):
        """Test __str__ method."""
        user = PlatformUser(
            platform=PlatformType.DISCORD,
            platform_user_id="987654321",
            username="alice",
        )

        assert str(user) == "discord:987654321"

    def test_user_string_without_username(self):
        """Test __str__ when username is None."""
        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )

        assert str(user) == "telegram:123"


class TestPlatformCapabilities:
    """Tests for PlatformCapabilities model."""

    def test_full_capabilities(self):
        """Test creating capabilities with all features."""
        caps = PlatformCapabilities(
            supports_streaming=True,
            supports_markdown=True,
            supports_buttons=True,
            supports_attachments=True,
            supports_typing_indicator=True,
            markdown_flavor="MarkdownV2",
            max_message_length=4096,
        )

        assert caps.supports_streaming is True
        assert caps.supports_markdown is True
        assert caps.supports_buttons is True
        assert caps.supports_attachments is True
        assert caps.supports_typing_indicator is True
        assert caps.markdown_flavor == "MarkdownV2"
        assert caps.max_message_length == 4096

    def test_minimal_capabilities(self):
        """Test creating capabilities with minimal features."""
        caps = PlatformCapabilities(
            supports_streaming=False,
            supports_markdown=False,
        )

        assert caps.supports_streaming is False
        assert caps.supports_markdown is False
        assert caps.supports_buttons is False
        assert caps.supports_attachments is False
        assert caps.supports_typing_indicator is False
        assert caps.markdown_flavor is None
        assert caps.max_message_length is None


class TestIncomingMessage:
    """Tests for IncomingMessage model."""

    def test_create_message(self):
        """Test creating an incoming message."""
        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
            username="test_user",
        )

        msg = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=user,
            content="Hello, bot!",
            message_id="msg_123",
            timestamp=datetime(2026, 2, 2, 10, 30, 0),
            metadata={"chat_id": "456"},
        )

        assert msg.platform == PlatformType.TELEGRAM
        assert msg.user == user
        assert msg.content == "Hello, bot!"
        assert msg.message_id == "msg_123"
        assert msg.timestamp.year == 2026
        assert msg.metadata["chat_id"] == "456"

    def test_message_defaults(self):
        """Test message with default values."""
        user = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="U123",
        )

        msg = IncomingMessage(
            platform=PlatformType.SLACK,
            user=user,
            content="Test message",
            message_id="msg_123",
        )

        assert msg.platform == PlatformType.SLACK
        assert msg.user == user
        assert msg.content == "Test message"
        assert msg.message_id == "msg_123"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}


class TestOutgoingMessage:
    """Tests for OutgoingMessage model."""

    def test_create_message(self):
        """Test creating an outgoing message."""
        msg = OutgoingMessage(
            content="Hello, user!",
            format="markdown",
            buttons=[{"text": "Click me", "callback": "button_1"}],
            metadata={"thread_id": "789"},
        )

        assert msg.content == "Hello, user!"
        assert msg.format == "markdown"
        assert len(msg.buttons) == 1
        assert msg.buttons[0]["text"] == "Click me"
        assert msg.metadata["thread_id"] == "789"

    def test_message_defaults(self):
        """Test message with default values."""
        msg = OutgoingMessage(
            content="Simple message",
        )

        assert msg.content == "Simple message"
        assert msg.format == "plain"
        assert msg.buttons == []
        assert msg.metadata == {}


class TestStreamChunk:
    """Tests for StreamChunk model."""

    def test_create_chunk(self):
        """Test creating a stream chunk."""
        chunk = StreamChunk(
            content="Partial response...",
            is_final=False,
        )

        assert chunk.content == "Partial response..."
        assert chunk.is_final is False

    def test_final_chunk(self):
        """Test creating a final chunk."""
        chunk = StreamChunk(
            content="Complete response.",
            is_final=True,
        )

        assert chunk.content == "Complete response."
        assert chunk.is_final is True

    def test_chunk_defaults(self):
        """Test chunk with default values."""
        chunk = StreamChunk(content="Text")

        assert chunk.content == "Text"
        assert chunk.is_final is False
