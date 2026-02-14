"""
inkarms platforms - Manage multi-platform messaging.

Usage:
    inkarms platforms list
    inkarms platforms start [--platform PLATFORM]
    inkarms platforms stop [--platform PLATFORM]
    inkarms platforms status
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from inkarms.audit import get_audit_logger
from inkarms.config import get_config
from inkarms.models.agent import AgentEvent, EventType
from inkarms.models.platforms import PlatformType
from inkarms.platforms.adapters.protocol import PlatformAdapter
from inkarms.platforms.processor import MessageProcessor
from inkarms.platforms.rate_limiter import get_rate_limiter
from inkarms.platforms.router import MessageRouter
from inkarms.platforms.session_mapper import get_session_mapper

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="platforms",
    help="Manage multi-platform messaging adapters.",
)

console = Console()


def _get_config_value(config_dict: dict, key: str, env_var: str) -> str | None:
    """Get config value, checking environment variable if not set."""
    value = config_dict.get(key)
    if value and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.getenv(env_name)
    return value


def _try_create_adapter(
    name: str,
    import_path: str,
    class_name: str,
    pip_package: str,
    **kwargs,
) -> PlatformAdapter | None:
    """Try to create a platform adapter, handling import errors.

    Args:
        name: Human-readable platform name
        import_path: Module import path
        class_name: Adapter class name
        pip_package: pip install instruction
        **kwargs: Keyword arguments to pass to adapter constructor

    Returns:
        Adapter instance or None on import error
    """
    try:
        import importlib

        module = importlib.import_module(import_path)
        adapter_cls = getattr(module, class_name)
        return adapter_cls(**kwargs)
    except ImportError as e:
        console.print(f"[yellow]Warning: {name} adapter not available: {e}[/yellow]")
        console.print(f"[dim]Install with: pip install {pip_package}[/dim]")
        return None


def _create_adapters(config) -> list[PlatformAdapter]:
    """Create platform adapters based on configuration."""
    adapters: list[PlatformAdapter] = []

    # Telegram
    if config.platforms.telegram.enable:
        bot_token = _get_config_value(
            config.platforms.telegram.model_dump(), "bot_token", "TELEGRAM_BOT_TOKEN"
        )
        if bot_token:
            adapter = _try_create_adapter(
                "Telegram",
                "inkarms.platforms.adapters.telegram",
                "TelegramAdapter",
                "python-telegram-bot",
                bot_token=bot_token,
                allowed_users=config.platforms.telegram.allowed_users,
                parse_mode=config.platforms.telegram.parse_mode,
                polling_interval=config.platforms.telegram.polling_interval,
            )
            if adapter:
                adapters.append(adapter)
        else:
            console.print(
                "[yellow]Warning: Telegram enabled but bot_token not configured[/yellow]"
            )

    # Slack
    if config.platforms.slack.enable:
        bot_token = _get_config_value(
            config.platforms.slack.model_dump(), "bot_token", "SLACK_BOT_TOKEN"
        )
        app_token = _get_config_value(
            config.platforms.slack.model_dump(), "app_token", "SLACK_APP_TOKEN"
        )
        if bot_token and app_token:
            adapter = _try_create_adapter(
                "Slack",
                "inkarms.platforms.adapters.slack",
                "SlackAdapter",
                "slack-sdk",
                bot_token=bot_token,
                app_token=app_token,
                allowed_channels=config.platforms.slack.allowed_channels,
            )
            if adapter:
                adapters.append(adapter)
        else:
            console.print(
                "[yellow]Warning: Slack enabled but tokens not configured[/yellow]"
            )

    # Discord
    if config.platforms.discord.enable:
        bot_token = _get_config_value(
            config.platforms.discord.model_dump(), "bot_token", "DISCORD_BOT_TOKEN"
        )
        if bot_token:
            adapter = _try_create_adapter(
                "Discord",
                "inkarms.platforms.adapters.discord",
                "DiscordAdapter",
                "discord.py",
                bot_token=bot_token,
                allowed_guilds=config.platforms.discord.allowed_guilds,
                allowed_channels=config.platforms.discord.allowed_channels,
                command_prefix=config.platforms.discord.command_prefix,
            )
            if adapter:
                adapters.append(adapter)
        else:
            console.print(
                "[yellow]Warning: Discord enabled but bot_token not configured[/yellow]"
            )

    return adapters


def _platform_event_callback(event: AgentEvent) -> None:
    """Log agent events for platform tool execution."""
    if event.event_type in (EventType.TOOL_START, EventType.TOOL_COMPLETE, EventType.TOOL_ERROR):
        logger.info("[%s] %s: %s", event.event_type, event.tool_name, event.message)
    elif event.event_type in (EventType.ITERATION_START, EventType.AGENT_COMPLETE):
        logger.info("[%s] %s", event.event_type, event.message)


async def _start_platform_service(platform_filter: str | None = None) -> None:
    """Start platform service with message processing."""
    config = get_config()

    if not config.platforms.enable:
        console.print("[red]Error: Platforms are not enabled in configuration[/red]")
        console.print("[dim]Set platforms.enable: true in your config[/dim]")
        raise typer.Exit(1)

    all_adapters = _create_adapters(config)

    if not all_adapters:
        console.print(
            "[yellow]No platforms configured. Please configure at least one platform.[/yellow]"
        )
        console.print("[dim]See: inkarms platforms list[/dim]")
        raise typer.Exit(1)

    if platform_filter:
        all_adapters = [
            a for a in all_adapters if a.platform_type.value == platform_filter
        ]
        if not all_adapters:
            console.print(
                f"[red]Error: Platform '{platform_filter}' not configured or not enabled[/red]"
            )
            raise typer.Exit(1)

    # Create router with all dependencies injected
    router = MessageRouter(
        max_concurrent_tasks=config.platforms.max_concurrent_sessions,
        processor=MessageProcessor(
            event_callback=_platform_event_callback,
            tool_approval_callback=lambda _tool_call, _tool: True,
        ),
        session_mapper=get_session_mapper(),
        rate_limiter=get_rate_limiter(
            max_tokens=config.platforms.rate_limit_per_user,
            refill_rate=1.0,
            refill_interval=60.0,
        ),
    )

    for adapter in all_adapters:
        router.register_adapter(adapter)

    console.print("[bold green]Starting platform service...[/bold green]")
    await router.start()

    # Log adapter started events
    audit_logger = get_audit_logger()
    for adapter in all_adapters:
        mode = "polling"
        if adapter.platform_type == PlatformType.SLACK:
            mode = "socket"
        elif adapter.platform_type == PlatformType.DISCORD:
            mode = "gateway"
        audit_logger.log_platform_adapter_started(
            platform=adapter.platform_type.value,
            mode=mode,
        )

    console.print(
        f"[green]\u2713[/green] Platform service started with {len(all_adapters)} platform(s)"
    )
    for adapter in all_adapters:
        console.print(f"  [cyan]\u2022[/cyan] {adapter.platform_type.value}")

    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    # Keep running until interrupted
    try:
        while router.is_running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping platform service...[/yellow]")
        await router.stop()
        for adapter in all_adapters:
            audit_logger.log_platform_adapter_stopped(
                platform=adapter.platform_type.value,
            )
        console.print("[green]\u2713[/green] Platform service stopped")


@app.command()
def list() -> None:
    """List available platforms and their configuration status."""
    config = get_config()

    table = Table(title="Available Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Mode", style="dim")
    table.add_column("Configuration", style="dim")

    platforms_info = [
        ("telegram", "Telegram", config.platforms.telegram, "Long Polling"),
        ("slack", "Slack", config.platforms.slack, "Socket Mode"),
        ("discord", "Discord", config.platforms.discord, "Gateway WebSocket"),
        ("imessage", "iMessage", config.platforms.imessage, "Local (macOS)"),
        ("signal", "Signal", config.platforms.signal, "Local Daemon"),
        ("whatsapp", "WhatsApp", config.platforms.whatsapp, "Local"),
        ("teams", "Teams", config.platforms.teams, "WebSocket"),
        ("wechat", "WeChat", config.platforms.wechat, "Webhook"),
    ]

    for _key, name, platform_config, mode in platforms_info:
        if platform_config.enable:
            status = "[green]Enabled[/green]"
            bot_token_key = "bot_token" if hasattr(platform_config, "bot_token") else None
            if bot_token_key:
                token = getattr(platform_config, bot_token_key, "")
                config_status = (
                    "[green]\u2713 Configured[/green]"
                    if token
                    else "[yellow]\u26a0 Missing token[/yellow]"
                )
            else:
                config_status = "[dim]N/A[/dim]"
        else:
            status = "[dim]Disabled[/dim]"
            config_status = "[dim]Not enabled[/dim]"

        table.add_row(name, status, mode, config_status)

    console.print(table)

    if not config.platforms.enable:
        console.print("\n[yellow]\u26a0 Platforms are disabled globally[/yellow]")
        console.print("[dim]Set platforms.enable: true in your config to enable[/dim]")

    console.print("\n[dim]Configuration: ~/.inkarms/config.yaml[/dim]")
    console.print("[dim]To configure a platform:[/dim]")
    console.print("[dim]  1. Get bot token from the platform[/dim]")
    console.print("[dim]  2. Set in config or environment variable[/dim]")
    console.print("[dim]  3. Enable the platform[/dim]")


@app.command()
def start(
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            "-p",
            help="Start specific platform (e.g., telegram, slack, discord)",
        ),
    ] = None,
) -> None:
    """Start platform message service.

    Starts all enabled platforms or a specific platform if specified.
    Runs continuously until stopped with Ctrl+C.
    """
    try:
        asyncio.run(_start_platform_service(platform_filter=platform))
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stop(
    platform: Annotated[
        str | None,
        typer.Option(
            "--platform",
            "-p",
            help="Stop specific platform",
        ),
    ] = None,
) -> None:
    """Stop platform message service.

    Note: Currently platforms must be stopped with Ctrl+C.
    This command is a placeholder for future daemon support.
    """
    console.print("[yellow]Platforms are currently run in foreground mode.[/yellow]")
    console.print("[dim]Use Ctrl+C to stop the running service.[/dim]")
    console.print("[dim]Future: Support for background daemon mode[/dim]")


@app.command()
def status() -> None:
    """Show platform health status.

    Note: This shows configuration status.
    For runtime status, see the output of 'inkarms platforms start'.
    """
    config = get_config()

    if not config.platforms.enable:
        console.print("[yellow]Platforms are disabled[/yellow]")
        console.print("[dim]Set platforms.enable: true to enable[/dim]")
        return

    adapters = _create_adapters(config)

    if not adapters:
        console.print("[yellow]No platforms configured[/yellow]")
        console.print("[dim]See: inkarms platforms list[/dim]")
        return

    table = Table(title="Platform Status")
    table.add_column("Platform", style="cyan")
    table.add_column("Configuration", style="bold")
    table.add_column("Mode")

    for adapter in adapters:
        table.add_row(
            adapter.platform_type.value,
            "[green]\u2713 Ready[/green]",
            adapter.capabilities.markdown_flavor or "N/A",
        )

    console.print(table)
    console.print(f"\n[green]\u2713[/green] {len(adapters)} platform(s) configured and ready")
    console.print("[dim]Run 'inkarms platforms start' to begin[/dim]")
