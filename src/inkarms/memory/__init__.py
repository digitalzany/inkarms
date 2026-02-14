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
# Compaction
from inkarms.memory.compaction import (
    BaseCompactor,
    CompactionOrchestrator,
    CompactionStrategy,
    SlidingWindowCompactor,
    SummarizeCompactor,
    TruncateCompactor,
    get_compactor,
)

# Context tracking
from inkarms.memory.context import (
    ContextTracker,
    TokenCounter,
)

# Handoff
from inkarms.memory.handoff import HandoffManager

# Manager
from inkarms.memory.manager import (
    SessionManager,
    get_session_manager,
    reset_session_manager,
)

# Persistence
from inkarms.memory.persister import SessionPersister

# Storage
from inkarms.memory.storage import MemoryStorage
from inkarms.models.memory import (
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

__all__ = [
    # Compaction
    "BaseCompactor",
    "CompactionOrchestrator",
    "CompactionStrategy",
    # Context
    "ContextTracker",
    # Models
    "ContextUsage",
    "ConversationTurn",
    "HandoffDocument",
    # Handoff
    "HandoffManager",
    "MemoryEntry",
    # Storage
    "MemoryStorage",
    "MemoryType",
    "Session",
    # Manager
    "SessionManager",
    "SessionMetadata",
    # Persistence
    "SessionPersister",
    "SlidingWindowCompactor",
    "Snapshot",
    "SummarizeCompactor",
    "TokenCounter",
    "TruncateCompactor",
    "TurnRole",
    "get_compactor",
    "get_session_manager",
    "reset_session_manager",
]
