"""Session mapper for platform channels to InkArms session mapping."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from inkarms.models.platforms import PlatformType, PlatformUser
from inkarms.storage import get_inkarms_home

logger = logging.getLogger(__name__)


class SessionMapping(BaseModel):
    """Mapping between platform channel and session."""

    platform: PlatformType
    platform_user_id: str
    channel_id: str | None = None
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = Field(default_factory=dict)

    def __str__(self) -> str:
        """String representation."""
        key = f"{self.platform.value}:{self.channel_id or self.platform_user_id}"
        return f"{key} -> {self.session_id}"


class SessionMapper:
    """Maps platform channels to InkArms session IDs.

    Features:
    - Per-channel sessions (different chats get different sessions)
    - Session chains (groups of channels sharing one session)
    - Persistent storage in JSON
    - User metadata tracking
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        chains: list[list[str]] | None = None,
    ):
        """Initialize the session mapper.

        Args:
            storage_path: Path to storage file (defaults to ~/.inkarms/platform_sessions.json)
            chains: Session chain config — groups of channel identifiers that share sessions.
                E.g. [["cli", "telegram"], ["slack:#dev", "discord:#dev"]]
        """
        if storage_path is None:
            inkarms_home = get_inkarms_home()
            storage_path = inkarms_home / "platform_sessions.json"

        self._storage_path = storage_path
        self._mappings: dict[str, SessionMapping] = {}
        self._chains: list[list[str]] = chains or []
        self._load()

    def get_session_id(
        self,
        user: PlatformUser,
        channel_id: str | None = None,
        create_if_missing: bool = True,
    ) -> str | None:
        """Get session ID for a platform channel.

        Uses channel_id for per-channel isolation. Falls back to user_id
        for DMs or when channel_id is not provided.

        Args:
            user: Platform user.
            channel_id: Channel/chat ID (e.g. Telegram chat_id).
            create_if_missing: Whether to create a new session if not found.

        Returns:
            Session ID, or None if not found and create_if_missing=False.
        """
        key = self._make_key(user.platform, channel_id or user.platform_user_id)

        # Check if mapping exists
        if key in self._mappings:
            mapping = self._mappings[key]
            mapping.last_accessed = datetime.now(UTC)
            self._save()
            return mapping.session_id

        # Check if this channel is in a chain with an existing session
        chain_session_id = self._find_chain_session(
            user.platform.value, channel_id or user.platform_user_id
        )

        if create_if_missing:
            session_id = chain_session_id or self._generate_session_id(
                user.platform, channel_id or user.platform_user_id
            )
            mapping = SessionMapping(
                platform=user.platform,
                platform_user_id=user.platform_user_id,
                channel_id=channel_id,
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

        return chain_session_id

    def set_session_id(
        self,
        user: PlatformUser,
        session_id: str,
        channel_id: str | None = None,
    ) -> None:
        """Explicitly set the session ID for a channel.

        Used by /load and /new commands to switch sessions.

        Args:
            user: Platform user.
            session_id: New session ID.
            channel_id: Channel/chat ID.
        """
        key = self._make_key(user.platform, channel_id or user.platform_user_id)

        if key in self._mappings:
            self._mappings[key].session_id = session_id
            self._mappings[key].last_accessed = datetime.now(UTC)
        else:
            self._mappings[key] = SessionMapping(
                platform=user.platform,
                platform_user_id=user.platform_user_id,
                channel_id=channel_id,
                session_id=session_id,
                metadata={
                    "username": user.username or "",
                    "display_name": user.display_name or "",
                },
            )

        # Sync chain members
        channel_identifier = self._to_channel_identifier(
            user.platform.value, channel_id or user.platform_user_id
        )
        self._sync_chain(channel_identifier, session_id)
        self._save()

    def link_channels(
        self,
        platform1: str,
        channel1: str,
        platform2: str,
        channel2: str,
    ) -> bool:
        """Link two channels to share the same session.

        Args:
            platform1: First platform name.
            channel1: First channel ID.
            platform2: Second platform name.
            channel2: Second channel ID.

        Returns:
            True if linked successfully, False if first channel not found.
        """
        key1 = self._make_key(PlatformType(platform1), channel1)
        key2 = self._make_key(PlatformType(platform2), channel2)

        if key1 not in self._mappings:
            return False

        session_id = self._mappings[key1].session_id

        if key2 in self._mappings:
            self._mappings[key2].session_id = session_id
        else:
            self._mappings[key2] = SessionMapping(
                platform=PlatformType(platform2),
                platform_user_id=channel2,
                channel_id=channel2,
                session_id=session_id,
            )

        self._save()
        logger.info(f"Linked {key2} to {key1} (session: {session_id})")
        return True

    def link_users(
        self,
        user1: PlatformUser,
        user2: PlatformUser,
    ) -> bool:
        """Link two platform users to share the same session.

        Kept for backward compatibility. Prefer link_channels() for new code.

        Args:
            user1: First platform user.
            user2: Second platform user.

        Returns:
            True if linked successfully, False if users don't exist.
        """
        key1 = self._make_key(user1.platform, user1.platform_user_id)
        key2 = self._make_key(user2.platform, user2.platform_user_id)

        if key1 not in self._mappings or key2 not in self._mappings:
            return False

        session_id = self._mappings[key1].session_id
        self._mappings[key2].session_id = session_id
        self._save()

        logger.info(f"Linked {key2} to {key1} (session: {session_id})")
        return True

    def unlink_user(self, user: PlatformUser) -> bool:
        """Unlink a user and give them a fresh session.

        Args:
            user: Platform user to unlink.

        Returns:
            True if unlinked, False if user doesn't exist.
        """
        key = self._make_key(user.platform, user.platform_user_id)

        if key not in self._mappings:
            return False

        new_session_id = self._generate_session_id(
            user.platform, user.platform_user_id
        )
        self._mappings[key].session_id = new_session_id
        self._save()

        logger.info(f"Unlinked {key}, new session: {new_session_id}")
        return True

    def get_mapping(
        self, user: PlatformUser, channel_id: str | None = None
    ) -> SessionMapping | None:
        """Get full mapping for a user/channel.

        Args:
            user: Platform user.
            channel_id: Optional channel ID. If provided, looks up by channel;
                otherwise falls back to user_id.

        Returns:
            SessionMapping or None if not found.
        """
        key = self._make_key(user.platform, channel_id or user.platform_user_id)
        return self._mappings.get(key)

    def delete_mapping(self, user: PlatformUser) -> bool:
        """Delete a user's session mapping.

        Args:
            user: Platform user.

        Returns:
            True if deleted, False if not found.
        """
        key = self._make_key(user.platform, user.platform_user_id)

        if key in self._mappings:
            del self._mappings[key]
            self._save()
            logger.info(f"Deleted mapping: {key}")
            return True

        return False

    def list_mappings(
        self, platform: PlatformType | None = None
    ) -> list[SessionMapping]:
        """List all session mappings.

        Args:
            platform: Optional platform filter.

        Returns:
            List of session mappings.
        """
        mappings = list(self._mappings.values())

        if platform:
            mappings = [m for m in mappings if m.platform == platform]

        return sorted(mappings, key=lambda m: m.last_accessed, reverse=True)

    # --- Chain helpers ---

    @staticmethod
    def _to_channel_identifier(platform: str, channel_id: str) -> str:
        """Build a channel identifier for chain matching.

        Channel identifiers in config use formats like:
        - "cli", "telegram" (generic, matches any channel on that platform)
        - "telegram:12345" (specific chat)
        """
        return f"{platform}:{channel_id}"

    def _find_chain_session(self, platform: str, channel_id: str) -> str | None:
        """Find session_id from chain members if this channel is in a chain.

        Returns the session_id of the first chain member that already has one.
        If the chain contains "cli" or "tui" but no member has a session yet,
        returns "default" to share the CLI's storage location.
        Returns None if the channel is not in any chain.
        """
        channel_ident = self._to_channel_identifier(platform, channel_id)

        for chain in self._chains:
            if not self._matches_chain(channel_ident, chain):
                continue

            # Found our chain — look for an existing session from another member
            for member in chain:
                for _key, mapping in self._mappings.items():
                    member_ident = self._to_channel_identifier(
                        mapping.platform.value,
                        mapping.channel_id or mapping.platform_user_id,
                    )
                    if self._identifier_matches(member_ident, member):
                        return mapping.session_id

            # No existing member session found.
            # If chain includes CLI/TUI, default to "default" session
            # so the platform shares CLI's storage location.
            if any(m in ("cli", "tui") for m in chain):
                return "default"

        return None

    def _sync_chain(self, channel_identifier: str, session_id: str) -> None:
        """Sync all chain members to the same session_id.

        Called when one member switches session (via /new, /load, etc.).
        """
        for chain in self._chains:
            if not self._matches_chain(channel_identifier, chain):
                continue

            for _key, mapping in self._mappings.items():
                member_ident = self._to_channel_identifier(
                    mapping.platform.value,
                    mapping.channel_id or mapping.platform_user_id,
                )
                for member in chain:
                    if self._identifier_matches(member_ident, member):
                        mapping.session_id = session_id
                        break

    @staticmethod
    def _matches_chain(channel_identifier: str, chain: list[str]) -> bool:
        """Check if a channel identifier matches any member of a chain."""
        return any(
            SessionMapper._identifier_matches(channel_identifier, member)
            for member in chain
        )

    @staticmethod
    def _identifier_matches(actual: str, pattern: str) -> bool:
        """Check if a channel identifier matches a chain pattern.

        Patterns:
        - "telegram" matches "telegram:*" (any telegram channel)
        - "telegram:12345" matches only "telegram:12345"
        - "cli" matches "cli:*"
        """
        if ":" not in pattern:
            # Generic pattern matches any channel on that platform
            return actual.startswith(f"{pattern}:")
        return actual == pattern

    # --- Internal helpers ---

    @staticmethod
    def _make_key(platform: PlatformType, identifier: str) -> str:
        """Create a unique key for a platform channel.

        Args:
            platform: Platform type.
            identifier: Channel ID or user ID.

        Returns:
            Unique key string.
        """
        return f"{platform.value}:{identifier}"

    @staticmethod
    def _generate_session_id(platform: PlatformType, identifier: str) -> str:
        """Generate a session ID for a channel.

        Args:
            platform: Platform type.
            identifier: Channel or user ID.

        Returns:
            Generated session ID.
        """
        safe_id = "".join(c for c in identifier if c.isalnum() or c in "-_")
        short_uuid = uuid.uuid4().hex[:8]
        return f"{platform.value}_{safe_id}_{short_uuid}"

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
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            data = {key: mapping.model_dump() for key, mapping in self._mappings.items()}
            self._storage_path.write_text(json.dumps(data, indent=2, default=str))

        except Exception as e:
            logger.error(f"Failed to save session mappings: {e}", exc_info=True)


# Singleton instance
_session_mapper: SessionMapper | None = None


def get_session_mapper() -> SessionMapper:
    """Get the global session mapper instance.

    Returns:
        SessionMapper singleton.
    """
    global _session_mapper
    if _session_mapper is None:
        _session_mapper = SessionMapper()
    return _session_mapper


def reset_session_mapper() -> None:
    """Reset the global session mapper instance."""
    global _session_mapper
    _session_mapper = None
