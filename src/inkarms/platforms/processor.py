"""Platform-agnostic message processor.

This module bridges platform adapters to the core InkArms components
(ProviderManager, SessionManager, SkillManager, ToolRegistry) without platform-specific logic.
"""

import logging
from collections.abc import AsyncIterator
from typing import Callable, Optional

from inkarms.agent import AgentConfig, AgentEvent, AgentLoop, ApprovalMode
from inkarms.audit import get_audit_logger
from inkarms.config import get_config
from inkarms.memory import get_session_manager
from inkarms.platforms.models import PlatformType, StreamChunk
from inkarms.providers import (
    AllProvidersFailedError,
    AuthenticationError,
    CompletionResponse,
    Message,
    ProviderError,
    get_provider_manager,
)
from inkarms.security.sandbox import SandboxExecutor
from inkarms.skills import Skill, SkillManager, get_skill_manager
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ProcessedResponse:
    """Response from message processing."""

    def __init__(
        self,
        content: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        finish_reason: str,
        error: Optional[str] = None,
        tools_used: int = 0,
        iterations: int = 1,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost = cost
        self.finish_reason = finish_reason
        self.error = error
        self.tools_used = tools_used
        self.iterations = iterations


class MessageProcessor:
    """Platform-agnostic message processor.

    This class handles the core logic of processing user queries:
    1. Load skills
    2. Build message list with system prompt
    3. Call AgentLoop (with tools) or ProviderManager (without tools)
    4. Track in SessionManager
    5. Audit log with platform context
    6. Emit streaming events for tool execution
    """

    def __init__(
        self,
        skill_manager: Optional[SkillManager] = None,
        event_callback: Optional[Callable[[AgentEvent], None]] = None,
        tool_approval_callback: Optional[Callable] = None,
    ):
        """Initialize the message processor.

        Args:
            skill_manager: Optional skill manager (defaults to singleton)
            event_callback: Optional callback for streaming events (tool execution, etc.)
            tool_approval_callback: Optional callback for manual tool approval
        """
        self._skill_manager = skill_manager or get_skill_manager()
        self._config = get_config()
        self._audit_logger = get_audit_logger()
        self._event_callback = event_callback
        self._tool_approval_callback = tool_approval_callback

        # Initialize tool registry with built-in tools
        self._tool_registry: Optional[ToolRegistry] = None
        if self._config.agent.enable_tools:
            self._tool_registry = ToolRegistry()
            sandbox = SandboxExecutor.from_config(self._config.security)
            register_builtin_tools(self._tool_registry, sandbox)

    def _build_system_prompt(self, skills: list[Skill]) -> str:
        """Build system prompt with personality and skills.

        Args:
            skills: List of skills to inject

        Returns:
            Combined system prompt
        """
        parts = []

        # Add personality if configured
        if self._config.system_prompt.personality:
            parts.append(self._config.system_prompt.personality)

        # Add skill instructions
        if skills:
            parts.append("# Active Skills\n")
            for skill in skills:
                parts.append(skill.get_system_prompt_injection())
                parts.append("\n---\n")

        return "\n\n".join(parts) if parts else ""

    def _build_messages(
        self,
        query: str,
        skills: list[Skill],
        session_id: Optional[str] = None,
    ) -> list[Message]:
        """Build message list for completion.

        Args:
            query: User query
            skills: List of skills to inject
            session_id: Optional session ID for context

        Returns:
            List of messages ready for completion
        """
        messages: list[Message] = []

        # Build system prompt
        system_prompt = self._build_system_prompt(skills)
        if system_prompt:
            messages.append(Message.system(system_prompt))

        # Get session manager if tracking context
        session_manager = None
        if session_id:
            try:
                session_manager = get_session_manager(session_id=session_id)
                if system_prompt:
                    session_manager.set_system_prompt(system_prompt)
            except Exception as e:
                logger.error(f"Failed to get session manager: {e}")

        # Add user query
        messages.append(Message.user(query))
        if session_manager:
            try:
                session_manager.add_user_message(query)
            except Exception as e:
                logger.error(f"Failed to add user message to session: {e}")

        return messages

    async def process(
        self,
        query: str,
        session_id: Optional[str] = None,
        platform: PlatformType = PlatformType.CLI,
        platform_user_id: Optional[str] = None,
        platform_username: Optional[str] = None,
        model: Optional[str] = None,
        skill_names: Optional[list[str]] = None,
        auto_skills: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ProcessedResponse:
        """Process a message and return non-streaming response.

        When tools are enabled, uses AgentLoop for multi-turn tool execution
        with streaming events. When tools are disabled, uses direct ProviderManager.

        Args:
            query: User query
            session_id: Optional session ID for context tracking
            platform: Platform the message came from
            platform_user_id: Platform-specific user ID
            platform_username: Platform username/display name
            model: Model to use (None = default)
            skill_names: Explicit skill names to load
            auto_skills: Whether to auto-discover skills
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Returns:
            ProcessedResponse with completion result

        Raises:
            ProviderError: If completion fails
        """
        # Log incoming platform message
        if platform != PlatformType.CLI and platform_user_id:
            self._audit_logger.log_platform_message_received(
                platform=platform.value,
                user_id=platform_user_id,
                username=platform_username,
                message=query,
                session_id=session_id,
            )
        else:
            # Fall back to generic query logging for CLI
            self._audit_logger.log_query(query, platform=platform.value, session_id=session_id)

        # Load skills
        skills = await self._load_skills(query, skill_names, auto_skills)

        # Build messages
        messages = self._build_messages(query, skills, session_id)

        # Get provider manager
        try:
            manager = get_provider_manager()
        except Exception as e:
            logger.error(f"Failed to initialize provider: {e}")
            return ProcessedResponse(
                content="",
                model="",
                provider="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                finish_reason="error",
                error=f"Failed to initialize provider: {e}",
            )

        # If tools enabled, use AgentLoop for tool execution
        if self._config.agent.enable_tools and self._tool_registry:
            try:
                # Create agent config
                agent_config = AgentConfig(
                    approval_mode=ApprovalMode(self._config.agent.approval_mode),
                    max_iterations=self._config.agent.max_iterations,
                    timeout_per_iteration=self._config.agent.timeout_per_iteration,
                    enable_tools=True,
                    allowed_tools=self._config.agent.allowed_tools,
                    blocked_tools=self._config.agent.blocked_tools,
                )

                # Create agent loop with event streaming
                agent = AgentLoop(
                    provider_manager=manager,
                    tool_registry=self._tool_registry,
                    config=agent_config,
                    approval_callback=self._tool_approval_callback,
                    event_callback=self._event_callback,
                )

                # Convert to dict format for AgentLoop
                message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

                # Run agent loop
                result = await agent.run(message_dicts, model=model)

                # Get cost summary from provider manager
                summary = manager.get_cost_summary()

                # Track in session if enabled
                if session_id:
                    try:
                        session_manager = get_session_manager(session_id=session_id)
                        session_manager.add_assistant_message(
                            result.final_response,
                            model=summary.last_model if summary else model or "unknown",
                            cost=summary.total_cost if summary else 0.0,
                        )
                    except Exception as e:
                        logger.error(f"Failed to track response in session: {e}")

                # Log response
                total_tokens = summary.total_tokens if summary else 0
                if platform != PlatformType.CLI and platform_user_id:
                    self._audit_logger.log_platform_message_sent(
                        platform=platform.value,
                        user_id=platform_user_id,
                        response=result.final_response,
                        session_id=session_id,
                        tokens=total_tokens,
                        cost=summary.total_cost if summary else 0.0,
                    )
                else:
                    # Fall back to generic query logging for CLI
                    self._audit_logger.log_query(
                        result.final_response,
                        platform=platform.value,
                        session_id=session_id,
                        metadata={"type": "response"},
                    )

                return ProcessedResponse(
                    content=result.final_response,
                    model=summary.last_model if summary else model or "unknown",
                    provider=summary.last_provider if summary else "unknown",
                    input_tokens=summary.input_tokens if summary else 0,
                    output_tokens=summary.output_tokens if summary else 0,
                    cost=summary.total_cost if summary else 0.0,
                    finish_reason=result.stopped_reason,
                    error=result.error,
                    tools_used=len(result.tool_calls_made),
                    iterations=result.iterations,
                )

            except Exception as e:
                logger.error(f"Agent loop error: {e}", exc_info=True)
                return ProcessedResponse(
                    content="",
                    model="",
                    provider="",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.0,
                    finish_reason="error",
                    error=f"Agent loop error: {e}",
                )

        # Fallback: Use direct ProviderManager completion (no tools)
        try:
            response = await manager.complete(
                messages,
                model=model,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            assert isinstance(response, CompletionResponse)

            # Track in session if enabled
            if session_id:
                try:
                    session_manager = get_session_manager(session_id=session_id)
                    session_manager.add_assistant_message(
                        response.content,
                        model=response.model,
                        cost=response.cost,
                    )
                except Exception as e:
                    logger.error(f"Failed to track response in session: {e}")

            # Log response
            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            if platform != PlatformType.CLI and platform_user_id:
                self._audit_logger.log_platform_message_sent(
                    platform=platform.value,
                    user_id=platform_user_id,
                    response=response.content,
                    session_id=session_id,
                    tokens=total_tokens,
                    cost=response.cost,
                )
            else:
                # Fall back to generic query logging for CLI
                self._audit_logger.log_query(
                    response.content,
                    platform=platform.value,
                    session_id=session_id,
                    metadata={"type": "response"},
                )

            return ProcessedResponse(
                content=response.content,
                model=response.model,
                provider=response.provider,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cost=response.cost,
                finish_reason=response.finish_reason,
            )

        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            return ProcessedResponse(
                content="",
                model="",
                provider="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                finish_reason="error",
                error=f"Authentication failed: {e}",
            )

        except AllProvidersFailedError as e:
            logger.error(f"All providers failed: {e}")
            return ProcessedResponse(
                content="",
                model="",
                provider="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                finish_reason="error",
                error=f"All providers failed: {e}",
            )

        except ProviderError as e:
            logger.error(f"Provider error: {e}")
            return ProcessedResponse(
                content="",
                model="",
                provider="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                finish_reason="error",
                error=f"Provider error: {e}",
            )

    async def process_streaming(
        self,
        query: str,
        session_id: Optional[str] = None,
        platform: PlatformType = PlatformType.CLI,
        platform_user_id: Optional[str] = None,
        platform_username: Optional[str] = None,
        model: Optional[str] = None,
        skill_names: Optional[list[str]] = None,
        auto_skills: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Process a message and return streaming response.

        When tools are enabled, runs AgentLoop and yields final response.
        Tool execution events are streamed via event_callback (set during init).
        When tools are disabled, streams AI response chunks directly.

        Args:
            query: User query
            session_id: Optional session ID for context tracking
            platform: Platform the message came from
            platform_user_id: Platform-specific user ID
            platform_username: Platform username/display name
            model: Model to use (None = default)
            skill_names: Explicit skill names to load
            auto_skills: Whether to auto-discover skills
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response

        Yields:
            StreamChunk objects with response content

        Raises:
            ProviderError: If completion fails
        """
        # Log incoming platform message
        if platform != PlatformType.CLI and platform_user_id:
            self._audit_logger.log_platform_message_received(
                platform=platform.value,
                user_id=platform_user_id,
                username=platform_username,
                message=query,
                session_id=session_id,
            )
        else:
            # Fall back to generic query logging for CLI
            self._audit_logger.log_query(query, platform=platform.value, session_id=session_id)

        # Load skills
        skills = await self._load_skills(query, skill_names, auto_skills)

        # Build messages
        messages = self._build_messages(query, skills, session_id)

        # Get provider manager
        try:
            manager = get_provider_manager()
        except Exception as e:
            logger.error(f"Failed to initialize provider: {e}")
            yield StreamChunk(
                content=f"Error: Failed to initialize provider: {e}", is_final=True
            )
            return

        # If tools enabled, use AgentLoop (events streamed via callback)
        if self._config.agent.enable_tools and self._tool_registry:
            try:
                # Create agent config
                agent_config = AgentConfig(
                    approval_mode=ApprovalMode(self._config.agent.approval_mode),
                    max_iterations=self._config.agent.max_iterations,
                    timeout_per_iteration=self._config.agent.timeout_per_iteration,
                    enable_tools=True,
                    allowed_tools=self._config.agent.allowed_tools,
                    blocked_tools=self._config.agent.blocked_tools,
                )

                # Create agent loop with event streaming
                # Note: Tool execution events are streamed via self._event_callback
                agent = AgentLoop(
                    provider_manager=manager,
                    tool_registry=self._tool_registry,
                    config=agent_config,
                    approval_callback=self._tool_approval_callback,
                    event_callback=self._event_callback,
                )

                # Convert to dict format for AgentLoop
                message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

                # Run agent loop (tool events streamed via callback)
                result = await agent.run(message_dicts, model=model)

                # Yield final response
                yield StreamChunk(content=result.final_response, is_final=True)

                # Get cost summary
                summary = manager.get_cost_summary()

                # Track in session if enabled
                if session_id:
                    try:
                        session_manager = get_session_manager(session_id=session_id)
                        session_manager.add_assistant_message(
                            result.final_response,
                            model=summary.last_model if summary else model or "unknown",
                            cost=summary.total_cost if summary else 0.0,
                        )
                    except Exception as e:
                        logger.error(f"Failed to track response in session: {e}")

                # Log response
                total_tokens = summary.total_tokens if summary else 0
                if platform != PlatformType.CLI and platform_user_id:
                    self._audit_logger.log_platform_message_sent(
                        platform=platform.value,
                        user_id=platform_user_id,
                        response=result.final_response,
                        session_id=session_id,
                        tokens=total_tokens,
                        cost=summary.total_cost if summary else 0.0,
                    )
                else:
                    # Fall back to generic query logging for CLI
                    self._audit_logger.log_query(
                        result.final_response,
                        platform=platform.value,
                        session_id=session_id,
                        metadata={"type": "response"},
                    )

            except Exception as e:
                logger.error(f"Agent loop error: {e}", exc_info=True)
                yield StreamChunk(content=f"Error: Agent loop error: {e}", is_final=True)

            return

        # Fallback: Perform streaming completion (no tools)
        try:
            response_text = ""
            stream_response = await manager.complete(
                messages,
                model=model,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            async for chunk in stream_response:  # type: ignore
                response_text += chunk.content
                yield StreamChunk(content=response_text, is_final=False)

            # Final chunk
            yield StreamChunk(content=response_text, is_final=True)

            # Track in session if enabled
            if session_id:
                try:
                    session_manager = get_session_manager(session_id=session_id)
                    summary = manager.get_cost_summary()
                    resolved_model = manager._resolve_model(model)
                    session_manager.add_assistant_message(
                        response_text,
                        model=resolved_model,
                        cost=summary.total_cost,
                    )
                except Exception as e:
                    logger.error(f"Failed to track response in session: {e}")

            # Log response
            if platform != PlatformType.CLI and platform_user_id:
                # Get summary for tokens and cost
                summary = manager.get_cost_summary()
                total_tokens = summary.total_tokens if summary else 0
                total_cost = summary.total_cost if summary else 0.0
                self._audit_logger.log_platform_message_sent(
                    platform=platform.value,
                    user_id=platform_user_id,
                    response=response_text,
                    session_id=session_id,
                    tokens=total_tokens,
                    cost=total_cost,
                )
            else:
                # Fall back to generic query logging for CLI
                self._audit_logger.log_query(
                    response_text,
                    platform=platform.value,
                    session_id=session_id,
                    metadata={"type": "response"},
                )

        except AuthenticationError as e:
            logger.error(f"Authentication failed: {e}")
            yield StreamChunk(content=f"Error: Authentication failed: {e}", is_final=True)

        except AllProvidersFailedError as e:
            logger.error(f"All providers failed: {e}")
            yield StreamChunk(content=f"Error: All providers failed: {e}", is_final=True)

        except ProviderError as e:
            logger.error(f"Provider error: {e}")
            yield StreamChunk(content=f"Error: Provider error: {e}", is_final=True)

    async def _load_skills(
        self,
        query: str,
        skill_names: Optional[list[str]] = None,
        auto_skills: bool = False,
    ) -> list[Skill]:
        """Load skills for this query.

        Args:
            query: User query (for auto-discovery)
            skill_names: Explicit skill names to load
            auto_skills: Whether to auto-discover skills

        Returns:
            List of loaded skills
        """
        loaded_skills: list[Skill] = []

        # Explicit skill loading
        if skill_names:
            for skill_name in skill_names:
                try:
                    skill = self._skill_manager.get_skill(skill_name)
                    loaded_skills.append(skill)
                    logger.info(f"Loaded skill: {skill_name}")
                except Exception as e:
                    logger.warning(f"Failed to load skill {skill_name}: {e}")

        # Auto skill discovery
        if auto_skills and not skill_names:
            try:
                auto_discovered = self._skill_manager.get_skills_for_query(query, max_skills=3)
                if auto_discovered:
                    loaded_skills.extend(auto_discovered)
                    names = [s.name for s in auto_discovered]
                    logger.info(f"Auto-loaded skills: {', '.join(names)}")
            except Exception as e:
                logger.warning(f"Auto-skill discovery failed: {e}")

        return loaded_skills
