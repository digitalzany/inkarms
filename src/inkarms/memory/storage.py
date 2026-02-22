"""
Memory storage for InkArms.

Provides file-based persistence for sessions, snapshots, and handoffs.
Acts as a facade over specific repositories.
"""

from datetime import datetime, timedelta
from pathlib import Path

from inkarms.memory.repositories.handoff import HandoffRepository
from inkarms.memory.repositories.session import SessionRepository
from inkarms.memory.repositories.snapshot import SnapshotRepository
from inkarms.models.memory import (
    HandoffDocument,
    MemoryEntry,
    MemoryType,
    Session,
    Snapshot,
)
from inkarms.storage.paths import get_memory_dir


class MemoryStorage:
    """File-based storage for memory.

    Stores sessions, snapshots, and handoffs as JSON files.
    """

    def __init__(self, base_path: Path | str | None = None):
        """Initialize the memory storage.

        Args:
            base_path: Base path for memory files. Defaults to ~/.inkarms/memory.
        """
        if base_path is None:
            self.base_path = get_memory_dir()
        else:
            self.base_path = Path(base_path).expanduser().resolve()

        # Initialize repositories
        self.session_repo = SessionRepository(self.base_path)
        self.snapshot_repo = SnapshotRepository(self.base_path)
        self.handoff_repo = HandoffRepository(self.base_path)

        # Backward compatibility attributes (deprecated)
        self.daily_path = self.session_repo.base_path
        self.snapshots_path = self.snapshot_repo.base_path
        self.handoffs_path = self.handoff_repo.base_path
        self.archive_path = self.handoff_repo.archive_path

    # =========================================================================
    # Daily Sessions
    # =========================================================================

    def get_daily_path(self, date: datetime | None = None) -> Path:
        """Get the path for a daily session file."""
        return self.session_repo.get_path(date)

    def save_daily_session(self, session: Session, date: datetime | None = None) -> Path:
        """Save a session as a daily log."""
        return self.session_repo.save(session, date)

    def load_daily_session(self, date: datetime | None = None) -> Session | None:
        """Load a daily session."""
        return self.session_repo.load(date)

    def list_daily_sessions(self) -> list[MemoryEntry]:
        """List all daily session files."""
        return self.session_repo.list_entries()

    # =========================================================================
    # Snapshots
    # =========================================================================

    def save_snapshot(self, snapshot: Snapshot) -> Path:
        """Save a snapshot."""
        return self.snapshot_repo.save(snapshot)

    def load_snapshot(self, name: str) -> Snapshot | None:
        """Load a snapshot by name."""
        return self.snapshot_repo.load(name)

    def delete_snapshot(self, name: str) -> bool:
        """Delete a snapshot."""
        path = self.snapshot_repo.base_path / f"{name}.json"
        return self.snapshot_repo.delete(path)

    def list_snapshots(self) -> list[MemoryEntry]:
        """List all snapshots."""
        return self.snapshot_repo.list_entries()

    # =========================================================================
    # Handoffs
    # =========================================================================

    def save_handoff(self, handoff: HandoffDocument) -> Path:
        """Save a handoff document."""
        return self.handoff_repo.save(handoff)

    def load_latest_handoff(self) -> HandoffDocument | None:
        """Load the most recent handoff."""
        return self.handoff_repo.load_latest()

    def archive_handoff(self, handoff: HandoffDocument) -> Path:
        """Move a handoff to the archive."""
        return self.handoff_repo.archive(handoff)

    def load_handoff_by_path(self, path: Path) -> HandoffDocument | None:
        """Load a handoff document from a specific file path."""
        return self.handoff_repo.load_by_path(path)

    def list_handoffs(self, include_archived: bool = False) -> list[MemoryEntry]:
        """List all handoffs."""
        return self.handoff_repo.list_entries(include_archived)

    # =========================================================================
    # General Operations
    # =========================================================================

    def list_all(self, memory_type: MemoryType | None = None) -> list[MemoryEntry]:
        """List all memory entries."""
        entries = []

        if memory_type is None or memory_type == MemoryType.DAILY:
            entries.extend(self.session_repo.list_entries())

        if memory_type is None or memory_type == MemoryType.SNAPSHOT:
            entries.extend(self.snapshot_repo.list_entries())

        if memory_type is None or memory_type == MemoryType.HANDOFF:
            entries.extend(self.handoff_repo.list_entries())

        # Sort by created_at
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def delete_older_than(self, days: int, memory_type: MemoryType | None = None) -> int:
        """Delete memory files older than a certain number of days."""
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = cutoff - timedelta(days=days)
        deleted = 0

        for entry in self.list_all(memory_type):
            if entry.created_at < cutoff:
                path = Path(entry.path)
                if path.exists():
                    path.unlink()
                    deleted += 1

        return deleted
