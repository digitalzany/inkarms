"""Platform adapter protocol definition."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    StreamChunk,
)

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """Abstract base class for platform adapters.

    Each platform (Telegram, Slack, Discord, etc.) implements this protocol
    to provide a unified interface for the message router.
    """

    def __init__(self) -> None:
        """Initialize the platform adapter."""
        self._running = False
        self._message_queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()

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

    async def receive_messages(self) -> AsyncIterator[IncomingMessage]:
        """Receive messages from the platform via the internal queue.

        Subclasses enqueue messages by calling ``self._message_queue.put()``.

        Yields:
            IncomingMessage objects as they arrive from the platform.
        """
        while self._running:
            try:
                message = await asyncio.wait_for(self._message_queue.get(), timeout=1.0)
                yield message
            except TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error receiving message: {e}", exc_info=True)

    @abstractmethod
    async def send_message(
        self,
        destination_id: str,
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a destination on this platform.

        Args:
            destination_id: Platform-specific identifier (chat_id, channel_id, etc.)
            message: The message to send

        Returns:
            Platform-specific message ID of the sent message
        """
        ...

    @abstractmethod
    async def send_streaming_chunk(
        self,
        destination_id: str,
        chunk: StreamChunk,
        message_id: str | None = None,
    ) -> str:
        """Send a streaming chunk to a destination.

        Args:
            destination_id: Platform-specific identifier
            chunk: The streaming chunk to send
            message_id: Existing message ID to update (if supported)

        Returns:
            Message ID (new or existing)
        """
        ...

    @abstractmethod
    def format_output(self, content: str, output_format: str) -> str:
        """Format content for this platform.

        Args:
            content: The content to format
            output_format: The format type ("plain", "markdown", "html")

        Returns:
            Platform-specific formatted content
        """
        ...

    async def send_typing_indicator(self, destination_id: str) -> None:
        """Send typing indicator (if supported).

        Args:
            destination_id: Platform-specific identifier
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
