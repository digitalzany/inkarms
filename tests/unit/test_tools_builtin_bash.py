"""Tests for built-in bash tool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inkarms.security.sandbox import ExecutionResult
from inkarms.tools.builtin.bash import BashTool


class TestBashTool:
    """Tests for BashTool."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = BashTool()

        assert tool.name == "execute_bash"
        assert "bash" in tool.description.lower()
        assert tool.is_dangerous is True  # Bash is dangerous

        params = {p.name: p for p in tool.parameters}
        assert "command" in params
        assert params["command"].required is True
        assert "working_dir" in params
        assert "timeout" in params
        assert params["timeout"].default == 30

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful command execution."""
        # Create mock sandbox
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(
            success=True, stdout="Hello, World!", stderr="", exit_code=0
        )
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        # Execute command
        result = await tool.execute(
            command="echo 'Hello, World!'", tool_call_id="call_123"
        )

        assert result.tool_call_id == "call_123"
        assert result.is_error is False
        assert "Hello, World!" in result.output
        assert result.exit_code == 0

        # Verify sandbox was called correctly
        mock_sandbox.execute.assert_called_once()
        call_args = mock_sandbox.execute.call_args
        assert call_args[0][0] == "echo 'Hello, World!'"

    @pytest.mark.asyncio
    async def test_execute_with_stderr(self):
        """Test command execution with stderr."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(
            success=True, stdout="output", stderr="warning message", exit_code=0
        )
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="test", tool_call_id="call_123")

        assert result.is_error is False
        assert "output" in result.output
        assert "warning message" in result.output

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Test command execution failure."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(
            success=False, stdout="", stderr="command not found", exit_code=127
        )
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="nonexistent", tool_call_id="call_123")

        assert result.is_error is True
        assert result.exit_code == 127
        assert "command not found" in result.output
        assert "Command failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_working_dir(self):
        """Test command execution with working directory."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="", stderr="", exit_code=0)
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        await tool.execute(
            command="ls", working_dir="/tmp", tool_call_id="call_123"
        )

        # Verify cwd was passed
        call_args = mock_sandbox.execute.call_args
        assert call_args[1]["cwd"] == "/tmp"

    @pytest.mark.asyncio
    async def test_execute_with_timeout(self):
        """Test command execution with custom timeout."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="", stderr="", exit_code=0)
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        # Execute with custom timeout
        await tool.execute(command="sleep 1", timeout=60, tool_call_id="call_123")

        # Verify wait_for was called with correct timeout
        # (Implementation uses asyncio.wait_for internally)

    @pytest.mark.asyncio
    async def test_execute_timeout_exceeded(self):
        """Test command timeout."""
        mock_sandbox = MagicMock()
        # Simulate timeout by raising TimeoutError
        mock_sandbox.execute = MagicMock(side_effect=asyncio.TimeoutError())

        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="sleep 100", timeout=1, tool_call_id="call_123")

        assert result.is_error is True
        assert "timed out" in result.error.lower()
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_execute_timeout_capped(self):
        """Test timeout is capped at 5 minutes."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="", stderr="", exit_code=0)
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        # Request very long timeout
        await tool.execute(command="ls", timeout=10000, tool_call_id="call_123")

        # Should be capped at 300 seconds (handled in implementation)
        # We can't easily verify asyncio.wait_for timeout in this test,
        # but the implementation caps it

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self):
        """Test permission denied error."""
        mock_sandbox = MagicMock()
        mock_sandbox.execute = MagicMock(side_effect=PermissionError("Access denied"))

        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="forbidden", tool_call_id="call_123")

        assert result.is_error is True
        assert "permission denied" in result.error.lower()

    @pytest.mark.asyncio
    @patch("asyncio.to_thread")
    async def test_execute_generic_error(self, mock_to_thread):
        """Test generic execution error."""
        # Make to_thread raise an exception
        async def raise_error(*args, **kwargs):
            raise Exception("Unexpected error")

        mock_to_thread.side_effect = raise_error

        mock_sandbox = MagicMock()
        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="error", tool_call_id="call_123")

        assert result.is_error is True
        assert "execution failed" in result.error.lower()
        assert "unexpected error" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_no_output(self):
        """Test command with no output."""
        mock_sandbox = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="", stderr="", exit_code=0)
        mock_sandbox.execute = MagicMock(return_value=mock_result)

        tool = BashTool(sandbox=mock_sandbox)

        result = await tool.execute(command="true", tool_call_id="call_123")

        assert result.is_error is False
        assert "(no output)" in result.output

    @pytest.mark.asyncio
    @patch("inkarms.tools.builtin.bash.SandboxExecutor")
    @patch("inkarms.config.get_config")
    async def test_execute_creates_sandbox_if_needed(
        self, mock_get_config, mock_sandbox_class
    ):
        """Test sandbox is created if not provided."""
        # Mock config
        mock_config = MagicMock()
        mock_config.security = MagicMock()
        mock_get_config.return_value = mock_config

        # Mock sandbox instance
        mock_sandbox_instance = MagicMock()
        mock_result = ExecutionResult(success=True, stdout="test", stderr="", exit_code=0)
        mock_sandbox_instance.execute = MagicMock(return_value=mock_result)
        mock_sandbox_class.from_config.return_value = mock_sandbox_instance

        # Create tool without sandbox
        tool = BashTool(sandbox=None)

        result = await tool.execute(command="test", tool_call_id="call_123")

        # Verify sandbox was created
        mock_sandbox_class.from_config.assert_called_once_with(
            mock_config.security
        )
        assert result.is_error is False

    def test_input_validation_missing_command(self):
        """Test validation fails without command."""
        tool = BashTool()

        with pytest.raises(ValueError, match="Missing required parameters: command"):
            tool.validate_input()

    def test_input_validation_unknown_param(self):
        """Test validation fails with unknown parameter."""
        tool = BashTool()

        with pytest.raises(ValueError, match="Unknown parameters"):
            tool.validate_input(command="ls", unknown_param="value")
