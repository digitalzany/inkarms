"""Unit tests for platform message processor."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from inkarms.platforms.models import PlatformType, StreamChunk
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
    manager._resolve_model = Mock(return_value="gpt-4")
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
        prompt = processor._build_system_prompt([])

        assert "Test personality" in prompt

    def test_build_system_prompt_with_skills(self, processor):
        """Test building system prompt with skills."""
        # Create mock skill
        skill = Mock(spec=Skill)
        skill.get_system_prompt_injection = Mock(return_value="Skill instructions here")

        prompt = processor._build_system_prompt([skill])

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
            prompt = processor._build_system_prompt([])

            assert prompt == ""

    def test_build_messages_basic(self, processor):
        """Test building messages without session."""
        messages = processor._build_messages(
            query="Hello, bot!",
            skills=[],
            session_id=None,
        )

        # Should have system and user messages
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[1].content == "Hello, bot!"

    def test_build_messages_with_session(self, processor, mock_session_manager):
        """Test building messages with session tracking."""
        with patch("inkarms.platforms.processor.get_session_manager",
                  return_value=mock_session_manager):

            messages = processor._build_messages(
                query="Test query",
                skills=[],
                session_id="test_session_123",
            )

            # Session manager should be called
            mock_session_manager.set_system_prompt.assert_called_once()
            mock_session_manager.add_user_message.assert_called_once_with("Test query")

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
