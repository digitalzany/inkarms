"""
Command whitelist/blacklist filtering for InkArms sandbox.

This module provides command validation against configurable
whitelist and blacklist patterns.
"""

import re
import shlex
from dataclasses import dataclass
from typing import Literal


@dataclass
class CommandCheck:
    """Result of a command validation check."""

    allowed: bool
    reason: str | None = None
    matched_rule: str | None = None
    mode: Literal["whitelist", "blacklist", "prompt", "disabled"] | None = None


class CommandFilter:
    """
    Filters commands based on whitelist/blacklist configuration.

    Supports multiple modes:
    - whitelist: Only explicitly allowed commands pass
    - blacklist: All commands except blacklisted ones pass
    - prompt: All commands allowed but user is prompted
    - disabled: No filtering applied
    """

    def __init__(
        self,
        whitelist: list[str],
        blacklist: list[str],
        mode: Literal["whitelist", "blacklist", "prompt", "disabled"] = "whitelist",
    ) -> None:
        """
        Initialize command filter.

        Args:
            whitelist: List of allowed command patterns
            blacklist: List of forbidden command patterns
            mode: Filtering mode
        """
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.mode = mode

        # Compile patterns for efficiency
        self._whitelist_patterns = [self._compile_pattern(p) for p in whitelist]
        self._blacklist_patterns = [self._compile_pattern(p) for p in blacklist]

    def _compile_pattern(self, pattern: str) -> re.Pattern[str]:
        """
        Compile a command pattern to regex.

        Patterns support:
        - Exact matches: "ls" matches only "ls"
        - Wildcards: "ls *" matches "ls" with any arguments
        - Regex patterns: "rm.*-rf" matches dangerous rm commands
        """
        # Escape special regex chars except * which we treat as wildcard
        escaped = pattern.replace(".", r"\.")
        escaped = escaped.replace("+", r"\+")
        escaped = escaped.replace("?", r"\?")
        escaped = escaped.replace("(", r"\(")
        escaped = escaped.replace(")", r"\)")
        escaped = escaped.replace("[", r"\[")
        escaped = escaped.replace("]", r"\]")
        escaped = escaped.replace("{", r"\{")
        escaped = escaped.replace("}", r"\}")
        escaped = escaped.replace("^", r"\^")
        escaped = escaped.replace("$", r"\$")

        # Replace * wildcard with regex equivalent
        escaped = escaped.replace("*", ".*")

        # Match full command (start to end or to pipe/redirect)
        return re.compile(f"^{escaped}(?:\\s|$|\\||>|<|&|;)")

    def check_command(self, command: str) -> CommandCheck:
        """
        Check if a command is allowed based on configured rules.

        Args:
            command: Shell command to validate

        Returns:
            CommandCheck with validation result
        """
        if self.mode == "disabled":
            return CommandCheck(allowed=True, mode="disabled")

        # Parse command to get base command
        try:
            tokens = shlex.split(command)
            if not tokens:
                return CommandCheck(
                    allowed=False, reason="Empty command", mode=self.mode
                )
            base_command = tokens[0]
        except ValueError:
            # Shlex parsing failed (unclosed quotes, etc.)
            return CommandCheck(
                allowed=False, reason="Invalid command syntax", mode=self.mode
            )

        # Check blacklist first (higher priority)
        for pattern, regex in zip(self.blacklist, self._blacklist_patterns, strict=False):
            if regex.search(command):
                return CommandCheck(
                    allowed=False,
                    reason=f"Command matches blacklist pattern: {pattern}",
                    matched_rule=pattern,
                    mode=self.mode,
                )

        # In whitelist mode, check if command is whitelisted
        if self.mode == "whitelist":
            for pattern, regex in zip(self.whitelist, self._whitelist_patterns, strict=False):
                if regex.search(command):
                    return CommandCheck(
                        allowed=True, matched_rule=pattern, mode=self.mode
                    )

            # Not in whitelist
            return CommandCheck(
                allowed=False,
                reason=f"Command '{base_command}' not in whitelist",
                mode=self.mode,
            )

        # In blacklist mode, allow if not blacklisted
        if self.mode == "blacklist":
            return CommandCheck(allowed=True, mode=self.mode)

        # In prompt mode, return allowed (caller should prompt user)
        if self.mode == "prompt":
            return CommandCheck(allowed=True, mode=self.mode)

        # Should never reach here
        return CommandCheck(
            allowed=False, reason=f"Unknown mode: {self.mode}", mode=self.mode
        )

    def add_to_whitelist(self, pattern: str) -> None:
        """Add a pattern to the whitelist."""
        if pattern not in self.whitelist:
            self.whitelist.append(pattern)
            self._whitelist_patterns.append(self._compile_pattern(pattern))

    def add_to_blacklist(self, pattern: str) -> None:
        """Add a pattern to the blacklist."""
        if pattern not in self.blacklist:
            self.blacklist.append(pattern)
            self._blacklist_patterns.append(self._compile_pattern(pattern))

    def remove_from_whitelist(self, pattern: str) -> bool:
        """
        Remove a pattern from the whitelist.

        Returns:
            True if pattern was removed, False if not found
        """
        try:
            idx = self.whitelist.index(pattern)
            self.whitelist.pop(idx)
            self._whitelist_patterns.pop(idx)
            return True
        except ValueError:
            return False

    def remove_from_blacklist(self, pattern: str) -> bool:
        """
        Remove a pattern from the blacklist.

        Returns:
            True if pattern was removed, False if not found
        """
        try:
            idx = self.blacklist.index(pattern)
            self.blacklist.pop(idx)
            self._blacklist_patterns.pop(idx)
            return True
        except ValueError:
            return False
