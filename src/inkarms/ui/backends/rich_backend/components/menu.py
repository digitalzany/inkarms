"""Menu components for the Rich backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.layout import (
    FormattedTextControl,
    Layout,
    Window,
)

from inkarms.config.theme import LOGO, STYLE
from inkarms.ui.backends.rich_backend.key_binding import bind_keys

if TYPE_CHECKING:
    from collections.abc import Callable


class Menu:
    """Simple menu component. Used for popups, categories (e.g., Sessions view)."""

    def __init__(self, title: str, items: list[tuple[str, str, str]], subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.items = items
        self.selected = 0
        self.result: str | None = None
        self.cancelled = False

    def get_formatted_text(self):
        result = []
        result.append(("class:title", f"\n  {self.title}\n"))
        if self.subtitle:
            result.append(("class:subtitle", f"  {self.subtitle}\n"))
        result.append(("", "\n"))

        for i, (value, label, desc) in enumerate(self.items):
            if i == self.selected:
                result.append(("class:menu-selected", f"    ❯ {label}"))
                if desc:
                    result.append(("class:menu-desc", f"      {desc}\n"))
                else:
                    result.append(("", "\n"))
            else:
                result.append(("class:menu-item", f"      {label}\n"))

        result.append(("", "\n"))
        result.append(("class:hint", "  ↑↓ navigate  Enter select  Esc cancel\n"))
        return result

    def run(self) -> str | None:
        kb = bind_keys(self)
        layout = Layout(Window(FormattedTextControl(self.get_formatted_text)))
        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()

        return None if self.cancelled else self.result


class MainMenu:
    """Main menu with branding. Used at the startup."""

    def __init__(self, status_bar_fn: Callable[[], list[tuple[str, str]]]):
        self._get_status_bar = status_bar_fn
        self.selected = 0
        self.items = [
            ("chat", "Chat", "Start or continue chatting"),
            ("dashboard", "Dashboard", "View usage and stats"),
            ("sessions", "Sessions", "Manage chat sessions"),
            ("config", "Config", "Configure provider and model"),
            ("quit", "Quit", ""),
        ]
        self.result: str | None = None

    def get_formatted_text(self):
        result = []

        for line in LOGO.strip().split("\n"):
            result.append(("class:brand", f"{line}\n"))

        result.append(("class:tagline", "    Your AI assistant that does things\n"))
        result.append(("", "\n"))
        result.extend(self._get_status_bar())
        result.append(("", "\n\n"))

        for i, (value, label, desc) in enumerate(self.items):
            if i == self.selected:
                result.append(("class:menu-selected", f"    ❯ {label}"))
                result.append(("class:menu-desc", f"      {desc}\n"))
            else:
                result.append(("class:menu-item", f"      {label}\n"))

        result.append(("", "\n"))
        result.append(("class:hint", "    ↑↓"))
        result.append(("class:hint-dim", " navigate  "))
        result.append(("class:hint", "Enter"))
        result.append(("class:hint-dim", " select  "))
        result.append(("class:hint", "q"))
        result.append(("class:hint-dim", " quit  "))
        result.append(("class:hint", "c"))
        result.append(("class:hint-dim", " chat  "))
        result.append(("class:hint", "d"))
        result.append(("class:hint-dim", " dashboard  "))
        result.append(("class:hint", "s"))
        result.append(("class:hint-dim", " sessions\n"))

        return result

    def run(self) -> str:
        kb = bind_keys(
            self,
            ["up", "down", "enter", "escape", "c-c", "c", "d", "s"]
        )
        layout = Layout(Window(FormattedTextControl(self.get_formatted_text)))
        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()

        return self.result or "quit"
