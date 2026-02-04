"""Session mapper for platform user to InkArms session mapping."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from inkarms.platforms.models import PlatformType, PlatformUser
from inkarms.storage import get_inkarms_home

logger = logging.getLogger(__name__)


class SessionMapping(BaseModel):
    """Mapping between platform user and session."""

    platform: PlatformType
    platform_user_id: str
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, str] = Field(default_factory=dict)

    def __str__(self) -> str:
        """String representation."""
        return f"{self.platform.value}:{self.platform_user_id} -> {self.session_id}"


class SessionMapper:
    """Maps platform users to InkArms session IDs.

    Features:
    - Unique session per (platform, user_id)
    - Persistent storage in JSON
    - Cross-platform user linking (optional)
    - User metadata tracking
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """Initialize the session mapper.

        Args:
            storage_path: Path to storage file (defaults to ~/.inkarms/platform_sessions.json)
        """
        if storage_path is None:
            inkarms_home = get_inkarms_home()
            storage_path = inkarms_home / "platform_sessions.json"

        self._storage_path = storage_path
        self._mappings: dict[str, SessionMapping] = {}
        self._load()

    def get_session_id(
        self,
        user: PlatformUser,
        create_if_missing: bool = True,
    ) -> Optional[str]:
        """Get session ID for a platform user.

        Args:
            user: Platform user
            create_if_missing: Whether to create a new session if not found

        Returns:
            Session ID, or None if not found and create_if_missing=False
        """
        key = self._make_key(user.platform, user.platform_user_id)

        # Check if mapping exists
        if key in self._mappings:
            mapping = self._mappings[key]
            # Update last accessed time
            mapping.last_accessed = datetime.utcnow()
            self._save()
            return mapping.session_id

        # Create new mapping if requested
        if create_if_missing:
            session_id = self._generate_session_id(user)
            mapping = SessionMapping(
                platform=user.platform,
                platform_user_id=user.platform_user_id,
                session_id=session_id,
                metadata={
                    "username": user.username or "",
                    "display_name": user.display_name or "",
                },
            )
            self._mappings[key] = mapping
            self._save()
            logger.info(f"Created new session mapping: {mapping}")
            return session_id

        return None

    def link_users(
        self,
        user1: PlatformUser,
        user2: PlatformUser,
    ) -> bool:
        """Link two platform users to share the same session.

        This allows cross-platform conversations (e.g., same user on Telegram and Slack).

        Args:
            user1: First platform user
            user2: Second platform user

        Returns:
            True if linked successfully, False if users don't exist
        """
        key1 = self._make_key(user1.platform, user1.platform_user_id)
        key2 = self._make_key(user2.platform, user2.platform_user_id)

        # Both users must exist
        if key1 not in self._mappings or key2 not in self._mappings:
            return False

        # Use the session ID from user1
        session_id = self._mappings[key1].session_id

        # Update user2's mapping
        self._mappings[key2].session_id = session_id
        self._save()

        logger.info(f"Linked {key2} to {key1} (session: {session_id})")
        return True

    def unlink_user(self, user: PlatformUser) -> bool:
        """Unlink a user and give them a fresh session.

        Args:
            user: Platform user to unlink

        Returns:
            True if unlinked, False if user doesn't exist
        """
        key = self._make_key(user.platform, user.platform_user_id)

        if key not in self._mappings:
            return False

        # Generate new session ID
        new_session_id = self._generate_session_id(user)
        self._mappings[key].session_id = new_session_id
        self._save()

        logger.info(f"Unlinked {key}, new session: {new_session_id}")
        return True

    def get_mapping(self, user: PlatformUser) -> Optional[SessionMapping]:
        """Get full mapping for a user.

        Args:
            user: Platform user

        Returns:
            SessionMapping or None if not found
        """
        key = self._make_key(user.platform, user.platform_user_id)
        return self._mappings.get(key)

    def delete_mapping(self, user: PlatformUser) -> bool:
        """Delete a user's session mapping.

        Args:
            user: Platform user

        Returns:
            True if deleted, False if not found
        """
        key = self._make_key(user.platform, user.platform_user_id)

        if key in self._mappings:
            del self._mappings[key]
            self._save()
            logger.info(f"Deleted mapping: {key}")
            return True

        return False

    def list_mappings(
        self, platform: Optional[PlatformType] = None
    ) -> list[SessionMapping]:
        """List all session mappings.

        Args:
            platform: Optional platform filter

        Returns:
            List of session mappings
        """
        mappings = list(self._mappings.values())

        if platform:
            mappings = [m for m in mappings if m.platform == platform]

        return sorted(mappings, key=lambda m: m.last_accessed, reverse=True)

    def _make_key(self, platform: PlatformType, user_id: str) -> str:
        """Create a unique key for a platform user.

        Args:
            platform: Platform type
            user_id: Platform-specific user ID

        Returns:
            Unique key string
        """
        return f"{platform.value}:{user_id}"

    def _generate_session_id(self, user: PlatformUser) -> str:
        """Generate a session ID for a user.

        Format: <platform>_<user_id>_<timestamp>

        Args:
            user: Platform user

        Returns:
            Generated session ID
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        # Sanitize user ID (remove special characters)
        safe_user_id = "".join(c for c in user.platform_user_id if c.isalnum() or c in "-_")
        return f"{user.platform.value}_{safe_user_id}_{timestamp}"

    def _load(self) -> None:
        """Load mappings from storage file."""
        if not self._storage_path.exists():
            logger.debug(f"No existing mappings file: {self._storage_path}")
            return

        try:
            data = json.loads(self._storage_path.read_text())
            for key, mapping_data in data.items():
                mapping = SessionMapping(**mapping_data)
                self._mappings[key] = mapping

            logger.info(f"Loaded {len(self._mappings)} session mappings")

        except Exception as e:
            logger.error(f"Failed to load session mappings: {e}", exc_info=True)

    def _save(self) -> None:
        """Save mappings to storage file."""
        try:
            # Ensure parent directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize mappings
            data = {key: mapping.model_dump() for key, mapping in self._mappings.items()}

            # Write to file
            self._storage_path.write_text(json.dumps(data, indent=2, default=str))

        except Exception as e:
            logger.error(f"Failed to save session mappings: {e}", exc_info=True)


# Singleton instance
_session_mapper: Optional[SessionMapper] = None


def get_session_mapper() -> SessionMapper:
    """Get the global session mapper instance.

    Returns:
        SessionMapper singleton
    """
    global _session_mapper
    if _session_mapper is None:
        _session_mapper = SessionMapper()
    return _session_mapper


def reset_session_mapper() -> None:
    """Reset the global session mapper instance."""
    global _session_mapper
    _session_mapper = None
