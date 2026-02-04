"""
Main InkArms TUI application.

Built with Textual for beautiful terminal user interfaces.
"""

from textual.app import App
from textual.binding import Binding

from inkarms.tui.screens.wizard import ConfigWizardWelcome


class InkArmsApp(App):
    """Main InkArms TUI application."""

    CSS = """
    Screen {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, mode: str = "wizard", force: bool = False, session_id: str = "default"):
        """Initialize TUI application.

        Args:
            mode: Application mode ('wizard', 'chat', 'dashboard')
            force: Force overwrite existing config (wizard mode)
            session_id: Session ID for chat mode
        """
        super().__init__()
        self.mode = mode
        self.force = force
        self.session_id = session_id

    def on_mount(self) -> None:
        """Mount the appropriate screen based on mode."""
        if self.mode == "wizard":
            self.push_screen(ConfigWizardWelcome(force=self.force))
        elif self.mode == "chat":
            from inkarms.tui.screens.chat import ChatScreen
            self.push_screen(ChatScreen(session_id=self.session_id))


def run_config_wizard(force: bool = False) -> None:
    """Run the configuration wizard in TUI mode.

    Args:
        force: Force overwrite existing configuration
    """
    app = InkArmsApp(mode="wizard", force=force)
    app.run()


def run_chat_interface(session_id: str = "default") -> None:
    """Run the chat interface in TUI mode.

    Args:
        session_id: Session ID for conversation tracking
    """
    app = InkArmsApp(mode="chat", session_id=session_id)
    app.run()
