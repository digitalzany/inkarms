"""
Interactive configuration wizard for InkArms.

Provides two-level setup experience:
- QuickStart: Get up and running in minutes with sensible defaults
- Advanced: Full configuration with all options and explanations
"""

import getpass
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from inkarms.config.setup import create_default_config, create_directory_structure
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_global_config_path, get_inkarms_home

console = Console()

# Custom style for questionary prompts
custom_style = Style(
    [
        ("qmark", "fg:#5f87ff bold"),  # Question mark
        ("question", "bold"),  # Question text
        ("answer", "fg:#00d787 bold"),  # User's answer
        ("pointer", "fg:#5f87ff bold"),  # Selection pointer
        ("highlighted", "fg:#5f87ff bold"),  # Highlighted choice
        ("selected", "fg:#00d787"),  # Selected choice
        ("separator", "fg:#6c6c6c"),  # Separator
        ("instruction", "fg:#6c6c6c"),  # Instructions
        ("text", ""),  # Plain text
        ("disabled", "fg:#6c6c6c italic"),  # Disabled choice
    ]
)


class WizardMetadata:
    """Track wizard state and history."""

    def __init__(self):
        self.started_at = datetime.now()
        self.mode: str | None = None
        self.steps_completed: list[str] = []
        self.config_choices: dict[str, Any] = {}

    def mark_step(self, step_name: str):
        """Mark a step as completed."""
        self.steps_completed.append(step_name)

    def save_choice(self, key: str, value: Any):
        """Save a configuration choice."""
        self.config_choices[key] = value


async def run_interactive_wizard(force: bool = False) -> dict[str, Any]:
    """
    Run the interactive configuration wizard.

    Args:
        force: If True, overwrite existing configuration

    Returns:
        Dictionary with wizard results
    """
    metadata = WizardMetadata()

    # Welcome message
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]🐙 Welcome to InkArms![/bold cyan]\n\n"
            "Let's get you set up with your AI agent assistant.\n"
            "This wizard will help you configure InkArms for your needs.",
            border_style="cyan",
        )
    )
    console.print()

    # Check if already initialized
    if get_inkarms_home().exists() and get_global_config_path().exists() and not force:
        overwrite = await questionary.confirm(
            "InkArms is already configured. Overwrite existing configuration?",
            default=False,
            style=custom_style,
        ).ask_async()

        if not overwrite:
            console.print("[yellow]Setup cancelled.[/yellow]")
            return {"cancelled": True}

        force = True

    # Choose setup mode
    console.print("[bold]Choose your setup experience:[/bold]\n")

    mode = await questionary.select(
        "How would you like to set up InkArms?",
        choices=[
            questionary.Choice(
                title="QuickStart (Recommended) - Get started in 2 minutes",
                value="quick",
                description="Minimal questions, sensible defaults, start chatting quickly",
            ),
            questionary.Choice(
                title="Advanced - Full configuration wizard",
                value="advanced",
                description="Comprehensive setup with all options and customization",
            ),
        ],
        style=custom_style,
        use_indicator=True,
    ).ask_async()

    metadata.mode = mode
    metadata.mark_step("mode_selection")

    if mode == "quick":
        return await _run_quickstart_wizard(metadata, force)
    else:
        return await _run_advanced_wizard(metadata, force)


async def _run_quickstart_wizard(metadata: WizardMetadata, force: bool) -> dict[str, Any]:
    """
    Run the QuickStart wizard (minimal questions).

    Args:
        metadata: Wizard metadata tracker
        force: If True, overwrite existing config

    Returns:
        Dictionary with setup results
    """
    console.print()
    console.print("[bold cyan]⚡ QuickStart Mode[/bold cyan]")
    console.print("[dim]We'll ask you a few essential questions to get started.[/dim]\n")

    results = {"mode": "quick", "config_created": False, "directories": {}}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: Create directories
        task = progress.add_task("Creating directories...", total=1)
        results["directories"] = create_directory_structure()
        progress.update(task, completed=1)
        metadata.mark_step("directories")

    console.print("[green]✓ Directories created[/green]\n")

    # Step 2: Choose AI provider
    console.print("[bold]Step 1: Choose your AI provider[/bold]")
    console.print("[dim]InkArms supports 100+ providers via LiteLLM[/dim]\n")

    provider = await questionary.select(
        "Which AI provider do you want to use?",
        choices=[
            questionary.Choice(
                title="Anthropic Claude (Recommended)",
                value="anthropic",
                description="Latest Claude models - Sonnet 4, Opus 4, Haiku",
            ),
            questionary.Choice(
                title="OpenAI",
                value="openai",
                description="GPT-4, GPT-4o, GPT-4o-mini, o3-mini, etc",
            ),
            questionary.Choice(
                title="Other / I'll configure later",
                value="other",
                description="Configure manually in config.yaml",
            ),
        ],
        style=custom_style,
    ).ask_async()

    metadata.save_choice("provider", provider)
    metadata.mark_step("provider_selection")

    # Choose model based on provider
    default_model = "anthropic/claude-sonnet-4-20250514"

    if provider == "anthropic":
        model = await questionary.select(
            "Which Claude model?",
            choices=[
                questionary.Choice(
                    title="Claude Sonnet 4 (Recommended)",
                    value="anthropic/claude-sonnet-4-20250514",
                    description="Best balance of speed, quality, and cost",
                ),
                questionary.Choice(
                    title="Claude Opus 4",
                    value="anthropic/claude-opus-4-20250514",
                    description="Most capable, higher cost",
                ),
                questionary.Choice(
                    title="Claude Haiku 3.5",
                    value="anthropic/claude-3-5-haiku-20241022",
                    description="Fastest, lowest cost",
                ),
            ],
            style=custom_style,
        ).ask_async()
        default_model = model
        metadata.save_choice("model", model)

    elif provider == "openai":
        model = await questionary.select(
            "Which OpenAI model?",
            choices=[
                questionary.Choice(
                    title="GPT-4o (Recommended)",
                    value="openai/gpt-4o",
                    description="Latest GPT-4 model, great performance",
                ),
                questionary.Choice(
                    title="GPT-4o-mini",
                    value="openai/gpt-4o-mini",
                    description="Faster and cheaper variant",
                ),
                questionary.Choice(
                    title="o3-mini",
                    value="openai/o3-mini",
                    description="Advanced reasoning model",
                ),
            ],
            style=custom_style,
        ).ask_async()
        default_model = model
        metadata.save_choice("model", model)

    # Step 3: API Key
    console.print()
    console.print("[bold]Step 2: Set up your API key[/bold]")

    if provider != "other":
        set_api_key = await questionary.confirm(
            f"Do you have an API key for {provider.title()}?",
            default=True,
            style=custom_style,
        ).ask_async()

        if set_api_key:
            console.print(
                f"\n[dim]Your API key will be encrypted and stored securely in ~/.inkarms/secrets/[/dim]"
            )

            api_key = await questionary.password(
                f"Enter your {provider.title()} API key:",
                style=custom_style,
            ).ask_async()

            if api_key:
                try:
                    secrets = SecretsManager()
                    secrets.set(provider, api_key)
                    console.print(f"[green]✓ API key saved securely[/green]\n")
                    metadata.mark_step("api_key")
                except Exception as e:
                    console.print(f"[red]✗ Failed to save API key: {e}[/red]\n")
        else:
            console.print(
                f"\n[yellow]⚠ You'll need to set your API key later:[/yellow]"
            )
            console.print(f"[dim]   inkarms config set-secret {provider}[/dim]")
            console.print(f"[dim]   OR export {provider.upper()}_API_KEY='your-key'[/dim]\n")

    # Step 4: Security sandbox
    console.print("[bold]Step 3: Security settings[/bold]")
    console.print("[dim]InkArms can execute commands - let's configure safety[/dim]\n")

    sandbox_mode = await questionary.select(
        "How should InkArms handle command execution?",
        choices=[
            questionary.Choice(
                title="Whitelist mode (Recommended)",
                value="whitelist",
                description="Only pre-approved commands can run (safest)",
            ),
            questionary.Choice(
                title="Prompt mode",
                value="prompt",
                description="Ask for confirmation before each command",
            ),
            questionary.Choice(
                title="Blacklist mode",
                value="blacklist",
                description="Block dangerous commands only (less safe)",
            ),
            questionary.Choice(
                title="Disabled",
                value="disabled",
                description="No safety checks (not recommended)",
            ),
        ],
        style=custom_style,
    ).ask_async()

    metadata.save_choice("sandbox_mode", sandbox_mode)
    metadata.mark_step("sandbox_config")

    if sandbox_mode == "disabled":
        console.print()
        understand_risk = await questionary.confirm(
            "[yellow]⚠ Disabling the sandbox allows unrestricted command execution.\n"
            "   This could be dangerous if the AI makes mistakes or is misused.\n"
            "   Do you understand and accept this risk?[/yellow]",
            default=False,
            style=custom_style,
        ).ask_async()

        if not understand_risk:
            console.print("[yellow]Switching to whitelist mode for safety.[/yellow]\n")
            sandbox_mode = "whitelist"
            metadata.save_choice("sandbox_mode", "whitelist")

    # Step 5: Enable tools
    console.print()
    console.print("[bold]Step 4: Tool capabilities[/bold]")
    console.print(
        "[dim]InkArms can use tools: HTTP requests, Python eval, Git, file operations[/dim]\n"
    )

    enable_tools = await questionary.confirm(
        "Enable tool use? (Allows AI to execute tools autonomously)",
        default=True,
        style=custom_style,
    ).ask_async()

    metadata.save_choice("enable_tools", enable_tools)
    metadata.mark_step("tools_config")

    # Create configuration
    config_dict = {
        "providers": {
            "default": default_model,
            "fallback": [],
            "aliases": {},
        },
        "agent": {
            "enable_tools": enable_tools,
            "tool_approval_mode": "auto" if enable_tools else "disabled",
            "max_iterations": 10,
        },
        "security": {
            "sandbox": {
                "enable": sandbox_mode != "disabled",
                "mode": sandbox_mode,
            },
            "whitelist": [
                "ls",
                "cat",
                "head",
                "tail",
                "grep",
                "find",
                "echo",
                "git",
                "python",
                "npm",
                "node",
            ],
            "blacklist": [
                "rm -rf",
                "sudo",
                "chmod",
                "chown",
                "dd",
                "curl | bash",
                "wget | bash",
            ],
            "audit_log": {
                "enable": True,
                "path": "~/.inkarms/audit.jsonl",
                "rotation": "daily",
                "retention_days": 90,
            },
        },
        "context": {
            "auto_compact_threshold": 0.70,
            "handoff_threshold": 0.85,
            "compaction": {
                "strategy": "summarize",
                "preserve_recent_turns": 5,
            },
            "memory_path": "~/.inkarms/memory",
            "daily_logs": True,
        },
        "skills": {
            "local_path": "~/.inkarms/skills",
            "project_path": "./.inkarms/skills",
            "smart_index": {
                "enable": True,
                "mode": "keyword",
            },
        },
        "cost": {
            "budgets": {
                "daily": None,
                "weekly": None,
                "monthly": None,
            },
            "alerts": {
                "warning_threshold": 0.80,
                "block_on_exceed": False,
            },
        },
        "tui": {
            "enable": True,
            "theme": "dark",
            "keybindings": "default",
        },
        "general": {
            "default_profile": None,
            "output": {
                "format": "rich",
                "color": True,
                "verbose": False,
            },
        },
    }

    # Write configuration
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Writing configuration...", total=1)

        import yaml

        config_path = get_global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Add header comment
        config_yaml = f"""# InkArms Configuration
# Generated by QuickStart wizard on {metadata.started_at.strftime('%Y-%m-%d %H:%M:%S')}
# Edit this file or use 'inkarms config set <key> <value>'

{yaml.dump(config_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)}
"""

        config_path.write_text(config_yaml, encoding="utf-8")
        progress.update(task, completed=1)
        results["config_created"] = True
        results["config_path"] = config_path

    # Success message
    console.print()
    console.print(
        Panel.fit(
            "[bold green]🎉 Setup complete![/bold green]\n\n"
            f"Configuration saved to: [cyan]{config_path}[/cyan]\n"
            f"Provider: [cyan]{provider.title()}[/cyan]\n"
            f"Model: [cyan]{default_model}[/cyan]\n"
            f"Security: [cyan]{sandbox_mode} mode[/cyan]\n"
            f"Tools: [cyan]{'enabled' if enable_tools else 'disabled'}[/cyan]",
            border_style="green",
        )
    )

    console.print("\n[bold]Next steps:[/bold]")
    console.print(
        "  1. [dim]Test your setup:[/dim] inkarms run \"Hello! Introduce yourself\""
    )
    console.print("  2. [dim]View config:[/dim] inkarms config show")
    console.print("  3. [dim]Edit config:[/dim] inkarms config edit")

    if provider != "other" and not set_api_key:
        console.print(
            f"\n[yellow]⚠ Don't forget to set your API key:[/yellow] inkarms config set-secret {provider}"
        )

    console.print()

    results["metadata"] = metadata
    return results


async def _run_advanced_wizard(metadata: WizardMetadata, force: bool) -> dict[str, Any]:
    """
    Run the Advanced wizard (comprehensive configuration).

    Args:
        metadata: Wizard metadata tracker
        force: If True, overwrite existing config

    Returns:
        Dictionary with setup results
    """
    console.print()
    console.print("[bold cyan]🔧 Advanced Setup Mode[/bold cyan]")
    console.print("[dim]Comprehensive configuration with full control over all settings[/dim]\n")

    results = {"mode": "advanced", "config_created": False, "directories": {}}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: Create directories
        task = progress.add_task("Creating directories...", total=1)
        results["directories"] = create_directory_structure()
        progress.update(task, completed=1)
        metadata.mark_step("directories")

    console.print("[green]✓ Directories created[/green]\n")

    # Section 1: Provider Configuration
    console.print("[bold cyan]━━━ Section 1: AI Provider Configuration ━━━[/bold cyan]\n")

    # Primary provider
    provider = await questionary.select(
        "Primary AI provider:",
        choices=[
            questionary.Choice("Anthropic Claude", "anthropic"),
            questionary.Choice("OpenAI", "openai"),
            questionary.Choice("Google (Gemini)", "google"),
            questionary.Choice("Azure OpenAI", "azure"),
            questionary.Choice("Other / Manual", "other"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("provider", provider)

    # Choose model
    default_model = "anthropic/claude-sonnet-4-20250514"
    if provider == "anthropic":
        model = await questionary.select(
            "Primary Claude model:",
            choices=[
                questionary.Choice("Claude Sonnet 4 (Best balance)", "anthropic/claude-sonnet-4-20250514"),
                questionary.Choice("Claude Opus 4 (Most capable)", "anthropic/claude-opus-4-20250514"),
                questionary.Choice("Claude Haiku 3.5 (Fastest)", "anthropic/claude-3-5-haiku-20241022"),
            ],
            style=custom_style,
        ).ask_async()
        default_model = model
    elif provider == "openai":
        model = await questionary.select(
            "Primary OpenAI model:",
            choices=[
                questionary.Choice("GPT-4o", "openai/gpt-4o"),
                questionary.Choice("GPT-4o-mini", "openai/gpt-4o-mini"),
                questionary.Choice("o3-mini", "openai/o3-mini"),
                questionary.Choice("GPT-4 Turbo", "openai/gpt-4-turbo"),
            ],
            style=custom_style,
        ).ask_async()
        default_model = model
    elif provider == "google":
        model = await questionary.select(
            "Primary Gemini model:",
            choices=[
                questionary.Choice("Gemini 2.0 Flash", "google/gemini-2.0-flash-exp"),
                questionary.Choice("Gemini 1.5 Pro", "google/gemini-1.5-pro"),
                questionary.Choice("Gemini 1.5 Flash", "google/gemini-1.5-flash"),
            ],
            style=custom_style,
        ).ask_async()
        default_model = model

    metadata.save_choice("model", default_model)

    # Fallback models
    setup_fallback = await questionary.confirm(
        "Configure fallback models? (Used if primary fails)",
        default=False,
        style=custom_style,
    ).ask_async()

    fallback_models = []
    if setup_fallback:
        fallback_choice = await questionary.select(
            "Fallback strategy:",
            choices=[
                questionary.Choice("Same provider, cheaper model", "same_provider"),
                questionary.Choice("Different provider", "different_provider"),
                questionary.Choice("Custom fallback chain", "custom"),
                questionary.Choice("Skip fallbacks", "skip"),
            ],
            style=custom_style,
        ).ask_async()

        if fallback_choice == "same_provider":
            if provider == "anthropic":
                fallback_models = ["anthropic/claude-3-5-haiku-20241022"]
            elif provider == "openai":
                fallback_models = ["openai/gpt-4o-mini"]
        elif fallback_choice == "different_provider":
            alt_provider = await questionary.select(
                "Fallback provider:",
                choices=[
                    questionary.Choice("Anthropic", "anthropic/claude-3-5-haiku-20241022"),
                    questionary.Choice("OpenAI", "openai/gpt-4o-mini"),
                    questionary.Choice("Google", "google/gemini-1.5-flash"),
                ],
                style=custom_style,
            ).ask_async()
            fallback_models = [alt_provider]

    metadata.save_choice("fallback_models", fallback_models)

    # Model aliases
    setup_aliases = await questionary.confirm(
        "Create model aliases? (Shortcuts like 'fast', 'smart')",
        default=True,
        style=custom_style,
    ).ask_async()

    aliases = {}
    if setup_aliases:
        aliases = {
            "fast": "anthropic/claude-3-5-haiku-20241022",
            "smart": "anthropic/claude-sonnet-4-20250514",
            "best": "anthropic/claude-opus-4-20250514",
        }

    metadata.save_choice("aliases", aliases)

    # API Key setup
    console.print()
    if provider != "other":
        set_api_key = await questionary.confirm(
            f"Set API key for {provider.title()}?",
            default=True,
            style=custom_style,
        ).ask_async()

        if set_api_key:
            api_key = await questionary.password(
                f"Enter {provider.title()} API key:",
                style=custom_style,
            ).ask_async()

            if api_key:
                try:
                    secrets = SecretsManager()
                    secrets.set(provider, api_key)
                    console.print(f"[green]✓ API key saved[/green]\n")
                except Exception as e:
                    console.print(f"[red]✗ Failed: {e}[/red]\n")

    # Section 2: Context & Memory Management
    console.print("[bold cyan]━━━ Section 2: Context & Memory Management ━━━[/bold cyan]\n")

    compaction_strategy = await questionary.select(
        "Context compaction strategy (when conversation gets too long):",
        choices=[
            questionary.Choice(
                "Summarize (Recommended)",
                "summarize",
                "AI summarizes old messages to compress context",
            ),
            questionary.Choice(
                "Sliding Window",
                "sliding_window",
                "Keep recent N turns, drop oldest",
            ),
            questionary.Choice(
                "Truncate",
                "truncate",
                "Simple truncation of old messages",
            ),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("compaction_strategy", compaction_strategy)

    auto_compact_threshold = await questionary.select(
        "Auto-compact threshold (% of context used before compaction):",
        choices=[
            questionary.Choice("60% (Early, saves costs)", "0.60"),
            questionary.Choice("70% (Balanced)", "0.70"),
            questionary.Choice("80% (Later, more context)", "0.80"),
            questionary.Choice("90% (Rarely compact)", "0.90"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("auto_compact_threshold", float(auto_compact_threshold))

    preserve_turns = await questionary.select(
        "Recent turns to preserve during compaction:",
        choices=[
            questionary.Choice("3 turns", "3"),
            questionary.Choice("5 turns (Recommended)", "5"),
            questionary.Choice("10 turns", "10"),
            questionary.Choice("15 turns", "15"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("preserve_turns", int(preserve_turns))

    # Section 3: Security & Sandbox
    console.print("\n[bold cyan]━━━ Section 3: Security & Sandbox ━━━[/bold cyan]\n")

    sandbox_mode = await questionary.select(
        "Command execution sandbox mode:",
        choices=[
            questionary.Choice(
                "Whitelist (Recommended)",
                "whitelist",
                "Only pre-approved commands can run",
            ),
            questionary.Choice(
                "Prompt",
                "prompt",
                "Ask for confirmation before each command",
            ),
            questionary.Choice(
                "Blacklist",
                "blacklist",
                "Block dangerous commands only",
            ),
            questionary.Choice(
                "Disabled (Unsafe)",
                "disabled",
                "No safety checks - USE WITH CAUTION",
            ),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("sandbox_mode", sandbox_mode)

    # Risk acknowledgement for disabled mode
    if sandbox_mode == "disabled":
        console.print()
        understand_risk = await questionary.confirm(
            "[yellow]⚠ WARNING: Disabling sandbox allows unrestricted command execution.\n"
            "   The AI could potentially:\n"
            "   • Delete files\n"
            "   • Modify system settings\n"
            "   • Execute any shell command\n"
            "   Do you understand and accept this risk?[/yellow]",
            default=False,
            style=custom_style,
        ).ask_async()

        if not understand_risk:
            console.print("[yellow]Switching to whitelist mode for safety.[/yellow]\n")
            sandbox_mode = "whitelist"

    # Customize whitelist
    customize_whitelist = False
    whitelist_commands = [
        "ls", "cat", "head", "tail", "grep", "find", "echo",
        "git", "python", "pip", "npm", "node", "mkdir", "cp", "mv",
    ]

    if sandbox_mode == "whitelist":
        customize_whitelist = await questionary.confirm(
            "Customize allowed commands?",
            default=False,
            style=custom_style,
        ).ask_async()

        if customize_whitelist:
            console.print("[dim]Current whitelist: ls, cat, head, tail, grep, find, echo, git, python, pip, npm, node, mkdir, cp, mv[/dim]")
            add_custom = await questionary.text(
                "Additional commands to allow (comma-separated):",
                style=custom_style,
            ).ask_async()

            if add_custom:
                custom_commands = [cmd.strip() for cmd in add_custom.split(",")]
                whitelist_commands.extend(custom_commands)

    metadata.save_choice("whitelist", whitelist_commands)

    # Audit logging
    audit_rotation = await questionary.select(
        "Audit log rotation:",
        choices=[
            questionary.Choice("Daily (Recommended)", "daily"),
            questionary.Choice("Weekly", "weekly"),
            questionary.Choice("Monthly", "monthly"),
            questionary.Choice("Size-based (10MB)", "size"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("audit_rotation", audit_rotation)

    audit_retention = await questionary.select(
        "Audit log retention (days):",
        choices=[
            questionary.Choice("30 days", "30"),
            questionary.Choice("90 days (Recommended)", "90"),
            questionary.Choice("180 days", "180"),
            questionary.Choice("365 days (1 year)", "365"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("audit_retention", int(audit_retention))

    # Section 4: Tool Configuration
    console.print("\n[bold cyan]━━━ Section 4: Tool Configuration ━━━[/bold cyan]\n")

    enable_tools = await questionary.confirm(
        "Enable tool use? (HTTP, Python, Git, File operations)",
        default=True,
        style=custom_style,
    ).ask_async()
    metadata.save_choice("enable_tools", enable_tools)

    tool_approval_mode = "disabled"
    max_iterations = 5

    if enable_tools:
        tool_approval_mode = await questionary.select(
            "Tool approval mode:",
            choices=[
                questionary.Choice(
                    "Auto (Recommended)",
                    "auto",
                    "Tools execute automatically",
                ),
                questionary.Choice(
                    "Manual",
                    "manual",
                    "Approve dangerous tools before execution",
                ),
                questionary.Choice(
                    "Disabled",
                    "disabled",
                    "No tools allowed",
                ),
            ],
            style=custom_style,
        ).ask_async()
        metadata.save_choice("tool_approval_mode", tool_approval_mode)

        max_iterations_choice = await questionary.select(
            "Maximum tool iterations (prevents infinite loops):",
            choices=[
                questionary.Choice("5 iterations", "5"),
                questionary.Choice("10 iterations (Recommended)", "10"),
                questionary.Choice("15 iterations", "15"),
                questionary.Choice("20 iterations", "20"),
            ],
            style=custom_style,
        ).ask_async()
        max_iterations = int(max_iterations_choice)
        metadata.save_choice("max_iterations", max_iterations)

    # Section 5: Skills Configuration
    console.print("\n[bold cyan]━━━ Section 5: Skills Configuration ━━━[/bold cyan]\n")

    skill_index_mode = await questionary.select(
        "Skill indexing mode:",
        choices=[
            questionary.Choice(
                "Keyword (Recommended)",
                "keyword",
                "Fast keyword-based matching",
            ),
            questionary.Choice(
                "LLM",
                "llm",
                "AI-powered semantic matching (slower, more accurate)",
            ),
            questionary.Choice(
                "Off",
                "off",
                "No automatic skill discovery",
            ),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("skill_index_mode", skill_index_mode)

    # Section 6: Cost Management
    console.print("\n[bold cyan]━━━ Section 6: Cost Management ━━━[/bold cyan]\n")

    setup_budgets = await questionary.confirm(
        "Set up cost budgets?",
        default=False,
        style=custom_style,
    ).ask_async()

    daily_budget = None
    weekly_budget = None
    monthly_budget = None

    if setup_budgets:
        daily_budget_str = await questionary.text(
            "Daily budget (USD, or blank for none):",
            default="",
            style=custom_style,
        ).ask_async()

        if daily_budget_str:
            try:
                daily_budget = float(daily_budget_str)
            except ValueError:
                pass

        monthly_budget_str = await questionary.text(
            "Monthly budget (USD, or blank for none):",
            default="",
            style=custom_style,
        ).ask_async()

        if monthly_budget_str:
            try:
                monthly_budget = float(monthly_budget_str)
            except ValueError:
                pass

    metadata.save_choice("budgets", {
        "daily": daily_budget,
        "weekly": weekly_budget,
        "monthly": monthly_budget,
    })

    # Section 7: TUI Preferences
    console.print("\n[bold cyan]━━━ Section 7: TUI Preferences ━━━[/bold cyan]\n")

    tui_theme = await questionary.select(
        "TUI theme:",
        choices=[
            questionary.Choice("Dark (Recommended)", "dark"),
            questionary.Choice("Light", "light"),
            questionary.Choice("Auto (system)", "auto"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("tui_theme", tui_theme)

    tui_keybindings = await questionary.select(
        "TUI keybindings:",
        choices=[
            questionary.Choice("Default", "default"),
            questionary.Choice("Vim", "vim"),
            questionary.Choice("Emacs", "emacs"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("tui_keybindings", tui_keybindings)

    # Section 8: General Settings
    console.print("\n[bold cyan]━━━ Section 8: General Settings ━━━[/bold cyan]\n")

    output_format = await questionary.select(
        "Output format:",
        choices=[
            questionary.Choice("Rich (Colored, formatted)", "rich"),
            questionary.Choice("Plain (No colors)", "plain"),
            questionary.Choice("JSON", "json"),
        ],
        style=custom_style,
    ).ask_async()
    metadata.save_choice("output_format", output_format)

    verbose_mode = await questionary.confirm(
        "Enable verbose output?",
        default=False,
        style=custom_style,
    ).ask_async()
    metadata.save_choice("verbose", verbose_mode)

    # Build configuration
    console.print()
    console.print("[bold]Building configuration...[/bold]")

    config_dict = {
        "providers": {
            "default": default_model,
            "fallback": fallback_models,
            "aliases": aliases,
        },
        "agent": {
            "enable_tools": enable_tools,
            "tool_approval_mode": tool_approval_mode,
            "max_iterations": max_iterations,
            "timeout_per_iteration": 120,
            "allowed_tools": [],
            "blocked_tools": [],
        },
        "context": {
            "auto_compact_threshold": metadata.config_choices.get("auto_compact_threshold", 0.70),
            "handoff_threshold": 0.85,
            "compaction": {
                "strategy": compaction_strategy,
                "preserve_recent_turns": metadata.config_choices.get("preserve_turns", 5),
            },
            "memory_path": "~/.inkarms/memory",
            "daily_logs": True,
        },
        "security": {
            "sandbox": {
                "enable": sandbox_mode != "disabled",
                "mode": sandbox_mode,
            },
            "whitelist": whitelist_commands,
            "blacklist": [
                "rm -rf",
                "sudo",
                "chmod",
                "chown",
                "dd",
                "curl | bash",
                "wget | bash",
            ],
            "audit_log": {
                "enable": True,
                "path": "~/.inkarms/audit.jsonl",
                "rotation": audit_rotation,
                "retention_days": metadata.config_choices.get("audit_retention", 90),
            },
        },
        "skills": {
            "local_path": "~/.inkarms/skills",
            "project_path": "./.inkarms/skills",
            "smart_index": {
                "enable": skill_index_mode != "off",
                "mode": skill_index_mode,
            },
        },
        "cost": {
            "budgets": metadata.config_choices.get("budgets", {
                "daily": None,
                "weekly": None,
                "monthly": None,
            }),
            "alerts": {
                "warning_threshold": 0.80,
                "block_on_exceed": False,
            },
        },
        "tui": {
            "enable": True,
            "theme": tui_theme,
            "keybindings": tui_keybindings,
            "chat": {
                "show_timestamps": True,
                "show_token_count": True,
                "show_cost": True,
                "markdown_rendering": True,
                "code_highlighting": True,
            },
            "status_bar": {
                "show_model": True,
                "show_context_usage": True,
                "show_session_cost": True,
            },
        },
        "general": {
            "default_profile": None,
            "output": {
                "format": output_format,
                "color": output_format != "plain",
                "verbose": verbose_mode,
            },
            "storage": {
                "backend": "file",
            },
        },
    }

    # Write configuration
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Writing configuration...", total=1)

        import yaml

        config_path = get_global_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Add header comment
        config_yaml = f"""# InkArms Configuration
# Generated by Advanced wizard on {metadata.started_at.strftime('%Y-%m-%d %H:%M:%S')}
# Edit this file or use 'inkarms config set <key> <value>'

{yaml.dump(config_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)}
"""

        config_path.write_text(config_yaml, encoding="utf-8")
        progress.update(task, completed=1)
        results["config_created"] = True
        results["config_path"] = config_path

    # Success summary
    console.print()
    console.print(
        Panel.fit(
            "[bold green]🎉 Advanced Setup Complete![/bold green]\n\n"
            f"Configuration: [cyan]{config_path}[/cyan]\n\n"
            "[bold]Your Configuration:[/bold]\n"
            f"• Provider: [cyan]{provider.title()}[/cyan] ({default_model})\n"
            f"• Fallbacks: [cyan]{len(fallback_models)} models[/cyan]\n"
            f"• Security: [cyan]{sandbox_mode} mode[/cyan]\n"
            f"• Tools: [cyan]{'enabled' if enable_tools else 'disabled'}[/cyan] ({tool_approval_mode} approval)\n"
            f"• Compaction: [cyan]{compaction_strategy}[/cyan] at {int(metadata.config_choices.get('auto_compact_threshold', 0.7) * 100)}%\n"
            f"• Skills: [cyan]{skill_index_mode} indexing[/cyan]\n"
            f"• TUI: [cyan]{tui_theme} theme, {tui_keybindings} keys[/cyan]",
            border_style="green",
        )
    )

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. [dim]Test your setup:[/dim] inkarms run \"Hello!\"")
    console.print("  2. [dim]View config:[/dim] inkarms config show")
    console.print("  3. [dim]Edit manually:[/dim] inkarms config edit")

    if provider != "other" and not set_api_key:
        console.print(
            f"\n[yellow]⚠ Don't forget to set your API key:[/yellow] inkarms config set-secret {provider}"
        )

    console.print()

    results["metadata"] = metadata
    return results


def run_wizard_sync(force: bool = False) -> dict[str, Any]:
    """
    Synchronous wrapper for run_interactive_wizard.

    Args:
        force: If True, overwrite existing configuration

    Returns:
        Dictionary with wizard results
    """
    import asyncio

    return asyncio.run(run_interactive_wizard(force=force))
