"""Snapshot repository for session snapshots."""

from datetime import datetime
from pathlib import Path

from inkarms.memory.repositories.base import JsonFileRepository
from inkarms.memory.repositories.session import SessionRepository
from inkarms.models.memory import MemoryEntry, MemoryType, Snapshot


class SnapshotRepository(JsonFileRepository[Snapshot]):
    """Repository for managing session snapshots."""

    def __init__(self, base_path: Path):
        """Initialize snapshot repository."""
        super().__init__(base_path / "snapshots")
        self._session_repo = SessionRepository(base_path)

    def save(self, snapshot: Snapshot) -> Path:
        """Save a snapshot."""
        filename = f"{snapshot.name}.json"
        path = self.base_path / filename

        data = {
            "id": snapshot.id,
            "name": snapshot.name,
            "description": snapshot.description,
            "created_at": snapshot.created_at.isoformat(),
            "tags": snapshot.tags,
            "topic": snapshot.topic,
            "session": self._session_repo.serialize(snapshot.session),
        }

        self._save_json(path, data)
        return path

    def load(self, name: str) -> Snapshot | None:
        """Load a snapshot by name."""
        path = self.base_path / f"{name}.json"
        data = self._load_json(path)
        if not data:
            return None

        try:
            return Snapshot(
                id=data.get("id", name),
                name=data["name"],
                description=data.get("description", ""),
                created_at=datetime.fromisoformat(data["created_at"]),
                tags=data.get("tags", []),
                topic=data.get("topic"),
                session=self._session_repo.deserialize(data["session"]),
            )
        except (ValueError, KeyError):
            return None

    def list_entries(self) -> list[MemoryEntry]:
        """List all snapshots."""
        entries = []
        for path in sorted(self.base_path.glob("*.json"), reverse=True):
            try:
                snapshot = self.load(path.stem)
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
            except (ValueError, Exception):
                continue
        return entries
