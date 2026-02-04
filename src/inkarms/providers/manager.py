"""
Provider manager for InkArms.

Main interface for AI provider access via LiteLLM.
Handles model resolution, API key management, fallbacks, and response parsing.
"""

import logging
import os
import time
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import litellm
from litellm import acompletion, completion_cost

from inkarms.config.schema import ProviderConfig
from inkarms.providers.cost import CostTracker
from inkarms.providers.exceptions import (
    AllProvidersFailedError,
    AuthenticationError,
    ProviderError,
    classify_error,
    should_retry,
)
from inkarms.providers.fallback import FallbackHandler
from inkarms.providers.models import (
    CompletionResponse,
    HealthStatus,
    Message,
    ProviderHealth,
    StreamChunk,
    TokenUsage,
)
from inkarms.secrets import SecretsManager

logger = logging.getLogger(__name__)

# Configure LiteLLM defaults
litellm.drop_params = True  # Drop unsupported params per-provider


class ProviderManager:
    """
    Manages AI provider connections via LiteLLM.

    Provides a unified interface for completions across providers,
    with automatic fallback, cost tracking, and health monitoring.
    """

    def __init__(
        self,
        config: ProviderConfig,
        secrets: SecretsManager | None = None,
        cost_tracker: CostTracker | None = None,
    ):
        """
        Initialize the provider manager.

        Args:
            config: Provider configuration.
            secrets: Secrets manager for API keys. Creates new if not provided.
            cost_tracker: Cost tracker instance. Creates new if not provided.
        """
        self.config = config
        self.secrets = secrets or SecretsManager()
        self.cost_tracker = cost_tracker or CostTracker()

        # Session-level override for default model
        self._session_default: str | None = None

        # Setup API keys
        self._setup_api_keys()

    def _setup_api_keys(self) -> None:
        """Load API keys into environment for LiteLLM."""
        # Load all stored secrets to environment
        loaded = self.secrets.load_all_to_env()
        if loaded:
            logger.debug(f"Loaded secrets: {list(loaded.keys())}")

    def _resolve_model(self, model: str | None) -> str:
        """
        Resolve model name from alias or default.

        Args:
            model: Model name, alias, or None for default.

        Returns:
            The fully resolved model identifier.
        """
        if model is None or model == "default":
            # Session override takes precedence
            if self._session_default:
                return self._session_default
            return self.config.default

        # Check aliases
        if model in self.config.aliases:
            resolved = self.config.aliases[model]
            logger.debug(f"Resolved alias '{model}' to '{resolved}'")
            return resolved

        # Return as-is (assumed to be full model name)
        return model

    def _extract_provider(self, model: str) -> str:
        """Extract provider name from model string."""
        if "/" in model:
            return model.split("/")[0]
        return "unknown"

    def _to_litellm_messages(
        self,
        messages: list[Message],
    ) -> list[dict[str, Any]]:
        """Convert internal messages to LiteLLM format."""
        return [msg.to_dict() for msg in messages]

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> CompletionResponse | AsyncIterator[StreamChunk]:
        """
        Send completion request to provider.

        Args:
            messages: Conversation messages.
            model: Model to use (name, alias, or None for default).
            stream: Whether to stream the response.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            tools: Tool definitions for function calling (Anthropic format).
            **kwargs: Additional parameters passed to LiteLLM.

        Returns:
            CompletionResponse for non-streaming, AsyncIterator[StreamChunk] for streaming.

        Raises:
            AllProvidersFailedError: If all providers (including fallbacks) fail.
            AuthenticationError: If authentication fails (no fallback attempted).
            ProviderError: For other provider-related errors.
        """
        # Resolve model name
        resolved_model = self._resolve_model(model)
        logger.info(f"Completing with model: {resolved_model}")

        # Convert messages
        litellm_messages = self._to_litellm_messages(messages)

        # Build request kwargs
        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": litellm_messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs,
        }
        if max_tokens:
            request_kwargs["max_tokens"] = max_tokens
        if tools:
            request_kwargs["tools"] = tools

        try:
            if stream:
                return self._stream_completion(**request_kwargs)
            else:
                response = await acompletion(**request_kwargs)
                return self._parse_response(response, resolved_model)

        except Exception as e:
            # Try fallback chain
            return await self._handle_failure(
                e,
                messages,
                stream,
                request_kwargs,
            )

    async def _stream_completion(
        self,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream completion response.

        Args:
            **kwargs: Arguments for acompletion.

        Yields:
            StreamChunk for each response chunk.
        """
        model = kwargs.get("model", "unknown")
        response = await acompletion(**kwargs)
        async for chunk in response:  # type: ignore
            if chunk.choices and chunk.choices[0].delta.content:
                yield StreamChunk(
                    content=chunk.choices[0].delta.content,
                    finish_reason=chunk.choices[0].finish_reason,
                    model=model,
                )

    def _parse_response(
        self,
        response: Any,
        model: str,
    ) -> CompletionResponse:
        """Parse LiteLLM response into unified format."""
        provider = self._extract_provider(model)

        # Calculate cost
        try:
            cost = completion_cost(completion_response=response)
        except Exception:
            cost = 0.0

        # Extract usage
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
        )

        # Record usage
        self.cost_tracker.record_usage(model, usage, cost)

        # Extract content (handle both string and structured content)
        message = response.choices[0].message
        content = message.content or ""

        # Check if message has tool_calls or structured content
        # Anthropic returns content as a list of content blocks
        if hasattr(message, "content") and isinstance(message.content, list):
            # Structured content (tool use)
            content = message.content
        elif hasattr(message, "tool_calls") and message.tool_calls:
            # OpenAI-style tool calls - convert to Anthropic format
            content_blocks = []
            if message.content:
                content_blocks.append({"type": "text", "text": message.content})
            for tool_call in message.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "input": tool_call.function.arguments,
                })
            content = content_blocks

        return CompletionResponse(
            content=content,
            model=model,
            provider=provider,
            usage=usage,
            cost=cost,
            finish_reason=response.choices[0].finish_reason or "unknown",
            created_at=datetime.now(),
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def _handle_failure(
        self,
        error: Exception,
        messages: list[Message],
        stream: bool,
        original_kwargs: dict[str, Any],
    ) -> CompletionResponse | AsyncIterator[StreamChunk]:
        """Handle provider failure with fallback chain."""
        # Check if this is an auth error (no fallback)
        if not should_retry(classify_error(error)):
            logger.error(f"Non-retriable error: {error}")
            if "auth" in str(error).lower() or "api key" in str(error).lower():
                raise AuthenticationError(str(error)) from error
            raise ProviderError(str(error)) from error

        # Initialize fallback handler
        fallback = FallbackHandler(self.config.fallback.copy())
        fallback.mark_failed(original_kwargs["model"], error)

        last_error = error

        while fallback.should_fallback(last_error):
            next_provider = fallback.get_next_provider()
            if not next_provider:
                break

            logger.warning(f"Primary provider failed, trying fallback: {next_provider}")

            try:
                kwargs = {**original_kwargs, "model": next_provider}

                if stream:
                    return self._stream_completion(**kwargs)
                else:
                    response = await acompletion(**kwargs)
                    fallback.mark_success(next_provider)
                    return self._parse_response(response, next_provider)

            except Exception as e:
                fallback.mark_failed(next_provider, e)
                last_error = e
                continue

        # All providers failed
        raise AllProvidersFailedError(
            f"All providers failed. Last error: {last_error}\n{fallback.get_attempt_summary()}",
            failed_providers=list(fallback.failed_providers),
        )

    async def switch_provider(
        self,
        provider: str,
        *,
        persist: bool = False,
        test: bool = True,
    ) -> None:
        """
        Switch to different provider mid-session.

        Args:
            provider: New provider/model to use.
            persist: If True, update config file (not implemented yet).
            test: If True, test the connection first.

        Raises:
            AuthenticationError: If authentication fails.
            ProviderError: If provider test fails.
        """
        resolved = self._resolve_model(provider)

        if test:
            # Test connection with simple request
            try:
                await acompletion(
                    model=resolved,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=1,
                )
            except Exception as e:
                if "auth" in str(e).lower() or "api key" in str(e).lower():
                    raise AuthenticationError(f"Authentication failed for {provider}") from e
                raise ProviderError(f"Provider test failed: {e}") from e

        # Update session default
        self._session_default = resolved
        logger.info(f"Switched provider to: {resolved}")

        if persist:
            # TODO: Implement config file update
            logger.warning("Persistent provider switch not yet implemented")

    async def health_check(
        self,
        provider: str | None = None,
    ) -> dict[str, ProviderHealth]:
        """
        Check health of provider(s).

        Args:
            provider: Specific provider to check, or None for all configured.

        Returns:
            Dict mapping provider names to health status.
        """
        providers_to_check = (
            [provider] if provider else [self.config.default] + list(self.config.fallback)
        )

        # Deduplicate while preserving order
        seen = set()
        unique_providers = []
        for p in providers_to_check:
            if p not in seen:
                seen.add(p)
                unique_providers.append(p)

        results = {}
        for p in unique_providers:
            results[p] = await self._check_single_provider(p)

        return results

    async def _check_single_provider(self, provider: str) -> ProviderHealth:
        """Check single provider health."""
        start = time.monotonic()

        try:
            await acompletion(
                model=provider,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )

            latency = (time.monotonic() - start) * 1000

            return ProviderHealth(
                provider=provider,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                last_check=datetime.now(),
            )

        except Exception as e:
            error_str = str(e).lower()

            # Classify the error
            if "rate" in error_str or "limit" in error_str:
                status = HealthStatus.DEGRADED
                error_msg = "Rate limited"
            elif "auth" in error_str or "key" in error_str:
                status = HealthStatus.UNHEALTHY
                error_msg = "Authentication failed"
            else:
                status = HealthStatus.UNHEALTHY
                error_msg = str(e)[:100]

            return ProviderHealth(
                provider=provider,
                status=status,
                latency_ms=None,
                last_check=datetime.now(),
                error=error_msg,
            )

    def get_current_model(self) -> str:
        """Get the currently active model."""
        return self._session_default or self.config.default

    def get_cost_summary(self):
        """Get the session cost summary."""
        return self.cost_tracker.get_session_summary()

    def reset_session(self) -> None:
        """Reset session state (model override, cost tracking)."""
        self._session_default = None
        self.cost_tracker.reset()


# Singleton instance
_provider_manager: ProviderManager | None = None


def get_provider_manager(reload: bool = False) -> ProviderManager:
    """
    Get the global provider manager instance.

    Args:
        reload: Force recreation of the manager.

    Returns:
        ProviderManager instance.
    """
    global _provider_manager

    if _provider_manager is None or reload:
        from inkarms.config import get_config

        config = get_config(reload=reload)
        _provider_manager = ProviderManager(config.providers)

    return _provider_manager


def clear_provider_manager() -> None:
    """Clear the global provider manager instance."""
    global _provider_manager
    _provider_manager = None
