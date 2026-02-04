"""
inkarms platforms - Manage multi-platform messaging.

Usage:
    inkarms platforms list
    inkarms platforms start [--platform PLATFORM]
    inkarms platforms stop [--platform PLATFORM]
    inkarms platforms status
"""

import asyncio
import sys
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from inkarms.audit import get_audit_logger
from inkarms.config import get_config
from inkarms.platforms.models import OutgoingMessage, PlatformType
from inkarms.platforms.protocol import PlatformAdapter
from inkarms.platforms.router import MessageRouter
from inkarms.platforms.processor import MessageProcessor
from inkarms.platforms.session_mapper import get_session_mapper
from inkarms.platforms.rate_limiter import get_rate_limiter

app = typer.Typer(
    name="platforms",
    help="Manage multi-platform messaging adapters.",
)

console = Console()

# Global router instance (will be created when starting platforms)
_router: Optional[MessageRouter] = None


def _get_config_value(config_dict: dict, key: str, env_var: str) -> Optional[str]:
    """Get config value, checking environment variable if not set.

    Args:
        config_dict: Configuration dictionary
        key: Key to look up
        env_var: Environment variable name

    Returns:
        Config value or None
    """
    import os

    value = config_dict.get(key)
    if value and value.startswith("${") and value.endswith("}"):
        # Extract env var name
        env_name = value[2:-1]
        return os.getenv(env_name)
    return value


def _create_adapters(config) -> list[PlatformAdapter]:
    """Create platform adapters based on configuration.

    Args:
        config: InkArms configuration

    Returns:
        List of enabled platform adapters
    """
    adapters: list[PlatformAdapter] = []

    # Telegram
    if config.platforms.telegram.enable:
        bot_token = _get_config_value(
            config.platforms.telegram.model_dump(), "bot_token", "TELEGRAM_BOT_TOKEN"
        )
        if bot_token:
            try:
                from inkarms.platforms.adapters.telegram import TelegramAdapter
                adapter = TelegramAdapter(
                    bot_token=bot_token,
                    allowed_users=config.platforms.telegram.allowed_users,
                    parse_mode=config.platforms.telegram.parse_mode,
                    polling_interval=config.platforms.telegram.polling_interval,
                )
                adapters.append(adapter)
            except ImportError as e:
                console.print(
                    f"[yellow]Warning: Telegram adapter not available: {e}[/yellow]"
                )
                console.print("[dim]Install with: pip install python-telegram-bot[/dim]")
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
            try:
                from inkarms.platforms.adapters.slack import SlackAdapter
                adapter = SlackAdapter(
                    bot_token=bot_token,
                    app_token=app_token,
                    allowed_channels=config.platforms.slack.allowed_channels,
                )
                adapters.append(adapter)
            except ImportError as e:
                console.print(
                    f"[yellow]Warning: Slack adapter not available: {e}[/yellow]"
                )
                console.print("[dim]Install with: pip install slack-sdk[/dim]")
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
            try:
                from inkarms.platforms.adapters.discord import DiscordAdapter
                adapter = DiscordAdapter(
                    bot_token=bot_token,
                    allowed_guilds=config.platforms.discord.allowed_guilds,
                    allowed_channels=config.platforms.discord.allowed_channels,
                    command_prefix=config.platforms.discord.command_prefix,
                )
                adapters.append(adapter)
            except ImportError as e:
                console.print(
                    f"[yellow]Warning: Discord adapter not available: {e}[/yellow]"
                )
                console.print("[dim]Install with: pip install discord.py[/dim]")
        else:
            console.print(
                "[yellow]Warning: Discord enabled but bot_token not configured[/yellow]"
            )

    return adapters


async def _start_platform_service(platform_filter: Optional[str] = None) -> None:
    """Start platform service with message processing.

    Args:
        platform_filter: Optional platform name to start (None = all)
    """
    global _router

    config = get_config()

    # Check if platforms are enabled
    if not config.platforms.enable:
        console.print("[red]Error: Platforms are not enabled in configuration[/red]")
        console.print("[dim]Set platforms.enable: true in your config[/dim]")
        raise typer.Exit(1)

    # Create adapters
    all_adapters = _create_adapters(config)

    if not all_adapters:
        console.print("[yellow]No platforms configured. Please configure at least one platform.[/yellow]")
        console.print("[dim]See: inkarms platforms list[/dim]")
        raise typer.Exit(1)

    # Filter adapters if specific platform requested
    if platform_filter:
        all_adapters = [
            a for a in all_adapters if a.platform_type.value == platform_filter
        ]
        if not all_adapters:
            console.print(f"[red]Error: Platform '{platform_filter}' not configured or not enabled[/red]")
            raise typer.Exit(1)

    # Create router
    _router = MessageRouter(max_concurrent_tasks=config.platforms.max_concurrent_sessions)

    # Initialize rate limiter
    rate_limiter = get_rate_limiter(
        max_tokens=config.platforms.rate_limit_per_user,
        refill_rate=1.0,
        refill_interval=60.0,
    )

    # Register adapters
    for adapter in all_adapters:
        _router.register_adapter(adapter)

    # Start router
    console.print("[bold green]Starting platform service...[/bold green]")
    await _router.start()

    # Create message processor
    processor = MessageProcessor()

    # Get session mapper
    session_mapper = get_session_mapper()

    # Get audit logger
    audit_logger = get_audit_logger()

    # Log adapter started events
    for adapter in all_adapters:
        mode = "polling"
        if hasattr(adapter, '_mode'):
            mode = adapter._mode  # Platform-specific mode
        elif adapter.platform_type == PlatformType.SLACK:
            mode = "socket"
        elif adapter.platform_type == PlatformType.DISCORD:
            mode = "gateway"
        audit_logger.log_platform_adapter_started(
            platform=adapter.platform_type.value,
            mode=mode,
        )

    # Display status
    console.print(f"[green]✓[/green] Platform service started with {len(all_adapters)} platform(s)")
    for adapter in all_adapters:
        console.print(f"  [cyan]•[/cyan] {adapter.platform_type.value}")

    console.print("\n[dim]Press Ctrl+C to stop[/dim]\n")

    # Process messages from all platforms
    try:
        # Create tasks for each adapter
        tasks = []
        for adapter in all_adapters:
            task = asyncio.create_task(_process_adapter_messages(adapter, processor, session_mapper, rate_limiter))
            tasks.append(task)

        # Wait for all tasks
        await asyncio.gather(*tasks)

    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping platform service...[/yellow]")
        await _router.stop()
        # Log adapter stopped events
        for adapter in all_adapters:
            audit_logger.log_platform_adapter_stopped(
                platform=adapter.platform_type.value,
            )
        console.print("[green]✓[/green] Platform service stopped")


async def _process_adapter_messages(
    adapter: PlatformAdapter,
    processor: MessageProcessor,
    session_mapper,
    rate_limiter,
) -> None:
    """Process messages from a specific adapter.

    Args:
        adapter: Platform adapter
        processor: Message processor
        session_mapper: Session mapper
        rate_limiter: Rate limiter
    """
    platform_name = adapter.platform_type.value
    audit_logger = get_audit_logger()

    try:
        async for message in adapter.receive_messages():
            console.print(
                f"[cyan]{platform_name}[/cyan] | [bold]{message.user.username or message.user.platform_user_id}:[/bold] {message.content[:50]}..."
            )

            # Get or create session for this user
            session_id = session_mapper.get_session_id(message.user, create_if_missing=True)

            # Check rate limit
            try:
                await rate_limiter.check_limit(message.user)
            except Exception as e:
                console.print(f"[yellow]Rate limit exceeded for {message.user}[/yellow]")
                # Log rate limit event
                retry_after = 60.0  # Default retry time
                audit_logger.log_platform_rate_limited(
                    platform=platform_name,
                    user_id=message.user.platform_user_id,
                    retry_after=retry_after,
                )
                await adapter.send_message(
                    message.metadata.get("channel_id", message.user.platform_user_id),
                    OutgoingMessage(
                        content=f"Rate limit exceeded. Please wait a moment before sending more messages.",
                        format="plain",
                    ),
                )
                continue

            # Send typing indicator if supported
            if adapter.capabilities.supports_typing_indicator:
                await adapter.send_typing_indicator(
                    message.metadata.get("channel_id", message.user.platform_user_id)
                )

            # Process message
            try:
                if adapter.capabilities.supports_streaming:
                    # Streaming response
                    channel_id = message.metadata.get("channel_id", message.user.platform_user_id)
                    message_id = None

                    async for chunk in processor.process_streaming(
                        query=message.content,
                        session_id=session_id,
                        platform=message.platform,
                        platform_user_id=message.user.platform_user_id,
                        platform_username=message.user.username,
                    ):
                        message_id = await adapter.send_streaming_chunk(
                            channel_id,
                            chunk,
                            message_id,
                        )
                else:
                    # Non-streaming response
                    response = await processor.process(
                        query=message.content,
                        session_id=session_id,
                        platform=message.platform,
                        platform_user_id=message.user.platform_user_id,
                        platform_username=message.user.username,
                    )

                    if response.error:
                        console.print(f"[red]Error processing message: {response.error}[/red]")
                        await adapter.send_message(
                            message.metadata.get("channel_id", message.user.platform_user_id),
                            OutgoingMessage(
                                content=f"Error: {response.error}",
                                format="plain",
                            ),
                        )
                    else:
                        await adapter.send_message(
                            message.metadata.get("channel_id", message.user.platform_user_id),
                            OutgoingMessage(
                                content=response.content,
                                format="markdown",
                            ),
                        )

            except Exception as e:
                console.print(f"[red]Error processing message: {e}[/red]")
                audit_logger.log_platform_adapter_error(
                    platform=platform_name,
                    error=str(e),
                )
                import traceback
                traceback.print_exc()

    except Exception as e:
        console.print(f"[red]Error in {platform_name} adapter: {e}[/red]")
        audit_logger.log_platform_adapter_error(
            platform=platform_name,
            error=str(e),
        )


@app.command()
def list() -> None:
    """List available platforms and their configuration status."""
    config = get_config()

    table = Table(title="Available Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Mode", style="dim")
    table.add_column("Configuration", style="dim")

    # Define all platforms
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

    for key, name, platform_config, mode in platforms_info:
        if platform_config.enable:
            status = "[green]Enabled[/green]"
            # Check if configured
            bot_token_key = "bot_token" if hasattr(platform_config, "bot_token") else None
            if bot_token_key:
                token = getattr(platform_config, bot_token_key, "")
                config_status = "[green]✓ Configured[/green]" if token else "[yellow]⚠ Missing token[/yellow]"
            else:
                config_status = "[dim]N/A[/dim]"
        else:
            status = "[dim]Disabled[/dim]"
            config_status = "[dim]Not enabled[/dim]"

        table.add_row(name, status, mode, config_status)

    console.print(table)

    if not config.platforms.enable:
        console.print("\n[yellow]⚠ Platforms are disabled globally[/yellow]")
        console.print("[dim]Set platforms.enable: true in your config to enable[/dim]")

    console.print("\n[dim]Configuration: ~/.inkarms/config.yaml[/dim]")
    console.print("[dim]To configure a platform:[/dim]")
    console.print("[dim]  1. Get bot token from the platform[/dim]")
    console.print("[dim]  2. Set in config or environment variable[/dim]")
    console.print("[dim]  3. Enable the platform[/dim]")


@app.command()
def start(
    platform: Annotated[
        Optional[str],
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
        Optional[str],
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

    # Create adapters to check configuration
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
            "[green]✓ Ready[/green]",
            adapter.capabilities.markdown_flavor or "N/A",
        )

    console.print(table)
    console.print(f"\n[green]✓[/green] {len(adapters)} platform(s) configured and ready")
    console.print("[dim]Run 'inkarms platforms start' to begin[/dim]")
