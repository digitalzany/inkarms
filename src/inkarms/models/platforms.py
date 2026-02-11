"""Data models for multi-platform messaging."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PlatformType(str, Enum):
    """Supported messaging platforms."""

    CLI = "cli"
    TUI = "tui"
    TELEGRAM = "telegram"
    SLACK = "slack"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    IMESSAGE = "imessage"
    SIGNAL = "signal"
    TEAMS = "teams"
    WECHAT = "wechat"


class PlatformUser(BaseModel):
    """Represents a user on a specific platform."""

    platform: PlatformType
    platform_user_id: str  # Platform-specific user identifier
    username: Optional[str] = None
    display_name: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        """String representation for logging."""
        return f"{self.platform.value}:{self.platform_user_id}"


class PlatformCapabilities(BaseModel):
    """Describes what features a platform supports."""

    supports_streaming: bool = False
    supports_markdown: bool = False
    supports_html: bool = False
    supports_buttons: bool = False
    supports_attachments: bool = False
    supports_threads: bool = False
    supports_reactions: bool = False
    supports_typing_indicator: bool = False
    supports_message_editing: bool = False
    markdown_flavor: Optional[str] = None  # e.g., "MarkdownV2", "mrkdwn", "standard"
    max_message_length: Optional[int] = None


class IncomingMessage(BaseModel):
    """Represents a message received from a platform."""

    platform: PlatformType
    user: PlatformUser
    content: str
    message_id: str  # Platform-specific message identifier
    thread_id: Optional[str] = None  # For threaded conversations
    reply_to_message_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def __str__(self) -> str:
        """String representation for logging."""
        return f"[{self.platform.value}] {self.user}: {self.content[:50]}"


class OutgoingMessage(BaseModel):
    """Represents a message to be sent to a platform."""

    content: str
    format: str = "plain"  # "plain", "markdown", "html"
    thread_id: Optional[str] = None
    reply_to_message_id: Optional[str] = None
    buttons: list[dict[str, str]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamChunk(BaseModel):
    """Represents a chunk of streaming response."""

    content: str
    is_final: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
