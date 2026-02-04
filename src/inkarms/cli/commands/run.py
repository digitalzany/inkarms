"""
inkarms run - Execute queries against the AI.

Usage:
    inkarms run "Your query here"
    inkarms run "Query" --model claude-opus
    inkarms run "Query" --task coding
    inkarms run "Query" --skill security-scan
    inkarms run "Query" --deep
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from inkarms.agent import AgentConfig, AgentLoop, ApprovalMode
from inkarms.config import get_config
from inkarms.memory import get_session_manager, reset_session_manager
from inkarms.providers import (
    AllProvidersFailedError,
    AuthenticationError,
    Message,
    ProviderError,
    get_provider_manager,
)
from inkarms.security.sandbox import SandboxExecutor
from inkarms.skills import (
    Skill,
    SkillNotFoundError,
    SkillParseError,
    get_skill_manager,
)
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.registry import ToolRegistry

app = typer.Typer(
    name="run",
    help="Execute a query against the AI.",
    invoke_without_command=True,
)

console = Console()


def _build_skill_prompt(skills: list[Skill]) -> str:
    """Build the skill injection for the system prompt.

    Args:
        skills: List of skills to inject.

    Returns:
        Combined skill instructions.
    """
    if not skills:
        return ""

    parts = ["# Active Skills\n"]
    for skill in skills:
        parts.append(skill.get_system_prompt_injection())
        parts.append("\n---\n")

    return "\n".join(parts)


async def _run_with_tools(
    query: str,
    model: str | None,
    tool_approval: str,
    skills: list[Skill] | None,
    track_context: bool,
    output: Path | None,
    json_output: bool,
) -> None:
    """Run completion with tool use enabled."""
    # Get config
    config = get_config()

    # Setup tool registry
    registry = ToolRegistry()
    sandbox = SandboxExecutor.from_config(config.security)
    register_builtin_tools(registry, sandbox)

    # Map approval mode
    approval_mode_map = {
        "auto": ApprovalMode.AUTO,
        "manual": ApprovalMode.MANUAL,
        "disabled": ApprovalMode.DISABLED,
    }
    approval_mode = approval_mode_map.get(tool_approval.lower(), ApprovalMode.MANUAL)

    # Configure agent
    agent_config = AgentConfig(
        approval_mode=approval_mode,
        enable_tools=True,
        max_iterations=config.agent.max_iterations,
        timeout_per_iteration=config.agent.timeout_per_iteration,
        allowed_tools=config.agent.allowed_tools,
        blocked_tools=config.agent.blocked_tools,
    )

    # Define approval callback for manual mode
    def approval_callback(tool_call, tool):
        console.print(f"\n[yellow]Tool Approval Request:[/yellow]")
        console.print(f"  Tool: [bold]{tool.name}[/bold]")
        console.print(f"  Dangerous: {tool.is_dangerous}")
        console.print(f"  Input: {tool_call.input}")

        response = typer.confirm("Approve this tool execution?", default=True)
        return response

    # Create agent loop
    provider_manager = get_provider_manager()
    agent = AgentLoop(
        provider_manager=provider_manager,
        tool_registry=registry,
        config=agent_config,
        approval_callback=approval_callback if approval_mode == ApprovalMode.MANUAL else None,
    )

    # Build messages
    messages: list[Message] = []

    # Build system prompt with skills
    system_parts = []
    if config.system_prompt.personality:
        system_parts.append(config.system_prompt.personality)

    if skills:
        skill_prompt = _build_skill_prompt(skills)
        if skill_prompt:
            system_parts.append(skill_prompt)

    # Add tool use instruction
    system_parts.append(
        "You have access to tools that allow you to execute commands, "
        "read/write files, and search for information. "
        "Use these tools when they can help answer the user's query."
    )

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    if system_prompt:
        messages.append(Message.system(system_prompt))

    # Add user query
    messages.append(Message.user(query))

    # Show starting message
    console.print("[dim]Running with tool use enabled...[/dim]\n")

    try:
        # Run agent loop
        result = await agent.run(messages, model=model)

        # Display results
        if result.success:
            console.print("\n" + "=" * 60)
            console.print(f"[green]✓[/green] Completed in {result.iterations} iteration(s)")
            console.print(f"Tools used: {len(result.tool_calls_made)}")

            if result.tool_calls_made:
                console.print("\nTools executed:")
                for tc in result.tool_calls_made:
                    console.print(f"  • {tc.name}")

            console.print("=" * 60 + "\n")

            # Display final response
            if json_output:
                output_data = {
                    "success": True,
                    "response": result.final_response,
                    "iterations": result.iterations,
                    "tool_calls": [
                        {"name": tc.name, "input": tc.input}
                        for tc in result.tool_calls_made
                    ],
                }
                console.print_json(data=output_data)
            else:
                md = Markdown(result.final_response)
                console.print(md)

            # Save to file if requested
            if output:
                output.write_text(result.final_response)
                console.print(f"\n[dim]Response saved to: {output}[/dim]")

        else:
            console.print(f"[red]✗ Failed:[/red] {result.error}")
            console.print(f"Stopped after {result.iterations} iteration(s)")
            console.print(f"Reason: {result.stopped_reason}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


async def _run_completion(
    query: str,
    model: str | None,
    stream: bool,
    context_file: Path | None,
    output: Path | None,
    json_output: bool,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    skills: list[Skill] | None = None,
    track_context: bool = True,
) -> None:
    """Run the completion request."""
    # Get session manager for context tracking
    session_manager = get_session_manager(model=model) if track_context else None

    # Build messages
    messages: list[Message] = []

    # Build system prompt with skills
    system_parts = []

    # Add personality if configured
    config = get_config()
    if config.system_prompt.personality:
        system_parts.append(config.system_prompt.personality)

    # Add skill instructions
    if skills:
        skill_prompt = _build_skill_prompt(skills)
        if skill_prompt:
            system_parts.append(skill_prompt)

    # Combine into system message
    system_prompt = "\n\n".join(system_parts) if system_parts else None
    if system_prompt:
        messages.append(Message.system(system_prompt))
        if session_manager:
            session_manager.set_system_prompt(system_prompt)

    # Add context file if provided
    if context_file:
        if context_file.exists():
            content = context_file.read_text()
            context_msg = f"Context from {context_file.name}:\n\n```\n{content}\n```"
            messages.append(Message.user(context_msg))
            if session_manager:
                session_manager.add_user_message(context_msg)
        else:
            console.print(f"[yellow]Warning: Context file not found: {context_file}[/yellow]")

    # Add the user query
    messages.append(Message.user(query))
    if session_manager:
        session_manager.add_user_message(query)

    # Check context usage before making request
    if session_manager:
        usage = session_manager.get_context_usage()
        if usage.should_handoff:
            console.print(
                f"[yellow]Warning: Context at {usage.usage_percent * 100:.0f}% capacity. "
                f"Consider running 'inkarms memory handoff'[/yellow]"
            )
        elif usage.should_compact:
            console.print(
                f"[dim]Context at {usage.usage_percent * 100:.0f}% - compaction recommended[/dim]"
            )

    # Get provider manager
    try:
        manager = get_provider_manager()
    except Exception as e:
        console.print(f"[red]Failed to initialize provider: {e}[/red]")
        raise typer.Exit(1)

    # Show what we're doing
    resolved_model = manager._resolve_model(model)
    console.print(f"[dim]Model: {resolved_model}[/dim]")

    try:
        if stream and not json_output:
            # Streaming output
            response_text = ""
            stream_response = await manager.complete(
                messages,
                model=model,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            with Live(console=console, refresh_per_second=10) as live:
                async for chunk in stream_response:  # type: ignore
                    response_text += chunk.content
                    live.update(Markdown(response_text))

            # Track assistant response
            if session_manager:
                summary = manager.get_cost_summary()
                session_manager.add_assistant_message(
                    response_text,
                    model=resolved_model,
                    cost=summary.total_cost,
                )

            # Show cost info
            summary = manager.get_cost_summary()
            if summary.total_cost > 0:
                usage_info = ""
                if session_manager:
                    ctx_usage = session_manager.get_context_usage()
                    usage_info = f" | Context: {ctx_usage.usage_percent * 100:.0f}%"

                console.print(
                    f"\n[dim]Tokens: {summary.total_input_tokens} in, "
                    f"{summary.total_output_tokens} out | "
                    f"Cost: ${summary.total_cost:.4f}{usage_info}[/dim]"
                )

            # Save to file if requested
            if output:
                output.write_text(response_text)
                console.print(f"[green]Saved to: {output}[/green]")

        else:
            # Non-streaming output
            response = await manager.complete(
                messages,
                model=model,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # Type assertion for non-streaming response
            from inkarms.providers import CompletionResponse

            assert isinstance(response, CompletionResponse)

            # Track assistant response
            if session_manager:
                session_manager.add_assistant_message(
                    response.content,
                    model=response.model,
                    cost=response.cost,
                )

            if json_output:
                result = {
                    "content": response.content,
                    "model": response.model,
                    "provider": response.provider,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                    "cost": response.cost,
                    "finish_reason": response.finish_reason,
                }
                if session_manager:
                    ctx_usage = session_manager.get_context_usage()
                    result["context"] = {
                        "tokens": ctx_usage.current_tokens,
                        "max_tokens": ctx_usage.max_tokens,
                        "usage_percent": ctx_usage.usage_percent,
                    }
                console.print_json(json.dumps(result))
            else:
                console.print(Markdown(response.content))

                usage_info = ""
                if session_manager:
                    ctx_usage = session_manager.get_context_usage()
                    usage_info = f" | Context: {ctx_usage.usage_percent * 100:.0f}%"

                console.print(
                    f"\n[dim]Tokens: {response.usage.input_tokens} in, "
                    f"{response.usage.output_tokens} out | "
                    f"Cost: ${response.cost:.4f}{usage_info}[/dim]"
                )

            # Save to file if requested
            if output:
                output.write_text(response.content)
                console.print(f"[green]Saved to: {output}[/green]")

    except AuthenticationError as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        console.print("[dim]Check your API key configuration:[/dim]")
        console.print("[dim]  - Environment variable (e.g., ANTHROPIC_API_KEY)[/dim]")
        console.print("[dim]  - inkarms config set-secret <provider>[/dim]")
        raise typer.Exit(3)

    except AllProvidersFailedError as e:
        console.print(f"[red]All providers failed: {e}[/red]")
        console.print(f"[dim]Failed providers: {', '.join(e.failed_providers)}[/dim]")
        raise typer.Exit(4)

    except ProviderError as e:
        console.print(f"[red]Provider error: {e}[/red]")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def run_query(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(
            help="The query to send to the AI.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Model to use (name or alias).",
        ),
    ] = None,
    task: Annotated[
        str | None,
        typer.Option(
            "--task",
            "-t",
            help="Task type (coding, consulting, etc.).",
        ),
    ] = None,
    skill: Annotated[
        str | None,
        typer.Option(
            "--skill",
            "-s",
            help="Explicitly load a skill by name or path.",
        ),
    ] = None,
    auto_skill: Annotated[
        bool,
        typer.Option(
            "--auto-skill/--no-auto-skill",
            help="Automatically discover relevant skills.",
        ),
    ] = False,
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            "-d",
            help="Enable deep thinking chain.",
        ),
    ] = False,
    approve: Annotated[
        bool,
        typer.Option(
            "--approve",
            "-a",
            help="Require approval for commands.",
        ),
    ] = False,
    stream: Annotated[
        bool,
        typer.Option(
            "--stream/--no-stream",
            help="Stream response (default: stream).",
        ),
    ] = True,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help="Skip confirmations.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would happen without executing.",
        ),
    ] = False,
    context_file: Annotated[
        Path | None,
        typer.Option(
            "--context",
            help="Include file in context.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write response to file.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output as JSON.",
        ),
    ] = False,
    temperature: Annotated[
        float,
        typer.Option(
            "--temperature",
            help="Sampling temperature (0.0-2.0).",
        ),
    ] = 0.7,
    max_tokens: Annotated[
        int | None,
        typer.Option(
            "--max-tokens",
            help="Maximum tokens in response.",
        ),
    ] = None,
    no_memory: Annotated[
        bool,
        typer.Option(
            "--no-memory",
            help="Don't track this query in session memory.",
        ),
    ] = False,
    new_session: Annotated[
        bool,
        typer.Option(
            "--new-session",
            help="Start a fresh session.",
        ),
    ] = False,
    tools: Annotated[
        bool,
        typer.Option(
            "--tools/--no-tools",
            help="Enable tool use (function calling).",
        ),
    ] = False,
    tool_approval: Annotated[
        str,
        typer.Option(
            "--tool-approval",
            help="Tool approval mode: auto, manual, or disabled.",
        ),
    ] = "manual",
) -> None:
    """Execute a query against the AI."""
    if query is None:
        console.print("[red]Error:[/red] Query is required.")
        console.print('Usage: [bold]inkarms run "Your query here"[/bold]')
        raise typer.Exit(1)

    # Start fresh session if requested
    if new_session:
        reset_session_manager()

    # Load skills
    loaded_skills: list[Skill] = []
    skill_manager = get_skill_manager()

    # Explicit skill loading
    if skill:
        try:
            loaded_skill = skill_manager.get_skill(skill)
            loaded_skills.append(loaded_skill)
            console.print(f"[dim]Skill loaded: {loaded_skill.name}[/dim]")
        except SkillNotFoundError:
            console.print(f"[yellow]Warning: Skill not found: {skill}[/yellow]")
        except SkillParseError as e:
            console.print(f"[yellow]Warning: Failed to load skill: {e}[/yellow]")

    # Auto skill discovery
    if auto_skill and not skill:
        try:
            auto_skills = skill_manager.get_skills_for_query(query, max_skills=3)
            if auto_skills:
                loaded_skills.extend(auto_skills)
                names = [s.name for s in auto_skills]
                console.print(f"[dim]Auto-loaded skills: {', '.join(names)}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Auto-skill discovery failed: {e}[/yellow]")

    # Show configuration if dry run
    if dry_run:
        skill_names = [s.name for s in loaded_skills] if loaded_skills else ["none"]

        # Get context usage
        session_manager = get_session_manager(model=model)
        ctx_usage = session_manager.get_context_usage()

        console.print(
            Panel(
                f"[bold]Query:[/bold] {query}\n"
                f"[bold]Model:[/bold] {model or 'default'}\n"
                f"[bold]Task:[/bold] {task or 'auto'}\n"
                f"[bold]Skills:[/bold] {', '.join(skill_names)}\n"
                f"[bold]Auto-skill:[/bold] {auto_skill}\n"
                f"[bold]Deep thinking:[/bold] {deep}\n"
                f"[bold]Stream:[/bold] {stream}\n"
                f"[bold]Temperature:[/bold] {temperature}\n"
                f"[bold]Context:[/bold] {ctx_usage.format_status()}\n"
                f"[bold]Memory:[/bold] {'disabled' if no_memory else 'enabled'}",
                title="Dry Run",
            )
        )
        return

    # Task routing not yet implemented
    if task:
        console.print(
            f"[yellow]Task routing ({task}) not yet implemented. Using default model.[/yellow]"
        )
    if deep:
        console.print("[yellow]Deep thinking not yet implemented. Coming in Phase 2.[/yellow]")

    # Run with tool use or standard completion
    if tools:
        asyncio.run(
            _run_with_tools(
                query=query,
                model=model,
                tool_approval=tool_approval,
                skills=loaded_skills if loaded_skills else None,
                track_context=not no_memory,
                output=output,
                json_output=json_output,
            )
        )
    else:
        asyncio.run(
            _run_completion(
                query=query,
                model=model,
            stream=stream,
            context_file=context_file,
            output=output,
            json_output=json_output,
            temperature=temperature,
            max_tokens=max_tokens,
            skills=loaded_skills if loaded_skills else None,
            track_context=not no_memory,
        )
    )


@app.command()
def rerun(
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            "-m",
            help="Override model for rerun.",
        ),
    ] = None,
    task: Annotated[
        str | None,
        typer.Option(
            "--task",
            "-t",
            help="Override task type for rerun.",
        ),
    ] = None,
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            "-d",
            help="Enable deep thinking chain.",
        ),
    ] = False,
) -> None:
    """Re-run the last query with different settings."""
    session_manager = get_session_manager()

    # Find last user message
    user_turns = [t for t in session_manager.session.turns if t.role == "user"]

    if not user_turns:
        console.print("[yellow]No previous query found in session.[/yellow]")
        return

    last_query = user_turns[-1].content

    console.print(f"[dim]Re-running: {last_query[:50]}...[/dim]")

    # Run the query again
    asyncio.run(
        _run_completion(
            query=last_query,
            model=model,
            stream=True,
            context_file=None,
            output=None,
            json_output=False,
            track_context=True,
        )
    )
