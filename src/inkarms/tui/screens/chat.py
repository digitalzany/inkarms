"""
Chat interface screen for InkArms TUI.

Provides an interactive chat experience with the AI assistant.
"""

from datetime import datetime

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from inkarms.agent import AgentConfig, AgentEvent, AgentLoop, ApprovalMode, EventType
from inkarms.config import get_config
from inkarms.memory import get_session_manager
from inkarms.providers import get_provider_manager
from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.registry import ToolRegistry


class MessageBubble(Static):
    """A message bubble widget for displaying chat messages."""

    DEFAULT_CSS = """
    MessageBubble {
        width: 100%;
        height: auto;
        padding: 1 2;
        margin: 1 0;
    }

    MessageBubble.user-message {
        background: $primary-darken-2;
        border-left: thick $primary;
        color: $text;
    }

    MessageBubble.ai-message {
        background: $surface-darken-1;
        border-left: thick $accent;
        color: $text;
    }

    MessageBubble.system-message {
        background: $panel;
        border-left: thick $warning;
        color: $text-muted;
        text-style: italic;
    }

    .message-header {
        text-style: bold;
        margin-bottom: 1;
    }

    .message-timestamp {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        **kwargs
    ):
        """Initialize message bubble.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
            timestamp: Message timestamp
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()

        # Set CSS class based on role
        if role == "user":
            self.add_class("user-message")
        elif role == "assistant":
            self.add_class("ai-message")
        else:
            self.add_class("system-message")

    def compose(self) -> ComposeResult:
        """Compose the message bubble."""
        # Header with role and timestamp
        role_label = {
            "user": "You",
            "assistant": "AI",
            "system": "System"
        }.get(self.role, self.role.title())

        timestamp_str = self.timestamp.strftime("%H:%M:%S")

        yield Label(
            f"{role_label} · {timestamp_str}",
            classes="message-header"
        )

        # Message content (with markdown support)
        from textual.widgets import Markdown
        yield Markdown(self.content)


class ToolExecutionIndicator(Static):
    """Widget to show tool execution in progress."""

    DEFAULT_CSS = """
    ToolExecutionIndicator {
        width: 100%;
        height: auto;
        padding: 1 2;
        margin: 1 0;
        background: $warning-darken-2;
        border-left: thick $warning;
    }

    .tool-spinner {
        text-style: bold;
        color: $warning;
    }
    """

    def __init__(self, tool_name: str, **kwargs):
        """Initialize tool execution indicator.

        Args:
            tool_name: Name of the tool being executed
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.tool_name = tool_name

    def compose(self) -> ComposeResult:
        """Compose the tool indicator."""
        yield Label(f"⚙️  Executing: {self.tool_name}...", classes="tool-spinner")


class SessionInfoPanel(Static):
    """Panel showing session information."""

    DEFAULT_CSS = """
    SessionInfoPanel {
        width: 100%;
        height: auto;
        background: $panel;
        border: tall $primary;
        padding: 1;
    }

    .info-label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }

    .info-value {
        color: $text;
    }
    """

    def __init__(self, **kwargs):
        """Initialize session info panel."""
        super().__init__(**kwargs)
        self.model = "Not set"
        self.tokens_used = 0
        self.cost = 0.0
        self.session_id = "default"

    def compose(self) -> ComposeResult:
        """Compose the session info panel."""
        yield Label("📊 Session Info", classes="info-label")
        yield Label(f"Model: {self.model}", id="model-info", classes="info-value")
        yield Label(f"Tokens: {self.tokens_used}", id="tokens-info", classes="info-value")
        yield Label(f"Cost: ${self.cost:.4f}", id="cost-info", classes="info-value")
        yield Label(f"Session: {self.session_id}", id="session-info", classes="info-value")

    def update_info(
        self,
        model: str | None = None,
        tokens: int | None = None,
        cost: float | None = None,
        session_id: str | None = None
    ) -> None:
        """Update session information.

        Args:
            model: Model name
            tokens: Token count
            cost: Total cost
            session_id: Session ID
        """
        if model:
            self.model = model
            self.query_one("#model-info", Label).update(f"Model: {model}")

        if tokens is not None:
            self.tokens_used = tokens
            self.query_one("#tokens-info", Label).update(f"Tokens: {tokens}")

        if cost is not None:
            self.cost = cost
            self.query_one("#cost-info", Label).update(f"Cost: ${cost:.4f}")

        if session_id:
            self.session_id = session_id
            self.query_one("#session-info", Label).update(f"Session: {session_id}")


class ChatScreen(Screen):
    """Main chat interface screen."""

    CSS = """
    ChatScreen {
        layout: grid;
        grid-size: 4 12;
        grid-columns: 3fr 1fr;
    }

    #chat-container {
        column-span: 3;
        row-span: 12;
        border: thick $primary;
        background: $surface;
    }

    #sidebar-container {
        column-span: 1;
        row-span: 12;
        border: thick $primary;
        background: $surface;
    }

    #messages-area {
        height: 1fr;
        border: tall $primary-darken-2;
        background: $surface-darken-1;
    }

    #input-area {
        height: auto;
        border: tall $primary;
        padding: 1;
        background: $panel;
    }

    #message-input {
        width: 100%;
    }

    #send-button {
        margin-top: 1;
    }

    #controls {
        height: auto;
        padding: 1;
        background: $panel;
    }

    Button {
        margin: 1;
        width: 100%;
    }
    """

    def __init__(self, session_id: str = "default"):
        """Initialize chat screen.

        Args:
            session_id: Session ID for conversation tracking
        """
        super().__init__()
        self.session_id = session_id
        self.messages: list[dict] = []
        self.current_tool_indicator: ToolExecutionIndicator | None = None
        self.streaming_message: MessageBubble | None = None

        # Initialize agent components
        self.config = get_config()
        self.provider = get_provider_manager()
        self.session_manager = get_session_manager(model=self.config.providers.default)

        # Setup tools
        self.tool_registry: ToolRegistry | None = None
        if self.config.agent.enable_tools:
            self.tool_registry = ToolRegistry()
            sandbox = SandboxExecutor.from_config(self.config.security)
            register_builtin_tools(self.tool_registry, sandbox)

    def compose(self) -> ComposeResult:
        """Compose the chat screen layout."""
        yield Header(show_clock=True)

        # Main chat area
        with Container(id="chat-container"):
            with VerticalScroll(id="messages-area"):
                # Welcome message
                yield MessageBubble(
                    role="system",
                    content="Welcome to InkArms! Type your message below to start chatting.",
                )

            with Container(id="input-area"):
                yield Input(
                    placeholder="Type your message here... (Ctrl+Enter to send)",
                    id="message-input"
                )
                yield Button("Send", id="send-button", variant="primary")

        # Sidebar
        with Vertical(id="sidebar-container"):
            yield SessionInfoPanel(id="session-info")

            with Container(id="controls"):
                yield Label("Controls:")
                yield Button("Clear Chat", id="clear-button")
                yield Button("Exit", id="exit-button", variant="error")

        yield Footer()

    def on_mount(self) -> None:
        """Mount event - initialize session info."""
        session_info = self.query_one("#session-info", SessionInfoPanel)
        session_info.update_info(
            model=self.config.providers.default,
            session_id=self.session_id
        )

        # Focus on input
        self.query_one("#message-input", Input).focus()

    @on(Button.Pressed, "#send-button")
    def on_send_button(self) -> None:
        """Handle send button press."""
        self._send_message()

    @on(Input.Submitted, "#message-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission (Enter key)."""
        self._send_message()

    def _send_message(self) -> None:
        """Send the current message."""
        message_input = self.query_one("#message-input", Input)
        message_text = message_input.value.strip()

        if not message_text:
            return

        # Clear input
        message_input.value = ""

        # Add user message to display
        messages_area = self.query_one("#messages-area", VerticalScroll)
        user_bubble = MessageBubble(role="user", content=message_text)
        messages_area.mount(user_bubble)

        # Scroll to bottom
        messages_area.scroll_end(animate=False)

        # Add to messages history
        self.messages.append({"role": "user", "content": message_text})

        # Process message with AI (in background)
        self._process_ai_response(message_text)

    def _update_streaming_message(self, bubble: MessageBubble, content: str) -> None:
        """Update a message bubble with streaming content.

        Args:
            bubble: The message bubble to update
            content: The accumulated content so far
        """
        from textual.widgets import Markdown

        # Remove existing content
        self.app.call_from_thread(bubble.remove_children)

        # Add header
        self.app.call_from_thread(
            bubble.mount,
            Label("AI · " + datetime.now().strftime("%H:%M:%S"), classes="message-header")
        )

        # Add streaming content with markdown
        # Add a cursor indicator to show it's still streaming
        streaming_content = content + " ▋"
        self.app.call_from_thread(bubble.mount, Markdown(streaming_content))

    @work(exclusive=True, thread=True)
    def _process_ai_response(self, user_message: str) -> None:
        """Process AI response in background.

        Args:
            user_message: User's message
        """
        import asyncio

        # Run async AI processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._async_process_response(user_message))
        finally:
            loop.close()

    async def _async_process_response(self, user_message: str) -> None:
        """Async AI response processing.

        Args:
            user_message: User's message
        """
        messages_area = self.query_one("#messages-area", VerticalScroll)

        # Create AI message placeholder for streaming
        ai_bubble = MessageBubble(role="assistant", content="...")
        self.streaming_message = ai_bubble
        self.app.call_from_thread(messages_area.mount, ai_bubble)
        self.app.call_from_thread(messages_area.scroll_end, animate=False)

        try:
            if self.config.agent.enable_tools and self.tool_registry:
                # Use agent loop with tools (non-streaming for now)
                result = await self._run_with_tools(user_message)
                final_response = result.final_response

                # Update session info with tool usage
                session_info = self.query_one("#session-info", SessionInfoPanel)
                summary = self.provider.get_cost_summary()
                self.app.call_from_thread(
                    session_info.update_info,
                    tokens=(summary.total_input_tokens + summary.total_output_tokens) if summary else 0,
                    cost=summary.total_cost if summary else 0.0
                )
            else:
                # Direct provider completion with streaming
                from inkarms.providers import Message

                provider_messages = [Message(role="user", content=user_message)]

                # Use streaming for better UX
                final_response = ""
                accumulated_text = ""

                async for chunk in self.provider.complete(
                    provider_messages,
                    model=self.config.providers.default,
                    stream=True
                ):
                    # Accumulate text
                    accumulated_text += chunk.content

                    # Update message display incrementally
                    self._update_streaming_message(ai_bubble, accumulated_text)

                    # Scroll to bottom periodically (every ~10 chunks to avoid too much overhead)
                    if len(accumulated_text) % 50 < len(chunk.content):
                        self.app.call_from_thread(messages_area.scroll_end, animate=False)

                final_response = accumulated_text

                # Get final usage stats (streaming doesn't provide usage in chunks)
                # We'll estimate or get from cost tracker
                session_info = self.query_one("#session-info", SessionInfoPanel)
                summary = self.provider.get_cost_summary()
                if summary:
                    self.app.call_from_thread(
                        session_info.update_info,
                        tokens=summary.total_input_tokens + summary.total_output_tokens,
                        cost=summary.total_cost
                    )

            # Update the AI message with final response
            from textual.widgets import Markdown
            self.app.call_from_thread(ai_bubble.remove_children)
            self.app.call_from_thread(
                ai_bubble.mount,
                Label("AI · " + datetime.now().strftime("%H:%M:%S"), classes="message-header")
            )
            self.app.call_from_thread(ai_bubble.mount, Markdown(final_response))
            self.app.call_from_thread(messages_area.scroll_end, animate=False)

            # Add to session
            self.session_manager.add_user_message(user_message)
            self.session_manager.add_assistant_message(
                final_response,
                model=self.config.providers.default,
                cost=0.0  # Will be updated by session manager
            )

        except Exception as e:
            # Show error message
            error_message = f"Error: {e!s}"
            self.app.call_from_thread(ai_bubble.remove_children)
            self.app.call_from_thread(
                ai_bubble.mount,
                Label("AI · Error", classes="message-header")
            )
            self.app.call_from_thread(
                ai_bubble.mount,
                Label(f"[red]{error_message}[/red]")
            )

    async def _run_with_tools(self, user_message: str) -> any:
        """Run agent loop with tool support.

        Args:
            user_message: User's message

        Returns:
            Agent result
        """
        messages_area = self.query_one("#messages-area", VerticalScroll)

        # Event callback for tool execution
        def event_handler(event: AgentEvent) -> None:
            if event.event_type == EventType.TOOL_START:
                # Show tool execution indicator
                indicator = ToolExecutionIndicator(tool_name=event.tool_name or "unknown")
                self.current_tool_indicator = indicator
                self.app.call_from_thread(messages_area.mount, indicator)
                self.app.call_from_thread(messages_area.scroll_end, animate=False)

            elif event.event_type == EventType.TOOL_COMPLETE:
                # Remove tool indicator
                if self.current_tool_indicator:
                    self.app.call_from_thread(self.current_tool_indicator.remove)
                    self.current_tool_indicator = None

            elif event.event_type == EventType.TOOL_ERROR:
                # Show error in indicator
                if self.current_tool_indicator:
                    self.app.call_from_thread(self.current_tool_indicator.remove)
                    self.current_tool_indicator = None

                # Add error message
                error_msg = MessageBubble(
                    role="system",
                    content=f"Tool failed: {event.tool_name} - {event.message}"
                )
                self.app.call_from_thread(messages_area.mount, error_msg)

        # Create agent config
        agent_config = AgentConfig(
            approval_mode=ApprovalMode(self.config.agent.tool_approval_mode),
            max_iterations=self.config.agent.max_iterations,
            enable_tools=True,
            allowed_tools=self.config.agent.allowed_tools,
            blocked_tools=self.config.agent.blocked_tools,
        )

        # Create agent loop
        agent = AgentLoop(
            provider_manager=self.provider,
            tool_registry=self.tool_registry,
            config=agent_config,
            event_callback=event_handler,
        )

        # Build messages
        message_dicts = [{"role": "user", "content": user_message}]

        # Run agent
        result = await agent.run(message_dicts, model=self.config.providers.default)

        return result

    @on(Button.Pressed, "#clear-button")
    def on_clear_chat(self) -> None:
        """Handle clear chat button."""
        messages_area = self.query_one("#messages-area", VerticalScroll)
        messages_area.remove_children()

        # Add welcome message back
        messages_area.mount(
            MessageBubble(
                role="system",
                content="Chat cleared. Type a message to start a new conversation.",
            )
        )

        # Clear messages history
        self.messages = []

    @on(Button.Pressed, "#exit-button")
    def on_exit_chat(self) -> None:
        """Handle exit button."""
        self.app.exit(message="Chat session ended")
