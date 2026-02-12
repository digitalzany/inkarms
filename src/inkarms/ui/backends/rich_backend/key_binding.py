"""Key binding setup for Rich backend UI components."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from prompt_toolkit.key_binding import KeyBindings

from inkarms.ui.protocol import UIView

if TYPE_CHECKING:
    from collections.abc import Iterable

    from prompt_toolkit.buffer import Buffer


@runtime_checkable
class MenuLike(Protocol):
    """Protocol for menu components that support navigation."""

    selected: int
    items: list[tuple[str, str, str]]
    result: str | None


@runtime_checkable
class Cancellable(Protocol):
    """Protocol for components that can be cancelled."""

    cancelled: bool


@runtime_checkable
class ChatLike(Protocol):
    """Protocol for chat-like components with scroll and exit."""

    exit_to: UIView | None
    chat_buffer: Buffer


def bind_keys(
    ui_instance: MenuLike | ChatLike | Cancellable,
    required_keys: Iterable[str] = ("up", "down", "enter", "escape", "c-c"),
) -> KeyBindings:
    """Bind keys to actions for a UI component.

    Args:
        ui_instance: The UI component to bind keys for.
        required_keys: Keys to bind. Use comma-separated strings for multi-key
            bindings (e.g. "c-c,c-q,escape").
    """
    # --- Menu navigation handlers ---

    def up(event):
        ui_instance.selected = (ui_instance.selected - 1) % len(ui_instance.items)

    def down(event):
        ui_instance.selected = (ui_instance.selected + 1) % len(ui_instance.items)

    def enter(event):
        ui_instance.result = ui_instance.items[ui_instance.selected][0]
        event.app.exit()

    def cancel(event):
        ui_instance.cancelled = True
        event.app.exit()

    def ctrl_c(event):
        ui_instance.cancelled = True
        event.app.exit()

    # --- Main menu shortcut handlers ---

    def chat(event):
        ui_instance.result = "chat"
        event.app.exit()

    def dashboard(event):
        ui_instance.result = "dashboard"
        event.app.exit()

    def sessions(event):
        ui_instance.result = "sessions"
        event.app.exit()

    # --- Input handlers ---

    def tab(event):
        buff = event.app.current_buffer
        if buff.complete_state:
            buff.complete_next()
        else:
            buff.start_completion(select_first=False)

    def backspace(event):
        buff = event.app.current_buffer
        buff.delete_before_cursor(1)
        if buff.text.startswith("/"):
            buff.start_completion(select_first=False)

    # --- Chat handlers ---

    def exit_from_chat(event):
        ui_instance.exit_to = UIView.MENU
        event.app.exit()

    def scroll_top(event):
        if ui_instance.chat_buffer:
            ui_instance.chat_buffer.cursor_position = 0

    def scroll_bottom(event):
        if ui_instance.chat_buffer:
            ui_instance.chat_buffer.cursor_position = len(ui_instance.chat_buffer.text)

    key_to_action = {
        "up": up,
        "down": down,
        "enter": enter,
        "escape": cancel,
        "c-c": ctrl_c,
        "c": chat,
        "d": dashboard,
        "s": sessions,
        "tab": tab,
        "backspace": backspace,
        "c-c,c-q,escape": exit_from_chat,
        "home": scroll_top,
        "end": scroll_bottom,
    }

    kb = KeyBindings()
    for key in required_keys:
        func = key_to_action.get(key)
        if not func:
            continue
        for k in key.split(","):
            kb.add(k)(func)

    return kb
