"""Message router service for multi-platform messaging."""

from __future__ import annotations

import asyncio
import logging

from inkarms.models.platforms import IncomingMessage, OutgoingMessage
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.processor import MessageProcessor
from inkarms.platforms.rate_limiter import RateLimiter, RateLimitExceeded
from inkarms.platforms.session_mapper import SessionMapper

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between platform adapters and the message processor.

    Handles the full message lifecycle:
    1. Receive message from adapter
    2. Resolve session via SessionMapper
    3. Check rate limit
    4. Send typing indicator
    5. Process via MessageProcessor (streaming or non-streaming)
    6. Deliver response back via adapter
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 100,
        processor: MessageProcessor | None = None,
        session_mapper: SessionMapper | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}
        self._tasks: set[asyncio.Task] = set()
        self._running = False
        self._max_concurrent_tasks = max_concurrent_tasks
        self._processor = processor
        self._session_mapper = session_mapper
        self._rate_limiter = rate_limiter
        self._semaphore: asyncio.Semaphore | None = None

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter with the router."""
        platform_name = adapter.platform_type.value
        if platform_name in self._adapters:
            raise ValueError(f"Adapter for {platform_name} already registered")

        self._adapters[platform_name] = adapter
        logger.info(f"Registered adapter for platform: {platform_name}")

    def unregister_adapter(self, platform_name: str) -> None:
        """Unregister a platform adapter."""
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

        for platform_name, adapter in self._adapters.items():
            try:
                await adapter.start()
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

        for task in self._tasks:
            task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        for platform_name, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info(f"Stopped adapter for {platform_name}")
            except Exception as e:
                logger.error(f"Failed to stop adapter for {platform_name}: {e}")

        logger.info("Message router stopped")

    async def _listen_to_adapter(self, adapter: PlatformAdapter) -> None:
        """Listen for messages from a platform adapter."""
        platform_name = adapter.platform_type.value
        logger.info(f"Listening for messages from {platform_name}")

        try:
            async for message in adapter.receive_messages():
                if not self._running:
                    break

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
        """Handle an incoming message with semaphore-limited concurrency."""
        if self._semaphore:
            async with self._semaphore:
                await self._process_message(adapter, message)
        else:
            await self._process_message(adapter, message)

    def _resolve_destination(self, message: IncomingMessage) -> str:
        """Resolve the destination_id for sending replies."""
        return message.metadata.get("channel_id", message.user.platform_user_id)

    async def _process_message(
        self, adapter: PlatformAdapter, message: IncomingMessage
    ) -> None:
        """Process a message through the full lifecycle."""
        destination_id = self._resolve_destination(message)

        # Resolve session
        session_id = None
        if self._session_mapper:
            session_id = self._session_mapper.get_session_id(
                message.user, create_if_missing=True,
            )

        # Check rate limit
        if self._rate_limiter:
            try:
                await self._rate_limiter.check_limit(message.user)
            except RateLimitExceeded:
                logger.warning(f"Rate limit exceeded for {message.user}")
                await adapter.send_message(
                    destination_id,
                    OutgoingMessage(
                        content="Rate limit exceeded. Please wait before sending more messages.",
                        format="plain",
                    ),
                )
                return

        # Send typing indicator if supported
        if adapter.capabilities.supports_typing_indicator:
            await adapter.send_typing_indicator(destination_id)

        # If no processor, just log and return
        if not self._processor:
            logger.info(f"No processor configured, ignoring message: {message.message_id}")
            return

        try:
            if adapter.capabilities.supports_streaming:
                await self._process_streaming(adapter, message, destination_id, session_id)
            else:
                await self._process_non_streaming(adapter, message, destination_id, session_id)
        except Exception as e:
            logger.error(f"Failed to process message: {e}", exc_info=True)

    async def _process_streaming(
        self,
        adapter: PlatformAdapter,
        message: IncomingMessage,
        destination_id: str,
        session_id: str | None,
    ) -> None:
        """Process a message with streaming response."""
        message_id = None
        async for chunk in self._processor.process_streaming(
            query=message.content,
            session_id=session_id,
            platform=message.platform,
            platform_user_id=message.user.platform_user_id,
            platform_username=message.user.username,
        ):
            message_id = await adapter.send_streaming_chunk(
                destination_id, chunk, message_id,
            )

    async def _process_non_streaming(
        self,
        adapter: PlatformAdapter,
        message: IncomingMessage,
        destination_id: str,
        session_id: str | None,
    ) -> None:
        """Process a message with non-streaming response."""
        response = await self._processor.process(
            query=message.content,
            session_id=session_id,
            platform=message.platform,
            platform_user_id=message.user.platform_user_id,
            platform_username=message.user.username,
        )

        if response.error:
            await adapter.send_message(
                destination_id,
                OutgoingMessage(content=f"Error: {response.error}", format="plain"),
            )
        else:
            await adapter.send_message(
                destination_id,
                OutgoingMessage(content=response.content, format="markdown"),
            )

    def get_adapter(self, platform_name: str) -> PlatformAdapter | None:
        """Get an adapter by platform name."""
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
        """Check health of all adapters."""
        health = {}
        for platform_name, adapter in self._adapters.items():
            try:
                health[platform_name] = await adapter.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {platform_name}: {e}")
                health[platform_name] = False
        return health
