"""Completers and lexers for the Rich backend."""

from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.lexers import Lexer


class CommandCompleter(Completer):
    """Completer for slash commands with fuzzy matching."""

    COMMANDS = [
        ("/help", "Show available commands"),
        ("/menu", "Return to main menu"),
        ("/dashboard", "Show dashboard"),
        ("/sessions", "Manage sessions"),
        ("/config", "Open configuration"),
        ("/clear", "Clear current session"),
        ("/usage", "Show token usage"),
        ("/status", "Show current status"),
        ("/model", "Show/change model"),
        ("/quit", "Exit InkArms"),
        ("/save", "Save session"),
        ("/load", "Load session"),
        ("/history", "Show message history"),
        ("/chat", "Go to chat"),
        ("/tools", "Show registered tools"),
        ("/agent", "Show/change agent settings"),
    ]

    def _fuzzy_match(self, text: str, cmd: str) -> bool:
        if cmd.startswith(text):
            return True
        text_lower = text.lower()
        cmd_lower = cmd.lower()
        t_idx = 0
        for c in cmd_lower:
            if t_idx < len(text_lower) and c == text_lower[t_idx]:
                t_idx += 1
        return t_idx == len(text_lower)

    def _match_score(self, text: str, cmd: str) -> int:
        return 0 if cmd.startswith(text) else 1

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip()
        if not text.startswith("/"):
            return

        matches = []
        for cmd, desc in self.COMMANDS:
            if self._fuzzy_match(text, cmd):
                matches.append((self._match_score(text, cmd), cmd, desc))

        matches.sort(key=lambda x: (x[0], x[1]))
        for score, cmd, desc in matches:
            yield Completion(cmd, start_position=-len(text), display=cmd, display_meta=desc)


COMMAND_COMPLETER = CommandCompleter()


class AnsiLexer(Lexer):
    """Lexer that interprets ANSI escape codes and returns styled fragments."""

    def lex_document(self, document):
        """Return a function that returns styled fragments for a line."""
        from prompt_toolkit.formatted_text import ANSI, to_formatted_text

        lines = document.lines

        def get_line(lineno):
            if lineno < len(lines):
                line = lines[lineno]
                try:
                    formatted = list(to_formatted_text(ANSI(line + "\n")))
                    result = []
                    for style, frag in formatted:
                        cleaned = frag.rstrip("\n")
                        if cleaned:
                            result.append((style, cleaned))
                    return result
                except Exception:
                    return [("", line)]
            return []

        return get_line

    def invalidation_hash(self):
        return None
