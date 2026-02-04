"""
inkarms memory - Memory and handoff management commands.

Usage:
    inkarms memory list
    inkarms memory show 2026-02-02
    inkarms memory compact
    inkarms memory handoff
"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from inkarms.memory import (
    CompactionStrategy,
    MemoryType,
    get_session_manager,
    reset_session_manager,
)

app = typer.Typer(
    name="memory",
    help="Memory and handoff management.",
)

console = Console()


@app.command("list")
def list_memory(
    memory_type: Annotated[
        str | None,
        typer.Option(
            "--type",
            "-t",
            help="Filter by type: daily, snapshot, handoff.",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-n",
            help="Maximum entries to show.",
        ),
    ] = 20,
) -> None:
    """List memory files."""
    manager = get_session_manager()

    # Parse memory type
    mem_type = None
    if memory_type:
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            console.print(f"[red]Invalid type: {memory_type}[/red]")
            console.print("[dim]Valid types: daily, snapshot, handoff[/dim]")
            raise typer.Exit(1)

    entries = manager.list_memory(mem_type)

    if not entries:
        console.print("[yellow]No memory entries found.[/yellow]")
        return

    table = Table(title="Memory Entries")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Created", style="dim")
    table.add_column("Turns", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Description")

    for entry in entries[:limit]:
        table.add_row(
            entry.name,
            entry.memory_type,
            entry.created_at.strftime("%Y-%m-%d %H:%M"),
            str(entry.turn_count),
            f"{entry.total_tokens:,}",
            entry.description[:40] + "..." if len(entry.description) > 40 else entry.description,
        )

    console.print(table)
    console.print(f"\n[dim]Showing {min(limit, len(entries))} of {len(entries)} entries[/dim]")


@app.command()
def show(
    name: Annotated[
        str,
        typer.Argument(
            help="Memory name or date (e.g., '2026-02-02', 'api-draft').",
        ),
    ],
) -> None:
    """Show memory content."""
    manager = get_session_manager()

    # Try to find the memory entry
    entries = manager.list_memory()
    entry = next((e for e in entries if e.name == name or e.id == name), None)

    if entry is None:
        console.print(f"[red]Memory not found: {name}[/red]")
        raise typer.Exit(1)

    # Load based on type
    if entry.memory_type == MemoryType.DAILY:
        from datetime import datetime

        date = datetime.strptime(entry.name, "%Y-%m-%d")
        session = manager.storage.load_daily_session(date)
        if session:
            _show_session(session, entry.name)
    elif entry.memory_type == MemoryType.SNAPSHOT:
        snapshot = manager.storage.load_snapshot(entry.name)
        if snapshot:
            console.print(f"[bold]Snapshot:[/bold] {snapshot.name}")
            console.print(f"[bold]Description:[/bold] {snapshot.description}")
            if snapshot.topic:
                console.print(f"[bold]Topic:[/bold] {snapshot.topic}")
            console.print()
            _show_session(snapshot.session, snapshot.name)
    elif entry.memory_type == MemoryType.HANDOFF:
        handoff = manager.storage._load_handoff_file(Path(entry.path))
        if handoff:
            _show_handoff(handoff)


def _show_session(session, name: str) -> None:
    """Display a session."""
    console.print(Panel(f"Session: {name}", style="bold"))
    console.print(
        f"[dim]Turns: {len(session.turns)} | Tokens: {session.metadata.total_tokens:,}[/dim]"
    )
    console.print()

    for turn in session.turns[-20:]:  # Show last 20 turns
        role = turn.role.upper() if isinstance(turn.role, str) else turn.role.value.upper()
        style = "green" if role == "USER" else "blue" if role == "ASSISTANT" else "dim"
        console.print(f"[{style}]{role}:[/{style}]")
        content = turn.content[:500] + "..." if len(turn.content) > 500 else turn.content
        console.print(content)
        console.print()


def _show_handoff(handoff) -> None:
    """Display a handoff document."""
    console.print(Panel("Handoff Document", style="bold yellow"))
    console.print(f"[bold]Created:[/bold] {handoff.created_at.isoformat()}")
    console.print(f"[bold]Session ID:[/bold] {handoff.session_id}")
    console.print(f"[bold]Tokens Used:[/bold] {handoff.total_tokens_used:,}")
    console.print(f"[bold]Total Cost:[/bold] ${handoff.total_cost:.4f}")
    console.print(f"[bold]Recovered:[/bold] {handoff.recovered}")
    console.print()
    console.print("[bold]Summary:[/bold]")
    console.print(handoff.summary)

    if handoff.key_decisions:
        console.print("\n[bold]Key Decisions:[/bold]")
        for decision in handoff.key_decisions:
            console.print(f"  - {decision}")

    if handoff.pending_tasks:
        console.print("\n[bold]Pending Tasks:[/bold]")
        for task in handoff.pending_tasks:
            console.print(f"  - {task}")


@app.command()
def snapshot(
    name: Annotated[
        str,
        typer.Argument(
            help="Snapshot name.",
        ),
    ],
    description: Annotated[
        str | None,
        typer.Option(
            "--description",
            "-d",
            help="Snapshot description.",
        ),
    ] = None,
    topic: Annotated[
        str | None,
        typer.Option(
            "--topic",
            "-t",
            help="Topic tag.",
        ),
    ] = None,
) -> None:
    """Create a memory snapshot of the current session."""
    manager = get_session_manager()

    if len(manager.session.turns) == 0:
        console.print("[yellow]No conversation to snapshot.[/yellow]")
        return

    path = manager.save_snapshot(name, description=description or "", topic=topic)
    console.print(f"[green]Snapshot saved:[/green] {name}")
    console.print(f"[dim]Path: {path}[/dim]")


@app.command()
def compact(
    strategy: Annotated[
        str,
        typer.Option(
            "--strategy",
            "-s",
            help="Compaction strategy: summarize, truncate, sliding_window.",
        ),
    ] = "summarize",
    keep_recent: Annotated[
        int,
        typer.Option(
            "--keep-recent",
            "-k",
            help="Number of recent turns to keep.",
        ),
    ] = 5,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would happen without compacting.",
        ),
    ] = False,
) -> None:
    """Compact the current context."""
    manager = get_session_manager()

    usage_before = manager.get_context_usage()

    console.print("[bold]Current context:[/bold]")
    console.print(f"  Tokens: {usage_before.format_status()}")
    console.print(f"  Turns: {len(manager.session.turns)}")

    if dry_run:
        console.print(
            f"\n[dim]Would compact using '{strategy}' strategy, keeping {keep_recent} recent turns[/dim]"
        )
        return

    try:
        comp_strategy = CompactionStrategy(strategy)
    except ValueError:
        console.print(f"[red]Invalid strategy: {strategy}[/red]")
        console.print("[dim]Valid strategies: summarize, truncate, sliding_window[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[dim]Compacting with '{strategy}' strategy...[/dim]")

    # Run compaction
    asyncio.run(_compact_async(manager, comp_strategy))

    usage_after = manager.get_context_usage()

    console.print("\n[green]Compaction complete![/green]")
    console.print(f"  Tokens: {usage_after.format_status()}")
    console.print(f"  Turns: {len(manager.session.turns)}")
    console.print(f"  Saved: {usage_before.current_tokens - usage_after.current_tokens:,} tokens")


async def _compact_async(manager, strategy):
    """Run compaction asynchronously."""
    await manager.compact(strategy)


@app.command()
def clean() -> None:
    """Clean non-essential messages from context."""
    manager = get_session_manager()

    # Remove system messages that are summaries
    initial_count = len(manager.session.turns)
    manager.session.turns = [
        t for t in manager.session.turns if not (t.role == "system" and t.is_compacted)
    ]
    removed = initial_count - len(manager.session.turns)

    if removed > 0:
        console.print(f"[green]Cleaned {removed} compacted summary message(s)[/green]")
    else:
        console.print("[dim]No messages to clean[/dim]")


@app.command()
def handoff(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Force handoff creation.",
        ),
    ] = False,
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Check for existing handoff without creating.",
        ),
    ] = False,
) -> None:
    """Create or check handoff document."""
    manager = get_session_manager()

    if check:
        handoff = manager.check_for_handoff()
        if handoff:
            console.print("[yellow]Pending handoff found![/yellow]")
            console.print(f"  Created: {handoff.created_at.isoformat()}")
            console.print(f"  Session: {handoff.session_id}")
            console.print("\nRun 'inkarms memory recover' to restore the session.")
        else:
            console.print("[green]No pending handoff[/green]")
        return

    usage = manager.get_context_usage()

    if not force and not usage.should_handoff:
        console.print(
            f"[yellow]Context usage ({usage.usage_percent * 100:.1f}%) below handoff threshold.[/yellow]"
        )
        console.print("[dim]Use --force to create anyway.[/dim]")
        return

    console.print("[dim]Creating handoff document...[/dim]")

    handoff = asyncio.run(_create_handoff_async(manager))

    console.print("[green]Handoff created successfully![/green]")
    console.print(f"  ID: {handoff.id}")
    console.print(f"  Tokens preserved: {handoff.total_tokens_used:,}")
    console.print(f"  Recent turns: {len(handoff.recent_turns)}")
    console.print("\nClear your context and run 'inkarms memory recover' to continue.")


async def _create_handoff_async(manager):
    """Create handoff asynchronously."""
    return await manager.create_handoff()


@app.command()
def recover(
    no_archive: Annotated[
        bool,
        typer.Option(
            "--no-archive",
            help="Don't archive the handoff file after recovery.",
        ),
    ] = False,
) -> None:
    """Recover session from handoff document."""
    manager = get_session_manager()

    handoff = manager.check_for_handoff()

    if handoff is None:
        console.print("[yellow]No pending handoff to recover.[/yellow]")
        return

    console.print(f"[dim]Recovering from handoff {handoff.id}...[/dim]")

    session = asyncio.run(_recover_async(manager, not no_archive))

    console.print("[green]Session recovered![/green]")
    console.print(f"  Turns: {len(session.turns)}")
    console.print(f"  Tokens: {manager.get_context_usage().format_status()}")


async def _recover_async(manager, archive: bool):
    """Recover asynchronously."""
    return await manager.recover_handoff(archive=archive)


@app.command()
def delete(
    name: Annotated[
        str,
        typer.Argument(
            help="Memory name or date to delete.",
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
    """Delete memory files."""
    manager = get_session_manager()

    # Find the entry
    entries = manager.list_memory()
    entry = next((e for e in entries if e.name == name or e.id == name), None)

    if entry is None:
        console.print(f"[red]Memory not found: {name}[/red]")
        raise typer.Exit(1)

    if not yes:
        confirmed = typer.confirm(f"Delete {entry.memory_type} '{entry.name}'?")
        if not confirmed:
            console.print("[dim]Cancelled[/dim]")
            return

    path = Path(entry.path)
    if path.exists():
        path.unlink()
        console.print(f"[green]Deleted: {entry.name}[/green]")
    else:
        console.print(f"[yellow]File not found: {entry.path}[/yellow]")


@app.command()
def status() -> None:
    """Show current session status."""
    manager = get_session_manager()
    info = manager.get_session_info()

    console.print(Panel("Session Status", style="bold"))
    console.print(f"[bold]Session ID:[/bold] {info['session_id'][:8]}...")
    console.print(f"[bold]Created:[/bold] {info['created_at']}")
    console.print(f"[bold]Turns:[/bold] {info['turn_count']}")
    console.print(
        f"[bold]Tokens:[/bold] {info['total_tokens']:,} / {info['max_tokens']:,} ({info['usage_percent']})"
    )
    console.print(f"[bold]Cost:[/bold] ${info['total_cost']:.4f}")
    console.print(f"[bold]Model:[/bold] {info['model']}")

    if info["should_compact"]:
        console.print(
            "\n[yellow]Recommendation: Consider running 'inkarms memory compact'[/yellow]"
        )
    if info["should_handoff"]:
        console.print("\n[red]Warning: Context is nearly full. Run 'inkarms memory handoff'[/red]")


@app.command()
def clear(
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmation.",
        ),
    ] = False,
) -> None:
    """Clear the current session."""
    if not yes:
        confirmed = typer.confirm("Clear the current session?")
        if not confirmed:
            console.print("[dim]Cancelled[/dim]")
            return

    reset_session_manager()
    console.print("[green]Session cleared[/green]")
