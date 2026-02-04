"""Parser for extracting tool calls from AI responses."""

import logging
from typing import Any

from inkarms.tools.models import ToolCall

logger = logging.getLogger(__name__)


class ToolCallParser:
    """Parses tool calls from AI provider responses.

    Supports Anthropic's tool use format with content blocks.
    """

    @staticmethod
    def parse_response(response: dict[str, Any]) -> list[ToolCall]:
        """Parse tool calls from AI response.

        Args:
            response: Response from AI provider (LiteLLM format)

        Returns:
            List of ToolCall objects

        The response format from Anthropic (via LiteLLM):
        {
            "content": [
                {"type": "text", "text": "I'll help you..."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "execute_bash",
                    "input": {"command": "ls -la"}
                }
            ],
            "role": "assistant",
            ...
        }
        """
        tool_calls = []

        # Get content blocks from response
        content = response.get("content")
        if not content:
            return tool_calls

        # Handle both string and list content
        if isinstance(content, str):
            # No tool calls in plain text response
            return tool_calls

        if not isinstance(content, list):
            logger.warning(f"Unexpected content type: {type(content)}")
            return tool_calls

        # Extract tool use blocks
        for block in content:
            if not isinstance(block, dict):
                continue

            block_type = block.get("type")
            if block_type != "tool_use":
                continue

            # Extract tool call details
            tool_id = block.get("id")
            tool_name = block.get("name")
            tool_input = block.get("input", {})

            if not tool_id or not tool_name:
                logger.warning(f"Invalid tool use block: {block}")
                continue

            # Handle case where input is a JSON string instead of dict
            if isinstance(tool_input, str):
                try:
                    import json
                    tool_input = json.loads(tool_input)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool input as JSON: {tool_input}")
                    tool_input = {"raw_input": tool_input}

            try:
                tool_call = ToolCall(
                    id=tool_id,
                    name=tool_name,
                    input=tool_input,
                )
                tool_calls.append(tool_call)
            except Exception as e:
                logger.error(f"Failed to parse tool call: {e}", exc_info=True)
                continue

        return tool_calls

    @staticmethod
    def extract_text_content(response: dict[str, Any]) -> str:
        """Extract text content from AI response.

        Args:
            response: Response from AI provider

        Returns:
            Concatenated text content (empty string if none)
        """
        content = response.get("content")
        if not content:
            return ""

        # Handle string content
        if isinstance(content, str):
            return content

        # Handle list content
        if not isinstance(content, list):
            return ""

        # Extract text blocks
        text_parts = []
        for block in content:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    text_parts.append(text)

        return "\n".join(text_parts)

    @staticmethod
    def has_tool_calls(response: dict[str, Any]) -> bool:
        """Check if response contains tool calls.

        Args:
            response: Response from AI provider

        Returns:
            True if response contains at least one tool call
        """
        content = response.get("content")
        if not content or not isinstance(content, list):
            return False

        return any(
            isinstance(block, dict) and block.get("type") == "tool_use"
            for block in content
        )
