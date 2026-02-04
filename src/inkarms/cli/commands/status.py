"""
inkarms status - Status and health monitoring commands.

Usage:
    inkarms status
    inkarms status health
    inkarms status tokens
    inkarms status cost
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
    watch: Annotated[
        bool,
        typer.Option(
            "--watch",
            "-w",
            help="Watch mode with live updates.",
        ),
    ] = False,
    interval: Annotated[
        int,
        typer.Option(
            "--interval",
            help="Update interval in seconds (for watch mode).",
        ),
    ] = 5,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON.",
        ),
    ] = False,
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


@app.command()
def tokens(
    today: Annotated[
        bool,
        typer.Option(
            "--today",
            help="Show today's usage only.",
        ),
    ] = False,
    by_model: Annotated[
        bool,
        typer.Option(
            "--by-model",
            help="Group by model.",
        ),
    ] = False,
) -> None:
    """Show token usage statistics."""
    # Show session usage from current provider manager
    try:
        from inkarms.providers import get_provider_manager

        manager = get_provider_manager()
        summary = manager.get_cost_summary()

        if not summary.by_model:
            console.print("[dim]No token usage in current session.[/dim]")
            console.print("[dim]Run some queries first with 'inkarms run'.[/dim]")
            return

        table = Table(title="Session Token Usage")
        table.add_column("Model", style="cyan")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        table.add_column("Requests", justify="right")
        table.add_column("Cost", justify="right", style="green")

        for model, usage in summary.by_model.items():
            table.add_row(
                model,
                f"{usage.input_tokens:,}",
                f"{usage.output_tokens:,}",
                str(usage.request_count),
                f"${usage.total_cost:.4f}",
            )

        # Total row
        table.add_row(
            "[bold]Total[/bold]",
            f"[bold]{summary.total_input_tokens:,}[/bold]",
            f"[bold]{summary.total_output_tokens:,}[/bold]",
            "[bold]-[/bold]",
            f"[bold]${summary.total_cost:.4f}[/bold]",
        )

        console.print(table)

        if today:
            console.print(
                "\n[yellow]Note: Historical usage tracking not yet implemented. "
                "Showing session only.[/yellow]"
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print(
            "[yellow]Token stats persistence not yet implemented. "
            "Coming in Phase 1, Milestone 1.5.[/yellow]"
        )


@app.command()
def cost(
    month: Annotated[
        bool,
        typer.Option(
            "--month",
            help="Show monthly cost.",
        ),
    ] = False,
    by_model: Annotated[
        bool,
        typer.Option(
            "--by-model",
            help="Group by model.",
        ),
    ] = False,
) -> None:
    """Show cost tracking information."""
    # For now, just show session costs
    try:
        from inkarms.providers import get_provider_manager

        manager = get_provider_manager()
        summary = manager.get_cost_summary()

        console.print("[bold]Session Cost Summary[/bold]\n")
        console.print(f"  Total cost: [green]${summary.total_cost:.4f}[/green]")
        console.print(
            f"  Total tokens: {summary.total_input_tokens + summary.total_output_tokens:,}"
        )

        if by_model and summary.by_model:
            console.print("\n[bold]By Model:[/bold]")
            for model, usage in summary.by_model.items():
                console.print(f"  {model}: ${usage.total_cost:.4f}")

        if month:
            console.print(
                "\n[yellow]Note: Monthly cost tracking not yet implemented. "
                "Showing session only.[/yellow]"
            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print(
            "[yellow]Cost tracking persistence not yet implemented. Coming in Phase 1.[/yellow]"
        )


@app.command()
def context() -> None:
    """Show current context window usage."""
    console.print(
        "[yellow]Context status not yet implemented. Coming in Phase 1, Milestone 1.5.[/yellow]"
    )
