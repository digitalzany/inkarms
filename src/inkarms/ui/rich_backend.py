"""
Rich + prompt_toolkit UI Backend.

This is the default, lightweight UI backend using Rich for formatting
and prompt_toolkit for full-screen applications and input handling.
"""

from __future__ import annotations

import traceback
import asyncio
import concurrent.futures
import io
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    BufferControl,
    Float,
    FloatContainer,
    FormattedTextControl,
    HSplit,
    Layout,
    Window,
)
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.widgets import TextArea
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from inkarms.config.theme import LOGO, STYLE, THEME_STYLES
from inkarms.config.wizard import RichWizard
from inkarms.memory import get_session_manager
from inkarms.memory.models import Snapshot
from inkarms.ui.protocol import ChatMessage, SessionInfo, StatusInfo, UIBackend, UIConfig, UIView
from inkarms.ui.session_persistence import SessionPersistence

logger = logging.getLogger(__name__)


# =============================================================================
# Command Completer
# =============================================================================


class CommandCompleter(Completer):
    """Completer for slash commands with fuzzy matching."""

    COMMANDS = [
        ("/help", "Show available commands"),
        ("/menu", "Return to main menu"),
        ("/dashboard", "Show dashboard"),
        ("/sessions", "Manage sessions"),
        ("/config", "Open configuration"),
        ("/clear", "Clear current session"),
        ("/usage", "Show token usage"),
        ("/status", "Show current status"),
        ("/model", "Show/change model"),
        ("/quit", "Exit InkArms"),
        ("/save", "Save session"),
        ("/load", "Load session"),
        ("/history", "Show message history"),
        ("/chat", "Go to chat"),
    ]

    def _fuzzy_match(self, text: str, cmd: str) -> bool:
        if cmd.startswith(text):
            return True
        text_lower = text.lower()
        cmd_lower = cmd.lower()
        t_idx = 0
        for c in cmd_lower:
            if t_idx < len(text_lower) and c == text_lower[t_idx]:
                t_idx += 1
        return t_idx == len(text_lower)

    def _match_score(self, text: str, cmd: str) -> int:
        return 0 if cmd.startswith(text) else 1

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.strip()
        if not text.startswith("/"):
            return

        matches = []
        for cmd, desc in self.COMMANDS:
            if self._fuzzy_match(text, cmd):
                matches.append((self._match_score(text, cmd), cmd, desc))

        matches.sort(key=lambda x: (x[0], x[1]))
        for score, cmd, desc in matches:
            yield Completion(cmd, start_position=-len(text), display=cmd, display_meta=desc)


COMMAND_COMPLETER = CommandCompleter()


def _render_markdown_to_tuples(text: str, width: int = 100) -> list:
    """Convert markdown to prompt_toolkit style tuples via Rich ANSI output."""
    from prompt_toolkit.formatted_text import ANSI, to_formatted_text

    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=width,
        color_system="256",
        highlight=False,
    )
    md = Markdown(text, code_theme="monokai")
    console.print(md)
    ansi_output = console.file.getvalue()
    return list(to_formatted_text(ANSI(ansi_output)))


def _render_markdown_ansi(
    text: str,
    width: int = 100,
    style: str = "",
    wrap_in_panel: bool = False,
    panel_title: str | None = None,
    panel_border_style: str = "blue",
) -> str:
    """Render markdown to ANSI-formatted string using Rich."""
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        width=width,
        color_system="256",
        highlight=False,
    )
    md = Markdown(text, code_theme="monokai", style=style)

    if wrap_in_panel:
        renderable = Panel(
            md,
            title=panel_title,
            style=style,  # Panel content style
            border_style=panel_border_style,
            expand=False,  # Let it fill width
            padding=(0, 1),
        )
    else:
        renderable = md

    console.print(renderable)
    return console.file.getvalue().rstrip()


def _render_styled_text(text: str, style_str: str) -> str:
    """Render text with a specific style to ANSI string."""
    console = Console(
        file=io.StringIO(),
        force_terminal=True,
        color_system="256",
    )
    console.print(Text(text, style=style_str), end="")
    return console.file.getvalue()


class AnsiLexer(Lexer):
    """Lexer that interprets ANSI escape codes and returns styled fragments."""

    def lex_document(self, document):
        """Return a function that returns styled fragments for a line."""
        from prompt_toolkit.formatted_text import ANSI, to_formatted_text

        lines = document.lines

        def get_line(lineno):
            if lineno < len(lines):
                line = lines[lineno]
                # Convert ANSI codes to styled fragments
                try:
                    formatted = list(to_formatted_text(ANSI(line + "\n")))
                    # Remove trailing newline from fragments
                    result = []
                    for style, text in formatted:
                        if text.endswith("\n"):
                            text = text[:-1]
                        if text:
                            result.append((style, text))
                    return result
                except Exception:
                    return [("", line)]
            return []

        return get_line

    def invalidation_hash(self):
        return None


# =============================================================================
# Rich Backend Implementation
# =============================================================================


class RichBackend(UIBackend):
    """Rich + prompt_toolkit UI backend implementation."""

    def __init__(self, ui_config: UIConfig | None = None):
        self._config = ui_config or UIConfig()
        self._status = StatusInfo()
        self._messages: list[ChatMessage] = []
        self._current_session: str | None = None
        self._configured = False
        self._streaming_content = ""
        self._session_dirty = False
        self._session_persistence: SessionPersistence | None = None

        # Will be set during initialization
        self._provider_manager = None
        self._session_manager = None
        self._skill_manager = None
        self._app_config = None

    # --- Properties ---

    @property
    def config(self) -> UIConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return self._configured

    # --- Lifecycle ---

    def initialize(self) -> None:
        """Initialize backend with InkArms core components."""
        # Trigger background model update
        try:
            from inkarms.config.updater import fetch_and_update_models

            def run_updater():
                import asyncio

                try:
                    asyncio.run(fetch_and_update_models())
                except Exception as e:
                    logger.debug(f"Model updater failed: {e}")

            threading.Thread(target=run_updater, daemon=True).start()
        except Exception as e:
            logger.debug(f"Failed to start model updater: {e}")

        try:
            from inkarms.config import get_config
            from inkarms.config.setup import is_initialized
            from inkarms.providers import get_provider_manager
            from inkarms.skills import get_skill_manager

            self._app_config = get_config()
            self._provider_manager = get_provider_manager()

            # Check if configured - verify config file exists
            self._configured = is_initialized()

            default_model = self._app_config.providers.default
            if self._configured:
                # Extract provider name from model string (e.g., "anthropic/claude-..." -> "anthropic")
                provider_name = default_model.split("/")[0] if "/" in default_model else "unknown"
                self._status.provider = provider_name
                self._status.model = default_model
                self._status.api_key_set = True  # Assume if provider is set

            self._skill_manager = get_skill_manager()

            # Initialize session manager for context tracking and persistence
            if self._configured:
                try:
                    self._session_manager = get_session_manager(model=default_model)
                    self._session_persistence = SessionPersistence(self._session_manager.storage)
                    self._update_status_from_session()

                    # Check for pending handoff
                    handoff = self._session_manager.check_for_handoff()
                    if handoff:
                        logger.info("Pending handoff found - can recover with /load")
                except Exception as e:
                    logger.debug(f"Session manager init failed: {e}")

        except Exception as e:
            logger.warning(f"Failed to initialize core components: {e}")
            self._configured = False

    def cleanup(self) -> None:
        """Cleanup resources."""
        self._persist_current_session()
        if self._session_manager:
            try:
                self._session_manager._auto_save_session()
            except Exception as e:
                logger.debug(f"Session save on cleanup failed: {e}")

    # --- Main entry point ---

    def run(self) -> None:
        """Run the UI main loop."""
        self.initialize()

        # First run wizard if not configured
        if not self._configured:
            if not self.run_config_wizard():
                self._configured = True  # Allow proceeding anyway

        current_view: UIView | None = UIView.MENU

        while True:
            try:
                if current_view is None:
                    # Quit signal
                    break
                elif current_view == UIView.MENU:
                    current_view = self.run_main_menu()
                elif current_view == UIView.CHAT:
                    if not self._current_session:
                        if not self._try_resume_recent_session():
                            self.create_session(SessionPersistence.generate_session_name())
                    current_view = self.run_chat()
                elif current_view == UIView.DASHBOARD:
                    current_view = self.run_dashboard()
                elif current_view == UIView.SESSIONS:
                    current_view = self.run_sessions()
                elif current_view == UIView.CONFIG:
                    self.run_config_wizard()
                    current_view = UIView.MENU
                elif current_view == UIView.SETTINGS:
                    current_view = self.run_settings()
                else:
                    current_view = UIView.MENU
            except KeyboardInterrupt:
                if current_view != UIView.MENU:
                    current_view = UIView.MENU
                else:
                    break

        self.cleanup()

    # --- View implementations ---

    def run_main_menu(self) -> UIView | None:
        """Display main menu. Returns None to quit."""
        menu = _MainMenu(self)
        result = menu.run()
        if result == "quit":
            return None  # Signal to exit
        return UIView(result)

    def run_chat(self) -> UIView:
        """Run chat interface."""
        chat = _ChatView(self)
        return chat.run()

    def run_dashboard(self) -> UIView | None:
        """Run dashboard."""
        dashboard = _DashboardView(self)
        return dashboard.run()

    def run_sessions(self) -> UIView:
        """Run sessions management."""
        result = self._run_sessions_menu()
        return UIView(result) if result else UIView.MENU

    def run_config_wizard(self) -> bool:
        """Run configuration wizard."""
        wizard = RichWizard(self)
        return wizard.run()

    def run_settings(self) -> UIView:
        """Run settings."""
        return UIView.MENU  # TODO: Implement settings view

    # --- Display methods ---

    def display_message(self, message: ChatMessage) -> None:
        self._messages.append(message)

    def display_streaming_start(self) -> None:
        self._streaming_content = ""

    def display_streaming_chunk(self, chunk: str) -> None:
        self._streaming_content += chunk

    def display_streaming_end(self) -> None:
        if self._streaming_content:
            self._messages.append(
                ChatMessage(
                    role="assistant",
                    content=self._streaming_content,
                    timestamp=datetime.now().strftime("%H:%M"),
                )
            )
            self._streaming_content = ""

    def display_error(self, message: str) -> None:
        # For now just log, TODO: show in UI
        logger.error(message)

    def display_info(self, message: str) -> None:
        logger.info(message)

    def display_status(self, status: StatusInfo) -> None:
        self._status = status

    # --- Input methods ---

    def get_user_input(self, prompt: str = "You: ") -> str | None:
        # This is handled by the chat view
        return None

    def get_text_input(
        self, title: str, prompt: str = "> ", password: bool = False, default: str = ""
    ) -> str | None:
        text_input = _TextInput(title, prompt, password, default)
        return text_input.run()

    def get_selection(
        self, title: str, options: list[tuple[str, str, str]], subtitle: str = ""
    ) -> str | None:
        menu = _Menu(title, options, subtitle)
        return menu.run()

    def confirm(self, message: str, default: bool = False) -> bool:
        result = self.get_selection(
            message,
            [("yes", "Yes", ""), ("no", "No", "")],
        )
        return result == "yes"

    # --- Session management ---

    def get_sessions(self) -> list[SessionInfo]:
        if not self._session_persistence:
            return []
        limit = self._config.max_recent_sessions
        snapshots = self._session_persistence.list_sessions(limit=limit)
        return [
            SessionInfo(
                name=s.name,
                message_count=len(s.session.turns),
                created=s.created_at.strftime("%Y-%m-%d %H:%M"),
                model=s.session.metadata.primary_model or "",
                is_current=(s.name == self._current_session),
            )
            for s in snapshots
        ]

    def get_current_session(self) -> str | None:
        return self._current_session

    def set_current_session(self, name: str) -> None:
        self._persist_current_session()
        self._load_persisted_session(name)

    def create_session(self, name: str) -> None:
        self._persist_current_session()

        self._current_session = name
        self._messages = []
        self._session_dirty = False
        self._status.session = name
        self._status.message_count = 0

        # Reset session manager for fresh context tracking
        if self._session_manager:
            self._session_manager.clear_session()
            self._update_status_from_session()

    def add_message(self, role: str, content: str) -> None:
        """Add message to current session."""
        msg = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now().strftime("%H:%M"),
        )
        self._messages.append(msg)
        self._session_dirty = True
        self._status.message_count = len(self._messages)

        # Auto-persist after each assistant response
        if role == "assistant":
            self._persist_current_session()

    # --- Internal helpers ---

    def _update_status_from_session(self) -> None:
        """Update status info from session manager."""
        if not self._session_manager:
            return
        try:
            usage = self._session_manager.get_context_usage()
            self._status.total_tokens = usage.current_tokens
            self._status.total_cost = self._session_manager.session.metadata.total_cost
            self._status.message_count = len(self._session_manager.session.turns)
        except Exception as e:
            logger.debug(f"Status update from session failed: {e}")

    def _rebuild_messages_from_session(self) -> None:
        """Rebuild local message list from session manager turns."""
        if not self._session_manager:
            return
        self._messages = []
        for turn in self._session_manager.session.turns:
            self._messages.append(
                ChatMessage(
                    role=turn.role,
                    content=turn.content,
                    timestamp=turn.timestamp.strftime("%H:%M"),
                    tokens=turn.token_count,
                )
            )
        self._update_status_from_session()

    def _get_status_bar(self):
        """Get status bar formatted text."""
        return [
            ("class:status-bar", " "),
            ("class:status-provider", f"{self._status.provider or 'not configured'}"),
            ("class:status-bar", " / "),
            ("class:status-model", f"{self._status.model.split('/')[0] if '/' in self._status.model else self._status.model or '—'}"),
            ("class:status-bar", " │ "),
            ("class:status-session", f"{self._status.session or 'no session'}"),
            ("class:status-bar", f" ({self._status.message_count})"),
            ("class:status-bar", " │ "),
            ("class:status-tokens", f"{self._status.total_tokens:,} tok"),
            ("class:status-bar", " │ "),
            ("class:status-cost", f"${self._status.total_cost:.2f}"),
            ("class:status-bar", " "),
        ]

    def _persist_current_session(self) -> None:
        """Persist current session to snapshot storage if dirty."""
        if (
            not self._session_dirty
            or not self._current_session
            or not self._session_persistence
            or not self._session_manager
        ):
            return
        try:
            snapshot = Snapshot(
                name=self._current_session,
                session=self._session_manager.session,
                tags=["ui-session"],
            )
            self._session_persistence.save_session(self._current_session, snapshot)
            self._session_dirty = False
        except Exception as e:
            logger.debug(f"Session persist failed: {e}")

    def _load_persisted_session(self, name: str) -> bool:
        """Load a persisted session by name. Returns True on success."""
        if not self._session_persistence or not self._session_manager:
            return False
        snapshot = self._session_persistence.load_session(name)
        if not snapshot:
            return False
        self._session_manager._session = snapshot.session
        self._session_manager.tracker.track_session(snapshot.session)
        self._current_session = name
        self._session_dirty = False
        self._rebuild_messages_from_session()
        self._status.session = name
        return True

    def _try_resume_recent_session(self) -> bool:
        """Try to resume the most recent session from today. Returns True if resumed."""
        if not self._session_persistence:
            return False
        snapshot = self._session_persistence.get_most_recent_today()
        if snapshot:
            return self._load_persisted_session(snapshot.name)
        return False

    def _run_sessions_menu(self) -> str:
        """Run sessions selection menu."""
        items = [("new", "New session", "Create a new chat session")]

        for info in self.get_sessions():
            marker = " (active)" if info.is_current else ""
            turns = info.message_count
            desc = f"{turns} turns | {info.created}"
            items.append((f"load:{info.name}", f"{info.name}{marker}", desc))

        items.append(("menu", "Back", "Return to main menu"))

        choice = self.get_selection("Sessions", items, "Manage your chat sessions")

        if not choice or choice == "menu":
            return "menu"

        if choice == "new":
            name = self.get_text_input(
                "New Session",
                "Name: ",
                default=SessionPersistence.generate_session_name(),
            )
            if name:
                self.create_session(name)
                return "chat"
            return "sessions"

        if choice.startswith("load:"):
            self.set_current_session(choice[5:])
            return "chat"

        return "menu"

    def _build_messages(self, query: str):
        """Build messages list for the query.

        When SessionManager is active, uses full conversation history.
        Otherwise falls back to single-message mode.
        """
        from inkarms.providers.models import Message

        # Use conversation history from session manager (includes the just-added user message)
        if self._session_manager:
            messages: list[Message] = []
            for msg_dict in self._session_manager.get_messages(include_system=True):
                messages.append(Message(role=msg_dict["role"], content=msg_dict["content"]))
            return messages

        # Fallback: single query without conversation history
        messages = []
        messages.append(Message.user(query))
        return messages

    def _track_response(self, content: str, cost_before: float) -> None:
        """Track an assistant response in session manager with cost delta."""
        if not self._session_manager:
            return
        try:
            cost_delta = 0.0
            if self._provider_manager:
                cost_after = self._provider_manager.get_cost_summary().total_cost
                cost_delta = cost_after - cost_before
            self._session_manager.add_assistant_message(
                content,
                model=self._status.model,
                cost=cost_delta,
            )
            self._update_status_from_session()
        except Exception as e:
            logger.debug(f"Failed to track assistant message: {e}")

    def _process_query_streaming(self, query: str, on_chunk, on_complete, on_error):
        """Process query with streaming, calling callbacks for each chunk."""
        import contextlib
        import warnings

        # Expand @file references
        query = self._expand_file_references(query)

        if not self._provider_manager:
            on_complete("Provider not configured")
            return

        # Track user message in session manager (with expanded text for accurate tokens)
        if self._session_manager:
            try:
                self._session_manager.add_user_message(query)
            except Exception as e:
                logger.debug(f"Failed to track user message: {e}")

        messages = self._build_messages(query)

        # Capture cost before streaming for delta calculation
        cost_before = 0.0
        if self._provider_manager:
            with contextlib.suppress(Exception):
                cost_before = self._provider_manager.get_cost_summary().total_cost

        def run_streaming():
            warnings.filterwarnings("ignore", category=RuntimeWarning)

            loop = asyncio.new_event_loop()
            loop.set_exception_handler(lambda lp, ctx: None)
            asyncio.set_event_loop(loop)

            async def stream_response():
                full_content = ""
                try:
                    stream = await self._provider_manager.complete(
                        messages=messages,
                        model=self._status.model,
                        stream=True,
                    )
                    async for chunk in stream:
                        full_content += chunk.content
                        on_chunk(chunk.content)
                    return full_content
                except Exception as e:
                    traceback.print_exc()
                    raise e

            try:
                result = loop.run_until_complete(stream_response())
                self._track_response(result, cost_before)
                on_complete(result)
            except Exception as e:
                on_error(str(e))
            finally:
                with contextlib.suppress(Exception):
                    loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        thread = threading.Thread(target=run_streaming, daemon=True)
        thread.start()
        return thread

    def _process_query(self, query: str) -> str:
        """Process a user query and get response (non-streaming fallback)."""
        # Expand @file references
        query = self._expand_file_references(query)

        # Track user message in session manager
        if self._session_manager:
            try:
                self._session_manager.add_user_message(query)
            except Exception as e:
                logger.debug(f"Failed to track user message: {e}")

        # Try to use the provider manager
        if self._provider_manager:
            try:
                messages = self._build_messages(query)

                # Get completion (async call - run in separate thread to avoid event loop conflict)
                def run_async():
                    import contextlib
                    import warnings

                    warnings.filterwarnings("ignore", category=RuntimeWarning)

                    loop = asyncio.new_event_loop()
                    loop.set_exception_handler(lambda lp, ctx: None)
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(
                            self._provider_manager.complete(
                                messages=messages,
                                model=self._status.model,
                            )
                        )
                    finally:
                        with contextlib.suppress(Exception):
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_async)
                    response = future.result()

                # Track assistant message in session manager
                if self._session_manager:
                    try:
                        self._session_manager.add_assistant_message(
                            response.content,
                            model=response.model,
                            cost=response.cost or 0,
                        )
                        self._update_status_from_session()
                    except Exception as e:
                        logger.debug(f"Failed to track assistant message: {e}")
                else:
                    # Fallback: update stats directly
                    if response.usage:
                        self._status.total_tokens += response.usage.total_tokens
                    self._status.total_cost += response.cost or 0

                return response.content

            except Exception as e:
                logger.error(f"Provider error: {e}")
                return f"Error: {e}"

        # Fallback: simulated response
        return "I understand. Let me help you with that. (Note: Provider not configured)"

    def _expand_file_references(self, text: str) -> str:
        """Expand @path references to file contents."""
        pattern = r"@([^\s]+)"

        def replace(m):
            path = Path(m.group(1)).expanduser()
            if path.exists() and path.is_file():
                try:
                    content = path.read_text()[:2000]
                    return f"\n[File: {m.group(1)}]\n{content}\n[End file]\n"
                except Exception:
                    pass
            return m.group(0)

        return re.sub(pattern, replace, text)


# =============================================================================
# Internal View Components
# =============================================================================


class _Menu:
    """Simple menu component."""

    def __init__(self, title: str, items: list[tuple[str, str, str]], subtitle: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.items = items
        self.selected = 0
        self.result = None
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
                result.append(("class:menu-item", f"      {label}\n"))

        result.append(("", "\n"))
        result.append(("class:hint", "  ↑↓ navigate  Enter select  Esc cancel\n"))
        return result

    def run(self) -> str | None:
        kb = KeyBindings()

        @kb.add("up")
        def up(event):
            self.selected = (self.selected - 1) % len(self.items)

        @kb.add("down")
        def down(event):
            self.selected = (self.selected + 1) % len(self.items)

        @kb.add("k")
        def up_k(event):
            self.selected = (self.selected - 1) % len(self.items)

        @kb.add("j")
        def down_j(event):
            self.selected = (self.selected + 1) % len(self.items)

        @kb.add("enter")
        def select(event):
            self.result = self.items[self.selected][0]
            event.app.exit()

        @kb.add("escape")
        def cancel(event):
            self.cancelled = True
            event.app.exit()

        @kb.add("q")
        def quit(event):
            self.cancelled = True
            event.app.exit()

        @kb.add("c-c")
        def ctrl_c(event):
            self.cancelled = True
            event.app.exit()

        layout = Layout(Window(FormattedTextControl(self.get_formatted_text)))
        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()
        return None if self.cancelled else self.result


class _TextInput:
    """Text input component."""

    def __init__(self, title: str, prompt: str = "> ", password: bool = False, default: str = ""):
        self.title = title
        self.prompt_text = prompt
        self.password = password
        self.default = default
        self.cancelled = False

    def run(self) -> str | None:
        kb = KeyBindings()

        @kb.add("escape")
        def cancel(event):
            self.cancelled = True
            event.app.exit()

        @kb.add("c-c")
        def ctrl_c(event):
            self.cancelled = True
            event.app.exit()

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


class _MainMenu:
    """Main menu with branding."""

    def __init__(self, backend: "RichBackend"):
        self.backend = backend
        self.selected = 0
        self.items = [
            ("chat", "Chat", "Start or continue chatting"),
            ("dashboard", "Dashboard", "View usage and stats"),
            ("sessions", "Sessions", "Manage chat sessions"),
            ("config", "Config", "Configure provider and model"),
            ("quit", "Quit", ""),
        ]
        self.result = None

    def get_formatted_text(self):
        result = []

        for line in LOGO.strip().split("\n"):
            result.append(("class:brand", f"{line}\n"))

        result.append(("class:tagline", "    Your AI assistant that does things\n"))
        result.append(("", "\n"))
        result.extend(self.backend._get_status_bar())
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
        kb = KeyBindings()

        @kb.add("up")
        def up(event):
            self.selected = (self.selected - 1) % len(self.items)

        @kb.add("down")
        def down(event):
            self.selected = (self.selected + 1) % len(self.items)

        @kb.add("k")
        def up_k(event):
            self.selected = (self.selected - 1) % len(self.items)

        @kb.add("j")
        def down_j(event):
            self.selected = (self.selected + 1) % len(self.items)

        @kb.add("enter")
        def select(event):
            self.result = self.items[self.selected][0]
            event.app.exit()

        @kb.add("escape")
        @kb.add("q")
        def quit(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c-c")
        def ctrl_c(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c")
        def chat(event):
            self.result = "chat"
            event.app.exit()

        @kb.add("d")
        def dashboard(event):
            self.result = "dashboard"
            event.app.exit()

        @kb.add("s")
        def sessions(event):
            self.result = "sessions"
            event.app.exit()

        layout = Layout(Window(FormattedTextControl(self.get_formatted_text)))
        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()
        return self.result or "quit"


class _ChatView:
    """Chat view component - uses pattern from working demo."""

    def __init__(self, backend: "RichBackend"):
        self.backend = backend
        self.exit_to: UIView | None = UIView.MENU
        self.pending_message: str | None = None
        self.streaming = False
        self.streaming_content = ""
        self.app: Application | None = None
        self.scroll_offset = 0
        self.total_lines = 0

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

        status = [
            ("class:status-bar", " "),
            ("class:status-provider", f"{s.provider or '—'}"),
            ("class:status-bar", " | "),
            ("class:status-model", f"{s.model or '—'}"),
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
                "/save [name] /load <name> /history /model /quit | Use @file to include file"
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

    def run(self) -> UIView | None:
        from prompt_toolkit.widgets import Frame, TextArea

        # Input area with command completion
        def _on_accept_handler(buff: Buffer) -> bool:
            self._on_accept(buff)
            return True

        input_area = TextArea(
            height=1,
            multiline=False,
            wrap_lines=False,
            completer=COMMAND_COMPLETER,
            complete_while_typing=True,
            accept_handler=_on_accept_handler,
            style="class:user-input",
        )

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-q")
        def exit_(event):
            self.exit_to = UIView.MENU
            event.app.exit()

        @kb.add("escape")
        def escape_(event):
            self.exit_to = UIView.MENU
            event.app.exit()

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

        @kb.add("pageup")
        def page_up(event):
            scroll_chat_up(10)

        @kb.add("pagedown")
        def page_down(event):
            scroll_chat_down(10)

        @kb.add("c-u")
        def scroll_up_half(event):
            scroll_chat_up(20)

        @kb.add("c-d")
        def scroll_down_half(event):
            scroll_chat_down(20)

        @kb.add("home")
        def scroll_top(event):
            if self.chat_buffer:
                self.chat_buffer.cursor_position = 0

        @kb.add("end")
        def scroll_bottom(event):
            if self.chat_buffer:
                self.chat_buffer.cursor_position = len(self.chat_buffer.text)

        # Mouse scroll support - move cursor to scroll the view
        @kb.add("<scroll-up>")
        def mouse_scroll_up(event):
            scroll_chat_up(3)

        @kb.add("<scroll-down>")
        def mouse_scroll_down(event):
            scroll_chat_down(3)

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
                            _render_styled_text(f"{ts}You: {msg.content}", THEME_STYLES["user"])
                        )
                        lines.append("")
                    else:
                        # For assistant, we use a Panel and omit the separate header
                        try:
                            rendered = _render_markdown_ansi(
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
                # Streaming content
                if self.streaming_content:
                    try:
                        # Render partially completed content in a panel
                        rendered = _render_markdown_ansi(
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
                else:
                    lines.append(_render_styled_text("Assistant:", THEME_STYLES["assistant"]))
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
                Frame(input_area, title="You (Enter to send, Tab for completions)"),
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
        layout.focus(input_area)

        self.app = Application(
            layout=layout,
            key_bindings=kb,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )
        self.app.run()
        return self.exit_to

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

        # Start streaming response
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

            # Show context warnings if approaching limits
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
                            f"Context at {usage.usage_percent * 100:.0f}% - compaction recommended"
                        )
                except Exception:
                    pass

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


class _DashboardView:
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

        kb = KeyBindings()

        @kb.add("c-c")
        def exit_(event):
            self.exit_to = UIView.MENU
            event.app.exit()

        @kb.add("tab")
        def tab(event):
            buff = event.app.current_buffer
            if buff.complete_state:
                buff.complete_next()
            else:
                buff.start_completion(select_first=False)

        @kb.add("backspace")
        def backspace(event):
            buff = event.app.current_buffer
            buff.delete_before_cursor(1)
            if buff.text.startswith("/"):
                buff.start_completion(select_first=False)

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
