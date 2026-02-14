"""Telegram bot platform adapter using long polling."""

from __future__ import annotations

import logging

from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
    StreamChunk,
)
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.formatting import markdown_to_telegram_html

logger = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.constants import ChatAction, ParseMode
    from telegram.error import TelegramError
    from telegram.ext import Application, MessageHandler, filters
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
        allowed_users: list[str] | None = None,
        parse_mode: str = "HTML",
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

        self._application: Application | None = None
        self._bot: Bot | None = None

    CAPABILITIES = PlatformCapabilities(
        supports_streaming=True,
        supports_markdown=True,
        supports_html=True,
        supports_buttons=True,
        supports_attachments=True,
        supports_threads=False,
        supports_reactions=False,
        supports_typing_indicator=True,
        supports_message_editing=True,
        markdown_flavor="HTML",
        max_message_length=4096,
    )

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.TELEGRAM

    @property
    def capabilities(self) -> PlatformCapabilities:
        return self.CAPABILITIES

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

    async def send_message(
        self,
        destination_id: str,
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a Telegram chat.

        Args:
            destination_id: Chat ID
            message: The message to send

        Returns:
            Message ID of sent message
        """
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        try:
            formatted_content = self.format_output(message.content, message.format)

            parse_mode = None
            if message.format in ("markdown", "html"):
                parse_mode = ParseMode.HTML

            reply_to = (
                int(message.reply_to_message_id)
                if message.reply_to_message_id
                else None
            )

            try:
                sent_message = await self._bot.send_message(
                    chat_id=destination_id,
                    text=formatted_content,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to,
                )
            except TelegramError as parse_err:
                if "can't parse entities" in str(parse_err).lower():
                    logger.warning("HTML parse failed, retrying as plain text")
                    sent_message = await self._bot.send_message(
                        chat_id=destination_id,
                        text=message.content,
                        parse_mode=None,
                        reply_to_message_id=reply_to,
                    )
                else:
                    raise

            return str(sent_message.message_id)

        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise

    async def send_streaming_chunk(
        self,
        destination_id: str,
        chunk: StreamChunk,
        message_id: str | None = None,
    ) -> str:
        """Send a streaming chunk via message editing."""
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        try:
            formatted_content = self.format_output(chunk.content, "markdown")

            if message_id is None:
                try:
                    sent_message = await self._bot.send_message(
                        chat_id=destination_id,
                        text=formatted_content,
                        parse_mode=ParseMode.HTML,
                    )
                except TelegramError as parse_err:
                    if "can't parse entities" in str(parse_err).lower():
                        sent_message = await self._bot.send_message(
                            chat_id=destination_id,
                            text=chunk.content,
                            parse_mode=None,
                        )
                    else:
                        raise
                return str(sent_message.message_id)
            else:
                try:
                    await self._bot.edit_message_text(
                        chat_id=destination_id,
                        message_id=int(message_id),
                        text=formatted_content,
                        parse_mode=ParseMode.HTML,
                    )
                except TelegramError as parse_err:
                    if "can't parse entities" in str(parse_err).lower():
                        await self._bot.edit_message_text(
                            chat_id=destination_id,
                            message_id=int(message_id),
                            text=chunk.content,
                            parse_mode=None,
                        )
                    else:
                        raise
                return message_id

        except TelegramError as e:
            # If edit fails (message unchanged), ignore
            if "message is not modified" not in str(e).lower():
                logger.error(f"Failed to send streaming chunk: {e}")
            return message_id or ""

    async def send_typing_indicator(self, destination_id: str) -> None:
        """Send typing indicator."""
        if not self._bot:
            return

        try:
            await self._bot.send_chat_action(
                chat_id=destination_id,
                action=ChatAction.TYPING,
            )
        except TelegramError as e:
            logger.debug(f"Failed to send typing indicator: {e}")

    def format_output(self, content: str, output_format: str) -> str:
        """Format content for Telegram.

        Converts standard Markdown to Telegram-compatible HTML.

        Args:
            content: The content to format
            output_format: The format type ("plain", "markdown", "html")

        Returns:
            Telegram-formatted content
        """
        if output_format == "plain":
            return content

        if output_format == "markdown":
            try:
                return markdown_to_telegram_html(content)
            except Exception:
                logger.warning("Markdown to HTML conversion failed, using plain text")
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
