"""
QuickStart configuration wizard screens.

Provides a fast 4-step setup experience.
"""

from dataclasses import dataclass, field
from datetime import datetime

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioButton, RadioSet

from inkarms.config.providers import PROVIDERS, get_default_model
from inkarms.secrets import SecretsManager
from inkarms.storage.paths import get_global_config_path


@dataclass
class WizardState:
    """Shared state across wizard screens."""

    mode: str = "quickstart"  # "quickstart" or "advanced"
    started_at: datetime = field(default_factory=datetime.now)

    # Provider settings
    provider: str = "anthropic"
    model: str = get_default_model()
    api_key: str = ""
    api_key_saved: bool = False

    # Security settings
    sandbox_mode: str = "whitelist"
    understand_risk: bool = False

    # Tool settings
    enable_tools: bool = True
    tool_approval_mode: str = "auto"

    # Additional settings (for advanced mode)
    fallback_models: list = field(default_factory=list)
    aliases: dict = field(default_factory=dict)
    compaction_strategy: str = "summarize"
    auto_compact_threshold: float = 0.70
    preserve_turns: int = 5
    audit_rotation: str = "daily"
    audit_retention: int = 90
    skill_index_mode: str = "keyword"
    daily_budget: float | None = None
    monthly_budget: float | None = None
    tui_theme: str = "dark"
    tui_keybindings: str = "default"
    output_format: str = "rich"
    verbose: bool = False

    def to_config_dict(self) -> dict:
        """Convert wizard state to configuration dictionary.

        Returns:
            Configuration dictionary ready for YAML serialization
        """
        config = {
            "providers": {
                "default": self.model,
                "fallback": self.fallback_models,
                "aliases": self.aliases,
            },
            "agent": {
                "enable_tools": self.enable_tools,
                "tool_approval_mode": self.tool_approval_mode if self.enable_tools else "disabled",
                "max_iterations": 10,
                "timeout_per_iteration": 120,
                "allowed_tools": [],
                "blocked_tools": [],
            },
            "context": {
                "auto_compact_threshold": self.auto_compact_threshold,
                "handoff_threshold": 0.85,
                "compaction": {
                    "strategy": self.compaction_strategy,
                    "preserve_recent_turns": self.preserve_turns,
                },
                "memory_path": "~/.inkarms/memory",
                "daily_logs": True,
            },
            "security": {
                "sandbox": {
                    "enable": self.sandbox_mode != "disabled",
                    "mode": self.sandbox_mode,
                },
                "whitelist": [
                    "ls", "cat", "head", "tail", "grep", "find", "echo",
                    "git", "python", "pip", "npm", "node", "mkdir", "cp", "mv",
                ],
                "blacklist": [
                    "rm -rf", "sudo", "chmod", "chown", "dd",
                    "curl | bash", "wget | bash",
                ],
                "audit_log": {
                    "enable": True,
                    "path": "~/.inkarms/audit.jsonl",
                    "rotation": self.audit_rotation,
                    "retention_days": self.audit_retention,
                },
            },
            "skills": {
                "local_path": "~/.inkarms/skills",
                "project_path": "./.inkarms/skills",
                "smart_index": {
                    "enable": self.skill_index_mode != "off",
                    "mode": self.skill_index_mode,
                },
            },
            "cost": {
                "budgets": {
                    "daily": self.daily_budget,
                    "weekly": None,
                    "monthly": self.monthly_budget,
                },
                "alerts": {
                    "warning_threshold": 0.80,
                    "block_on_exceed": False,
                },
            },
            "tui": {
                "enable": True,
                "theme": self.tui_theme,
                "keybindings": self.tui_keybindings,
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
                    "format": self.output_format,
                    "color": self.output_format != "plain",
                    "verbose": self.verbose,
                },
                "storage": {
                    "backend": "file",
                },
            },
        }

        return config


class ProviderSelectionScreen(Screen):
    """QuickStart Step 1: Choose AI provider."""

    CSS = """
    ProviderSelectionScreen {
        align: center middle;
    }

    #provider-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #step-header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #step-description {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    RadioSet {
        border: tall $primary;
        background: $panel;
        padding: 1;
        margin: 1 0;
    }

    RadioButton {
        margin: 1 2;
    }

    .provider-description {
        color: $text-muted;
        margin-left: 4;
    }

    #model-section {
        margin-top: 2;
    }

    #button-bar {
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 20;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize provider selection screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the provider selection screen."""
        yield Header(show_clock=True)

        with Container(id="provider-container"):
            yield Label("⚡ QuickStart - Step 1 of 4", id="step-header")
            yield Label("Choose your AI provider", id="step-description")

            with RadioSet(id="provider-choice"):
                # Dynamically populate providers
                for provider_id, provider in PROVIDERS.items():
                    # Only show recommended or popular providers in QuickStart?
                    # For now, show all defined providers
                    label = provider.name
                    if "Recommended" in provider.description:
                        label += " (Recommended)"

                    yield RadioButton(label, id=provider_id, value=(provider_id == "anthropic"))
                    yield Label(provider.description, classes="provider-description")

                yield RadioButton("Other / Configure Later", id="other")
                yield Label(
                    "Configure manually in config.yaml",
                    classes="provider-description"
                )

            with Container(id="model-section"):
                yield Label("Model:", id="model-label")
                with RadioSet(id="model-choice"):
                    # Models populated based on provider selection
                    pass

            with Horizontal(id="button-bar"):
                yield Button("Cancel", id="cancel", variant="error")
                yield Button("Next →", id="next", variant="primary")

        yield Footer()

    def on_mount(self) -> None:
        """Mount event - populate initial model choices."""
        self._update_model_choices("anthropic")

    @on(RadioSet.Changed, "#provider-choice")
    def on_provider_changed(self, event: RadioSet.Changed) -> None:
        """Handle provider selection change."""
        if event.pressed:
            provider_id = event.pressed.id
            self._update_model_choices(provider_id)

    def _update_model_choices(self, provider_id: str | None) -> None:
        """Update model choices based on provider.

        Args:
            provider_id: Provider ID (anthropic, openai, other)
        """
        model_set = self.query_one("#model-choice", RadioSet)
        model_set.remove_children()

        if not provider_id or provider_id == "other":
            # Other provider - will configure manually
            model_label = self.query_one("#model-label", Label)
            model_label.update("(Configure manually later)")
            return

        # Reset label
        model_label = self.query_one("#model-label", Label)
        model_label.update("Model:")

        if provider_id in PROVIDERS:
            provider = PROVIDERS[provider_id]
            for model in provider.models:
                if model.deprecated:
                    continue

                label = model.name
                if model.recommended:
                    label += " (Recommended)"
                elif model.description:
                    label += f" ({model.description})"

                # Default to recommended model
                is_default = model.recommended

                model_set.mount(RadioButton(label, id=model.id, value=is_default))

    @on(Button.Pressed, "#next")
    def on_next(self) -> None:
        """Handle Next button - save selections and move to next screen."""
        # Get selected provider
        provider_set = self.query_one("#provider-choice", RadioSet)
        if provider_set.pressed_button:
            provider_id = provider_set.pressed_button.id
            self.state.provider = provider_id

            # Map model selection to full model name
            model_set = self.query_one("#model-choice", RadioSet)
            if model_set.pressed_button and provider_id in PROVIDERS:
                model_id = model_set.pressed_button.id
                # Construct full model ID: provider/model
                self.state.model = f"{provider_id}/{model_id}"

        # Move to API key screen
        self.app.push_screen(APIKeySetupScreen(self.state))

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        """Handle Cancel button."""
        self.app.exit(message="Setup cancelled")


class APIKeySetupScreen(Screen):
    """QuickStart Step 2: Set up API key."""

    CSS = """
    APIKeySetupScreen {
        align: center middle;
    }

    #apikey-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #step-header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #step-description {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    #info-box {
        background: $panel;
        border: tall $primary-darken-2;
        padding: 1;
        margin: 2 0;
    }

    Input {
        margin: 1 0;
    }

    #status-message {
        text-align: center;
        margin: 1 0;
        height: 3;
    }

    #button-bar {
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 20;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize API key setup screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the API key setup screen."""
        yield Header(show_clock=True)

        with Container(id="apikey-container"):
            yield Label("⚡ QuickStart - Step 2 of 4", id="step-header")
            yield Label("Set up your API key", id="step-description")

            provider_name = self.state.provider.replace("_", " ").title()

            if self.state.provider == "github_copilot":
                # GitHub Copilot uses OAuth
                with Container(id="info-box"):
                    yield Label(
                        "GitHub Copilot uses OAuth authentication.\n\n"
                        "On first use, you'll be prompted to authenticate:\n"
                        "  1. InkArms will display a device code\n"
                        "  2. Visit github.com/login/device\n"
                        "  3. Enter the code to authorize\n\n"
                        "Credentials will be stored locally automatically.\n\n"
                        "Requirements:\n"
                        "  • GitHub account with Copilot subscription\n"
                        "  • Active Copilot access",
                        markup=False
                    )
                yield Label("OAuth authentication will happen automatically on first use.")
            elif self.state.provider != "other":
                # Standard API key providers
                with Container(id="info-box"):
                    yield Label(
                        f"Your {provider_name} API key will be encrypted and stored securely\n"
                        f"in ~/.inkarms/secrets/\n\n"
                        f"You can also set it later with:\n"
                        f"  inkarms config set-secret {self.state.provider}",
                        markup=False
                    )
                yield Label(f"Enter your {provider_name} API key (or leave blank to skip):")
                yield Input(
                    placeholder="sk-ant-... or sk-...",
                    password=True,
                    id="api-key-input"
                )
            else:
                with Container(id="info-box"):
                    yield Label(
                        "API key will be configured manually later.",
                        markup=False
                    )
                yield Label("API key setup skipped (provider will be configured manually)")

            yield Label("", id="status-message")

            with Horizontal(id="button-bar"):
                yield Button("← Back", id="back", variant="default")
                yield Button("Skip", id="skip", variant="default")
                yield Button("Next →", id="next", variant="primary")

        yield Footer()

    @on(Button.Pressed, "#next")
    async def on_next(self) -> None:
        """Handle Next button - save API key and move to next screen."""
        if self.state.provider in ("other", "github_copilot"):
            # Skip API key for "other" provider and GitHub Copilot (uses OAuth)
            self.app.push_screen(SecurityConfigScreen(self.state))
            return

        api_key_input = self.query_one("#api-key-input", Input)
        api_key = api_key_input.value.strip()

        if api_key:
            # Save API key
            try:
                secrets = SecretsManager()
                secrets.set(self.state.provider, api_key)
                self.state.api_key_saved = True

                # Show success message
                status = self.query_one("#status-message", Label)
                status.update("[green]✓ API key saved successfully[/green]")

                # Move to next screen after brief delay
                self.set_timer(1.0, lambda: self.app.push_screen(SecurityConfigScreen(self.state)))

            except Exception as e:
                # Show error message
                status = self.query_one("#status-message", Label)
                status.update(f"[red]✗ Failed to save API key: {e}[/red]")
        else:
            # No API key provided - skip
            self.app.push_screen(SecurityConfigScreen(self.state))

    @on(Button.Pressed, "#skip")
    def on_skip(self) -> None:
        """Handle Skip button."""
        self.app.push_screen(SecurityConfigScreen(self.state))

    @on(Button.Pressed, "#back")
    def on_back(self) -> None:
        """Handle Back button."""
        self.app.pop_screen()


class SecurityConfigScreen(Screen):
    """QuickStart Step 3: Configure security sandbox."""

    CSS = """
    SecurityConfigScreen {
        align: center middle;
    }

    #security-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #step-header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #step-description {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    RadioSet {
        border: tall $primary;
        background: $panel;
        padding: 1;
        margin: 1 0;
    }

    RadioButton {
        margin: 1 2;
    }

    .mode-description {
        color: $text-muted;
        margin-left: 4;
        margin-bottom: 1;
    }

    #risk-warning {
        background: $error-darken-2;
        border: tall $error;
        padding: 1;
        margin: 2 0;
        display: none;
    }

    #button-bar {
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 20;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize security config screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the security configuration screen."""
        yield Header(show_clock=True)

        with Container(id="security-container"):
            yield Label("⚡ QuickStart - Step 3 of 4", id="step-header")
            yield Label("Configure security settings", id="step-description")

            yield Label("How should InkArms handle command execution?")

            with RadioSet(id="sandbox-choice"):
                yield RadioButton("Whitelist mode (Recommended)", id="whitelist", value=True)
                yield Label(
                    "Only pre-approved commands can run (safest)",
                    classes="mode-description"
                )

                yield RadioButton("Prompt mode", id="prompt")
                yield Label(
                    "Ask for confirmation before each command",
                    classes="mode-description"
                )

                yield RadioButton("Blacklist mode", id="blacklist")
                yield Label(
                    "Block dangerous commands only (less safe)",
                    classes="mode-description"
                )

                yield RadioButton("Disabled (Unsafe)", id="disabled")
                yield Label(
                    "No safety checks (not recommended)",
                    classes="mode-description"
                )

            with Container(id="risk-warning"):
                yield Label(
                    "⚠ WARNING: Disabling the sandbox allows unrestricted command execution.\n"
                    "   The AI could potentially delete files, modify settings, or execute\n"
                    "   any shell command. Only disable if you fully understand the risks.",
                    markup=False
                )

            with Horizontal(id="button-bar"):
                yield Button("← Back", id="back", variant="default")
                yield Button("Next →", id="next", variant="primary")

        yield Footer()

    @on(RadioSet.Changed, "#sandbox-choice")
    def on_sandbox_changed(self, event: RadioSet.Changed) -> None:
        """Handle sandbox mode selection change."""
        if event.pressed:
            mode_id = event.pressed.id
            risk_warning = self.query_one("#risk-warning", Container)

            if mode_id == "disabled":
                risk_warning.styles.display = "block"
            else:
                risk_warning.styles.display = "none"

    @on(Button.Pressed, "#next")
    def on_next(self) -> None:
        """Handle Next button - save selection and move to next screen."""
        sandbox_set = self.query_one("#sandbox-choice", RadioSet)
        if sandbox_set.pressed_button:
            mode_id = sandbox_set.pressed_button.id
            self.state.sandbox_mode = mode_id

        # Move to tools screen
        self.app.push_screen(ToolsConfigScreen(self.state))

    @on(Button.Pressed, "#back")
    def on_back(self) -> None:
        """Handle Back button."""
        self.app.pop_screen()


class ToolsConfigScreen(Screen):
    """QuickStart Step 4: Configure tool capabilities."""

    CSS = """
    ToolsConfigScreen {
        align: center middle;
    }

    #tools-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #step-header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #step-description {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    #info-box {
        background: $panel;
        border: tall $primary-darken-2;
        padding: 1;
        margin: 2 0;
    }

    RadioSet {
        border: tall $primary;
        background: $panel;
        padding: 1;
        margin: 1 0;
    }

    RadioButton {
        margin: 1 2;
    }

    #button-bar {
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 20;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize tools config screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the tools configuration screen."""
        yield Header(show_clock=True)

        with Container(id="tools-container"):
            yield Label("⚡ QuickStart - Step 4 of 4", id="step-header")
            yield Label("Configure tool capabilities", id="step-description")

            with Container(id="info-box"):
                yield Label(
                    "InkArms can use tools to:\n"
                    "  • Make HTTP requests to APIs\n"
                    "  • Execute safe Python code\n"
                    "  • Perform Git operations\n"
                    "  • Read and write files\n"
                    "  • Search and list files",
                    markup=False
                )

            yield Label("Enable tool use?")

            with RadioSet(id="tools-choice"):
                yield RadioButton("Yes, enable tools (Recommended)", id="enable", value=True)
                yield RadioButton("No, disable tools", id="disable")

            with Horizontal(id="button-bar"):
                yield Button("← Back", id="back", variant="default")
                yield Button("Finish →", id="finish", variant="success")

        yield Footer()

    @on(Button.Pressed, "#finish")
    def on_finish(self) -> None:
        """Handle Finish button - save selection and build configuration."""
        tools_set = self.query_one("#tools-choice", RadioSet)
        if tools_set.pressed_button:
            enable_tools = tools_set.pressed_button.id == "enable"
            self.state.enable_tools = enable_tools
            self.state.tool_approval_mode = "auto" if enable_tools else "disabled"

        # Move to progress/building screen
        self.app.push_screen(BuildingConfigScreen(self.state))

    @on(Button.Pressed, "#back")
    def on_back(self) -> None:
        """Handle Back button."""
        self.app.pop_screen()


class BuildingConfigScreen(Screen):
    """Progress screen while building configuration."""

    CSS = """
    BuildingConfigScreen {
        align: center middle;
    }

    #building-container {
        width: 90%;
        max-width: 80;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #building-header {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 2;
    }

    #progress-message {
        text-align: center;
        margin: 2 0;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize building screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the building screen."""
        yield Header(show_clock=True)

        with Container(id="building-container"):
            yield Label("🔧 Building Your Configuration...", id="building-header")
            yield Label("Please wait...", id="progress-message")

        yield Footer()

    def on_mount(self) -> None:
        """Mount event - start building configuration."""
        self.set_timer(0.5, self._build_configuration)

    def _build_configuration(self) -> None:
        """Build and save configuration file."""
        try:
            # Build configuration
            config_dict = self.state.to_config_dict()

            # Write to file
            import yaml

            from inkarms.config.setup import create_directory_structure

            create_directory_structure()

            config_path = get_global_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)

            config_yaml = f"""# InkArms Configuration
# Generated by QuickStart wizard on {self.state.started_at.strftime('%Y-%m-%d %H:%M:%S')}
# Edit this file or use 'inkarms config set <key> <value>'

{yaml.dump(config_dict, default_flow_style=False, sort_keys=False, allow_unicode=True)}
"""

            config_path.write_text(config_yaml, encoding="utf-8")

            # Move to success screen
            self.set_timer(0.5, lambda: self.app.push_screen(SuccessScreen(self.state)))

        except Exception as ex:
            # Show error and exit
            progress = self.query_one("#progress-message", Label)
            error_msg = str(ex)
            progress.update(f"[red]Error: {error_msg}[/red]")
            self.set_timer(3.0, lambda msg=error_msg: self.app.exit(message=f"Configuration failed: {msg}"))


class SuccessScreen(Screen):
    """Success screen showing completion and next steps."""

    CSS = """
    SuccessScreen {
        align: center middle;
    }

    #success-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    #success-header {
        text-align: center;
        text-style: bold;
        color: $success;
        margin-bottom: 2;
    }

    #config-summary {
        background: $panel;
        border: tall $success-darken-2;
        padding: 1;
        margin: 2 0;
    }

    #next-steps {
        margin: 2 0;
    }

    .step {
        margin: 1 2;
    }

    #button-bar {
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
        min-width: 20;
    }
    """

    def __init__(self, state: WizardState):
        """Initialize success screen.

        Args:
            state: Wizard state object
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the success screen."""
        yield Header(show_clock=True)

        with Container(id="success-container"):
            yield Label("🎉 Setup Complete!", id="success-header")

            config_path = get_global_config_path()

            with Container(id="config-summary"):
                provider_name = self.state.provider.title()
                sandbox_name = self.state.sandbox_mode.title()
                tools_status = "enabled" if self.state.enable_tools else "disabled"

                yield Label(
                    f"Configuration saved to:\n{config_path}\n\n"
                    f"Your Configuration:\n"
                    f"  • Provider: {provider_name}\n"
                    f"  • Model: {self.state.model}\n"
                    f"  • Security: {sandbox_name} mode\n"
                    f"  • Tools: {tools_status}\n"
                    f"  • API Key: {'saved' if self.state.api_key_saved else 'not set'}",
                    markup=False
                )

            with Container(id="next-steps"):
                yield Label("[bold]Next steps:[/bold]")
                yield Label("  1. Test your setup: inkarms run \"Hello!\"", classes="step")
                yield Label("  2. View config: inkarms config show", classes="step")
                yield Label("  3. Edit manually: inkarms config edit", classes="step")

                if not self.state.api_key_saved and self.state.provider != "other":
                    yield Label(
                        f"\n[yellow]⚠ Don't forget to set your API key:[/yellow]\n"
                        f"  inkarms config set-secret {self.state.provider}"
                    )

            with Horizontal(id="button-bar"):
                yield Button("Exit", id="exit", variant="success")

        yield Footer()

    @on(Button.Pressed, "#exit")
    def on_exit(self) -> None:
        """Handle Exit button."""
        self.app.exit(message="Setup complete")
