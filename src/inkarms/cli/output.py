"""
Output formatting utilities for the CLI.

Provides consistent output formatting across all CLI commands.
"""

from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class OutputFormat(Enum):
    """Output format options."""

    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"


# Global console instance
console = Console()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]i[/blue] {message}")


def print_panel(content: str, title: str | None = None) -> None:
    """Print content in a panel."""
    console.print(Panel(content, title=title))


def print_table(
    headers: list[str],
    rows: list[list[Any]],
    title: str | None = None,
) -> None:
    """Print a table."""
    table = Table(title=title)

    for header in headers:
        table.add_column(header)

    for row in rows:
        table.add_row(*[str(cell) for cell in row])

    console.print(table)
