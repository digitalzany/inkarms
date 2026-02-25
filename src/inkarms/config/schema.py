"""
Pydantic configuration schema for InkArms.

This module defines all configuration models with validation.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from inkarms.config.defaults import get_security_defaults
from inkarms.config.providers import get_default_model

# =============================================================================
# System Prompt Configuration
# =============================================================================


class SystemPromptConfig(BaseModel):
    """System prompt configuration for AI personality and guardrails."""

    model_config = ConfigDict(extra="allow")

    # Inline configuration
    personality: str | None = None
    boundaries: str | None = None
    user_context: str | None = None

    # File-based configuration (mutually exclusive with inline)
    personality_file: Path | None = None
    boundaries_file: Path | None = None
    user_context_file: Path | None = None



# =============================================================================
# Provider Configuration
# =============================================================================


class ProviderConfig(BaseModel):
    """Provider and model configuration."""

    model_config = ConfigDict(extra="allow")

    default: str = Field(default_factory=get_default_model)
    fallback: list[str] = Field(default_factory=list)
    aliases: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    auto_discover_models: bool = False


# =============================================================================
# Context Management Configuration
# =============================================================================


class CompactionConfig(BaseModel):
    """Context compaction configuration."""

    strategy: Literal["summarize", "truncate", "sliding_window"] = "summarize"
    preserve_recent_turns: int = Field(default=5, ge=1)
    summary_model: str | None = None
    summary_max_tokens: int = 500


class HandoffConfig(BaseModel):
    """Handoff protection configuration."""

    auto_recover: bool = True
    archive_path: str = "~/.inkarms/memory"
    include_full_context: bool = False


class ContextConfig(BaseModel):
    """Context window and memory configuration."""

    model_config = ConfigDict(extra="allow")

    auto_compact_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    handoff_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)
    memory_path: str = "~/.inkarms/memory"
    daily_logs: bool = True
    handoff: HandoffConfig = Field(default_factory=HandoffConfig)
    session_chains: list[list[str]] = Field(
        default_factory=list,
        description=(
            "Groups of channel identifiers that share the same active session. "
            "E.g. [['cli', 'telegram'], ['slack:#dev', 'discord:#dev']]"
        ),
    )


# =============================================================================
# Security Configuration
# =============================================================================


class SandboxConfig(BaseModel):
    """Sandbox execution configuration."""

    enable: bool = True
    mode: Literal["whitelist", "blacklist", "prompt", "disabled"] = "blacklist"


class RestrictedPathsConfig(BaseModel):
    """Path restriction configuration."""

    read_only: list[str] = Field(default_factory=list)
    no_access: list[str] = Field(default_factory=list)


class AuditLogConfig(BaseModel):
    """Audit logging configuration."""

    enable: bool = True
    path: str = "~/.inkarms/audit/audit.jsonl"
    rotation: Literal["daily", "weekly", "size"] = "daily"
    max_size_mb: int = 100
    retention_days: int = Field(default=90, ge=1, le=365)
    compress_old: bool = True
    include_responses: bool = False
    include_queries: bool = True
    hash_queries: bool = False
    redact_paths: bool = True
    redact_patterns: list[str] = Field(default_factory=list)
    buffer_size: int = 100
    flush_interval_seconds: int = 5


def _get_default_whitelist() -> list[str]:
    """Load default whitelist from bundled config."""
    return get_security_defaults().get("whitelist", [])


def _get_default_blacklist() -> dict:
    """Load default blacklist from bundled config."""
    return get_security_defaults().get("blacklist", {})


class BlacklistConfig(BaseModel):
    """Structured command blacklist organized by category."""

    model_config = ConfigDict(extra="allow")

    single_word_commands: list[str] = Field(default_factory=list)
    multi_word_patterns: list[str] = Field(default_factory=list)
    sensitive_paths: list[str] = Field(default_factory=list)
    dangerous_redirects: list[str] = Field(default_factory=list)
    container_patterns: list[str] = Field(default_factory=list)
    command_substitutions: list[str] = Field(default_factory=list)
    dos_patterns: list[str] = Field(default_factory=list)
    pipe_to_interpreters: list[str] = Field(default_factory=list)

    def to_flat_list(self) -> list[str]:
        """Return all patterns as a flat list."""
        return (
            self.single_word_commands
            + self.multi_word_patterns
            + self.sensitive_paths
            + self.dangerous_redirects
            + self.container_patterns
            + self.command_substitutions
            + self.dos_patterns
            + self.pipe_to_interpreters
        )


class SecurityConfig(BaseModel):
    """Security and sandbox configuration."""

    model_config = ConfigDict(extra="allow")

    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    whitelist: list[str] = Field(default_factory=_get_default_whitelist)
    blacklist: BlacklistConfig = Field(
        default_factory=lambda: BlacklistConfig(**_get_default_blacklist())
    )
    restricted_paths: RestrictedPathsConfig = Field(default_factory=RestrictedPathsConfig)
    audit_log: AuditLogConfig = Field(default_factory=AuditLogConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_flat_blacklist(cls, data: dict) -> dict:
        """Convert legacy flat-list blacklist to structured BlacklistConfig format."""
        if not isinstance(data, dict):
            return data
        blacklist = data.get("blacklist")
        if isinstance(blacklist, list):
            # Legacy format: flat list of strings (or dicts with key:comment)
            patterns: list[str] = []
            for item in blacklist:
                if isinstance(item, str):
                    patterns.append(item)
                elif isinstance(item, dict):
                    patterns.extend(item.keys())
            data["blacklist"] = {"multi_word_patterns": patterns}
        return data


# =============================================================================
# Skills Configuration
# =============================================================================


class SkillRegistryConfig(BaseModel):
    """Skill registry configuration (future feature)."""

    url: str = "https://skills.inkarms.io"
    enabled: bool = False


class SmartIndexConfig(BaseModel):
    """Smart skill index configuration."""

    enable: bool = True
    mode: Literal["keyword", "llm", "off"] = "keyword"
    max_skills_per_query: int = Field(default=3, ge=1, le=10)
    index_path: str = "~/.inkarms/skills/index.json"
    llm_model: str | None = None


class SkillAutoUpdateConfig(BaseModel):
    """Skill auto-update configuration."""

    enable: bool = False
    check_interval_hours: int = 24


class SkillsConfig(BaseModel):
    """Skills system configuration."""

    model_config = ConfigDict(extra="allow")

    local_path: str = "~/.inkarms/skills"
    project_path: str = "./.inkarms/skills"
    registry: SkillRegistryConfig = Field(default_factory=SkillRegistryConfig)
    smart_index: SmartIndexConfig = Field(default_factory=SmartIndexConfig)
    auto_update: SkillAutoUpdateConfig = Field(default_factory=SkillAutoUpdateConfig)


# =============================================================================
# Plugin Configuration
# =============================================================================


class PluginsConfig(BaseModel):
    """Plugin system configuration."""

    model_config = ConfigDict(extra="allow")

    enable: bool = True
    local_path: str = "~/.inkarms/plugins"
    config: dict[str, dict] = Field(default_factory=dict)


# =============================================================================
# Cost Configuration
# =============================================================================


class BudgetConfig(BaseModel):
    """Budget limits configuration."""

    daily: float | None = None
    weekly: float | None = None
    monthly: float | None = None


class CostAlertsConfig(BaseModel):
    """Cost alert configuration."""

    warning_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    block_on_exceed: bool = False


class CostConfig(BaseModel):
    """Cost tracking and budgets configuration."""

    model_config = ConfigDict(extra="allow")

    budgets: BudgetConfig = Field(default_factory=BudgetConfig)
    alerts: CostAlertsConfig = Field(default_factory=CostAlertsConfig)


# =============================================================================
# UI Configuration (Unified UI Backend)
# =============================================================================


class UIConfig(BaseModel):
    """Unified UI configuration for pluggable backends."""

    model_config = ConfigDict(extra="allow")

    # Backend selection: "auto" or "rich"
    backend: Literal["auto", "rich"] = "auto"

    # Display settings
    theme: str = "default"
    show_status_bar: bool = True
    show_timestamps: bool = True
    max_messages_display: int = Field(default=20, ge=5, le=100)
    max_recent_sessions: int = Field(default=10, ge=1, le=50)
    enable_mouse: bool = True
    enable_completion: bool = True


# =============================================================================
# Platform Messaging Configuration
# =============================================================================


class WebhookConfig(BaseModel):
    """Webhook server configuration for platform adapters.

    NOTE: Webhooks are OPTIONAL and only needed for advanced deployments.
    For personal use, platforms support polling/WebSocket modes that don't
    require static IPs, domain names, or SSL certificates.
    """

    enable: bool = False  # Disabled by default - not needed for personal use
    host: str = "0.0.0.0"
    port: int = 8000
    base_path: str = "/webhook"
    ssl_cert: str | None = None
    ssl_key: str | None = None
    webhook_secret: str | None = None


class PlatformAdapterConfig(BaseModel):
    """Base configuration for platform adapters."""

    enable: bool = False
    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "polling"
    polling_interval: int = 2
    rate_limit_per_second: int | None = None


class TelegramConfig(PlatformAdapterConfig):
    """Telegram bot configuration.

    Uses long polling by default (recommended for personal use).
    No webhook setup required - works without static IP or domain.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "polling"
    bot_token: str = ""
    allowed_users: list[str] = Field(default_factory=list)
    parse_mode: str = "MarkdownV2"


class SlackConfig(PlatformAdapterConfig):
    """Slack bot configuration.

    Uses Socket Mode by default (WebSocket connection).
    Perfect for personal use - no public URL required.
    Requires both bot_token and app_token for Socket Mode.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "socket"
    bot_token: str = ""
    app_token: str = ""  # Required for Socket Mode
    allowed_channels: list[str] = Field(default_factory=list)


class DiscordConfig(PlatformAdapterConfig):
    """Discord bot configuration.

    Uses Gateway WebSocket connection (standard for Discord bots).
    No webhook required - maintains persistent WebSocket to Discord.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "gateway"
    bot_token: str = ""
    allowed_guilds: list[str] = Field(default_factory=list)
    allowed_channels: list[str] = Field(default_factory=list)
    command_prefix: str = "!"


class WhatsAppConfig(PlatformAdapterConfig):
    """WhatsApp configuration.

    NOTE: Official WhatsApp Business API requires webhooks (complex setup).
    For personal use, consider using community libraries like whatsapp-web.js
    that don't require Business API approval.

    This config is for advanced users only.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "local"
    phone_number_id: str = ""
    access_token: str = ""
    verify_token: str = ""


class IMessageConfig(PlatformAdapterConfig):
    """iMessage configuration (macOS only)."""

    mode: Literal["webhook", "polling", "local"] = "local"
    allowed_numbers: list[str] = Field(default_factory=list)
    apple_script_path: str | None = None


class SignalConfig(PlatformAdapterConfig):
    """Signal messenger configuration."""

    mode: Literal["webhook", "polling", "local"] = "local"
    phone_number: str = ""
    signal_cli_path: str = "/usr/local/bin/signal-cli"
    allowed_numbers: list[str] = Field(default_factory=list)


class TeamsConfig(PlatformAdapterConfig):
    """Microsoft Teams bot configuration.

    Can use WebSocket mode via Bot Framework Direct Line.
    Advanced feature - requires Azure account and bot registration.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "socket"
    app_id: str = ""
    app_password: str = ""
    tenant_id: str = ""


class WeChatConfig(PlatformAdapterConfig):
    """WeChat Official Account configuration.

    NOTE: This is an ADVANCED/OPTIONAL feature.
    Requires Official Account approval (complex process in China).
    Official API requires webhooks.

    For most users, skip this platform.
    """

    mode: Literal["webhook", "polling", "local", "socket", "gateway"] = "webhook"
    app_id: str = ""
    app_secret: str = ""
    token: str = ""
    encoding_aes_key: str = ""


class PlatformsConfig(BaseModel):
    """Multi-platform messaging configuration."""

    model_config = ConfigDict(extra="allow")

    enable: bool = False
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    imessage: IMessageConfig = Field(default_factory=IMessageConfig)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    teams: TeamsConfig = Field(default_factory=TeamsConfig)
    wechat: WeChatConfig = Field(default_factory=WeChatConfig)

    # Security settings
    require_authentication: bool = True
    rate_limit_per_user: int = 10  # messages per minute
    max_concurrent_sessions: int = 100


# =============================================================================
# General Configuration
# =============================================================================


class OutputConfig(BaseModel):
    """Output formatting configuration."""

    format: Literal["rich", "plain", "json"] = "rich"
    color: bool = True
    verbose: bool = False


class StorageConfig(BaseModel):
    """Storage backend configuration."""

    backend: Literal["file", "sqlite"] = "file"
    sqlite_path: str = "~/.inkarms/data.db"


class GeneralConfig(BaseModel):
    """General settings configuration."""

    model_config = ConfigDict(extra="allow")

    default_profile: str | None = None
    output: OutputConfig = Field(default_factory=OutputConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


# =============================================================================
# Profile Metadata
# =============================================================================


class ProfileMeta(BaseModel):
    """Profile metadata."""

    name: str | None = None
    description: str | None = None


# =============================================================================
# Tools Configuration
# =============================================================================


class WebSearchToolConfig(BaseModel):
    """Web search tool configuration."""

    brave_api_key: str = ""


class ToolsConfig(BaseModel):
    """Tool-specific API keys and settings."""

    model_config = ConfigDict(extra="allow")

    web_search: WebSearchToolConfig = Field(default_factory=WebSearchToolConfig)


# =============================================================================
# Agent & Tool Use Configuration
# =============================================================================


class AgentConfigSchema(BaseModel):
    """Agent execution and tool use configuration."""

    model_config = ConfigDict(extra="allow")

    enable_tools: bool = Field(
        default=True,
        description="Enable tool use (function calling)",
    )

    approval_mode: Literal["auto", "manual", "disabled"] = Field(
        default="manual",
        description="Tool approval mode: auto (all tools), manual (dangerous tools need approval), disabled (no tools)",
    )

    max_iterations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum agent loop iterations",
    )

    timeout_per_iteration: int = Field(
        default=300,
        ge=10,
        le=600,
        description="Timeout per iteration in seconds",
    )

    allowed_tools: list[str] | None = Field(
        default=None,
        description="Whitelist of allowed tool names (None = all tools allowed)",
    )

    blocked_tools: list[str] | None = Field(
        default=None,
        description="Blacklist of blocked tool names",
    )


# =============================================================================
# Hub Configuration
# =============================================================================


class HubTriggerRoute(BaseModel):
    """Webhook trigger route — an HTTP POST fires an AI agent action.

    Named "trigger" (not "pipeline" or "webhook") to distinguish from WebhookConfig
    (platform webhook server on port 8000) and to match industry convention
    (GitHub Actions triggers, Zapier triggers).
    """

    name: str
    prompt_template: str  # Placeholders: {body.x.y}, {headers.x}, {query.x}
    session_id: str = "default"
    reply_to: str | None = None  # "telegram:@user", "slack:#channel", or HTTP URL
    shared_secret: str | None = None  # If set, verify HMAC-SHA256 of body
    secret_header: str = "X-Hub-Signature-256"  # Header containing the signature


class CronJobConfig(BaseModel):
    """Scheduled job configuration."""

    id: str
    schedule: str  # cron expression OR "every 5m", "every 1h"
    type: Literal["bash", "ai_query"] = "bash"
    command: str  # bash command (sandboxed) or AI prompt
    session_id: str = "default"
    notify: str | None = None
    enabled: bool = True
    allowed_tools: list[str] | None = None
    # For type=ai_query: restrict tool use.
    # None = no tools (safe default for headless).
    # Explicit list = only those tools allowed.


class HubConfig(BaseModel):
    """InkArms Hub daemon configuration.

    The hub runs platform adapters as persistent background tasks, exposes a
    REST + WebSocket API, manages scheduled AI queries, accepts webhook triggers,
    and optionally proxies OpenAI-compatible requests.

    NOTE: HubConfig.port (default 18750) is the hub API server.
    WebhookConfig.port (default 8000) is the existing platform webhook server.
    These are distinct features — do not confuse them.

    WARNING: trust_localhost=True means any local process can access the hub
    without a key. Set to False on shared systems (VPS, cloud VMs, CI, Docker).
    """

    enable: bool = False
    host: str = "127.0.0.1"
    port: int = 18750
    api_key_name: str = "hub_api_key"  # Key name in SecretsManager — NOT stored here
    trust_localhost: bool = True
    auth_max_failures: int = 20
    auth_window_seconds: int = 60
    auth_lockout_seconds: int = 300
    tool_approval_mode: Literal["auto", "disabled"] = "auto"  # /ws/chat sessions
    cron_tool_approval_mode: Literal["auto", "disabled"] = "disabled"  # ai_query cron jobs
    webhook_tool_approval_mode: Literal["auto", "disabled"] = "disabled"  # trigger routes
    openai_proxy: bool = False
    cron_jobs: list[CronJobConfig] = Field(default_factory=list)
    triggers: list[HubTriggerRoute] = Field(default_factory=list)
    auto_start_platforms: bool = True
    shutdown_timeout: int = 30  # Seconds to wait for in-flight requests on SIGTERM
    max_event_subscribers: int = 50  # Max concurrent /ws/events connections
    ws_ping_interval: int = 30  # Seconds between server-side WS ping frames
    trigger_max_body_bytes: int = 1_048_576  # 1 MB limit on webhook trigger request body
    budget_sync_interval: int = 60  # Seconds between in-memory budget flushes to DB


# =============================================================================
# Root Configuration Model
# =============================================================================


class Config(BaseModel):
    """
    Root configuration model for InkArms.

    This model represents the complete configuration with all sections.
    Configuration can be loaded from YAML files, environment variables,
    and CLI flags, merged in order of priority.
    """

    model_config = ConfigDict(extra="allow")

    # Profile metadata (only in profile/project configs)
    _meta: ProfileMeta | None = None

    # Main configuration sections
    system_prompt: SystemPromptConfig = Field(default_factory=SystemPromptConfig)
    providers: ProviderConfig = Field(default_factory=ProviderConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    agent: AgentConfigSchema = Field(default_factory=AgentConfigSchema)
    context: ContextConfig = Field(default_factory=ContextConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    platforms: PlatformsConfig = Field(default_factory=PlatformsConfig)
    hub: HubConfig = Field(default_factory=HubConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)

    def resolve_model_alias(self, model: str) -> str:
        """Resolve a model name or alias to the full model identifier."""
        return self.providers.aliases.get(model, model)

    def is_sandbox_enabled(self) -> bool:
        """Check if sandbox is enabled."""
        return self.security.sandbox.enable and self.security.sandbox.mode != "disabled"
