"""
Sandbox executor for safe command execution.

This module provides sandboxed command execution with path restrictions,
command filtering, and audit logging integration.
"""

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from inkarms.security.whitelist import CommandCheck, CommandFilter

if TYPE_CHECKING:
    from inkarms.audit.logger import AuditLogger
    from inkarms.config.schema import SecurityConfig


@dataclass
class ExecutionResult:
    """Result of a sandboxed command execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    blocked: bool = False
    blocked_reason: str | None = None


class PathRestrictions:
    """
    Enforces path access restrictions.

    Prevents access to sensitive paths like ~/.ssh, /etc, etc.
    """

    def __init__(
        self, read_only: list[str] | None = None, no_access: list[str] | None = None
    ) -> None:
        """
        Initialize path restrictions.

        Args:
            read_only: Paths that are read-only (not implemented yet)
            no_access: Paths that are completely blocked
        """
        self.read_only = [Path(p).expanduser() for p in (read_only or [])]
        self.no_access = [Path(p).expanduser() for p in (no_access or [])]

        # Default sensitive paths
        if not self.no_access:
            home = Path.home()
            self.no_access = [
                home / ".ssh",
                home / ".aws",
                home / ".config" / "gcloud",
                Path("/etc"),
                Path("/root"),
                Path("/var"),
            ]

    def check_path(self, path: str | Path) -> tuple[bool, str | None]:
        """
        Check if a path is accessible.

        Args:
            path: Path to check

        Returns:
            Tuple of (allowed, reason)
        """
        path = Path(path).expanduser().resolve()

        # Check no-access list
        for restricted in self.no_access:
            try:
                # Check if path is under restricted path
                path.relative_to(restricted)
                return (
                    False,
                    f"Access denied: {path} is under restricted path {restricted}",
                )
            except ValueError:
                # Not a subpath, continue checking
                continue

        return True, None

    def extract_paths_from_command(self, command: str) -> list[Path]:
        """
        Extract file paths from a command string.

        This is a heuristic approach that looks for path-like strings.

        Args:
            command: Shell command

        Returns:
            List of potential paths found in command
        """
        paths: list[Path] = []
        try:
            tokens = shlex.split(command)
        except ValueError:
            # If parsing fails, return empty list
            return paths

        for token in tokens:
            # Skip flags and common non-path tokens
            if token.startswith("-") or token in {"|", ">", "<", ">>", "&&", "||", ";"}:
                continue

            # Check if token looks like a path
            if "/" in token or token.startswith("~"):
                paths.append(Path(token))

        return paths


class SandboxExecutor:
    """
    Executes commands in a sandboxed environment.

    Provides:
    - Command filtering (whitelist/blacklist)
    - Path access restrictions
    - Audit logging integration
    - Safe subprocess execution
    """

    def __init__(
        self,
        command_filter: CommandFilter,
        path_restrictions: PathRestrictions | None = None,
        audit_logger: "AuditLogger | None" = None,
    ) -> None:
        """
        Initialize sandbox executor.

        Args:
            command_filter: Command filtering instance
            path_restrictions: Path restriction instance
            audit_logger: Audit logger for recording executions
        """
        self.command_filter = command_filter
        self.path_restrictions = path_restrictions or PathRestrictions()
        self.audit_logger = audit_logger

    @classmethod
    def from_config(
        cls, config: "SecurityConfig", audit_logger: "AuditLogger | None" = None
    ) -> "SandboxExecutor":
        """
        Create sandbox executor from configuration.

        Args:
            config: Security configuration
            audit_logger: Optional audit logger

        Returns:
            Configured SandboxExecutor instance
        """
        command_filter = CommandFilter(
            whitelist=config.whitelist,
            blacklist=config.blacklist,
            mode=config.sandbox.mode,
        )

        path_restrictions = PathRestrictions(
            read_only=config.restricted_paths.read_only,
            no_access=config.restricted_paths.no_access,
        )

        return cls(command_filter, path_restrictions, audit_logger)

    def check_command(self, command: str) -> CommandCheck:
        """
        Check if a command is allowed without executing it.

        Args:
            command: Command to check

        Returns:
            CommandCheck result
        """
        # Check command filtering
        cmd_check = self.command_filter.check_command(command)
        if not cmd_check.allowed:
            return cmd_check

        # Check path restrictions
        paths = self.path_restrictions.extract_paths_from_command(command)
        for path in paths:
            allowed, reason = self.path_restrictions.check_path(path)
            if not allowed:
                return CommandCheck(
                    allowed=False, reason=reason, mode=cmd_check.mode
                )

        return cmd_check

    def execute(
        self,
        command: str,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = 30,
    ) -> ExecutionResult:
        """
        Execute a command in the sandbox.

        Args:
            command: Shell command to execute
            cwd: Working directory (default: current directory)
            env: Environment variables (default: inherit from parent)
            timeout: Timeout in seconds (default: 30)

        Returns:
            ExecutionResult with output and status
        """
        # Check if command is allowed
        check = self.check_command(command)

        if not check.allowed:
            # Log blocked command
            if self.audit_logger:
                self.audit_logger.log_command_blocked(
                    command=command, reason=check.reason or "Unknown"
                )

            return ExecutionResult(
                success=False,
                blocked=True,
                blocked_reason=check.reason,
            )

        # Log command execution start
        if self.audit_logger:
            self.audit_logger.log_command_start(command=command)

        # Execute command
        try:
            # Prepare environment
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)

            # Execute
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd,
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            # Log execution result
            if self.audit_logger:
                self.audit_logger.log_command_complete(
                    command=command,
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            error = f"Command timed out after {timeout} seconds"
            if self.audit_logger:
                self.audit_logger.log_command_error(command=command, error=error)

            return ExecutionResult(
                success=False,
                stderr=error,
            )

        except Exception as e:
            error = f"Command execution failed: {e}"
            if self.audit_logger:
                self.audit_logger.log_command_error(command=command, error=str(e))

            return ExecutionResult(
                success=False,
                stderr=error,
            )

    def is_enabled(self) -> bool:
        """Check if sandbox is enabled."""
        return bool(self.command_filter.mode != "disabled")
