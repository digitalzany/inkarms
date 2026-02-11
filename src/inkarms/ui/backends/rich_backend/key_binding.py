from typing import TYPE_CHECKING, Iterable

from inkarms.ui.protocol import UIView
from prompt_toolkit.key_binding import KeyBindings

if TYPE_CHECKING:
    from inkarms.ui.backends.rich_backend.backend import _Menu, _MainMenu
    from inkarms.ui.backends.rich_backend.components.input import TextInput
    from inkarms.ui.backends.rich_backend.components.chat import ChatView
    from inkarms.ui.backends.rich_backend.components.dashboard import DashboardView


def bind_keys(
        ui_instance: "_Menu | _MainMenu | DashboardView | ChatView | TextInput",
        required_keys: Iterable[str] = ("up", "down", "enter", "escape", "c-c")
) -> KeyBindings:
    """
    Common key binding function for Rich backend UI elements.
    :param ui_instance:
    :param required_keys: list of keys to bind to actions (using prompt_toolkit.key_binding.KeyBindings format).
    For single key bindings, use a string (e.g. "c-c"). For multiple keys, use a comma-separated string (e.g. "c-c,c-q,escape").
    If None, default keys are set: up, down, enter, escape, ctrl-c.
    :return: prompt_toolkit.key_binding.KeyBindings object
    """
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

    def chat(event):
        ui_instance.result = "chat"
        event.app.exit()

    def dashboard(event):
        ui_instance.result = "dashboard"
        event.app.exit()

    def sessions(event):
        ui_instance.result = "sessions"
        event.app.exit()

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

    def exit_from_chat(event):
        ui_instance.exit_to = UIView.MENU
        event.app.exit()

    def scroll_top(event):
        """Suitable for _Chat instance"""
        if ui_instance.chat_buffer:
            ui_instance.chat_buffer.cursor_position = 0

    def scroll_bottom(event):
        """Suitable for _Chat instance"""
        if ui_instance.chat_buffer:
            ui_instance.chat_buffer.cursor_position = len(ui_instance.chat_buffer.text)

    key_to_action_mapping = {
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
        "end": scroll_bottom
    }

    kb = KeyBindings()

    for key in required_keys:
        func = key_to_action_mapping.get(key, None)
        if not func:
            continue

        for k in key.split(","):
            kb.add(k)(func)

    return kb
