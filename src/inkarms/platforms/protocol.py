"""Platform adapter protocol definition."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Optional

from inkarms.platforms.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    StreamChunk,
)


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters.

    Each platform (Telegram, Slack, Discord, etc.) implements this protocol
    to provide a unified interface for the message router.
    """

    def __init__(self) -> None:
        """Initialize the platform adapter."""
        self._running = False

    @property
    @abstractmethod
    def platform_type(self) -> PlatformType:
        """The type of platform this adapter handles."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> PlatformCapabilities:
        """The capabilities supported by this platform."""
        ...

    @property
    def is_running(self) -> bool:
        """Check if the adapter is currently running."""
        return self._running

    @abstractmethod
    async def start(self) -> None:
        """Start the platform adapter.

        This method should:
        1. Initialize platform-specific clients/connections
        2. Set up webhooks or polling as needed
        3. Begin listening for incoming messages
        4. Set self._running = True
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the platform adapter.

        This method should:
        1. Clean up connections
        2. Stop webhooks/polling
        3. Flush any pending messages
        4. Set self._running = False
        """
        ...

    @abstractmethod
    async def receive_messages(self) -> AsyncIterator[IncomingMessage]:
        """Receive messages from the platform.

        Yields:
            IncomingMessage objects as they arrive from the platform.

        This is an async generator that should:
        1. Listen for incoming messages from the platform
        2. Convert platform-specific messages to IncomingMessage
        3. Yield messages as they arrive
        4. Handle platform-specific errors gracefully
        """
        ...

    @abstractmethod
    async def send_message(
        self,
        user: str,  # Platform-specific user identifier
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a user on this platform.

        Args:
            user: Platform-specific user identifier (e.g., Telegram chat_id)
            message: The message to send

        Returns:
            Platform-specific message ID of the sent message

        Raises:
            Exception: If sending fails
        """
        ...

    @abstractmethod
    async def send_streaming_chunk(
        self,
        user: str,
        chunk: StreamChunk,
        message_id: Optional[str] = None,
    ) -> str:
        """Send a streaming chunk to a user.

        For platforms that support message editing, this should update
        an existing message. For platforms that don't, this should send
        a new message or buffer chunks.

        Args:
            user: Platform-specific user identifier
            chunk: The streaming chunk to send
            message_id: Existing message ID to update (if supported)

        Returns:
            Message ID (new or existing)

        Raises:
            Exception: If sending fails
        """
        ...

    @abstractmethod
    def format_output(self, content: str, format: str) -> str:
        """Format content for this platform.

        Converts generic markdown/html to platform-specific formatting.

        Args:
            content: The content to format
            format: The format type ("plain", "markdown", "html")

        Returns:
            Platform-specific formatted content
        """
        ...

    async def send_typing_indicator(self, user: str) -> None:
        """Send typing indicator to user (if supported).

        Args:
            user: Platform-specific user identifier

        Default implementation does nothing. Platforms that support
        typing indicators should override this.
        """
        pass

    async def health_check(self) -> bool:
        """Check if the platform connection is healthy.

        Returns:
            True if healthy, False otherwise

        Default implementation returns True. Platforms can override
        to implement specific health checks.
        """
        return self._running
