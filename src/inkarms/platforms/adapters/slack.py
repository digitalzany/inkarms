"""Slack bot platform adapter using Socket Mode."""

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
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.errors import SlackApiError

    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    logger.warning("slack-sdk not installed. Install with: pip install slack-sdk")


class SlackAdapter(PlatformAdapter):
    """Slack bot adapter using Socket Mode.

    Socket Mode uses WebSocket connections, perfect for personal use.
    No webhook setup required - works behind firewalls.

    Configuration:
        - bot_token: Bot User OAuth Token (starts with xoxb-)
        - app_token: App-Level Token for Socket Mode (starts with xapp-)
        - allowed_channels: List of allowed channel IDs (empty = all channels)
    """

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        allowed_channels: Optional[list[str]] = None,
    ):
        """Initialize Slack adapter.

        Args:
            bot_token: Bot User OAuth Token (xoxb-...)
            app_token: App-Level Token for Socket Mode (xapp-...)
            allowed_channels: List of allowed channel IDs (None or empty = all channels)
        """
        if not SLACK_AVAILABLE:
            raise ImportError(
                "slack-sdk is required for Slack adapter. "
                "Install with: pip install slack-sdk"
            )

        super().__init__()

        self._bot_token = bot_token
        self._app_token = app_token
        self._allowed_channels = set(allowed_channels) if allowed_channels else None

        self._web_client: Optional[AsyncWebClient] = None
        self._socket_client: Optional[SocketModeClient] = None
        self._message_queue: asyncio.Queue[IncomingMessage] = asyncio.Queue()
        self._bot_user_id: Optional[str] = None

        self._capabilities = PlatformCapabilities(
            supports_streaming=True,  # Via message editing
            supports_markdown=True,
            supports_html=False,
            supports_buttons=True,
            supports_attachments=True,
            supports_threads=True,
            supports_reactions=True,
            supports_typing_indicator=False,  # Slack doesn't have typing indicator
            supports_message_editing=True,
            markdown_flavor="mrkdwn",  # Slack's markdown variant
            max_message_length=40000,  # Slack allows very long messages
        )

    @property
    def platform_type(self) -> PlatformType:
        """The type of platform this adapter handles."""
        return PlatformType.SLACK

    @property
    def capabilities(self) -> PlatformCapabilities:
        """The capabilities supported by this platform."""
        return self._capabilities

    async def start(self) -> None:
        """Start the Slack bot with Socket Mode."""
        if self._running:
            logger.warning("Slack adapter already running")
            return

        logger.info("Starting Slack bot adapter (Socket Mode)")

        # Initialize web client for API calls
        self._web_client = AsyncWebClient(token=self._bot_token)

        # Get bot user ID
        try:
            auth_response = await self._web_client.auth_test()
            self._bot_user_id = auth_response["user_id"]
            logger.info(f"Slack bot authenticated as user ID: {self._bot_user_id}")
        except SlackApiError as e:
            logger.error(f"Failed to authenticate Slack bot: {e}")
            raise

        # Initialize Socket Mode client
        self._socket_client = SocketModeClient(
            app_token=self._app_token,
            web_client=self._web_client,
        )

        # Register event handlers
        self._socket_client.socket_mode_request_listeners.append(self._handle_socket_event)

        # Connect to Slack
        await self._socket_client.connect()

        self._running = True
        logger.info("Slack bot started successfully in Socket Mode")

    async def stop(self) -> None:
        """Stop the Slack bot."""
        if not self._running:
            logger.warning("Slack adapter not running")
            return

        logger.info("Stopping Slack bot adapter")

        if self._socket_client:
            await self._socket_client.close()

        self._running = False
        logger.info("Slack bot stopped")

    async def _handle_socket_event(
        self, client: SocketModeClient, req: SocketModeRequest
    ) -> None:
        """Handle incoming Socket Mode events.

        Args:
            client: Socket Mode client
            req: Socket Mode request
        """
        # Acknowledge the request
        response = SocketModeResponse(envelope_id=req.envelope_id)
        await client.send_socket_mode_response(response)

        # Handle event
        if req.type == "events_api":
            event = req.payload.get("event", {})
            event_type = event.get("type")

            if event_type == "message":
                await self._handle_message_event(event)

    async def _handle_message_event(self, event: dict) -> None:
        """Handle message event from Slack.

        Args:
            event: Message event data
        """
        # Ignore bot messages and message changes
        if event.get("subtype") in ("bot_message", "message_changed"):
            return

        # Ignore our own messages
        if event.get("user") == self._bot_user_id:
            return

        # Get message details
        user_id = event.get("user")
        channel_id = event.get("channel")
        text = event.get("text", "")
        message_ts = event.get("ts")
        thread_ts = event.get("thread_ts")

        if not user_id or not channel_id or not text:
            return

        # Check channel whitelist
        if self._allowed_channels and channel_id not in self._allowed_channels:
            logger.warning(f"Rejected message from unauthorized channel: {channel_id}")
            return

        # Get user info
        try:
            user_info = await self._web_client.users_info(user=user_id)
            user_data = user_info.get("user", {})
            username = user_data.get("name")
            display_name = user_data.get("real_name") or username
        except SlackApiError as e:
            logger.warning(f"Failed to get user info: {e}")
            username = None
            display_name = None

        # Create platform user
        platform_user = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id=user_id,
            username=username,
            display_name=display_name,
        )

        # Create incoming message
        incoming_msg = IncomingMessage(
            platform=PlatformType.SLACK,
            user=platform_user,
            content=text,
            message_id=message_ts,
            thread_id=thread_ts,  # Use thread_ts for threading
            reply_to_message_id=thread_ts if thread_ts else None,
            metadata={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
            },
        )

        # Queue message for processing
        await self._message_queue.put(incoming_msg)

    async def receive_messages(self) -> AsyncIterator[IncomingMessage]:
        """Receive messages from Slack.

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
        """Send a message to a Slack channel.

        Args:
            user: Channel ID (stored in metadata from incoming message)
            message: The message to send

        Returns:
            Message timestamp (ts) of sent message

        Raises:
            SlackApiError: If sending fails
        """
        if not self._web_client:
            raise RuntimeError("Web client not initialized")

        # Extract channel ID from metadata
        channel_id = user

        try:
            # Format content
            formatted_content = self.format_output(message.content, message.format)

            # Send message
            response = await self._web_client.chat_postMessage(
                channel=channel_id,
                text=formatted_content,
                thread_ts=message.thread_id,  # Reply in thread if specified
            )

            return response["ts"]

        except SlackApiError as e:
            logger.error(f"Failed to send Slack message: {e}")
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
            user: Channel ID
            chunk: The streaming chunk
            message_id: Existing message timestamp to edit

        Returns:
            Message timestamp
        """
        if not self._web_client:
            raise RuntimeError("Web client not initialized")

        channel_id = user

        try:
            # Format content
            formatted_content = self.format_output(chunk.content, "markdown")

            if message_id is None:
                # First chunk - send new message
                response = await self._web_client.chat_postMessage(
                    channel=channel_id,
                    text=formatted_content,
                )
                return response["ts"]
            else:
                # Subsequent chunks - edit message
                await self._web_client.chat_update(
                    channel=channel_id,
                    ts=message_id,
                    text=formatted_content,
                )
                return message_id

        except SlackApiError as e:
            # If edit fails, ignore (message might not have changed enough)
            logger.debug(f"Failed to send streaming chunk: {e}")
            return message_id or ""

    def format_output(self, content: str, format: str) -> str:
        """Format content for Slack.

        Converts markdown to Slack's mrkdwn format.

        Args:
            content: The content to format
            format: The format type ("plain", "markdown", "html")

        Returns:
            Slack-formatted content
        """
        if format == "plain":
            return content

        if format == "markdown":
            # Slack uses mrkdwn which is similar but not identical to markdown
            # Key differences:
            # - Bold: **text** → *text*
            # - Italic: *text* → _text_
            # - Code: `code` stays the same
            # - Code block: ```code``` stays the same
            # This is a simplified conversion
            return content

        return content

    async def health_check(self) -> bool:
        """Check if the Slack bot connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        if not self._running or not self._web_client:
            return False

        try:
            # Try to authenticate
            await self._web_client.auth_test()
            return True
        except SlackApiError as e:
            logger.error(f"Slack health check failed: {e}")
            return False
