from __future__ import annotations

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import FormattedTextControl, HSplit, Layout, Window
from prompt_toolkit.widgets import TextArea

from inkarms.config.theme import STYLE
from inkarms.ui.backends.rich_backend.key_binding import bind_keys


class TextInput:
    """Text input component."""

    def __init__(self, title: str, prompt: str = "> ", password: bool = False, default: str = ""):
        self.title = title
        self.prompt_text = prompt
        self.password = password
        self.default = default
        self.cancelled = False

    def run(self) -> str | None:
        kb = bind_keys(self, ["escape", "c-c"])

        def _accept_and_exit(buff: Buffer) -> bool:
            get_app().exit()
            return True

        text_area = TextArea(
            text=self.default,
            multiline=False,
            password=self.password,
            accept_handler=_accept_and_exit,
        )

        def get_title():
            return [
                ("class:title", f"\n  {self.title}\n\n"),
                ("class:hint", "  Enter to confirm, Esc to cancel\n\n"),
            ]

        layout = Layout(
            HSplit(
                [
                    Window(FormattedTextControl(get_title), height=5),
                    Window(
                        FormattedTextControl(lambda: [("class:prompt", f"  {self.prompt_text}")]),
                        height=1,
                        width=len(self.prompt_text) + 2,
                    ),
                    text_area,
                ]
            )
        )
        layout.focus(text_area)

        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()

        return None if self.cancelled else text_area.text
