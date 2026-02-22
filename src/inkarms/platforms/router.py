"""Message router service for multi-platform messaging."""

from __future__ import annotations

import asyncio
import logging
import uuid

from inkarms.commands import CommandContext, CommandRegistry
from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformUser,
    StreamChunk,
)
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.processor import MessageProcessor
from inkarms.platforms.rate_limiter import RateLimiter, RateLimitExceeded
from inkarms.platforms.session_mapper import SessionMapper
from inkarms.platforms.sessions import PlatformSessionStore

logger = logging.getLogger(__name__)


class MessageRouter:
    """Routes messages between platform adapters and the message processor.

    Handles the full message lifecycle:
    1. Receive message from adapter
    2. Resolve session via SessionMapper (per-channel)
    3. Check rate limit
    4. Send typing indicator
    5. Process via MessageProcessor (streaming or non-streaming)
    6. Deliver response back via adapter

    Also provides a command callback for adapters that support slash commands.
    """

    def __init__(
        self,
        max_concurrent_tasks: int = 100,
        processor: MessageProcessor | None = None,
        session_mapper: SessionMapper | None = None,
        rate_limiter: RateLimiter | None = None,
        session_store: PlatformSessionStore | None = None,
    ) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}
        self._tasks: set[asyncio.Task] = set()
        self._running = False
        self._max_concurrent_tasks = max_concurrent_tasks
        self._processor = processor
        self._session_mapper = session_mapper
        self._rate_limiter = rate_limiter
        self._session_store = session_store or PlatformSessionStore()
        self._semaphore: asyncio.Semaphore | None = None

    def register_adapter(self, adapter: PlatformAdapter) -> None:
        """Register a platform adapter with the router.

        Automatically injects the command callback into adapters that
        support it (e.g. TelegramAdapter).
        """
        platform_name = adapter.platform_type.value
        if platform_name in self._adapters:
            raise ValueError(f"Adapter for {platform_name} already registered")

        # Inject command callback if the adapter supports it
        if hasattr(adapter, "set_command_callback"):
            adapter.set_command_callback(self.handle_command)

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
                    self.listen_to_adapter(adapter), name=f"listen-{platform_name}"
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

        # Save all sessions before shutdown
        self._session_store.save_all()

        logger.info("Message router stopped")

    async def listen_to_adapter(self, adapter: PlatformAdapter) -> None:
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

    async def _handle_message(self, adapter: PlatformAdapter, message: IncomingMessage) -> None:
        """Handle an incoming message with semaphore-limited concurrency."""
        if self._semaphore:
            async with self._semaphore:
                await self._process_message(adapter, message)
        else:
            await self._process_message(adapter, message)

    def _resolve_destination(self, message: IncomingMessage) -> str:
        """Resolve the destination_id for sending replies."""
        return message.metadata.get("channel_id", message.user.platform_user_id)

    async def _process_message(self, adapter: PlatformAdapter, message: IncomingMessage) -> None:
        """Process a message through the full lifecycle."""
        destination_id = self._resolve_destination(message)
        channel_id = message.metadata.get("channel_id")

        # Resolve session (per-channel)
        session_id = None
        if self._session_mapper:
            session_id = self._session_mapper.get_session_id(
                message.user,
                channel_id=channel_id,
                create_if_missing=True,
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
            try:
                await adapter.send_message(
                    destination_id,
                    OutgoingMessage(
                        content="Sorry, an error occurred while processing your message.",
                        format="plain",
                    ),
                )
            except Exception:
                logger.error("Failed to send error message to user")

        # Persist session metadata into hub.db session_index.
        # hub_db is always available when the hub is running; silently skip otherwise.
        if session_id:
            try:
                from inkarms.hub import db as hub_db
                if hub_db.is_connected():
                    await hub_db.upsert_session(
                        session_id=session_id,
                        platform=adapter.platform_type.value,
                        platform_user_id=message.user.platform_user_id,
                        channel_id=channel_id,
                        display_name=message.user.username,
                        turn_count_delta=1,
                    )
            except ImportError:
                pass  # hub extras not installed — CLI mode
            except Exception as _e:  # noqa: BLE001
                logger.debug("session_index upsert skipped: %s", _e)

    async def _process_streaming(
        self,
        adapter: PlatformAdapter,
        message: IncomingMessage,
        destination_id: str,
        session_id: str | None,
    ) -> None:
        """Process a message with streaming response."""
        if not self._processor:
            return

        message_id = None
        full_text = ""

        async for chunk in self._processor.process_streaming(
            query=message.content,
            session_id=session_id,
            platform=message.platform,
            platform_user_id=message.user.platform_user_id,
            platform_username=message.user.username,
        ):
            # Accumulate text content
            # Text chunks have empty metadata (or just event_type=stream_chunk which we treat as content)
            is_text_chunk = not chunk.metadata or chunk.metadata.get("event_type") == "stream_chunk"

            if chunk.is_final:
                # Final chunk carries the authoritative complete response — don't accumulate
                if chunk.content:
                    full_text = chunk.content
            elif is_text_chunk:
                full_text += chunk.content

            # Determine what to display
            # If it's a status update (tool execution), append it temporarily or ignore?
            # For Telegram/Slack, we usually want to see "Thinking..." or "Running tool X..."
            # But we don't want to lose the generated text.

            display_text = full_text
            if not is_text_chunk and chunk.content:
                # It's a status update (e.g. "Running tool: Search...")
                # We can append it to the text
                separator = "\n\n" if full_text else ""
                display_text = f"{full_text}{separator}*{chunk.content}*"

            # Skip if empty (Telegram rejects empty messages)
            if not display_text.strip():
                continue

            # Send full accumulated text (plus current status) to adapter
            # Create a new chunk object because adapter might expect one
            display_chunk = StreamChunk(
                content=display_text, is_final=chunk.is_final, metadata=chunk.metadata
            )

            message_id = await adapter.send_streaming_chunk(
                destination_id,
                display_chunk,
                message_id,
            )

    async def _process_non_streaming(
        self,
        adapter: PlatformAdapter,
        message: IncomingMessage,
        destination_id: str,
        session_id: str | None,
    ) -> None:
        """Process a message with non-streaming response."""
        if not self._processor:
            return

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

    # --- Command handling ---

    async def handle_command(
        self,
        user: PlatformUser,
        command: str,
        args: str,
        channel_id: str,
        _message_id: str,
    ) -> str | None:
        """Handle a slash command from a platform adapter.

        This is the callback passed to adapters that support commands.

        Args:
            user: Platform user who sent the command.
            command: Command name (e.g. "/help").
            args: Command arguments.
            channel_id: Channel/chat ID where the command was sent.
            _message_id: Message ID of the command (reserved for future use).

        Returns:
            Reply text, or None if no reply needed.
        """
        # Ensure command starts with /
        if not command.startswith("/"):
            command = f"/{command}"

        # Handle /new — create a fresh session for this channel
        if command == "/new":
            return self._handle_new_session(user, channel_id)

        # Resolve session for this channel
        session_id = None
        session_mgr = None
        if self._session_mapper:
            session_id = self._session_mapper.get_session_id(
                user,
                channel_id=channel_id,
                create_if_missing=True,
            )
        if session_id:
            session_mgr = self._session_store.get_manager(session_id)

        # Build command context
        ctx = self._build_command_context(session_mgr)

        # Build full command text for the registry
        full_text = f"{command} {args}".strip() if args else command

        result = CommandRegistry.handle(full_text, ctx)
        if result is None:
            return f"Unknown command: {command}. Type /help for available commands."

        # If /load was used and session was loaded, sync chain
        if command == "/load" and args and session_id and self._session_mapper:
            self._session_mapper._sync_chain(
                self._session_mapper._to_channel_identifier(user.platform.value, channel_id),
                session_id,
            )

        return result.message

    def _handle_new_session(self, user: PlatformUser, channel_id: str) -> str:
        """Create a new session for a channel, syncing chain members."""
        new_session_id = f"{user.platform.value}_{uuid.uuid4().hex[:8]}"

        if self._session_mapper:
            self._session_mapper.set_session_id(
                user,
                new_session_id,
                channel_id=channel_id,
            )

        # Create a fresh SessionManager for the new session
        self._session_store.get_manager(new_session_id)

        return f"New session started: {new_session_id[:16]}..."

    def _build_command_context(
        self,
        session_mgr,
    ) -> CommandContext:
        """Build a CommandContext for platform command handling."""
        model = ""
        provider = ""
        if session_mgr:
            model = session_mgr.model or ""
            provider = model.split("/")[0] if "/" in model else ""

        return CommandContext(
            session_manager=session_mgr,
            model=model,
            provider=provider,
            tool_registry=(self._processor._tool_registry if self._processor else None),
            agent_config=None,
            on_clear=session_mgr.clear_session if session_mgr else None,
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
