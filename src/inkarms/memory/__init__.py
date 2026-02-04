"""
InkArms Memory System.

Provides context tracking, session management, and memory persistence.

Usage:
    from inkarms.memory import SessionManager, get_session_manager

    # Get the session manager
    manager = get_session_manager()

    # Add messages
    manager.add_user_message("Hello!")
    manager.add_assistant_message("Hi there!")

    # Check context usage
    usage = manager.get_context_usage()
    print(f"Context: {usage.format_status()}")

    # Compact if needed
    if manager.should_compact():
        await manager.compact()

    # Create handoff when context is full
    if manager.should_handoff():
        await manager.create_handoff()
"""

# Models
from inkarms.memory.models import (
    ContextUsage,
    ConversationTurn,
    HandoffDocument,
    MemoryEntry,
    MemoryType,
    Session,
    SessionMetadata,
    Snapshot,
    TurnRole,
)

# Context tracking
from inkarms.memory.context import (
    ContextTracker,
    TokenCounter,
)

# Compaction
from inkarms.memory.compaction import (
    BaseCompactor,
    CompactionStrategy,
    SlidingWindowCompactor,
    SummarizeCompactor,
    TruncateCompactor,
    get_compactor,
)

# Storage
from inkarms.memory.storage import MemoryStorage

# Handoff
from inkarms.memory.handoff import HandoffManager

# Manager
from inkarms.memory.manager import (
    SessionManager,
    get_session_manager,
    reset_session_manager,
)

__all__ = [
    # Models
    "ContextUsage",
    "ConversationTurn",
    "HandoffDocument",
    "MemoryEntry",
    "MemoryType",
    "Session",
    "SessionMetadata",
    "Snapshot",
    "TurnRole",
    # Context
    "ContextTracker",
    "TokenCounter",
    # Compaction
    "BaseCompactor",
    "CompactionStrategy",
    "SlidingWindowCompactor",
    "SummarizeCompactor",
    "TruncateCompactor",
    "get_compactor",
    # Storage
    "MemoryStorage",
    # Handoff
    "HandoffManager",
    # Manager
    "SessionManager",
    "get_session_manager",
    "reset_session_manager",
]
