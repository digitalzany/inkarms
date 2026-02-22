"""
OpenAI-compatible chat completions proxy.

POST /v1/chat/completions

Enabled only when hub.openai_proxy = true.

Proxies requests through ProviderManager, supporting both streaming (SSE)
and non-streaming responses in the OpenAI wire format. Clients such as
Continue.dev, Open WebUI, and shell scripts that expect the OpenAI API
can point at this endpoint.

Streaming notes:
- X-Accel-Buffering: no — disables nginx proxy buffering (required for SSE)
- Transfer-Encoding: chunked — ensures chunks are flushed immediately
- "[DONE]" sentinel is sent as-is; never JSON-parsed (it is not valid JSON)
- asyncio.CancelledError from client disconnect is handled cleanly

Non-streaming: returns a standard OpenAI-style JSON response.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from inkarms.config.loader import get_config
from inkarms.providers import get_provider_manager

router = APIRouter()
logger = logging.getLogger(__name__)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Transfer-Encoding": "chunked",
}


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    """OpenAI-compatible completions endpoint (hub.openai_proxy must be true)."""
    config = get_config()
    if not config.hub.openai_proxy:
        raise HTTPException(
            status_code=404,
            detail="OpenAI proxy is disabled — set hub.openai_proxy = true to enable",
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    model: str | None = body.get("model") or config.providers.default
    is_stream: bool = body.get("stream", False)
    temperature: float = float(body.get("temperature", 0.7))
    max_tokens: int | None = body.get("max_tokens")

    try:
        manager = get_provider_manager()
    except Exception as exc:
        logger.error("Failed to initialize provider manager: %s", exc)
        raise HTTPException(status_code=503, detail="Provider unavailable") from exc

    if is_stream:
        return StreamingResponse(
            _stream_sse(manager, messages, model, temperature, max_tokens),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    return await _non_stream_response(manager, messages, model, temperature, max_tokens)


# ---------------------------------------------------------------------------
# Streaming SSE generator
# ---------------------------------------------------------------------------


async def _stream_sse(
    manager: Any,
    messages: list[dict],
    model: str | None,
    temperature: float,
    max_tokens: int | None,
) -> Any:
    """Yield SSE data lines for a streaming chat completion."""
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model_name = model or "unknown"

    try:
        stream_response = await manager.complete(
            messages,
            model=model,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        async for chunk in stream_response:  # type: ignore[union-attr]
            delta_content = chunk.content if chunk.content else ""
            data = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": delta_content},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(data)}\n\n".encode()

        # Final chunk with finish_reason
        final_data = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(final_data)}\n\n".encode()

        # Required SSE sentinel — do NOT json.loads() this
        yield b"data: [DONE]\n\n"

    except asyncio.CancelledError:
        # Client disconnected cleanly
        logger.debug("SSE stream cancelled by client")
        return
    except Exception as exc:  # noqa: BLE001
        logger.error("SSE stream error: %s", exc)
        error_data = json.dumps({"error": {"message": str(exc), "type": "server_error"}})
        yield f"data: {error_data}\n\n".encode()
        yield b"data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# Non-streaming response
# ---------------------------------------------------------------------------


async def _non_stream_response(
    manager: Any,
    messages: list[dict],
    model: str | None,
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Return an OpenAI-style non-streaming completion response."""
    from inkarms.providers import CompletionResponse

    try:
        response = await manager.complete(
            messages,
            model=model,
            stream=False,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.error("Completion error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    assert isinstance(response, CompletionResponse)

    content = response.content
    if isinstance(content, list):
        # Join content blocks into a single string
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": response.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": response.finish_reason or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        },
    }
