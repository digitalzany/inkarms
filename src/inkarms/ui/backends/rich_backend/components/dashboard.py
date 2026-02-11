from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit import HTML, Application
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import HSplit, Window, FormattedTextControl, Layout, FloatContainer, Float, CompletionsMenu
from prompt_toolkit.widgets import TextArea

from inkarms.config.theme import STYLE
from inkarms.ui.backends.rich_backend.key_binding import bind_keys
from inkarms.ui.protocol import UIView

if TYPE_CHECKING:
    from inkarms.ui.backends.rich_backend.backend import RichBackend


class DashboardView:
    """Dashboard view component."""

    def __init__(self, backend: "RichBackend"):
        self.backend = backend
        self.exit_to = UIView.MENU

    def get_header(self):
        return self.backend._get_status_bar()

    def get_content(self):
        s = self.backend._status
        content = [
            ("class:title", "\n  Dashboard\n"),
            ("", "\n"),
            ("class:info", "  ┌─ Configuration ─────────────────────────────────────\n"),
            ("class:info", "  │  Provider     "),
            ("class:status-provider", f"{s.provider or '—'}\n"),
            ("class:info", "  │  Model        "),
            ("", f"{s.model or '—'}\n"),
            ("class:info", "  │  API Key      "),
            (
                "class:success" if s.api_key_set else "class:warning",
                f"{'✓ configured' if s.api_key_set else '✗ not set'}\n",
            ),
            ("", "\n"),
            ("class:info", "  ┌─ Current Session ────────────────────────────────────\n"),
            ("class:info", "  │  Name         "),
            ("class:success", f"{s.session or 'none'}\n"),
            ("class:info", "  │  Messages     "),
            ("", f"{s.message_count}\n"),
            ("", "\n"),
            ("class:info", "  ┌─ Usage Statistics ──────────────────────────────────\n"),
            ("class:info", "  │  Tokens       "),
            ("class:success", f"{s.total_tokens:,}\n"),
            ("class:info", "  │  Est. Cost    "),
            ("class:warning", f"${s.total_cost:.4f}\n"),
        ]

        # Add context usage from session manager
        if self.backend._session_manager:
            try:
                usage = self.backend._session_manager.get_context_usage()
                percent = usage.usage_percent * 100
                ctx_style = "class:warning" if usage.should_compact else "class:success"
                content.extend(
                    [
                        ("", "\n"),
                        (
                            "class:info",
                            "  ┌─ Context Window ────────────────────────────────────\n",
                        ),
                        ("class:info", "  │  Usage        "),
                        (
                            ctx_style,
                            f"{usage.current_tokens:,}/{usage.max_tokens:,} ({percent:.1f}%)\n",
                        ),
                        ("class:info", "  │  Remaining    "),
                        ("", f"{usage.tokens_remaining:,} tokens\n"),
                        ("class:info", "  │  Status       "),
                    ]
                )
                if usage.should_handoff:
                    content.append(("class:warning", "HANDOFF RECOMMENDED\n"))
                elif usage.should_compact:
                    content.append(("class:warning", "Compaction recommended\n"))
                else:
                    content.append(("class:success", "OK\n"))
            except Exception:
                pass

        # Tools section
        if self.backend._agent_config:
            ac = self.backend._agent_config
            tool_count = len(self.backend._tool_registry) if self.backend._tool_registry else 0
            content.extend([
                ("", "\n"),
                ("class:info", "  ┌─ Tools & Agent ─────────────────────────────────────\n"),
                ("class:info", "  │  Tools        "),
                ("class:success" if ac.enable_tools else "class:warning",
                 f"{tool_count} registered ({'enabled' if ac.enable_tools else 'disabled'})\n"),
                ("class:info", "  │  Mode         "),
                ("", f"{ac.approval_mode.value}\n"),
                ("class:info", "  │  Max Iters    "),
                ("", f"{ac.max_iterations}\n"),
            ])

        content.extend(
            [
                ("", "\n"),
                ("class:info", f"  Total sessions: {len(self.backend.get_sessions())}\n"),
            ]
        )
        return content

    def get_footer(self):
        return [
            ("class:hint", " /"),
            ("class:hint-dim", "chat "),
            ("class:hint", "/"),
            ("class:hint-dim", "sessions "),
            ("class:hint", "/"),
            ("class:hint-dim", "menu "),
            ("class:hint", "/"),
            ("class:hint-dim", "quit "),
            ("class:hint", "│ Ctrl+C"),
            ("class:hint-dim", " back"),
        ]

    def run(self) -> UIView | None:
        from inkarms.ui.backends.rich_backend.backend import COMMAND_COMPLETER

        input_area = TextArea(
            height=1,
            prompt=HTML('<style fg="#e94560">> </style>'),
            multiline=False,
            completer=COMMAND_COMPLETER,
            complete_while_typing=True,
        )

        def handle(buff: Buffer) -> bool:
            cmd = buff.text.strip().lower()
            buff.reset()
            if cmd in ("/chat", "/c"):
                self.exit_to = UIView.CHAT
                get_app().exit()
            elif cmd in ("/menu", "/m"):
                self.exit_to = UIView.MENU
                get_app().exit()
            elif cmd in ("/sessions", "/s"):
                self.exit_to = UIView.SESSIONS
                get_app().exit()
            elif cmd in ("/quit", "/q"):
                self.exit_to = None  # Signal to quit
                get_app().exit()
            return True

        input_area.accept_handler = handle

        kb = bind_keys(self, ["c-c", "tab", "backspace"])

        body = HSplit(
            [
                Window(FormattedTextControl(self.get_header), height=1),
                Window(char="─", height=1, style="class:frame"),
                Window(FormattedTextControl(self.get_content)),
                Window(FormattedTextControl(self.get_footer), height=1),
                Window(char="─", height=1, style="class:frame"),
                input_area,
            ]
        )

        layout = Layout(
            FloatContainer(
                content=body,
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=16, scroll_offset=1),
                    )
                ],
            )
        )
        layout.focus(input_area)

        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()
        return self.exit_to
