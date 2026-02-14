"""Discord bot platform adapter using Gateway WebSocket."""

from __future__ import annotations

import asyncio
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

logger = logging.getLogger(__name__)

try:
    import discord
    from discord.ext import commands

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    logger.warning("discord.py not installed. Install with: pip install discord.py")


class DiscordAdapter(PlatformAdapter):
    """Discord bot adapter using Gateway WebSocket.

    Uses discord.py library with Gateway connection (standard for Discord bots).
    No webhook required - maintains persistent WebSocket to Discord.

    Configuration:
        - bot_token: Discord bot token
        - allowed_guilds: List of allowed guild (server) IDs (empty = all guilds)
        - allowed_channels: List of allowed channel IDs (empty = all channels)
        - command_prefix: Command prefix (default: "!")
    """

    def __init__(
        self,
        bot_token: str,
        allowed_guilds: list[str] | None = None,
        allowed_channels: list[str] | None = None,
        command_prefix: str = "!",
    ):
        """Initialize Discord adapter.

        Args:
            bot_token: Discord bot token
            allowed_guilds: List of allowed guild IDs (None or empty = all guilds)
            allowed_channels: List of allowed channel IDs (None or empty = all channels)
            command_prefix: Command prefix for bot commands
        """
        if not DISCORD_AVAILABLE:
            raise ImportError(
                "discord.py is required for Discord adapter. "
                "Install with: pip install discord.py"
            )

        super().__init__()

        self._bot_token = bot_token
        self._allowed_guilds = set(allowed_guilds) if allowed_guilds else None
        self._allowed_channels = set(allowed_channels) if allowed_channels else None
        self._command_prefix = command_prefix

        # Set up intents (need message content intent)
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        self._bot = commands.Bot(command_prefix=command_prefix, intents=intents)
        self._ready_event = asyncio.Event()

        # Register event handlers
        self._bot.event(self._on_ready)
        self._bot.event(self._on_message)

    CAPABILITIES = PlatformCapabilities(
        supports_streaming=True,
        supports_markdown=True,
        supports_html=False,
        supports_buttons=False,
        supports_attachments=True,
        supports_threads=True,
        supports_reactions=True,
        supports_typing_indicator=True,
        supports_message_editing=True,
        markdown_flavor="standard",
        max_message_length=2000,
    )

    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.DISCORD

    @property
    def capabilities(self) -> PlatformCapabilities:
        return self.CAPABILITIES

    async def start(self) -> None:
        """Start the Discord bot with Gateway connection."""
        if self._running:
            logger.warning("Discord adapter already running")
            return

        logger.info("Starting Discord bot adapter (Gateway WebSocket)")

        # Start bot in background task
        asyncio.create_task(self._run_bot())

        # Wait for bot to be ready
        await self._ready_event.wait()

        self._running = True
        logger.info("Discord bot started successfully")

    async def _run_bot(self) -> None:
        """Run the Discord bot (internal task)."""
        try:
            await self._bot.start(self._bot_token)
        except Exception as e:
            logger.error(f"Discord bot error: {e}", exc_info=True)

    async def _on_ready(self) -> None:
        """Called when bot is ready."""
        logger.info(f"Discord bot logged in as {self._bot.user}")
        self._ready_event.set()

    async def _on_message(self, message: discord.Message) -> None:
        """Handle incoming message from Discord.

        Args:
            message: Discord message object
        """
        # Ignore bot messages
        if message.author.bot:
            return

        # Check guild whitelist
        if message.guild:
            guild_id = str(message.guild.id)
            if self._allowed_guilds and guild_id not in self._allowed_guilds:
                logger.warning(f"Rejected message from unauthorized guild: {guild_id}")
                return

        # Check channel whitelist
        channel_id = str(message.channel.id)
        if self._allowed_channels and channel_id not in self._allowed_channels:
            logger.warning(f"Rejected message from unauthorized channel: {channel_id}")
            return

        # Get message details
        user_id = str(message.author.id)
        username = message.author.name
        display_name = message.author.display_name
        content = message.content

        if not content:
            return

        # Create platform user
        platform_user = PlatformUser(
            platform=PlatformType.DISCORD,
            platform_user_id=user_id,
            username=username,
            display_name=display_name,
        )

        # Get thread info
        thread_id = None
        if isinstance(message.channel, discord.Thread):
            thread_id = str(message.channel.id)

        # Create incoming message
        incoming_msg = IncomingMessage(
            platform=PlatformType.DISCORD,
            user=platform_user,
            content=content,
            message_id=str(message.id),
            thread_id=thread_id,
            reply_to_message_id=(
                str(message.reference.message_id) if message.reference else None
            ),
            metadata={
                "channel_id": channel_id,
                "guild_id": str(message.guild.id) if message.guild else None,
                "channel_type": str(message.channel.type),
            },
        )

        # Queue message for processing
        await self._message_queue.put(incoming_msg)

    async def stop(self) -> None:
        """Stop the Discord bot."""
        if not self._running:
            logger.warning("Discord adapter not running")
            return

        logger.info("Stopping Discord bot adapter")

        await self._bot.close()

        self._running = False
        logger.info("Discord bot stopped")

    async def send_message(
        self,
        destination_id: str,
        message: OutgoingMessage,
    ) -> str:
        """Send a message to a Discord channel.

        Args:
            destination_id: Channel ID
            message: The message to send

        Returns:
            Message ID of sent message
        """
        channel_id = int(destination_id)

        try:
            channel = self._bot.get_channel(channel_id)
            if not channel:
                # Try fetching channel
                channel = await self._bot.fetch_channel(channel_id)

            if not channel:
                raise ValueError(f"Channel not found: {channel_id}")

            # Format content
            formatted_content = self.format_output(message.content, message.format)

            # Split message if too long (Discord limit: 2000 chars)
            if len(formatted_content) > 2000:
                # Send in chunks
                chunks = [
                    formatted_content[i : i + 2000]
                    for i in range(0, len(formatted_content), 2000)
                ]
                sent_message = None
                for chunk in chunks:
                    sent_message = await channel.send(chunk)
                return str(sent_message.id) if sent_message else ""
            else:
                # Send single message
                sent_message = await channel.send(formatted_content)
                return str(sent_message.id)

        except discord.DiscordException as e:
            logger.error(f"Failed to send Discord message: {e}")
            raise

    async def send_streaming_chunk(
        self,
        destination_id: str,
        chunk: StreamChunk,
        message_id: str | None = None,
    ) -> str:
        """Send a streaming chunk via message editing."""
        channel_id = int(destination_id)

        try:
            channel = self._bot.get_channel(channel_id)
            if not channel:
                channel = await self._bot.fetch_channel(channel_id)

            if not channel:
                raise ValueError(f"Channel not found: {channel_id}")

            # Format content
            formatted_content = self.format_output(chunk.content, "markdown")

            # Truncate if too long
            if len(formatted_content) > 2000:
                formatted_content = formatted_content[:1997] + "..."

            if message_id is None:
                # First chunk - send new message
                sent_message = await channel.send(formatted_content)
                return str(sent_message.id)
            else:
                # Subsequent chunks - edit message
                message = await channel.fetch_message(int(message_id))
                await message.edit(content=formatted_content)
                return message_id

        except discord.DiscordException as e:
            # If edit fails, ignore
            logger.debug(f"Failed to send streaming chunk: {e}")
            return message_id or ""

    async def send_typing_indicator(self, destination_id: str) -> None:
        """Send typing indicator to channel."""
        try:
            channel_id = int(destination_id)
            channel = self._bot.get_channel(channel_id)
            if not channel:
                channel = await self._bot.fetch_channel(channel_id)

            if channel:
                await channel.typing()
        except Exception as e:
            logger.debug(f"Failed to send typing indicator: {e}")

    def format_output(self, content: str, output_format: str) -> str:
        """Format content for Discord.

        Discord supports standard markdown.

        Args:
            content: The content to format
            output_format: The format type ("plain", "markdown", "html")

        Returns:
            Discord-formatted content
        """
        if output_format == "plain":
            return content

        if output_format == "markdown":
            # Discord supports standard markdown
            return content

        return content

    async def health_check(self) -> bool:
        """Check if the Discord bot connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self._running:
            return False

        # Check if bot is connected and ready
        return self._bot.is_ready() and not self._bot.is_closed()
