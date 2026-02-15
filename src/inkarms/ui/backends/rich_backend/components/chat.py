from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import (
    BufferControl,
    Float,
    FloatContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    ScrollbarMargin,
    Window,
)

from inkarms.config.theme import STYLE, THEME_STYLES
from inkarms.ui.backends.rich_backend.helpers import render_markdown_ansi, render_styled_text
from inkarms.ui.backends.rich_backend.key_binding import bind_keys
from inkarms.ui.protocol import UIView

if TYPE_CHECKING:
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.widgets import TextArea

    from inkarms.ui.backends.rich_backend.backend import RichBackend


class ChatView:
    """Chat view component"""

    def __init__(self, backend: RichBackend):
        self.backend = backend
        self.exit_to: UIView | None = UIView.MENU
        self.pending_message: str | None = None
        self.streaming = False
        self.streaming_content = ""
        self.app: Application | None = None
        self.scroll_offset = 0
        self.total_lines = 0
        self.input_area: TextArea = self._build_input_area()
        self._key_bindings: KeyBindings | None = None
        self.chat_buffer: Buffer = Buffer(read_only=True)
        # Agent/tool state
        self._tool_blocks: list[str] = []
        self._current_tool_status: str = ""
        self._approval_event = threading.Event()
        self._approval_result: bool = False
        self._pending_approval_info: tuple | None = None

        self.add_key_bindings()

    def _get_history_text(self):
        """Format message history for display - same pattern as working demo."""
        lines = []
        messages = self.backend.messages

        if not messages and not self.streaming:
            lines.append(("class:info", "  Start typing to chat...\n"))
            lines.append(("class:hint", "  Type /help for commands\n"))
            return lines

        for msg in messages:
            ts = msg.timestamp if self.backend.config.show_timestamps else ""
            if msg.role == "user":
                if ts:
                    lines.append(("class:info", f"[{ts}] "))
                lines.append(("class:user", "You: "))
                lines.append(("", f"{msg.content}\n\n"))
            else:
                if ts:
                    lines.append(("class:info", f"[{ts}] "))
                lines.append(("class:assistant", "Assistant: "))
                # Plain text - prompt_toolkit doesn't support ANSI from Rich
                lines.append(("", f"{msg.content}\n\n"))

        # Show streaming content
        if self.streaming:
            lines.append(("class:assistant", "Assistant: "))
            if self.streaming_content:
                lines.append(("", f"{self.streaming_content}▌\n"))
            else:
                lines.append(("class:info", "thinking...▌\n"))

        if self.pending_message:
            lines.append(("class:warning", f"\n  {self.pending_message}\n"))

        return lines

    def _get_status_text(self):
        """Status bar text."""
        from inkarms.ui.backends.rich_backend.helpers import build_status_bar

        return build_status_bar(
            self.backend.status,
            agent_config=self.backend.agent_config,
            tool_registry=self.backend.tool_registry,
            session_manager=self.backend.session_manager,
            streaming=self.streaming,
            model_format="short",
        )

    def _handle_command(self, text: str):
        from inkarms.ui.backends.rich_backend.commands import ChatCommandHandler

        result = ChatCommandHandler(self.backend).handle(text)
        if result.should_exit:
            self.exit_to = result.navigate_to
            get_app().exit()
            return
        if result.message:
            self.pending_message = result.message
        if self.app:
            self.app.invalidate()

    def run(self) -> UIView | None:
        self.chat_buffer = Buffer(read_only=True)
        self._update_chat_buffer()
        layout = self._build_layout()

        self.app = Application(
            layout=layout,
            key_bindings=self._key_bindings,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )
        self.app.run()
        return self.exit_to

    def _build_input_area(self) -> TextArea:
        """Create the input TextArea with command completion."""
        from prompt_toolkit.widgets import TextArea

        from inkarms.ui.backends.rich_backend.completers import COMMAND_COMPLETER

        def _on_accept_handler(buff: Buffer) -> bool:
            self._on_accept(buff)
            # Ensure input_area is not None before accessing text
            if self.input_area:
                self.input_area.text = ""
            return True

        return TextArea(
            height=1,
            multiline=False,
            wrap_lines=False,
            completer=COMMAND_COMPLETER,
            complete_while_typing=True,
            accept_handler=_on_accept_handler,
            style="class:user-input",
        )

    def _update_chat_buffer(self) -> None:
        """Update chat buffer with markdown-rendered content as ANSI text."""
        from prompt_toolkit.document import Document

        try:
            lines = []
            messages = self.backend.messages

            try:
                width = get_app().output.get_size().columns - 4
            except Exception:
                width = 100

            if not messages and not self.streaming:
                lines.append("  Start typing to chat...")
                lines.append("  Type /help for commands")
            else:
                for msg in messages:
                    ts = (
                        f"[{msg.timestamp}] "
                        if msg.timestamp and self.backend.config.show_timestamps
                        else ""
                    )
                    if msg.role == "user":
                        lines.append(
                            render_styled_text(f"{ts}You: {msg.content}", THEME_STYLES["user"])
                        )
                        lines.append("")
                    else:
                        try:
                            rendered = render_markdown_ansi(
                                msg.content,
                                width=width,
                                style=THEME_STYLES.get("assistant-text", ""),
                                wrap_in_panel=True,
                                panel_title=f"{ts}Assistant",
                                panel_border_style=THEME_STYLES["assistant"],
                            )
                            lines.append(rendered)
                        except Exception:
                            lines.append(msg.content)
                        lines.append("")

            if self.streaming:
                self._render_streaming_content(lines, width)

            if self.pending_message:
                lines.append("")
                lines.append(f"  {self.pending_message}")

            text = "\n".join(lines)
            self.chat_buffer.set_document(Document(text, len(text)), bypass_readonly=True)
        except Exception as e:
            # Fallback to avoid empty screen on error
            import traceback
            import contextlib

            traceback.print_exc()
            with contextlib.suppress(Exception):
                self.chat_buffer.set_document(
                    Document(f"Error updating UI: {e}", 0), bypass_readonly=True
                )

    def _render_streaming_content(self, lines: list[str], width: int) -> None:
        """Render streaming, tool, and approval content into lines."""
        for block in self._tool_blocks:
            lines.append(block)

        if self.streaming_content:
            try:
                rendered = render_markdown_ansi(
                    self.streaming_content + "▌",
                    width=width,
                    style=THEME_STYLES.get("assistant-text", ""),
                    wrap_in_panel=True,
                    panel_title="Assistant (thinking...)",
                    panel_border_style=THEME_STYLES["assistant"],
                )
                lines.append(rendered)
            except Exception:
                lines.append(self.streaming_content + "▌")
        elif self._pending_approval_info:
            name, args_str, dangerous = self._pending_approval_info
            danger_tag = " [DANGEROUS]" if dangerous else ""
            lines.append(
                render_styled_text(
                    f"  Tool requires approval: {name}{danger_tag}",
                    THEME_STYLES["warning"],
                )
            )
            lines.append(f"  Args: {args_str[:100]}")
            lines.append(
                render_styled_text(
                    "  [a] Allow  [d] Deny  [A] Allow All",
                    THEME_STYLES["hint"],
                )
            )
        elif self._current_tool_status:
            lines.append(
                render_styled_text(
                    f"  {self._current_tool_status}▌",
                    THEME_STYLES["tool-running"],
                )
            )
        else:
            lines.append(render_styled_text("Assistant:", THEME_STYLES["assistant"]))
            lines.append("thinking...▌")

    def _build_layout(self) -> Layout:
        """Build the prompt_toolkit layout for the chat view."""
        from prompt_toolkit.layout.menus import CompletionsMenu
        from prompt_toolkit.widgets import Frame

        from inkarms.ui.backends.rich_backend.completers import AnsiLexer

        header = Window(
            content=FormattedTextControl(
                lambda: [
                    (
                        "class:header",
                        " InkArms Chat | /help | PgUp/PgDn or mouse scroll | Ctrl+C menu ",
                    )
                ]
            ),
            height=1,
        )

        chat_control = BufferControl(
            buffer=self.chat_buffer,
            focusable=True,
            lexer=AnsiLexer(),
        )

        chat_window = Window(
            content=chat_control,
            wrap_lines=True,
            right_margins=[ScrollbarMargin(display_arrows=True)],
            scroll_offsets=None,
            allow_scroll_beyond_bottom=True,
        )

        status_bar = Window(
            content=FormattedTextControl(self._get_status_text),
            height=1,
        )

        body = HSplit(
            [
                header,
                Frame(chat_window, title="Chat"),
                Frame(self.input_area, title="You (Enter to send, Tab for completions)"),
                status_bar,
            ]
        )

        layout = Layout(
            FloatContainer(
                content=body,
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        content=CompletionsMenu(max_height=8, scroll_offset=1),
                    )
                ],
            )
        )
        layout.focus(self.input_area)
        return layout

    def add_key_bindings(self) -> None:
        self._key_bindings = bind_keys(self, ["c-c,c-q,escape", "home", "end"])

        # Scroll by moving cursor in the buffer (BufferControl native scrolling)
        def scroll_chat_up(lines: int):
            if self.chat_buffer:
                doc = self.chat_buffer.document
                # Move cursor up by `lines` lines
                for _ in range(lines):
                    new_pos = doc.get_cursor_up_position()
                    if new_pos == 0 and self.chat_buffer.cursor_position == 0:
                        break
                    self.chat_buffer.cursor_position += new_pos
                    doc = self.chat_buffer.document

        def scroll_chat_down(lines: int):
            if self.chat_buffer:
                doc = self.chat_buffer.document
                # Move cursor down by `lines` lines
                for _ in range(lines):
                    new_pos = doc.get_cursor_down_position()
                    if new_pos == 0:
                        break
                    self.chat_buffer.cursor_position += new_pos
                    doc = self.chat_buffer.document

        @self._key_bindings.add("pageup")
        def page_up(event):
            scroll_chat_up(10)

        @self._key_bindings.add("pagedown")
        def page_down(event):
            scroll_chat_down(10)

        @self._key_bindings.add("c-u")
        def scroll_up_half(event):
            scroll_chat_up(20)

        @self._key_bindings.add("c-d")
        def scroll_down_half(event):
            scroll_chat_down(20)

        # Mouse scroll support - move cursor to scroll the view
        @self._key_bindings.add("<scroll-up>")
        def mouse_scroll_up(event):
            scroll_chat_up(3)

        @self._key_bindings.add("<scroll-down>")
        def mouse_scroll_down(event):
            scroll_chat_down(3)

        # Tool approval key bindings (only active when approval is pending)
        approval_pending = Condition(lambda: self._pending_approval_info is not None)

        @self._key_bindings.add("a", filter=approval_pending)
        def approve_tool(event):
            self._approval_result = True
            self._approval_event.set()

        @self._key_bindings.add("d", filter=approval_pending)
        def deny_tool(event):
            self._approval_result = False
            self._approval_event.set()

        @self._key_bindings.add("A", filter=approval_pending)
        def approve_all_tools(event):
            from inkarms.models.agent import ApprovalMode

            if self.backend.agent_config:
                self.backend.agent_config.approval_mode = ApprovalMode.AUTO
            self._approval_result = True
            self._approval_event.set()

    def _on_accept(self, buff: Buffer) -> None:
        """Handle input submission."""
        text = buff.text.strip()
        if not text or self.streaming:
            return
        buff.text = ""
        self.pending_message = None

        # Handle commands
        if text.startswith("/"):
            self._handle_command(text)
            self._update_chat_buffer()
            return

        # Regular message - add to history
        self.backend.add_message("user", text)
        self._update_chat_buffer()

        # Dispatch: agent mode vs streaming mode
        tools_enabled = (
            self.backend.agent_config is not None
            and self.backend.agent_config.enable_tools
            and self.backend.tool_registry is not None
            and len(self.backend.tool_registry) > 0
        )
        if tools_enabled:
            self._start_agent_query(text)
        else:
            self._start_streaming_query(text)

    def _start_streaming_query(self, text):
        """Start a streaming query (no tools)."""
        self.streaming = True
        self.streaming_content = ""

        def on_chunk(chunk):
            self.streaming_content += chunk
            self._update_chat_buffer()
            if self.app:
                self.app.invalidate()

        def on_complete(full_response):
            self.streaming = False
            self.streaming_content = ""
            self.backend.add_message("assistant", full_response)
            self._show_context_warnings()
            self._update_chat_buffer()
            if self.app:
                self.app.invalidate()

        def on_error(error):
            self.streaming = False
            self.streaming_content = ""
            self.pending_message = f"Error: {error}"
            self._update_chat_buffer()
            if self.app:
                self.app.invalidate()

        self.backend.process_query_streaming(text, on_chunk, on_complete, on_error)

    def _start_agent_query(self, text):
        """Start an agent query with tool use."""
        self.streaming = True
        self.streaming_content = ""
        self._tool_blocks = []
        self._current_tool_status = "Thinking..."

        def on_chunk(chunk):
            self.streaming_content += chunk
            self._update_chat_buffer()
            if self.app:
                self.app.invalidate()

        self.backend.process_query_agent(
            text,
            self._handle_agent_event,
            self._handle_agent_approval,
            self._handle_agent_complete,
            self._handle_agent_error,
            on_chunk=on_chunk,
        )

    def _handle_agent_event(self, event):
        """Handle agent loop events (tool start/complete/error)."""
        from inkarms.models.agent import EventType

        # Ignore stream chunks in event loop as they are handled by on_chunk callback
        # This prevents double-updating and flicker
        if event.event_type == EventType.STREAM_CHUNK:
            return

        if event.event_type == EventType.TOOL_START:
            self.streaming_content = ""  # Clear streamed text so tool UI shows
            self._current_tool_status = f"Running {event.tool_name}..."
        elif event.event_type == EventType.TOOL_COMPLETE:
            data = event.data or {}
            block = self._render_tool_block(
                event.tool_name,
                "success",
                data.get("execution_time", 0),
                data.get("output_preview", ""),
            )
            self._tool_blocks.append(block)
            self._current_tool_status = ""
        elif event.event_type == EventType.TOOL_ERROR:
            data = event.data or {}
            error_msg = data.get("error") or data.get("exception") or "Unknown error"
            block = self._render_tool_block(
                event.tool_name,
                "error",
                data.get("execution_time", 0),
                error_msg,
            )
            self._tool_blocks.append(block)
            self._current_tool_status = ""
        elif event.event_type == EventType.TOOL_DENIED:
            block = self._render_tool_block(
                event.tool_name,
                "denied",
                0,
                "Denied by user",
            )
            self._tool_blocks.append(block)
            self._current_tool_status = ""
        elif event.event_type == EventType.AI_RESPONSE:
            self._current_tool_status = "Thinking..."
        self._update_chat_buffer()
        if self.app:
            self.app.invalidate()

    def _handle_agent_approval(self, tool_call, tool):
        """Handle tool approval request (blocks until user responds)."""
        self._pending_approval_info = (
            tool.name,
            str(tool_call.input)[:200],
            tool.is_dangerous,
        )
        self._approval_event.clear()
        if self.app:
            self._update_chat_buffer()
            self.app.invalidate()
        self._approval_event.wait()
        self._pending_approval_info = None
        if self.app:
            self._update_chat_buffer()
            self.app.invalidate()
        return self._approval_result

    def _handle_agent_complete(self, result):
        """Handle agent loop completion."""
        self.streaming = False
        self.streaming_content = ""
        self._current_tool_status = ""
        if result.final_response:
            self.backend.add_message("assistant", result.final_response)
        elif result.error:
            # Show first line only — full error is in the tool block
            short_err = result.error.split("\n")[0][:120] if result.error else "Unknown"
            self.pending_message = f"Agent error: {short_err}"
        self._tool_blocks = []
        self._show_context_warnings()
        self._update_chat_buffer()
        if self.app:
            self.app.invalidate()

    def _handle_agent_error(self, error_str):
        """Handle agent loop error."""
        self.streaming = False
        self.streaming_content = ""
        self._current_tool_status = ""
        self._tool_blocks = []
        # Show first line only to avoid overwhelming the chat
        short_err = error_str.split("\n")[0][:120] if error_str else "Unknown error"
        self.pending_message = f"Error: {short_err}"
        self._update_chat_buffer()
        if self.app:
            self.app.invalidate()

    def _show_context_warnings(self):
        """Show context usage warnings if approaching limits."""
        if self.backend.session_manager:
            try:
                usage = self.backend.session_manager.get_context_usage()
                if usage.should_handoff:
                    self.pending_message = (
                        f"Context at {usage.usage_percent * 100:.0f}% capacity. "
                        f"Consider /save and starting a new session."
                    )
                elif usage.should_compact:
                    self.pending_message = (
                        f"Context at {usage.usage_percent * 100:.0f}% - compaction recommended"
                    )
            except Exception:
                pass

    def _render_tool_block(self, tool_name, status, exec_time, output):
        """Render a collapsed tool execution block as ANSI text."""
        try:
            width = get_app().output.get_size().columns - 4
        except Exception:
            width = 100

        if status == "success":
            icon, border = "[+]", THEME_STYLES["tool-success"]
        elif status == "error":
            icon, border = "[!]", THEME_STYLES["tool-error"]
        else:
            icon, border = "[x]", THEME_STYLES["tool-denied"]

        title = f"{icon} {tool_name}"
        if exec_time:
            title += f" ({exec_time:.1f}s)"

        # Truncate output for display
        display_output = output[:300] if output else "(no output)"
        content = f"```\n{display_output}\n```"

        return render_markdown_ansi(
            content,
            width=width,
            wrap_in_panel=True,
            panel_title=title,
            panel_border_style=border,
        )
