"""
inkarms audit - Audit log access commands.

Usage:
    inkarms audit tail
    inkarms audit search --type request_complete
    inkarms audit stats tokens
    inkarms audit export --format json
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="audit",
    help="Audit log access.",
)

console = Console()


@app.command()
def tail(
    lines: Annotated[
        int,
        typer.Option(
            "--lines",
            "-n",
            help="Number of lines to show.",
        ),
    ] = 20,
) -> None:
    """View recent audit events."""
    console.print(
        "[yellow]Audit tail not yet implemented. Coming in Phase 1, Milestone 1.6.[/yellow]"
    )


@app.command()
def search(
    event_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Filter by event type.",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Start time (e.g., '24h', '7d', '2026-02-01').",
        ),
    ] = None,
    until: Annotated[
        str | None,
        typer.Option(
            "--until",
            help="End time.",
        ),
    ] = None,
    severity: Annotated[
        str | None,
        typer.Option(
            "--severity",
            help="Minimum severity level.",
        ),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session",
            help="Filter by session ID.",
        ),
    ] = None,
    contains: Annotated[
        str | None,
        typer.Option(
            "--contains",
            help="Text search in event data.",
        ),
    ] = None,
) -> None:
    """Search audit events."""
    console.print(
        "[yellow]Audit search not yet implemented. Coming in Phase 1, Milestone 1.6.[/yellow]"
    )


@app.command()
def stats(
    metric: Annotated[
        str,
        typer.Argument(
            help="Metric to show: tokens, cost, requests.",
        ),
    ],
    today: Annotated[
        bool,
        typer.Option(
            "--today",
            help="Show today only.",
        ),
    ] = False,
    week: Annotated[
        bool,
        typer.Option(
            "--week",
            help="Show last 7 days.",
        ),
    ] = False,
    month: Annotated[
        bool,
        typer.Option(
            "--month",
            help="Show last 30 days.",
        ),
    ] = False,
) -> None:
    """Show audit statistics."""
    console.print(
        "[yellow]Audit stats not yet implemented. Coming in Phase 1, Milestone 1.6.[/yellow]"
    )


@app.command()
def export(
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Export format: json, jsonl, csv, markdown.",
        ),
    ] = "json",
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output file path.",
        ),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option(
            "--since",
            help="Start time.",
        ),
    ] = None,
    event_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            help="Filter by event type.",
        ),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option(
            "--session",
            help="Filter by session ID.",
        ),
    ] = None,
) -> None:
    """Export audit log."""
    console.print(
        "[yellow]Audit export not yet implemented. Coming in Phase 1, Milestone 1.6.[/yellow]"
    )
