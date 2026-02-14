"""Unit tests for ProviderManager.parse_response tool_call argument parsing."""

from unittest.mock import Mock

import pytest

from inkarms.providers.cost import CostTracker
from inkarms.providers.manager import ProviderManager


def _make_provider_manager():
    """Create a ProviderManager with minimal config for testing."""
    config = Mock()
    config.default = "test-model"
    config.aliases = {}
    config.fallback = []

    secrets = Mock()
    secrets.load_all_to_env = Mock(return_value={})

    return ProviderManager(config=config, secrets=secrets, cost_tracker=CostTracker())


def _make_response(tool_calls=None, content_text=None):
    """Build a mock LiteLLM response object."""
    message = Mock()
    message.content = content_text

    if tool_calls:
        message.tool_calls = tool_calls
        # Make isinstance(message.content, list) False so we hit the tool_calls branch
        message.content = content_text
    else:
        message.tool_calls = None

    choice = Mock()
    choice.message = message
    choice.finish_reason = "stop"

    usage = Mock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15

    response = Mock()
    response.choices = [choice]
    response.usage = usage
    response.model_dump = Mock(return_value={})

    return response


def _make_tool_call(tc_id, name, arguments):
    """Build a mock tool_call object."""
    function = Mock()
    function.name = name
    function.arguments = arguments

    tc = Mock()
    tc.id = tc_id
    tc.function = function
    return tc


class TestParseResponseToolCallArguments:
    """Tests for tool_call argument parsing in parse_response."""

    def test_json_string_arguments_parsed_to_dict(self):
        """Arguments as JSON string should be parsed to dict."""
        manager = _make_provider_manager()
        tool_call = _make_tool_call(
            "tc_1", "execute_bash", '{"command": "ls -la"}'
        )
        response = _make_response(tool_calls=[tool_call])

        result = manager.parse_response(response, "test-model")

        # Content should be a list with a tool_use block
        tool_use_blocks = [b for b in result.content if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["input"] == {"command": "ls -la"}
        assert isinstance(tool_use_blocks[0]["input"], dict)

    def test_dict_arguments_passed_through(self):
        """Arguments already a dict should pass through unchanged."""
        manager = _make_provider_manager()
        tool_call = _make_tool_call(
            "tc_2", "read_file", {"path": "/tmp/test.txt"}
        )
        response = _make_response(tool_calls=[tool_call])

        result = manager.parse_response(response, "test-model")

        tool_use_blocks = [b for b in result.content if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["input"] == {"path": "/tmp/test.txt"}

    def test_invalid_json_string_kept_as_is(self):
        """Invalid JSON string should be kept as-is (parser fallback handles it)."""
        manager = _make_provider_manager()
        tool_call = _make_tool_call(
            "tc_3", "some_tool", "not valid json {"
        )
        response = _make_response(tool_calls=[tool_call])

        result = manager.parse_response(response, "test-model")

        tool_use_blocks = [b for b in result.content if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        # Should fall through to the raw string since json.loads failed
        assert tool_use_blocks[0]["input"] == "not valid json {"

    def test_multiple_tool_calls_all_parsed(self):
        """Multiple tool calls should all have their arguments parsed."""
        manager = _make_provider_manager()
        tc1 = _make_tool_call("tc_a", "bash", '{"command": "pwd"}')
        tc2 = _make_tool_call("tc_b", "read", {"file": "test.py"})
        response = _make_response(tool_calls=[tc1, tc2])

        result = manager.parse_response(response, "test-model")

        tool_use_blocks = [b for b in result.content if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 2
        assert tool_use_blocks[0]["input"] == {"command": "pwd"}
        assert tool_use_blocks[1]["input"] == {"file": "test.py"}

    def test_text_content_preserved_with_tool_calls(self):
        """Text content should be preserved alongside tool calls."""
        manager = _make_provider_manager()
        tool_call = _make_tool_call("tc_4", "bash", '{"command": "echo hi"}')
        response = _make_response(tool_calls=[tool_call], content_text="Let me run that.")

        result = manager.parse_response(response, "test-model")

        text_blocks = [b for b in result.content if b.get("type") == "text"]
        assert len(text_blocks) == 1
        assert text_blocks[0]["text"] == "Let me run that."

    def test_empty_json_string_parsed(self):
        """Empty JSON object string should parse to empty dict."""
        manager = _make_provider_manager()
        tool_call = _make_tool_call("tc_5", "no_args_tool", "{}")
        response = _make_response(tool_calls=[tool_call])

        result = manager.parse_response(response, "test-model")

        tool_use_blocks = [b for b in result.content if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["input"] == {}
