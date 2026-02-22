"""
Handoff system for InkArms.

Creates and recovers handoff documents for session continuity.
"""

import logging
from datetime import datetime

from inkarms.memory.context import TokenCounter
from inkarms.memory.storage import MemoryStorage
from inkarms.memory.summarization import format_conversation, generate_llm_summary
from inkarms.models.memory import (
    ConversationTurn,
    HandoffDocument,
    Session,
    TurnRole,
)

logger = logging.getLogger(__name__)


HANDOFF_SUMMARY_PROMPT = """Create a comprehensive handoff summary for continuing this conversation.
The summary should help a new AI assistant understand:

1. **Context**: What was the main topic/goal of this conversation?
2. **Progress**: What has been accomplished so far?
3. **Key Decisions**: What important decisions were made?
4. **Pending Tasks**: What still needs to be done?
5. **Technical Details**: Any important technical context?

Keep the summary concise but thorough (under 1000 words).

Conversation history:
{conversation}

Handoff Summary:"""


class HandoffManager:
    """Manages handoff creation and recovery.

    Provides functionality to:
    - Create handoff documents when context is full
    - Recover sessions from handoff documents
    - Archive used handoffs
    """

    def __init__(
        self,
        storage: MemoryStorage | None = None,
        include_full_context: bool = False,
    ):
        """Initialize the handoff manager.

        Args:
            storage: Memory storage instance.
            include_full_context: Whether to include full context in handoffs.
        """
        self.storage = storage or MemoryStorage()
        self.include_full_context = include_full_context
        self.counter = TokenCounter()

    async def create_handoff(
        self,
        session: Session,
        recent_turns_count: int = 10,
        summary_model: str | None = None,
    ) -> HandoffDocument:
        """Create a handoff document from a session.

        Args:
            session: Session to create handoff from.
            recent_turns_count: Number of recent turns to preserve.
            summary_model: Model to use for summarization.

        Returns:
            Created handoff document.
        """
        # Get recent turns to preserve
        recent_turns = session.get_recent_turns(recent_turns_count)

        # Generate summary
        summary = await self._generate_summary(session, summary_model)

        # Create handoff document
        # NOTE: key_decisions and pending_tasks intentionally left empty —
        # LLM-based extraction would require a separate API call with diminishing returns.
        handoff = HandoffDocument(
            session_id=session.id,
            summary=summary,
            key_decisions=[],
            pending_tasks=[],
            system_prompt=session.system_prompt,
            recent_turns=recent_turns,
            full_context=session if self.include_full_context else None,
            total_tokens_used=session.metadata.total_tokens,
            total_cost=session.metadata.total_cost,
            primary_model=session.metadata.primary_model,
        )

        # Save the handoff
        self.storage.save_handoff(handoff)

        return handoff

    async def _generate_summary(
        self,
        session: Session,
        model: str | None = None,
    ) -> str:
        """Generate a summary of the session.

        Args:
            session: Session to summarize.
            model: Model to use.

        Returns:
            Summary text.
        """
        # Use last 50 turns with a higher truncation limit for handoffs
        conversation = format_conversation(session.turns[-50:], max_content_length=2000)
        return await generate_llm_summary(
            conversation,
            prompt_template=HANDOFF_SUMMARY_PROMPT,
            model=model,
            max_tokens=1500,
        )

    def check_for_handoff(self) -> HandoffDocument | None:
        """Check if there's a pending handoff to recover.

        Returns:
            Handoff if found and not recovered, None otherwise.
        """
        handoff = self.storage.load_latest_handoff()

        if handoff and not handoff.recovered:
            return handoff

        return None

    async def recover_from_handoff(
        self,
        handoff: HandoffDocument | None = None,
        archive: bool = True,
    ) -> Session:
        """Recover a session from a handoff document.

        Args:
            handoff: Handoff to recover from. If None, uses latest.
            archive: Whether to archive the handoff after recovery.

        Returns:
            Recovered session.
        """
        if handoff is None:
            handoff = self.storage.load_latest_handoff()
            if handoff is None:
                raise ValueError("No handoff found to recover from")

        # Create new session
        session = Session()
        session.system_prompt = handoff.system_prompt

        # Add summary as context
        if handoff.summary:
            summary_turn = ConversationTurn(
                role=TurnRole.SYSTEM,
                content=f"[Previous session summary]\n{handoff.summary}",
                token_count=self.counter.count(handoff.summary),
                is_compacted=True,
            )
            session.add_turn(summary_turn)

        # Add recent turns
        for turn in handoff.recent_turns:
            session.add_turn(turn)

        # Mark handoff as recovered
        handoff.recovered = True
        handoff.recovered_at = datetime.now()

        if archive:
            self.storage.archive_handoff(handoff)
        else:
            self.storage.save_handoff(handoff)

        return session

