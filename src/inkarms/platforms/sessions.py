"""Per-channel session manager store for platform messaging.

Manages SessionManager instances keyed by session_id. The special
session_id "default" maps to the CLI's singleton SessionManager,
so channels chained with CLI share its storage transparently.
"""

from __future__ import annotations

import logging
from pathlib import Path

from inkarms.memory.manager import SessionManager, get_session_manager
from inkarms.storage import get_inkarms_home

logger = logging.getLogger(__name__)


class PlatformSessionStore:
    """Cache of per-channel SessionManager instances.

    Storage layout:
        ~/.inkarms/memory/platform/<session_id>/daily/YYYY-MM-DD.json
        Special: session_id="default" -> ~/.inkarms/memory/ (CLI's location)
    """

    def __init__(self, base_path: Path | None = None):
        """Initialize the session store.

        Args:
            base_path: Root directory for platform session storage.
                Defaults to ~/.inkarms/memory/platform/.
        """
        if base_path is None:
            base_path = get_inkarms_home() / "memory" / "platform"
        self._base_path = base_path
        self._managers: dict[str, SessionManager] = {}

    def get_manager(
        self,
        session_id: str,
        model: str | None = None,
    ) -> SessionManager:
        """Get or create a SessionManager for the given session_id.

        Args:
            session_id: Session identifier. "default" reuses the CLI singleton.
            model: Model name for context tracking.

        Returns:
            SessionManager instance.
        """
        if session_id == "default":
            return get_session_manager(model=model)

        if session_id in self._managers:
            mgr = self._managers[session_id]
            if model and mgr.model != model:
                mgr.set_model(model)
            return mgr

        storage_path = self._base_path / session_id
        mgr = SessionManager(model=model, storage_path=storage_path)
        self._managers[session_id] = mgr
        logger.info(f"Created session manager for session: {session_id}")
        return mgr

    def clear_session(self, session_id: str) -> None:
        """Clear the session data for a given session_id.

        Args:
            session_id: Session identifier.
        """
        if session_id == "default":
            get_session_manager().clear_session()
            return

        if session_id in self._managers:
            self._managers[session_id].clear_session()

    def drop_manager(self, session_id: str) -> None:
        """Remove a cached SessionManager instance.

        Args:
            session_id: Session identifier.
        """
        if session_id in self._managers:
            try:
                self._managers[session_id].save_session()
            except Exception as e:
                logger.error(f"Failed to save session {session_id} before drop: {e}")
            del self._managers[session_id]

    def list_sessions(self, prefix: str | None = None) -> list[dict[str, str]]:
        """List known sessions.

        Args:
            prefix: Optional prefix filter for session IDs.

        Returns:
            List of dicts with session_id and path.
        """
        results: list[dict[str, str]] = []

        if not self._base_path.exists():
            return results

        for child in sorted(self._base_path.iterdir()):
            if child.is_dir():
                sid = child.name
                if prefix and not sid.startswith(prefix):
                    continue
                results.append({"session_id": sid, "path": str(child)})

        return results

    def save_all(self) -> None:
        """Save all cached session managers to disk."""
        for session_id, mgr in self._managers.items():
            try:
                mgr.save_session()
            except Exception as e:
                logger.error(f"Failed to save session {session_id}: {e}")
