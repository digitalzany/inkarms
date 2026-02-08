"""
inkarms config - Configuration management commands.

Usage:
    inkarms config show
    inkarms config show providers
    inkarms config set providers.default "openai/gpt-4"
    inkarms config edit
    inkarms config validate
    inkarms config init
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from inkarms.config import (
    Config,
    ConfigurationError,
    get_config_sources,
    load_config,
    load_yaml_file,
    save_yaml_file,
    set_nested_value,
)
from inkarms.config.setup import (
    create_profile,
    create_project_config,
    is_initialized,
    run_setup,
)
from inkarms.storage.paths import (
    find_project_config,
    get_global_config_path,
    get_profile_path,
)

app = typer.Typer(
    name="config",
    help="Configuration management.",
)

console = Console()


def _parse_value(value: str) -> Any:
    """
    Parse a string value to the appropriate Python type.

    Args:
        value: String value to parse.

    Returns:
        Parsed value (bool, int, float, list, or string).
    """
    # Boolean
    if value.lower() in ("true", "yes", "1", "on"):
        return True
    if value.lower() in ("false", "no", "0", "off"):
        return False

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # JSON (for arrays and objects)
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

    # String
    return value


@app.command()
def show(
    section: Annotated[
        str | None,
        typer.Argument(
            help="Config section to show (e.g., 'providers', 'security.whitelist').",
        ),
    ] = None,
    yaml_output: Annotated[
        bool,
        typer.Option(
            "--yaml",
            help="Output as YAML.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON.",
        ),
    ] = False,
    effective: Annotated[
        bool,
        typer.Option(
            "--effective",
            help="Show effective (merged) configuration.",
        ),
    ] = True,
    sources: Annotated[
        bool,
        typer.Option(
            "--sources",
            help="Show configuration source files.",
        ),
    ] = False,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Profile to use.",
        ),
    ] = None,
) -> None:
    """Show configuration values."""
    # Show sources if requested
    if sources:
        config_sources = get_config_sources()
        table = Table(title="Configuration Sources")
        table.add_column("Source", style="cyan")
        table.add_column("Path", style="green")
        table.add_column("Status")

        for source_name, source_path in config_sources.items():
            if source_path:
                table.add_row(source_name, str(source_path), "[green]loaded[/green]")
            else:
                table.add_row(source_name, "-", "[dim]not found[/dim]")

        console.print(table)
        return

    try:
        # Load configuration
        config = load_config(profile=profile)
        config_dict = config.model_dump()

        # Get specific section if requested
        if section:
            # value = get_nested_value(config_dict, section)
            value = getattr(config, section, None)
            if value is None:
                console.print(f"[red]Section '{section}' not found in configuration.[/red]")
                raise typer.Exit(1)
            config_dict = value

        # Output format
        if json_output:
            output = json.dumps(config_dict, indent=2, default=str)
            console.print(Syntax(output, "json", theme="monokai"))
        elif yaml_output or not json_output:
            # YAML is default
            output = yaml.dump(
                config_dict,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            if section:
                console.print(
                    Panel(Syntax(output, "yaml", theme="monokai"), title=f"[cyan]{section}[/cyan]")
                )
            else:
                console.print(Syntax(output, "yaml", theme="monokai"))

    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)


@app.command("set")
def set_value(
    key: Annotated[
        str,
        typer.Argument(
            help="Configuration key (e.g., 'providers.default').",
        ),
    ],
    value: Annotated[
        str,
        typer.Argument(
            help="Value to set.",
        ),
    ],
    scope: Annotated[
        str,
        typer.Option(
            "--scope",
            "-s",
            help="Config scope: global, profile, or project.",
        ),
    ] = "global",
    profile_name: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Profile name (if scope is 'profile').",
        ),
    ] = None,
) -> None:
    """Set a configuration value."""
    # Determine which config file to modify
    if scope == "global":
        config_path = get_global_config_path()
    elif scope == "profile":
        if not profile_name:
            console.print("[red]Profile name required with --profile option.[/red]")
            raise typer.Exit(1)
        config_path = get_profile_path(profile_name)
    elif scope == "project":
        config_path = find_project_config()
        if not config_path:
            console.print(
                "[red]No project configuration found. Run 'inkarms config init --project' first.[/red]"
            )
            raise typer.Exit(1)
    else:
        console.print(f"[red]Invalid scope: {scope}. Use 'global', 'profile', or 'project'.[/red]")
        raise typer.Exit(1)

    # Load existing config or create empty
    try:
        config_dict = load_yaml_file(config_path)
    except ConfigurationError:
        config_dict = {}

    # Parse and set value
    parsed_value = _parse_value(value)
    config_dict = set_nested_value(config_dict, key, parsed_value)

    # Save config
    try:
        save_yaml_file(config_path, config_dict)
        console.print(f"[green]Set {key} = {parsed_value!r} in {scope} config[/green]")
        console.print(f"[dim]File: {config_path}[/dim]")
    except ConfigurationError as e:
        console.print(f"[red]Failed to save configuration: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def edit(
    profile_name: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Edit specific profile.",
        ),
    ] = None,
    project: Annotated[
        bool,
        typer.Option(
            "--project",
            help="Edit project config.",
        ),
    ] = False,
    editor: Annotated[
        str | None,
        typer.Option(
            "--editor",
            "-e",
            help="Editor to use.",
        ),
    ] = None,
) -> None:
    """Open configuration in editor."""
    # Determine which config file to edit
    if profile_name:
        config_path = get_profile_path(profile_name)
        if not config_path.exists():
            console.print(f"[red]Profile '{profile_name}' not found.[/red]")
            console.print("[dim]Create it with: inkarms config init --profile <name>[/dim]")
            raise typer.Exit(1)
    elif project:
        config_path = find_project_config()
        if not config_path:
            console.print("[red]No project configuration found.[/red]")
            console.print("[dim]Create it with: inkarms config init --project[/dim]")
            raise typer.Exit(1)
    else:
        config_path = get_global_config_path()
        if not config_path.exists():
            console.print("[yellow]Global config not found. Running setup first...[/yellow]")
            run_setup()

    # Determine editor
    editor_cmd = editor or os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

    try:
        subprocess.run([editor_cmd, str(config_path)], check=True)
        console.print(f"[green]Edited: {config_path}[/green]")

        # Validate after editing
        try:
            load_config()
            console.print("[green]Configuration is valid.[/green]")
        except ConfigurationError as e:
            console.print(f"[yellow]Warning: Configuration validation failed: {e}[/yellow]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Editor exited with error: {e}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print(f"[red]Editor not found: {editor_cmd}[/red]")
        console.print("[dim]Set the EDITOR environment variable or use --editor[/dim]")
        raise typer.Exit(1)


@app.command("set-secret")
def set_secret(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider name (e.g., 'openai', 'anthropic').",
        ),
    ],
    value: Annotated[
        str | None,
        typer.Option(
            "--value",
            help="API key value (will prompt if not provided).",
        ),
    ] = None,
) -> None:
    """Set an API key secret."""
    from inkarms.secrets import SecretsManager

    secrets = SecretsManager()

    # Get the value
    if value is None:
        # Prompt securely
        import getpass

        env_var = secrets.get_env_var_name(provider)
        console.print(f"[dim]This will be stored encrypted and loaded as {env_var}[/dim]")
        value = getpass.getpass(f"Enter API key for {provider}: ")

        if not value:
            console.print("[red]No value provided.[/red]")
            raise typer.Exit(1)

    # Store the secret
    try:
        secrets.set(provider, value)
        console.print(f"[green]Secret '{provider}' stored successfully.[/green]")
        console.print(f"[dim]File: {secrets.secrets_dir / f'{provider}.enc'}[/dim]")
    except Exception as e:
        console.print(f"[red]Failed to store secret: {e}[/red]")
        raise typer.Exit(1)


@app.command("list-secrets")
def list_secrets() -> None:
    """List configured secrets."""
    from rich.table import Table

    from inkarms.secrets import SecretsManager

    secrets = SecretsManager()
    secret_names = secrets.list()

    if not secret_names:
        console.print("[dim]No secrets configured.[/dim]")
        console.print("[dim]Use 'inkarms config set-secret <provider>' to add one.[/dim]")
        return

    table = Table(title="Stored Secrets")
    table.add_column("Provider", style="cyan")
    table.add_column("Environment Variable", style="green")
    table.add_column("Status")

    for name in secret_names:
        env_var = secrets.get_env_var_name(name)
        # Check if also set in environment
        import os

        if os.environ.get(env_var):
            status = "[yellow]env override[/yellow]"
        else:
            status = "[green]stored[/green]"
        table.add_row(name, env_var, status)

    console.print(table)


@app.command("delete-secret")
def delete_secret(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider name to delete.",
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
    """Delete a stored secret."""
    from inkarms.secrets import SecretsManager

    secrets = SecretsManager()

    if not secrets.exists(provider):
        console.print(f"[red]Secret '{provider}' not found.[/red]")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Delete secret '{provider}'?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    if secrets.delete(provider):
        console.print(f"[green]Secret '{provider}' deleted.[/green]")
    else:
        console.print(f"[red]Failed to delete secret '{provider}'.[/red]")
        raise typer.Exit(1)


@app.command("validate")
def validate(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Config file to validate.",
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Profile to validate.",
        ),
    ] = None,
) -> None:
    """Validate configuration."""
    try:
        if file:
            # Validate specific file
            console.print(f"Validating: {file}")
            config_dict = load_yaml_file(file)
            Config.model_validate(config_dict)
            console.print(f"[green]Valid: {file}[/green]")
        else:
            # Validate merged configuration
            console.print("Validating merged configuration...")

            # Show sources
            sources = get_config_sources()
            for source_name, source_path in sources.items():
                if source_path:
                    console.print(f"  [dim]{source_name}:[/dim] {source_path}")

            # Load and validate
            config = load_config(profile=profile)
            console.print("[green]Configuration is valid.[/green]")

            # Show summary
            console.print("\n[bold]Configuration summary:[/bold]")
            console.print(f"  Model: {config.providers.default}")
            console.print(f"  Sandbox: {'enabled' if config.is_sandbox_enabled() else 'disabled'}")
            console.print(f"  TUI: {'enabled' if config.tui.enable else 'disabled'}")

    except ConfigurationError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except ValidationError as e:
        console.print("[red]Validation failed:[/red]")
        for error in e.errors():
            loc = ".".join(str(x) for x in error["loc"])
            console.print(f"  [red]{loc}:[/red] {error['msg']}")
        raise typer.Exit(1)


@app.command("init")
def init(
    project: Annotated[
        bool,
        typer.Option(
            "--project",
            help="Initialize project configuration in current directory.",
        ),
    ] = False,
    profile_name: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help="Create a new profile.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force overwrite (only valid with --quick for automation).",
        ),
    ] = False,
    quick: Annotated[
        bool,
        typer.Option(
            "--quick",
            help="CLI inline wizard (instead of TUI).",
        ),
    ] = False,
) -> None:
    """Initialize InkArms configuration.

    By default, launches TUI wizard for guided setup.
    Use --quick for CLI inline wizard.
    Use --quick --force for non-interactive automation.
    """
    if project:
        # Initialize project config
        config_path = create_project_config(overwrite=force)
        if config_path:
            console.print(f"[green]Created project configuration: {config_path}[/green]")
            console.print("[dim]Edit .inkarms/project.yaml to customize project settings.[/dim]")
        else:
            console.print("[yellow]Project configuration already exists.[/yellow]")
            console.print("[dim]Use --force to overwrite.[/dim]")

    elif profile_name:
        # Create new profile
        profile_path = create_profile(profile_name, overwrite=force)
        if profile_path:
            console.print(f"[green]Created profile: {profile_path}[/green]")
            console.print(f"[dim]Use with: inkarms --profile {profile_name}[/dim]")
        else:
            console.print(f"[yellow]Profile '{profile_name}' already exists.[/yellow]")
            console.print("[dim]Use --force to overwrite.[/dim]")

    else:
        # Validate --force usage
        if force and not quick:
            console.print(
                "[red]Error:[/red] --force is only valid with --quick for automation.\n"
                "[dim]For interactive setup, use:[/dim] inkarms config init\n"
                "[dim]For scripting, use:[/dim] inkarms config init --quick --force"
            )
            raise typer.Exit(1)

        # Decide which mode to use
        if quick:
            # CLI inline wizard mode
            from inkarms.config.legacy_wizard import run_wizard_sync

            try:
                results = run_wizard_sync(force=force)

                if results.get("cancelled"):
                    console.print("[yellow]Setup cancelled by user.[/yellow]")
                    # add logic
                    return

                return

            except KeyboardInterrupt:
                console.print("\n[yellow]Setup cancelled by user.[/yellow]")
                return
            except Exception as e:
                console.print(f"\n[red]Wizard failed: {e}[/red]")
                console.print("[dim]Falling back to non-interactive setup...[/dim]\n")
                # Fall through to non-interactive setup
                if is_initialized() and not force:
                    console.print("[yellow]InkArms is already initialized.[/yellow]")
                    console.print(f"[dim]Config: {get_global_config_path()}[/dim]")
                    return

                results = run_setup(force=force)

                console.print("[green]InkArms initialized successfully![/green]")
                console.print("\n[bold]Directories created:[/bold]")
                for name, path in results["directories"].items():
                    console.print(f"  {name}: {path}")

                if results["config_created"]:
                    console.print(f"\n[bold]Configuration:[/bold] {results['config_path']}")

                console.print("\n[dim]Next steps:[/dim]")
                console.print(
                    "[dim]  1. Edit ~/.inkarms/config.yaml to configure your settings[/dim]"
                )
                console.print(
                    "[dim]  2. Set your API key: inkarms config set-secret <provider>[/dim]"
                )
                console.print("[dim]  3. Run: inkarms run 'Hello!'[/dim]")

        else:
            # Interactive TUI wizard
            try:
                from inkarms.ui.rich_backend import RichBackend
                from inkarms.config.wizard import RichWizard

                # Initialize minimal backend for wizard
                backend = RichBackend()
                # We don't need full backend.run(), just enough for the wizard primitives

                wizard = RichWizard(backend)
                if wizard.run():
                    # Wizard handled success message
                    pass
                else:
                    console.print("[yellow]Setup cancelled.[/yellow]")

            except ImportError:
                console.print("[red]UI dependencies not found.[/red]")
                console.print(
                    "[dim]Install with: pip install inkarms[textual][/dim]"
                )  # rich is default now but message helps
                raise typer.Exit(1)
            except Exception as e:
                console.print(f"[red]Wizard failed: {e}[/red]")
                if os.environ.get("INKARMS_DEBUG"):
                    import traceback

                    traceback.print_exc()
                raise typer.Exit(1)
