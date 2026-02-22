"""
inkarms status - Status and health monitoring commands.

Usage:
    inkarms status
    inkarms status health
"""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from inkarms.providers import HealthStatus

app = typer.Typer(
    name="status",
    help="Status and health monitoring.",
    invoke_without_command=True,
)

console = Console()


@app.callback(invoke_without_command=True)
def status_overview(
    ctx: typer.Context,
) -> None:
    """Show overall status."""
    if ctx.invoked_subcommand is None:
        # Show a quick summary
        try:
            from inkarms.config import get_config
            from inkarms.providers import get_provider_manager

            config = get_config()
            console.print("[bold]InkArms Status[/bold]\n")
            console.print(f"  [dim]Default model:[/dim] {config.providers.default}")
            console.print(
                f"  [dim]Fallback chain:[/dim] {len(config.providers.fallback)} providers"
            )
            console.print(
                f"  [dim]Sandbox:[/dim] {'enabled' if config.is_sandbox_enabled() else 'disabled'}"
            )

            # Quick health check on default
            console.print("\n[dim]Run 'inkarms status health' for provider health check[/dim]")

        except Exception as e:
            console.print(f"[red]Error getting status: {e}[/red]")


@app.command()
def health(
    provider: Annotated[
        str | None,
        typer.Argument(
            help="Provider to check.",
        ),
    ] = None,
    all_providers: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Check all configured providers.",
        ),
    ] = False,
) -> None:
    """Check provider health status."""
    asyncio.run(_health_check(provider, all_providers))


async def _health_check(provider: str | None, all_providers: bool) -> None:
    """Run health check asynchronously."""
    from inkarms.providers import get_provider_manager

    try:
        manager = get_provider_manager()
    except Exception as e:
        console.print(f"[red]Failed to initialize provider manager: {e}[/red]")
        raise typer.Exit(1)

    console.print("[dim]Checking provider health...[/dim]\n")

    try:
        if provider:
            results = await manager.health_check(provider)
        elif all_providers:
            results = await manager.health_check()
        else:
            # Just check the default provider
            results = await manager.health_check(manager.get_current_model())

        # Display results
        table = Table(title="Provider Health")
        table.add_column("Provider", style="cyan")
        table.add_column("Status")
        table.add_column("Latency")
        table.add_column("Error")

        for provider_name, health in results.items():
            # Status with color
            if health.status == HealthStatus.HEALTHY:
                status = "[green]healthy[/green]"
            elif health.status == HealthStatus.DEGRADED:
                status = "[yellow]degraded[/yellow]"
            else:
                status = "[red]unhealthy[/red]"

            # Latency
            latency = f"{health.latency_ms:.0f}ms" if health.latency_ms else "-"

            # Error
            error = health.error or "-"

            table.add_row(provider_name, status, latency, error)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Health check failed: {e}[/red]")
        raise typer.Exit(1)
