"""Base repository for JSON file storage."""

import json
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonFileRepository(Generic[T]):
    """Base class for JSON file-based repositories."""

    def __init__(self, base_path: Path):
        """Initialize repository.

        Args:
            base_path: Root directory for this repository.
        """
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write(path: Path, data: str) -> None:
        """Write data to a file atomically using a temp file and os.replace.

        Args:
            path: Target file path.
            data: String data to write.
        """
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(data, encoding="utf-8")
        tmp_path.replace(path)

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        """Save dictionary to JSON file."""
        self._atomic_write(path, json.dumps(data, indent=2, default=str))

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any] | None:
        """Load dictionary from JSON file."""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            return None

    @staticmethod
    def delete(path: Path) -> bool:
        """Delete a file if it exists."""
        if path.exists():
            path.unlink()
            return True
        return False
