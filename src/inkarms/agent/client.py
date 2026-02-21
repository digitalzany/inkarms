"""AI Client for provider interaction."""

from collections.abc import Callable
from typing import Any

from litellm import acompletion, stream_chunk_builder

from inkarms.providers.manager import ProviderManager


class AIClient:
    """Client for interacting with AI providers."""

    def __init__(
        self,
        provider_manager: ProviderManager,
        stream_callback: Callable[[str], None] | None = None,
    ):
        """Initialize AI client.

        Args:
            provider_manager: Provider manager instance.
            stream_callback: Optional callback for streaming text tokens.
        """
        self.provider_manager = provider_manager
        self.stream_callback = stream_callback

    async def call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str | None,
    ) -> dict[str, Any]:
        """Call AI provider.

        Args:
            messages: Conversation messages.
            tools: Tool definitions.
            model: Optional model override.

        Returns:
            AI response (OpenAI format).
        """
        resolved_model = self.provider_manager.resolve_model(model)
        use_streaming = self.stream_callback is not None

        # Normalize provider-required fields (e.g. reasoning_content for reasoning models)
        messages = self.provider_manager._normalize_reasoning_content(resolved_model, messages)

        request_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": 0.7,
            "stream": use_streaming,
        }
        if tools:
            request_kwargs["tools"] = tools

        response = await acompletion(**request_kwargs)

        if not use_streaming:
            parsed = self.provider_manager.parse_response(response, resolved_model)
            result: dict[str, Any] = {"role": "assistant", "content": parsed.content}
            if parsed.reasoning_content is not None:
                result["reasoning_content"] = parsed.reasoning_content
            return result

        return await self._handle_streaming_response(response, messages, resolved_model)

    async def _handle_streaming_response(
        self,
        response: Any,
        messages: list[dict[str, Any]],
        resolved_model: str,
    ) -> dict[str, Any]:
        """Consume a streaming response, emitting text chunks via callback."""
        chunks: list[Any] = []
        has_tool_calls = False

        async for chunk in response:
            chunks.append(chunk)
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content and not has_tool_calls and self.stream_callback:
                    self.stream_callback(delta.content)
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    has_tool_calls = True

        full_response = stream_chunk_builder(chunks, messages=messages)
        chunks.clear()  # Release chunk references immediately

        parsed = self.provider_manager.parse_response(full_response, resolved_model)
        content = parsed.content
        reasoning_content = parsed.reasoning_content
        del full_response, parsed  # Release large objects before returning

        result: dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning_content is not None:
            result["reasoning_content"] = reasoning_content
        return result
