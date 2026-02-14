"""Chat command handling for the Rich backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from inkarms.commands import CommandContext, CommandRegistry
from inkarms.commands import CommandResult as SharedResult
from inkarms.ui.protocol import UIView

if TYPE_CHECKING:
    from inkarms.ui.backends.rich_backend.backend import RichBackend


@dataclass
class CommandResult:
    """Result of a chat command execution."""

    message: str | None = None
    navigate_to: UIView | None = None
    should_exit: bool = False


class ChatCommandHandler:
    """Handles slash commands in the chat view.

    Delegates shared commands (help, clear, usage, etc.) to the
    platform-agnostic CommandRegistry. TUI navigation commands
    are handled locally.
    """

    def __init__(self, backend: RichBackend):
        self._backend = backend

    def _build_context(self) -> CommandContext:
        """Build a CommandContext from the RichBackend state."""
        return CommandContext(
            session_manager=self._backend.session_manager,
            model=self._backend.status.model,
            provider=self._backend.status.provider,
            tool_registry=self._backend.tool_registry,
            agent_config=self._backend.agent_config,
            on_clear=self._backend.clear_chat,
            on_session_loaded=self._backend.rebuild_messages_from_session,
        )

    def handle(self, text: str) -> CommandResult:
        """Parse and execute a slash command."""
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()

        # Navigation commands that exit the chat view (TUI-only)
        nav_map = {
            "/quit": None,
            "/q": None,
            "/exit": None,
            "/menu": UIView.MENU,
            "/m": UIView.MENU,
            "/dashboard": UIView.DASHBOARD,
            "/d": UIView.DASHBOARD,
            "/sessions": UIView.SESSIONS,
            "/s": UIView.SESSIONS,
            "/config": UIView.CONFIG,
            "/cfg": UIView.CONFIG,
        }
        if cmd in nav_map:
            return CommandResult(navigate_to=nav_map[cmd], should_exit=True)

        if cmd == "/chat":
            return CommandResult()  # Already in chat, no-op

        # Delegate to shared command registry
        ctx = self._build_context()
        shared = CommandRegistry.handle(text, ctx)
        if shared is not None:
            return self._from_shared(shared)

        return CommandResult(
            message=f"Unknown command: {cmd}. Type /help for available commands."
        )

    @staticmethod
    def _from_shared(result: SharedResult) -> CommandResult:
        """Convert a shared CommandResult to a TUI CommandResult."""
        return CommandResult(
            message=result.message,
            should_exit=result.should_exit,
        )
