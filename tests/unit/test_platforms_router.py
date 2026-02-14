"""Unit tests for platform message router."""

import asyncio

import pytest

from inkarms.models.platforms import (
    IncomingMessage,
    OutgoingMessage,
    PlatformCapabilities,
    PlatformType,
    PlatformUser,
    StreamChunk,
)
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.rate_limiter import RateLimiter
from inkarms.platforms.router import MessageRouter
from inkarms.platforms.session_mapper import SessionMapper


class MockAdapter(PlatformAdapter):
    """Mock platform adapter for testing."""

    def __init__(
        self,
        platform_type: PlatformType,
        capabilities: PlatformCapabilities | None = None,
    ):
        super().__init__()
        self._platform_type = platform_type
        self._capabilities = capabilities or PlatformCapabilities(
            supports_streaming=False,
            supports_markdown=False,
        )
        self._started = False
        self._stopped = False
        self._messages_queue: list[IncomingMessage] = []
        self._sent_messages: list[tuple[str, OutgoingMessage]] = []
        self._streaming_chunks: list[tuple[str, StreamChunk]] = []
        self._typing_indicators: list[str] = []

    @property
    def platform_type(self) -> PlatformType:
        return self._platform_type

    @property
    def capabilities(self) -> PlatformCapabilities:
        return self._capabilities

    async def start(self) -> None:
        self._started = True
        self._stopped = False
        self._running = True

    async def stop(self) -> None:
        self._stopped = True
        self._started = False
        self._running = False

    async def receive_messages(self):
        """Yield messages from queue."""
        while self._started and self._messages_queue:
            yield self._messages_queue.pop(0)
            await asyncio.sleep(0.01)

    async def send_message(self, destination_id: str, message: OutgoingMessage) -> str:
        """Mock send message."""
        self._sent_messages.append((destination_id, message))
        return f"msg_{id(message)}"

    async def send_streaming_chunk(
        self,
        destination_id: str,
        chunk: StreamChunk,
        message_id: str | None = None,
    ) -> str:
        """Mock send streaming chunk."""
        self._streaming_chunks.append((destination_id, chunk))
        return message_id or f"msg_{id(chunk)}"

    async def send_typing_indicator(self, destination_id: str) -> None:
        """Mock typing indicator."""
        self._typing_indicators.append(destination_id)

    def format_output(self, content: str, output_format: str) -> str:
        """Mock format output."""
        return content

    def add_test_message(self, message: IncomingMessage) -> None:
        """Add a message to the queue for testing."""
        self._messages_queue.append(message)


@pytest.fixture
def router():
    """Create a message router."""
    return MessageRouter(max_concurrent_tasks=10)


@pytest.fixture
def telegram_adapter():
    """Create a mock Telegram adapter."""
    return MockAdapter(
        platform_type=PlatformType.TELEGRAM,
        capabilities=PlatformCapabilities(
            supports_streaming=True,
            supports_markdown=True,
            markdown_flavor="MarkdownV2",
        ),
    )


@pytest.fixture
def slack_adapter():
    """Create a mock Slack adapter."""
    return MockAdapter(
        platform_type=PlatformType.SLACK,
        capabilities=PlatformCapabilities(
            supports_streaming=True,
            supports_markdown=True,
            markdown_flavor="mrkdwn",
        ),
    )


class TestMessageRouter:
    """Tests for MessageRouter class."""

    def test_create_router(self, router):
        """Test creating a message router."""
        assert router._max_concurrent_tasks == 10
        assert len(router._adapters) == 0

    def test_register_adapter(self, router, telegram_adapter):
        """Test registering an adapter."""
        router.register_adapter(telegram_adapter)

        assert "telegram" in router._adapters
        assert router._adapters["telegram"] == telegram_adapter

    def test_register_multiple_adapters(self, router, telegram_adapter, slack_adapter):
        """Test registering multiple adapters."""
        router.register_adapter(telegram_adapter)
        router.register_adapter(slack_adapter)

        assert len(router._adapters) == 2
        assert "telegram" in router._adapters
        assert "slack" in router._adapters

    def test_register_duplicate_adapter_raises_error(self, router, telegram_adapter):
        """Test that registering duplicate platform raises error."""
        adapter2 = MockAdapter(PlatformType.TELEGRAM)

        router.register_adapter(telegram_adapter)

        with pytest.raises(ValueError, match="already registered"):
            router.register_adapter(adapter2)

    def test_unregister_adapter(self, router, telegram_adapter):
        """Test unregistering an adapter."""
        router.register_adapter(telegram_adapter)
        router.unregister_adapter("telegram")

        assert "telegram" not in router._adapters

    def test_unregister_nonexistent_adapter(self, router):
        """Test unregistering adapter that doesn't exist."""
        router.unregister_adapter("nonexistent")

    def test_get_adapter(self, router, telegram_adapter):
        """Test getting an adapter by name."""
        router.register_adapter(telegram_adapter)

        adapter = router.get_adapter("telegram")
        assert adapter == telegram_adapter

    def test_get_nonexistent_adapter(self, router):
        """Test getting adapter that doesn't exist."""
        adapter = router.get_adapter("nonexistent")
        assert adapter is None

    @pytest.mark.asyncio
    async def test_start_router(self, router, telegram_adapter):
        """Test starting the router."""
        router.register_adapter(telegram_adapter)

        await router.start()

        assert telegram_adapter._started is True

    @pytest.mark.asyncio
    async def test_start_multiple_adapters(self, router, telegram_adapter, slack_adapter):
        """Test starting router with multiple adapters."""
        router.register_adapter(telegram_adapter)
        router.register_adapter(slack_adapter)

        await router.start()

        assert telegram_adapter._started is True
        assert slack_adapter._started is True

    @pytest.mark.asyncio
    async def test_stop_router(self, router, telegram_adapter):
        """Test stopping the router."""
        router.register_adapter(telegram_adapter)

        await router.start()
        await router.stop()

        assert telegram_adapter._stopped is True

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, router, telegram_adapter):
        """Test that stop cancels running tasks."""
        router.register_adapter(telegram_adapter)

        await router.start()

        async def long_running_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(long_running_task())
        router._tasks.add(task)

        await router.stop()

        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_semaphore_created_on_start(self, router):
        """Test that semaphore is created on start."""
        assert router._semaphore is None

        await router.start()

        assert router._semaphore is not None
        assert router._semaphore._value == 10

        await router.stop()

    @pytest.mark.asyncio
    async def test_concurrent_message_processing(self, router, telegram_adapter):
        """Test that messages can be processed concurrently."""
        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )

        for i in range(5):
            message = IncomingMessage(
                platform=PlatformType.TELEGRAM,
                user=user,
                content=f"Message {i}",
                message_id=f"msg_{i}",
            )
            telegram_adapter.add_test_message(message)

        router.register_adapter(telegram_adapter)
        await router.start()

        await asyncio.sleep(0.1)

        await router.stop()

        assert len(telegram_adapter._messages_queue) == 0

    @pytest.mark.asyncio
    async def test_adapter_isolation(self, router, telegram_adapter, slack_adapter):
        """Test that adapters are isolated from each other."""
        telegram_user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        slack_user = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="U123",
        )

        telegram_adapter.add_test_message(IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=telegram_user,
            content="Telegram message",
            message_id="tg_msg_1",
        ))

        slack_adapter.add_test_message(IncomingMessage(
            platform=PlatformType.SLACK,
            user=slack_user,
            content="Slack message",
            message_id="slack_msg_1",
        ))

        router.register_adapter(telegram_adapter)
        router.register_adapter(slack_adapter)

        await router.start()
        await asyncio.sleep(0.1)
        await router.stop()

        assert len(telegram_adapter._messages_queue) == 0
        assert len(slack_adapter._messages_queue) == 0

    @pytest.mark.asyncio
    async def test_start_without_adapters(self, router):
        """Test starting router without any adapters."""
        await router.start()
        await router.stop()

    @pytest.mark.asyncio
    async def test_double_start_idempotent(self, router, telegram_adapter):
        """Test that starting twice is idempotent."""
        router.register_adapter(telegram_adapter)

        await router.start()
        await router.start()

        assert telegram_adapter._started is True

        await router.stop()

    @pytest.mark.asyncio
    async def test_double_stop_idempotent(self, router, telegram_adapter):
        """Test that stopping twice is idempotent."""
        router.register_adapter(telegram_adapter)

        await router.start()
        await router.stop()
        await router.stop()

        assert telegram_adapter._stopped is True


class TestRouterOrchestration:
    """Tests for router message processing orchestration."""

    @pytest.mark.asyncio
    async def test_rate_limiting_sends_error(self):
        """Test that rate-limited messages get error response."""
        adapter = MockAdapter(
            PlatformType.TELEGRAM,
            capabilities=PlatformCapabilities(supports_streaming=False),
        )

        # Rate limiter with 0 tokens = always rate-limited
        rate_limiter = RateLimiter(max_tokens=0, refill_rate=1.0, refill_interval=60.0)

        router = MessageRouter(rate_limiter=rate_limiter)
        router.register_adapter(adapter)

        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        message = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=user,
            content="Hello",
            message_id="msg_1",
            metadata={"channel_id": "ch_1"},
        )

        await router.start()
        adapter.add_test_message(message)
        await asyncio.sleep(0.1)
        await router.stop()

        # Should have sent rate limit error message
        assert len(adapter._sent_messages) == 1
        dest, msg = adapter._sent_messages[0]
        assert dest == "ch_1"
        assert "Rate limit" in msg.content

    @pytest.mark.asyncio
    async def test_typing_indicator_sent(self):
        """Test typing indicator is sent for adapters that support it."""
        adapter = MockAdapter(
            PlatformType.TELEGRAM,
            capabilities=PlatformCapabilities(
                supports_streaming=False,
                supports_typing_indicator=True,
            ),
        )

        router = MessageRouter()
        router.register_adapter(adapter)

        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )
        message = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=user,
            content="Hello",
            message_id="msg_1",
            metadata={"channel_id": "ch_1"},
        )

        await router.start()
        adapter.add_test_message(message)
        await asyncio.sleep(0.1)
        await router.stop()

        # Typing indicator should have been sent
        assert len(adapter._typing_indicators) == 1
        assert adapter._typing_indicators[0] == "ch_1"

    @pytest.mark.asyncio
    async def test_no_typing_indicator_when_unsupported(self):
        """Test no typing indicator for adapters without support."""
        adapter = MockAdapter(
            PlatformType.SLACK,
            capabilities=PlatformCapabilities(
                supports_streaming=False,
                supports_typing_indicator=False,
            ),
        )

        router = MessageRouter()
        router.register_adapter(adapter)

        user = PlatformUser(
            platform=PlatformType.SLACK,
            platform_user_id="U123",
        )
        message = IncomingMessage(
            platform=PlatformType.SLACK,
            user=user,
            content="Hello",
            message_id="msg_1",
            metadata={"channel_id": "ch_1"},
        )

        await router.start()
        adapter.add_test_message(message)
        await asyncio.sleep(0.1)
        await router.stop()

        assert len(adapter._typing_indicators) == 0

    @pytest.mark.asyncio
    async def test_session_mapping(self, tmp_path):
        """Test that session mapper is called for messages."""
        adapter = MockAdapter(
            PlatformType.TELEGRAM,
            capabilities=PlatformCapabilities(supports_streaming=False),
        )

        session_mapper = SessionMapper(storage_path=tmp_path / "sessions.json")

        router = MessageRouter(session_mapper=session_mapper)
        router.register_adapter(adapter)

        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
            username="testuser",
        )
        message = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=user,
            content="Hello",
            message_id="msg_1",
            metadata={"channel_id": "ch_1"},
        )

        await router.start()
        adapter.add_test_message(message)
        await asyncio.sleep(0.1)
        await router.stop()

        # Session should have been created
        mapping = session_mapper.get_mapping(user)
        assert mapping is not None
        assert mapping.session_id is not None

    @pytest.mark.asyncio
    async def test_destination_resolution_channel(self):
        """Test that destination_id resolves from channel_id metadata."""
        router = MessageRouter()
        message = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=PlatformUser(
                platform=PlatformType.TELEGRAM,
                platform_user_id="user_123",
            ),
            content="test",
            message_id="msg_1",
            metadata={"channel_id": "channel_456"},
        )

        assert router._resolve_destination(message) == "channel_456"

    @pytest.mark.asyncio
    async def test_destination_resolution_fallback(self):
        """Test that destination_id falls back to user_id when no channel_id."""
        router = MessageRouter()
        message = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=PlatformUser(
                platform=PlatformType.TELEGRAM,
                platform_user_id="user_123",
            ),
            content="test",
            message_id="msg_1",
        )

        assert router._resolve_destination(message) == "user_123"


class TestMockAdapter:
    """Tests for the MockAdapter itself."""

    @pytest.mark.asyncio
    async def test_adapter_lifecycle(self):
        """Test adapter start/stop lifecycle."""
        adapter = MockAdapter(PlatformType.TELEGRAM)

        assert adapter._started is False
        assert adapter._stopped is False

        await adapter.start()
        assert adapter._started is True
        assert adapter._stopped is False

        await adapter.stop()
        assert adapter._started is False
        assert adapter._stopped is True

    @pytest.mark.asyncio
    async def test_adapter_receive_messages(self):
        """Test receiving messages from adapter."""
        adapter = MockAdapter(PlatformType.TELEGRAM)

        user = PlatformUser(
            platform=PlatformType.TELEGRAM,
            platform_user_id="123",
        )

        msg = IncomingMessage(
            platform=PlatformType.TELEGRAM,
            user=user,
            content="Test",
            message_id="msg_1",
        )

        adapter.add_test_message(msg)

        await adapter.start()

        messages = []
        async for message in adapter.receive_messages():
            messages.append(message)
            break

        assert len(messages) == 1
        assert messages[0].content == "Test"

    @pytest.mark.asyncio
    async def test_adapter_send_message(self):
        """Test sending message through adapter."""
        adapter = MockAdapter(PlatformType.TELEGRAM)

        msg = OutgoingMessage(content="Response")

        message_id = await adapter.send_message("channel_123", msg)

        assert message_id.startswith("msg_")

    @pytest.mark.asyncio
    async def test_adapter_send_streaming_chunk(self):
        """Test sending streaming chunk."""
        adapter = MockAdapter(PlatformType.TELEGRAM)

        chunk = StreamChunk(content="Partial", is_final=False)

        message_id = await adapter.send_streaming_chunk("channel_123", chunk)

        assert message_id.startswith("msg_")

    @pytest.mark.asyncio
    async def test_adapter_capabilities(self):
        """Test adapter capabilities."""
        caps = PlatformCapabilities(
            supports_streaming=True,
            supports_markdown=True,
            markdown_flavor="MarkdownV2",
        )

        adapter = MockAdapter(PlatformType.TELEGRAM, capabilities=caps)

        assert adapter.capabilities.supports_streaming is True
        assert adapter.capabilities.supports_markdown is True
        assert adapter.capabilities.markdown_flavor == "MarkdownV2"
