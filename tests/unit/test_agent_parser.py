"""Tests for tool call parser."""

import pytest

from inkarms.agent.parser import ToolCallParser


class TestToolCallParser:
    """Tests for ToolCallParser."""

    def test_parse_response_with_tool_calls(self):
        """Test parsing response with tool calls."""
        response = {
            "content": [
                {"type": "text", "text": "I'll help you with that."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "execute_bash",
                    "input": {"command": "ls -la"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_456",
                    "name": "read_file",
                    "input": {"path": "test.txt"},
                },
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 2

        # First tool call
        assert tool_calls[0].id == "toolu_123"
        assert tool_calls[0].name == "execute_bash"
        assert tool_calls[0].input == {"command": "ls -la"}

        # Second tool call
        assert tool_calls[1].id == "toolu_456"
        assert tool_calls[1].name == "read_file"
        assert tool_calls[1].input == {"path": "test.txt"}

    def test_parse_response_no_tool_calls(self):
        """Test parsing response without tool calls."""
        response = {
            "content": [{"type": "text", "text": "Here's your answer."}],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 0

    def test_parse_response_string_content(self):
        """Test parsing response with string content."""
        response = {
            "content": "Plain text response",
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 0

    def test_parse_response_empty_content(self):
        """Test parsing response with empty content."""
        response = {
            "content": None,
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 0

    def test_parse_response_invalid_tool_block(self):
        """Test parsing response with invalid tool block."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    # Missing 'id' field
                    "name": "execute_bash",
                    "input": {"command": "ls"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_789",
                    # Missing 'name' field
                    "input": {"path": "test.txt"},
                },
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        # Both should be skipped
        assert len(tool_calls) == 0

    def test_parse_response_mixed_content(self):
        """Test parsing response with mixed text and tool blocks."""
        response = {
            "content": [
                {"type": "text", "text": "Let me check that."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "read_file",
                    "input": {"path": "config.yaml"},
                },
                {"type": "text", "text": "Reading the file now."},
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 1
        assert tool_calls[0].name == "read_file"

    def test_extract_text_content(self):
        """Test extracting text content from response."""
        response = {
            "content": [
                {"type": "text", "text": "First part."},
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "execute_bash",
                    "input": {},
                },
                {"type": "text", "text": "Second part."},
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        text = parser.extract_text_content(response)

        assert text == "First part.\nSecond part."

    def test_extract_text_content_string(self):
        """Test extracting text from string content."""
        response = {
            "content": "Plain text response",
            "role": "assistant",
        }

        parser = ToolCallParser()
        text = parser.extract_text_content(response)

        assert text == "Plain text response"

    def test_extract_text_content_empty(self):
        """Test extracting text from empty response."""
        response = {
            "content": None,
            "role": "assistant",
        }

        parser = ToolCallParser()
        text = parser.extract_text_content(response)

        assert text == ""

    def test_extract_text_content_no_text_blocks(self):
        """Test extracting text when only tool blocks present."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "execute_bash",
                    "input": {},
                },
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        text = parser.extract_text_content(response)

        assert text == ""

    def test_has_tool_calls_true(self):
        """Test checking if response has tool calls (true)."""
        response = {
            "content": [
                {"type": "text", "text": "Text"},
                {"type": "tool_use", "id": "toolu_123", "name": "test", "input": {}},
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        has_tools = parser.has_tool_calls(response)

        assert has_tools is True

    def test_has_tool_calls_false(self):
        """Test checking if response has tool calls (false)."""
        response = {
            "content": [{"type": "text", "text": "Text only"}],
            "role": "assistant",
        }

        parser = ToolCallParser()
        has_tools = parser.has_tool_calls(response)

        assert has_tools is False

    def test_has_tool_calls_string_content(self):
        """Test checking tool calls with string content."""
        response = {
            "content": "Plain text",
            "role": "assistant",
        }

        parser = ToolCallParser()
        has_tools = parser.has_tool_calls(response)

        assert has_tools is False

    def test_parse_response_with_empty_input(self):
        """Test parsing tool call with empty input."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "list_files",
                    # No input field
                },
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 1
        assert tool_calls[0].input == {}

    def test_parse_response_with_complex_input(self):
        """Test parsing tool call with complex nested input."""
        response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "search_files",
                    "input": {
                        "path": "/home/user",
                        "pattern": "*.py",
                        "options": {
                            "recursive": True,
                            "exclude": ["__pycache__", ".git"],
                        },
                    },
                },
            ],
            "role": "assistant",
        }

        parser = ToolCallParser()
        tool_calls = parser.parse_response(response)

        assert len(tool_calls) == 1
        assert tool_calls[0].input["path"] == "/home/user"
        assert tool_calls[0].input["options"]["recursive"] is True
