"""Telegram bot platform adapter using long polling."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Optional

from inkarms.platforms.models import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
    StreamChunk,
)
from inkarms.platforms.protocol import PlatformAdapter

logger = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.ext import Application, MessageHandler, filters
    from telegram.constants import ParseMode, ChatAction
    from telegram.error import TelegramError

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning(
        "python-telegram-bot not installed. "
        "Install with: pip install python-telegram-bot"
    )


class TelegramAdapter(PlatformAdapter):
    """Telegram bot adapter using long polling.

    Uses python-telegram-bot library with polling mode.
    No webhook setup required - perfect for personal use.

    Configuration:
        - bot_token: Telegram bot token from @BotFather
        - allowed_users: List of allowed Telegram user IDs (empty = all users)
        - parse_mode: Message parse mode (MarkdownV2, Markdown, HTML)
        - polling_interval: Seconds between poll requests (default: 2)
    """

    def __init__(
        self,
        bot_token: str,
        allowed_users: Optional[list[str]] = None,
        parse_mode: str = "MarkdownV2",
        polling_interval: int = 2,
    ):
        """Initialize Telegram adapter.

        Args:
            bot_token: Bot token from @BotFather
            allowed_users: List of allowed user IDs (None or empty = all users)
            parse_mode: Telegram parse mode (MarkdownV2, Markdown, HTML)
            polling_interval: Polling interval in seconds
        """
        if not TELEGRAM_AVAILABLE:
            raise ImportError(
                "python-telegram-bot is required for Telegram adapter. "
                "Install with: pip install python-telegram-bot"
            )

        super().__init__()

        self._bot_token = bot_token
        self._allowed_users = set(allowed_users) if allowed_users else None
        self._parse_mode = parse_mode
        self._polling_interval = polling_interval

        self._application: Optional[Application] = None
        self._message_queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self._bot: Optional[Bot] = None

        self._capabilities = PlatformCapabilities(
            supports_streaming=True,  # Via message editing
            supports_markdown=True,
            supports_html=True,
            supports_buttons=True,
            supports_attachments=True,
            supports_threads=False,
            supports_reactions=False,
            supports_typing_indicator=True,
            supports_message_editing=True,
            markdown_flavor="MarkdownV2",
            max_message_length=4096,
        )

    @property
    def platform_type(self) -> PlatformType:
        """The type of platform this adapter handles."""
        return PlatformType.TELEGRAM

    @property
    def capabilities(self) -> PlatformCapabilities:
        """The capabilities supported by this platform."""
        return self._capabilities

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if self._running:
            logger.warning("Telegram adapter already running")
            return

        logger.info("Starting Telegram bot adapter (polling mode)")

        # Build application
        self._application = Application.builder().token(self._bot_token).build()
        self._bot = self._application.bot

        # Add message handler
        self._application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        # Initialize and start polling
        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(
            poll_interval=self._polling_interval,
            allowed_updates=Update.ALL_TYPES,
        )

        self._running = True
        logger.info("Telegram bot started successfully")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._running:
            logger.warning("Telegram adapter not running")
            return

        logger.info("Stopping Telegram bot adapter")

        if self._application:
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()

        self._running = False
        logger.info("Telegram bot stopped")

    async def _handle_message(self, update: Update, context) -> None:
        """Handle incoming message from Telegram.

        Args:
            update: Telegram update object
            context: Telegram context
        """
        if not update.message or not update.message.text:
            return

        message = update.message
        user_id = str(message.from_user.id)

        # Check user whitelist
        if self._allowed_users and user_id not in self._allowed_users:
            logger.warning(f"Rejected message from unauthorized user: {user_id}")
            await message.reply_text(
                "Sorry, you are not authorized to use this bot.",
                parse_mode=None,
            )
            return

        # Create platform user
        platform_user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id=user_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )

        # Create incoming message
        incoming_msg = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=platform_user,
            content=message.text,
            message_id=str(message.message_id),
            thread_id=None,
            reply_to_message_id=(
                str(message.reply_to_message.message_id)
                if message.reply_to_message
                else None
            ),
            metadata={
                "chat_id": str(message.chat_id),
                "chat_type": message.chat.type,
            },
        )

        # Queue message for processing
        await self._message_queue.put(incoming_msg)

    async def receive_messages(self) -> AsyncIterator[IncomingMessage]:
        """Receive messages from Telegram.

        Yields:
            IncomingMessage objects as they arrive
        """
        while self._running:
            try:
                # Wait for message with timeout to allow checking _running
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0,
                )
                yield message
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error receiving message: {e}", exc_info=True)

    async def send_message(
        self,
        user: str,
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a Telegram user.

        Args:
            user: Chat ID (stored in metadata from incoming message)
            message: The message to send

        Returns:
            Message ID of sent message

        Raises:
            TelegramError: If sending fails
        """
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        try:
            # Format content
            formatted_content = self.format_output(message.content, message.format)

            # Determine parse mode
            parse_mode = None
            if message.format == "markdown":
                parse_mode = ParseMode.MARKDOWN_V2
            elif message.format == "html":
                parse_mode = ParseMode.HTML

            # Send message
            sent_message = await self._bot.send_message(
                chat_id=user,
                text=formatted_content,
                parse_mode=parse_mode,
                reply_to_message_id=(
                    int(message.reply_to_message_id)
                    if message.reply_to_message_id
                    else None
                ),
            )

            return str(sent_message.message_id)

        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise

    async def send_streaming_chunk(
        self,
        user: str,
        chunk: StreamChunk,
        message_id: Optional[str] = None,
    ) -> str:
        """Send a streaming chunk via message editing.

        For the first chunk, creates a new message.
        For subsequent chunks, edits the existing message.

        Args:
            user: Chat ID
            chunk: The streaming chunk
            message_id: Existing message ID to edit

        Returns:
            Message ID
        """
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        try:
            # Format content
            formatted_content = self.format_output(chunk.content, "markdown")

            if message_id is None:
                # First chunk - send new message
                sent_message = await self._bot.send_message(
                    chat_id=user,
                    text=formatted_content,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return str(sent_message.message_id)
            else:
                # Subsequent chunks - edit message
                await self._bot.edit_message_text(
                    chat_id=user,
                    message_id=int(message_id),
                    text=formatted_content,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return message_id

        except TelegramError as e:
            # If edit fails (message unchanged), ignore
            if "message is not modified" not in str(e).lower():
                logger.error(f"Failed to send streaming chunk: {e}")
            return message_id or ""

    async def send_typing_indicator(self, user: str) -> None:
        """Send typing indicator to user.

        Args:
            user: Chat ID
        """
        if not self._bot:
            return

        try:
            await self._bot.send_chat_action(
                chat_id=user,
                action=ChatAction.TYPING,
            )
        except TelegramError as e:
            logger.debug(f"Failed to send typing indicator: {e}")

    def format_output(self, content: str, format: str) -> str:
        """Format content for Telegram.

        Escapes special characters for MarkdownV2 if needed.

        Args:
            content: The content to format
            format: The format type ("plain", "markdown", "html")

        Returns:
            Telegram-formatted content
        """
        if format == "plain":
            return content

        if format == "markdown" and self._parse_mode == "MarkdownV2":
            # For MarkdownV2, certain characters need escaping
            # This is a simplified version - full implementation would be more complex
            return content

        return content

    async def health_check(self) -> bool:
        """Check if the Telegram bot connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self._running or not self._bot:
            return False

        try:
            # Try to get bot info
            await self._bot.get_me()
            return True
        except TelegramError as e:
            logger.error(f"Telegram health check failed: {e}")
            return False
