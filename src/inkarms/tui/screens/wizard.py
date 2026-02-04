"""
Configuration wizard screens for InkArms TUI.

Provides QuickStart and Advanced setup modes.
"""


from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label

from inkarms.storage.paths import get_global_config_path, get_inkarms_home


class ConfigWizardWelcome(Screen):
    """Welcome screen for configuration wizard."""

    CSS = """
    ConfigWizardWelcome {
        align: center middle;
    }

    #welcome-container {
        width: 90%;
        max-width: 80;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 2;
    }

    #welcome-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #welcome-message {
        text-align: center;
        margin-bottom: 2;
    }

    #mode-buttons {
        align: center middle;
        height: auto;
        margin-top: 2;
    }

    Button {
        margin: 1 2;
        min-width: 50;
    }

    .mode-description {
        text-align: center;
        color: $text-muted;
        margin: 0 2;
    }
    """

    def __init__(self, force: bool = False):
        """Initialize welcome screen.

        Args:
            force: Force overwrite existing configuration
        """
        super().__init__()
        self.force = force
        self.config_exists = False

    def compose(self) -> ComposeResult:
        """Compose the welcome screen layout."""
        yield Header(show_clock=True)

        # Check if config exists
        config_path = get_global_config_path()
        self.config_exists = config_path.exists() and get_inkarms_home().exists()

        with Container(id="welcome-container"):
            yield Label("🐙 Welcome to InkArms!", id="welcome-title")

            if self.config_exists and not self.force:
                yield Label(
                    "InkArms is already configured.\n"
                    "Would you like to reconfigure?",
                    id="welcome-message"
                )
            else:
                yield Label(
                    "Let's get you set up with your AI agent assistant.\n"
                    "Choose your setup experience below:",
                    id="welcome-message"
                )

            with Vertical(id="mode-buttons"):
                yield Button("⚡ QuickStart (2 minutes)", id="quickstart", variant="primary")
                yield Label(
                    "Minimal questions, sensible defaults, start chatting quickly",
                    classes="mode-description"
                )

                yield Button("🔧 Advanced (10-15 minutes)", id="advanced", variant="default")
                yield Label(
                    "Comprehensive setup with all options and customization",
                    classes="mode-description"
                )

                if self.config_exists and not self.force:
                    yield Button("❌ Cancel", id="cancel", variant="error")

        yield Footer()

    @on(Button.Pressed, "#quickstart")
    def on_quickstart(self) -> None:
        """Handle QuickStart button press."""
        from inkarms.tui.screens.quickstart import ProviderSelectionScreen, WizardState

        state = WizardState(mode="quickstart")
        self.app.push_screen(ProviderSelectionScreen(state))

    @on(Button.Pressed, "#advanced")
    def on_advanced(self) -> None:
        """Handle Advanced button press."""
        from inkarms.tui.screens.advanced import AdvancedWizardState, ProviderConfigurationScreen

        state = AdvancedWizardState(mode="advanced")
        self.app.push_screen(ProviderConfigurationScreen(state))

    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        """Handle Cancel button press."""
        self.app.exit(message="Setup cancelled")


class QuickStartWizard(Screen):
    """QuickStart configuration wizard."""

    # TODO: Implement QuickStart wizard screens
    pass


class AdvancedWizard(Screen):
    """Advanced configuration wizard."""

    # TODO: Implement Advanced wizard screens
    pass
