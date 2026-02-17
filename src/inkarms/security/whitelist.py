"""
Command whitelist/blacklist filtering for InkArms sandbox.

This module provides command validation against configurable
whitelist and blacklist patterns using category-aware matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from inkarms.config.schema import BlacklistConfig

# Shell keywords that can precede a command in compound statements
_SHELL_KEYWORDS = frozenset({
    "do", "done", "then", "else", "elif", "fi", "time",
    "!", "{", "}", "((", "))",
})


@dataclass
class CommandSegment:
    """A single segment of a command chain (between ; && || |)."""

    text: str
    is_piped: bool = False
    base_command: str = ""
    tokens: list[str] = field(default_factory=list)


@dataclass
class CommandCheck:
    """Result of a command validation check."""

    allowed: bool
    reason: str | None = None
    matched_rule: str | None = None
    mode: Literal["whitelist", "blacklist", "prompt", "disabled"] | None = None


def _split_command_chain(command: str) -> list[CommandSegment]:
    """Split a command string into segments by ; && || | respecting quotes.

    Returns a list of CommandSegment with metadata about each segment.
    """
    segments: list[CommandSegment] = []
    current: list[str] = []
    i = 0
    in_single = False
    in_double = False
    is_piped = False

    while i < len(command):
        c = command[i]

        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
            i += 1
            continue
        if c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
            i += 1
            continue

        if in_single or in_double:
            current.append(c)
            i += 1
            continue

        # Check for ;
        if c == ";":
            _flush_segment(current, is_piped, segments)
            current = []
            is_piped = False
            i += 1
            continue

        # Check for && or ||
        if c in ("&", "|") and i + 1 < len(command) and command[i + 1] == c:
            _flush_segment(current, is_piped, segments)
            current = []
            is_piped = False
            i += 2
            continue

        # Check for single | (pipe)
        if c == "|":
            _flush_segment(current, is_piped, segments)
            current = []
            is_piped = True
            i += 1
            continue

        current.append(c)
        i += 1

    _flush_segment(current, is_piped, segments)
    return segments


def _flush_segment(
    chars: list[str], is_piped: bool, segments: list[CommandSegment]
) -> None:
    """Build a CommandSegment from accumulated chars and append to segments."""
    text = "".join(chars).strip()
    if not text:
        return

    # Tokenize the segment text
    tokens = text.split()
    if not tokens:
        return

    # Strip leading shell keywords to find the actual command
    base_idx = 0
    while base_idx < len(tokens) and tokens[base_idx] in _SHELL_KEYWORDS:
        base_idx += 1

    base_command = tokens[base_idx] if base_idx < len(tokens) else ""

    segments.append(CommandSegment(
        text=text,
        is_piped=is_piped,
        base_command=base_command,
        tokens=tokens,
    ))


class CommandFilter:
    """
    Filters commands based on whitelist/blacklist configuration.

    Uses category-aware matching where each blacklist category
    (single_word_commands, multi_word_patterns, sensitive_paths, etc.)
    uses a matching strategy suited to its purpose.

    Supports multiple modes:
    - whitelist: Only explicitly allowed commands pass
    - blacklist: All commands except blacklisted ones pass
    - prompt: All commands allowed but user is prompted
    - disabled: No filtering applied
    """

    def __init__(
        self,
        whitelist: list[str],
        blacklist: BlacklistConfig,
        mode: Literal["whitelist", "blacklist", "prompt", "disabled"] = "whitelist",
    ) -> None:
        """
        Initialize command filter.

        Args:
            whitelist: List of allowed command names
            blacklist: Structured blacklist configuration
            mode: Filtering mode
        """
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.mode = mode

        # Precompute whitelist set for fast lookup
        self._whitelist_set = {cmd.lower() for cmd in whitelist}

        # Precompute blacklist structures
        self._single_word_set = {
            cmd.lower() for cmd in blacklist.single_word_commands
        }

        # Parse multi_word_patterns into (command, required_tokens) tuples
        self._multi_word_parsed: list[tuple[str, list[str], str]] = []
        for pattern in blacklist.multi_word_patterns:
            parts = pattern.split()
            if parts:
                cmd = parts[0].lower()
                required = [t.lower() for t in parts[1:]]
                self._multi_word_parsed.append((cmd, required, pattern))

        self._pipe_interpreters_set = {
            cmd.lower() for cmd in blacklist.pipe_to_interpreters
        }

        # Collect all substring-match patterns
        self._substring_patterns: list[tuple[str, str]] = []
        for p in blacklist.command_substitutions:
            self._substring_patterns.append((p, f"command substitution: {p}"))
        for p in blacklist.sensitive_paths:
            self._substring_patterns.append((p, f"sensitive path: {p}"))
        for p in blacklist.dangerous_redirects:
            self._substring_patterns.append((p, f"dangerous redirect: {p}"))
        for p in blacklist.container_patterns:
            self._substring_patterns.append((p, f"container pattern: {p}"))
        for p in blacklist.dos_patterns:
            self._substring_patterns.append((p, f"DoS pattern: {p}"))

        # Compile word-boundary regexes for single_word_commands fallback
        self._word_boundary_checks: list[tuple[re.Pattern[str], str]] = []
        for cmd in blacklist.single_word_commands:
            regex = re.compile(rf"\b{re.escape(cmd)}\b", re.IGNORECASE)
            self._word_boundary_checks.append((regex, cmd))

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

        command = command.strip()
        if not command:
            return CommandCheck(
                allowed=False, reason="Empty command", mode=self.mode
            )

        # Check blacklist first (higher priority)
        blacklist_result = self._check_blacklist(command)
        if blacklist_result is not None:
            return blacklist_result

        # In whitelist mode, check if command is whitelisted
        if self.mode == "whitelist":
            return self._check_whitelist(command)

        # In blacklist mode, allow if not blacklisted
        if self.mode == "blacklist":
            return CommandCheck(allowed=True, mode=self.mode)

        # In prompt mode, return allowed (caller should prompt user)
        if self.mode == "prompt":
            return CommandCheck(allowed=True, mode=self.mode)

        return CommandCheck(
            allowed=False, reason=f"Unknown mode: {self.mode}", mode=self.mode
        )

    def _check_blacklist(self, command: str) -> CommandCheck | None:
        """Run all blacklist checks. Returns CommandCheck if blocked, None if OK."""
        # Step 1: Fast substring checks on full command
        for pattern, description in self._substring_patterns:
            if pattern in command:
                return CommandCheck(
                    allowed=False,
                    reason=f"Command matches blacklist: {description}",
                    matched_rule=pattern,
                    mode=self.mode,
                )

        # Step 2: Split into segments and check each
        segments = _split_command_chain(command)
        for segment in segments:
            result = self._check_segment(segment)
            if result is not None:
                return result

        # Step 3: Word-boundary fallback for single_word_commands
        for regex, cmd in self._word_boundary_checks:
            if regex.search(command):
                return CommandCheck(
                    allowed=False,
                    reason=f"Command contains blacklisted command '{cmd}'",
                    matched_rule=cmd,
                    mode=self.mode,
                )

        return None

    def _check_segment(self, segment: CommandSegment) -> CommandCheck | None:
        """Check a single command segment against blacklist rules."""
        base = segment.base_command.lower()
        if not base:
            return None

        # Extract basename for full-path commands like /usr/bin/sudo
        base_name = base.rsplit("/", 1)[-1] if "/" in base else None

        # Single word commands (case-insensitive exact match)
        if base in self._single_word_set or (
            base_name and base_name in self._single_word_set
        ):
            return CommandCheck(
                allowed=False,
                reason=f"Command '{segment.base_command}' is blacklisted",
                matched_rule=segment.base_command,
                mode=self.mode,
            )

        # Multi-word patterns
        segment_tokens_lower = [t.lower() for t in segment.tokens]
        for cmd, required_tokens, pattern in self._multi_word_parsed:
            if base != cmd and (base_name is None or base_name != cmd):
                continue
            if all(tok in segment_tokens_lower for tok in required_tokens):
                return CommandCheck(
                    allowed=False,
                    reason=f"Command matches blacklist pattern: {pattern}",
                    matched_rule=pattern,
                    mode=self.mode,
                )

        # Pipe-to-interpreter check
        if segment.is_piped and (
            base in self._pipe_interpreters_set
            or (base_name and base_name in self._pipe_interpreters_set)
        ):
            return CommandCheck(
                allowed=False,
                reason=f"Piping to interpreter "
                       f"'{segment.base_command}' is not allowed",
                matched_rule=segment.base_command,
                mode=self.mode,
            )

        # Variable substitution at command position
        if segment.base_command.startswith("$"):
            return CommandCheck(
                allowed=False,
                reason="Variable substitution at command position "
                       "is not allowed",
                matched_rule=segment.base_command,
                mode=self.mode,
            )

        return None

    def _check_whitelist(self, command: str) -> CommandCheck:
        """Check if command is whitelisted."""
        segments = _split_command_chain(command)

        for segment in segments:
            base = segment.base_command.lower()
            if not base:
                continue

            # Check base command name (also handle full paths)
            base_name = base.rsplit("/", 1)[-1] if "/" in base else base
            if base_name not in self._whitelist_set:
                return CommandCheck(
                    allowed=False,
                    reason=f"Command '{segment.base_command}' not in whitelist",
                    mode=self.mode,
                )

        # All segments' commands are whitelisted
        return CommandCheck(
            allowed=True,
            matched_rule=segments[0].base_command if segments else None,
            mode=self.mode,
        )

    def add_to_whitelist(self, pattern: str) -> None:
        """Add a command to the whitelist."""
        if pattern not in self.whitelist:
            self.whitelist.append(pattern)
            self._whitelist_set.add(pattern.lower())

    def add_to_blacklist(self, pattern: str) -> None:
        """Add a pattern to the blacklist multi_word_patterns."""
        if pattern not in self.blacklist.multi_word_patterns:
            self.blacklist.multi_word_patterns.append(pattern)
            parts = pattern.split()
            if parts:
                cmd = parts[0].lower()
                required = [t.lower() for t in parts[1:]]
                self._multi_word_parsed.append((cmd, required, pattern))

    def remove_from_whitelist(self, pattern: str) -> bool:
        """Remove a command from the whitelist."""
        try:
            self.whitelist.remove(pattern)
            self._whitelist_set.discard(pattern.lower())
            return True
        except ValueError:
            return False

    def remove_from_blacklist(self, pattern: str) -> bool:
        """Remove a pattern from the blacklist multi_word_patterns."""
        try:
            self.blacklist.multi_word_patterns.remove(pattern)
            self._multi_word_parsed = [
                entry for entry in self._multi_word_parsed if entry[2] != pattern
            ]
            return True
        except ValueError:
            return False
