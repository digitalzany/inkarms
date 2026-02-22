"""Session repository for daily session logs."""

from datetime import datetime
from pathlib import Path
from typing import Any

from inkarms.memory.repositories.base import JsonFileRepository
from inkarms.models.memory import (
    ConversationTurn,
    MemoryEntry,
    MemoryType,
    Session,
    SessionMetadata,
)


class SessionRepository(JsonFileRepository[Session]):
    """Repository for managing daily session files."""

    def __init__(self, base_path: Path):
        """Initialize session repository."""
        super().__init__(base_path / "daily")

    @staticmethod
    def serialize(session: Session) -> dict[str, Any]:
        """Serialize a session to dict."""
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

    @staticmethod
    def deserialize(data: dict[str, Any]) -> Session:
        """Deserialize a session from dict."""
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

    def get_path(self, date: datetime | None = None) -> Path:
        """Get the path for a daily session file."""
        if date is None:
            date = datetime.now()
        filename = date.strftime("%Y-%m-%d.json")
        return self.base_path / filename

    def save(self, session: Session, date: datetime | None = None) -> Path:
        """Save a session as a daily log."""
        path = self.get_path(date)
        data = self.serialize(session)
        self._save_json(path, data)
        return path

    def load(self, date: datetime | None = None) -> Session | None:
        """Load a daily session."""
        path = self.get_path(date)
        data = self._load_json(path)
        if not data:
            return None
        return self.deserialize(data)

    def list_entries(self) -> list[MemoryEntry]:
        """List all daily session files."""
        entries = []
        for path in sorted(self.base_path.glob("*.json"), reverse=True):
            try:
                date_str = path.stem
                date = datetime.strptime(date_str, "%Y-%m-%d")
                data = self._load_json(path)
                if not data:
                    continue

                metadata = data.get("metadata", {})
                entries.append(
                    MemoryEntry(
                        id=date_str,
                        name=date_str,
                        memory_type=MemoryType.DAILY,
                        created_at=date,
                        path=str(path),
                        turn_count=metadata.get("turn_count", 0),
                        total_tokens=metadata.get("total_tokens", 0),
                    )
                )
            except (ValueError, Exception):
                continue
        return entries
