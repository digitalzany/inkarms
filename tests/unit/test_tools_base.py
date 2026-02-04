"""Tests for tool base classes and models."""

import pytest

from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolCall, ToolParameter, ToolResult


class TestToolParameter:
    """Tests for ToolParameter model."""

    def test_required_parameter(self):
        """Test required parameter."""
        param = ToolParameter(
            name="test_param",
            type="string",
            description="A test parameter",
            required=True,
        )

        assert param.name == "test_param"
        assert param.type == "string"
        assert param.description == "A test parameter"
        assert param.required is True
        assert param.default is None
        assert param.enum is None

    def test_optional_parameter_with_default(self):
        """Test optional parameter with default value."""
        param = ToolParameter(
            name="timeout",
            type="integer",
            description="Timeout in seconds",
            required=False,
            default=30,
        )

        assert param.required is False
        assert param.default == 30

    def test_enum_parameter(self):
        """Test parameter with enum values."""
        param = ToolParameter(
            name="mode",
            type="string",
            description="Operation mode",
            required=True,
            enum=["read", "write", "append"],
        )

        assert param.enum == ["read", "write", "append"]


class TestToolCall:
    """Tests for ToolCall model."""

    def test_tool_call(self):
        """Test tool call creation."""
        call = ToolCall(
            id="call_123",
            name="execute_bash",
            input={"command": "ls -la"},
        )

        assert call.id == "call_123"
        assert call.name == "execute_bash"
        assert call.input == {"command": "ls -la"}

    def test_tool_call_str(self):
        """Test tool call string representation."""
        call = ToolCall(
            id="call_123",
            name="read_file",
            input={"path": "test.txt", "encoding": "utf-8"},
        )

        str_repr = str(call)
        assert "read_file" in str_repr
        assert "path=test.txt" in str_repr
        assert "encoding=utf-8" in str_repr


class TestToolResult:
    """Tests for ToolResult model."""

    def test_successful_result(self):
        """Test successful tool result."""
        result = ToolResult(
            tool_call_id="call_123",
            output="Command executed successfully",
            is_error=False,
        )

        assert result.tool_call_id == "call_123"
        assert result.output == "Command executed successfully"
        assert result.error is None
        assert result.is_error is False

    def test_error_result(self):
        """Test error tool result."""
        result = ToolResult(
            tool_call_id="call_123",
            output="",
            error="Command not found",
            exit_code=127,
            is_error=True,
        )

        assert result.error == "Command not found"
        assert result.exit_code == 127
        assert result.is_error is True

    def test_result_str_success(self):
        """Test result string representation for success."""
        result = ToolResult(
            tool_call_id="call_123",
            output="Short output",
            is_error=False,
        )

        assert str(result) == "Short output"

    def test_result_str_error(self):
        """Test result string representation for error."""
        result = ToolResult(
            tool_call_id="call_123",
            output="",
            error="Something failed",
            is_error=True,
        )

        assert "Error: Something failed" in str(result)

    def test_result_str_truncation(self):
        """Test result string truncation for long output."""
        long_output = "x" * 300
        result = ToolResult(
            tool_call_id="call_123",
            output=long_output,
            is_error=False,
        )

        str_repr = str(result)
        assert len(str_repr) <= 203  # 200 + "..."
        assert str_repr.endswith("...")


class DummyTool(Tool):
    """Dummy tool for testing abstract base class."""

    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A dummy tool for testing"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="param1",
                type="string",
                description="First parameter",
                required=True,
            ),
            ToolParameter(
                name="param2",
                type="integer",
                description="Second parameter",
                required=False,
                default=10,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            tool_call_id=kwargs.get("tool_call_id", "unknown"),
            output="Dummy execution",
            is_error=False,
        )


class TestTool:
    """Tests for Tool base class."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = DummyTool()

        assert tool.name == "dummy_tool"
        assert tool.description == "A dummy tool for testing"
        assert len(tool.parameters) == 2
        assert tool.is_dangerous is False

    def test_get_input_schema(self):
        """Test JSON schema generation."""
        tool = DummyTool()
        schema = tool.get_input_schema()

        assert schema["type"] == "object"
        assert "param1" in schema["properties"]
        assert "param2" in schema["properties"]
        assert schema["required"] == ["param1"]

        # Check param1 schema
        param1_schema = schema["properties"]["param1"]
        assert param1_schema["type"] == "string"
        assert param1_schema["description"] == "First parameter"

        # Check param2 schema
        param2_schema = schema["properties"]["param2"]
        assert param2_schema["type"] == "integer"
        assert param2_schema["default"] == 10

    def test_get_tool_definition(self):
        """Test tool definition for AI provider."""
        tool = DummyTool()
        definition = tool.get_tool_definition()

        assert definition["name"] == "dummy_tool"
        assert definition["description"] == "A dummy tool for testing"
        assert "input_schema" in definition
        assert definition["input_schema"]["type"] == "object"

    def test_validate_input_success(self):
        """Test successful input validation."""
        tool = DummyTool()

        # Should not raise
        tool.validate_input(param1="test")
        tool.validate_input(param1="test", param2=20)

    def test_validate_input_missing_required(self):
        """Test validation fails with missing required parameter."""
        tool = DummyTool()

        with pytest.raises(ValueError, match="Missing required parameters: param1"):
            tool.validate_input(param2=20)

    def test_validate_input_unknown_parameter(self):
        """Test validation fails with unknown parameter."""
        tool = DummyTool()

        with pytest.raises(ValueError, match="Unknown parameters: param3"):
            tool.validate_input(param1="test", param3="unknown")

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test tool execution."""
        tool = DummyTool()
        result = await tool.execute(param1="test", tool_call_id="call_123")

        assert result.tool_call_id == "call_123"
        assert result.output == "Dummy execution"
        assert result.is_error is False

    def test_tool_str(self):
        """Test tool string representation."""
        tool = DummyTool()
        assert str(tool) == "Tool(dummy_tool)"

    def test_tool_repr(self):
        """Test tool representation."""
        tool = DummyTool()
        repr_str = repr(tool)
        assert "dummy_tool" in repr_str
        assert "dangerous=False" in repr_str


class InvalidTool(Tool):
    """Tool with invalid definition for testing validation."""

    @property
    def name(self) -> str:
        return ""  # Empty name

    @property
    def description(self) -> str:
        return "Invalid tool"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool_call_id="", output="", is_error=False)


class TestToolValidation:
    """Tests for tool definition validation."""

    def test_empty_name_validation(self):
        """Test validation fails with empty name."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            InvalidTool()


class DuplicateParamTool(Tool):
    """Tool with duplicate parameter names."""

    @property
    def name(self) -> str:
        return "duplicate_tool"

    @property
    def description(self) -> str:
        return "Tool with duplicate params"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="param1", type="string", description="First", required=True
            ),
            ToolParameter(
                name="param1", type="string", description="Duplicate", required=True
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool_call_id="", output="", is_error=False)


class TestToolValidationDuplicates:
    """Test tool validation for duplicate parameters."""

    def test_duplicate_parameter_names(self):
        """Test validation fails with duplicate parameter names."""
        with pytest.raises(ValueError, match="Parameter names must be unique"):
            DuplicateParamTool()


class TestToolExecutionError:
    """Tests for ToolExecutionError."""

    def test_error_with_message(self):
        """Test error with just message."""
        error = ToolExecutionError("Execution failed")
        assert str(error) == "Execution failed"
        assert error.exit_code is None

    def test_error_with_exit_code(self):
        """Test error with message and exit code."""
        error = ToolExecutionError("Command failed", exit_code=1)
        assert str(error) == "Command failed"
        assert error.exit_code == 1
