"""
Main Typer application for inkarms CLI.

This module defines the root CLI application and registers all command groups.
"""

from typing import Annotated

import typer
from rich.console import Console

from inkarms import __version__
from inkarms.cli.commands import audit, config, memory, platforms, profile, run, skill, status, tools

# Create the main Typer app
app = typer.Typer(
    name="inkarms",
    help="Your local AI Agent with multi-provider support, skills, and TUI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)

# Rich console for output
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"[bold blue]inkarms[/bold blue] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose output.",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Minimal output.",
        ),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Use specific config profile.",
        ),
    ] = None,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="Disable colored output.",
        ),
    ] = False,
) -> None:
    """
    [bold blue]inkarms[/bold blue] - AI Agent CLI Tool

    A powerful AI agent with multi-provider support, skills system,
    TUI interface, and secure execution sandbox.

    Use [bold]inkarms --help[/bold] to see all commands.
    """
    # Store global options in context for subcommands
    # This will be implemented when we add the config system
    pass


# Register command groups
app.add_typer(run.app, name="run")
app.add_typer(config.app, name="config")
app.add_typer(skill.app, name="skill")
app.add_typer(tools.app, name="tools")
app.add_typer(memory.app, name="memory")
app.add_typer(status.app, name="status")
app.add_typer(audit.app, name="audit")
app.add_typer(profile.app, name="profile")
app.add_typer(platforms.app, name="platforms")


@app.command()
def chat(
    session_id: Annotated[
        str,
        typer.Option(
            "--session",
            "-s",
            help="Session ID for conversation tracking.",
        ),
    ] = "default",
) -> None:
    """Launch the interactive chat interface (TUI)."""
    from inkarms.tui.app import run_chat_interface

    run_chat_interface(session_id=session_id)


@app.command()
def interactive() -> None:
    """Start an interactive CLI session (REPL mode)."""
    console.print(
        "[yellow]Interactive mode not yet implemented. Coming in Phase 1.[/yellow]"
    )
    raise typer.Exit(1)


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
