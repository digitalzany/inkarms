"""Context building logic for message processing."""

import logging

from inkarms.config import Config
from inkarms.memory.manager import SessionManager
from inkarms.providers.manager import Message
from inkarms.skills import Skill

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Builds conversation context including system prompts and history."""

    def __init__(self, config: Config):
        """Initialize builder.

        Args:
            config: Global configuration.
        """
        self.config = config

    def build_system_prompt(self, skills: list[Skill]) -> str:
        """Build system prompt with personality and skills."""
        parts = []

        if self.config.system_prompt.personality:
            parts.append(self.config.system_prompt.personality)

        if skills:
            parts.append("# Active Skills\n")
            for skill in skills:
                parts.append(skill.get_system_prompt_injection())
                parts.append("\n---\n")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        query: str,
        skills: list[Skill],
        session_id: str | None = None,
        session_manager: SessionManager | None = None,
    ) -> list[Message]:
        """Build message list for completion."""
        messages: list[Message] = []

        system_prompt = self.build_system_prompt(skills)
        if system_prompt:
            messages.append(Message.system(system_prompt))

        # Load prior conversation history
        if session_id and session_manager:
            try:
                for prior_msg in session_manager.get_messages(include_system=False):
                    messages.append(Message(
                        role=prior_msg["role"],
                        content=prior_msg["content"],
                        reasoning_content=prior_msg.get("reasoning_content"),
                    ))
            except Exception as e:
                logger.error(f"Failed to load session history: {e}")

        if session_id and session_manager:
            try:
                if system_prompt:
                    session_manager.set_system_prompt(system_prompt)
            except Exception as e:
                logger.error(f"Failed to set system prompt: {e}")

        messages.append(Message.user(query))

        if session_manager:
            try:
                session_manager.add_user_message(query)
            except Exception as e:
                logger.error(f"Failed to add user message to session: {e}")

        return messages
