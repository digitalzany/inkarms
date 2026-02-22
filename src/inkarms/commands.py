"""Shared command registry for slash commands across all frontends.

Provides a platform-agnostic command registry that can be used by the
Rich/TUI backend, Telegram, Slack, Discord, and other adapters.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from inkarms.config.loader import clear_config_cache, get_config, load_yaml_file, save_yaml_file
from inkarms.config.providers import get_model_choices, get_provider_choices, load_providers_config
from inkarms.models.agent import ApprovalMode
from inkarms.storage.paths import get_inkarms_home

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
            "/load <name> /history /model [name] /models /tools /agent [mode]"
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


def _resolve_model_arg(arg: str, current_provider: str) -> tuple[str, str | None]:
    """Resolve and validate a model argument.

    Accepts 'provider/model' (validates provider exists) or bare 'model'
    (auto-resolves to current_provider/model). Model IDs are NOT validated
    against our static config — the provider validates at request time.

    Returns (resolved_full_model, error_message). error_message is None if valid.
    """
    providers = load_providers_config()

    if "/" in arg:
        provider_id, model_id = arg.split("/", 1)
        if provider_id not in providers:
            known = ", ".join(sorted(providers.keys()))
            return "", f"Unknown provider '{provider_id}'. Known providers: {known}"
        return f"{provider_id}/{model_id}", None

    # Bare model name — always use current provider
    model_id = arg
    if not current_provider:
        known = ", ".join(sorted(providers.keys()))
        return "", (
            f"No current provider set. Specify as <provider>/<model>.\n"
            f"Known providers: {known}"
        )
    if current_provider not in providers:
        known = ", ".join(sorted(providers.keys()))
        return "", f"Current provider '{current_provider}' is unknown. Known: {known}"

    return f"{current_provider}/{model_id}", None


def cmd_model(ctx: CommandContext, arg: str) -> CommandResult:
    """Show or change model. Accepts provider/model or bare model name."""
    current_provider = ctx.provider or (
        ctx.model.split("/")[0] if ctx.model and "/" in ctx.model else ""
    )
    if arg:
        resolved, error = _resolve_model_arg(arg, current_provider)
        if error:
            return CommandResult(message=f"Invalid model: {error}")
        if ctx.session_manager:
            ctx.session_manager.set_model(resolved)
        saved = _save_model_to_config(resolved)
        suffix = " (saved to config)" if saved else " (session only — config save failed)"
        return CommandResult(message=f"Model changed to: {resolved}{suffix}")

    # Show current model and last 5 available models
    lines = [f"Current model: {ctx.model or '(not set)'}"]
    available = _get_available_models(ctx)
    if available:
        preview = available[-5:]
        total = len(available)
        lines.append(f"\nAvailable models for provider '{current_provider}' (last {len(preview)} of {total}):")
        for m in preview:
            lines.append(f"  \u2022 {m}")
        lines.append("\nUse /model <model> to change | /models for all")
    else:
        lines.append("No models found for current provider")

    return CommandResult(message="\n".join(lines))


def _save_model_to_config(model: str) -> bool:
    """Persist model change to user config. Returns True on success."""
    try:
        config_path = get_inkarms_home() / "config.yaml"
        config_dict = load_yaml_file(config_path) if config_path.exists() else {}
        if "providers" not in config_dict:
            config_dict["providers"] = {}
        config_dict["providers"]["default"] = model
        save_yaml_file(config_path, config_dict)
        clear_config_cache()
        return True
    except Exception:
        return False


def _get_available_models(ctx: CommandContext | None = None) -> list[str]:
    """Collect available model names from config for the current provider."""
    try:
        provider = ""
        if ctx and ctx.provider:
            provider = ctx.provider.split("/")[0] if "/" in ctx.provider else ctx.provider

        if not provider:
            try:
                default = get_config().providers.default
                provider = default.split("/")[0] if "/" in default else default
            except Exception:
                pass

        if not provider:
            return []

        return [f"{provider}/{m[0]}" for m in get_model_choices(provider)]

    except Exception:
        return []


def cmd_models(_ctx: CommandContext, _arg: str) -> CommandResult:
    """Show all available providers and their models."""
    try:
        providers = get_provider_choices()
        if not providers:
            return CommandResult(message="No providers configured")

        lines = ["Available providers and models:"]
        for provider_id, provider_name, _ in providers:
            models = get_model_choices(provider_id)
            lines.append(f"\n{provider_name} ({len(models)} models):")
            for model_id, model_name, _ in models:
                label = f"  \u2022 {model_id}"
                if model_name and model_name != model_id:
                    label += f" \u2014 {model_name}"
                lines.append(label)

        lines.append("\nUse /model <provider>/<name> to change")
        return CommandResult(message="\n".join(lines))
    except Exception as e:
        return CommandResult(message=f"Error loading models: {e}")


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
        "/models": ("Show all providers and models", cmd_models),
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
