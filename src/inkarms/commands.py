"""Shared command registry for slash commands across all frontends.

Provides a platform-agnostic command registry that can be used by the
Rich/TUI backend, Telegram, Slack, Discord, and other adapters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from inkarms.models.agent import ApprovalMode

if TYPE_CHECKING:
    from inkarms.memory.manager import SessionManager
    from inkarms.tools.registry import ToolRegistry


@dataclass
class CommandContext:
    """Dependencies for command execution.

    Each frontend builds this from its own state before calling the registry.
    """

    session_manager: SessionManager | None = None
    model: str = ""
    provider: str = ""
    tool_registry: ToolRegistry | None = None
    agent_config: Any = None
    on_clear: Callable[[], None] | None = None
    on_session_loaded: Callable[[], None] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandResult:
    """Result of a shared command execution."""

    message: str | None = None
    should_exit: bool = False


def cmd_help(_ctx: CommandContext, _arg: str) -> CommandResult:
    """Show available commands."""
    return CommandResult(
        message=(
            "Commands: /help /clear /usage /status /save [name] "
            "/load <name> /history /model [name] /tools /agent [mode]"
        )
    )


def cmd_clear(ctx: CommandContext, _arg: str) -> CommandResult:
    """Clear current session."""
    if ctx.on_clear:
        ctx.on_clear()
    elif ctx.session_manager:
        ctx.session_manager.clear_session()
    return CommandResult(message="Chat cleared")


def cmd_usage(ctx: CommandContext, _arg: str) -> CommandResult:
    """Show token usage and cost."""
    if ctx.session_manager:
        usage = ctx.session_manager.get_context_usage()
        info = ctx.session_manager.get_session_info()
        return CommandResult(
            message=(
                f"Tokens: {usage.current_tokens:,}/{usage.max_tokens:,} "
                f"({usage.usage_percent * 100:.1f}%) | "
                f"Cost: ${info['total_cost']:.4f} | "
                f"Turns: {info['turn_count']}"
            )
        )
    return CommandResult(message="Session manager not available")


def cmd_status(ctx: CommandContext, _arg: str) -> CommandResult:
    """Show current status."""
    parts = [
        f"Provider: {ctx.provider}",
        f"Model: {ctx.model}",
    ]
    if ctx.session_manager:
        usage = ctx.session_manager.get_context_usage()
        parts.append(f"Context: {usage.usage_percent * 100:.1f}%")
        if usage.should_handoff:
            parts.append("HANDOFF RECOMMENDED")
        elif usage.should_compact:
            parts.append("Compaction recommended")
    return CommandResult(message=" | ".join(parts))


def cmd_save(ctx: CommandContext, arg: str) -> CommandResult:
    """Save session snapshot."""
    name = arg or f"session-{datetime.now().strftime('%Y%m%d-%H%M')}"
    if ctx.session_manager:
        try:
            ctx.session_manager.save_snapshot(name)
            return CommandResult(message=f"Session saved as '{name}'")
        except Exception as e:
            return CommandResult(message=f"Save failed: {e}")
    return CommandResult(message="Session manager not available")


def cmd_load(ctx: CommandContext, arg: str) -> CommandResult:
    """Load session snapshot."""
    if not ctx.session_manager:
        return CommandResult(message="Session manager not available")

    if not arg:
        entries = ctx.session_manager.list_memory("snapshot")
        if entries:
            names = [e.name for e in entries]
            return CommandResult(
                message=f"Snapshots: {', '.join(names)} | /load <name>"
            )
        return CommandResult(message="No snapshots found")

    session = ctx.session_manager.load_snapshot(arg)
    if session:
        if ctx.on_session_loaded:
            ctx.on_session_loaded()
        return CommandResult(message=f"Session '{arg}' loaded")
    return CommandResult(message=f"Snapshot '{arg}' not found")


def cmd_history(ctx: CommandContext, _arg: str) -> CommandResult:
    """Show message history."""
    if ctx.session_manager:
        turns = ctx.session_manager.session.turns
        if turns:
            count = len(turns)
            first = turns[0].timestamp.strftime("%H:%M")
            last = turns[-1].timestamp.strftime("%H:%M")
            return CommandResult(
                message=f"History: {count} turns ({first} - {last})"
            )
        return CommandResult(message="No history in current session")
    return CommandResult(message="Session manager not available")


def cmd_model(ctx: CommandContext, arg: str) -> CommandResult:
    """Show or change model. Lists available models when called without args."""
    if arg and ctx.session_manager:
        ctx.session_manager.set_model(arg)
        return CommandResult(message=f"Model changed to: {arg}")

    # Show current model and available models
    parts = [f"Current model: {ctx.model}"]

    available = _get_available_models()
    if available:
        parts.append(f"Available: {', '.join(available)}")
        parts.append("Usage: /model <name>")

    return CommandResult(message=" | ".join(parts))


def _get_available_models() -> list[str]:
    """Collect available model names from config."""
    try:
        from inkarms.config import get_config

        config = get_config()
        models: list[str] = []

        # Default model
        if config.providers.default:
            models.append(config.providers.default)

        # Fallback chain
        for fb in config.providers.fallback:
            if fb not in models:
                models.append(fb)

        # Aliases (show alias → target)
        for alias, target in config.providers.aliases.items():
            label = f"{alias} ({target})" if target not in models else alias
            if label not in models:
                models.append(label)

        return models
    except Exception:
        return []


def cmd_tools(ctx: CommandContext, _arg: str) -> CommandResult:
    """Show registered tools."""
    registry = ctx.tool_registry
    if not registry or len(registry) == 0:
        return CommandResult(message="No tools registered")
    tools = registry.list_tools()
    parts = []
    for tool in tools:
        label = f"{tool.name} [!]" if tool.is_dangerous else tool.name
        parts.append(label)
    mode = "off"
    if ctx.agent_config:
        mode = ctx.agent_config.approval_mode.value
    return CommandResult(message=f"Tools ({mode}): {', '.join(parts)}")


def cmd_agent(ctx: CommandContext, arg: str) -> CommandResult:
    """Show or change agent settings."""
    config = ctx.agent_config
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


# Command handler type
CommandHandler = Callable[[CommandContext, str], CommandResult]


class CommandRegistry:
    """Registry of shared slash commands.

    These commands work identically across CLI, TUI, Telegram, Slack, etc.
    Frontend-specific commands (e.g. TUI navigation) are handled separately.
    """

    COMMANDS: ClassVar[dict[str, tuple[str, CommandHandler]]] = {
        "/help": ("Show available commands", cmd_help),
        "/clear": ("Clear current session", cmd_clear),
        "/usage": ("Show token usage", cmd_usage),
        "/status": ("Show current status", cmd_status),
        "/save": ("Save session snapshot", cmd_save),
        "/load": ("Load session snapshot", cmd_load),
        "/history": ("Show message history", cmd_history),
        "/model": ("Show/change model", cmd_model),
        "/tools": ("Show registered tools", cmd_tools),
        "/agent": ("Show/change agent settings", cmd_agent),
    }

    @staticmethod
    def handle(text: str, ctx: CommandContext) -> CommandResult | None:
        """Parse and execute a shared slash command.

        Args:
            text: Full command text (e.g. "/model gpt-4").
            ctx: Command context with dependencies.

        Returns:
            CommandResult if handled, None if command not recognized.
        """
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        entry = CommandRegistry.COMMANDS.get(cmd)
        if entry is None:
            return None

        _, handler = entry
        return handler(ctx, arg)

    @staticmethod
    def list_commands() -> list[tuple[str, str]]:
        """List all registered commands with descriptions.

        Returns:
            List of (command_name, description) tuples.
        """
        return [(cmd, desc) for cmd, (desc, _) in CommandRegistry.COMMANDS.items()]

    @staticmethod
    def is_command(text: str) -> bool:
        """Check if text is a registered shared command.

        Args:
            text: Text to check.

        Returns:
            True if the text starts with a registered command.
        """
        if not text.startswith("/"):
            return False
        cmd = text.split(maxsplit=1)[0].lower()
        return cmd in CommandRegistry.COMMANDS
