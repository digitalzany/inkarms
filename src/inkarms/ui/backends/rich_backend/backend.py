from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from inkarms.config.wizard import RichWizard
from inkarms.memory import SessionManager, get_session_manager
from inkarms.memory.session_persistence import UISessionPersistence
from inkarms.models.memory import Snapshot
from inkarms.ui.backends.rich_backend.components.chat import ChatView
from inkarms.ui.backends.rich_backend.components.dashboard import DashboardView
from inkarms.ui.backends.rich_backend.components.input import TextInput
from inkarms.ui.backends.rich_backend.components.menu import MainMenu, Menu
from inkarms.ui.protocol import ChatMessage, SessionInfo, StatusInfo, UIBackend, UIConfig, UIView

if TYPE_CHECKING:
    from inkarms.agent import AgentConfig
    from inkarms.config import Config
    from inkarms.providers import ProviderManager
    from inkarms.security.sandbox import SandboxExecutor
    from inkarms.skills import SkillManager
    from inkarms.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


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
        self._session_persistence: UISessionPersistence | None = None

        # Will be set during initialization
        self._provider_manager: ProviderManager | None = None
        self._session_manager: SessionManager | None = None
        self._skill_manager: SkillManager | None = None
        self._app_config: Config | None = None
        self._tool_registry: ToolRegistry | None = None
        self._sandbox: SandboxExecutor | None = None
        self._agent_config: AgentConfig | None = None

    # --- Properties ---

    @property
    def config(self) -> UIConfig:
        return self._config

    @property
    def is_configured(self) -> bool:
        return self._configured

    @is_configured.setter
    def is_configured(self, value: bool) -> None:
        self._configured = value

    @property
    def status(self) -> StatusInfo:
        """Current status info for views to read/update."""
        return self._status

    @property
    def messages(self) -> list[ChatMessage]:
        """Current message list."""
        return self._messages

    @messages.setter
    def messages(self, value: list[ChatMessage]) -> None:
        self._messages = value

    @property
    def session_manager(self) -> SessionManager | None:
        """Session manager instance (None if not configured)."""
        return self._session_manager

    @property
    def agent_config(self) -> AgentConfig | None:
        """Agent configuration (None if not configured)."""
        return self._agent_config

    @property
    def tool_registry(self) -> ToolRegistry | None:
        """Tool registry (None if not configured)."""
        return self._tool_registry

    @property
    def provider_manager(self):
        """Provider manager (None if not configured)."""
        return self._provider_manager

    def mark_session_dirty(self) -> None:
        """Mark the current session as needing persistence."""
        self._session_dirty = True

    def clear_chat(self) -> None:
        """Clear messages, session state, and reset counters."""
        self._messages = []
        if self._session_manager:
            self._session_manager.clear_session()
        self._session_dirty = True
        self._status.message_count = 0
        self._status.total_tokens = 0
        self._status.total_cost = 0.0

    # --- Lifecycle ---

    def initialize(self) -> None:
        """Initialize backend with InkArms core components."""
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
                    self._session_persistence = UISessionPersistence(self._session_manager.storage)
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
                from inkarms.audit import get_audit_logger

                self._sandbox = SandboxExecutor.from_config(
                    self._app_config.security, get_audit_logger()
                )

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
                self._session_manager.save_session()
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
            self._reload_config()

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
                            self.create_session(UISessionPersistence.generate_session_name())
                    current_view = self.run_chat()
                elif current_view == UIView.DASHBOARD:
                    current_view = self.run_dashboard()
                elif current_view == UIView.SESSIONS:
                    current_view = self.run_sessions()
                elif current_view == UIView.CONFIG:
                    self.run_config_wizard()
                    self._reload_config()
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
        menu = MainMenu(self.get_status_bar)
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
        logger.error(message)
        self._messages.append(
            ChatMessage(
                role="system",
                content=f"Error: {message}",
                timestamp=datetime.now().strftime("%H:%M"),
            )
        )

    def display_info(self, message: str) -> None:
        logger.info(message)
        self._messages.append(
            ChatMessage(
                role="system",
                content=message,
                timestamp=datetime.now().strftime("%H:%M"),
            )
        )

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
        menu = Menu(title, options, subtitle)
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

    def rebuild_messages_from_session(self) -> None:
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

    def get_status_bar(self):
        """Get status bar formatted text."""
        from inkarms.ui.backends.rich_backend.helpers import build_status_bar

        return build_status_bar(
            self._status,
            agent_config=self._agent_config,
            tool_registry=self._tool_registry,
            separator=" │ ",
            model_format="full",
        )

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
        self._session_manager.restore_session(snapshot.session)
        self._current_session = name
        self._session_dirty = False
        self.rebuild_messages_from_session()
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
                default=UISessionPersistence.generate_session_name(),
            )
            if name:
                self.create_session(name)
                return "chat"
            return "sessions"

        if choice.startswith("load:"):
            self.set_current_session(choice[5:])
            return "chat"

        return "menu"

    def _reload_config(self) -> None:
        """Reload config from disk and update runtime model/provider state."""
        try:
            from inkarms.config import get_config

            self._app_config = get_config(reload=True)
            new_model = self._app_config.providers.default
            self._status.model = new_model
            self._status.provider = new_model.split("/")[0] if "/" in new_model else "unknown"
        except Exception as e:
            logger.debug(f"Config reload failed: {e}")

    def _get_query_processor(self):
        """Get the query processor, creating it if needed."""
        from inkarms.ui.backends.rich_backend.query import QueryProcessor

        return QueryProcessor(
            provider_manager=self._provider_manager,
            session_manager=self._session_manager,
            status=self._status,
            agent_config=self._agent_config,
            tool_registry=self._tool_registry,
            on_status_update=self._update_status_from_session,
        )

    def process_query_streaming(self, query, on_chunk, on_complete, on_error):
        """Process query with streaming, calling callbacks for each chunk."""
        return self._get_query_processor().process_streaming(
            query, on_chunk, on_complete, on_error
        )

    def process_query_agent(
        self, query, event_callback, approval_callback, on_complete, on_error,
        *, on_chunk=None,
    ):
        """Process query through agent loop with tool use."""
        return self._get_query_processor().process_agent(
            query, event_callback, approval_callback, on_complete, on_error,
            on_chunk=on_chunk,
        )


