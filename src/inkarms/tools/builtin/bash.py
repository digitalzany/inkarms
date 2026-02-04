"""Bash command execution tool."""

import asyncio
import logging
from typing import Optional

from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class BashTool(Tool):
    """Execute bash commands through security sandbox.

    This tool allows the AI agent to run shell commands safely through
    the existing security sandbox system. All commands are subject to:
    - Command filtering (whitelist/blacklist)
    - Path restrictions
    - Timeout limits
    - Audit logging
    """

    def __init__(self, sandbox: Optional[SandboxExecutor] = None):
        """Initialize bash tool.

        Args:
            sandbox: SandboxExecutor instance. If None, one will be created
                    from default config when needed.
        """
        self._sandbox = sandbox
        super().__init__()

    @property
    def name(self) -> str:
        """Tool name."""
        return "execute_bash"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Execute a bash command in a secure sandbox environment. "
            "Returns stdout, stderr, and exit code. "
            "Commands are subject to security filtering and path restrictions. "
            "Use this for: running CLI tools, file operations, system queries, "
            "package installation, git operations, etc. "
            "Avoid long-running commands (timeout: 30s default)."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="command",
                type="string",
                description=(
                    "The bash command to execute. "
                    "Can be a single command or a pipeline. "
                    "Use '&&' to chain commands. "
                    "Example: 'ls -la' or 'cat file.txt | grep pattern'"
                ),
                required=True,
            ),
            ToolParameter(
                name="working_dir",
                type="string",
                description=(
                    "Working directory for command execution. "
                    "Defaults to current directory if not specified."
                ),
                required=False,
            ),
            ToolParameter(
                name="timeout",
                type="integer",
                description=(
                    "Timeout in seconds. Kills command if it runs longer. "
                    "Default: 30 seconds. Max: 300 seconds (5 minutes)."
                ),
                required=False,
                default=30,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Bash commands can modify system state."""
        return True

    async def execute(self, **kwargs) -> ToolResult:
        """Execute bash command.

        Args:
            command: Bash command to execute
            working_dir: Optional working directory
            timeout: Optional timeout in seconds

        Returns:
            ToolResult with command output

        Raises:
            ToolExecutionError: If execution fails critically
        """
        # Validate input
        self.validate_input(**kwargs)

        command = kwargs["command"]
        working_dir = kwargs.get("working_dir")
        timeout = kwargs.get("timeout", 30)

        # Cap timeout at 5 minutes
        timeout = min(timeout, 300)

        # Get tool call ID from context (will be set by agent loop)
        tool_call_id = kwargs.get("tool_call_id", "unknown")

        logger.info(f"Executing bash command: {command[:100]}...")

        try:
            # Get or create sandbox
            sandbox = self._sandbox
            if sandbox is None:
                from inkarms.config import get_config

                config = get_config()
                sandbox = SandboxExecutor.from_config(config.security)

            # Execute through sandbox (run in thread pool since it's sync)
            result = await asyncio.wait_for(
                asyncio.to_thread(sandbox.execute, command, cwd=working_dir, timeout=timeout),
                timeout=timeout + 1,  # Give extra second for cleanup
            )

            # Check if command was blocked
            if result.blocked:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Command blocked: {result.blocked_reason}",
                    exit_code=-1,
                    is_error=True,
                )

            # Build output message
            output_parts = []

            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")

            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")

            if result.exit_code is not None and result.exit_code != 0:
                output_parts.append(f"Exit Code: {result.exit_code}")

            output = "\n\n".join(output_parts) if output_parts else "(no output)"

            # Determine if this is an error based on exit code or success flag
            is_error = not result.success or (
                result.exit_code is not None and result.exit_code != 0
            )

            return ToolResult(
                tool_call_id=tool_call_id,
                output=output,
                exit_code=result.exit_code,
                is_error=is_error,
                error=f"Command failed with exit code {result.exit_code}"
                if is_error
                else None,
            )

        except asyncio.TimeoutError:
            error_msg = f"Command timed out after {timeout} seconds"
            logger.warning(f"Bash command timeout: {command[:100]}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                exit_code=-1,
                is_error=True,
            )

        except PermissionError as e:
            error_msg = f"Permission denied: {str(e)}"
            logger.warning(f"Bash command permission denied: {command[:100]}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                exit_code=-1,
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Execution failed: {str(e)}"
            logger.error(f"Bash command execution error: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                exit_code=-1,
                is_error=True,
            )
