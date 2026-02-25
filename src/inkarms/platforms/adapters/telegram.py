"""Telegram bot platform adapter using long polling."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Callable, Coroutine
from typing import Any, ClassVar

from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformStreamChunk,
    PlatformType,
    PlatformUser,
)
from inkarms.platforms.adapters.protocol import PlatformAdapter, PlatformField
from inkarms.platforms.formatting import markdown_to_telegram_html

logger = logging.getLogger(__name__)

try:
    from telegram import Bot, Update
    from telegram.constants import ChatAction, ParseMode
    from telegram.error import RetryAfter, TelegramError
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning(
        "python-telegram-bot not installed. "
        "Install with: pip install python-telegram-bot"
    )

# Type alias for the command callback
CommandCallback = Callable[
    [PlatformUser, str, str, str, str],
    Coroutine[Any, Any, str | None],
]


class TelegramAdapter(PlatformAdapter):
    """Telegram bot adapter using long polling.

    Uses python-telegram-bot library with polling mode.
    No webhook setup required - perfect for personal use.

    Configuration:
        - bot_token: Telegram bot token from @BotFather
        - allowed_users: List of allowed Telegram user IDs (empty = all users)
        - parse_mode: Message parse mode (MarkdownV2, Markdown, HTML)
        - polling_interval: Seconds between poll requests (default: 2)
        - command_callback: Async callback for slash command handling
    """

    PLATFORM_KEY = "telegram"
    DISPLAY_NAME = "Telegram"
    WIZARD_FIELDS: ClassVar[list[PlatformField]] = [
        PlatformField("bot_token", "Bot Token", "password", is_secret=True, required=True, hint="from @BotFather"),
        PlatformField("allowed_users", "Allowed Users, comma-separated", "list", hint="Telegram user IDs (comma-separated), empty = all users"),
    ]

    def __init__(
        self,
        bot_token: str,
        allowed_users: list[str] | None = None,
        parse_mode: str = "HTML",
        polling_interval: int = 2,
        command_callback: CommandCallback | None = None,
    ):
        """Initialize Telegram adapter.

        Args:
            bot_token: Bot token from @BotFather
            allowed_users: List of allowed user IDs (None or empty = all users)
            parse_mode: Telegram parse mode (MarkdownV2, Markdown, HTML)
            polling_interval: Polling interval in seconds
            command_callback: Async callback(user, command, args, channel_id, message_id)
                that returns a reply string or None.
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
        self._command_callback = command_callback

        self._application: Application | None = None
        self._bot: Bot | None = None
        self._last_stream_edit: dict[str, float] = {}
        self._stream_edit_interval = 5.0  # min seconds between edits per chat (~20 edits/min)

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

    def set_command_callback(self, callback: CommandCallback) -> None:
        """Set the command callback after construction.

        This allows the router to inject its handle_command method
        after the adapter is created.
        """
        self._command_callback = callback

    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if self._running:
            logger.warning("Telegram adapter already running")
            return

        logger.info("Starting Telegram bot adapter (polling mode)")

        # Build application
        self._application = Application.builder().token(self._bot_token).build()
        self._bot = self._application.bot

        # Register command handlers if callback is provided
        if self._command_callback:
            self._register_command_handlers()

        # Add message handler (text messages, excluding commands)
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

        # Register commands with Telegram so they appear in the menu
        if self._command_callback:
            await self._set_bot_commands()

        self._running = True
        logger.info("Telegram bot started successfully")

    async def _set_bot_commands(self) -> None:
        """Register bot commands with Telegram for the UI menu."""
        from inkarms.commands import CommandRegistry

        try:
            from telegram import BotCommand

            commands = [
                BotCommand(cmd.lstrip("/"), desc)
                for cmd, desc in CommandRegistry.list_commands()
            ]
            commands.append(BotCommand("new", "Start a new session"))
            await self._bot.set_my_commands(commands)
            logger.info(f"Registered {len(commands)} bot commands with Telegram")
        except Exception as e:
            logger.warning(f"Failed to set bot commands: {e}")

    def _register_command_handlers(self) -> None:
        """Register Telegram command handlers for shared slash commands."""
        from inkarms.commands import CommandRegistry

        # Register handlers for all shared commands + /new
        command_names = [
            cmd.lstrip("/") for cmd, _ in CommandRegistry.list_commands()
        ] + ["new"]

        for cmd_name in command_names:
            self._application.add_handler(
                CommandHandler(cmd_name, self._handle_command)
            )

        logger.info(f"Registered {len(command_names)} command handlers")

    async def _handle_command(self, update: Update, context: Any) -> None:
        """Handle an incoming slash command from Telegram.

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
            logger.warning(f"Rejected command from unauthorized user: {user_id}")
            await message.reply_text(
                "Sorry, you are not authorized to use this bot.",
                parse_mode=None,
            )
            return

        # Parse command and args
        text = message.text
        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        # Telegram commands may include @botname, strip it
        if "@" in command:
            command = command.split("@")[0]
        args = parts[1].strip() if len(parts) > 1 else ""

        # Build platform user
        platform_user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id=user_id,
            username=message.from_user.username,
            display_name=message.from_user.full_name,
        )

        channel_id = str(message.chat_id)
        message_id = str(message.message_id)

        if self._command_callback:
            try:
                reply = await self._command_callback(
                    platform_user, command, args, channel_id, message_id,
                )
                if reply:
                    max_len = self.CAPABILITIES.max_message_length or 4096
                    if len(reply) > max_len:
                        await self._send_split_message(
                            str(message.chat_id), reply, None, message.message_id,
                        )
                    else:
                        await message.reply_text(reply, parse_mode=None)
            except Exception as e:
                logger.error(f"Command callback error: {e}", exc_info=True)
                await message.reply_text(f"Error: {e}", parse_mode=None)

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

        # Create incoming message with correct channel_id
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
                "channel_id": str(message.chat_id),
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

            max_len = self.CAPABILITIES.max_message_length or 4096

            # Split long messages into multiple sends
            if len(formatted_content) > max_len:
                return await self._send_split_message(
                    destination_id, formatted_content, parse_mode, reply_to,
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

    async def _send_split_message(
        self,
        destination_id: str,
        text: str,
        parse_mode: str | None,
        reply_to: int | None,
    ) -> str:
        """Split a long message and send as multiple Telegram messages."""
        max_len = self.CAPABILITIES.max_message_length or 4096
        parts = self._split_html_message(text, max_len)

        sent_message = None
        for part in parts:
            try:
                sent_message = await self._bot.send_message(
                    chat_id=destination_id,
                    text=part,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to,
                )
            except TelegramError as parse_err:
                if "can't parse entities" in str(parse_err).lower():
                    sent_message = await self._bot.send_message(
                        chat_id=destination_id,
                        text=part,
                        parse_mode=None,
                        reply_to_message_id=reply_to,
                    )
                else:
                    raise
            reply_to = None  # Only first part replies to original

        return str(sent_message.message_id) if sent_message else ""

    async def send_streaming_chunk(
        self,
        destination_id: str,
        chunk: PlatformStreamChunk,
        message_id: str | None = None,
    ) -> str:
        """Send a streaming chunk via message editing."""
        if not self._bot:
            raise RuntimeError("Bot not initialized")

        # Throttle edits to avoid Telegram flood control (3 s ≈ 20 edits/min per chat)
        now = time.monotonic()
        last_edit = self._last_stream_edit.get(destination_id, 0)
        if not chunk.is_final and message_id is not None and (now - last_edit) < self._stream_edit_interval:
            return message_id  # Skip this edit, too soon

        max_len = self.CAPABILITIES.max_message_length or 4096
        formatted_content = self.format_output(chunk.content, "markdown")

        # Guard: skip edits when formatting collapses content to empty string
        if not formatted_content.strip():
            if not chunk.is_final:
                return message_id or ""
            formatted_content = chunk.content  # raw text fallback for final chunk

        # Handle final overflow (message exceeds Telegram's length limit)
        if len(formatted_content) > max_len:
            if chunk.is_final:
                try:
                    result = await self._send_final_overflow(
                        destination_id, formatted_content, max_len, message_id,
                    )
                    self._last_stream_edit[destination_id] = time.monotonic()
                    return result
                except TelegramError as e:
                    if "message is not modified" not in str(e).lower():
                        logger.error(f"Failed to send streaming chunk: {e}")
                    return message_id or ""
            formatted_content = formatted_content[: max_len - 20] + "\n\n<i>…sending</i>"

        fallback_text = chunk.content[:max_len]
        try:
            result = await self._send_or_edit_chunk(
                destination_id, formatted_content, fallback_text, message_id,
            )
            self._last_stream_edit[destination_id] = time.monotonic()
            return result

        except RetryAfter as e:
            # Telegram flood control: block all further edits for this chat until the
            # cooldown has passed by pushing _last_stream_edit into the future.
            # The throttle check (now - last_edit < interval) will then reject every
            # non-final chunk until the window expires — no more hammering.
            wait_secs = float(e.retry_after) + 1.0
            self._last_stream_edit[destination_id] = time.monotonic() + wait_secs
            logger.warning(
                f"Telegram flood control ({destination_id}): "
                f"retry_after={e.retry_after}s — suppressing edits for {wait_secs:.0f}s"
            )
            if chunk.is_final:
                # Must deliver the complete response — wait the required time then retry once.
                await asyncio.sleep(wait_secs)
                try:
                    result = await self._send_or_edit_chunk(
                        destination_id, formatted_content, fallback_text, message_id,
                    )
                    self._last_stream_edit[destination_id] = time.monotonic()
                    return result
                except TelegramError as retry_err:
                    logger.error(f"Failed to deliver final chunk after flood control wait: {retry_err}")
            return message_id or ""

        except TelegramError as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Failed to send streaming chunk: {e}")
            return message_id or ""

    async def _send_or_edit_chunk(
        self,
        destination_id: str,
        html_text: str,
        fallback_text: str,
        message_id: str | None,
    ) -> str:
        """Send a new message or edit an existing one, with HTML parse fallback."""
        if not message_id:
            try:
                sent = await self._bot.send_message(
                    chat_id=destination_id, text=html_text, parse_mode=ParseMode.HTML,
                )
            except TelegramError as e:
                if "can't parse entities" not in str(e).lower():
                    raise
                sent = await self._bot.send_message(
                    chat_id=destination_id, text=fallback_text, parse_mode=None,
                )
            return str(sent.message_id)

        try:
            await self._bot.edit_message_text(
                chat_id=destination_id, message_id=int(message_id),
                text=html_text, parse_mode=ParseMode.HTML,
            )
        except TelegramError as e:
            if "can't parse entities" not in str(e).lower():
                raise
            await self._bot.edit_message_text(
                chat_id=destination_id, message_id=int(message_id),
                text=fallback_text, parse_mode=None,
            )
        return message_id

    async def _send_final_overflow(
        self,
        destination_id: str,
        formatted_content: str,
        max_len: int,
        message_id: str | None,
    ) -> str:
        """Handle a final streaming chunk that exceeds the message length limit.

        Edits the existing message with the first part and sends overflow as new messages.
        """
        parts = self._split_html_message(formatted_content, max_len)
        first_part = parts[0]
        overflow_parts = parts[1:]

        # Edit existing message with first part (or send new if no message_id)
        await self._send_or_edit_chunk(
            destination_id, first_part, first_part, message_id,
        )

        # Send overflow as new message(s)
        sent_message = None
        for part in overflow_parts:
            try:
                sent_message = await self._bot.send_message(
                    chat_id=destination_id,
                    text=part,
                    parse_mode=ParseMode.HTML,
                )
            except TelegramError as parse_err:
                if "can't parse entities" in str(parse_err).lower():
                    sent_message = await self._bot.send_message(
                        chat_id=destination_id,
                        text=part,
                        parse_mode=None,
                    )
                else:
                    raise

        return str(sent_message.message_id) if sent_message else message_id or ""

    # --- HTML-aware message splitting ---

    @staticmethod
    def _split_html_message(text: str, max_len: int) -> list[str]:
        """Split a long HTML message into parts that respect tag boundaries.

        Splits at newlines (preferred) or spaces, and properly closes/re-opens
        HTML tags across message boundaries so each part is valid HTML.
        """
        if len(text) <= max_len:
            return [text]

        parts: list[str] = []
        remaining = text
        # Reserve space for closing tags we may need to append
        effective_len = max_len - 50

        while remaining:
            if len(remaining) <= max_len:
                parts.append(remaining)
                break

            split_at = TelegramAdapter._find_split_point(remaining, effective_len)
            part = remaining[:split_at]
            remaining = remaining[split_at:]

            # Strip a single leading newline (the split point itself)
            if remaining.startswith("\n"):
                remaining = remaining[1:]

            # Balance HTML tags: close open tags in this part, re-open in next
            open_tags = TelegramAdapter._get_open_tags(part)
            if open_tags:
                for tag in reversed(open_tags):
                    part += f"</{tag}>"
                remaining = "".join(f"<{tag}>" for tag in open_tags) + remaining

            parts.append(part)

        return parts

    @staticmethod
    def _find_split_point(text: str, max_len: int) -> int:
        """Find a good point to split text, avoiding mid-tag cuts."""
        if len(text) <= max_len:
            return len(text)

        pos = max_len

        # Don't split inside an HTML tag (between < and >)
        last_open = text.rfind("<", 0, pos)
        last_close = text.rfind(">", 0, pos)
        if last_open > last_close:
            pos = last_open

        # Prefer splitting at a newline
        last_newline = text.rfind("\n", 0, pos)
        if last_newline > pos // 2:
            return last_newline + 1

        # Then at a space
        last_space = text.rfind(" ", 0, pos)
        if last_space > pos // 2:
            return last_space + 1

        return pos

    @staticmethod
    def _get_open_tags(html: str) -> list[str]:
        """Get list of HTML tags that are opened but not closed."""
        open_tags: list[str] = []
        for match in re.finditer(r"<(/?)(\w+)[^>]*>", html):
            is_closing = match.group(1) == "/"
            tag_name = match.group(2)
            if is_closing:
                for i in range(len(open_tags) - 1, -1, -1):
                    if open_tags[i] == tag_name:
                        open_tags.pop(i)
                        break
            else:
                open_tags.append(tag_name)
        return open_tags

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
