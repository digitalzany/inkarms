"""
UI Backend Protocol - Abstract interface for UI implementations.

This module defines the contract that all UI backends must implement.
Backends can be Rich+prompt_toolkit, Textual, or future implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class UIView(str, Enum):
    """Available UI views."""

    MENU = "menu"
    CHAT = "chat"
    DASHBOARD = "dashboard"
    SESSIONS = "sessions"
    CONFIG = "config"
    SETTINGS = "settings"


@dataclass
class UIConfig:
    """Configuration for UI backend."""

    theme: str = "default"
    show_status_bar: bool = True
    show_timestamps: bool = True
    max_messages_display: int = 20
    enable_mouse: bool = True
    enable_completion: bool = True


@dataclass
class ChatMessage:
    """A chat message for display."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: str
    tokens: int | None = None


@dataclass
class SessionInfo:
    """Session information for display."""

    name: str
    message_count: int
    created: str
    model: str
    is_current: bool = False


@dataclass
class StatusInfo:
    """Status information for status bar."""

    provider: str | None = None
    model: str | None = None
    session: str | None = None
    message_count: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    api_key_set: bool = False


class UIBackend(ABC):
    """Abstract base class for UI backends.

    All UI implementations must implement these methods to provide
    a consistent interface for the InkArms application.
    """

    @abstractmethod
    def run(self) -> None:
        """Run the UI main loop.

        This is the main entry point. It should:
        1. Show config wizard on first run
        2. Display main menu
        3. Handle view transitions
        4. Exit cleanly when done
        """
        ...

    @abstractmethod
    def run_main_menu(self) -> UIView | None:
        """Display main menu and return selected view."""
        ...

    @abstractmethod
    def run_chat(self) -> UIView:
        """Run chat interface. Returns next view to show."""
        ...

    @abstractmethod
    def run_dashboard(self) -> UIView | None:
        """Run dashboard interface. Returns next view to show."""
        ...

    @abstractmethod
    def run_sessions(self) -> UIView:
        """Run sessions management. Returns next view to show."""
        ...

    @abstractmethod
    def run_config_wizard(self) -> bool:
        """Run configuration wizard. Returns True if completed."""
        ...

    @abstractmethod
    def run_settings(self) -> UIView:
        """Run settings interface. Returns next view to show."""
        ...

    # --- Display methods ---

    @abstractmethod
    def display_message(self, message: ChatMessage) -> None:
        """Display a chat message."""
        ...

    @abstractmethod
    def display_streaming_start(self) -> None:
        """Called when streaming response starts."""
        ...

    @abstractmethod
    def display_streaming_chunk(self, chunk: str) -> None:
        """Display a chunk of streaming response."""
        ...

    @abstractmethod
    def display_streaming_end(self) -> None:
        """Called when streaming response ends."""
        ...

    @abstractmethod
    def display_error(self, message: str) -> None:
        """Display an error message."""
        ...

    @abstractmethod
    def display_info(self, message: str) -> None:
        """Display an info message."""
        ...

    @abstractmethod
    def display_status(self, status: StatusInfo) -> None:
        """Update status bar with current status."""
        ...

    # --- Input methods ---

    @abstractmethod
    def get_user_input(self, prompt: str = "You: ") -> str | None:
        """Get user input. Returns None if cancelled."""
        ...

    @abstractmethod
    def get_text_input(
        self, title: str, prompt: str = "> ", password: bool = False, default: str = ""
    ) -> str | None:
        """Get text input with a title. Returns None if cancelled."""
        ...

    @abstractmethod
    def get_selection(
        self, title: str, options: list[tuple[str, str, str]], subtitle: str = ""
    ) -> str | None:
        """Show selection menu. Options are (value, label, description).
        Returns selected value or None if cancelled."""
        ...

    @abstractmethod
    def confirm(self, message: str, default: bool = False) -> bool:
        """Show confirmation dialog."""
        ...

    # --- Session management ---

    @abstractmethod
    def get_sessions(self) -> list[SessionInfo]:
        """Get list of available sessions."""
        ...

    @abstractmethod
    def get_current_session(self) -> str | None:
        """Get current session name."""
        ...

    @abstractmethod
    def set_current_session(self, name: str) -> None:
        """Set current session."""
        ...

    @abstractmethod
    def create_session(self, name: str) -> None:
        """Create a new session."""
        ...

    # --- Lifecycle ---

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the UI backend. Called before run()."""
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup resources. Called after run() or on error."""
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the application is configured."""
        ...

    @property
    @abstractmethod
    def config(self) -> UIConfig:
        """Get UI configuration."""
        ...
