"""
inkarms profile - Profile management commands.

Usage:
    inkarms profile list
    inkarms profile show dev
    inkarms profile create staging
    inkarms profile use dev
"""

from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="profile",
    help="Profile management.",
)

console = Console()


@app.command("list")
def list_profiles() -> None:
    """List all profiles."""
    console.print(
        "[yellow]Profile list not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )


@app.command()
def show(
    name: Annotated[
        str,
        typer.Argument(
            help="Profile name.",
        ),
    ],
) -> None:
    """Show profile details."""
    console.print(
        "[yellow]Profile show not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )


@app.command()
def create(
    name: Annotated[
        str,
        typer.Argument(
            help="Profile name.",
        ),
    ],
    from_profile: Annotated[
        str | None,
        typer.Option(
            "--from",
            help="Copy from existing profile.",
        ),
    ] = None,
) -> None:
    """Create a new profile."""
    console.print(
        "[yellow]Profile create not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )


@app.command()
def use(
    name: Annotated[
        str,
        typer.Argument(
            help="Profile name.",
        ),
    ],
    set_default: Annotated[
        bool,
        typer.Option(
            "--default",
            help="Set as default profile.",
        ),
    ] = False,
) -> None:
    """Switch to a profile."""
    console.print(
        "[yellow]Profile use not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )


@app.command()
def edit(
    name: Annotated[
        str,
        typer.Argument(
            help="Profile name.",
        ),
    ],
) -> None:
    """Edit a profile."""
    console.print(
        "[yellow]Profile edit not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )


@app.command()
def delete(
    name: Annotated[
        str,
        typer.Argument(
            help="Profile name.",
        ),
    ],
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation.",
        ),
    ] = False,
) -> None:
    """Delete a profile."""
    console.print(
        "[yellow]Profile delete not yet implemented. Coming in Phase 1, Milestone 1.2.[/yellow]"
    )
