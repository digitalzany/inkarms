"""
Cost tracking for InkArms provider layer.

Tracks token usage and costs across sessions and models.
"""

import logging
from typing import Any

from inkarms.providers.models import (
    CostEstimate,
    Message,
    SessionCostSummary,
    SessionUsage,
    TokenUsage,
)

logger = logging.getLogger(__name__)


class CostTracker:
    """
    Tracks token usage and costs for the session.

    Uses LiteLLM's built-in token counting and cost calculation.
    """

    def __init__(self) -> None:
        """Initialize the cost tracker."""
        self.session_usage: dict[str, SessionUsage] = {}
        self._total_requests = 0

    def estimate_cost(
        self,
        model: str,
        messages: list[Message],
        max_output_tokens: int = 1000,
    ) -> CostEstimate:
        """
        Estimate cost before making a request.

        Args:
            model: The model to use.
            messages: Input messages.
            max_output_tokens: Expected maximum output tokens.

        Returns:
            Cost estimate with input/output breakdown.
        """
        try:
            from litellm import completion_cost, token_counter

            # Count input tokens
            litellm_messages = [msg.to_dict() for msg in messages]
            input_tokens = token_counter(model=model, messages=litellm_messages)

            # Estimate costs using LiteLLM's cost calculation
            # Note: completion_cost expects either a response or explicit token counts
            input_cost = self._calculate_input_cost(model, input_tokens)
            output_cost = self._calculate_output_cost(model, max_output_tokens)

            return CostEstimate(
                model=model,
                input_tokens=input_tokens,
                estimated_output_tokens=max_output_tokens,
                input_cost=input_cost,
                estimated_output_cost=output_cost,
                total_estimated=input_cost + output_cost,
            )

        except Exception as e:
            logger.warning(f"Could not estimate cost: {e}")
            # Return zero estimate on failure
            return CostEstimate(
                model=model,
                input_tokens=0,
                estimated_output_tokens=max_output_tokens,
                input_cost=0.0,
                estimated_output_cost=0.0,
                total_estimated=0.0,
            )

    def _calculate_input_cost(self, model: str, input_tokens: int) -> float:
        """Calculate input token cost."""
        try:
            from litellm import completion_cost

            # LiteLLM can calculate cost from token counts
            return completion_cost(
                model=model,
                prompt=str(input_tokens),  # Just need token count
                completion="",
            )
        except Exception:
            return 0.0

    def _calculate_output_cost(self, model: str, output_tokens: int) -> float:
        """Calculate output token cost."""
        try:
            from litellm import completion_cost

            return completion_cost(
                model=model,
                prompt="",
                completion=str(output_tokens),
            )
        except Exception:
            return 0.0

    def record_usage(
        self,
        model: str,
        usage: TokenUsage,
        cost: float,
    ) -> None:
        """
        Record actual usage after completion.

        Args:
            model: The model that was used.
            usage: Token usage from the response.
            cost: Calculated cost.
        """
        if model not in self.session_usage:
            self.session_usage[model] = SessionUsage(model=model)

        self.session_usage[model].add(usage, cost)
        self._total_requests += 1

        logger.debug(
            f"Recorded usage for {model}: "
            f"{usage.input_tokens} in, {usage.output_tokens} out, ${cost:.6f}"
        )

    def calculate_response_cost(self, response: Any, model: str) -> float:
        """
        Calculate cost from a LiteLLM response.

        Args:
            response: The LiteLLM completion response.
            model: The model used.

        Returns:
            The calculated cost in USD.
        """
        try:
            from litellm import completion_cost

            return completion_cost(completion_response=response)
        except Exception as e:
            logger.warning(f"Could not calculate cost: {e}")
            return 0.0

    def get_session_summary(self) -> SessionCostSummary:
        """
        Get cost summary for current session.

        Returns:
            Summary with totals and per-model breakdown.
        """
        total_input = sum(u.input_tokens for u in self.session_usage.values())
        total_output = sum(u.output_tokens for u in self.session_usage.values())
        total_cost = sum(u.total_cost for u in self.session_usage.values())

        return SessionCostSummary(
            by_model=dict(self.session_usage),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_cost=total_cost,
        )

    def get_model_usage(self, model: str) -> SessionUsage | None:
        """
        Get usage for a specific model.

        Args:
            model: The model to get usage for.

        Returns:
            Usage for the model, or None if not used.
        """
        return self.session_usage.get(model)

    @property
    def total_cost(self) -> float:
        """Total cost for the session."""
        return sum(u.total_cost for u in self.session_usage.values())

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output) for the session."""
        return sum(u.input_tokens + u.output_tokens for u in self.session_usage.values())

    @property
    def total_requests(self) -> int:
        """Total number of requests in the session."""
        return self._total_requests

    def reset(self) -> None:
        """Reset session tracking."""
        self.session_usage.clear()
        self._total_requests = 0


def count_tokens(model: str, messages: list[Message]) -> int:
    """
    Count tokens for messages using LiteLLM.

    Args:
        model: The model to count tokens for.
        messages: The messages to count.

    Returns:
        Token count.
    """
    try:
        from litellm import token_counter

        litellm_messages = [msg.to_dict() for msg in messages]
        return token_counter(model=model, messages=litellm_messages)
    except Exception as e:
        logger.warning(f"Could not count tokens: {e}")
        # Rough estimate: ~4 chars per token
        total_chars = sum(len(msg.content) for msg in messages)
        return total_chars // 4


def count_text_tokens(model: str, text: str) -> int:
    """
    Count tokens for plain text.

    Args:
        model: The model to count tokens for.
        text: The text to count.

    Returns:
        Token count.
    """
    try:
        from litellm import token_counter

        return token_counter(model=model, text=text)
    except Exception as e:
        logger.warning(f"Could not count tokens: {e}")
        # Rough estimate: ~4 chars per token
        return len(text) // 4
