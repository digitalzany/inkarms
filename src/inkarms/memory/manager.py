"""
Session manager for InkArms.

Provides the main interface for managing sessions, context, and memory.
"""

import logging
from pathlib import Path
from typing import Any

from inkarms.config import get_config
from inkarms.memory.compaction import CompactionOrchestrator, CompactionStrategy
from inkarms.memory.context import ContextTracker
from inkarms.memory.handoff import HandoffManager
from inkarms.memory.persister import SessionPersister
from inkarms.memory.storage import MemoryStorage
from inkarms.models.memory import (
    ContextUsage,
    ConversationTurn,
    HandoffDocument,
    MemoryEntry,
    MemoryType,
    Session,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Main interface for managing sessions and memory.

    Acts as a thin facade that delegates to focused components:
    - ContextTracker: token counting and context window monitoring
    - SessionPersister: all disk I/O (daily logs, snapshots, memory listing)
    - CompactionOrchestrator: compaction decisions and execution
    - HandoffManager: handoff creation and recovery
    """

    def __init__(
        self,
        model: str | None = None,
        storage_path: Path | str | None = None,
    ):
        """Initialize the session manager.

        Args:
            model: Model name for context tracking.
            storage_path: Path for memory storage.
        """
        # Load config
        config = get_config()

        # Determine model — validate it's not empty
        self.model = model or config.providers.default
        if not self.model:
            logger.warning("SessionManager initialized without a model name")

        # Initialize storage (exposed via property for external consumers)
        self._storage = MemoryStorage(storage_path)

        # Initialize components
        self.tracker = ContextTracker(
            model=self.model or "default",
            compact_threshold=config.context.auto_compact_threshold,
            handoff_threshold=config.context.handoff_threshold,
        )
        self.persister = SessionPersister(
            storage=self._storage,
            auto_save=config.context.daily_logs,
        )
        self.compaction = CompactionOrchestrator(
            tracker=self.tracker,
            strategy=config.context.compaction.strategy,
            preserve_recent=config.context.compaction.preserve_recent_turns,
            summary_model=config.context.compaction.summary_model or config.providers.default,
            summary_max_tokens=config.context.compaction.summary_max_tokens,
        )
        self.handoff_manager = HandoffManager(
            storage=self._storage,
            include_full_context=config.context.handoff.include_full_context,
        )

        # Current session
        self._session: Session | None = None

    @property
    def storage(self) -> MemoryStorage:
        """Access the underlying storage backend."""
        return self._storage

    @property
    def session(self) -> Session:
        """Get the current session, creating one if needed."""
        if self._session is None:
            self._session = self._load_or_create_session()
        return self._session

    def _load_or_create_session(self) -> Session:
        """Load today's session or create a new one.

        Returns:
            Session instance.
        """
        session = self.persister.load_daily_session()

        if session is not None:
            self.tracker.track_session(session)
            return session

        return Session()

    def set_model(self, model: str) -> None:
        """Update the model for context tracking.

        Args:
            model: New model name.
        """
        self.model = model
        self.tracker.set_model(model)
        self.session.metadata.primary_model = model

    def set_system_prompt(self, prompt: str | None) -> int:
        """Set the system prompt.

        Args:
            prompt: System prompt text.

        Returns:
            Token count of the prompt.
        """
        self.session.system_prompt = prompt
        return self.tracker.set_system_prompt(prompt)

    def add_user_message(self, content: str) -> ConversationTurn:
        """Add a user message to the session.

        Args:
            content: Message content.

        Returns:
            Created turn.
        """
        token_count = self.tracker.count_text(content)
        turn = self.session.add_user_message(content, token_count)
        self.tracker.add_turn(turn)
        self.persister.auto_save(self._session)  # type: ignore[arg-type]
        return turn

    def add_assistant_message(
        self,
        content: str,
        model: str | None = None,
        cost: float | None = None,
        reasoning_content: str | None = None,
    ) -> ConversationTurn:
        """Add an assistant message to the session.

        Args:
            content: Message content.
            model: Model that generated the response.
            cost: Cost of the response.
            reasoning_content: Reasoning content from reasoning-capable models.

        Returns:
            Created turn.
        """
        resolved_model = model or self.model
        if not resolved_model:
            logger.debug("add_assistant_message falling back to empty model name")

        token_count = self.tracker.count_text(content)
        turn = self.session.add_assistant_message(
            content,
            token_count=token_count,
            model=resolved_model,
            cost=cost,
            reasoning_content=reasoning_content,
        )
        self.tracker.add_turn(turn)
        self.persister.auto_save(self._session)  # type: ignore[arg-type]
        return turn

    def save_session(self) -> None:
        """Explicitly save the current session to daily log."""
        if self._session is not None:
            self.persister.save_daily(self._session)

    def restore_session(self, session: Session) -> None:
        """Restore a session from an external source (e.g., a loaded snapshot).

        Replaces the current session and re-tracks it.

        Args:
            session: The session to restore.
        """
        self._session = session
        self.tracker.track_session(session)

    def get_messages(self, include_system: bool = True) -> list[dict[str, Any]]:
        """Get messages for LLM completion.

        Args:
            include_system: Whether to include system prompt.

        Returns:
            List of message dicts.
        """
        return self.session.get_messages(include_system)

    def get_context_usage(self) -> ContextUsage:
        """Get current context usage.

        Returns:
            Context usage info.
        """
        self.tracker.track_session(self.session)
        return self.tracker.get_usage()

    def should_compact(self) -> bool:
        """Check if compaction should be triggered."""
        return self.compaction.should_compact(self.session)

    def should_handoff(self) -> bool:
        """Check if handoff should be triggered."""
        return self.compaction.should_handoff(self.session)

    async def compact(
        self,
        strategy: CompactionStrategy | str | None = None,
        target_tokens: int | None = None,
    ) -> Session:
        """Compact the session to reduce context size.

        Args:
            strategy: Compaction strategy to use.
            target_tokens: Target token count.

        Returns:
            Compacted session.
        """
        self._session = await self.compaction.compact(
            self.session, strategy=strategy, target_tokens=target_tokens,
        )
        self.tracker.track_session(self._session)
        self.persister.auto_save(self._session)
        return self._session

    async def create_handoff(self) -> HandoffDocument:
        """Create a handoff document.

        Returns:
            Created handoff document.
        """
        return await self.handoff_manager.create_handoff(
            self.session,
            summary_model=self.compaction.summary_model,
        )

    def check_for_handoff(self) -> HandoffDocument | None:
        """Check for pending handoff to recover.

        Returns:
            Handoff if found, None otherwise.
        """
        return self.handoff_manager.check_for_handoff()

    async def recover_handoff(self, archive: bool = True) -> Session:
        """Recover from a pending handoff.

        Args:
            archive: Whether to archive the handoff after recovery.

        Returns:
            Recovered session.
        """
        self._session = await self.handoff_manager.recover_from_handoff(
            archive=archive,
        )
        self.tracker.track_session(self._session)
        return self._session

    def save_snapshot(self, name: str, description: str = "", topic: str | None = None) -> Path:
        """Save a snapshot of the current session.

        Args:
            name: Snapshot name.
            description: Description.
            topic: Topic tag.

        Returns:
            Path to saved snapshot.
        """
        return self.persister.save_snapshot(self.session, name, description, topic)

    def load_snapshot(self, name: str) -> Session | None:
        """Load a session from a snapshot.

        Args:
            name: Snapshot name.

        Returns:
            Session from snapshot, or None if not found.
        """
        session = self.persister.load_snapshot(name)
        if session:
            self._session = session
            self.tracker.track_session(self._session)
            return self._session
        return None

    def list_memory(self, memory_type: MemoryType | str | None = None) -> list[MemoryEntry]:
        """List memory entries.

        Args:
            memory_type: Filter by type.

        Returns:
            List of memory entries.
        """
        return self.persister.list_memory(memory_type)

    def clear_session(self) -> None:
        """Clear the current session."""
        self._session = Session()
        self.tracker.track_session(self._session)

    def get_session_info(self) -> dict[str, Any]:
        """Get information about the current session.

        Returns:
            Session info dict.
        """
        usage = self.get_context_usage()

        return {
            "session_id": self.session.id,
            "created_at": self.session.metadata.created_at.isoformat(),
            "turn_count": len(self.session.turns),
            "total_tokens": usage.current_tokens,
            "max_tokens": usage.max_tokens,
            "usage_percent": f"{usage.usage_percent * 100:.1f}%",
            "should_compact": usage.should_compact,
            "should_handoff": usage.should_handoff,
            "total_cost": self.session.metadata.total_cost,
            "model": self.model,
            "models_used": self.session.metadata.models_used,
        }


# Singleton instance
_manager: SessionManager | None = None


def get_session_manager(
    model: str | None = None,
    storage_path: Path | str | None = None,
) -> SessionManager:
    """Get the session manager singleton.

    Args:
        model: Model name for context tracking.
        storage_path: Path for memory storage.

    Returns:
        SessionManager instance.
    """
    global _manager
    if _manager is None:
        _manager = SessionManager(model=model, storage_path=storage_path)
    elif model and _manager.model != model:
        _manager.set_model(model)
    return _manager


def reset_session_manager() -> None:
    """Reset the session manager singleton."""
    global _manager
    _manager = None
