"""
Context tracking for InkArms.

Tracks token usage and context window consumption.
"""

from typing import Any

import tiktoken

from inkarms.config.providers import ENCODING_MAP, MODEL_CONTEXT_WINDOWS
from inkarms.memory.models import ContextUsage, ConversationTurn, Session, TurnRole


class TokenCounter:
    """Counts tokens for text using tiktoken.

    Provides token counting for context tracking.
    """

    def __init__(self, model: str | None = None):
        """Initialize the token counter.

        Args:
            model: Model name to determine encoding.
        """
        self.model = model
        self._encoding = self._get_encoding(model)

    def _get_encoding(self, model: str | None) -> tiktoken.Encoding:
        """Get the appropriate encoding for a model.

        Args:
            model: Model name.

        Returns:
            Tiktoken encoding.
        """
        encoding_name = ENCODING_MAP["default"]

        if model:
            # Determine provider from model name
            for provider, enc_name in ENCODING_MAP.items():
                if model.startswith(provider):
                    encoding_name = enc_name
                    break

        try:
            return tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fall back to cl100k_base
            return tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Text to count.

        Returns:
            Token count.
        """
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens in a list of messages.

        Args:
            messages: List of message dicts.

        Returns:
            Total token count.
        """
        total = 0
        for message in messages:
            # Add overhead for message structure
            total += 4  # Every message has overhead
            total += self.count(message.get("content", ""))
            if message.get("name"):
                total += self.count(message["name"])
        total += 2  # Priming tokens
        return total


class ContextTracker:
    """Tracks context window usage for a session.

    Monitors token usage and triggers compaction/handoff when needed.
    """

    def __init__(
        self,
        model: str = "default",
        compact_threshold: float = 0.70,
        handoff_threshold: float = 0.85,
    ):
        """Initialize the context tracker.

        Args:
            model: Model name for context window size.
            compact_threshold: Trigger compaction at this usage %.
            handoff_threshold: Trigger handoff at this usage %.
        """
        self.model = model
        self.counter = TokenCounter(model)
        self.max_tokens = self._get_context_window(model)

        self.usage = ContextUsage(
            current_tokens=0,
            max_tokens=self.max_tokens,
            compact_threshold=compact_threshold,
            handoff_threshold=handoff_threshold,
        )

        # Track system prompt separately
        self._system_prompt_tokens = 0

    def _get_context_window(self, model: str) -> int:
        """Get context window size for a model.

        Args:
            model: Model name.

        Returns:
            Context window size in tokens.
        """
        # Check exact match
        if model in MODEL_CONTEXT_WINDOWS:
            return MODEL_CONTEXT_WINDOWS[model]

        # Check prefix match
        for model_prefix, window in MODEL_CONTEXT_WINDOWS.items():
            if model.startswith(model_prefix.split("/")[0]):
                return window

        return MODEL_CONTEXT_WINDOWS["default"]

    def set_model(self, model: str) -> None:
        """Update the model and context window size.

        Args:
            model: New model name.
        """
        self.model = model
        self.max_tokens = self._get_context_window(model)
        self.usage.max_tokens = self.max_tokens
        self.counter = TokenCounter(model)

    def count_text(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Text to count.

        Returns:
            Token count.
        """
        return self.counter.count(text)

    def set_system_prompt(self, prompt: str | None) -> int:
        """Set and count the system prompt.

        Args:
            prompt: System prompt text.

        Returns:
            Token count of the prompt.
        """
        if prompt:
            self._system_prompt_tokens = self.counter.count(prompt)
        else:
            self._system_prompt_tokens = 0
        self._update_usage()
        return self._system_prompt_tokens

    def add_turn(self, turn: ConversationTurn) -> int:
        """Add a turn and update token count.

        Updates the turn's token_count if not already set.

        Args:
            turn: Conversation turn.

        Returns:
            Token count of the turn.
        """
        if turn.token_count == 0:
            turn.token_count = self.counter.count(turn.content)
        self._update_usage()
        return turn.token_count

    def track_session(self, session: Session) -> ContextUsage:
        """Track token usage for a session.

        Args:
            session: Session to track.

        Returns:
            Current context usage.
        """
        # Count system prompt
        if session.system_prompt:
            self._system_prompt_tokens = self.counter.count(session.system_prompt)
        else:
            self._system_prompt_tokens = 0

        # Count all turns
        for turn in session.turns:
            if turn.token_count == 0:
                turn.token_count = self.counter.count(turn.content)

        self._update_usage(session)
        return self.usage

    def _update_usage(self, session: Session | None = None) -> None:
        """Update the usage tracking.

        Args:
            session: Optional session to count turns from.
        """
        total = self._system_prompt_tokens

        if session:
            total += sum(t.token_count for t in session.turns)

        self.usage.current_tokens = total

    def get_usage(self) -> ContextUsage:
        """Get current context usage.

        Returns:
            Context usage info.
        """
        return self.usage

    def estimate_message_tokens(self, content: str, role: str = "user") -> int:
        """Estimate tokens for a message.

        Args:
            content: Message content.
            role: Message role.

        Returns:
            Estimated token count including overhead.
        """
        return self.counter.count(content) + 4  # Message overhead

    def can_fit(self, tokens: int) -> bool:
        """Check if additional tokens can fit.

        Args:
            tokens: Number of tokens to add.

        Returns:
            True if they fit within handoff threshold.
        """
        projected = self.usage.current_tokens + tokens
        projected_percent = projected / self.max_tokens
        return projected_percent < self.usage.handoff_threshold

    def tokens_until_compact(self) -> int:
        """Get tokens remaining until compaction threshold.

        Returns:
            Number of tokens until compaction is triggered.
        """
        compact_limit = int(self.max_tokens * self.usage.compact_threshold)
        return max(0, compact_limit - self.usage.current_tokens)

    def tokens_until_handoff(self) -> int:
        """Get tokens remaining until handoff threshold.

        Returns:
            Number of tokens until handoff is triggered.
        """
        handoff_limit = int(self.max_tokens * self.usage.handoff_threshold)
        return max(0, handoff_limit - self.usage.current_tokens)
