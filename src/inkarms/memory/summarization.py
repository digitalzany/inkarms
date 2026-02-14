"""
Shared summarization utilities for the memory module.

Extracts common conversation formatting and summary generation logic
used by both compaction and handoff systems.
"""

import logging

from inkarms.memory.context import TokenCounter
from inkarms.models.memory import ConversationTurn

logger = logging.getLogger(__name__)

# Default truncation limit for individual message content
DEFAULT_CONTENT_TRUNCATION = 1000


def format_conversation(
    turns: list[ConversationTurn],
    max_content_length: int = DEFAULT_CONTENT_TRUNCATION,
) -> str:
    """Format conversation turns into text for summarization.

    Args:
        turns: Turns to format.
        max_content_length: Maximum characters per message content.

    Returns:
        Formatted conversation text.
    """
    lines = []
    for turn in turns:
        role = turn.role.upper() if isinstance(turn.role, str) else turn.role.value.upper()
        lines.append(f"{role}: {turn.content[:max_content_length]}")
    return "\n\n".join(lines)


def fallback_summary(
    conversation: str,
    max_tokens: int,
    counter: TokenCounter | None = None,
) -> str:
    """Create a simple summary without LLM by truncating to fit token budget.

    Args:
        conversation: Formatted conversation text.
        max_tokens: Maximum tokens for the summary.
        counter: Token counter instance. Creates one if not provided.

    Returns:
        Truncated summary text.
    """
    if counter is None:
        counter = TokenCounter()

    lines = conversation.split("\n")
    summary_lines = []
    token_count = 0

    for line in lines:
        line_tokens = counter.count(line)
        if token_count + line_tokens > max_tokens:
            break
        summary_lines.append(line)
        token_count += line_tokens

    return "\n".join(summary_lines) + "\n[... earlier context truncated ...]"


async def generate_llm_summary(
    conversation: str,
    prompt_template: str,
    model: str | None = None,
    max_tokens: int = 500,
) -> str:
    """Generate a summary using an LLM provider.

    Falls back to simple truncation if the LLM is unavailable.

    Args:
        conversation: Formatted conversation text.
        prompt_template: Prompt template with {conversation} and optionally {max_tokens} placeholders.
        model: Model to use for summarization.
        max_tokens: Maximum tokens for the summary.

    Returns:
        Summary text.
    """
    try:
        from inkarms.providers import Message, get_provider_manager

        manager = get_provider_manager()

        prompt = prompt_template.format(
            conversation=conversation,
            max_tokens=max_tokens,
        )

        response = await manager.complete(
            [Message.user(prompt)],
            model=model,
            stream=False,
            max_tokens=max_tokens,
        )

        return response.content  # type: ignore

    except Exception:
        logger.warning("LLM summarization failed, using fallback", exc_info=True)
        return fallback_summary(conversation, max_tokens)
