"""Handoff repository for managing context handoffs."""

from datetime import datetime
from pathlib import Path

from inkarms.memory.repositories.base import JsonFileRepository
from inkarms.memory.repositories.session import SessionRepository
from inkarms.models.memory import ConversationTurn, HandoffDocument, MemoryEntry, MemoryType


class HandoffRepository(JsonFileRepository[HandoffDocument]):
    """Repository for managing handoff files."""

    def __init__(self, base_path: Path):
        """Initialize handoff repository."""
        super().__init__(base_path / "handoffs")
        self.archive_path = base_path / "archive"
        self.archive_path.mkdir(parents=True, exist_ok=True)
        # Helper for session serialization
        self._session_repo = SessionRepository(base_path)

    def save(self, handoff: HandoffDocument) -> Path:
        """Save a handoff document."""
        timestamp = handoff.created_at.strftime("%Y%m%d_%H%M%S")
        filename = f"handoff_{timestamp}.json"
        path = self.base_path / filename

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
                self._session_repo._serialize(handoff.full_context)
                if handoff.full_context
                else None
            ),
            "total_tokens_used": handoff.total_tokens_used,
            "total_cost": handoff.total_cost,
            "primary_model": handoff.primary_model,
            "recovered": handoff.recovered,
            "recovered_at": (handoff.recovered_at.isoformat() if handoff.recovered_at else None),
        }

        self._save_json(path, data)
        return path

    def load_latest(self) -> HandoffDocument | None:
        """Load the most recent handoff."""
        handoffs = list(self.base_path.glob("handoff_*.json"))
        if not handoffs:
            return None

        # Sort by filename (timestamp) and get most recent
        latest = sorted(handoffs, reverse=True)[0]
        return self._load_file(latest)

    def _load_file(self, path: Path) -> HandoffDocument | None:
        """Load a handoff from a file."""
        data = self._load_json(path)
        if not data:
            return None

        try:
            # Parse turns
            recent_turns = []
            for turn_data in data.get("recent_turns", []):
                if "timestamp" in turn_data and isinstance(turn_data["timestamp"], str):
                    turn_data["timestamp"] = datetime.fromisoformat(turn_data["timestamp"])
                recent_turns.append(ConversationTurn(**turn_data))

            # Parse full context if present
            full_context = None
            if data.get("full_context"):
                full_context = self._session_repo._deserialize(data["full_context"])

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
        except (ValueError, KeyError):
            return None

    def archive(self, handoff: HandoffDocument) -> Path:
        """Move a handoff to the archive."""
        # Find the current file
        timestamp = handoff.created_at.strftime("%Y%m%d_%H%M%S")
        current_path = self.base_path / f"handoff_{timestamp}.json"

        if not current_path.exists():
            # Save it first if it doesn't exist
            current_path = self.save(handoff)

        # Move to archive
        archive_path = self.archive_path / current_path.name
        current_path.rename(archive_path)
        return archive_path

    def list_entries(self, include_archived: bool = False) -> list[MemoryEntry]:
        """List all handoffs."""
        entries = []
        paths = list(self.base_path.glob("handoff_*.json"))

        if include_archived:
            paths.extend(self.archive_path.glob("handoff_*.json"))

        for path in sorted(paths, reverse=True):
            try:
                handoff = self._load_file(path)
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
                            description=(
                                handoff.summary[:100] + "..."
                                if len(handoff.summary) > 100
                                else handoff.summary
                            ),
                        )
                    )
            except (ValueError, Exception):
                continue
        return entries
