"""Query processing for the Rich backend.

Handles streaming, agent, and synchronous query execution,
consolidating asyncio event-loop management and cost tracking.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import logging
import re
import threading
import traceback
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from inkarms.ui.protocol import StatusInfo

logger = logging.getLogger(__name__)


class QueryProcessor:
    """Handles query execution: streaming, agent, and synchronous modes.

    Consolidates asyncio event-loop management and cost tracking
    that was previously duplicated across three methods in RichBackend.
    """

    def __init__(
        self,
        provider_manager,
        session_manager,
        status: StatusInfo,
        agent_config=None,
        tool_registry=None,
        on_status_update: Callable[[], None] | None = None,
    ):
        self._provider = provider_manager
        self._session = session_manager
        self._status = status
        self._agent_config = agent_config
        self._tool_registry = tool_registry
        self._on_status_update = on_status_update

    # --- Public methods ---

    def process_streaming(
        self,
        query: str,
        on_chunk: Callable[[str], None],
        on_complete: Callable[[str], None],
        on_error: Callable[[str], None],
    ) -> threading.Thread:
        """Process query with streaming callbacks."""
        query = expand_file_references(query)

        if not self._provider:
            on_complete("Provider not configured")
            return threading.Thread()  # no-op

        self._track_user_message(query)
        messages = self._build_messages(query)
        cost_before = self._get_cost_before()

        async def run(loop: asyncio.AbstractEventLoop) -> str:
            full_content = ""
            try:
                stream = await self._provider.complete(
                    messages=messages,
                    model=self._status.model,
                    stream=True,
                )
                async for chunk in stream:
                    full_content += chunk.content
                    on_chunk(chunk.content)
                return full_content
            except Exception as e:
                traceback.print_exc()
                raise e

        def on_success(result: str) -> None:
            self._track_response(result, cost_before)
            on_complete(result)

        return self._run_in_thread(run, on_success, on_error)

    def process_agent(
        self,
        query: str,
        event_callback: Callable,
        approval_callback: Callable,
        on_complete: Callable,
        on_error: Callable[[str], None],
        *,
        on_chunk: Callable[[str], None] | None = None,
    ) -> threading.Thread:
        """Process query through agent loop with tool use."""
        query = expand_file_references(query)

        if not self._provider or not self._tool_registry or not self._agent_config:
            on_error("Agent not configured")
            return threading.Thread()  # no-op

        self._track_user_message(query)
        messages = self._build_messages(query)
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        cost_before = self._get_cost_before()

        async def run(loop: asyncio.AbstractEventLoop) -> Any:
            from inkarms.agent.loop import AgentLoop

            agent_loop = AgentLoop(
                provider_manager=self._provider,
                tool_registry=self._tool_registry,
                config=self._agent_config,
                approval_callback=approval_callback,
                event_callback=event_callback,
                stream_callback=on_chunk,
            )
            return await agent_loop.run(msg_dicts, model=self._status.model)

        def on_success(result: Any) -> None:
            self._track_response(result.final_response, cost_before)
            on_complete(result)

        return self._run_in_thread(run, on_success, on_error)

    def process_sync(self, query: str) -> str:
        """Process a user query synchronously (non-streaming fallback)."""
        query = expand_file_references(query)
        self._track_user_message(query)

        if not self._provider:
            return "I understand. Let me help you with that. (Note: Provider not configured)"

        try:
            messages = self._build_messages(query)

            def run_async():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                loop = asyncio.new_event_loop()
                loop.set_exception_handler(lambda lp, ctx: None)
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(
                        self._provider.complete(
                            messages=messages,
                            model=self._status.model,
                        )
                    )
                finally:
                    with contextlib.suppress(Exception):
                        loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_async)
                response = future.result()

            # Track assistant message
            if self._session:
                try:
                    self._session.add_assistant_message(
                        response.content,
                        model=response.model,
                        cost=response.cost or 0,
                    )
                    if self._on_status_update:
                        self._on_status_update()
                except Exception as e:
                    logger.debug(f"Failed to track assistant message: {e}")
            else:
                if response.usage:
                    self._status.total_tokens += response.usage.total_tokens
                self._status.total_cost += response.cost or 0

            return response.content

        except Exception as e:
            logger.error(f"Provider error: {e}")
            return f"Error: {e}"

    # --- Private helpers ---

    def _run_in_thread(
        self,
        async_fn: Callable[[asyncio.AbstractEventLoop], Coroutine],
        on_success: Callable,
        on_error: Callable[[str], None],
    ) -> threading.Thread:
        """Run an async function in a daemon thread with proper loop lifecycle."""
        def run():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            loop = asyncio.new_event_loop()
            loop.set_exception_handler(lambda lp, ctx: None)
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(async_fn(loop))
                on_success(result)
            except Exception as e:
                on_error(str(e))
            finally:
                with contextlib.suppress(Exception):
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                with contextlib.suppress(Exception):
                    loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

    def _track_user_message(self, query: str) -> None:
        """Track user message in session manager."""
        if self._session:
            try:
                self._session.add_user_message(query)
            except Exception as e:
                logger.debug(f"Failed to track user message: {e}")

    def _get_cost_before(self) -> float:
        """Snapshot current cost for delta calculation."""
        if self._provider:
            with contextlib.suppress(Exception):
                return self._provider.get_cost_summary().total_cost
        return 0.0

    def _track_response(self, content: str, cost_before: float) -> None:
        """Track an assistant response in session manager with cost delta."""
        if not self._session:
            return
        try:
            cost_delta = 0.0
            if self._provider:
                cost_after = self._provider.get_cost_summary().total_cost
                cost_delta = cost_after - cost_before
            self._session.add_assistant_message(
                content,
                model=self._status.model,
                cost=cost_delta,
            )
            if self._on_status_update:
                self._on_status_update()
        except Exception as e:
            logger.debug(f"Failed to track assistant message: {e}")

    def _build_messages(self, query: str):
        """Build messages list for the provider."""
        from inkarms.models.providers import Message

        if self._session:
            return [
                Message(role=msg_dict["role"], content=msg_dict["content"])
                for msg_dict in self._session.get_messages(include_system=True)
            ]

        return [Message.user(query)]


def expand_file_references(text: str) -> str:
    """Expand @path references to file contents."""
    pattern = r"@([^\s]+)"

    def replace(m):
        path = Path(m.group(1)).expanduser()
        if path.exists() and path.is_file():
            try:
                content = path.read_text()[:2000]
                return f"\n[File: {m.group(1)}]\n{content}\n[End file]\n"
            except Exception:
                pass
        return m.group(0)

    return re.sub(pattern, replace, text)
