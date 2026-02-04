"""CLI platform adapter.

This adapter treats the CLI as a platform, allowing it to use the
same MessageProcessor infrastructure as other platforms.
"""

from collections.abc import AsyncIterator
from typing import Optional

from inkarms.platforms.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    StreamChunk,
)
from inkarms.platforms.protocol import PlatformAdapter


class CLIAdapter(PlatformAdapter):
    """Platform adapter for CLI interface.

    This is a special adapter that doesn't maintain a persistent connection.
    It's used to provide a unified interface for CLI commands to use the
    MessageProcessor infrastructure.
    """

    def __init__(self) -> None:
        """Initialize CLI adapter."""
        super().__init__()
        self._capabilities = PlatformCapabilities(
            supports_streaming=True,
            supports_markdown=True,
            supports_html=False,
            supports_buttons=False,
            supports_attachments=False,
            supports_threads=False,
            supports_reactions=False,
            supports_typing_indicator=False,
            supports_message_editing=False,
            markdown_flavor="commonmark",
            max_message_length=None,
        )

    @property
    def platform_type(self) -> PlatformType:
        """The type of platform this adapter handles."""
        return PlatformType.CLI

    @property
    def capabilities(self) -> PlatformCapabilities:
        """The capabilities supported by this platform."""
        return self._capabilities

    async def start(self) -> None:
        """Start the platform adapter.

        For CLI, this is a no-op since CLI doesn't maintain a connection.
        """
        self._running = True

    async def stop(self) -> None:
        """Stop the platform adapter.

        For CLI, this is a no-op.
        """
        self._running = False

    async def receive_messages(self) -> AsyncIterator[IncomingMessage]:
        """Receive messages from the platform.

        For CLI, this is not used as CLI is command-based, not event-driven.
        This method exists only to satisfy the protocol.
        """
        # CLI doesn't receive messages in a streaming fashion
        # This method should not be called for CLI
        if False:  # pragma: no cover
            yield  # Make this an async generator

    async def send_message(
        self,
        user: str,
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a user on this platform.

        For CLI, this is not used as output is handled directly by the CLI command.
        This method exists only to satisfy the protocol.

        Args:
            user: Platform-specific user identifier
            message: The message to send

        Returns:
            Mock message ID
        """
        # CLI handles output directly, this method is not used
        return "cli-message-id"

    async def send_streaming_chunk(
        self,
        user: str,
        chunk: StreamChunk,
        message_id: Optional[str] = None,
    ) -> str:
        """Send a streaming chunk to a user.

        For CLI, this is not used as streaming is handled directly by the CLI command.

        Args:
            user: Platform-specific user identifier
            chunk: The streaming chunk to send
            message_id: Existing message ID to update

        Returns:
            Mock message ID
        """
        # CLI handles streaming directly, this method is not used
        return message_id or "cli-message-id"

    def format_output(self, content: str, format: str) -> str:
        """Format content for this platform.

        For CLI, we support markdown rendering via Rich.

        Args:
            content: The content to format
            format: The format type ("plain", "markdown", "html")

        Returns:
            Content as-is (formatting handled by Rich)
        """
        # CLI uses Rich for rendering, so we just pass through
        return content
