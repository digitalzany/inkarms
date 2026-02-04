"""
Unit tests for the InkArms provider layer.
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkarms.config.schema import ProviderConfig
from inkarms.providers import (
    AllProvidersFailedError,
    AuthenticationError,
    CompletionResponse,
    CostTracker,
    FailureType,
    FallbackHandler,
    HealthStatus,
    Message,
    MessageRole,
    ProviderError,
    ProviderHealth,
    ProviderManager,
    RateLimitError,
    SessionUsage,
    StreamChunk,
    TokenUsage,
    classify_error,
    should_retry,
)
from inkarms.secrets import SecretsManager


# =============================================================================
# Model Tests
# =============================================================================


class TestMessage:
    """Tests for Message model."""

    def test_create_user_message(self):
        """Test creating a user message."""
        msg = Message.user("Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None

    def test_create_system_message(self):
        """Test creating a system message."""
        msg = Message.system("You are helpful.")
        assert msg.role == "system"
        assert msg.content == "You are helpful."

    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        msg = Message.assistant("I can help.")
        assert msg.role == "assistant"
        assert msg.content == "I can help."

    def test_to_dict(self):
        """Test converting message to dict."""
        msg = Message(role="user", content="Test", name="John")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Test", "name": "John"}

    def test_to_dict_without_name(self):
        """Test converting message to dict without name."""
        msg = Message(role="user", content="Test")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Test"}


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_default_total(self):
        """Test that total is calculated from input + output."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_explicit_total(self):
        """Test explicit total is preserved."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, total_tokens=160)
        assert usage.total_tokens == 160


class TestStreamChunk:
    """Tests for StreamChunk model."""

    def test_basic_chunk(self):
        """Test basic stream chunk."""
        chunk = StreamChunk(content="Hello")
        assert chunk.content == "Hello"
        assert chunk.finish_reason is None

    def test_final_chunk(self):
        """Test final stream chunk with finish reason."""
        chunk = StreamChunk(content=".", finish_reason="stop", model="gpt-4")
        assert chunk.finish_reason == "stop"
        assert chunk.model == "gpt-4"


# =============================================================================
# Exception Tests
# =============================================================================


class TestExceptions:
    """Tests for provider exceptions."""

    def test_classify_rate_limit(self):
        """Test classifying rate limit error."""
        error = RateLimitError("Rate limited", retry_after=60)
        assert classify_error(error) == FailureType.RATE_LIMIT
        assert error.retry_after == 60

    def test_classify_auth_error(self):
        """Test classifying authentication error."""
        error = AuthenticationError("Invalid key")
        assert classify_error(error) == FailureType.AUTH_ERROR

    def test_should_retry_rate_limit(self):
        """Test that rate limits should trigger retry."""
        assert should_retry(FailureType.RATE_LIMIT) is True

    def test_should_not_retry_auth(self):
        """Test that auth errors should not retry."""
        assert should_retry(FailureType.AUTH_ERROR) is False

    def test_all_providers_failed(self):
        """Test AllProvidersFailedError."""
        error = AllProvidersFailedError("All failed", failed_providers=["gpt-4", "claude-3"])
        assert error.failed_providers == ["gpt-4", "claude-3"]


# =============================================================================
# Fallback Handler Tests
# =============================================================================


class TestFallbackHandler:
    """Tests for FallbackHandler."""

    def test_get_next_provider(self):
        """Test getting next provider in chain."""
        handler = FallbackHandler(fallback_chain=["gpt-4", "claude-3", "llama"])

        assert handler.get_next_provider() == "gpt-4"
        assert handler.get_next_provider() == "claude-3"
        assert handler.get_next_provider() == "llama"
        assert handler.get_next_provider() is None

    def test_mark_failed_skips_provider(self):
        """Test that failed providers are skipped."""
        handler = FallbackHandler(fallback_chain=["gpt-4", "claude-3"])

        handler.mark_failed("gpt-4", Exception("failed"))

        # Reset index but keep failed set
        handler.current_index = 0

        # Should skip gpt-4 and return claude-3
        assert handler.get_next_provider() == "claude-3"

    def test_should_fallback_on_network_error(self):
        """Test fallback on network error."""
        handler = FallbackHandler(fallback_chain=["gpt-4"])
        from inkarms.providers.exceptions import NetworkError

        error = NetworkError("Connection failed")
        assert handler.should_fallback(error) is True

    def test_no_fallback_on_auth_error(self):
        """Test no fallback on auth error."""
        handler = FallbackHandler(fallback_chain=["gpt-4"])

        error = AuthenticationError("Bad key")
        assert handler.should_fallback(error) is False

    def test_reset(self):
        """Test resetting fallback state."""
        handler = FallbackHandler(fallback_chain=["gpt-4", "claude-3"])
        handler.get_next_provider()
        handler.mark_failed("gpt-4", Exception("failed"))

        handler.reset()

        assert handler.current_index == 0
        assert len(handler.failed_providers) == 0

    def test_has_more_providers(self):
        """Test checking for more providers."""
        handler = FallbackHandler(fallback_chain=["gpt-4"])

        assert handler.has_more_providers is True
        handler.get_next_provider()
        assert handler.has_more_providers is False


# =============================================================================
# Secrets Manager Tests
# =============================================================================


class TestSecretsManager:
    """Tests for SecretsManager."""

    def test_set_and_get_secret(self, temp_dir):
        """Test storing and retrieving a secret."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")

        secrets.set("openai", "sk-test-key-123")
        value = secrets.get("openai")

        assert value == "sk-test-key-123"

    def test_get_nonexistent_secret(self, temp_dir):
        """Test getting a secret that doesn't exist."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")

        value = secrets.get("nonexistent")
        assert value is None

    def test_delete_secret(self, temp_dir):
        """Test deleting a secret."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        secrets.set("test", "value")

        assert secrets.delete("test") is True
        assert secrets.get("test") is None
        assert secrets.delete("test") is False  # Already deleted

    def test_list_secrets(self, temp_dir):
        """Test listing all secrets."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        secrets.set("openai", "key1")
        secrets.set("anthropic", "key2")

        names = secrets.list()
        assert sorted(names) == ["anthropic", "openai"]

    def test_exists(self, temp_dir):
        """Test checking if secret exists."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        secrets.set("test", "value")

        assert secrets.exists("test") is True
        assert secrets.exists("nonexistent") is False

    def test_load_to_env(self, temp_dir, monkeypatch):
        """Test loading secret to environment."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        secrets.set("openai", "sk-test")

        # Clear any existing value
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = secrets.load_to_env("openai")

        assert result is True
        assert os.environ.get("OPENAI_API_KEY") == "sk-test"

    def test_load_to_env_with_existing(self, temp_dir, monkeypatch):
        """Test that existing env vars are not overwritten."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        secrets.set("openai", "sk-stored")

        # Set existing value
        monkeypatch.setenv("OPENAI_API_KEY", "sk-existing")

        result = secrets.load_to_env("openai")

        assert result is True
        assert os.environ.get("OPENAI_API_KEY") == "sk-existing"

    def test_get_env_var_name(self, temp_dir):
        """Test getting environment variable names."""
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")

        assert secrets.get_env_var_name("openai") == "OPENAI_API_KEY"
        assert secrets.get_env_var_name("anthropic") == "ANTHROPIC_API_KEY"
        assert secrets.get_env_var_name("custom") == "CUSTOM_API_KEY"


# =============================================================================
# Cost Tracker Tests
# =============================================================================


class TestCostTracker:
    """Tests for CostTracker."""

    def test_record_usage(self):
        """Test recording usage."""
        tracker = CostTracker()
        usage = TokenUsage(input_tokens=100, output_tokens=50)

        tracker.record_usage("gpt-4", usage, 0.01)

        assert tracker.total_tokens == 150
        assert tracker.total_cost == 0.01
        assert tracker.total_requests == 1

    def test_multiple_models(self):
        """Test tracking multiple models."""
        tracker = CostTracker()

        tracker.record_usage("gpt-4", TokenUsage(100, 50), 0.01)
        tracker.record_usage("claude-3", TokenUsage(200, 100), 0.02)

        summary = tracker.get_session_summary()

        assert len(summary.by_model) == 2
        assert summary.total_cost == 0.03
        assert summary.total_input_tokens == 300
        assert summary.total_output_tokens == 150

    def test_reset(self):
        """Test resetting tracker."""
        tracker = CostTracker()
        tracker.record_usage("gpt-4", TokenUsage(100, 50), 0.01)

        tracker.reset()

        assert tracker.total_tokens == 0
        assert tracker.total_cost == 0.0

    def test_get_model_usage(self):
        """Test getting usage for specific model."""
        tracker = CostTracker()
        tracker.record_usage("gpt-4", TokenUsage(100, 50), 0.01)

        usage = tracker.get_model_usage("gpt-4")
        assert usage is not None
        assert usage.input_tokens == 100

        usage = tracker.get_model_usage("nonexistent")
        assert usage is None


# =============================================================================
# Provider Manager Tests
# =============================================================================


class TestProviderManager:
    """Tests for ProviderManager."""

    def test_resolve_model_default(self, temp_dir):
        """Test resolving default model."""
        config = ProviderConfig(
            default="anthropic/claude-3",
            aliases={"fast": "openai/gpt-3.5-turbo"},
        )
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        assert manager._resolve_model(None) == "anthropic/claude-3"
        assert manager._resolve_model("default") == "anthropic/claude-3"

    def test_resolve_model_alias(self, temp_dir):
        """Test resolving model alias."""
        config = ProviderConfig(
            default="anthropic/claude-3",
            aliases={"fast": "openai/gpt-3.5-turbo"},
        )
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        assert manager._resolve_model("fast") == "openai/gpt-3.5-turbo"

    def test_resolve_model_direct(self, temp_dir):
        """Test resolving direct model name."""
        config = ProviderConfig(default="anthropic/claude-3")
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        assert manager._resolve_model("openai/gpt-4") == "openai/gpt-4"

    def test_extract_provider(self, temp_dir):
        """Test extracting provider from model string."""
        config = ProviderConfig()
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        assert manager._extract_provider("openai/gpt-4") == "openai"
        assert manager._extract_provider("anthropic/claude-3") == "anthropic"
        assert manager._extract_provider("gpt-4") == "unknown"

    def test_to_litellm_messages(self, temp_dir):
        """Test converting messages to LiteLLM format."""
        config = ProviderConfig()
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        messages = [
            Message.system("Be helpful"),
            Message.user("Hello"),
        ]

        litellm_msgs = manager._to_litellm_messages(messages)

        assert litellm_msgs == [
            {"role": "system", "content": "Be helpful"},
            {"role": "user", "content": "Hello"},
        ]

    def test_get_current_model(self, temp_dir):
        """Test getting current model."""
        config = ProviderConfig(default="anthropic/claude-3")
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        assert manager.get_current_model() == "anthropic/claude-3"

    def test_reset_session(self, temp_dir):
        """Test resetting session state."""
        config = ProviderConfig(default="anthropic/claude-3")
        secrets = SecretsManager(secrets_dir=temp_dir / "secrets")
        manager = ProviderManager(config, secrets)

        # Set session override
        manager._session_default = "openai/gpt-4"

        manager.reset_session()

        assert manager._session_default is None
        assert manager.get_current_model() == "anthropic/claude-3"


# =============================================================================
# Health Status Tests
# =============================================================================


class TestHealthStatus:
    """Tests for health-related models."""

    def test_health_status_enum(self):
        """Test HealthStatus enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"

    def test_provider_health(self):
        """Test ProviderHealth model."""
        from datetime import datetime

        health = ProviderHealth(
            provider="openai/gpt-4",
            status=HealthStatus.HEALTHY,
            latency_ms=150.5,
            last_check=datetime.now(),
        )

        assert health.provider == "openai/gpt-4"
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms == 150.5
        assert health.error is None

    def test_provider_health_with_error(self):
        """Test ProviderHealth with error."""
        from datetime import datetime

        health = ProviderHealth(
            provider="openai/gpt-4",
            status=HealthStatus.UNHEALTHY,
            latency_ms=None,
            last_check=datetime.now(),
            error="Connection refused",
        )

        assert health.status == HealthStatus.UNHEALTHY
        assert health.error == "Connection refused"
