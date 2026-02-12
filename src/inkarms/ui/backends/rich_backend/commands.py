"""Chat command handling for the Rich backend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

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
    """Handles slash commands in the chat view."""

    def __init__(self, backend: RichBackend):
        self._backend = backend

    def handle(self, text: str) -> CommandResult:
        """Parse and execute a slash command."""
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Navigation commands that exit the chat view
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

        # In-chat commands
        handler = self._COMMANDS.get(cmd)
        if handler:
            return handler(self, arg)

        if cmd == "/chat":
            return CommandResult()  # Already in chat, no-op

        return CommandResult(
            message=f"Unknown command: {cmd}. Type /help for available commands."
        )

    def _cmd_help(self, arg: str) -> CommandResult:
        return CommandResult(
            message=(
                "Commands: /menu /dashboard /sessions /clear /usage /status "
                "/save [name] /load <name> /history /model /tools /agent [mode] /quit "
                "| Use @file to include file"
            )
        )

    def _cmd_clear(self, arg: str) -> CommandResult:
        self._backend.clear_chat()
        return CommandResult(message="Chat cleared")

    def _cmd_usage(self, arg: str) -> CommandResult:
        if self._backend.session_manager:
            usage = self._backend.session_manager.get_context_usage()
            info = self._backend.session_manager.get_session_info()
            return CommandResult(
                message=(
                    f"Tokens: {usage.current_tokens:,}/{usage.max_tokens:,} "
                    f"({usage.usage_percent * 100:.1f}%) | "
                    f"Cost: ${info['total_cost']:.4f} | "
                    f"Turns: {info['turn_count']}"
                )
            )
        s = self._backend.status
        return CommandResult(
            message=f"Tokens: {s.total_tokens:,} | Cost: ${s.total_cost:.4f}"
        )

    def _cmd_status(self, arg: str) -> CommandResult:
        status_parts = [
            f"Provider: {self._backend.status.provider}",
            f"Model: {self._backend.status.model}",
        ]
        if self._backend.session_manager:
            usage = self._backend.session_manager.get_context_usage()
            status_parts.append(f"Context: {usage.usage_percent * 100:.1f}%")
            if usage.should_handoff:
                status_parts.append("HANDOFF RECOMMENDED")
            elif usage.should_compact:
                status_parts.append("Compaction recommended")
        return CommandResult(message=" | ".join(status_parts))

    def _cmd_save(self, arg: str) -> CommandResult:
        name = arg or f"session-{datetime.now().strftime('%Y%m%d-%H%M')}"
        if self._backend.session_manager:
            try:
                self._backend.session_manager.save_snapshot(name)
                return CommandResult(message=f"Session saved as '{name}'")
            except Exception as e:
                return CommandResult(message=f"Save failed: {e}")
        return CommandResult(message="Session manager not available")

    def _cmd_load(self, arg: str) -> CommandResult:
        if not self._backend.session_manager:
            return CommandResult(message="Session manager not available")

        if not arg:
            entries = self._backend.session_manager.list_memory("snapshot")
            if entries:
                names = [e.name for e in entries]
                return CommandResult(
                    message=f"Snapshots: {', '.join(names)} | /load <name>"
                )
            return CommandResult(message="No snapshots found")

        session = self._backend.session_manager.load_snapshot(arg)
        if session:
            self._backend.rebuild_messages_from_session()
            return CommandResult(message=f"Session '{arg}' loaded")
        return CommandResult(message=f"Snapshot '{arg}' not found")

    def _cmd_history(self, arg: str) -> CommandResult:
        if self._backend.session_manager:
            turns = self._backend.session_manager.session.turns
            if turns:
                count = len(turns)
                first = turns[0].timestamp.strftime("%H:%M")
                last = turns[-1].timestamp.strftime("%H:%M")
                return CommandResult(
                    message=f"History: {count} turns ({first} - {last})"
                )
            return CommandResult(message="No history in current session")
        return CommandResult(
            message=f"Messages: {len(self._backend.messages)}"
        )

    def _cmd_model(self, arg: str) -> CommandResult:
        if arg and self._backend.session_manager:
            self._backend.session_manager.set_model(arg)
            self._backend.status.model = arg
            return CommandResult(message=f"Model changed to: {arg}")
        return CommandResult(
            message=f"Current model: {self._backend.status.model}"
        )

    def _cmd_tools(self, arg: str) -> CommandResult:
        registry = self._backend.tool_registry
        if not registry or len(registry) == 0:
            return CommandResult(message="No tools registered")
        tools = registry.list_tools()
        parts = []
        for tool in tools:
            label = f"{tool.name} [!]" if tool.is_dangerous else tool.name
            parts.append(label)
        mode = "off"
        if self._backend.agent_config:
            mode = self._backend.agent_config.approval_mode.value
        return CommandResult(message=f"Tools ({mode}): {', '.join(parts)}")

    def _cmd_agent(self, arg: str) -> CommandResult:
        config = self._backend.agent_config
        if not config:
            return CommandResult(message="Agent not configured")
        if not arg:
            mode = config.approval_mode.value
            enabled = config.enable_tools
            iters = config.max_iterations
            return CommandResult(
                message=(
                    f"Agent: tools={'on' if enabled else 'off'} mode={mode} "
                    f"max_iterations={iters}"
                )
            )
        from inkarms.models.agent import ApprovalMode

        valid = {m.value for m in ApprovalMode}
        if arg in valid:
            config.approval_mode = ApprovalMode(arg)
            return CommandResult(message=f"Agent mode changed to: {arg}")
        if arg == "on":
            config.enable_tools = True
            return CommandResult(message="Tools enabled")
        if arg == "off":
            config.enable_tools = False
            return CommandResult(message="Tools disabled")
        return CommandResult(
            message="Usage: /agent [on|off|auto|manual|disabled]"
        )

    _COMMANDS: dict[str, object] = {
        "/help": _cmd_help,
        "/clear": _cmd_clear,
        "/usage": _cmd_usage,
        "/status": _cmd_status,
        "/save": _cmd_save,
        "/load": _cmd_load,
        "/history": _cmd_history,
        "/model": _cmd_model,
        "/tools": _cmd_tools,
        "/agent": _cmd_agent,
    }
