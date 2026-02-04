"""
Advanced configuration wizard screens for InkArms TUI.

Provides comprehensive 8-section setup with all configuration options.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
)

from inkarms.config.setup import create_directory_structure
from inkarms.storage.paths import get_global_config_path


@dataclass
class AdvancedWizardState:
    """Shared state across advanced wizard sections."""

    mode: str = "advanced"
    started_at: datetime = field(default_factory=datetime.now)

    # Section 1: Provider Configuration
    provider: str = "anthropic"
    model: str = "anthropic/claude-sonnet-4-20250514"
    api_key: str = ""
    fallback_provider: str = ""
    fallback_model: str = ""
    model_aliases: dict[str, str] = field(default_factory=dict)
    timeout: int = 120
    max_retries: int = 3

    # Section 2: Context Management
    compaction_strategy: str = "sliding_window"
    context_threshold: int = 100000
    preserve_recent_turns: int = 5
    enable_handoffs: bool = True
    handoff_threshold: int = 150000

    # Section 3: Security Advanced
    sandbox_mode: str = "whitelist"
    custom_whitelist: list[str] = field(default_factory=list)
    custom_blacklist: list[str] = field(default_factory=list)
    enable_audit_log: bool = True
    audit_retention_days: int = 90
    enable_path_restrictions: bool = True

    # Section 4: Tool Configuration
    enable_tools: bool = True
    tool_approval_mode: str = "disabled"
    max_tool_iterations: int = 10
    enable_http: bool = True
    enable_python: bool = True
    enable_git: bool = True

    # Section 5: Skills Configuration
    enable_skills: bool = True
    skills_indexing_mode: str = "auto"
    auto_inject_skills: bool = True

    # Section 6: Cost Management
    enable_cost_tracking: bool = True
    daily_budget: float = 0.0  # 0 = unlimited
    monthly_budget: float = 0.0
    warning_threshold: float = 0.8  # 80% of budget

    # Section 7: TUI Preferences
    tui_theme: str = "default"
    enable_animations: bool = True
    show_timestamps: bool = True

    # Section 8: General Settings
    output_format: str = "markdown"
    verbose: bool = False
    enable_telemetry: bool = False

    def to_config_dict(self) -> dict:
        """Convert advanced wizard state to configuration dictionary.

        Returns:
            Complete configuration dictionary ready for YAML serialization
        """
        config = {
            "providers": {
                "default": self.model,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
            },
            "agent": {
                "enable_tools": self.enable_tools,
                "tool_approval_mode": self.tool_approval_mode,
                "max_iterations": self.max_tool_iterations,
            },
            "context": {
                "compaction_strategy": self.compaction_strategy,
                "threshold_tokens": self.context_threshold,
                "preserve_recent_turns": self.preserve_recent_turns,
            },
            "security": {
                "sandbox": {
                    "mode": self.sandbox_mode,
                    "custom_whitelist": self.custom_whitelist,
                    "custom_blacklist": self.custom_blacklist,
                },
                "audit_log": {
                    "enable": self.enable_audit_log,
                    "retention_days": self.audit_retention_days,
                },
                "path_restrictions": {
                    "enable": self.enable_path_restrictions,
                },
            },
            "skills": {
                "enable": self.enable_skills,
                "indexing_mode": self.skills_indexing_mode,
                "auto_inject": self.auto_inject_skills,
            },
            "cost": {
                "enable_tracking": self.enable_cost_tracking,
                "budgets": {
                    "daily": self.daily_budget,
                    "monthly": self.monthly_budget,
                    "warning_threshold": self.warning_threshold,
                },
            },
            "tui": {
                "theme": self.tui_theme,
                "enable_animations": self.enable_animations,
                "show_timestamps": self.show_timestamps,
            },
            "general": {
                "output_format": self.output_format,
                "verbose": self.verbose,
                "enable_telemetry": self.enable_telemetry,
            },
        }

        # Add fallback if configured
        if self.fallback_provider and self.fallback_model:
            config["providers"]["fallback"] = {
                "provider": self.fallback_provider,
                "model": self.fallback_model,
            }

        # Add model aliases if configured
        if self.model_aliases:
            config["providers"]["aliases"] = self.model_aliases

        # Add handoff settings
        if self.enable_handoffs:
            config["context"]["handoff_threshold"] = self.handoff_threshold
            config["context"]["enable_handoffs"] = True

        return config


class ProviderConfigurationScreen(Screen):
    """Advanced Wizard Section 1 of 8: Provider Configuration."""

    CSS = """
    ProviderConfigurationScreen {
        align: center middle;
    }

    #provider-config-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .section-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .section-progress {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    .input-group {
        margin: 1 0;
        height: auto;
    }

    .input-label {
        text-style: bold;
        margin-bottom: 1;
    }

    .input-hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    RadioSet {
        margin: 1 0;
        background: $panel;
        padding: 1;
        height: auto;
    }

    Input {
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state: AdvancedWizardState):
        """Initialize provider configuration screen.

        Args:
            state: Shared wizard state
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the provider configuration screen."""
        yield Header(show_clock=True)

        with Container(id="provider-config-container"):
            yield Label("⚙ Provider Configuration", classes="section-title")
            yield Label("Section 1 of 8", classes="section-progress")

            # Primary Provider Selection
            with Container(classes="input-group"):
                yield Label("Primary AI Provider:", classes="input-label")
                yield Label(
                    "Select your main AI provider for completions",
                    classes="input-hint"
                )

                with RadioSet(id="provider-select"):
                    yield RadioButton("Anthropic Claude (Recommended)", value="anthropic")
                    yield RadioButton("OpenAI", value="openai")
                    yield RadioButton("GitHub Copilot (OAuth)", value="github_copilot")
                    yield RadioButton("Other", value="other")

            # Model Selection
            with Container(classes="input-group"):
                yield Label("Model:", classes="input-label")
                yield Input(
                    value=self.state.model,
                    placeholder="e.g., anthropic/claude-sonnet-4-20250514",
                    id="model-input"
                )

            # Fallback Provider (Optional)
            with Container(classes="input-group"):
                yield Label("Fallback Provider (Optional):", classes="input-label")
                yield Label(
                    "Provider to use if primary fails (leave blank to disable)",
                    classes="input-hint"
                )
                yield Input(
                    value=self.state.fallback_provider,
                    placeholder="e.g., openai",
                    id="fallback-provider-input"
                )

            # Fallback Model
            with Container(classes="input-group"):
                yield Label("Fallback Model (Optional):", classes="input-label")
                yield Input(
                    value=self.state.fallback_model,
                    placeholder="e.g., openai/gpt-4",
                    id="fallback-model-input"
                )

            # Timeout
            with Container(classes="input-group"):
                yield Label("Request Timeout (seconds):", classes="input-label")
                yield Input(
                    value=str(self.state.timeout),
                    placeholder="120",
                    id="timeout-input",
                    type="integer"
                )

            # Max Retries
            with Container(classes="input-group"):
                yield Label("Max Retries:", classes="input-label")
                yield Input(
                    value=str(self.state.max_retries),
                    placeholder="3",
                    id="max-retries-input",
                    type="integer"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        """Mount event - set initial selections."""
        # Set provider radio button based on state
        provider_radio = self.query_one("#provider-select", RadioSet)
        for btn in provider_radio.query(RadioButton):
            if btn.value == self.state.provider:
                btn.value = True
                break

    @on(RadioButton.Changed, "#provider-select RadioButton")
    def on_provider_changed(self, event: RadioButton.Changed) -> None:
        """Handle provider selection change."""
        if event.radio_button.value:
            provider = event.radio_button.value

            # Update model based on provider
            model_input = self.query_one("#model-input", Input)

            if provider == "anthropic":
                model_input.value = "anthropic/claude-sonnet-4-20250514"
            elif provider == "openai":
                model_input.value = "openai/gpt-4o"
            elif provider == "github_copilot":
                model_input.value = "github_copilot/gpt-5.2"
            else:
                model_input.value = ""

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        """Handle back button press."""
        # Go back to welcome screen
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        """Handle next button press."""
        # Save current values to state
        model_input = self.query_one("#model-input", Input)
        fallback_provider_input = self.query_one("#fallback-provider-input", Input)
        fallback_model_input = self.query_one("#fallback-model-input", Input)
        timeout_input = self.query_one("#timeout-input", Input)
        max_retries_input = self.query_one("#max-retries-input", Input)

        self.state.model = model_input.value
        self.state.fallback_provider = fallback_provider_input.value
        self.state.fallback_model = fallback_model_input.value

        try:
            self.state.timeout = int(timeout_input.value) if timeout_input.value else 120
            self.state.max_retries = int(max_retries_input.value) if max_retries_input.value else 3
        except ValueError:
            # Use defaults if invalid
            self.state.timeout = 120
            self.state.max_retries = 3

        # Move to next section
        self.app.push_screen(ContextManagementScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        """Handle cancel button press."""
        self.app.exit(message="Advanced wizard cancelled")


class ContextManagementScreen(Screen):
    """Advanced Wizard Section 2 of 8: Context Management."""

    CSS = """
    ContextManagementScreen {
        align: center middle;
    }

    #context-container {
        width: 90%;
        max-width: 90;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .section-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .section-progress {
        text-align: center;
        color: $text-muted;
        margin-bottom: 2;
    }

    .input-group {
        margin: 1 0;
        height: auto;
    }

    .input-label {
        text-style: bold;
        margin-bottom: 1;
    }

    .input-hint {
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }

    RadioSet {
        margin: 1 0;
        background: $panel;
        padding: 1;
        height: auto;
    }

    Input, Checkbox {
        margin: 1 0;
    }

    #buttons {
        layout: horizontal;
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state: AdvancedWizardState):
        """Initialize context management screen.

        Args:
            state: Shared wizard state
        """
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        """Compose the context management screen."""
        yield Header(show_clock=True)

        with Container(id="context-container"):
            yield Label("🧠 Context Management", classes="section-title")
            yield Label("Section 2 of 8", classes="section-progress")

            # Compaction Strategy
            with Container(classes="input-group"):
                yield Label("Compaction Strategy:", classes="input-label")
                yield Label(
                    "How to handle conversation when context limit is reached",
                    classes="input-hint"
                )

                with RadioSet(id="compaction-select"):
                    yield RadioButton("Truncate - Drop oldest messages", value="truncate")
                    yield RadioButton(
                        "Sliding Window - Keep recent N turns (Recommended)",
                        value="sliding_window",
                    )
                    yield RadioButton(
                        "Summarize - Compress old messages with LLM",
                        value="summarize",
                    )

            # Context Threshold
            with Container(classes="input-group"):
                yield Label("Context Threshold (tokens):", classes="input-label")
                yield Label(
                    "Maximum context size before compaction (100,000 recommended)",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.context_threshold),
                    placeholder="100000",
                    id="threshold-input",
                    type="integer"
                )

            # Preserve Recent Turns
            with Container(classes="input-group"):
                yield Label("Preserve Recent Turns:", classes="input-label")
                yield Label(
                    "Number of recent conversation turns to always keep",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.preserve_recent_turns),
                    placeholder="5",
                    id="preserve-turns-input",
                    type="integer"
                )

            # Enable Handoffs
            with Container(classes="input-group"):
                yield Label("Handoff Settings:", classes="input-label")
                yield Checkbox(
                    "Enable handoff documents (create summaries when context overflows)",
                    value=self.state.enable_handoffs,
                    id="enable-handoffs-checkbox"
                )

            # Handoff Threshold
            with Container(classes="input-group"):
                yield Label("Handoff Threshold (tokens):", classes="input-label")
                yield Label(
                    "Create handoff document when context exceeds this size",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.handoff_threshold),
                    placeholder="80000",
                    id="handoff-threshold-input",
                    type="integer"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        """Mount event - set initial selections."""
        # Set compaction strategy radio button
        compaction_radio = self.query_one("#compaction-select", RadioSet)
        for btn in compaction_radio.query(RadioButton):
            if btn.value == self.state.compaction_strategy:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        """Handle back button press."""
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        """Handle next button press."""
        # Save current values to state
        compaction_radio = self.query_one("#compaction-select", RadioSet)
        threshold_input = self.query_one("#threshold-input", Input)
        preserve_turns_input = self.query_one("#preserve-turns-input", Input)
        enable_handoffs_checkbox = self.query_one("#enable-handoffs-checkbox", Checkbox)
        handoff_threshold_input = self.query_one("#handoff-threshold-input", Input)

        self.state.compaction_strategy = str(compaction_radio.pressed_button.value)
        self.state.enable_handoffs = enable_handoffs_checkbox.value

        try:
            self.state.context_threshold = int(threshold_input.value) if threshold_input.value else 100000
            self.state.preserve_recent_turns = int(preserve_turns_input.value) if preserve_turns_input.value else 5
            self.state.handoff_threshold = int(handoff_threshold_input.value) if handoff_threshold_input.value else 150000
        except ValueError:
            # Use defaults if invalid
            self.state.context_threshold = 100000
            self.state.preserve_recent_turns = 5
            self.state.handoff_threshold = 150000

        # Move to next section
        self.app.push_screen(SecurityAdvancedScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        """Handle cancel button press."""
        self.app.exit(message="Advanced wizard cancelled")


# Shared CSS for all wizard screens (screen alignment defined per-screen)
WIZARD_CSS = """
.wizard-container {
    width: 90%;
    max-width: 90;
    height: auto;
    border: thick $primary;
    background: $surface;
    padding: 2;
}

.section-title {
    text-align: center;
    text-style: bold;
    color: $accent;
    margin-bottom: 1;
}

.section-progress {
    text-align: center;
    color: $text-muted;
    margin-bottom: 2;
}

.input-group {
    margin: 1 0;
    height: auto;
}

.input-label {
    text-style: bold;
    margin-bottom: 1;
}

.input-hint {
    color: $text-muted;
    text-style: italic;
    margin-bottom: 1;
}

.warning-box {
    background: $warning-darken-3;
    border: tall $warning;
    padding: 1;
    margin: 1 0;
}

RadioSet {
    margin: 1 0;
    background: $panel;
    padding: 1;
    height: auto;
}

Input, Checkbox {
    margin: 1 0;
}

#buttons {
    layout: horizontal;
    align: center middle;
    margin-top: 2;
    height: auto;
}

Button {
    margin: 0 1;
}
"""


class SecurityAdvancedScreen(Screen):
    """Advanced Wizard Section 3 of 8: Security Configuration."""

    CSS = """
    SecurityAdvancedScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("🔒 Security Configuration", classes="section-title")
            yield Label("Section 3 of 8", classes="section-progress")

            # Sandbox Mode
            with Container(classes="input-group"):
                yield Label("Sandbox Mode:", classes="input-label")
                yield Label(
                    "How to handle command execution security",
                    classes="input-hint"
                )

                with RadioSet(id="sandbox-mode"):
                    yield RadioButton(
                        "Whitelist - Only allow specific commands (Most secure)",
                        value="whitelist"
                    )
                    yield RadioButton(
                        "Blacklist - Block specific commands",
                        value="blacklist"
                    )
                    yield RadioButton(
                        "Prompt - Ask before each command",
                        value="prompt"
                    )
                    yield RadioButton(
                        "Disabled - No restrictions (Development only)",
                        value="disabled"
                    )

            # Path Restrictions
            with Container(classes="input-group"):
                yield Label("Path Restrictions:", classes="input-label")
                yield Checkbox(
                    "Enable path restrictions (block ~/.ssh, ~/.aws, /etc)",
                    value=self.state.enable_path_restrictions,
                    id="path-restrictions-checkbox"
                )

            # Audit Logging
            with Container(classes="input-group"):
                yield Label("Audit Logging:", classes="input-label")
                yield Checkbox(
                    "Enable audit logging (track all operations)",
                    value=self.state.enable_audit_log,
                    id="audit-log-checkbox"
                )

            # Audit Retention
            with Container(classes="input-group"):
                yield Label("Audit Log Retention (days):", classes="input-label")
                yield Input(
                    value=str(self.state.audit_retention_days),
                    placeholder="90",
                    id="retention-input",
                    type="integer"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        sandbox_radio = self.query_one("#sandbox-mode", RadioSet)
        for btn in sandbox_radio.query(RadioButton):
            if btn.value == self.state.sandbox_mode:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        sandbox_radio = self.query_one("#sandbox-mode", RadioSet)
        if sandbox_radio.pressed_button:
            self.state.sandbox_mode = str(sandbox_radio.pressed_button.value)

        self.state.enable_path_restrictions = self.query_one(
            "#path-restrictions-checkbox", Checkbox
        ).value
        self.state.enable_audit_log = self.query_one("#audit-log-checkbox", Checkbox).value

        try:
            retention = self.query_one("#retention-input", Input).value
            self.state.audit_retention_days = int(retention) if retention else 90
        except ValueError:
            self.state.audit_retention_days = 90

        self.app.push_screen(ToolConfigurationScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class ToolConfigurationScreen(Screen):
    """Advanced Wizard Section 4 of 8: Tool Configuration."""

    CSS = """
    ToolConfigurationScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("🔧 Tool Configuration", classes="section-title")
            yield Label("Section 4 of 8", classes="section-progress")

            # Enable Tools
            with Container(classes="input-group"):
                yield Label("Tool Execution:", classes="input-label")
                yield Checkbox(
                    "Enable tool execution (HTTP, Python, Git)",
                    value=self.state.enable_tools,
                    id="enable-tools-checkbox"
                )

            # Individual Tools
            with Container(classes="input-group"):
                yield Label("Available Tools:", classes="input-label")
                yield Checkbox(
                    "HTTP Request Tool (fetch URLs, APIs)",
                    value=self.state.enable_http,
                    id="enable-http-checkbox"
                )
                yield Checkbox(
                    "Python Eval Tool (execute Python code)",
                    value=self.state.enable_python,
                    id="enable-python-checkbox"
                )
                yield Checkbox(
                    "Git Operations Tool (clone, status, diff)",
                    value=self.state.enable_git,
                    id="enable-git-checkbox"
                )

            # Approval Mode
            with Container(classes="input-group"):
                yield Label("Tool Approval Mode:", classes="input-label")
                yield Label(
                    "When to require approval before tool execution",
                    classes="input-hint"
                )

                with RadioSet(id="approval-mode"):
                    yield RadioButton(
                        "Disabled - Execute without approval",
                        value="disabled"
                    )
                    yield RadioButton(
                        "Always - Require approval for every tool",
                        value="always"
                    )
                    yield RadioButton(
                        "Dangerous - Require for risky operations",
                        value="dangerous"
                    )

            # Max Iterations
            with Container(classes="input-group"):
                yield Label("Max Tool Iterations:", classes="input-label")
                yield Label(
                    "Maximum tool execution rounds per query",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.max_tool_iterations),
                    placeholder="10",
                    id="max-iterations-input",
                    type="integer"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        approval_radio = self.query_one("#approval-mode", RadioSet)
        for btn in approval_radio.query(RadioButton):
            if btn.value == self.state.tool_approval_mode:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        self.state.enable_tools = self.query_one("#enable-tools-checkbox", Checkbox).value
        self.state.enable_http = self.query_one("#enable-http-checkbox", Checkbox).value
        self.state.enable_python = self.query_one("#enable-python-checkbox", Checkbox).value
        self.state.enable_git = self.query_one("#enable-git-checkbox", Checkbox).value

        approval_radio = self.query_one("#approval-mode", RadioSet)
        if approval_radio.pressed_button:
            self.state.tool_approval_mode = str(approval_radio.pressed_button.value)

        try:
            max_iter = self.query_one("#max-iterations-input", Input).value
            self.state.max_tool_iterations = int(max_iter) if max_iter else 10
        except ValueError:
            self.state.max_tool_iterations = 10

        self.app.push_screen(SkillsConfigurationScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class SkillsConfigurationScreen(Screen):
    """Advanced Wizard Section 5 of 8: Skills Configuration."""

    CSS = """
    SkillsConfigurationScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("📚 Skills Configuration", classes="section-title")
            yield Label("Section 5 of 8", classes="section-progress")

            # Enable Skills
            with Container(classes="input-group"):
                yield Label("Skills System:", classes="input-label")
                yield Checkbox(
                    "Enable skills system",
                    value=self.state.enable_skills,
                    id="enable-skills-checkbox"
                )

            # Auto Inject
            with Container(classes="input-group"):
                yield Label("Skill Injection:", classes="input-label")
                yield Checkbox(
                    "Auto-inject relevant skills into prompts",
                    value=self.state.auto_inject_skills,
                    id="auto-inject-checkbox"
                )

            # Indexing Mode
            with Container(classes="input-group"):
                yield Label("Indexing Mode:", classes="input-label")
                yield Label(
                    "How skills are indexed and searched",
                    classes="input-hint"
                )

                with RadioSet(id="indexing-mode"):
                    yield RadioButton(
                        "Auto - Index on demand (Recommended)",
                        value="auto"
                    )
                    yield RadioButton(
                        "Eager - Index all skills at startup",
                        value="eager"
                    )
                    yield RadioButton(
                        "Lazy - Index only when explicitly requested",
                        value="lazy"
                    )

            # Info box
            with Container(classes="input-group"):
                yield Label(
                    "Skills are stored in ~/.inkarms/skills/\n"
                    "Create skills with: inkarms skill create <name>",
                    classes="input-hint"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        indexing_radio = self.query_one("#indexing-mode", RadioSet)
        for btn in indexing_radio.query(RadioButton):
            if btn.value == self.state.skills_indexing_mode:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        self.state.enable_skills = self.query_one("#enable-skills-checkbox", Checkbox).value
        self.state.auto_inject_skills = self.query_one("#auto-inject-checkbox", Checkbox).value

        indexing_radio = self.query_one("#indexing-mode", RadioSet)
        if indexing_radio.pressed_button:
            self.state.skills_indexing_mode = str(indexing_radio.pressed_button.value)

        self.app.push_screen(CostManagementScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class CostManagementScreen(Screen):
    """Advanced Wizard Section 6 of 8: Cost Management."""

    CSS = """
    CostManagementScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("💰 Cost Management", classes="section-title")
            yield Label("Section 6 of 8", classes="section-progress")

            # Enable Cost Tracking
            with Container(classes="input-group"):
                yield Label("Cost Tracking:", classes="input-label")
                yield Checkbox(
                    "Enable cost tracking",
                    value=self.state.enable_cost_tracking,
                    id="enable-cost-checkbox"
                )

            # Daily Budget
            with Container(classes="input-group"):
                yield Label("Daily Budget ($):", classes="input-label")
                yield Label(
                    "Maximum daily spending (0 = unlimited)",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.daily_budget),
                    placeholder="0.00",
                    id="daily-budget-input",
                    type="number"
                )

            # Monthly Budget
            with Container(classes="input-group"):
                yield Label("Monthly Budget ($):", classes="input-label")
                yield Label(
                    "Maximum monthly spending (0 = unlimited)",
                    classes="input-hint"
                )
                yield Input(
                    value=str(self.state.monthly_budget),
                    placeholder="0.00",
                    id="monthly-budget-input",
                    type="number"
                )

            # Warning Threshold
            with Container(classes="input-group"):
                yield Label("Warning Threshold (%):", classes="input-label")
                yield Label(
                    "Warn when this percentage of budget is reached",
                    classes="input-hint"
                )
                yield Input(
                    value=str(int(self.state.warning_threshold * 100)),
                    placeholder="80",
                    id="warning-threshold-input",
                    type="integer"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        self.state.enable_cost_tracking = self.query_one(
            "#enable-cost-checkbox", Checkbox
        ).value

        try:
            daily = self.query_one("#daily-budget-input", Input).value
            self.state.daily_budget = float(daily) if daily else 0.0
        except ValueError:
            self.state.daily_budget = 0.0

        try:
            monthly = self.query_one("#monthly-budget-input", Input).value
            self.state.monthly_budget = float(monthly) if monthly else 0.0
        except ValueError:
            self.state.monthly_budget = 0.0

        try:
            threshold = self.query_one("#warning-threshold-input", Input).value
            self.state.warning_threshold = int(threshold) / 100 if threshold else 0.8
        except ValueError:
            self.state.warning_threshold = 0.8

        self.app.push_screen(TUIPreferencesScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class TUIPreferencesScreen(Screen):
    """Advanced Wizard Section 7 of 8: TUI Preferences."""

    CSS = """
    TUIPreferencesScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("🎨 TUI Preferences", classes="section-title")
            yield Label("Section 7 of 8", classes="section-progress")

            # Theme
            with Container(classes="input-group"):
                yield Label("Theme:", classes="input-label")

                with RadioSet(id="theme-select"):
                    yield RadioButton("Default (Dark)", value="default")
                    yield RadioButton("Light", value="light")
                    yield RadioButton("High Contrast", value="high_contrast")

            # Animations
            with Container(classes="input-group"):
                yield Label("Visual Settings:", classes="input-label")
                yield Checkbox(
                    "Enable animations",
                    value=self.state.enable_animations,
                    id="animations-checkbox"
                )
                yield Checkbox(
                    "Show timestamps in messages",
                    value=self.state.show_timestamps,
                    id="timestamps-checkbox"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Next →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        theme_radio = self.query_one("#theme-select", RadioSet)
        for btn in theme_radio.query(RadioButton):
            if btn.value == self.state.tui_theme:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        theme_radio = self.query_one("#theme-select", RadioSet)
        if theme_radio.pressed_button:
            self.state.tui_theme = str(theme_radio.pressed_button.value)

        self.state.enable_animations = self.query_one("#animations-checkbox", Checkbox).value
        self.state.show_timestamps = self.query_one("#timestamps-checkbox", Checkbox).value

        self.app.push_screen(GeneralSettingsScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class GeneralSettingsScreen(Screen):
    """Advanced Wizard Section 8 of 8: General Settings."""

    CSS = """
    GeneralSettingsScreen {
        align: center middle;
    }
    """ + WIZARD_CSS

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="wizard-container"):
            yield Label("⚙️ General Settings", classes="section-title")
            yield Label("Section 8 of 8", classes="section-progress")

            # Output Format
            with Container(classes="input-group"):
                yield Label("Output Format:", classes="input-label")

                with RadioSet(id="format-select"):
                    yield RadioButton("Markdown (Recommended)", value="markdown")
                    yield RadioButton("Plain Text", value="plain")
                    yield RadioButton("JSON", value="json")

            # Verbose Mode
            with Container(classes="input-group"):
                yield Label("Logging:", classes="input-label")
                yield Checkbox(
                    "Enable verbose output",
                    value=self.state.verbose,
                    id="verbose-checkbox"
                )

            # Telemetry
            with Container(classes="input-group"):
                yield Label("Telemetry:", classes="input-label")
                yield Checkbox(
                    "Enable anonymous usage telemetry",
                    value=self.state.enable_telemetry,
                    id="telemetry-checkbox"
                )
                yield Label(
                    "Helps improve InkArms. No personal data collected.",
                    classes="input-hint"
                )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("Review & Save →", id="next-button", variant="primary")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        format_radio = self.query_one("#format-select", RadioSet)
        for btn in format_radio.query(RadioButton):
            if btn.value == self.state.output_format:
                btn.value = True
                break

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#next-button")
    def on_next_button(self) -> None:
        format_radio = self.query_one("#format-select", RadioSet)
        if format_radio.pressed_button:
            self.state.output_format = str(format_radio.pressed_button.value)

        self.state.verbose = self.query_one("#verbose-checkbox", Checkbox).value
        self.state.enable_telemetry = self.query_one("#telemetry-checkbox", Checkbox).value

        self.app.push_screen(ConfigPreviewScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class ConfigPreviewScreen(Screen):
    """Preview configuration before saving."""

    CSS = """
    ConfigPreviewScreen {
        align: center middle;
    }

    .preview-container {
        width: 90%;
        max-width: 100;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .section-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 2;
    }

    .config-preview {
        background: $panel;
        border: tall $primary-darken-2;
        padding: 1;
        margin: 1 0;
        height: auto;
    }

    .config-section {
        margin: 1 0;
    }

    .config-header {
        text-style: bold;
        color: $accent;
    }

    .config-item {
        margin-left: 2;
        color: $text;
    }

    #buttons {
        layout: horizontal;
        align: center middle;
        margin-top: 2;
        height: auto;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="preview-container"):
            yield Label("📋 Configuration Preview", classes="section-title")

            with Container(classes="config-preview"):
                # Provider Section
                with Container(classes="config-section"):
                    yield Label("🔌 Provider", classes="config-header")
                    yield Label(f"  Model: {self.state.model}", classes="config-item")
                    if self.state.fallback_model:
                        yield Label(
                            f"  Fallback: {self.state.fallback_model}",
                            classes="config-item"
                        )
                    yield Label(
                        f"  Timeout: {self.state.timeout}s, Retries: {self.state.max_retries}",
                        classes="config-item"
                    )

                # Context Section
                with Container(classes="config-section"):
                    yield Label("🧠 Context", classes="config-header")
                    yield Label(
                        f"  Strategy: {self.state.compaction_strategy}",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Threshold: {self.state.context_threshold:,} tokens",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Handoffs: {'Enabled' if self.state.enable_handoffs else 'Disabled'}",
                        classes="config-item"
                    )

                # Security Section
                with Container(classes="config-section"):
                    yield Label("🔒 Security", classes="config-header")
                    yield Label(
                        f"  Sandbox: {self.state.sandbox_mode}",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Path Restrictions: {'On' if self.state.enable_path_restrictions else 'Off'}",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Audit Log: {'On' if self.state.enable_audit_log else 'Off'}"
                        f" ({self.state.audit_retention_days} days)",
                        classes="config-item"
                    )

                # Tools Section
                with Container(classes="config-section"):
                    yield Label("🔧 Tools", classes="config-header")
                    yield Label(
                        f"  Enabled: {'Yes' if self.state.enable_tools else 'No'}",
                        classes="config-item"
                    )
                    if self.state.enable_tools:
                        tools = []
                        if self.state.enable_http:
                            tools.append("HTTP")
                        if self.state.enable_python:
                            tools.append("Python")
                        if self.state.enable_git:
                            tools.append("Git")
                        yield Label(f"  Active: {', '.join(tools)}", classes="config-item")
                        yield Label(
                            f"  Approval: {self.state.tool_approval_mode}",
                            classes="config-item"
                        )

                # Skills Section
                with Container(classes="config-section"):
                    yield Label("📚 Skills", classes="config-header")
                    yield Label(
                        f"  Enabled: {'Yes' if self.state.enable_skills else 'No'}",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Auto-inject: {'Yes' if self.state.auto_inject_skills else 'No'}",
                        classes="config-item"
                    )

                # Cost Section
                with Container(classes="config-section"):
                    yield Label("💰 Cost", classes="config-header")
                    yield Label(
                        f"  Tracking: {'On' if self.state.enable_cost_tracking else 'Off'}",
                        classes="config-item"
                    )
                    if self.state.daily_budget > 0:
                        yield Label(
                            f"  Daily Budget: ${self.state.daily_budget:.2f}",
                            classes="config-item"
                        )
                    if self.state.monthly_budget > 0:
                        yield Label(
                            f"  Monthly Budget: ${self.state.monthly_budget:.2f}",
                            classes="config-item"
                        )

                # General Section
                with Container(classes="config-section"):
                    yield Label("⚙️ General", classes="config-header")
                    yield Label(
                        f"  Output: {self.state.output_format}",
                        classes="config-item"
                    )
                    yield Label(
                        f"  Verbose: {'Yes' if self.state.verbose else 'No'}",
                        classes="config-item"
                    )

            # Buttons
            with Horizontal(id="buttons"):
                yield Button("← Back", id="back-button")
                yield Button("💾 Save Configuration", id="save-button", variant="success")
                yield Button("Cancel", id="cancel-button", variant="error")

        yield Footer()

    @on(Button.Pressed, "#back-button")
    def on_back_button(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#save-button")
    def on_save_button(self) -> None:
        self.app.push_screen(BuildingAdvancedConfigScreen(self.state))

    @on(Button.Pressed, "#cancel-button")
    def on_cancel_button(self) -> None:
        self.app.exit(message="Advanced wizard cancelled")


class BuildingAdvancedConfigScreen(Screen):
    """Building configuration progress screen."""

    CSS = """
    BuildingAdvancedConfigScreen {
        align: center middle;
    }

    .building-container {
        width: 90%;
        max-width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    .section-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 2;
    }

    .status-message {
        text-align: center;
        margin: 1 0;
    }
    """

    def __init__(self, state: AdvancedWizardState):
        super().__init__()
        self.state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="building-container"):
            yield Label("🔨 Building Configuration", classes="section-title")
            yield Label("Creating directories...", id="status", classes="status-message")

        yield Footer()

    def on_mount(self) -> None:
        self.build_config()

    @work(thread=True)
    def build_config(self) -> None:
        import time

        import yaml

        status = self.query_one("#status", Label)

        # Step 1: Create directories
        self.app.call_from_thread(status.update, "Creating directories...")
        time.sleep(0.3)
        create_directory_structure()

        # Step 2: Build config
        self.app.call_from_thread(status.update, "Building configuration...")
        time.sleep(0.3)
        config_dict = self.state.to_config_dict()

        # Step 3: Write config file
        self.app.call_from_thread(status.update, "Writing config.yaml...")
        time.sleep(0.3)
        config_path = get_global_config_path()

        header = """# InkArms Configuration
# Generated by Advanced Configuration Wizard
# https://github.com/inkarms/inkarms
#
# Edit this file to customize InkArms behavior.
# See docs/configuration.md for all options.

"""
        yaml_content = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

        config_path.write_text(header + yaml_content)

        # Step 4: Done
        self.app.call_from_thread(status.update, "Configuration saved!")
        time.sleep(0.5)

        # Move to success screen
        self.app.call_from_thread(
            self.app.push_screen,
            AdvancedSuccessScreen(self.state, config_path)
        )


class AdvancedSuccessScreen(Screen):
    """Success screen after saving configuration."""

    CSS = """
    AdvancedSuccessScreen {
        align: center middle;
    }

    .success-container {
        width: 90%;
        max-width: 80;
        height: auto;
        border: thick $success;
        background: $surface;
        padding: 2;
    }

    .success-title {
        text-align: center;
        text-style: bold;
        color: $success;
        margin-bottom: 2;
    }

    .success-message {
        text-align: center;
        margin: 1 0;
    }

    .next-steps {
        background: $panel;
        border: tall $primary-darken-2;
        padding: 1;
        margin: 2 0;
    }

    .step-header {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    .step-item {
        margin-left: 2;
    }

    #buttons {
        layout: horizontal;
        align: center middle;
        margin-top: 2;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(self, state: AdvancedWizardState, config_path: Path):
        super().__init__()
        self.state = state
        self.config_path = config_path

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(classes="success-container"):
            yield Label("✅ Configuration Complete!", classes="success-title")
            yield Label(
                f"Your configuration has been saved to:\n{self.config_path}",
                classes="success-message"
            )

            with Container(classes="next-steps"):
                yield Label("Next Steps:", classes="step-header")
                yield Label("1. Set your API key:", classes="step-item")
                yield Label(
                    f"   inkarms config set-secret {self.state.provider}",
                    classes="step-item"
                )
                yield Label("", classes="step-item")
                yield Label("2. Test your setup:", classes="step-item")
                yield Label("   inkarms run \"Hello!\"", classes="step-item")
                yield Label("", classes="step-item")
                yield Label("3. Start chatting:", classes="step-item")
                yield Label("   inkarms chat", classes="step-item")
                yield Label("", classes="step-item")
                yield Label("4. Create a skill:", classes="step-item")
                yield Label("   inkarms skill create my-skill", classes="step-item")

            with Horizontal(id="buttons"):
                yield Button("🚀 Start Chat", id="chat-button", variant="primary")
                yield Button("Exit", id="exit-button")

        yield Footer()

    @on(Button.Pressed, "#chat-button")
    def on_chat_button(self) -> None:
        from inkarms.tui.screens.chat import ChatScreen
        self.app.switch_screen(ChatScreen())

    @on(Button.Pressed, "#exit-button")
    def on_exit_button(self) -> None:
        self.app.exit(message="Configuration complete! Run 'inkarms chat' to start.")
