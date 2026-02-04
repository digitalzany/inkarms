"""Tests for sandbox executor."""

import tempfile
from pathlib import Path

from inkarms.security.sandbox import PathRestrictions, SandboxExecutor
from inkarms.security.whitelist import CommandFilter


class TestPathRestrictions:
    """Test PathRestrictions functionality."""

    def test_default_restricted_paths(self) -> None:
        """Test that default sensitive paths are restricted."""
        restrictions = PathRestrictions()

        # .ssh should be restricted
        allowed, reason = restrictions.check_path("~/.ssh/id_rsa")
        assert allowed is False
        assert ".ssh" in reason

        # .aws should be restricted
        allowed, reason = restrictions.check_path("~/.aws/credentials")
        assert allowed is False
        assert ".aws" in reason

    def test_custom_no_access_paths(self) -> None:
        """Test custom no-access paths."""
        restrictions = PathRestrictions(no_access=["/custom/restricted"])

        allowed, reason = restrictions.check_path("/custom/restricted/file.txt")
        assert allowed is False
        assert "restricted" in reason

    def test_allowed_paths(self) -> None:
        """Test that non-restricted paths are allowed."""
        restrictions = PathRestrictions(no_access=["~/.ssh"])

        allowed, reason = restrictions.check_path("/tmp/safe_file.txt")
        assert allowed is True
        assert reason is None

    def test_extract_paths_from_command(self) -> None:
        """Test path extraction from commands."""
        restrictions = PathRestrictions()

        # Command with file paths
        paths = restrictions.extract_paths_from_command("cat /etc/passwd")
        assert len(paths) == 1
        assert paths[0] == Path("/etc/passwd")

        # Command with multiple paths
        paths = restrictions.extract_paths_from_command("cp /tmp/a /tmp/b")
        assert len(paths) == 2

        # Command with home directory
        paths = restrictions.extract_paths_from_command("cat ~/.bashrc")
        assert len(paths) == 1
        assert "~" in str(paths[0])

        # Command with no paths
        paths = restrictions.extract_paths_from_command("ls")
        assert len(paths) == 0

    def test_path_expansion(self) -> None:
        """Test that paths are properly expanded."""
        restrictions = PathRestrictions(no_access=["~/.config"])

        # Should block expanded path
        home = Path.home()
        config_path = home / ".config" / "test.conf"

        allowed, _reason = restrictions.check_path(config_path)
        assert allowed is False


class TestSandboxExecutor:
    """Test SandboxExecutor functionality."""

    def test_check_command_with_whitelist(self) -> None:
        """Test command checking with whitelist."""
        filter = CommandFilter(whitelist=["echo"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        # Allowed command
        check = sandbox.check_command("echo hello")
        assert check.allowed is True

        # Blocked command
        check = sandbox.check_command("rm -rf /")
        assert check.allowed is False

    def test_check_command_with_path_restrictions(self) -> None:
        """Test command checking with path restrictions."""
        filter = CommandFilter(whitelist=["cat"], blacklist=[], mode="whitelist")
        restrictions = PathRestrictions(no_access=["~/.ssh"])
        sandbox = SandboxExecutor(
            command_filter=filter, path_restrictions=restrictions
        )

        # Allowed path
        check = sandbox.check_command("cat /tmp/safe.txt")
        assert check.allowed is True

        # Restricted path
        check = sandbox.check_command("cat ~/.ssh/id_rsa")
        assert check.allowed is False
        assert ".ssh" in check.reason

    def test_execute_allowed_command(self) -> None:
        """Test executing an allowed command."""
        filter = CommandFilter(whitelist=["echo"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        result = sandbox.execute("echo hello world")

        assert result.success is True
        assert result.blocked is False
        assert "hello world" in result.stdout
        assert result.exit_code == 0

    def test_execute_blocked_command(self) -> None:
        """Test executing a blocked command."""
        filter = CommandFilter(whitelist=["echo"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        result = sandbox.execute("rm -rf /")

        assert result.success is False
        assert result.blocked is True
        assert result.blocked_reason is not None
        assert result.exit_code is None

    def test_execute_with_working_directory(self) -> None:
        """Test executing command with custom working directory."""
        filter = CommandFilter(whitelist=["pwd"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = sandbox.execute("pwd", cwd=tmpdir)

            assert result.success is True
            assert tmpdir in result.stdout

    def test_execute_with_timeout(self) -> None:
        """Test command timeout."""
        filter = CommandFilter(whitelist=["sleep"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        result = sandbox.execute("sleep 10", timeout=1)

        assert result.success is False
        assert "timed out" in result.stderr.lower()

    def test_execute_failing_command(self) -> None:
        """Test executing a command that fails."""
        filter = CommandFilter(whitelist=["ls"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        result = sandbox.execute("ls /nonexistent_directory_12345")

        assert result.success is False
        assert result.exit_code != 0
        assert result.stderr != ""

    def test_is_enabled(self) -> None:
        """Test sandbox enabled check."""
        filter_enabled = CommandFilter(
            whitelist=["ls"], blacklist=[], mode="whitelist"
        )
        sandbox_enabled = SandboxExecutor(command_filter=filter_enabled)
        assert sandbox_enabled.is_enabled() is True

        filter_disabled = CommandFilter(
            whitelist=[], blacklist=[], mode="disabled"
        )
        sandbox_disabled = SandboxExecutor(command_filter=filter_disabled)
        assert sandbox_disabled.is_enabled() is False

    def test_from_config(self) -> None:
        """Test creating sandbox from config."""
        from inkarms.config.schema import (
            RestrictedPathsConfig,
            SandboxConfig,
            SecurityConfig,
        )

        config = SecurityConfig(
            sandbox=SandboxConfig(enable=True, mode="whitelist"),
            whitelist=["ls", "cat"],
            blacklist=["rm -rf"],
            restricted_paths=RestrictedPathsConfig(
                read_only=[], no_access=["~/.ssh"]
            ),
        )

        sandbox = SandboxExecutor.from_config(config)

        # Test that configuration is applied
        check = sandbox.check_command("ls -la")
        assert check.allowed is True

        check = sandbox.check_command("rm -rf /")
        assert check.allowed is False

        check = sandbox.check_command("cat ~/.ssh/id_rsa")
        assert check.allowed is False

    def test_execute_with_custom_env(self) -> None:
        """Test executing command with custom environment variables."""
        filter = CommandFilter(whitelist=["printenv"], blacklist=[], mode="whitelist")
        sandbox = SandboxExecutor(command_filter=filter)

        result = sandbox.execute("printenv TEST_VAR", env={"TEST_VAR": "test_value"})

        assert result.success is True
        assert "test_value" in result.stdout
