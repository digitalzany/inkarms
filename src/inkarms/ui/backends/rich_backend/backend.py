"""
Rich + prompt_toolkit UI Backend.

This is the default, lightweight UI backend using Rich for formatting
and prompt_toolkit for full-screen applications and input handling.
"""

from __future__ import annotations

import traceback
import asyncio
import concurrent.futures
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

from prompt_toolkit import Application
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.layout import (
    FormattedTextControl,
    Layout,
    Window,
)
from prompt_toolkit.lexers import Lexer

from inkarms.config.theme import LOGO, STYLE
from inkarms.config.wizard import RichWizard
from inkarms.memory import get_session_manager
from inkarms.models.memory import Snapshot
from inkarms.ui.backends.rich_backend.components.chat import ChatView
from inkarms.ui.backends.rich_backend.components.dashboard import DashboardView
from inkarms.ui.backends.rich_backend.components.input import TextInput
from inkarms.ui.protocol import ChatMessage, SessionInfo, StatusInfo, UIBackend, UIConfig, UIView
from inkarms.memory.session_persistence import SessionPersistence
from inkarms.ui.backends.rich_backend.key_binding import bind_keys

logger = logging.getLogger(__name__)


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
        ("/tools", "Show registered tools"),
        ("/agent", "Show/change agent settings"),
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
        self._tool_registry = None
        self._sandbox = None
        self._agent_config = None

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

            # Initialize tools and agent config
            if self._configured:
                self._init_agent_tools()

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

    def _init_agent_tools(self) -> None:
        """Initialize agent config, sandbox, and tool registry."""
        try:
            from inkarms.models.agent import AgentConfig as AgentRuntimeConfig
            from inkarms.models.agent import ApprovalMode
            from inkarms.security.sandbox import SandboxExecutor
            from inkarms.tools.builtin.registry_utils import register_builtin_tools
            from inkarms.tools.registry import get_tool_registry

            agent_schema = self._app_config.agent
            self._agent_config = AgentRuntimeConfig(
                approval_mode=ApprovalMode(agent_schema.approval_mode),
                max_iterations=agent_schema.max_iterations,
                enable_tools=agent_schema.enable_tools,
                allowed_tools=agent_schema.allowed_tools,
                blocked_tools=agent_schema.blocked_tools,
                timeout_per_iteration=agent_schema.timeout_per_iteration,
            )

            if self._app_config.is_sandbox_enabled():
                self._sandbox = SandboxExecutor.from_config(self._app_config.security)

            self._tool_registry = get_tool_registry()
            if len(self._tool_registry) == 0:
                register_builtin_tools(self._tool_registry, self._sandbox)

        except Exception as e:
            logger.debug(f"Agent/tools init failed: {e}")

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
        chat = ChatView(self)
        return chat.run()

    def run_dashboard(self) -> UIView | None:
        """Run dashboard."""
        dashboard = DashboardView(self)
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
        text_input = TextInput(title, prompt, password, default)
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
        items = [
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
        ]
        if self._agent_config and self._agent_config.enable_tools:
            tool_count = len(self._tool_registry) if self._tool_registry else 0
            mode = self._agent_config.approval_mode.value
            items.extend([
                ("class:status-bar", " │ "),
                ("class:tool-running", f"Tools: {tool_count} ({mode})"),
            ])
        items.append(("class:status-bar", " "))
        return items

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
        from inkarms.models.providers import Message

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

    def _process_query_agent(
        self, query, event_callback, approval_callback, on_complete, on_error
    ):
        """Process query through agent loop with tool use."""
        import contextlib
        import warnings

        query = self._expand_file_references(query)

        if not self._provider_manager or not self._tool_registry or not self._agent_config:
            on_error("Agent not configured")
            return

        if self._session_manager:
            try:
                self._session_manager.add_user_message(query)
            except Exception as e:
                logger.debug(f"Failed to track user message: {e}")

        messages = self._build_messages(query)
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]

        cost_before = 0.0
        if self._provider_manager:
            with contextlib.suppress(Exception):
                cost_before = self._provider_manager.get_cost_summary().total_cost

        def run_agent():
            warnings.filterwarnings("ignore", category=RuntimeWarning)

            loop = asyncio.new_event_loop()
            loop.set_exception_handler(lambda lp, ctx: None)
            asyncio.set_event_loop(loop)

            try:
                from inkarms.agent.loop import AgentLoop

                agent_loop = AgentLoop(
                    provider_manager=self._provider_manager,
                    tool_registry=self._tool_registry,
                    config=self._agent_config,
                    approval_callback=approval_callback,
                    event_callback=event_callback,
                )
                result = loop.run_until_complete(
                    agent_loop.run(msg_dicts, model=self._status.model)
                )
                self._track_response(result.final_response, cost_before)
                on_complete(result)
            except Exception as e:
                on_error(str(e))
            finally:
                # Cancel pending tasks (LiteLLM logging workers) before closing
                with contextlib.suppress(Exception):
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                with contextlib.suppress(Exception):
                    loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        thread = threading.Thread(target=run_agent, daemon=True)
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

    @staticmethod
    def _expand_file_references(text: str) -> str:
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


class _Menu:
    """Simple menu component. Used for popups, categories (e.g., Sessions view)."""

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
        kb = bind_keys(self)
        layout = Layout(Window(FormattedTextControl(self.get_formatted_text)))
        app = Application(
            layout=layout, key_bindings=kb, style=STYLE, full_screen=True, erase_when_done=True
        )
        app.run()

        return None if self.cancelled else self.result


class _MainMenu:
    """Main menu with branding. Used at the startup."""

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
