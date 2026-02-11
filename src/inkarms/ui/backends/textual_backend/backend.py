"""
Textual UI Backend (Optional).

This backend provides a rich TUI using the Textual framework.
It is an optional dependency - install with: pip install inkarms[textual]
"""


from inkarms.ui.protocol import ChatMessage, SessionInfo, StatusInfo, UIBackend, UIConfig, UIView


class TextualBackend(UIBackend):
    """Textual-based UI backend implementation.

    This is a more feature-rich TUI option using the Textual framework.
    Requires optional dependency: pip install inkarms[textual]
    """

    def __init__(self, ui_config: UIConfig | None = None):
        self._config = ui_config or UIConfig()
        # Implementation would go here when Textual TUI is fully implemented
        raise NotImplementedError("Textual backend not yet implemented")

    @property
    def config(self) -> UIConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return False

    def initialize(self) -> None:
        raise NotImplementedError(
            "Textual backend is not yet fully implemented. "
            "Please use the Rich backend (default) instead."
        )

    def cleanup(self) -> None:
        pass

    def run(self) -> None:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_main_menu(self) -> UIView:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_chat(self) -> UIView:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_dashboard(self) -> UIView:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_sessions(self) -> UIView:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_config_wizard(self) -> bool:
        raise NotImplementedError("Textual backend not yet implemented")

    def run_settings(self) -> UIView:
        raise NotImplementedError("Textual backend not yet implemented")

    def display_message(self, message: ChatMessage) -> None:
        pass

    def display_streaming_start(self) -> None:
        pass

    def display_streaming_chunk(self, chunk: str) -> None:
        pass

    def display_streaming_end(self) -> None:
        pass

    def display_error(self, message: str) -> None:
        pass

    def display_info(self, message: str) -> None:
        pass

    def display_status(self, status: StatusInfo) -> None:
        pass

    def get_user_input(self, prompt: str = "You: ") -> str | None:
        return None

    def get_text_input(self, title: str, prompt: str = "> ",
                       password: bool = False, default: str = "") -> str | None:
        return None

    def get_selection(self, title: str, options: list[tuple[str, str, str]],
                     subtitle: str = "") -> str | None:
        return None

    def confirm(self, message: str, default: bool = False) -> bool:
        return False

    def get_sessions(self) -> list[SessionInfo]:
        return []

    def get_current_session(self) -> str | None:
        return None

    def set_current_session(self, name: str) -> None:
        pass

    def create_session(self, name: str) -> None:
        pass
