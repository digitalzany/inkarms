from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING

from prompt_toolkit import Application
from prompt_toolkit.application import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition
from prompt_toolkit.layout import (Window, FormattedTextControl, BufferControl, ScrollbarMargin, HSplit, Layout,
                                   FloatContainer, Float)

from inkarms.config.theme import THEME_STYLES, STYLE
from inkarms.ui.backends.rich_backend.helpers import render_styled_text, render_markdown_ansi
from inkarms.ui.backends.rich_backend.key_binding import bind_keys
from inkarms.ui.protocol import UIView

if TYPE_CHECKING:
    from inkarms.ui.backends.rich_backend.backend import RichBackend


class ChatView:
    """Chat view component"""

    def __init__(self, backend: "RichBackend"):
        self.backend = backend
        self.exit_to: UIView | None = UIView.MENU
        self.pending_message: str | None = None
        self.streaming = False
        self.streaming_content = ""
        self.app: Application | None = None
        self.scroll_offset = 0
        self.total_lines = 0
        self.input_area = None
        self._key_bindings = None
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
        messages = self.backend._messages

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
        s = self.backend._status
        if self.streaming:
            return [("class:info", " Streaming response... | Ctrl+C to cancel ")]

        model = s.model.split("/")[1] if "/" in s.model else s.model
        status = [
            ("class:status-bar", " "),
            ("class:status-provider", f"{s.provider or '—'}"),
            ("class:status-bar", " | "),
            ("class:status-model", f"{model or '—'}"),
            ("class:status-bar", " | "),
            ("class:status-session", f"{s.session or '—'}"),
            ("class:status-bar", f" ({s.message_count}) | "),
            ("class:status-tokens", f"{s.total_tokens:,} tok"),
            ("class:status-bar", " | "),
            ("class:status-cost", f"${s.total_cost:.2f}"),
        ]

        # Add context percentage when session manager is active
        if self.backend._session_manager:
            try:
                usage = self.backend._session_manager.get_context_usage()
                percent = usage.usage_percent * 100
                ctx_style = "class:warning" if usage.should_compact else "class:status-bar"
                status.extend(
                    [
                        ("class:status-bar", " | "),
                        (ctx_style, f"ctx {percent:.0f}%"),
                    ]
                )
            except Exception:
                pass

        # Add tools indicator
        if self.backend._agent_config and self.backend._agent_config.enable_tools:
            tool_count = len(self.backend._tool_registry) if self.backend._tool_registry else 0
            mode = self.backend._agent_config.approval_mode.value
            status.extend([
                ("class:status-bar", " | "),
                ("class:tool-running", f"Tools: {tool_count} ({mode})"),
            ])
        else:
            status.extend([
                ("class:status-bar", " | "),
                ("class:status-bar", "Tools: off"),
            ])

        status.append(("class:status-bar", " "))
        return status

    def _handle_command(self, text: str):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # Navigation commands that exit the chat view
        nav_map = {
            "/quit": None,
            "/q": None,
            "/exit": None,
            "/menu": UIView.MENU,
            "/m": UIView.MENU,
            "/dashboard": UIView.DASHBOARD,
            "/d": UIView.DASHBOARD,
            "/sessions": UIView.SESSIONS,
            "/s": UIView.SESSIONS,
            "/config": UIView.CONFIG,
            "/cfg": UIView.CONFIG,
        }
        if cmd in nav_map:
            self.exit_to = nav_map[cmd]
            get_app().exit()
            return

        # In-chat commands
        if cmd == "/clear":
            self._cmd_clear()
        elif cmd == "/help":
            self.pending_message = (
                "Commands: /menu /dashboard /sessions /clear /usage /status "
                "/save [name] /load <name> /history /model /tools /agent [mode] /quit "
                "| Use @file to include file"
            )
        elif cmd == "/usage":
            self._cmd_usage()
        elif cmd == "/status":
            self._cmd_status()
        elif cmd == "/save":
            self._cmd_save(arg)
        elif cmd == "/load":
            self._cmd_load(arg)
        elif cmd == "/history":
            self._cmd_history()
        elif cmd == "/model":
            self._cmd_model(arg)
        elif cmd == "/chat":
            pass  # Already in chat
        elif cmd == "/tools":
            self._cmd_tools()
        elif cmd == "/agent":
            self._cmd_agent(arg)
        else:
            self.pending_message = f"Unknown command: {cmd}. Type /help for available commands."

        # Refresh display
        if self.app:
            self.app.invalidate()

    def _cmd_clear(self):
        self.backend._messages = []
        if self.backend._session_manager:
            self.backend._session_manager.clear_session()
        self.backend._session_dirty = True
        self.backend._status.message_count = 0
        self.backend._status.total_tokens = 0
        self.backend._status.total_cost = 0.0
        self.pending_message = "Chat cleared"

    def _cmd_usage(self):
        if self.backend._session_manager:
            usage = self.backend._session_manager.get_context_usage()
            info = self.backend._session_manager.get_session_info()
            self.pending_message = (
                f"Tokens: {usage.current_tokens:,}/{usage.max_tokens:,} "
                f"({usage.usage_percent * 100:.1f}%) | "
                f"Cost: ${info['total_cost']:.4f} | "
                f"Turns: {info['turn_count']}"
            )
        else:
            s = self.backend._status
            self.pending_message = f"Tokens: {s.total_tokens:,} | Cost: ${s.total_cost:.4f}"

    def _cmd_status(self):
        status_parts = [
            f"Provider: {self.backend._status.provider}",
            f"Model: {self.backend._status.model}",
        ]
        if self.backend._session_manager:
            usage = self.backend._session_manager.get_context_usage()
            status_parts.append(f"Context: {usage.usage_percent * 100:.1f}%")
            if usage.should_handoff:
                status_parts.append("HANDOFF RECOMMENDED")
            elif usage.should_compact:
                status_parts.append("Compaction recommended")
        self.pending_message = " | ".join(status_parts)

    def _cmd_save(self, arg: str):
        name = arg or f"session-{datetime.now().strftime('%Y%m%d-%H%M')}"
        if self.backend._session_manager:
            try:
                self.backend._session_manager.save_snapshot(name)
                self.pending_message = f"Session saved as '{name}'"
            except Exception as e:
                self.pending_message = f"Save failed: {e}"
        else:
            self.pending_message = "Session manager not available"

    def _cmd_load(self, arg: str):
        if not self.backend._session_manager:
            self.pending_message = "Session manager not available"
            return

        if not arg:
            # List available snapshots
            entries = self.backend._session_manager.list_memory("snapshot")
            if entries:
                names = [e.name for e in entries]
                self.pending_message = f"Snapshots: {', '.join(names)} | /load <name>"
            else:
                self.pending_message = "No snapshots found"
            return

        session = self.backend._session_manager.load_snapshot(arg)
        if session:
            self.backend._rebuild_messages_from_session()
            self.pending_message = f"Session '{arg}' loaded"
        else:
            self.pending_message = f"Snapshot '{arg}' not found"

    def _cmd_history(self):
        if self.backend._session_manager:
            turns = self.backend._session_manager.session.turns
            if turns:
                count = len(turns)
                first = turns[0].timestamp.strftime("%H:%M")
                last = turns[-1].timestamp.strftime("%H:%M")
                self.pending_message = f"History: {count} turns ({first} - {last})"
            else:
                self.pending_message = "No history in current session"
        else:
            self.pending_message = f"Messages: {len(self.backend._messages)}"

    def _cmd_model(self, arg: str):
        if arg and self.backend._session_manager:
            self.backend._session_manager.set_model(arg)
            self.backend._status.model = arg
            self.pending_message = f"Model changed to: {arg}"
        else:
            self.pending_message = f"Current model: {self.backend._status.model}"

    def _cmd_tools(self):
        registry = self.backend._tool_registry
        if not registry or len(registry) == 0:
            self.pending_message = "No tools registered"
            return
        tools = registry.list_tools()
        parts = []
        for tool in tools:
            label = f"{tool.name} [!]" if tool.is_dangerous else tool.name
            parts.append(label)
        mode = "off"
        if self.backend._agent_config:
            mode = self.backend._agent_config.approval_mode.value
        self.pending_message = f"Tools ({mode}): {', '.join(parts)}"

    def _cmd_agent(self, arg: str):
        config = self.backend._agent_config
        if not config:
            self.pending_message = "Agent not configured"
            return
        if not arg:
            mode = config.approval_mode.value
            enabled = config.enable_tools
            iters = config.max_iterations
            self.pending_message = (
                f"Agent: tools={'on' if enabled else 'off'} mode={mode} "
                f"max_iterations={iters}"
            )
            return
        from inkarms.models.agent import ApprovalMode

        valid = {m.value for m in ApprovalMode}
        if arg in valid:
            config.approval_mode = ApprovalMode(arg)
            self.pending_message = f"Agent mode changed to: {arg}"
        elif arg == "on":
            config.enable_tools = True
            self.pending_message = "Tools enabled"
        elif arg == "off":
            config.enable_tools = False
            self.pending_message = "Tools disabled"
        else:
            self.pending_message = "Usage: /agent [on|off|auto|manual|disabled]"

    def run(self) -> UIView | None:
        from prompt_toolkit.widgets import Frame, TextArea
        from inkarms.ui.backends.rich_backend.backend import COMMAND_COMPLETER, AnsiLexer

        # Input area with command completion
        def _on_accept_handler(buff: Buffer) -> bool:
            self._on_accept(buff)
            self.input_area.text = ""
            return True

        self.input_area = TextArea(
            height=1,
            multiline=False,
            wrap_lines=False,
            completer=COMMAND_COMPLETER,
            complete_while_typing=True,
            accept_handler=_on_accept_handler,
            style="class:user-input",
        )

        # Layout
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

        # Use Buffer + BufferControl for native scrolling
        from prompt_toolkit.document import Document

        self.chat_buffer = Buffer(read_only=True)

        def update_chat_buffer():
            """Update chat buffer with markdown-rendered content as ANSI text."""
            lines = []
            messages = self.backend._messages

            # Calculate available width (fallback to 100 if app not fully ready)
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
                        # For assistant, we use a Panel and omit the separate header
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
                # Show tool blocks from agent mode
                for block in self._tool_blocks:
                    lines.append(block)

                # Streaming content (standard streaming mode)
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
                    # Show approval prompt
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

            if self.pending_message:
                lines.append("")
                lines.append(f"  {self.pending_message}")

            text = "\n".join(lines)
            # Move cursor to end for auto-scroll
            self.chat_buffer.set_document(Document(text, len(text)), bypass_readonly=True)

        # Initial update
        update_chat_buffer()
        self._update_chat_buffer = update_chat_buffer

        chat_control = BufferControl(
            buffer=self.chat_buffer,
            focusable=True,
            lexer=AnsiLexer(),
        )

        chat_window = Window(
            content=chat_control,
            wrap_lines=True,
            right_margins=[ScrollbarMargin(display_arrows=True)],
            scroll_offsets=None,  # Let the window scroll freely
            allow_scroll_beyond_bottom=True,
        )

        status_bar = Window(
            content=FormattedTextControl(self._get_status_text),
            height=1,
        )

        # Use FloatContainer for completion menu
        body = HSplit(
            [
                header,
                Frame(chat_window, title="Chat"),
                Frame(self.input_area, title="You (Enter to send, Tab for completions)"),
                status_bar,
            ]
        )

        from prompt_toolkit.layout.menus import CompletionsMenu

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

        self.app = Application(
            layout=layout,
            key_bindings=self._key_bindings,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )
        self.app.run()
        return self.exit_to


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

            if self.backend._agent_config:
                self.backend._agent_config.approval_mode = ApprovalMode.AUTO
            self._approval_result = True
            self._approval_event.set()


    def _on_accept(self, buff):
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
            self.backend._agent_config is not None
            and self.backend._agent_config.enable_tools
            and self.backend._tool_registry is not None
            and len(self.backend._tool_registry) > 0
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

        self.backend._process_query_streaming(text, on_chunk, on_complete, on_error)

    def _start_agent_query(self, text):
        """Start an agent query with tool use."""
        self.streaming = True
        self.streaming_content = ""
        self._tool_blocks = []
        self._current_tool_status = "Thinking..."

        self.backend._process_query_agent(
            text,
            self._handle_agent_event,
            self._handle_agent_approval,
            self._handle_agent_complete,
            self._handle_agent_error,
        )

    def _handle_agent_event(self, event):
        """Handle agent loop events (tool start/complete/error)."""
        from inkarms.models.agent import EventType

        if event.event_type == EventType.TOOL_START:
            self._current_tool_status = f"Running {event.tool_name}..."
        elif event.event_type == EventType.TOOL_COMPLETE:
            data = event.data or {}
            block = self._render_tool_block(
                event.tool_name, "success",
                data.get("execution_time", 0), data.get("output_preview", ""),
            )
            self._tool_blocks.append(block)
            self._current_tool_status = ""
        elif event.event_type == EventType.TOOL_ERROR:
            data = event.data or {}
            error_msg = data.get("error") or data.get("exception") or "Unknown error"
            block = self._render_tool_block(
                event.tool_name, "error",
                data.get("execution_time", 0), error_msg,
            )
            self._tool_blocks.append(block)
            self._current_tool_status = ""
        elif event.event_type == EventType.TOOL_DENIED:
            block = self._render_tool_block(
                event.tool_name, "denied", 0, "Denied by user",
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
            tool.name, str(tool_call.input)[:200], tool.is_dangerous,
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
        if self.backend._session_manager:
            try:
                usage = self.backend._session_manager.get_context_usage()
                if usage.should_handoff:
                    self.pending_message = (
                        f"Context at {usage.usage_percent * 100:.0f}% capacity. "
                        f"Consider /save and starting a new session."
                    )
                elif usage.should_compact:
                    self.pending_message = (
                        f"Context at {usage.usage_percent * 100:.0f}% - "
                        f"compaction recommended"
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
