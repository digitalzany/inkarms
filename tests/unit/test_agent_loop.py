"""Unit tests for AgentLoop output truncation and tool result handling."""

import pytest

from inkarms.agent.loop import AgentLoop, MAX_TOOL_OUTPUT_CHARS
from inkarms.models.tools import ToolResult


class TestTruncateOutput:
    """Tests for AgentLoop._truncate_output."""

    def test_short_string_unchanged(self):
        """Short output should pass through unchanged."""
        output = "Hello, world!"
        assert AgentLoop._truncate_output(output) == output

    def test_exact_limit_unchanged(self):
        """Output exactly at the limit should pass through unchanged."""
        output = "x" * MAX_TOOL_OUTPUT_CHARS
        assert AgentLoop._truncate_output(output) == output

    def test_over_limit_truncated(self):
        """Output over the limit should be truncated with head + indicator + tail."""
        size = MAX_TOOL_OUTPUT_CHARS + 10_000
        output = "A" * size
        result = AgentLoop._truncate_output(output)

        assert len(result) < size
        assert "truncated" in result
        assert "10000 characters" in result
        # Head should be preserved
        half = MAX_TOOL_OUTPUT_CHARS // 2
        assert result.startswith("A" * half)
        # Tail should be preserved
        assert result.endswith("A" * half)

    def test_custom_max_chars(self):
        """Custom max_chars should be respected."""
        output = "abcdefghij"  # 10 chars
        result = AgentLoop._truncate_output(output, max_chars=6)

        assert "truncated" in result
        assert "4 characters" in result
        assert result.startswith("abc")
        assert result.endswith("hij")

    def test_empty_string(self):
        """Empty string should pass through."""
        assert AgentLoop._truncate_output("") == ""


class TestAddToolResultsToConversation:
    """Tests for AgentLoop._add_tool_results_to_conversation."""

    def test_normal_output_not_truncated(self):
        """Normal-sized output should not be truncated."""
        conversation: list[dict] = []
        results = [
            ToolResult(
                tool_call_id="tc_1",
                output="short output",
                is_error=False,
            )
        ]

        AgentLoop._add_tool_results_to_conversation(conversation, results)

        assert len(conversation) == 1
        assert conversation[0]["content"] == "short output"
        assert conversation[0]["role"] == "tool"
        assert conversation[0]["tool_call_id"] == "tc_1"

    def test_large_output_truncated(self):
        """Large output should be truncated."""
        conversation: list[dict] = []
        large_output = "X" * (MAX_TOOL_OUTPUT_CHARS + 5000)
        results = [
            ToolResult(
                tool_call_id="tc_2",
                output=large_output,
                is_error=False,
            )
        ]

        AgentLoop._add_tool_results_to_conversation(conversation, results)

        assert len(conversation) == 1
        content = conversation[0]["content"]
        assert len(content) < len(large_output)
        assert "truncated" in content

    def test_error_results_not_truncated(self):
        """Error results should use error message, not truncated output."""
        conversation: list[dict] = []
        results = [
            ToolResult(
                tool_call_id="tc_3",
                output="",
                error="Command failed with exit code 1",
                is_error=True,
            )
        ]

        AgentLoop._add_tool_results_to_conversation(conversation, results)

        assert len(conversation) == 1
        assert conversation[0]["content"] == "Command failed with exit code 1"

    def test_error_with_no_message_uses_fallback(self):
        """Error result with no error message should use 'Error' fallback."""
        conversation: list[dict] = []
        results = [
            ToolResult(
                tool_call_id="tc_4",
                output="",
                error=None,
                is_error=True,
            )
        ]

        AgentLoop._add_tool_results_to_conversation(conversation, results)

        assert conversation[0]["content"] == "Error"

    def test_multiple_results(self):
        """Multiple tool results should all be added."""
        conversation: list[dict] = []
        results = [
            ToolResult(tool_call_id="tc_a", output="result A", is_error=False),
            ToolResult(tool_call_id="tc_b", output="result B", is_error=False),
        ]

        AgentLoop._add_tool_results_to_conversation(conversation, results)

        assert len(conversation) == 2
        assert conversation[0]["tool_call_id"] == "tc_a"
        assert conversation[1]["tool_call_id"] == "tc_b"
