"""Platform-agnostic message processor.

This module bridges platform adapters to the core InkArms components
(ProviderManager, SessionManager, SkillManager, ToolRegistry) without platform-specific logic.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable

from pydantic import BaseModel

from inkarms.agent import AgentConfig, AgentEvent, AgentLoop, ApprovalMode, EventType
from inkarms.audit import get_audit_logger
from inkarms.config import get_config
from inkarms.memory import get_session_manager
from inkarms.models.platforms import PlatformType, StreamChunk
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


class ProcessedResponse(BaseModel):
    """Response from message processing."""

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost: float
    finish_reason: str
    error: str | None = None
    tools_used: int = 0
    iterations: int = 1


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
        skill_manager: SkillManager | None = None,
        event_callback: Callable[[AgentEvent], None] | None = None,
        tool_approval_callback: Callable | None = None,
    ):
        """Initialize the message processor.

        Args:
            skill_manager: Optional skill manager (defaults to singleton)
            event_callback: Optional callback for streaming events (tool execution, etc.)
            tool_approval_callback: Optional callback for manual tool approval
        """
        self._skill_manager = skill_manager or get_skill_manager()
        self._config = get_config()
        self._session_manager = get_session_manager(model=self._config.providers.default)
        self._audit_logger = get_audit_logger()
        self._event_callback = event_callback
        self._tool_approval_callback = tool_approval_callback

        # Initialize tool registry with built-in tools
        self._tool_registry: ToolRegistry | None = None
        if self._config.agent.enable_tools:
            self._tool_registry = ToolRegistry()
            sandbox = SandboxExecutor.from_config(self._config.security)
            register_builtin_tools(self._tool_registry, sandbox)

    def _build_system_prompt(self, skills: list[Skill]) -> str:
        """Build system prompt with personality and skills."""
        parts = []

        if self._config.system_prompt.personality:
            parts.append(self._config.system_prompt.personality)

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
        session_id: str | None = None,
    ) -> list[Message]:
        """Build message list for completion."""
        messages: list[Message] = []

        system_prompt = self._build_system_prompt(skills)
        if system_prompt:
            messages.append(Message.system(system_prompt))

        # Load prior conversation history for platform sessions
        if session_id and self._session_manager:
            try:
                for prior_msg in self._session_manager.get_messages(include_system=False):
                    messages.append(Message(role=prior_msg["role"], content=prior_msg["content"]))
            except Exception as e:
                logger.error(f"Failed to load session history: {e}")

        if session_id:
            try:
                if system_prompt:
                    self._session_manager.set_system_prompt(system_prompt)
            except Exception as e:
                logger.error(f"Failed to get session manager: {e}")

        messages.append(Message.user(query))
        if self._session_manager:
            try:
                self._session_manager.add_user_message(query)
            except Exception as e:
                logger.error(f"Failed to add user message to session: {e}")

        return messages

    def _make_error_response(self, error_msg: str) -> ProcessedResponse:
        """Create an error ProcessedResponse."""
        return ProcessedResponse(
            content="",
            model="",
            provider="",
            input_tokens=0,
            output_tokens=0,
            cost=0.0,
            finish_reason="error",
            error=error_msg,
        )

    def _log_incoming(
        self,
        query: str,
        platform: PlatformType,
        platform_user_id: str | None,
        platform_username: str | None,
        session_id: str | None,
    ) -> None:
        """Log an incoming platform message."""
        if platform != PlatformType.CLI and platform_user_id:
            self._audit_logger.log_platform_message_received(
                platform=platform.value,
                user_id=platform_user_id,
                username=platform_username,
                message=query,
                session_id=session_id,
            )
        else:
            self._audit_logger.log_query(query, platform=platform.value, session_id=session_id)

    def _log_outgoing(
        self,
        response_text: str,
        platform: PlatformType,
        platform_user_id: str | None,
        session_id: str | None,
        tokens: int,
        cost: float,
    ) -> None:
        """Log an outgoing platform response."""
        if platform != PlatformType.CLI and platform_user_id:
            self._audit_logger.log_platform_message_sent(
                platform=platform.value,
                user_id=platform_user_id,
                response=response_text,
                session_id=session_id,
                tokens=tokens,
                cost=cost,
            )
        else:
            self._audit_logger.log_query(
                response_text,
                platform=platform.value,
                session_id=session_id,
                metadata={"type": "response"},
            )

    def _track_response(
        self,
        session_id: str | None,
        text: str,
        model: str,
        cost: float,
    ) -> None:
        """Track assistant response in session manager."""
        if session_id:
            try:
                self._session_manager.add_assistant_message(text, model=model, cost=cost)
            except Exception as e:
                logger.error(f"Failed to track response in session: {e}")

    def _create_agent(self, manager) -> AgentLoop:
        """Create an AgentLoop with current config."""
        agent_config = AgentConfig(
            approval_mode=ApprovalMode(self._config.agent.approval_mode),
            max_iterations=self._config.agent.max_iterations,
            timeout_per_iteration=self._config.agent.timeout_per_iteration,
            enable_tools=True,
            allowed_tools=self._config.agent.allowed_tools,
            blocked_tools=self._config.agent.blocked_tools,
        )
        return AgentLoop(
            provider_manager=manager,
            tool_registry=self._tool_registry,
            config=agent_config,
            approval_callback=self._tool_approval_callback,
            event_callback=self._event_callback,
        )

    @staticmethod
    def _event_to_stream_chunk(event: AgentEvent) -> StreamChunk | None:
        """Convert an agent event to a progress stream chunk."""
        formatters = {
            EventType.TOOL_START: lambda e: f"Running tool: {e.tool_name}...",
            EventType.TOOL_COMPLETE: lambda e: f"Tool completed: {e.tool_name}",
            EventType.TOOL_ERROR: lambda e: f"Tool error: {e.tool_name}",
        }
        formatter = formatters.get(event.event_type)
        if not formatter:
            return None
        return StreamChunk(
            content=formatter(event),
            is_final=False,
            metadata={"event_type": event.event_type, "tool_name": event.tool_name},
        )

    async def _stream_agent_loop(
        self,
        manager,
        messages,
        model,
        session_id,
        platform,
        platform_user_id,
    ) -> AsyncIterator[StreamChunk]:
        """Run agent loop and yield progress chunks as events arrive."""
        try:
            event_queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

            def _queue_event(event: AgentEvent) -> None:
                event_queue.put_nowait(event)
                if self._event_callback:
                    self._event_callback(event)

            agent = self._create_agent(manager)
            agent.event_callback = _queue_event
            message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

            agent_task = asyncio.create_task(agent.run(message_dicts, model=model))

            while not agent_task.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    chunk = self._event_to_stream_chunk(event)
                    if chunk:
                        yield chunk
                except TimeoutError:
                    continue

            # Drain remaining events
            while not event_queue.empty():
                event = event_queue.get_nowait()
                chunk = self._event_to_stream_chunk(event)
                if chunk:
                    yield chunk

            result = agent_task.result()
            yield StreamChunk(content=result.final_response, is_final=True)

            summary = manager.get_cost_summary()
            self._track_response(
                session_id, result.final_response,
                self._session_manager.model or "unknown",
                summary.total_cost if summary else 0.0,
            )
            self._log_outgoing(
                result.final_response, platform, platform_user_id, session_id,
                self._session_total_tokens(),
                summary.total_cost if summary else 0.0,
            )
        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            yield StreamChunk(content=f"Error: Agent loop error: {e}", is_final=True)

    def _session_total_tokens(self) -> int:
        """Get total tokens from session metadata, or 0."""
        meta = self._session_manager.session.metadata
        return meta.total_tokens if meta else 0

    async def process(
        self,
        query: str,
        session_id: str | None = None,
        platform: PlatformType = PlatformType.CLI,
        platform_user_id: str | None = None,
        platform_username: str | None = None,
        model: str | None = None,
        skill_names: list[str] | None = None,
        auto_skills: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ProcessedResponse:
        """Process a message and return non-streaming response.

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
        """
        self._log_incoming(query, platform, platform_user_id, platform_username, session_id)

        skills = await self._load_skills(query, skill_names, auto_skills)
        messages = self._build_messages(query, skills, session_id)
        self._session_manager.set_model(model)

        try:
            manager = get_provider_manager()
        except Exception as e:
            logger.error(f"Failed to initialize provider: {e}")
            return self._make_error_response(f"Failed to initialize provider: {e}")

        # Agent loop path (tools enabled)
        if self._config.agent.enable_tools and self._tool_registry:
            try:
                agent = self._create_agent(manager)
                message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]
                result = await agent.run(message_dicts, model=model)
                summary = manager.get_cost_summary()

                self._track_response(
                    session_id, result.final_response,
                    self._session_manager.model or "unknown",
                    summary.total_cost if summary else 0.0,
                )
                self._log_outgoing(
                    result.final_response, platform, platform_user_id, session_id,
                    self._session_total_tokens(),
                    summary.total_cost if summary else 0.0,
                )

                return ProcessedResponse(
                    content=result.final_response,
                    model=model or "unknown",
                    provider=self._config.providers.default or "unknown",
                    input_tokens=summary.total_input_tokens if summary else 0,
                    output_tokens=summary.total_output_tokens if summary else 0,
                    cost=summary.total_cost if summary else 0.0,
                    finish_reason=result.stopped_reason,
                    error=result.error,
                    tools_used=len(result.tool_calls_made),
                    iterations=result.iterations,
                )
            except Exception as e:
                logger.error(f"Agent loop error: {e}", exc_info=True)
                return self._make_error_response(f"Agent loop error: {e}")

        # Direct provider path (no tools)
        try:
            response = await manager.complete(
                messages, model=model, stream=False,
                temperature=temperature, max_tokens=max_tokens,
            )
            assert isinstance(response, CompletionResponse)

            self._track_response(session_id, response.content, response.model, response.cost)

            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            self._log_outgoing(
                response.content, platform, platform_user_id, session_id,
                total_tokens, response.cost,
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
            return self._make_error_response(f"Authentication failed: {e}")
        except (AllProvidersFailedError, ProviderError) as e:
            logger.error(f"Provider error: {e}")
            return self._make_error_response(f"Provider error: {e}")

    async def process_streaming(
        self,
        query: str,
        session_id: str | None = None,
        platform: PlatformType = PlatformType.CLI,
        platform_user_id: str | None = None,
        platform_username: str | None = None,
        model: str | None = None,
        skill_names: list[str] | None = None,
        auto_skills: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Process a message and return streaming response.

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
        """
        self._log_incoming(query, platform, platform_user_id, platform_username, session_id)

        skills = await self._load_skills(query, skill_names, auto_skills)
        messages = self._build_messages(query, skills, session_id)
        self._session_manager.set_model(model)

        try:
            manager = get_provider_manager()
        except Exception as e:
            logger.error(f"Failed to initialize provider: {e}")
            yield StreamChunk(
                content=f"Error: Failed to initialize provider: {e}", is_final=True
            )
            return

        # Agent loop path (tools enabled)
        if self._config.agent.enable_tools and self._tool_registry:
            async for chunk in self._stream_agent_loop(
                manager, messages, model, session_id, platform, platform_user_id,
            ):
                yield chunk
            return

        # Direct streaming path (no tools)
        try:
            response_text = ""
            stream_response = await manager.complete(
                messages, model=model, stream=True,
                temperature=temperature, max_tokens=max_tokens,
            )

            async for chunk in stream_response:  # type: ignore
                response_text += chunk.content
                yield StreamChunk(content=response_text, is_final=False)

            yield StreamChunk(content=response_text, is_final=True)

            if session_id:
                try:
                    summary = manager.get_cost_summary()
                    resolved_model = manager.resolve_model(model)
                    self._session_manager.add_assistant_message(
                        response_text, model=resolved_model, cost=summary.total_cost,
                    )
                except Exception as e:
                    logger.error(f"Failed to track response in session: {e}")

            summary = manager.get_cost_summary()
            self._log_outgoing(
                response_text, platform, platform_user_id, session_id,
                self._session_total_tokens(),
                summary.total_cost if summary else 0.0,
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
        skill_names: list[str] | None = None,
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
