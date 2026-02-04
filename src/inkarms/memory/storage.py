"""
Memory storage for InkArms.

Provides file-based persistence for sessions, snapshots, and handoffs.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from inkarms.memory.models import (
    ConversationTurn,
    HandoffDocument,
    MemoryEntry,
    MemoryType,
    Session,
    SessionMetadata,
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

        # Create subdirectories
        self.daily_path = self.base_path / "daily"
        self.snapshots_path = self.base_path / "snapshots"
        self.handoffs_path = self.base_path / "handoffs"
        self.archive_path = self.base_path / "archive"

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create required directories."""
        for path in [
            self.base_path,
            self.daily_path,
            self.snapshots_path,
            self.handoffs_path,
            self.archive_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _serialize_session(self, session: Session) -> dict[str, Any]:
        """Serialize a session to dict.

        Args:
            session: Session to serialize.

        Returns:
            Dict representation.
        """
        return {
            "metadata": session.metadata.model_dump(mode="json"),
            "system_prompt": session.system_prompt,
            "turns": [
                {
                    **t.model_dump(mode="json"),
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                }
                for t in session.turns
            ],
        }

    def _deserialize_session(self, data: dict[str, Any]) -> Session:
        """Deserialize a session from dict.

        Args:
            data: Dict representation.

        Returns:
            Session object.
        """
        # Parse metadata
        meta_data = data.get("metadata", {})
        if "created_at" in meta_data and isinstance(meta_data["created_at"], str):
            meta_data["created_at"] = datetime.fromisoformat(meta_data["created_at"])
        if "updated_at" in meta_data and isinstance(meta_data["updated_at"], str):
            meta_data["updated_at"] = datetime.fromisoformat(meta_data["updated_at"])

        metadata = SessionMetadata(**meta_data)

        # Parse turns
        turns = []
        for turn_data in data.get("turns", []):
            if "timestamp" in turn_data and isinstance(turn_data["timestamp"], str):
                turn_data["timestamp"] = datetime.fromisoformat(turn_data["timestamp"])
            turns.append(ConversationTurn(**turn_data))

        return Session(
            metadata=metadata,
            system_prompt=data.get("system_prompt"),
            turns=turns,
        )

    # =========================================================================
    # Daily Sessions
    # =========================================================================

    def get_daily_path(self, date: datetime | None = None) -> Path:
        """Get the path for a daily session file.

        Args:
            date: Date for the file. Defaults to today.

        Returns:
            Path to the daily file.
        """
        if date is None:
            date = datetime.now()
        filename = date.strftime("%Y-%m-%d.json")
        return self.daily_path / filename

    def save_daily_session(self, session: Session, date: datetime | None = None) -> Path:
        """Save a session as a daily log.

        Args:
            session: Session to save.
            date: Date for the file. Defaults to today.

        Returns:
            Path to the saved file.
        """
        path = self.get_daily_path(date)
        data = self._serialize_session(session)

        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def load_daily_session(self, date: datetime | None = None) -> Session | None:
        """Load a daily session.

        Args:
            date: Date to load. Defaults to today.

        Returns:
            Session if found, None otherwise.
        """
        path = self.get_daily_path(date)

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return self._deserialize_session(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def append_to_daily(self, turn: ConversationTurn, date: datetime | None = None) -> None:
        """Append a turn to the daily session.

        Args:
            turn: Turn to append.
            date: Date for the file. Defaults to today.
        """
        session = self.load_daily_session(date)

        if session is None:
            session = Session()

        session.add_turn(turn)
        self.save_daily_session(session, date)

    def list_daily_sessions(self) -> list[MemoryEntry]:
        """List all daily session files.

        Returns:
            List of memory entries.
        """
        entries = []

        for path in sorted(self.daily_path.glob("*.json"), reverse=True):
            try:
                date_str = path.stem  # e.g., "2026-02-02"
                date = datetime.strptime(date_str, "%Y-%m-%d")

                # Load to get metadata
                session = self.load_daily_session(date)
                if session:
                    entries.append(
                        MemoryEntry(
                            id=date_str,
                            name=date_str,
                            memory_type=MemoryType.DAILY,
                            created_at=date,
                            path=str(path),
                            turn_count=len(session.turns),
                            total_tokens=session.metadata.total_tokens,
                        )
                    )
            except (ValueError, json.JSONDecodeError):
                continue

        return entries

    # =========================================================================
    # Snapshots
    # =========================================================================

    def save_snapshot(self, snapshot: Snapshot) -> Path:
        """Save a snapshot.

        Args:
            snapshot: Snapshot to save.

        Returns:
            Path to the saved file.
        """
        filename = f"{snapshot.name}.json"
        path = self.snapshots_path / filename

        data = {
            "id": snapshot.id,
            "name": snapshot.name,
            "description": snapshot.description,
            "created_at": snapshot.created_at.isoformat(),
            "tags": snapshot.tags,
            "topic": snapshot.topic,
            "session": self._serialize_session(snapshot.session),
        }

        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def load_snapshot(self, name: str) -> Snapshot | None:
        """Load a snapshot by name.

        Args:
            name: Snapshot name.

        Returns:
            Snapshot if found, None otherwise.
        """
        path = self.snapshots_path / f"{name}.json"

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text())
            return Snapshot(
                id=data.get("id", name),
                name=data["name"],
                description=data.get("description", ""),
                created_at=datetime.fromisoformat(data["created_at"]),
                tags=data.get("tags", []),
                topic=data.get("topic"),
                session=self._deserialize_session(data["session"]),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def delete_snapshot(self, name: str) -> bool:
        """Delete a snapshot.

        Args:
            name: Snapshot name.

        Returns:
            True if deleted, False if not found.
        """
        path = self.snapshots_path / f"{name}.json"

        if path.exists():
            path.unlink()
            return True
        return False

    def list_snapshots(self) -> list[MemoryEntry]:
        """List all snapshots.

        Returns:
            List of memory entries.
        """
        entries = []

        for path in sorted(self.snapshots_path.glob("*.json"), reverse=True):
            try:
                snapshot = self.load_snapshot(path.stem)
                if snapshot:
                    entries.append(
                        MemoryEntry(
                            id=snapshot.id,
                            name=snapshot.name,
                            memory_type=MemoryType.SNAPSHOT,
                            created_at=snapshot.created_at,
                            path=str(path),
                            turn_count=len(snapshot.session.turns),
                            total_tokens=snapshot.session.metadata.total_tokens,
                            description=snapshot.description,
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                continue

        return entries

    # =========================================================================
    # Handoffs
    # =========================================================================

    def save_handoff(self, handoff: HandoffDocument) -> Path:
        """Save a handoff document.

        Args:
            handoff: Handoff to save.

        Returns:
            Path to the saved file.
        """
        timestamp = handoff.created_at.strftime("%Y%m%d_%H%M%S")
        filename = f"handoff_{timestamp}.json"
        path = self.handoffs_path / filename

        data = {
            "id": handoff.id,
            "created_at": handoff.created_at.isoformat(),
            "session_id": handoff.session_id,
            "summary": handoff.summary,
            "key_decisions": handoff.key_decisions,
            "pending_tasks": handoff.pending_tasks,
            "system_prompt": handoff.system_prompt,
            "recent_turns": [
                {
                    **t.model_dump(mode="json"),
                    "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                }
                for t in handoff.recent_turns
            ],
            "full_context": (
                self._serialize_session(handoff.full_context) if handoff.full_context else None
            ),
            "total_tokens_used": handoff.total_tokens_used,
            "total_cost": handoff.total_cost,
            "primary_model": handoff.primary_model,
            "recovered": handoff.recovered,
            "recovered_at": (handoff.recovered_at.isoformat() if handoff.recovered_at else None),
        }

        path.write_text(json.dumps(data, indent=2, default=str))
        return path

    def load_latest_handoff(self) -> HandoffDocument | None:
        """Load the most recent handoff.

        Returns:
            Handoff if found, None otherwise.
        """
        handoffs = list(self.handoffs_path.glob("handoff_*.json"))

        if not handoffs:
            return None

        # Sort by filename (timestamp) and get most recent
        latest = sorted(handoffs, reverse=True)[0]
        return self._load_handoff_file(latest)

    def _load_handoff_file(self, path: Path) -> HandoffDocument | None:
        """Load a handoff from a file.

        Args:
            path: Path to handoff file.

        Returns:
            Handoff if valid, None otherwise.
        """
        try:
            data = json.loads(path.read_text())

            # Parse turns
            recent_turns = []
            for turn_data in data.get("recent_turns", []):
                if "timestamp" in turn_data and isinstance(turn_data["timestamp"], str):
                    turn_data["timestamp"] = datetime.fromisoformat(turn_data["timestamp"])
                recent_turns.append(ConversationTurn(**turn_data))

            # Parse full context if present
            full_context = None
            if data.get("full_context"):
                full_context = self._deserialize_session(data["full_context"])

            return HandoffDocument(
                id=data.get("id", path.stem),
                created_at=datetime.fromisoformat(data["created_at"]),
                session_id=data["session_id"],
                summary=data["summary"],
                key_decisions=data.get("key_decisions", []),
                pending_tasks=data.get("pending_tasks", []),
                system_prompt=data.get("system_prompt"),
                recent_turns=recent_turns,
                full_context=full_context,
                total_tokens_used=data.get("total_tokens_used", 0),
                total_cost=data.get("total_cost", 0.0),
                primary_model=data.get("primary_model"),
                recovered=data.get("recovered", False),
                recovered_at=(
                    datetime.fromisoformat(data["recovered_at"])
                    if data.get("recovered_at")
                    else None
                ),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def archive_handoff(self, handoff: HandoffDocument) -> Path:
        """Move a handoff to the archive.

        Args:
            handoff: Handoff to archive.

        Returns:
            New path in archive.
        """
        # Find the current file
        timestamp = handoff.created_at.strftime("%Y%m%d_%H%M%S")
        current_path = self.handoffs_path / f"handoff_{timestamp}.json"

        if not current_path.exists():
            # Save it first
            current_path = self.save_handoff(handoff)

        # Move to archive
        archive_path = self.archive_path / current_path.name

        current_path.rename(archive_path)
        return archive_path

    def list_handoffs(self, include_archived: bool = False) -> list[MemoryEntry]:
        """List all handoffs.

        Args:
            include_archived: Whether to include archived handoffs.

        Returns:
            List of memory entries.
        """
        entries = []
        paths = list(self.handoffs_path.glob("handoff_*.json"))

        if include_archived:
            paths.extend(self.archive_path.glob("handoff_*.json"))

        for path in sorted(paths, reverse=True):
            try:
                handoff = self._load_handoff_file(path)
                if handoff:
                    entries.append(
                        MemoryEntry(
                            id=handoff.id,
                            name=path.stem,
                            memory_type=MemoryType.HANDOFF,
                            created_at=handoff.created_at,
                            path=str(path),
                            turn_count=len(handoff.recent_turns),
                            total_tokens=handoff.total_tokens_used,
                            description=handoff.summary[:100] + "..."
                            if len(handoff.summary) > 100
                            else handoff.summary,
                        )
                    )
            except (json.JSONDecodeError, KeyError):
                continue

        return entries

    # =========================================================================
    # General Operations
    # =========================================================================

    def list_all(self, memory_type: MemoryType | None = None) -> list[MemoryEntry]:
        """List all memory entries.

        Args:
            memory_type: Filter by type, or None for all.

        Returns:
            List of memory entries.
        """
        entries = []

        if memory_type is None or memory_type == MemoryType.DAILY:
            entries.extend(self.list_daily_sessions())

        if memory_type is None or memory_type == MemoryType.SNAPSHOT:
            entries.extend(self.list_snapshots())

        if memory_type is None or memory_type == MemoryType.HANDOFF:
            entries.extend(self.list_handoffs())

        # Sort by created_at
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    def delete_older_than(self, days: int, memory_type: MemoryType | None = None) -> int:
        """Delete memory files older than a certain number of days.

        Args:
            days: Delete files older than this many days.
            memory_type: Type to delete, or None for all.

        Returns:
            Number of files deleted.
        """
        cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        cutoff = cutoff - timedelta(days=days)

        deleted = 0

        for entry in self.list_all(memory_type):
            if entry.created_at < cutoff:
                path = Path(entry.path)
                if path.exists():
                    path.unlink()
                    deleted += 1

        return deleted
