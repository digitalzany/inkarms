"""
inkarms tools - Manage and test tools.

Usage:
    inkarms tools list
    inkarms tools test <tool-name>
    inkarms tools info <tool-name>
    inkarms tools metrics
"""

import asyncio
from datetime import datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from inkarms.config import get_config
from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.metrics import get_metrics_tracker
from inkarms.tools.registry import ToolRegistry

app = typer.Typer(
    name="tools",
    help="Manage and test tools for the AI agent.",
)

console = Console()


@app.command("list")
def list_tools(
    show_all: Annotated[
        bool,
        typer.Option(
            "--all",
            "-a",
            help="Show all tools including blocked ones.",
        ),
    ] = False,
) -> None:
    """List all available tools."""
    # Setup registry
    registry = ToolRegistry()
    config = get_config()
    sandbox = SandboxExecutor.from_config(config.security)
    register_builtin_tools(registry, sandbox)

    # Get tools
    all_tools = registry.list_tools()

    if not all_tools:
        console.print("[yellow]No tools registered.[/yellow]")
        return

    # Filter by configuration if not showing all
    if not show_all and config.agent.allowed_tools:
        all_tools = [t for t in all_tools if t.name in config.agent.allowed_tools]

    if not show_all and config.agent.blocked_tools:
        all_tools = [t for t in all_tools if t.name not in config.agent.blocked_tools]

    # Create table
    table = Table(title="Available Tools")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Type", style="magenta")
    table.add_column("Description")

    for tool in all_tools:
        tool_type = "⚠️  Dangerous" if tool.is_dangerous else "✓ Safe"
        desc = tool.description[:80] + "..." if len(tool.description) > 80 else tool.description
        table.add_row(tool.name, tool_type, desc)

    console.print(table)
    console.print(f"\n[dim]Total: {len(all_tools)} tool(s)[/dim]")


@app.command("info")
def tool_info(
    tool_name: Annotated[
        str,
        typer.Argument(help="Tool name to get info about"),
    ],
) -> None:
    """Show detailed information about a tool."""
    # Setup registry
    registry = ToolRegistry()
    config = get_config()
    sandbox = SandboxExecutor.from_config(config.security)
    register_builtin_tools(registry, sandbox)

    # Get tool
    tool = registry.get(tool_name)

    if not tool:
        console.print(f"[red]Error:[/red] Tool not found: {tool_name}")
        available = registry.list_tool_names()
        console.print(f"\n[dim]Available tools: {', '.join(available)}[/dim]")
        raise typer.Exit(1)

    # Display info
    console.print(f"\n[bold cyan]{tool.name}[/bold cyan]")
    console.print(f"Type: {'⚠️  Dangerous' if tool.is_dangerous else '✓ Safe'}")
    console.print(f"\n[bold]Description:[/bold]\n{tool.description}")

    # Show parameters
    if tool.parameters:
        console.print(f"\n[bold]Parameters:[/bold]")
        for param in tool.parameters:
            required = "[red]*[/red]" if param.required else ""
            default = f" (default: {param.default})" if param.default is not None else ""
            console.print(f"  • {param.name}{required}: {param.type}{default}")
            console.print(f"    {param.description}")

    # Show JSON schema
    console.print(f"\n[bold]Input Schema:[/bold]")
    schema = tool.get_input_schema()
    import json
    console.print_json(json.dumps(schema, indent=2))


@app.command("test")
def test_tool(
    tool_name: Annotated[
        str,
        typer.Argument(help="Tool name to test"),
    ],
    params: Annotated[
        str | None,
        typer.Option(
            "--params",
            "-p",
            help="Tool parameters as JSON",
        ),
    ] = None,
) -> None:
    """Test a tool with given parameters."""
    # Setup registry
    registry = ToolRegistry()
    config = get_config()
    sandbox = SandboxExecutor.from_config(config.security)
    register_builtin_tools(registry, sandbox)

    # Get tool
    tool = registry.get(tool_name)

    if not tool:
        console.print(f"[red]Error:[/red] Tool not found: {tool_name}")
        raise typer.Exit(1)

    # Parse parameters
    import json

    tool_params = {}
    if params:
        try:
            tool_params = json.loads(params)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error:[/red] Invalid JSON: {e}")
            raise typer.Exit(1)

    # Validate parameters
    try:
        tool.validate_input(**tool_params)
    except ValueError as e:
        console.print(f"[red]Validation Error:[/red] {e}")
        console.print(f"\n[dim]Run 'inkarms tools info {tool_name}' to see parameters[/dim]")
        raise typer.Exit(1)

    # Confirm if dangerous
    if tool.is_dangerous:
        console.print(f"[yellow]Warning:[/yellow] {tool_name} is a dangerous tool")
        console.print(f"Parameters: {tool_params}")
        if not typer.confirm("Continue?"):
            console.print("Cancelled.")
            raise typer.Exit(0)

    # Execute tool
    console.print(f"\n[dim]Executing {tool_name}...[/dim]\n")

    async def run_tool():
        result = await tool.execute(tool_call_id="test", **tool_params)
        return result

    try:
        result = asyncio.run(run_tool())

        if result.is_error:
            console.print(f"[red]Tool Error:[/red]")
            console.print(f"Error: {result.error}")
            if result.exit_code is not None:
                console.print(f"Exit Code: {result.exit_code}")
        else:
            console.print(f"[green]Success![/green]")
            if result.exit_code is not None:
                console.print(f"Exit Code: {result.exit_code}")

        console.print(f"\n[bold]Output:[/bold]")
        console.print(result.output)

    except Exception as e:
        console.print(f"[red]Execution Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("metrics")
def show_metrics(
    tool_name: Annotated[
        str | None,
        typer.Argument(help="Show metrics for specific tool (optional)"),
    ] = None,
    clear: Annotated[
        bool,
        typer.Option(
            "--clear",
            help="Clear all metrics",
        ),
    ] = False,
) -> None:
    """Show tool usage metrics and statistics."""
    metrics = get_metrics_tracker()

    if clear:
        if typer.confirm("Are you sure you want to clear all metrics?"):
            metrics.clear_metrics()
            console.print("[green]Metrics cleared.[/green]")
        return

    # Show metrics for specific tool
    if tool_name:
        stats = metrics.get_tool_stats(tool_name)
        if not stats:
            console.print(f"[yellow]No metrics found for tool: {tool_name}[/yellow]")
            return

        console.print(f"\n[bold cyan]{stats.tool_name}[/bold cyan]\n")
        console.print(f"Total Executions: {stats.total_executions}")
        console.print(f"Successful: {stats.successful_executions} ({stats.success_rate * 100:.1f}%)")
        console.print(f"Failed: {stats.failed_executions}")
        console.print(f"Average Execution Time: {stats.average_execution_time:.3f}s")
        console.print(f"Total Time: {stats.total_execution_time:.3f}s")

        last_used = datetime.fromtimestamp(stats.last_used)
        console.print(f"Last Used: {last_used.strftime('%Y-%m-%d %H:%M:%S')}")

        return

    # Show overall metrics
    total = metrics.get_total_executions()
    if total == 0:
        console.print("[yellow]No tool execution metrics recorded yet.[/yellow]")
        return

    success_rate = metrics.get_success_rate()

    console.print("\n[bold]Tool Usage Metrics[/bold]\n")
    console.print(f"Total Executions: {total}")
    console.print(f"Overall Success Rate: {success_rate * 100:.1f}%\n")

    # Most used tools
    console.print("[bold]Most Used Tools:[/bold]")
    most_used = metrics.get_most_used_tools(limit=10)
    for i, (tool_name, count) in enumerate(most_used, 1):
        console.print(f"  {i}. {tool_name}: {count} times")

    # All tool stats table
    console.print("\n[bold]All Tools:[/bold]\n")
    table = Table(title="Tool Statistics")
    table.add_column("Tool", style="cyan")
    table.add_column("Executions", justify="right")
    table.add_column("Success Rate", justify="right")
    table.add_column("Avg Time", justify="right")

    all_stats = metrics.get_all_stats()
    for stats in all_stats:
        table.add_row(
            stats.tool_name,
            str(stats.total_executions),
            f"{stats.success_rate * 100:.1f}%",
            f"{stats.average_execution_time:.3f}s",
        )

    console.print(table)

    # Recent executions
    console.print("\n[bold]Recent Executions:[/bold]\n")
    recent = metrics.get_recent_executions(limit=5)
    for exec in recent:
        timestamp = datetime.fromtimestamp(exec.timestamp)
        status = "✓" if exec.success else "✗"
        status_color = "green" if exec.success else "red"
        console.print(
            f"[{status_color}]{status}[/{status_color}] "
            f"{exec.tool_name} - {exec.execution_time:.3f}s "
            f"({timestamp.strftime('%H:%M:%S')})"
        )


if __name__ == "__main__":
    app()
