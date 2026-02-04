"""
Context compaction strategies for InkArms.

Provides different strategies for reducing context size when approaching limits.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from inkarms.memory.context import TokenCounter
from inkarms.memory.models import ConversationTurn, Session, TurnRole


class CompactionStrategy(str, Enum):
    """Available compaction strategies."""

    SUMMARIZE = "summarize"  # LLM-based summarization
    TRUNCATE = "truncate"  # Simple truncation of old messages
    SLIDING_WINDOW = "sliding_window"  # Keep recent messages, discard old


class BaseCompactor(ABC):
    """Base class for compaction strategies."""

    def __init__(self, preserve_recent: int = 5):
        """Initialize the compactor.

        Args:
            preserve_recent: Number of recent turns to always preserve.
        """
        self.preserve_recent = preserve_recent
        self.counter = TokenCounter()

    @abstractmethod
    async def compact(self, session: Session, target_tokens: int | None = None) -> Session:
        """Compact the session to reduce token usage.

        Args:
            session: Session to compact.
            target_tokens: Optional target token count.

        Returns:
            Compacted session.
        """
        pass

    def _split_turns(
        self, turns: list[ConversationTurn]
    ) -> tuple[list[ConversationTurn], list[ConversationTurn]]:
        """Split turns into compactable and preserved.

        Args:
            turns: All turns.

        Returns:
            Tuple of (compactable, preserved) turns.
        """
        if len(turns) <= self.preserve_recent:
            return [], turns

        split_point = len(turns) - self.preserve_recent
        return turns[:split_point], turns[split_point:]


class TruncateCompactor(BaseCompactor):
    """Simple truncation compactor.

    Removes oldest messages until target is reached.
    """

    async def compact(self, session: Session, target_tokens: int | None = None) -> Session:
        """Compact by truncating old messages.

        Args:
            session: Session to compact.
            target_tokens: Target token count (if None, removes half of compactable turns).

        Returns:
            Compacted session.
        """
        compactable, preserved = self._split_turns(session.turns)

        if not compactable:
            return session

        # If no target, remove half of compactable turns
        if target_tokens is None:
            keep_count = len(compactable) // 2
            remaining = compactable[-keep_count:] if keep_count > 0 else []
        else:
            # Calculate current tokens in preserved
            preserved_tokens = sum(t.token_count for t in preserved)
            system_tokens = self.counter.count(session.system_prompt or "")
            available = target_tokens - preserved_tokens - system_tokens

            # Keep as many old turns as fit
            remaining = []
            current = 0
            for turn in reversed(compactable):
                if current + turn.token_count <= available:
                    remaining.insert(0, turn)
                    current += turn.token_count
                else:
                    break

        # Create new session with compacted turns
        compacted = Session(
            metadata=session.metadata.model_copy(),
            system_prompt=session.system_prompt,
            turns=remaining + preserved,
        )

        # Update metadata
        compacted.metadata.total_tokens = sum(t.token_count for t in compacted.turns)

        return compacted


class SlidingWindowCompactor(BaseCompactor):
    """Sliding window compactor.

    Keeps only the most recent N turns.
    """

    def __init__(self, window_size: int = 20, preserve_recent: int = 5):
        """Initialize the sliding window compactor.

        Args:
            window_size: Total turns to keep in window.
            preserve_recent: Minimum recent turns to preserve.
        """
        super().__init__(preserve_recent)
        self.window_size = max(window_size, preserve_recent)

    async def compact(self, session: Session, target_tokens: int | None = None) -> Session:
        """Compact using sliding window.

        Args:
            session: Session to compact.
            target_tokens: Ignored for sliding window.

        Returns:
            Compacted session.
        """
        # Keep only the window_size most recent turns
        kept_turns = session.turns[-self.window_size :] if session.turns else []

        # Create new session
        compacted = Session(
            metadata=session.metadata.model_copy(),
            system_prompt=session.system_prompt,
            turns=kept_turns,
        )

        compacted.metadata.total_tokens = sum(t.token_count for t in compacted.turns)

        return compacted


class SummarizeCompactor(BaseCompactor):
    """LLM-based summarization compactor.

    Summarizes old conversation history into a condensed form.
    """

    SUMMARY_PROMPT = """Summarize the following conversation history concisely.
Focus on:
- Key decisions made
- Important context established
- Pending tasks or questions
- Technical details that may be needed later

Keep the summary under {max_tokens} tokens.

Conversation:
{conversation}

Summary:"""

    def __init__(
        self,
        preserve_recent: int = 5,
        summary_model: str | None = None,
        summary_max_tokens: int = 500,
    ):
        """Initialize the summarization compactor.

        Args:
            preserve_recent: Number of recent turns to preserve.
            summary_model: Model to use for summarization.
            summary_max_tokens: Max tokens for the summary.
        """
        super().__init__(preserve_recent)
        self.summary_model = summary_model
        self.summary_max_tokens = summary_max_tokens

    async def compact(self, session: Session, target_tokens: int | None = None) -> Session:
        """Compact by summarizing old messages.

        Args:
            session: Session to compact.
            target_tokens: Target token count.

        Returns:
            Compacted session.
        """
        compactable, preserved = self._split_turns(session.turns)

        if not compactable:
            return session

        # Format conversation for summarization
        conversation_text = self._format_conversation(compactable)

        # Generate summary using LLM
        summary = await self._generate_summary(conversation_text)

        # Create summary turn
        summary_turn = ConversationTurn(
            role=TurnRole.SYSTEM,
            content=f"[Previous conversation summary]\n{summary}",
            token_count=self.counter.count(summary),
            is_compacted=True,
            original_turn_ids=[t.id for t in compactable],
        )

        # Create new session with summary + preserved turns
        compacted = Session(
            metadata=session.metadata.model_copy(),
            system_prompt=session.system_prompt,
            turns=[summary_turn] + preserved,
        )

        compacted.metadata.total_tokens = sum(t.token_count for t in compacted.turns)

        return compacted

    def _format_conversation(self, turns: list[ConversationTurn]) -> str:
        """Format turns into text for summarization.

        Args:
            turns: Turns to format.

        Returns:
            Formatted conversation text.
        """
        lines = []
        for turn in turns:
            role = turn.role.upper() if isinstance(turn.role, str) else turn.role.value.upper()
            lines.append(f"{role}: {turn.content[:1000]}")  # Truncate very long messages
        return "\n\n".join(lines)

    async def _generate_summary(self, conversation: str) -> str:
        """Generate a summary using LLM.

        Args:
            conversation: Conversation text.

        Returns:
            Summary text.
        """
        # Try to use the provider manager if available
        try:
            from inkarms.providers import get_provider_manager, Message

            manager = get_provider_manager()

            prompt = self.SUMMARY_PROMPT.format(
                max_tokens=self.summary_max_tokens,
                conversation=conversation,
            )

            response = await manager.complete(
                [Message.user(prompt)],
                model=self.summary_model,
                stream=False,
                max_tokens=self.summary_max_tokens,
            )

            return response.content  # type: ignore

        except Exception:
            # Fallback to simple truncation if LLM not available
            return self._fallback_summary(conversation)

    def _fallback_summary(self, conversation: str) -> str:
        """Create a simple summary without LLM.

        Args:
            conversation: Conversation text.

        Returns:
            Simple summary.
        """
        # Just take the first part of the conversation as context
        lines = conversation.split("\n")
        summary_lines = []
        token_count = 0

        for line in lines:
            line_tokens = self.counter.count(line)
            if token_count + line_tokens > self.summary_max_tokens:
                break
            summary_lines.append(line)
            token_count += line_tokens

        return "\n".join(summary_lines) + "\n[... earlier context truncated ...]"


def get_compactor(
    strategy: CompactionStrategy | str,
    preserve_recent: int = 5,
    **kwargs: Any,
) -> BaseCompactor:
    """Get a compactor instance for the given strategy.

    Args:
        strategy: Compaction strategy.
        preserve_recent: Number of recent turns to preserve.
        **kwargs: Additional arguments for specific compactors.

    Returns:
        Compactor instance.

    Raises:
        ValueError: If strategy is unknown.
    """
    if isinstance(strategy, str):
        strategy = CompactionStrategy(strategy)

    if strategy == CompactionStrategy.TRUNCATE:
        return TruncateCompactor(preserve_recent=preserve_recent)
    elif strategy == CompactionStrategy.SLIDING_WINDOW:
        window_size = kwargs.get("window_size", 20)
        return SlidingWindowCompactor(
            window_size=window_size,
            preserve_recent=preserve_recent,
        )
    elif strategy == CompactionStrategy.SUMMARIZE:
        return SummarizeCompactor(
            preserve_recent=preserve_recent,
            summary_model=kwargs.get("summary_model"),
            summary_max_tokens=kwargs.get("summary_max_tokens", 500),
        )
    else:
        raise ValueError(f"Unknown compaction strategy: {strategy}")
