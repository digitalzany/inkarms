"""
Session persistence for InkArms.

Handles all disk I/O for sessions: auto-save, daily logs, snapshots, and memory listing.
Extracted from SessionManager to satisfy Single Responsibility Principle.
"""

import logging
from pathlib import Path

from inkarms.memory.storage import MemoryStorage
from inkarms.models.memory import (
    MemoryEntry,
    MemoryType,
    Session,
    Snapshot,
)

logger = logging.getLogger(__name__)


class SessionPersister:
    """Handles session persistence operations.

    Provides:
    - Auto-save to daily logs
    - Snapshot save/load
    - Memory listing
    """

    def __init__(self, storage: MemoryStorage, auto_save: bool = True):
        """Initialize the persister.

        Args:
            storage: Memory storage backend.
            auto_save: Whether to enable auto-save to daily logs.
        """
        self._storage = storage
        self._auto_save = auto_save

    @property
    def auto_save_enabled(self) -> bool:
        """Whether auto-save is enabled."""
        return self._auto_save

    def auto_save(self, session: Session) -> None:
        """Save session to daily log if auto-save is enabled.

        Logs errors instead of swallowing them silently.
        """
        if not self._auto_save:
            return
        try:
            self._storage.save_daily_session(session)
        except Exception:
            logger.warning("Failed to auto-save session to daily log", exc_info=True)

    def save_daily(self, session: Session) -> None:
        """Explicitly save to daily log."""
        self._storage.save_daily_session(session)

    def save_snapshot(
        self,
        session: Session,
        name: str,
        description: str = "",
        topic: str | None = None,
    ) -> Path:
        """Save a snapshot of a session.

        Args:
            session: Session to snapshot.
            name: Snapshot name.
            description: Description.
            topic: Topic tag.

        Returns:
            Path to saved snapshot.
        """
        snapshot = Snapshot(
            name=name,
            description=description,
            topic=topic,
            session=session,
        )
        return self._storage.save_snapshot(snapshot)

    def load_snapshot(self, name: str) -> Session | None:
        """Load a session from a snapshot.

        Args:
            name: Snapshot name.

        Returns:
            Session from snapshot, or None if not found.
        """
        snapshot = self._storage.load_snapshot(name)
        if snapshot:
            return snapshot.session
        return None

    def list_memory(self, memory_type: MemoryType | str | None = None) -> list[MemoryEntry]:
        """List memory entries.

        Args:
            memory_type: Filter by type.

        Returns:
            List of memory entries.
        """
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)
        return self._storage.list_all(memory_type)

    def load_daily_session(self) -> Session | None:
        """Load today's session from daily log.

        Returns:
            Session if found, None otherwise.
        """
        return self._storage.load_daily_session()
