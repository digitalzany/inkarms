"""
Main Typer application for inkarms CLI.

This module defines the root CLI application and registers all command groups.
"""

import logging
import typer

from typing import Annotated

from inkarms import __version__
from inkarms.cli.commands import (
    config,
    hub,
    memory,
    platforms,
    run,
    skill,
    status,
    tools,
)
from inkarms.cli.output import print_error, print_warning, print_info

# Create the main Typer app
app = typer.Typer(
    name="inkarms",
    help="Your local AI Agent with multi-provider support, skills, and TUI.",
    no_args_is_help=False,  # Allow running without args to launch UI
    invoke_without_command=True,  # Allow callback to run when no subcommand
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
)


def _setup_file_logging() -> None:
    """Attach a rotating file handler to the inkarms logger namespace."""
    from inkarms.storage.paths import get_inkarms_home

    log_dir = get_inkarms_home() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "cli.log"

    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=3)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )

    inkarms_log = logging.getLogger("inkarms")
    inkarms_log.setLevel(logging.DEBUG)
    inkarms_log.addHandler(handler)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        print_info(f"inkarms version [green]{__version__}[/green]")
        raise typer.Exit()


# noinspection PyUnusedLocal
@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
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
    config_profile: Annotated[
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
    ui_backend: Annotated[
        str | None,
        typer.Option(
            "--ui",
            help="UI backend: auto or rich.",
        ),
    ] = None,
) -> None:
    """
    [bold blue]inkarms[/bold blue] - AI Agent CLI Tool

    A powerful AI agent with multi-provider support, skills system,
    TUI interface, and secure execution sandbox.

    Run [bold]inkarms[/bold] without arguments to launch the interactive UI.
    Use [bold]inkarms --help[/bold] to see all commands.
    """
    _setup_file_logging()

    # If no subcommand is invoked, launch the UI
    if ctx.invoked_subcommand is None:
        _launch_ui(ui_backend)


# Register command groups
app.add_typer(run.app, name="run")
app.add_typer(config.app, name="config")
app.add_typer(skill.app, name="skill")
app.add_typer(tools.app, name="tools")
app.add_typer(memory.app, name="memory")
app.add_typer(status.app, name="status")
app.add_typer(platforms.app, name="platforms")
app.add_typer(hub.app, name="hub")


def _launch_ui(backend: str | None = None) -> None:
    """Launch the unified UI interface."""
    try:
        from inkarms.ui import get_ui_backend
        from inkarms.ui.protocol import UIConfig

        # Get config from app config if available
        ui_config = UIConfig()
        try:
            from inkarms.config import get_config
            app_config = get_config()
            ui_config = UIConfig(
                theme=app_config.ui.theme,
                show_status_bar=app_config.ui.show_status_bar,
                show_timestamps=app_config.ui.show_timestamps,
                max_messages_display=app_config.ui.max_messages_display,
                enable_mouse=app_config.ui.enable_mouse,
                enable_completion=app_config.ui.enable_completion,
            )
            if backend is None:
                backend = app_config.ui.backend

        except Exception:
            pass  # Use defaults if config not available

        # Get and run the UI backend
        backend_type = backend or "auto"
        ui_backend = get_ui_backend(backend_type=backend_type, config=ui_config)  # type: ignore
        ui_backend.run()

    except ImportError as e:
        print_error(f"Failed to load UI: {e}")
        print_warning("Try to reinstall dependencies")
        raise typer.Exit(1)

    except KeyboardInterrupt:
        pass  # Clean exit on Ctrl+C


@app.command()
def ui(
    backend: Annotated[
        str | None,
        typer.Option(
            "--backend",
            "-b",
            help="UI backend: auto or rich.",
        ),
    ] = None,
) -> None:
    """Launch the interactive UI (menu, chat, dashboard, sessions)."""
    _launch_ui(backend)


if __name__ == "__main__":
    app()
