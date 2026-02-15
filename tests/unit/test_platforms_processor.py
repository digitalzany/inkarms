"""Unit tests for platform message processor."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from inkarms.models.agent import AgentEvent, EventType
from inkarms.models.platforms import PlatformType, StreamChunk
from inkarms.platforms.processor import MessageProcessor, ProcessedResponse
from inkarms.providers import (
    AuthenticationError,
    AllProvidersFailedError,
    CompletionResponse,
    ProviderError,
    TokenUsage,
)
from inkarms.skills import Skill


@pytest.fixture
def mock_config():
    """Create a mock config."""
    config = Mock()
    config.system_prompt.personality = "You are a helpful assistant."
    return config


@pytest.fixture
def mock_audit_logger():
    """Create a mock audit logger."""
    logger = Mock()
    logger.log_query = Mock()
    logger.log_platform_message_received = Mock()
    logger.log_platform_message_sent = Mock()
    return logger


@pytest.fixture
def mock_skill_manager():
    """Create a mock skill manager."""
    manager = Mock()
    manager.get_skill = Mock()
    manager.get_skills_for_query = Mock(return_value=[])
    return manager


@pytest.fixture
def mock_provider_manager():
    """Create a mock provider manager."""
    manager = AsyncMock()
    manager.resolve_model = Mock(return_value="gpt-4")
    manager.get_cost_summary = Mock()
    return manager


@pytest.fixture
def mock_session_manager():
    """Create a mock session manager."""
    manager = Mock()
    manager.set_system_prompt = Mock()
    manager.add_user_message = Mock()
    manager.add_assistant_message = Mock()
    return manager


@pytest.fixture
def processor(mock_skill_manager):
    """Create a MessageProcessor with mocked skill manager."""
    with patch("inkarms.platforms.processor.get_config") as mock_get_config, \
         patch("inkarms.platforms.processor.get_audit_logger") as mock_get_audit:
        from inkarms.config.schema import Config, SystemPromptConfig, AgentConfigSchema

        # Create real config with custom personality and tools disabled for simpler testing
        mock_config = Config(
            system_prompt=SystemPromptConfig(personality="Test personality"),
            agent=AgentConfigSchema(enable_tools=False),
        )
        mock_get_config.return_value = mock_config
        mock_get_audit.return_value = Mock()

        return MessageProcessor(skill_manager=mock_skill_manager)


class TestProcessedResponse:
    """Tests for ProcessedResponse model."""

    def test_create_response(self):
        """Test creating a processed response."""
        response = ProcessedResponse(
            content="Test response",
            model="gpt-4",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            cost=0.005,
            finish_reason="stop",
        )

        assert response.content == "Test response"
        assert response.model == "gpt-4"
        assert response.provider == "openai"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.cost == 0.005
        assert response.finish_reason == "stop"
        assert response.error is None

    def test_response_with_error(self):
        """Test creating a response with error."""
        response = ProcessedResponse(
            content="",
            model="",
            provider="",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            finish_reason="error",
            error="Authentication failed",
        )

        assert response.error == "Authentication failed"
        assert response.finish_reason == "error"


class TestMessageProcessor:
    """Tests for MessageProcessor class."""

    def test_build_system_prompt_with_personality(self, processor):
        """Test building system prompt with personality."""
        prompt = processor._context_builder.build_system_prompt([])

        assert "Test personality" in prompt

    def test_build_system_prompt_with_skills(self, processor):
        """Test building system prompt with skills."""
        # Create mock skill
        skill = Mock(spec=Skill)
        skill.get_system_prompt_injection = Mock(return_value="Skill instructions here")

        prompt = processor._context_builder.build_system_prompt([skill])

        assert "Test personality" in prompt
        assert "Skill instructions" in prompt
        assert "Active Skills" in prompt

    def test_build_system_prompt_without_personality(self, mock_skill_manager):
        """Test building system prompt without personality."""
        with patch("inkarms.platforms.processor.get_config") as mock_get_config, \
             patch("inkarms.platforms.processor.get_audit_logger"):
            from inkarms.config.schema import Config, SystemPromptConfig

            # Use real Config with empty personality
            mock_config = Config(
                system_prompt=SystemPromptConfig(personality="")
            )
            mock_get_config.return_value = mock_config

            processor = MessageProcessor(skill_manager=mock_skill_manager)
            prompt = processor._context_builder.build_system_prompt([])

            assert prompt == ""

    def test_build_messages_basic(self, processor):
        """Test building messages without session."""
        messages = processor._context_builder.build_messages(
            query="Hello, bot!",
            skills=[],
            session_id=None,
            session_manager=processor._session_manager,
        )

        # Should have system and user messages
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello, bot!"

    def test_build_messages_with_session(self, processor):
        """Test building messages with session tracking."""
        processor._session_manager.get_messages = Mock(return_value=[])
        processor._session_manager.set_system_prompt = Mock()
        processor._session_manager.add_user_message = Mock()

        messages = processor._context_builder.build_messages(
            query="Test query",
            skills=[],
            session_id="test_session_123",
            session_manager=processor._session_manager,
        )

        # Session manager should be called
        processor._session_manager.get_messages.assert_called_once_with(include_system=False)
        processor._session_manager.set_system_prompt.assert_called_once()
        processor._session_manager.add_user_message.assert_called_once_with("Test query")

    def test_build_messages_includes_prior_history(self, processor):
        """Test that prior session history is included in messages."""
        prior_turns = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        processor._session_manager.get_messages = Mock(return_value=prior_turns)

        messages = processor._context_builder.build_messages(
            query="Follow-up question",
            skills=[],
            session_id="test_session_123",
            session_manager=processor._session_manager,
        )

        # system + 2 prior turns + current user query
        assert len(messages) == 4
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello"
        assert messages[2].role == "assistant"
        assert messages[2].content == "Hi there!"
        assert messages[3].role == "user"
        assert messages[3].content == "Follow-up question"

    def test_build_messages_no_history_without_session_id(self, processor):
        """Test that no history is loaded when session_id is None (CLI path)."""
        processor._session_manager.get_messages = Mock(return_value=[])

        messages = processor._context_builder.build_messages(
            query="Hello",
            skills=[],
            session_id=None,
            session_manager=processor._session_manager,
        )

        # Should NOT call get_messages without a session_id
        processor._session_manager.get_messages.assert_not_called()
        # Should only have system + user
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_process_success(self, processor, mock_provider_manager):
        """Test successful message processing."""
        # Setup mock response
        mock_response = CompletionResponse(
            content="Hello! How can I help?",
            model="gpt-4",
            provider="openai",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            cost=0.001,
            finish_reason="stop",
        )
        mock_provider_manager.complete = AsyncMock(return_value=mock_response)

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            response = await processor.process(
                query="Hello",
                platform=PlatformType.CLI,
            )

            assert response.content == "Hello! How can I help?"
            assert response.model == "gpt-4"
            assert response.input_tokens == 10
            assert response.output_tokens == 5
            assert response.cost == 0.001
            assert response.error is None

    @pytest.mark.asyncio
    async def test_process_with_platform_user(self, processor, mock_provider_manager):
        """Test processing with platform user information."""
        mock_response = CompletionResponse(
            content="Response",
            model="gpt-4",
            provider="openai",
            usage=TokenUsage(input_tokens=10, output_tokens=5),
            cost=0.001,
            finish_reason="stop",
        )
        mock_provider_manager.complete = AsyncMock(return_value=mock_response)

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            response = await processor.process(
                query="Test",
                platform=PlatformType.TELEGRAM,
                platform_user_id="123456789",
                platform_username="john_doe",
            )

            # Should call platform-specific audit logging
            processor._audit_logger.log_platform_message_received.assert_called_once()
            processor._audit_logger.log_platform_message_sent.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_authentication_error(self, processor, mock_provider_manager):
        """Test handling authentication error."""
        mock_provider_manager.complete = AsyncMock(
            side_effect=AuthenticationError("Invalid API key", provider="openai")
        )

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            response = await processor.process(
                query="Test",
                platform=PlatformType.CLI,
            )

            assert response.error is not None
            assert "Authentication failed" in response.error
            assert response.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_process_all_providers_failed(self, processor, mock_provider_manager):
        """Test handling all providers failed error."""
        mock_provider_manager.complete = AsyncMock(
            side_effect=AllProvidersFailedError(
                "All providers failed",
                failed_providers=["openai", "anthropic"]
            )
        )

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            response = await processor.process(
                query="Test",
                platform=PlatformType.CLI,
            )

            assert response.error is not None
            assert "All providers failed" in response.error
            assert response.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_process_provider_error(self, processor, mock_provider_manager):
        """Test handling provider error."""
        mock_provider_manager.complete = AsyncMock(
            side_effect=ProviderError("Rate limit exceeded", provider="openai")
        )

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            response = await processor.process(
                query="Test",
                platform=PlatformType.CLI,
            )

            assert response.error is not None
            assert "Provider error" in response.error
            assert response.finish_reason == "error"

    @pytest.mark.asyncio
    async def test_process_streaming_success(self, processor, mock_provider_manager):
        """Test successful streaming message processing."""
        # Setup mock streaming response
        async def mock_stream():
            yield Mock(content="Hello ")
            yield Mock(content="world")
            yield Mock(content="!")

        mock_provider_manager.complete = AsyncMock(return_value=mock_stream())
        mock_provider_manager.get_cost_summary = Mock(return_value=Mock(
            total_tokens=15,
            total_cost=0.002,
        ))

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            chunks = []
            async for chunk in processor.process_streaming(
                query="Hello",
                platform=PlatformType.CLI,
            ):
                chunks.append(chunk)

            # Should get progressive chunks plus final
            assert len(chunks) > 0

            # Final chunk should be marked as final
            assert chunks[-1].is_final is True

            # Final content should be complete
            assert chunks[-1].content == "Hello world!"

    @pytest.mark.asyncio
    async def test_process_streaming_with_platform_user(self, processor, mock_provider_manager):
        """Test streaming with platform user information."""
        async def mock_stream():
            yield Mock(content="Test")

        mock_provider_manager.complete = AsyncMock(return_value=mock_stream())
        mock_provider_manager.get_cost_summary = Mock(return_value=Mock(
            total_tokens=10,
            total_cost=0.001,
        ))

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            chunks = []
            async for chunk in processor.process_streaming(
                query="Test",
                platform=PlatformType.TELEGRAM,
                platform_user_id="123",
                platform_username="test_user",
            ):
                chunks.append(chunk)

            # Should call platform-specific audit logging
            processor._audit_logger.log_platform_message_received.assert_called_once()
            processor._audit_logger.log_platform_message_sent.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_streaming_authentication_error(self, processor, mock_provider_manager):
        """Test handling authentication error in streaming."""
        mock_provider_manager.complete = AsyncMock(
            side_effect=AuthenticationError("Invalid API key", provider="openai")
        )

        with patch("inkarms.platforms.processor.get_provider_manager",
                  return_value=mock_provider_manager):

            chunks = []
            async for chunk in processor.process_streaming(
                query="Test",
                platform=PlatformType.CLI,
            ):
                chunks.append(chunk)

            # Should get error chunk
            assert len(chunks) == 1
            assert "Authentication failed" in chunks[0].content
            assert chunks[0].is_final is True

    @pytest.mark.asyncio
    async def test_load_skills_explicit(self, processor, mock_skill_manager):
        """Test loading explicit skills."""
        mock_skill = Mock(spec=Skill)
        mock_skill.name = "test-skill"
        mock_skill_manager.get_skill = Mock(return_value=mock_skill)

        skills = await processor._load_skills(
            query="Test",
            skill_names=["test-skill"],
            auto_skills=False,
        )

        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        mock_skill_manager.get_skill.assert_called_once_with("test-skill")

    @pytest.mark.asyncio
    async def test_load_skills_auto_discovery(self, processor, mock_skill_manager):
        """Test auto skill discovery."""
        mock_skills = [
            Mock(spec=Skill, name="skill1"),
            Mock(spec=Skill, name="skill2"),
        ]
        mock_skill_manager.get_skills_for_query = Mock(return_value=mock_skills)

        skills = await processor._load_skills(
            query="Test query",
            skill_names=None,
            auto_skills=True,
        )

        assert len(skills) == 2
        mock_skill_manager.get_skills_for_query.assert_called_once_with("Test query", max_skills=3)

    @pytest.mark.asyncio
    async def test_load_skills_explicit_takes_priority(self, processor, mock_skill_manager):
        """Test that explicit skills take priority over auto discovery."""
        mock_skill = Mock(spec=Skill)
        mock_skill.name = "explicit-skill"
        mock_skill_manager.get_skill = Mock(return_value=mock_skill)

        skills = await processor._load_skills(
            query="Test",
            skill_names=["explicit-skill"],
            auto_skills=True,  # Should be ignored
        )

        # Should only load explicit skill
        assert len(skills) == 1
        assert skills[0].name == "explicit-skill"

        # Auto discovery should not be called
        mock_skill_manager.get_skills_for_query.assert_not_called()


class TestPlatformEventCallback:
    """Tests for _platform_event_callback used in platform startup."""

    def test_callback_handles_tool_start(self):
        """Event callback should not raise for TOOL_START events."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.TOOL_START,
            iteration=0,
            tool_name="execute_bash",
            message="Executing tool: execute_bash",
        )
        # Should not raise
        _platform_event_callback(event)

    def test_callback_handles_tool_complete(self):
        """Event callback should not raise for TOOL_COMPLETE events."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.TOOL_COMPLETE,
            iteration=0,
            tool_name="read_file",
            message="Tool completed: read_file",
        )
        _platform_event_callback(event)

    def test_callback_handles_tool_error(self):
        """Event callback should not raise for TOOL_ERROR events."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.TOOL_ERROR,
            iteration=0,
            tool_name="bash",
            message="Tool failed: bash",
        )
        _platform_event_callback(event)

    def test_callback_handles_iteration_start(self):
        """Event callback should not raise for ITERATION_START events."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.ITERATION_START,
            iteration=0,
            message="Starting iteration 1/10",
        )
        _platform_event_callback(event)

    def test_callback_handles_agent_complete(self):
        """Event callback should not raise for AGENT_COMPLETE events."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.AGENT_COMPLETE,
            iteration=2,
            message="Agent completed after 3 iterations",
        )
        _platform_event_callback(event)

    def test_callback_handles_unmatched_event(self):
        """Event callback should not raise for unmatched event types."""
        from inkarms.cli.commands.platforms import _platform_event_callback

        event = AgentEvent(
            event_type=EventType.AI_RESPONSE,
            iteration=0,
            message="AI response received",
        )
        # Should not raise even though it doesn't match any logged type
        _platform_event_callback(event)


class TestMessageProcessorCallbackWiring:
    """Tests that MessageProcessor passes callbacks through to agents."""

    def test_callbacks_stored_on_processor(self, mock_skill_manager):
        """Callbacks passed to MessageProcessor should be stored."""
        event_cb = Mock()
        approval_cb = Mock(return_value=True)

        with patch("inkarms.platforms.processor.get_config") as mock_get_config, \
             patch("inkarms.platforms.processor.get_audit_logger"):
            from inkarms.config.schema import Config, SystemPromptConfig, AgentConfigSchema

            mock_config = Config(
                system_prompt=SystemPromptConfig(personality="Test"),
                agent=AgentConfigSchema(enable_tools=False),
            )
            mock_get_config.return_value = mock_config

            proc = MessageProcessor(
                skill_manager=mock_skill_manager,
                event_callback=event_cb,
                tool_approval_callback=approval_cb,
            )

            assert proc._event_callback is event_cb
            assert proc._tool_approval_callback is approval_cb

    def test_create_agent_passes_callbacks(self, mock_skill_manager):
        """_create_agent should pass callbacks to AgentLoop."""
        event_cb = Mock()
        approval_cb = Mock(return_value=True)

        with patch("inkarms.platforms.processor.get_config") as mock_get_config, \
             patch("inkarms.platforms.processor.get_audit_logger"), \
             patch("inkarms.platforms.processor.register_builtin_tools"):
            from inkarms.config.schema import Config, SystemPromptConfig, AgentConfigSchema

            mock_config = Config(
                system_prompt=SystemPromptConfig(personality="Test"),
                agent=AgentConfigSchema(enable_tools=True),
            )
            mock_get_config.return_value = mock_config

            proc = MessageProcessor(
                skill_manager=mock_skill_manager,
                event_callback=event_cb,
                tool_approval_callback=approval_cb,
            )

            mock_manager = Mock()
            agent = proc._create_agent(mock_manager)

            assert agent.event_callback is event_cb
            assert agent.approval_callback is approval_cb


class TestEventToStreamChunk:
    """Tests for MessageProcessor._event_to_stream_chunk."""

    def test_tool_start_returns_chunk(self):
        """TOOL_START event should produce a progress chunk."""
        event = AgentEvent(
            event_type=EventType.TOOL_START,
            iteration=0,
            tool_name="execute_bash",
            message="Executing tool",
        )
        chunk = MessageProcessor._event_to_stream_chunk(event)

        assert chunk is not None
        assert "execute_bash" in chunk.content
        assert chunk.is_final is False
        assert chunk.metadata.get("event_type") == EventType.TOOL_START

    def test_tool_complete_returns_chunk(self):
        """TOOL_COMPLETE event should produce a progress chunk."""
        event = AgentEvent(
            event_type=EventType.TOOL_COMPLETE,
            iteration=0,
            tool_name="read_file",
            message="Tool completed",
        )
        chunk = MessageProcessor._event_to_stream_chunk(event)

        assert chunk is not None
        assert "read_file" in chunk.content
        assert chunk.is_final is False

    def test_tool_error_returns_chunk(self):
        """TOOL_ERROR event should produce a progress chunk."""
        event = AgentEvent(
            event_type=EventType.TOOL_ERROR,
            iteration=0,
            tool_name="bash",
            message="Tool error",
        )
        chunk = MessageProcessor._event_to_stream_chunk(event)

        assert chunk is not None
        assert "bash" in chunk.content

    def test_ai_response_returns_none(self):
        """AI_RESPONSE event should not produce a chunk."""
        event = AgentEvent(
            event_type=EventType.AI_RESPONSE,
            iteration=0,
            message="AI response received",
        )
        chunk = MessageProcessor._event_to_stream_chunk(event)

        assert chunk is None

    def test_iteration_start_returns_none(self):
        """ITERATION_START event should not produce a chunk."""
        event = AgentEvent(
            event_type=EventType.ITERATION_START,
            iteration=0,
            message="Starting iteration",
        )
        chunk = MessageProcessor._event_to_stream_chunk(event)

        assert chunk is None
