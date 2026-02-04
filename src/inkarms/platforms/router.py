"""Message router service for multi-platform messaging."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Optional

from inkarms.platforms.models import IncomingMessage, OutgoingMessage, StreamChunk
from inkarms.platforms.protocol import PlatformAdapter

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between platform adapters and the message processor.

    The router:
    1. Manages multiple platform adapters
    2. Routes incoming messages to the processor
    3. Handles concurrent message processing
    4. Delivers responses back to appropriate platforms
    5. Supports both streaming and non-streaming responses
    """

    def __init__(self, max_concurrent_tasks: int = 100) -> None:
        """Initialize the message router.

        Args:
            max_concurrent_tasks: Maximum number of concurrent message processing tasks
        """
        self._adapters: dict[str, PlatformAdapter] = {}
        self._tasks: set[asyncio.Task] = set()
        self._running = False
        self._max_concurrent_tasks = max_concurrent_tasks
        self._semaphore: Optional[asyncio.Semaphore] = None

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter with the router.

        Args:
            adapter: The platform adapter to register

        Raises:
            ValueError: If an adapter for this platform is already registered
        """
        platform_name = adapter.platform_type.value
        if platform_name in self._adapters:
            raise ValueError(f"Adapter for {platform_name} already registered")

        self._adapters[platform_name] = adapter
        logger.info(f"Registered adapter for platform: {platform_name}")

    def unregister_adapter(self, platform_name: str) -> None:
        """Unregister a platform adapter.

        Args:
            platform_name: The name of the platform to unregister
        """
        if platform_name in self._adapters:
            del self._adapters[platform_name]
            logger.info(f"Unregistered adapter for platform: {platform_name}")

    async def start(self) -> None:
        """Start the message router and all registered adapters."""
        if self._running:
            logger.warning("Router is already running")
            return

        self._running = True
        self._semaphore = asyncio.Semaphore(self._max_concurrent_tasks)
        logger.info("Starting message router")

        # Start all registered adapters
        for platform_name, adapter in self._adapters.items():
            try:
                await adapter.start()
                # Create a task to listen for messages from this adapter
                task = asyncio.create_task(
                    self._listen_to_adapter(adapter), name=f"listen-{platform_name}"
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
                logger.info(f"Started adapter for {platform_name}")
            except Exception as e:
                logger.error(f"Failed to start adapter for {platform_name}: {e}")

        logger.info(f"Message router started with {len(self._adapters)} adapters")

    async def stop(self) -> None:
        """Stop the message router and all registered adapters."""
        if not self._running:
            logger.warning("Router is not running")
            return

        logger.info("Stopping message router")
        self._running = False

        # Cancel all running tasks
        for task in self._tasks:
            task.cancel()

        # Wait for all tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop all adapters
        for platform_name, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info(f"Stopped adapter for {platform_name}")
            except Exception as e:
                logger.error(f"Failed to stop adapter for {platform_name}: {e}")

        logger.info("Message router stopped")

    async def _listen_to_adapter(self, adapter: PlatformAdapter) -> None:
        """Listen for messages from a platform adapter.

        Args:
            adapter: The adapter to listen to
        """
        platform_name = adapter.platform_type.value
        logger.info(f"Listening for messages from {platform_name}")

        try:
            async for message in adapter.receive_messages():
                if not self._running:
                    break

                # Create a task to handle this message
                task = asyncio.create_task(
                    self._handle_message(adapter, message),
                    name=f"handle-{platform_name}-{message.message_id}",
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        except asyncio.CancelledError:
            logger.info(f"Stopped listening to {platform_name}")
        except Exception as e:
            logger.error(f"Error listening to {platform_name}: {e}", exc_info=True)

    async def _handle_message(
        self, adapter: PlatformAdapter, message: IncomingMessage
    ) -> None:
        """Handle an incoming message from a platform.

        This method is meant to be overridden or have a processor injected.
        For now, it's a placeholder that logs the message.

        Args:
            adapter: The adapter that received the message
            message: The incoming message
        """
        # Acquire semaphore to limit concurrent processing
        if self._semaphore:
            async with self._semaphore:
                await self._process_message(adapter, message)
        else:
            await self._process_message(adapter, message)

    async def _process_message(
        self, adapter: PlatformAdapter, message: IncomingMessage
    ) -> None:
        """Process a message (placeholder for now).

        This will be connected to the MessageProcessor in the next task.

        Args:
            adapter: The adapter that received the message
            message: The incoming message
        """
        logger.info(f"Received message: {message}")

        # Placeholder: Echo the message back
        # This will be replaced with actual message processing
        response = OutgoingMessage(
            content=f"Received: {message.content}",
            format="plain",
            thread_id=message.thread_id,
            reply_to_message_id=message.message_id,
        )

        try:
            await adapter.send_message(message.user.platform_user_id, response)
        except Exception as e:
            logger.error(f"Failed to send response: {e}", exc_info=True)

    async def send_streaming_response(
        self,
        adapter: PlatformAdapter,
        user_id: str,
        chunks: AsyncIterator[StreamChunk],
        thread_id: Optional[str] = None,
    ) -> None:
        """Send a streaming response to a user.

        Args:
            adapter: The adapter to send through
            user_id: Platform-specific user identifier
            chunks: Async iterator of streaming chunks
            thread_id: Optional thread ID for threaded platforms
        """
        message_id: Optional[str] = None

        try:
            async for chunk in chunks:
                message_id = await adapter.send_streaming_chunk(user_id, chunk, message_id)

                # If this is the final chunk and we haven't created a message yet,
                # send it as a regular message
                if chunk.is_final and message_id is None:
                    response = OutgoingMessage(
                        content=chunk.content, format="plain", thread_id=thread_id
                    )
                    await adapter.send_message(user_id, response)

        except Exception as e:
            logger.error(f"Error sending streaming response: {e}", exc_info=True)

    async def send_response(
        self,
        adapter: PlatformAdapter,
        user_id: str,
        message: OutgoingMessage,
    ) -> None:
        """Send a non-streaming response to a user.

        Args:
            adapter: The adapter to send through
            user_id: Platform-specific user identifier
            message: The message to send
        """
        try:
            await adapter.send_message(user_id, message)
        except Exception as e:
            logger.error(f"Error sending response: {e}", exc_info=True)

    def get_adapter(self, platform_name: str) -> Optional[PlatformAdapter]:
        """Get an adapter by platform name.

        Args:
            platform_name: The name of the platform

        Returns:
            The adapter, or None if not found
        """
        return self._adapters.get(platform_name)

    @property
    def is_running(self) -> bool:
        """Check if the router is running."""
        return self._running

    @property
    def active_platforms(self) -> list[str]:
        """Get list of active platform names."""
        return list(self._adapters.keys())

    async def health_check(self) -> dict[str, bool]:
        """Check health of all adapters.

        Returns:
            Dict mapping platform names to health status
        """
        health = {}
        for platform_name, adapter in self._adapters.items():
            try:
                health[platform_name] = await adapter.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {platform_name}: {e}")
                health[platform_name] = False
        return health
