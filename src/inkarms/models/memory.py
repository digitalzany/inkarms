"""
Memory models for InkArms.

Defines data structures for sessions, conversations, snapshots, and handoffs.
"""

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Types of memory entries."""

    DAILY = "daily"  # Daily conversation log
    SNAPSHOT = "snapshot"  # Named snapshot
    HANDOFF = "handoff"  # Handoff document for session transfer


class TurnRole(str, Enum):
    """Role in a conversation turn."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class ConversationTurn(BaseModel):
    """A single turn in a conversation.

    Represents one message in the conversation history with
    metadata for context management.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: TurnRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Token counts for context tracking
    token_count: int = 0

    # Optional metadata
    model: str | None = None
    cost: float | None = None
    skill: str | None = None  # Skill that was active

    # Compaction metadata
    is_compacted: bool = False  # Was this turn summarized?
    original_turn_ids: list[str] = Field(default_factory=list)  # IDs of turns that were compacted

    class Config:
        """Pydantic configuration."""

        use_enum_values = True

    def to_message_dict(self) -> dict[str, Any]:
        """Convert to LiteLLM-compatible message dict."""
        return {"role": self.role, "content": self.content}


class SessionMetadata(BaseModel):
    """Metadata for a session."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Session info
    name: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

    # Context tracking
    total_tokens: int = 0
    total_cost: float = 0.0
    turn_count: int = 0

    # Model info
    primary_model: str | None = None
    models_used: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """A conversation session.

    Contains the full conversation history and metadata.
    """

    metadata: SessionMetadata = Field(default_factory=SessionMetadata)
    turns: list[ConversationTurn] = Field(default_factory=list)

    # Active system prompt (separate from turns for efficiency)
    system_prompt: str | None = None

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True

    @property
    def id(self) -> str:
        """Get the session ID."""
        return self.metadata.id

    @property
    def total_tokens(self) -> int:
        """Get total token count."""
        return sum(t.token_count for t in self.turns)

    def add_turn(self, turn: ConversationTurn) -> None:
        """Add a turn to the session."""
        self.turns.append(turn)
        self.metadata.turn_count = len(self.turns)
        self.metadata.total_tokens = self.total_tokens
        self.metadata.updated_at = datetime.now()

        if turn.cost:
            self.metadata.total_cost += turn.cost
        if turn.model and turn.model not in self.metadata.models_used:
            self.metadata.models_used.append(turn.model)

    def add_user_message(self, content: str, token_count: int = 0) -> ConversationTurn:
        """Add a user message."""
        turn = ConversationTurn(
            role=TurnRole.USER,
            content=content,
            token_count=token_count,
        )
        self.add_turn(turn)
        return turn

    def add_assistant_message(
        self,
        content: str,
        token_count: int = 0,
        model: str | None = None,
        cost: float | None = None,
    ) -> ConversationTurn:
        """Add an assistant message."""
        turn = ConversationTurn(
            role=TurnRole.ASSISTANT,
            content=content,
            token_count=token_count,
            model=model,
            cost=cost,
        )
        self.add_turn(turn)
        return turn

    def get_messages(self, include_system: bool = True) -> list[dict[str, Any]]:
        """Get messages in LiteLLM format.

        Args:
            include_system: Whether to include the system prompt.

        Returns:
            List of message dicts.
        """
        messages = []

        if include_system and self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        for turn in self.turns:
            messages.append(turn.to_message_dict())

        return messages

    def get_recent_turns(self, count: int) -> list[ConversationTurn]:
        """Get the most recent turns.

        Args:
            count: Number of turns to get.

        Returns:
            List of recent turns.
        """
        return self.turns[-count:] if self.turns else []


class Snapshot(BaseModel):
    """A named snapshot of a session.

    Used for saving important conversation states.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

    # The session state at snapshot time
    session: Session

    # Snapshot metadata
    tags: list[str] = Field(default_factory=list)
    topic: str | None = None


class HandoffDocument(BaseModel):
    """A handoff document for session transfer.

    Created when context is full or session needs to be continued elsewhere.
    Contains everything needed to resume the conversation.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = Field(default_factory=datetime.now)

    # Session summary
    session_id: str
    summary: str  # LLM-generated summary of the conversation
    key_decisions: list[str] = Field(default_factory=list)
    pending_tasks: list[str] = Field(default_factory=list)

    # Context preservation
    system_prompt: str | None = None
    recent_turns: list[ConversationTurn] = Field(default_factory=list)
    full_context: Session | None = None  # Optional full context

    # Technical metadata
    total_tokens_used: int = 0
    total_cost: float = 0.0
    primary_model: str | None = None

    # Recovery status
    recovered: bool = False
    recovered_at: datetime | None = None


class MemoryEntry(BaseModel):
    """An entry in the memory index.

    Used for listing and searching memory files.
    """

    id: str
    name: str
    memory_type: MemoryType
    created_at: datetime
    path: str

    # Summary info
    turn_count: int = 0
    total_tokens: int = 0
    description: str = ""

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class ContextUsage(BaseModel):
    """Current context window usage.

    Tracks how much of the context window is used.
    """

    current_tokens: int = 0
    max_tokens: int = 128000  # Default for most models

    # Thresholds (from config)
    compact_threshold: float = 0.70  # Trigger compaction at 70%
    handoff_threshold: float = 0.85  # Trigger handoff at 85%

    @property
    def usage_percent(self) -> float:
        """Get usage as a percentage."""
        if self.max_tokens == 0:
            return 0.0
        return self.current_tokens / self.max_tokens

    @property
    def should_compact(self) -> bool:
        """Check if compaction should be triggered."""
        return self.usage_percent >= self.compact_threshold

    @property
    def should_handoff(self) -> bool:
        """Check if handoff should be triggered."""
        return self.usage_percent >= self.handoff_threshold

    @property
    def tokens_remaining(self) -> int:
        """Get remaining token capacity."""
        return max(0, self.max_tokens - self.current_tokens)

    def format_status(self) -> str:
        """Format a status string."""
        percent = self.usage_percent * 100
        return f"{self.current_tokens:,}/{self.max_tokens:,} ({percent:.1f}%)"
