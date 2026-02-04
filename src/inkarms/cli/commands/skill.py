"""
inkarms skill - Skill management commands.

Usage:
    inkarms skill list
    inkarms skill install github:user/repo/skill-name
    inkarms skill remove skill-name
    inkarms skill show skill-name
    inkarms skill create my-skill
    inkarms skill validate ./path/to/skill
    inkarms skill reindex
"""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from inkarms.skills import (
    SkillManager,
    SkillNotFoundError,
    SkillParseError,
    SkillValidationError,
    get_skill_manager,
)

app = typer.Typer(
    name="skill",
    help="Skill management.",
)

console = Console()


@app.command("list")
def list_skills(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed information.",
        ),
    ] = False,
    global_only: Annotated[
        bool,
        typer.Option(
            "--global",
            "-g",
            help="Only show global skills.",
        ),
    ] = False,
) -> None:
    """List installed skills."""
    manager = get_skill_manager()
    skills = manager.list_skills(include_project=not global_only)

    if not skills:
        console.print("[yellow]No skills installed.[/yellow]")
        console.print("[dim]Create a skill: inkarms skill create my-skill[/dim]")
        return

    table = Table(title="Installed Skills")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Description")
    table.add_column("Location", style="dim")

    if verbose:
        table.add_column("Keywords", style="dim")
        table.add_column("Path", style="dim")

    for skill in skills:
        location = "global" if skill.is_global else "project"
        row = [
            skill.name,
            skill.version,
            skill.description[:50] + "..." if len(skill.description) > 50 else skill.description,
            location,
        ]
        if verbose:
            row.append(", ".join(skill.keywords[:5]))
            row.append(skill.path)
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(skills)} skill(s)[/dim]")


@app.command()
def search(
    query: Annotated[
        str,
        typer.Argument(
            help="Search query.",
        ),
    ],
    max_results: Annotated[
        int,
        typer.Option(
            "--max",
            "-n",
            help="Maximum number of results.",
        ),
    ] = 10,
) -> None:
    """Search for skills by keyword."""
    manager = get_skill_manager()
    results = manager.search(query, max_results)

    if not results:
        console.print(f"[yellow]No skills found matching '{query}'[/yellow]")
        return

    table = Table(title=f"Search Results for '{query}'")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Description")
    table.add_column("Keywords", style="dim")

    for skill in results:
        table.add_row(
            skill.name,
            skill.version,
            skill.description[:40] + "..." if len(skill.description) > 40 else skill.description,
            ", ".join(skill.keywords[:3]),
        )

    console.print(table)


@app.command()
def show(
    name: Annotated[
        str,
        typer.Argument(
            help="Skill name or path.",
        ),
    ],
) -> None:
    """Show skill details."""
    manager = get_skill_manager()

    try:
        info = manager.get_skill_info(name)
    except SkillNotFoundError:
        console.print(f"[red]Skill not found: {name}[/red]")
        raise typer.Exit(1)
    except SkillParseError as e:
        console.print(f"[red]Failed to parse skill: {e}[/red]")
        raise typer.Exit(1)

    # Build info panel
    lines = [
        f"[bold]Name:[/bold] {info['name']}",
        f"[bold]Version:[/bold] {info['version']}",
        f"[bold]Description:[/bold] {info['description'] or '(none)'}",
    ]

    if info["author"]:
        lines.append(f"[bold]Author:[/bold] {info['author']}")
    if info["license"]:
        lines.append(f"[bold]License:[/bold] {info['license']}")
    if info["repository"]:
        lines.append(f"[bold]Repository:[/bold] {info['repository']}")

    lines.append("")
    lines.append(f"[bold]Keywords:[/bold] {', '.join(info['keywords']) or '(none)'}")
    lines.append("")
    lines.append("[bold]Permissions:[/bold]")
    lines.append(f"  Tools: {', '.join(info['permissions']['tools']) or '(none)'}")
    lines.append(f"  Network: {info['permissions']['network']}")
    lines.append(f"  Read: {', '.join(info['permissions']['filesystem']['read']) or '(none)'}")
    lines.append(f"  Write: {', '.join(info['permissions']['filesystem']['write']) or '(none)'}")

    if info["path"]:
        lines.append("")
        lines.append(f"[bold]Path:[/bold] {info['path']}")

    console.print(Panel("\n".join(lines), title=f"Skill: {info['name']}"))

    # Show instructions preview
    console.print("\n[bold]Instructions Preview:[/bold]")
    console.print(f"[dim]{info['instructions_preview']}[/dim]")


@app.command()
def install(
    source: Annotated[
        str,
        typer.Argument(
            help="Skill source (local path).",
        ),
    ],
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Overwrite existing skill.",
        ),
    ] = False,
) -> None:
    """Install a skill from a local path."""
    manager = get_skill_manager()

    try:
        dest_path = manager.install_skill(source, force=force)
        console.print(f"[green]Skill installed successfully![/green]")
        console.print(f"[dim]Location: {dest_path}[/dim]")
    except NotImplementedError as e:
        console.print(f"[yellow]{e}[/yellow]")
        console.print("[dim]Currently only local path installation is supported.[/dim]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except SkillParseError as e:
        console.print(f"[red]Invalid skill: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def remove(
    name: Annotated[
        str,
        typer.Argument(
            help="Skill name to remove.",
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
    """Remove an installed skill."""
    manager = get_skill_manager()

    # Check if skill exists
    try:
        info = manager.get_skill_info(name)
    except SkillNotFoundError:
        console.print(f"[red]Skill not found: {name}[/red]")
        raise typer.Exit(1)

    # Confirm removal
    if not yes:
        console.print(f"[yellow]This will remove skill '{name}' from {info['path']}[/yellow]")
        confirmed = typer.confirm("Are you sure?")
        if not confirmed:
            console.print("[dim]Cancelled.[/dim]")
            return

    try:
        manager.remove_skill(name)
        console.print(f"[green]Skill '{name}' removed successfully.[/green]")
    except SkillNotFoundError:
        console.print(f"[red]Skill not found: {name}[/red]")
        raise typer.Exit(1)


@app.command()
def update(
    name: Annotated[
        str | None,
        typer.Argument(
            help="Skill name (updates all if not specified).",
        ),
    ] = None,
) -> None:
    """Update skill(s) to latest version."""
    console.print(
        "[yellow]Skill update not yet implemented. "
        "Remote skill installation coming in a future release.[/yellow]"
    )


@app.command()
def create(
    name: Annotated[
        str,
        typer.Argument(
            help="Name for the new skill.",
        ),
    ],
    description: Annotated[
        str,
        typer.Option(
            "--description",
            "-d",
            help="Short description.",
        ),
    ] = "A new skill",
    location: Annotated[
        str,
        typer.Option(
            "--location",
            "-l",
            help="Where to create (global or project).",
        ),
    ] = "global",
) -> None:
    """Create a new skill from template."""
    manager = get_skill_manager()

    try:
        skill_path = manager.create_skill(name, description=description, location=location)
        console.print(f"[green]Skill created successfully![/green]")
        console.print(f"[dim]Location: {skill_path}[/dim]")
        console.print("\nNext steps:")
        console.print(f"  1. Edit [cyan]{skill_path}/SKILL.md[/cyan] to add instructions")
        console.print(f"  2. Edit [cyan]{skill_path}/skill.yaml[/cyan] to configure metadata")
        console.print(f"  3. Validate: [cyan]inkarms skill validate {skill_path}[/cyan]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("validate")
def validate_skill(
    path: Annotated[
        Path,
        typer.Argument(
            help="Path to skill directory.",
        ),
    ],
) -> None:
    """Validate a skill."""
    manager = get_skill_manager()

    issues = manager.validate_skill(path)

    if not issues:
        console.print(f"[green]Skill is valid![/green]")
        return

    # Separate errors and warnings
    errors = [i for i in issues if not i.startswith("Warning:")]
    warnings = [i for i in issues if i.startswith("Warning:")]

    if errors:
        console.print("[red]Validation errors:[/red]")
        for error in errors:
            console.print(f"  [red]- {error}[/red]")

    if warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for warning in warnings:
            console.print(f"  [yellow]- {warning}[/yellow]")

    if errors:
        raise typer.Exit(1)


@app.command()
def reindex() -> None:
    """Rebuild the skill index."""
    manager = get_skill_manager()

    console.print("[dim]Rebuilding skill index...[/dim]")
    index = manager.reindex()

    console.print(f"[green]Index rebuilt successfully![/green]")
    console.print(f"[dim]Indexed {len(index.skills)} skill(s)[/dim]")
