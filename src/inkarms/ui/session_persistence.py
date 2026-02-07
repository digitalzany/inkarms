"""
Session persistence for UI sessions.

Provides a thin wrapper around MemoryStorage snapshots to persist
UI chat sessions across app restarts. Sessions are stored as snapshots
tagged with "ui-session" to distinguish them from user-created /save bookmarks.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inkarms.memory.models import Snapshot
    from inkarms.memory.storage import MemoryStorage

logger = logging.getLogger(__name__)

UI_SESSION_TAG = "ui-session"


class SessionPersistence:
    """Manages persistent UI sessions via tagged snapshots."""

    def __init__(self, storage: MemoryStorage):
        self._storage = storage

    @staticmethod
    def generate_session_name() -> str:
        """Generate an auto-session name like 'chat-20260206-1430'."""
        return f"chat-{datetime.now().strftime('%Y%m%d-%H%M')}"

    def list_sessions(self, limit: int = 10) -> list[Snapshot]:
        """List UI sessions sorted by recency, excluding empty ones."""
        snapshots: list[Snapshot] = []

        for entry in self._storage.list_snapshots():
            snapshot = self._storage.load_snapshot(entry.name)
            if snapshot is None:
                continue
            if UI_SESSION_TAG not in snapshot.tags:
                continue
            if not snapshot.session.turns:
                continue
            snapshots.append(snapshot)
            if len(snapshots) >= limit:
                break

        return snapshots

    def save_session(self, name: str, snapshot: Snapshot) -> None:
        """Save a UI session snapshot with the ui-session tag."""
        if UI_SESSION_TAG not in snapshot.tags:
            snapshot.tags.append(UI_SESSION_TAG)
        snapshot.name = name
        self._storage.save_snapshot(snapshot)

    def load_session(self, name: str) -> Snapshot | None:
        """Load a UI session snapshot by name."""
        return self._storage.load_snapshot(name)

    def get_most_recent_today(self) -> Snapshot | None:
        """Get the most recent UI session from today, if any."""
        today = datetime.now().strftime("%Y%m%d")
        for snapshot in self.list_sessions(limit=5):
            if today in snapshot.name:
                return snapshot

        return None
